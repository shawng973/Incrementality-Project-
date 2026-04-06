"use client";

import { useState, useEffect, useCallback } from "react";
import { Play, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { JobStatusBadge } from "@/components/ui/badge";
import { api, ApiError } from "@/lib/api";
import type { AnalysisJob, AnalysisResult, JobStatus } from "@/types";

interface AnalysisTriggerProps {
  testId: string;
  /** Called when a job completes so the parent can show results. */
  onComplete: (result: AnalysisResult) => void;
  /** If a job is already running on mount, pass it here. */
  activeJob?: AnalysisJob | null;
}

const POLL_INTERVAL_MS = 3000;

export function AnalysisTrigger({
  testId,
  onComplete,
  activeJob = null,
}: AnalysisTriggerProps) {
  const [spend, setSpend] = useState("");
  const [hasPriorYear, setHasPriorYear] = useState(false);
  const [job, setJob] = useState<AnalysisJob | null>(activeJob);
  const [isTriggering, setIsTriggering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Poll job status while pending / running
  // ---------------------------------------------------------------------------

  const pollJob = useCallback(async () => {
    if (!job) return;
    try {
      const updated = await api.analysis.getJob(testId, job.job_id);
      setJob(updated);

      if (updated.status === "completed") {
        const result = await api.analysis.getLatest(testId);
        onComplete(result);
      }
    } catch {
      // Transient network error — keep polling
    }
  }, [job, testId, onComplete]);

  useEffect(() => {
    if (!job) return;
    const isActive: JobStatus[] = ["pending", "running"];
    if (!isActive.includes(job.status as JobStatus)) return;

    const id = setInterval(pollJob, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [job, pollJob]);

  // ---------------------------------------------------------------------------
  // Trigger
  // ---------------------------------------------------------------------------

  async function handleTrigger() {
    const spendNum = parseFloat(spend);
    if (!spend || isNaN(spendNum) || spendNum <= 0) {
      setError("Enter the total media spend for the test period.");
      return;
    }
    setIsTriggering(true);
    setError(null);

    try {
      const newJob = await api.analysis.trigger(testId, {
        spend: spendNum,
        has_prior_year: hasPriorYear,
      });
      setJob(newJob);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        setError("Upload historical data before running analysis.");
      } else {
        setError("Failed to start analysis. Please try again.");
      }
    } finally {
      setIsTriggering(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Render — active job
  // ---------------------------------------------------------------------------

  if (job && (job.status === "pending" || job.status === "running")) {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-center">
        <RefreshCw className="h-8 w-8 animate-spin text-brand-400" />
        <div>
          <p className="text-sm font-medium text-gray-700">Analysis in progress…</p>
          <p className="mt-0.5 text-xs text-gray-400">
            This usually takes 30–60 seconds. The page will update automatically.
          </p>
        </div>
        <JobStatusBadge status={job.status} />
      </div>
    );
  }

  if (job?.status === "failed") {
    return (
      <div
        role="alert"
        className="rounded-md bg-red-50 px-5 py-4 text-sm text-red-700"
      >
        <p className="font-medium">Analysis failed</p>
        <p className="mt-1 text-xs">{job.message || "An error occurred in the analysis pipeline."}</p>
        <Button
          variant="danger"
          size="sm"
          className="mt-3"
          onClick={() => setJob(null)}
        >
          Try again
        </Button>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render — trigger form
  // ---------------------------------------------------------------------------

  return (
    <div className="py-2">
      <p className="mb-4 text-sm text-gray-500">
        Enter the total media spend for the test period, then run the full
        statistical analysis.
      </p>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
        {/* Spend input */}
        <div className="flex-1">
          <label
            htmlFor="spend"
            className="mb-1 block text-sm font-medium text-gray-700"
          >
            Total test spend ($) <span className="text-red-500">*</span>
          </label>
          <input
            id="spend"
            type="number"
            min={1}
            step={1000}
            placeholder="50000"
            value={spend}
            onChange={(e) => setSpend(e.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>

        {/* Prior year toggle */}
        <label className="flex cursor-pointer items-center gap-2 text-sm text-gray-700 sm:mb-2">
          <input
            type="checkbox"
            checked={hasPriorYear}
            onChange={(e) => setHasPriorYear(e.target.checked)}
            className="accent-brand-600"
          />
          Include prior-year data
        </label>

        <Button
          onClick={handleTrigger}
          isLoading={isTriggering}
          className="sm:mb-0"
        >
          <Play className="h-4 w-4" />
          Run analysis
        </Button>
      </div>

      {error && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}
