import { clsx } from "clsx";
import { CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import { formatPValue } from "@/lib/format";
import type { AnalysisResult } from "@/types";

interface DataQualityProps {
  result: AnalysisResult;
}

function QualityRow({
  label,
  pass,
  passLabel = "Pass",
  failLabel = "Fail",
  detail,
}: {
  label: string;
  pass: boolean | undefined | null;
  passLabel?: string;
  failLabel?: string;
  detail?: string;
}) {
  if (pass == null) return null;

  return (
    <div className="flex items-start gap-3 py-2.5 text-sm">
      {pass ? (
        <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-green-500" />
      ) : (
        <XCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-500" />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium text-gray-800">{label}</span>
          <span
            className={clsx(
              "rounded-full px-2 py-0.5 text-xs font-medium",
              pass ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
            )}
          >
            {pass ? passLabel : failLabel}
          </span>
        </div>
        {detail && (
          <p className="mt-0.5 text-xs text-gray-500">{detail}</p>
        )}
      </div>
    </div>
  );
}

export function DataQuality({ result }: DataQualityProps) {
  const power = result.power_analysis_json;

  return (
    <div className="divide-y divide-gray-100">
      <QualityRow
        label="Parallel trends"
        pass={result.parallel_trends_passes}
        passLabel="Passes"
        failLabel="Fails"
        detail={
          result.parallel_trends_passes
            ? `Pre-period trends were parallel (p = ${formatPValue(result.parallel_trends_p_value)}). DiD assumptions hold.`
            : result.parallel_trends_flag ?? "Pre-period trends diverged — DiD estimates may be biased."
        }
      />

      <QualityRow
        label="Causally clean"
        pass={result.is_causally_clean}
        passLabel="Yes"
        failLabel="No"
        detail={
          result.is_causally_clean
            ? "Pre-trend adjustment confirms no systematic bias in the estimate."
            : "Pre-trend regression detected bias. Use the adjusted YoY estimate for reporting."
        }
      />

      {power && (
        <div className="flex items-start gap-3 py-2.5 text-sm">
          {power.is_adequately_powered ? (
            <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-green-500" />
          ) : (
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-orange-400" />
          )}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="font-medium text-gray-800">Statistical power</span>
              <span
                className={clsx(
                  "rounded-full px-2 py-0.5 text-xs font-medium",
                  power.is_adequately_powered
                    ? "bg-green-100 text-green-700"
                    : "bg-orange-100 text-orange-700"
                )}
              >
                {power.power != null ? `${(power.power * 100).toFixed(0)}%` : "—"}
              </span>
            </div>
            <p className="mt-0.5 text-xs text-gray-500">
              {power.is_adequately_powered
                ? "Test was adequately powered to detect the measured effect."
                : (power.warning_message ?? "Test may be underpowered. Results should be interpreted with caution.")}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
