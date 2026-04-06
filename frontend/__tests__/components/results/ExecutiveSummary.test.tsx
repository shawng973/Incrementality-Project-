import { render, screen } from "@testing-library/react";
import { ExecutiveSummary } from "@/components/results/ExecutiveSummary";
import type { AnalysisResult } from "@/types";

const baseResult: AnalysisResult = {
  job_id: "job-1",
  test_id: "test-1",
  status: "completed",
  twfe_treatment_effect: 0.15,
  twfe_treatment_effect_dollars: 120_000,
  twfe_p_value: 0.02,
  twfe_ci_95: { lower: 0.08, upper: 0.22 },
  incremental_revenue_midpoint: 117_500,
  roas_low: 1.8,
  roas_mid: 2.35,
  roas_high: 2.9,
  total_spend: 50_000,
  power_analysis_json: { power: 0.85, is_adequately_powered: true },
};

describe("ExecutiveSummary", () => {
  it("shows significant result banner for p < 0.05", () => {
    render(<ExecutiveSummary result={baseResult} />);
    expect(
      screen.getByText(/statistically significant/i)
    ).toBeInTheDocument();
  });

  it("shows non-significant banner for p >= 0.05", () => {
    render(
      <ExecutiveSummary result={{ ...baseResult, twfe_p_value: 0.12 }} />
    );
    expect(screen.getByText(/not statistically significant/i)).toBeInTheDocument();
  });

  it("displays the p-value in the banner", () => {
    render(<ExecutiveSummary result={baseResult} />);
    expect(screen.getByText(/p = 0\.020/i)).toBeInTheDocument();
  });

  it("displays the lift percentage", () => {
    render(<ExecutiveSummary result={baseResult} />);
    expect(screen.getByText("15.0%")).toBeInTheDocument();
  });

  it("displays the incremental revenue", () => {
    render(<ExecutiveSummary result={baseResult} />);
    expect(screen.getByText("$117,500")).toBeInTheDocument();
  });

  it("displays the ROAS mid value", () => {
    render(<ExecutiveSummary result={baseResult} />);
    expect(screen.getByText("2.35x")).toBeInTheDocument();
  });

  it("displays the total spend", () => {
    render(<ExecutiveSummary result={baseResult} />);
    expect(screen.getByText("$50,000")).toBeInTheDocument();
  });

  it("does not show power warning when adequately powered", () => {
    render(<ExecutiveSummary result={baseResult} />);
    expect(screen.queryByText(/underpowered/i)).not.toBeInTheDocument();
  });

  it("shows power warning when underpowered", () => {
    render(
      <ExecutiveSummary
        result={{
          ...baseResult,
          power_analysis_json: {
            power: 0.45,
            is_adequately_powered: false,
            warning_message: "Extend test by 4 weeks.",
          },
        }}
      />
    );
    expect(screen.getByText(/underpowered/i)).toBeInTheDocument();
    expect(screen.getByText(/extend test by 4 weeks/i)).toBeInTheDocument();
  });

  it("shows em dash when a value is missing", () => {
    render(
      <ExecutiveSummary
        result={{ ...baseResult, incremental_revenue_midpoint: undefined }}
      />
    );
    // em dash rendered for missing value
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});
