import { render, screen } from "@testing-library/react";
import { Badge, TestStatusBadge, JobStatusBadge } from "@/components/ui/badge";

describe("Badge", () => {
  it("renders children text", () => {
    render(<Badge>Hello</Badge>);
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("defaults to neutral variant", () => {
    render(<Badge>neutral</Badge>);
    expect(screen.getByText("neutral")).toHaveClass("bg-gray-100");
  });

  it("applies active variant", () => {
    render(<Badge variant="active">Active</Badge>);
    expect(screen.getByText("Active")).toHaveClass("bg-blue-100");
  });

  it("applies completed variant", () => {
    render(<Badge variant="completed">Done</Badge>);
    expect(screen.getByText("Done")).toHaveClass("bg-green-100");
  });

  it("applies failed variant", () => {
    render(<Badge variant="failed">Error</Badge>);
    expect(screen.getByText("Error")).toHaveClass("bg-red-100");
  });

  it("applies custom className", () => {
    render(<Badge className="ml-2">Custom</Badge>);
    expect(screen.getByText("Custom")).toHaveClass("ml-2");
  });
});

describe("TestStatusBadge", () => {
  it("renders Draft for draft status", () => {
    render(<TestStatusBadge status="draft" />);
    expect(screen.getByText("Draft")).toBeInTheDocument();
  });

  it("renders Active for active status", () => {
    render(<TestStatusBadge status="active" />);
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("renders Completed for completed status", () => {
    render(<TestStatusBadge status="completed" />);
    expect(screen.getByText("Completed")).toBeInTheDocument();
  });
});

describe("JobStatusBadge", () => {
  it("renders Queued for pending status", () => {
    render(<JobStatusBadge status="pending" />);
    expect(screen.getByText("Queued")).toBeInTheDocument();
  });

  it("renders Running for running status", () => {
    render(<JobStatusBadge status="running" />);
    expect(screen.getByText("Running")).toBeInTheDocument();
  });

  it("renders Failed for failed status", () => {
    render(<JobStatusBadge status="failed" />);
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });
});
