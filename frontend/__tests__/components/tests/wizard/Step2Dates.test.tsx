import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Step2Dates } from "@/components/tests/wizard/Step2Dates";

function renderStep(overrides: { onBack?: jest.Mock; onNext?: jest.Mock } = {}) {
  const onBack = overrides.onBack ?? jest.fn();
  const onNext = overrides.onNext ?? jest.fn();
  return { onBack, onNext, ...render(<Step2Dates onBack={onBack} onNext={onNext} />) };
}

describe("Step2Dates", () => {
  it("renders start date, end date, and cooldown fields", () => {
    renderStep();
    expect(screen.getByLabelText(/start date/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/end date/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/cooldown/i)).toBeInTheDocument();
  });

  it("calls onBack when Back button is clicked", async () => {
    const user = userEvent.setup();
    const { onBack } = renderStep();
    await user.click(screen.getByRole("button", { name: /back/i }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("calls onNext with empty dates when no input (dates are optional)", async () => {
    const user = userEvent.setup();
    const { onNext } = renderStep();
    await user.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => {
      expect(onNext).toHaveBeenCalledWith(
        expect.objectContaining({ start_date: "", end_date: "" })
      );
    });
  });

  it("shows error when end date is before start date", async () => {
    const user = userEvent.setup();
    renderStep();
    // set start_date to a date after end_date
    await user.type(screen.getByLabelText(/start date/i), "2026-06-01");
    await user.type(screen.getByLabelText(/end date/i), "2026-05-01");
    await user.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/end date must be after/i);
    });
  });

  it("does not show error when end date is after start date", async () => {
    const user = userEvent.setup();
    const { onNext } = renderStep();
    await user.type(screen.getByLabelText(/start date/i), "2026-05-01");
    await user.type(screen.getByLabelText(/end date/i), "2026-07-01");
    await user.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(onNext).toHaveBeenCalled();
    });
  });

  it("shows error when cooldown_weeks is negative", async () => {
    const user = userEvent.setup();
    renderStep();
    await user.type(screen.getByLabelText(/cooldown/i), "-1");
    await user.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/negative/i);
    });
  });

  it("shows error when cooldown_weeks exceeds 8", async () => {
    const user = userEvent.setup();
    renderStep();
    await user.type(screen.getByLabelText(/cooldown/i), "9");
    await user.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/8/i);
    });
  });

  it("calls onNext with cooldown value when valid", async () => {
    const user = userEvent.setup();
    const { onNext } = renderStep();
    await user.type(screen.getByLabelText(/cooldown/i), "2");
    await user.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => {
      expect(onNext).toHaveBeenCalledWith(
        expect.objectContaining({ cooldown_weeks: 2 })
      );
    });
  });

  it("pre-populates from defaultValues", () => {
    render(
      <Step2Dates
        defaultValues={{ start_date: "2026-05-01", end_date: "2026-07-01", cooldown_weeks: 2 }}
        onBack={jest.fn()}
        onNext={jest.fn()}
      />
    );
    expect(
      (screen.getByLabelText(/start date/i) as HTMLInputElement).value
    ).toBe("2026-05-01");
    expect(
      (screen.getByLabelText(/end date/i) as HTMLInputElement).value
    ).toBe("2026-07-01");
  });
});
