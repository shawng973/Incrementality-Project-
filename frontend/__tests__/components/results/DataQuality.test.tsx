import { render, screen } from "@testing-library/react";
import { DataQuality } from "@/components/results/DataQuality";
import type { AnalysisResult } from "@/types";

const baseResult: AnalysisResult = {
  job_id: "job-1",
  test_id: "test-1",
  status: "completed",
  parallel_trends_passes: true,
  parallel_trends_p_value: 0.45,
  is_causally_clean: true,
  power_analysis_json: {
    power: 0.85,
    is_adequately_powered: true,
  },
};

describe("DataQuality", () => {
  it("shows parallel trends pass", () => {
    render(<DataQuality result={baseResult} />);
    expect(screen.getByText("Passes")).toBeInTheDocument();
  });

  it("shows parallel trends fail", () => {
    render(
      <DataQuality
        result={{ ...baseResult, parallel_trends_passes: false, parallel_trends_flag: "Slope detected" }}
      />
    );
    expect(screen.getByText("Fails")).toBeInTheDocument();
    expect(screen.getByText("Slope detected")).toBeInTheDocument();
  });

  it("shows causally clean pass", () => {
    render(<DataQuality result={baseResult} />);
    expect(screen.getAllByText("Yes").length).toBeGreaterThan(0);
  });

  it("shows causally clean fail", () => {
    render(<DataQuality result={{ ...baseResult, is_causally_clean: false }} />);
    expect(screen.getByText("No")).toBeInTheDocument();
  });

  it("shows statistical power percentage", () => {
    render(<DataQuality result={baseResult} />);
    expect(screen.getByText("85%")).toBeInTheDocument();
  });

  it("shows underpowered state", () => {
    render(
      <DataQuality
        result={{
          ...baseResult,
          power_analysis_json: {
            power: 0.45,
            is_adequately_powered: false,
            warning_message: "Test needs more geos.",
          },
        }}
      />
    );
    expect(screen.getByText("45%")).toBeInTheDocument();
    expect(screen.getByText("Test needs more geos.")).toBeInTheDocument();
  });

  it("does not render power section when power_analysis_json is absent", () => {
    render(<DataQuality result={{ ...baseResult, power_analysis_json: undefined }} />);
    expect(screen.queryByText(/statistical power/i)).not.toBeInTheDocument();
  });

  it("does not render quality rows when values are null", () => {
    render(
      <DataQuality
        result={{
          ...baseResult,
          parallel_trends_passes: undefined,
          is_causally_clean: undefined,
          power_analysis_json: undefined,
        }}
      />
    );
    expect(screen.queryByText("Passes")).not.toBeInTheDocument();
    expect(screen.queryByText("Yes")).not.toBeInTheDocument();
  });
});
