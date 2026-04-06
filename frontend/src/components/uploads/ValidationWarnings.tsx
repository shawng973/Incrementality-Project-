import { AlertTriangle, CheckCircle2 } from "lucide-react";

interface ValidationWarningsProps {
  warnings: string[];
  errors?: string[];
}

export function ValidationWarnings({ warnings, errors = [] }: ValidationWarningsProps) {
  if (warnings.length === 0 && errors.length === 0) return null;

  return (
    <div className="space-y-2 rounded-lg border border-gray-200 p-4 text-sm">
      {errors.map((err, i) => (
        <div key={i} className="flex items-start gap-2 text-red-700">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-red-500" />
          <span>{err}</span>
        </div>
      ))}
      {warnings.map((w, i) => (
        <div key={i} className="flex items-start gap-2 text-yellow-700">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-yellow-500" />
          <span>{w}</span>
        </div>
      ))}
    </div>
  );
}

interface UploadSuccessStatsProps {
  rowCount?: number;
  geoCount?: number;
  periodCount?: number;
}

export function UploadSuccessStats({
  rowCount,
  geoCount,
  periodCount,
}: UploadSuccessStatsProps) {
  return (
    <div className="flex items-center gap-2 rounded-md bg-green-50 px-4 py-2.5 text-sm text-green-800">
      <CheckCircle2 className="h-4 w-4 flex-shrink-0 text-green-500" />
      <span>
        Upload successful —{" "}
        {rowCount != null && <><strong>{rowCount.toLocaleString()}</strong> rows, </>}
        {geoCount != null && <><strong>{geoCount}</strong> regions, </>}
        {periodCount != null && <><strong>{periodCount}</strong> periods</>}
      </span>
    </div>
  );
}
