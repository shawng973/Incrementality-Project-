import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NarrativeDisplay } from "@/components/results/NarrativeDisplay";
import type { NarrativeResponse } from "@/types";

const mockGenerate = jest.fn();
jest.mock("@/lib/api", () => ({
  api: {
    narrative: {
      generate: (...args: unknown[]) => mockGenerate(...args),
    },
  },
}));

const MOCK_NARRATIVE: NarrativeResponse = {
  test_id: "test-1",
  job_id: "job-1",
  headline: "The test confirmed a 15% revenue lift.",
  body_markdown:
    "## Headline\n**15% lift confirmed.**\n\n## Results\nTWFE estimate: 15.0%\n\n## Recommendation\nIncrease investment.",
  model: "anthropic/claude-sonnet-4-5",
  prompt_tokens: 100,
  completion_tokens: 200,
};

beforeEach(() => {
  mockGenerate.mockClear();
});

describe("NarrativeDisplay — no initial narrative", () => {
  it("shows generate button when no initial narrative", () => {
    render(<NarrativeDisplay testId="test-1" jobId="job-1" />);
    expect(
      screen.getByRole("button", { name: /generate narrative/i })
    ).toBeInTheDocument();
  });

  it("calls api.narrative.generate with testId and jobId on click", async () => {
    mockGenerate.mockResolvedValueOnce(MOCK_NARRATIVE);
    const user = userEvent.setup();
    render(<NarrativeDisplay testId="test-1" jobId="job-1" />);
    await user.click(screen.getByRole("button", { name: /generate narrative/i }));
    expect(mockGenerate).toHaveBeenCalledWith("test-1", "job-1");
  });

  it("renders narrative body after generation", async () => {
    mockGenerate.mockResolvedValueOnce(MOCK_NARRATIVE);
    const user = userEvent.setup();
    render(<NarrativeDisplay testId="test-1" jobId="job-1" />);
    await user.click(screen.getByRole("button", { name: /generate narrative/i }));
    await waitFor(() => {
      expect(screen.getByText("Results")).toBeInTheDocument();
    });
  });

  it("shows error message on generate failure", async () => {
    mockGenerate.mockRejectedValueOnce(new Error("Network error"));
    const user = userEvent.setup();
    render(<NarrativeDisplay testId="test-1" jobId="job-1" />);
    await user.click(screen.getByRole("button", { name: /generate narrative/i }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/failed to generate/i);
    });
  });
});

describe("NarrativeDisplay — with initial narrative", () => {
  it("renders the narrative body immediately", () => {
    render(
      <NarrativeDisplay
        testId="test-1"
        jobId="job-1"
        initial={MOCK_NARRATIVE}
      />
    );
    expect(screen.getByText("Recommendation")).toBeInTheDocument();
  });

  it("shows the model name", () => {
    render(
      <NarrativeDisplay
        testId="test-1"
        jobId="job-1"
        initial={MOCK_NARRATIVE}
      />
    );
    expect(screen.getByText(/claude-sonnet/i)).toBeInTheDocument();
  });

  it("shows the total token count", () => {
    render(
      <NarrativeDisplay
        testId="test-1"
        jobId="job-1"
        initial={MOCK_NARRATIVE}
      />
    );
    expect(screen.getByText(/300 tokens/)).toBeInTheDocument();
  });

  it("shows regenerate button", () => {
    render(
      <NarrativeDisplay
        testId="test-1"
        jobId="job-1"
        initial={MOCK_NARRATIVE}
      />
    );
    expect(
      screen.getByRole("button", { name: /regenerate/i })
    ).toBeInTheDocument();
  });

  it("regenerates on regenerate button click", async () => {
    const updated: NarrativeResponse = { ...MOCK_NARRATIVE, headline: "Updated headline." };
    mockGenerate.mockResolvedValueOnce(updated);
    const user = userEvent.setup();
    render(
      <NarrativeDisplay
        testId="test-1"
        jobId="job-1"
        initial={MOCK_NARRATIVE}
      />
    );
    await user.click(screen.getByRole("button", { name: /regenerate/i }));
    expect(mockGenerate).toHaveBeenCalledTimes(1);
  });

  it("renders ## headings from markdown", () => {
    render(
      <NarrativeDisplay
        testId="test-1"
        jobId="job-1"
        initial={MOCK_NARRATIVE}
      />
    );
    expect(screen.getByText("Headline")).toBeInTheDocument();
    expect(screen.getByText("Results")).toBeInTheDocument();
  });
});
