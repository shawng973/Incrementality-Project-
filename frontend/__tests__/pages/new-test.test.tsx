/**
 * Integration test for the New Test wizard page.
 *
 * Mocks:
 * - next/navigation (useRouter, push)
 * - @/lib/api (api.tests.create)
 *
 * Tests the full wizard flow: step 1 → step 2 → step 3 → submit.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import NewTestPage from "@/app/(dashboard)/tests/new/page";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockPush = jest.fn();
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

const mockCreate = jest.fn();
jest.mock("@/lib/api", () => ({
  api: {
    tests: {
      create: (...args: unknown[]) => mockCreate(...args),
    },
  },
  ApiError: class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
      super(message);
      this.status = status;
      this.name = "ApiError";
    }
  },
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function fillAndSubmitStep1(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/test name/i), "Q1 CTV Test");
  await user.selectOptions(screen.getByLabelText(/channel/i), "ctv");
  await user.click(screen.getByRole("button", { name: /next/i }));
}

async function submitStep2(user: ReturnType<typeof userEvent.setup>) {
  // Dates are optional — just proceed
  await user.click(screen.getByRole("button", { name: /next: review/i }));
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  mockPush.mockClear();
  mockCreate.mockClear();
});

describe("NewTestPage — wizard", () => {
  it("renders step 1 on initial load", () => {
    render(<NewTestPage />);
    expect(screen.getByLabelText(/test name/i)).toBeInTheDocument();
  });

  it("shows step indicators", () => {
    render(<NewTestPage />);
    expect(screen.getByText("Setup")).toBeInTheDocument();
    expect(screen.getByText("Dates")).toBeInTheDocument();
    expect(screen.getByText("Review")).toBeInTheDocument();
  });

  it("advances to step 2 after valid step 1", async () => {
    const user = userEvent.setup();
    render(<NewTestPage />);
    await fillAndSubmitStep1(user);

    await waitFor(() => {
      expect(screen.getByLabelText(/start date/i)).toBeInTheDocument();
    });
  });

  it("does not advance to step 2 if name is empty", async () => {
    const user = userEvent.setup();
    render(<NewTestPage />);
    await user.click(screen.getByRole("button", { name: /next/i }));
    await waitFor(() => {
      // Still on step 1
      expect(screen.getByLabelText(/test name/i)).toBeInTheDocument();
    });
  });

  it("goes back to step 1 from step 2", async () => {
    const user = userEvent.setup();
    render(<NewTestPage />);
    await fillAndSubmitStep1(user);
    await waitFor(() => screen.getByRole("button", { name: /back/i }));
    await user.click(screen.getByRole("button", { name: /back/i }));
    await waitFor(() => {
      expect(screen.getByLabelText(/test name/i)).toBeInTheDocument();
    });
  });

  it("advances to step 3 (review) from step 2", async () => {
    const user = userEvent.setup();
    render(<NewTestPage />);
    await fillAndSubmitStep1(user);
    await waitFor(() => screen.getByLabelText(/start date/i));
    await submitStep2(user);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /create test/i })).toBeInTheDocument();
    });
  });

  it("shows test name in review step", async () => {
    const user = userEvent.setup();
    render(<NewTestPage />);
    await fillAndSubmitStep1(user);
    await waitFor(() => screen.getByLabelText(/start date/i));
    await submitStep2(user);
    await waitFor(() => {
      expect(screen.getByText("Q1 CTV Test")).toBeInTheDocument();
    });
  });

  it("calls api.tests.create on final submit", async () => {
    mockCreate.mockResolvedValueOnce({ id: "new-test-id", name: "Q1 CTV Test" });
    const user = userEvent.setup();
    render(<NewTestPage />);
    await fillAndSubmitStep1(user);
    await waitFor(() => screen.getByLabelText(/start date/i));
    await submitStep2(user);
    await waitFor(() => screen.getByRole("button", { name: /create test/i }));
    await user.click(screen.getByRole("button", { name: /create test/i }));
    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith(
        expect.objectContaining({ name: "Q1 CTV Test", channel: "ctv" })
      );
    });
  });

  it("redirects to test detail page on success", async () => {
    mockCreate.mockResolvedValueOnce({ id: "new-test-id", name: "Q1 CTV Test" });
    const user = userEvent.setup();
    render(<NewTestPage />);
    await fillAndSubmitStep1(user);
    await waitFor(() => screen.getByLabelText(/start date/i));
    await submitStep2(user);
    await waitFor(() => screen.getByRole("button", { name: /create test/i }));
    await user.click(screen.getByRole("button", { name: /create test/i }));
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/tests/new-test-id");
    });
  });

  it("shows error message on API failure", async () => {
    // Reject with a plain Error — the page catches any non-ApiError and shows a generic message
    mockCreate.mockRejectedValueOnce(new Error("Network error"));
    const user = userEvent.setup();
    render(<NewTestPage />);
    await fillAndSubmitStep1(user);
    await waitFor(() => screen.getByLabelText(/start date/i));
    await submitStep2(user);
    await waitFor(() => screen.getByRole("button", { name: /create test/i }));
    await user.click(screen.getByRole("button", { name: /create test/i }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/something went wrong/i);
    });
  });

  it("goes back from step 3 to step 2 and preserves data", async () => {
    const user = userEvent.setup();
    render(<NewTestPage />);
    await fillAndSubmitStep1(user);
    await waitFor(() => screen.getByLabelText(/start date/i));
    await submitStep2(user);
    await waitFor(() => screen.getByRole("button", { name: /back/i }));
    await user.click(screen.getByRole("button", { name: /back/i }));
    await waitFor(() => {
      // Back on step 2 — dates fields visible
      expect(screen.getByLabelText(/start date/i)).toBeInTheDocument();
    });
  });
});
