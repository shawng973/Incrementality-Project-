import { clsx } from "clsx";
import { CheckCircle2, AlertTriangle, TrendingUp } from "lucide-react";
import {
  formatDollars,
  formatPct,
  formatROAS,
  formatPValue,
  isSignificant,
} from "@/lib/format";
import type { AnalysisResult } from "@/types";

interface ExecutiveSummaryProps {
  result: AnalysisResult;
}

interface MetricTileProps {
  label: string;
  value: string;
  sub?: string;
  highlight?: "positive" | "negative" | "neutral";
}

function MetricTile({ label, value, sub, highlight = "neutral" }: MetricTileProps) {
  return (
    <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
      <p
        className={clsx(
          "mt-1 text-2xl font-bold",
          highlight === "positive" && "text-green-700",
          highlight === "negative" && "text-red-600",
          highlight === "neutral" && "text-gray-900"
        )}
      >
        {value}
      </p>
      {sub && <p className="mt-0.5 text-xs text-gray-500">{sub}</p>}
    </div>
  );
}

export function ExecutiveSummary({ result }: ExecutiveSummaryProps) {
  const sig = isSignificant(result.twfe_p_value);
  const lift = result.twfe_treatment_effect;
  const liftPositive = lift != null && lift > 0;

  return (
    <div className="px-6 py-5">
      {/* Significance banner */}
      <div
        className={clsx(
          "mb-5 flex items-center gap-2 rounded-md px-4 py-3 text-sm font-medium",
          sig
            ? "bg-green-50 text-green-800"
            : "bg-yellow-50 text-yellow-800"
        )}
        role="status"
      >
        {sig ? (
          <CheckCircle2 className="h-4 w-4 flex-shrink-0 text-green-600" />
        ) : (
          <AlertTriangle className="h-4 w-4 flex-shrink-0 text-yellow-500" />
        )}
        {sig
          ? "Statistically significant result — the test detected a real effect."
          : "Result is not statistically significant at the 5% level."}
        <span className="ml-auto text-xs font-normal opacity-70">
          p = {formatPValue(result.twfe_p_value)}
        </span>
      </div>

      {/* Key metric tiles */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <MetricTile
          label="Measured lift"
          value={formatPct(lift)}
          sub="TWFE estimate"
          highlight={liftPositive ? "positive" : lift != null && lift < 0 ? "negative" : "neutral"}
        />
        <MetricTile
          label="Incremental revenue"
          value={formatDollars(result.incremental_revenue_midpoint)}
          sub="Midpoint estimate"
          highlight={liftPositive ? "positive" : "neutral"}
        />
        <MetricTile
          label="ROAS (mid)"
          value={formatROAS(result.roas_mid)}
          sub={
            result.roas_low != null && result.roas_high != null
              ? `${formatROAS(result.roas_low)} – ${formatROAS(result.roas_high)}`
              : undefined
          }
          highlight={
            result.roas_mid != null && result.roas_mid >= 1
              ? "positive"
              : result.roas_mid != null
              ? "negative"
              : "neutral"
          }
        />
        <MetricTile
          label="Total spend"
          value={formatDollars(result.total_spend)}
        />
      </div>

      {/* Power warning */}
      {result.power_analysis_json?.is_adequately_powered === false && (
        <div className="mt-4 flex items-start gap-2 rounded-md bg-orange-50 px-4 py-3 text-sm text-orange-800">
          <TrendingUp className="mt-0.5 h-4 w-4 flex-shrink-0 text-orange-500" />
          <span>
            <strong>Underpowered test.</strong>{" "}
            {result.power_analysis_json.warning_message ??
              "Results should be interpreted with caution."}
          </span>
        </div>
      )}
    </div>
  );
}
