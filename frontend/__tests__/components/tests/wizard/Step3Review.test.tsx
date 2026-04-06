import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Step3Review } from "@/components/tests/wizard/Step3Review";
import type { Step1Data } from "@/components/tests/wizard/Step1Config";
import type { Step2Data } from "@/components/tests/wizard/Step2Dates";

const step1: Step1Data = {
  name: "Q1 CTV Test",
  test_type: "geo_split",
  channel: "ctv",
  region_granularity: "state",
  n_cells: 2,
};

const step2: Step2Data = {
  start_date: "2026-05-01",
  end_date: "2026-07-31",
  cooldown_weeks: 2,
};

function renderReview(overrides: Partial<{
  step1: Step1Data;
  step2: Step2Data;
  isSubmitting: boolean;
  error: string | null;
  onBack: jest.Mock;
  onSubmit: jest.Mock;
}> = {}) {
  const props = {
    step1,
    step2,
    isSubmitting: false,
    error: null,
    onBack: jest.fn(),
    onSubmit: jest.fn(),
    ...overrides,
  };
  return { ...props, ...render(<Step3Review {...props} />) };
}

describe("Step3Review", () => {
  it("displays the test name", () => {
    renderReview();
    expect(screen.getByText("Q1 CTV Test")).toBeInTheDocument();
  });

  it("displays the test type label", () => {
    renderReview();
    expect(screen.getByText("Geo Split")).toBeInTheDocument();
  });

  it("displays the channel label", () => {
    renderReview();
    expect(screen.getByText("CTV")).toBeInTheDocument();
  });

  it("displays the region granularity label", () => {
    renderReview();
    expect(screen.getByText("State")).toBeInTheDocument();
  });

  it("displays the number of cells", () => {
    renderReview();
    expect(screen.getByText("2 cells")).toBeInTheDocument();
  });

  it("displays the start date", () => {
    renderReview();
    expect(screen.getByText("2026-05-01")).toBeInTheDocument();
  });

  it("displays the end date", () => {
    renderReview();
    expect(screen.getByText("2026-07-31")).toBeInTheDocument();
  });

  it("displays cooldown weeks", () => {
    renderReview();
    expect(screen.getByText("2 weeks")).toBeInTheDocument();
  });

  it("shows 'Not set' for missing channel", () => {
    renderReview({ step1: { ...step1, channel: undefined } });
    expect(screen.getAllByText(/not set/i).length).toBeGreaterThan(0);
  });

  it("shows 'None' for missing cooldown", () => {
    renderReview({ step2: { ...step2, cooldown_weeks: undefined } });
    expect(screen.getByText(/none/i)).toBeInTheDocument();
  });

  it("renders description when provided", () => {
    renderReview({ step1: { ...step1, description: "CTV heavy-up test in western US" } });
    expect(screen.getByText("CTV heavy-up test in western US")).toBeInTheDocument();
  });

  it("does not render description row when absent", () => {
    renderReview({ step1: { ...step1, description: undefined } });
    expect(screen.queryByText(/description/i)).not.toBeInTheDocument();
  });

  it("calls onBack when Back is clicked", async () => {
    const user = userEvent.setup();
    const { onBack } = renderReview();
    await user.click(screen.getByRole("button", { name: /back/i }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("calls onSubmit when Create test is clicked", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderReview();
    await user.click(screen.getByRole("button", { name: /create test/i }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("shows loading state on Create button when isSubmitting", () => {
    renderReview({ isSubmitting: true });
    expect(screen.getByRole("button", { name: /create test/i })).toBeDisabled();
  });

  it("shows error message when error prop is set", () => {
    renderReview({ error: "Something went wrong creating your test." });
    expect(
      screen.getByRole("alert")
    ).toHaveTextContent("Something went wrong creating your test.");
  });

  it("does not show error when error is null", () => {
    renderReview({ error: null });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("disables Back button while submitting", () => {
    renderReview({ isSubmitting: true });
    expect(screen.getByRole("button", { name: /back/i })).toBeDisabled();
  });
});
