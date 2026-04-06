import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CsvDropzone } from "@/components/uploads/CsvDropzone";

function makeFile(name = "data.csv", type = "text/csv") {
  return new File(["region,period,metric\nCA,2025-01-01,100"], name, { type });
}

describe("CsvDropzone — idle state", () => {
  it("renders the drop zone", () => {
    render(<CsvDropzone onFileSelected={jest.fn()} />);
    expect(screen.getByRole("button", { name: /csv drop zone/i })).toBeInTheDocument();
    expect(screen.getByText(/drop a csv file/i)).toBeInTheDocument();
  });

  it("shows 50 MB size hint", () => {
    render(<CsvDropzone onFileSelected={jest.fn()} />);
    expect(screen.getByText(/50 mb/i)).toBeInTheDocument();
  });

  it("calls onFileSelected when a CSV is picked via input", async () => {
    const user = userEvent.setup();
    const onFileSelected = jest.fn();
    render(<CsvDropzone onFileSelected={onFileSelected} />);
    await user.upload(screen.getByTestId("csv-file-input"), makeFile());
    expect(onFileSelected).toHaveBeenCalledWith(expect.objectContaining({ name: "data.csv" }));
  });

  it("does not call onFileSelected for non-CSV files", async () => {
    const user = userEvent.setup();
    const onFileSelected = jest.fn();
    render(<CsvDropzone onFileSelected={onFileSelected} />);
    await user.upload(
      screen.getByTestId("csv-file-input"),
      makeFile("report.xlsx", "application/vnd.ms-excel")
    );
    expect(onFileSelected).not.toHaveBeenCalled();
  });

  it("applies drag-over styles on dragover", () => {
    render(<CsvDropzone onFileSelected={jest.fn()} />);
    const zone = screen.getByRole("button", { name: /csv drop zone/i });
    fireEvent.dragOver(zone);
    expect(zone).toHaveClass("border-brand-400");
  });

  it("removes drag-over styles on dragleave", () => {
    render(<CsvDropzone onFileSelected={jest.fn()} />);
    const zone = screen.getByRole("button", { name: /csv drop zone/i });
    fireEvent.dragOver(zone);
    fireEvent.dragLeave(zone);
    expect(zone).not.toHaveClass("border-brand-400");
  });

  it("calls onFileSelected on drop of a CSV", () => {
    const onFileSelected = jest.fn();
    render(<CsvDropzone onFileSelected={onFileSelected} />);
    fireEvent.drop(screen.getByRole("button", { name: /csv drop zone/i }), {
      dataTransfer: { files: [makeFile()] },
    });
    expect(onFileSelected).toHaveBeenCalledWith(expect.objectContaining({ name: "data.csv" }));
  });

  it("does not call onFileSelected on drop of a non-CSV", () => {
    const onFileSelected = jest.fn();
    render(<CsvDropzone onFileSelected={onFileSelected} />);
    fireEvent.drop(screen.getByRole("button", { name: /csv drop zone/i }), {
      dataTransfer: { files: [makeFile("file.xlsx", "application/vnd.ms-excel")] },
    });
    expect(onFileSelected).not.toHaveBeenCalled();
  });

  it("ignores drops when disabled", () => {
    const onFileSelected = jest.fn();
    render(<CsvDropzone onFileSelected={onFileSelected} disabled />);
    fireEvent.drop(screen.getByRole("button", { name: /csv drop zone/i }), {
      dataTransfer: { files: [makeFile()] },
    });
    expect(onFileSelected).not.toHaveBeenCalled();
  });

  it("shows opacity-50 when disabled", () => {
    render(<CsvDropzone onFileSelected={jest.fn()} disabled />);
    expect(screen.getByRole("button", { name: /csv drop zone/i })).toHaveClass("opacity-50");
  });
});

describe("CsvDropzone — selected file state", () => {
  it("shows the selected filename", () => {
    render(<CsvDropzone onFileSelected={jest.fn()} selectedFile={makeFile("my_data.csv")} />);
    expect(screen.getByText("my_data.csv")).toBeInTheDocument();
  });

  it("shows clear button when onClear is provided", () => {
    render(
      <CsvDropzone onFileSelected={jest.fn()} selectedFile={makeFile()} onClear={jest.fn()} />
    );
    expect(screen.getByRole("button", { name: /remove selected file/i })).toBeInTheDocument();
  });

  it("calls onClear when clear button is clicked", async () => {
    const user = userEvent.setup();
    const onClear = jest.fn();
    render(
      <CsvDropzone onFileSelected={jest.fn()} selectedFile={makeFile()} onClear={onClear} />
    );
    await user.click(screen.getByRole("button", { name: /remove selected file/i }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });
});
