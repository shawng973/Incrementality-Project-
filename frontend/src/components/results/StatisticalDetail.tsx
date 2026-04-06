import { clsx } from "clsx";
import { formatDollars, formatPct, formatPValue, isSignificant } from "@/lib/format";
import type { AnalysisResult } from "@/types";

interface StatisticalDetailProps {
  result: AnalysisResult;
}

function Row({
  label,
  value,
  className,
}: {
  label: string;
  value: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={clsx("flex items-center justify-between py-2 text-sm", className)}>
      <span className="text-gray-500">{label}</span>
      <span className="font-medium text-gray-900">{value}</span>
    </div>
  );
}

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1 mt-4 text-xs font-semibold uppercase tracking-wide text-gray-400 first:mt-0">
      {children}
    </p>
  );
}

export function StatisticalDetail({ result }: StatisticalDetailProps) {
  const sig = isSignificant(result.twfe_p_value);
  const ci95 = result.twfe_ci_95;
  const ci90 = result.twfe_ci_90;
  const ci80 = result.twfe_ci_80;

  return (
    <div className="divide-y divide-gray-100">
      {/* TWFE */}
      <div className="pb-4">
        <SectionHeading>TWFE Difference-in-Differences (primary)</SectionHeading>
        <Row label="Treatment effect (lift)" value={formatPct(result.twfe_treatment_effect)} />
        <Row
          label="Treatment effect ($)"
          value={formatDollars(result.twfe_treatment_effect_dollars)}
        />
        <Row
          label="p-value"
          value={
            <span className={clsx(sig ? "text-green-700" : "text-yellow-700")}>
              {formatPValue(result.twfe_p_value)}
              {sig ? " ✓" : " (n.s.)"}
            </span>
          }
        />
        {ci95 && (
          <Row
            label="95% CI"
            value={`${formatPct(ci95.lower)} – ${formatPct(ci95.upper)}`}
          />
        )}
        {ci90 && (
          <Row
            label="90% CI"
            value={`${formatPct(ci90.lower)} – ${formatPct(ci90.upper)}`}
          />
        )}
        {ci80 && (
          <Row
            label="80% CI"
            value={`${formatPct(ci80.lower)} – ${formatPct(ci80.upper)}`}
          />
        )}
      </div>

      {/* Simple DiD cross-check */}
      {result.simple_did_estimate != null && (
        <div className="py-4">
          <SectionHeading>Simple DiD cross-check</SectionHeading>
          <Row
            label="DiD estimate (lift)"
            value={formatPct(result.simple_did_estimate)}
          />
          <Row
            label="DiD estimate ($)"
            value={formatDollars(result.simple_did_dollars)}
          />
          {result.twfe_treatment_effect != null && (
            <Row
              label="Alignment with TWFE"
              value={
                Math.abs(
                  (result.simple_did_estimate ?? 0) -
                    (result.twfe_treatment_effect ?? 0)
                ) < 0.03
                  ? "✓ Closely aligned"
                  : "⚠ Diverges from TWFE — review inputs"
              }
            />
          )}
        </div>
      )}

      {/* YoY */}
      {result.yoy_did_proportion != null && (
        <div className="py-4">
          <SectionHeading>Year-over-Year DiD</SectionHeading>
          <Row
            label="YoY DiD estimate (lift)"
            value={formatPct(result.yoy_did_proportion)}
          />
          <Row
            label="YoY DiD estimate ($)"
            value={formatDollars(result.yoy_did_dollars)}
          />
          {result.adjusted_yoy_did_dollars != null && (
            <Row
              label="Pre-trend adjusted ($)"
              value={formatDollars(result.adjusted_yoy_did_dollars)}
            />
          )}
        </div>
      )}

      {/* Reconciled */}
      {result.incremental_revenue_midpoint != null && (
        <div className="pt-4">
          <SectionHeading>Reconciled incrementality</SectionHeading>
          <Row
            label="Midpoint estimate"
            value={formatDollars(result.incremental_revenue_midpoint)}
          />
          {result.incremental_revenue_weighted != null && (
            <Row
              label="Variance-weighted estimate"
              value={formatDollars(result.incremental_revenue_weighted)}
            />
          )}
        </div>
      )}
    </div>
  );
}
