import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AnalysisTrigger } from "@/components/results/AnalysisTrigger";
import type { AnalysisJob, AnalysisResult } from "@/types";

const mockTrigger = jest.fn();
const mockGetJob = jest.fn();
const mockGetLatest = jest.fn();

jest.mock("@/lib/api", () => ({
  api: {
    analysis: {
      trigger: (...args: unknown[]) => mockTrigger(...args),
      getJob: (...args: unknown[]) => mockGetJob(...args),
      getLatest: (...args: unknown[]) => mockGetLatest(...args),
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

const PENDING_JOB: AnalysisJob = {
  job_id: "job-1",
  test_id: "test-1",
  workspace_id: "ws-1",
  status: "pending",
  message: "",
};

const COMPLETED_JOB: AnalysisJob = {
  ...PENDING_JOB,
  status: "completed",
};

const MOCK_RESULT: AnalysisResult = {
  job_id: "job-1",
  test_id: "test-1",
  status: "completed",
  twfe_treatment_effect: 0.15,
  incremental_revenue_midpoint: 117_500,
};

beforeEach(() => {
  mockTrigger.mockClear();
  mockGetJob.mockClear();
  mockGetLatest.mockClear();
});

describe("AnalysisTrigger — trigger form", () => {
  it("renders the spend input and run button", () => {
    render(<AnalysisTrigger testId="test-1" onComplete={jest.fn()} />);
    expect(screen.getByLabelText(/total test spend/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /run analysis/i })).toBeInTheDocument();
  });

  it("shows error when spend is empty and form submitted", async () => {
    const user = userEvent.setup();
    render(<AnalysisTrigger testId="test-1" onComplete={jest.fn()} />);
    await user.click(screen.getByRole("button", { name: /run analysis/i }));
    expect(screen.getByRole("alert")).toHaveTextContent(/enter.*spend/i);
  });

  it("shows error when spend is zero", async () => {
    const user = userEvent.setup();
    render(<AnalysisTrigger testId="test-1" onComplete={jest.fn()} />);
    await user.type(screen.getByLabelText(/total test spend/i), "0");
    await user.click(screen.getByRole("button", { name: /run analysis/i }));
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("calls api.analysis.trigger with spend and testId", async () => {
    mockTrigger.mockResolvedValueOnce(PENDING_JOB);
    const user = userEvent.setup();
    render(<AnalysisTrigger testId="test-1" onComplete={jest.fn()} />);
    await user.type(screen.getByLabelText(/total test spend/i), "50000");
    await user.click(screen.getByRole("button", { name: /run analysis/i }));
    await waitFor(() => {
      expect(mockTrigger).toHaveBeenCalledWith("test-1", {
        spend: 50000,
        has_prior_year: false,
      });
    });
  });

  it("includes has_prior_year when checkbox is checked", async () => {
    mockTrigger.mockResolvedValueOnce(PENDING_JOB);
    const user = userEvent.setup();
    render(<AnalysisTrigger testId="test-1" onComplete={jest.fn()} />);
    await user.type(screen.getByLabelText(/total test spend/i), "50000");
    await user.click(screen.getByLabelText(/prior-year/i));
    await user.click(screen.getByRole("button", { name: /run analysis/i }));
    await waitFor(() => {
      expect(mockTrigger).toHaveBeenCalledWith("test-1", {
        spend: 50000,
        has_prior_year: true,
      });
    });
  });

  it("shows 422 error as upload-required message", async () => {
    const { ApiError } = jest.requireMock("@/lib/api");
    mockTrigger.mockRejectedValueOnce(new ApiError(422, "No upload"));
    const user = userEvent.setup();
    render(<AnalysisTrigger testId="test-1" onComplete={jest.fn()} />);
    await user.type(screen.getByLabelText(/total test spend/i), "50000");
    await user.click(screen.getByRole("button", { name: /run analysis/i }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/upload historical data/i);
    });
  });
});

describe("AnalysisTrigger — running job", () => {
  it("shows running state when activeJob is pending", () => {
    render(
      <AnalysisTrigger
        testId="test-1"
        onComplete={jest.fn()}
        activeJob={PENDING_JOB}
      />
    );
    expect(screen.getByText(/analysis in progress/i)).toBeInTheDocument();
  });

  it("calls onComplete when job transitions to completed", async () => {
    mockGetJob.mockResolvedValueOnce(COMPLETED_JOB);
    mockGetLatest.mockResolvedValueOnce(MOCK_RESULT);
    const onComplete = jest.fn();

    render(
      <AnalysisTrigger
        testId="test-1"
        onComplete={onComplete}
        activeJob={PENDING_JOB}
      />
    );

    await waitFor(() => {
      expect(onComplete).toHaveBeenCalledWith(MOCK_RESULT);
    }, { timeout: 5000 });
  });
});

describe("AnalysisTrigger — failed job", () => {
  const failedJob: AnalysisJob = { ...PENDING_JOB, status: "failed", message: "Pipeline error" };

  it("shows failed state", () => {
    render(
      <AnalysisTrigger
        testId="test-1"
        onComplete={jest.fn()}
        activeJob={failedJob}
      />
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/pipeline error/i)).toBeInTheDocument();
  });

  it("returns to trigger form when Try again is clicked", async () => {
    const user = userEvent.setup();
    render(
      <AnalysisTrigger
        testId="test-1"
        onComplete={jest.fn()}
        activeJob={failedJob}
      />
    );
    await user.click(screen.getByRole("button", { name: /try again/i }));
    expect(screen.getByLabelText(/total test spend/i)).toBeInTheDocument();
  });
});
