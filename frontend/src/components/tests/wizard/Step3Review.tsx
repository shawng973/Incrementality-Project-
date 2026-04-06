import { Button } from "@/components/ui/button";
import type { Step1Data } from "./Step1Config";
import type { Step2Data } from "./Step2Dates";

interface Step3ReviewProps {
  step1: Step1Data;
  step2: Step2Data;
  isSubmitting: boolean;
  error: string | null;
  onBack: () => void;
  onSubmit: () => void;
}

const TEST_TYPE_LABELS: Record<string, string> = {
  geo_split: "Geo Split",
  pre_post: "Pre / Post",
};

const GRANULARITY_LABELS: Record<string, string> = {
  state: "State",
  dma: "DMA",
  zip: "ZIP",
};

const CHANNEL_LABELS: Record<string, string> = {
  ctv: "CTV",
  paid_search: "Paid Search",
  paid_social: "Paid Social",
  display: "Display",
  audio: "Audio",
  ooh: "OOH",
  other: "Other",
};

function ReviewRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between py-2.5 text-sm">
      <span className="w-44 flex-shrink-0 font-medium text-gray-500">{label}</span>
      <span className="text-gray-900">{value}</span>
    </div>
  );
}

export function Step3Review({
  step1,
  step2,
  isSubmitting,
  error,
  onBack,
  onSubmit,
}: Step3ReviewProps) {
  const hasAnyDate = step2.start_date || step2.end_date;

  return (
    <div>
      <p className="mb-5 text-sm text-gray-500">
        Review your test configuration below. You can go back to make changes before creating.
      </p>

      {/* Config summary */}
      <div className="divide-y divide-gray-100 rounded-lg border border-gray-200 bg-gray-50 px-4">
        <ReviewRow label="Test name" value={step1.name} />
        <ReviewRow label="Test type" value={TEST_TYPE_LABELS[step1.test_type]} />
        <ReviewRow
          label="Channel"
          value={
            step1.channel
              ? (CHANNEL_LABELS[step1.channel] ?? step1.channel)
              : <span className="text-gray-400 italic">Not set</span>
          }
        />
        <ReviewRow
          label="Region granularity"
          value={GRANULARITY_LABELS[step1.region_granularity]}
        />
        <ReviewRow
          label="Test cells"
          value={`${step1.n_cells} cells`}
        />
        {step1.description && (
          <ReviewRow label="Description" value={step1.description} />
        )}
      </div>

      {/* Dates summary */}
      <div className="mt-4 divide-y divide-gray-100 rounded-lg border border-gray-200 bg-gray-50 px-4">
        <ReviewRow
          label="Start date"
          value={
            step2.start_date || (
              <span className="text-gray-400 italic">Not set</span>
            )
          }
        />
        <ReviewRow
          label="End date"
          value={
            step2.end_date || (
              <span className="text-gray-400 italic">Not set</span>
            )
          }
        />
        <ReviewRow
          label="Cooldown weeks"
          value={
            step2.cooldown_weeks != null && step2.cooldown_weeks !== ""
              ? `${step2.cooldown_weeks} week${Number(step2.cooldown_weeks) !== 1 ? "s" : ""}`
              : <span className="text-gray-400 italic">None</span>
          }
        />
      </div>

      {!hasAnyDate && (
        <p className="mt-3 text-xs text-gray-400">
          No dates set — the test will be saved as Draft. You can add dates later.
        </p>
      )}

      {/* Submit error */}
      {error && (
        <div
          role="alert"
          className="mt-4 rounded-md bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {error}
        </div>
      )}

      <div className="mt-8 flex justify-between">
        <Button type="button" variant="secondary" onClick={onBack} disabled={isSubmitting}>
          ← Back
        </Button>
        <Button
          type="button"
          onClick={onSubmit}
          isLoading={isSubmitting}
        >
          Create test
        </Button>
      </div>
    </div>
  );
}
