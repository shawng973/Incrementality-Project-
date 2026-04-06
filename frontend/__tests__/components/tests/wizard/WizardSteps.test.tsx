import { render, screen } from "@testing-library/react";
import { WizardSteps } from "@/components/tests/wizard/WizardSteps";

const STEPS = [
  { index: 1, label: "Setup" },
  { index: 2, label: "Dates" },
  { index: 3, label: "Review" },
];

describe("WizardSteps", () => {
  it("renders all step labels", () => {
    render(<WizardSteps steps={STEPS} currentStep={0} />);
    expect(screen.getByText("Setup")).toBeInTheDocument();
    expect(screen.getByText("Dates")).toBeInTheDocument();
    expect(screen.getByText("Review")).toBeInTheDocument();
  });

  it("marks the current step with aria-current=step", () => {
    render(<WizardSteps steps={STEPS} currentStep={1} />);
    const stepCircles = screen.getAllByRole("generic").filter(
      (el) => el.getAttribute("aria-current") === "step"
    );
    expect(stepCircles).toHaveLength(1);
  });

  it("shows step numbers for incomplete steps", () => {
    render(<WizardSteps steps={STEPS} currentStep={0} />);
    // Step 2 and 3 are not complete — they show their index numbers
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("shows a check icon for completed steps (not the number)", () => {
    render(<WizardSteps steps={STEPS} currentStep={2} />);
    // Step 1 and 2 are complete — their numbers should not be visible as text
    // (they're replaced by check icons)
    const stepCircles = screen.queryByText("1");
    expect(stepCircles).not.toBeInTheDocument();
  });

  it("applies active styling to the current step label", () => {
    render(<WizardSteps steps={STEPS} currentStep={1} />);
    const datesLabel = screen.getByText("Dates");
    expect(datesLabel).toHaveClass("text-brand-600");
  });

  it("renders connector lines between steps", () => {
    const { container } = render(<WizardSteps steps={STEPS} currentStep={0} />);
    // 2 connectors for 3 steps
    const connectors = container.querySelectorAll(".h-0\\.5");
    expect(connectors).toHaveLength(2);
  });
});
