import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Step1Config } from "@/components/tests/wizard/Step1Config";

function renderStep(onNext = jest.fn()) {
  return { onNext, ...render(<Step1Config onNext={onNext} />) };
}

describe("Step1Config", () => {
  it("renders the test name field", () => {
    renderStep();
    expect(screen.getByLabelText(/test name/i)).toBeInTheDocument();
  });

  it("renders channel, granularity, and n_cells controls", () => {
    renderStep();
    expect(screen.getByLabelText(/channel/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/number of test cells/i)).toBeInTheDocument();
    // Granularity radios
    expect(screen.getByDisplayValue("state")).toBeInTheDocument();
    expect(screen.getByDisplayValue("dma")).toBeInTheDocument();
    expect(screen.getByDisplayValue("zip")).toBeInTheDocument();
  });

  it("defaults test_type to geo_split", () => {
    renderStep();
    expect(
      screen.getByDisplayValue("geo_split") as HTMLInputElement
    ).toBeChecked();
  });

  it("defaults region_granularity to state", () => {
    renderStep();
    expect(
      screen.getByDisplayValue("state") as HTMLInputElement
    ).toBeChecked();
  });

  it("defaults n_cells to 2", () => {
    renderStep();
    expect(
      (screen.getByLabelText(/number of test cells/i) as HTMLSelectElement).value
    ).toBe("2");
  });

  it("shows validation error when name is empty and form is submitted", async () => {
    const user = userEvent.setup();
    renderStep();
    await user.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/required/i);
    });
  });

  it("does not call onNext when name is empty", async () => {
    const user = userEvent.setup();
    const { onNext } = renderStep();
    await user.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => {
      expect(onNext).not.toHaveBeenCalled();
    });
  });

  it("calls onNext with correct data when form is valid", async () => {
    const user = userEvent.setup();
    const { onNext } = renderStep();

    await user.type(screen.getByLabelText(/test name/i), "My CTV Test");
    await user.click(screen.getByRole("button", { name: /next/i }));

    await waitFor(() => {
      expect(onNext).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "My CTV Test",
          test_type: "geo_split",
          region_granularity: "state",
          n_cells: 2,
        })
      );
    });
  });

  it("calls onNext with selected channel", async () => {
    const user = userEvent.setup();
    const { onNext } = renderStep();

    await user.type(screen.getByLabelText(/test name/i), "Test");
    await user.selectOptions(screen.getByLabelText(/channel/i), "ctv");
    await user.click(screen.getByRole("button", { name: /next/i }));

    await waitFor(() => {
      expect(onNext).toHaveBeenCalledWith(
        expect.objectContaining({ channel: "ctv" })
      );
    });
  });

  it("calls onNext with selected granularity dma", async () => {
    const user = userEvent.setup();
    const { onNext } = renderStep();

    await user.type(screen.getByLabelText(/test name/i), "Test");
    await user.click(screen.getByDisplayValue("dma"));
    await user.click(screen.getByRole("button", { name: /next/i }));

    await waitFor(() => {
      expect(onNext).toHaveBeenCalledWith(
        expect.objectContaining({ region_granularity: "dma" })
      );
    });
  });

  it("shows error if name exceeds 120 characters", async () => {
    const user = userEvent.setup();
    renderStep();
    const longName = "a".repeat(121);
    await user.type(screen.getByLabelText(/test name/i), longName);
    await user.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/120/i);
    });
  });

  it("pre-populates fields from defaultValues", () => {
    render(
      <Step1Config
        defaultValues={{ name: "Pre-filled Test", channel: "ctv", n_cells: 3 }}
        onNext={jest.fn()}
      />
    );
    expect(
      (screen.getByLabelText(/test name/i) as HTMLInputElement).value
    ).toBe("Pre-filled Test");
    expect(
      (screen.getByLabelText(/channel/i) as HTMLSelectElement).value
    ).toBe("ctv");
  });
});
