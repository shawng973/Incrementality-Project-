import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UploadSection } from "@/components/uploads/UploadSection";
import type { CsvUpload } from "@/types";

const mockUpload = jest.fn();
jest.mock("@/lib/api", () => ({
  api: {
    uploads: {
      upload: (...args: unknown[]) => mockUpload(...args),
    },
  },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, msg: string) {
      super(msg);
      this.status = status;
      this.name = "ApiError";
    }
  },
}));

const MOCK_UPLOAD_RESPONSE: CsvUpload = {
  id: "upload-1",
  test_id: "test-1",
  workspace_id: "ws-1",
  upload_type: "historical",
  filename: "data.csv",
  storage_path: "workspaces/ws-1/tests/test-1/historical/data.csv",
  row_count: 50,
  geo_count: 10,
  period_count: 12,
  column_mapping: { region: "region", period: "period", metric: "metric" },
  validation_warnings: [],
  uploaded_at: "2026-04-01T10:00:00Z",
};

function makeFile(name = "data.csv") {
  return new File(["region,period,metric\nCA,2025-01-01,100"], name, { type: "text/csv" });
}

beforeEach(() => mockUpload.mockClear());

describe("UploadSection", () => {
  it("renders the section heading for historical type", () => {
    render(<UploadSection testId="test-1" />);
    expect(screen.getByText(/historical baseline data/i)).toBeInTheDocument();
  });

  it("renders the section heading for results type", () => {
    render(<UploadSection testId="test-1" uploadType="results" />);
    expect(screen.getByText(/post-test results data/i)).toBeInTheDocument();
  });

  it("shows the dropzone initially", () => {
    render(<UploadSection testId="test-1" />);
    expect(screen.getByRole("button", { name: /csv drop zone/i })).toBeInTheDocument();
  });

  it("shows Upload button after file selection", async () => {
    const user = userEvent.setup();
    render(<UploadSection testId="test-1" />);
    await user.upload(screen.getByTestId("csv-file-input"), makeFile());
    expect(screen.getByRole("button", { name: /^upload$/i })).toBeInTheDocument();
  });

  it("calls api.uploads.upload with the file on submit", async () => {
    mockUpload.mockResolvedValueOnce(MOCK_UPLOAD_RESPONSE);
    const user = userEvent.setup();
    render(<UploadSection testId="test-1" />);
    await user.upload(screen.getByTestId("csv-file-input"), makeFile());
    await user.click(screen.getByRole("button", { name: /^upload$/i }));
    await waitFor(() => {
      expect(mockUpload).toHaveBeenCalledWith("test-1", expect.objectContaining({ name: "data.csv" }), "historical");
    });
  });

  it("shows success stats after successful upload", async () => {
    mockUpload.mockResolvedValueOnce(MOCK_UPLOAD_RESPONSE);
    const user = userEvent.setup();
    render(<UploadSection testId="test-1" />);
    await user.upload(screen.getByTestId("csv-file-input"), makeFile());
    await user.click(screen.getByRole("button", { name: /^upload$/i }));
    await waitFor(() => {
      expect(screen.getByText(/upload successful/i)).toBeInTheDocument();
    });
  });

  it("shows row count in success state", async () => {
    mockUpload.mockResolvedValueOnce(MOCK_UPLOAD_RESPONSE);
    const user = userEvent.setup();
    render(<UploadSection testId="test-1" />);
    await user.upload(screen.getByTestId("csv-file-input"), makeFile());
    await user.click(screen.getByRole("button", { name: /^upload$/i }));
    await waitFor(() => {
      expect(screen.getByText(/50/)).toBeInTheDocument();
    });
  });

  it("calls onUploaded callback after success", async () => {
    mockUpload.mockResolvedValueOnce(MOCK_UPLOAD_RESPONSE);
    const onUploaded = jest.fn();
    const user = userEvent.setup();
    render(<UploadSection testId="test-1" onUploaded={onUploaded} />);
    await user.upload(screen.getByTestId("csv-file-input"), makeFile());
    await user.click(screen.getByRole("button", { name: /^upload$/i }));
    await waitFor(() => {
      expect(onUploaded).toHaveBeenCalledWith(MOCK_UPLOAD_RESPONSE);
    });
  });

  it("shows validation errors on 422 response", async () => {
    const { ApiError } = jest.requireMock("@/lib/api");
    mockUpload.mockRejectedValueOnce(
      new ApiError(422, JSON.stringify({ errors: ["Required column 'metric' is missing."] }))
    );
    const user = userEvent.setup();
    render(<UploadSection testId="test-1" />);
    await user.upload(screen.getByTestId("csv-file-input"), makeFile());
    await user.click(screen.getByRole("button", { name: /^upload$/i }));
    await waitFor(() => {
      expect(screen.getByText(/required column 'metric' is missing/i)).toBeInTheDocument();
    });
  });

  it("shows Try a different file button on error", async () => {
    const { ApiError } = jest.requireMock("@/lib/api");
    mockUpload.mockRejectedValueOnce(new ApiError(422, JSON.stringify({ errors: ["Bad file."] })));
    const user = userEvent.setup();
    render(<UploadSection testId="test-1" />);
    await user.upload(screen.getByTestId("csv-file-input"), makeFile());
    await user.click(screen.getByRole("button", { name: /^upload$/i }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /try a different file/i })).toBeInTheDocument();
    });
  });

  it("returns to idle state when Try a different file is clicked", async () => {
    const { ApiError } = jest.requireMock("@/lib/api");
    mockUpload.mockRejectedValueOnce(new ApiError(422, JSON.stringify({ errors: ["Bad file."] })));
    const user = userEvent.setup();
    render(<UploadSection testId="test-1" />);
    await user.upload(screen.getByTestId("csv-file-input"), makeFile());
    await user.click(screen.getByRole("button", { name: /^upload$/i }));
    await waitFor(() => screen.getByRole("button", { name: /try a different file/i }));
    await user.click(screen.getByRole("button", { name: /try a different file/i }));
    expect(screen.getByRole("button", { name: /csv drop zone/i })).toBeInTheDocument();
  });

  it("shows validation warnings from the upload response", async () => {
    mockUpload.mockResolvedValueOnce({
      ...MOCK_UPLOAD_RESPONSE,
      validation_warnings: ["3 rows have missing spend values."],
    });
    const user = userEvent.setup();
    render(<UploadSection testId="test-1" />);
    await user.upload(screen.getByTestId("csv-file-input"), makeFile());
    await user.click(screen.getByRole("button", { name: /^upload$/i }));
    await waitFor(() => {
      expect(screen.getByText(/3 rows have missing spend values/i)).toBeInTheDocument();
    });
  });
});
