import { render, screen } from "@testing-library/react";
import { TestCard } from "@/components/tests/TestCard";
import type { Test } from "@/types";

// TestCard uses next/link — jest maps it via next/jest config automatically.

const baseTest: Test = {
  id: "test-uuid-001",
  workspace_id: "ws-uuid-001",
  name: "Q1 CTV Geo Split",
  test_type: "geo_split",
  status: "draft",
  region_granularity: "state",
  primary_metric: "revenue",
  n_cells: 2,
  created_at: "2026-01-15T10:00:00Z",
  updated_at: "2026-01-15T10:00:00Z",
};

describe("TestCard", () => {
  it("renders the test name", () => {
    render(<TestCard test={baseTest} />);
    expect(screen.getByText("Q1 CTV Geo Split")).toBeInTheDocument();
  });

  it("renders the status badge", () => {
    render(<TestCard test={baseTest} />);
    expect(screen.getByText("Draft")).toBeInTheDocument();
  });

  it("renders active status badge", () => {
    render(<TestCard test={{ ...baseTest, status: "active" }} />);
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("renders the region granularity", () => {
    render(<TestCard test={baseTest} />);
    expect(screen.getByText("State-level")).toBeInTheDocument();
  });

  it("renders DMA granularity", () => {
    render(<TestCard test={{ ...baseTest, region_granularity: "dma" }} />);
    expect(screen.getByText("DMA-level")).toBeInTheDocument();
  });

  it("renders the number of cells", () => {
    render(<TestCard test={baseTest} />);
    expect(screen.getByText("2 cells")).toBeInTheDocument();
  });

  it("renders the channel when provided", () => {
    render(<TestCard test={{ ...baseTest, channel: "ctv" }} />);
    expect(screen.getByText("CTV")).toBeInTheDocument();
  });

  it("renders raw channel slug when not in label map", () => {
    render(<TestCard test={{ ...baseTest, channel: "email" }} />);
    expect(screen.getByText("email")).toBeInTheDocument();
  });

  it("does not render channel when absent", () => {
    render(<TestCard test={baseTest} />);
    expect(screen.queryByText("CTV")).not.toBeInTheDocument();
  });

  it("renders the description when provided", () => {
    render(
      <TestCard test={{ ...baseTest, description: "Testing CTV in western states" }} />
    );
    expect(
      screen.getByText("Testing CTV in western states")
    ).toBeInTheDocument();
  });

  it("links to the test detail page", () => {
    render(<TestCard test={baseTest} />);
    const link = screen.getByRole("link", { name: /View test: Q1 CTV Geo Split/i });
    expect(link).toHaveAttribute("href", `/tests/${baseTest.id}`);
  });

  it("renders the created date in human-readable form", () => {
    render(<TestCard test={baseTest} />);
    expect(screen.getByText("Jan 15, 2026")).toBeInTheDocument();
  });
});
