"use client";

import { useState } from "react";
import { Download } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CollapsibleSection } from "./CollapsibleSection";
import { ExecutiveSummary } from "./ExecutiveSummary";
import { StatisticalDetail } from "./StatisticalDetail";
import { DataQuality } from "./DataQuality";
import { NarrativeDisplay } from "./NarrativeDisplay";
import { AnalysisTrigger } from "./AnalysisTrigger";
import { UploadSection } from "@/components/uploads/UploadSection";
import { api } from "@/lib/api";
import type { AnalysisResult, Test } from "@/types";

interface ResultsDashboardProps {
  test: Test;
  initialResult: AnalysisResult | null;
}

export function ResultsDashboard({ test, initialResult }: ResultsDashboardProps) {
  const [result, setResult] = useState<AnalysisResult | null>(initialResult);
  const [isDownloading, setIsDownloading] = useState(false);

  async function handleDownloadPdf() {
    setIsDownloading(true);
    try {
      const blob = await api.pdf.downloadLatest(test.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${test.name.replace(/[^a-z0-9]/gi, "_")}_analysis.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // Silent fail — user can retry
    } finally {
      setIsDownloading(false);
    }
  }

  // ── No results yet ──────────────────────────────────────────────────────────
  if (!result) {
    return (
      <Card>
        <div className="px-6 py-5">
          <h2 className="mb-1 text-base font-semibold text-gray-900">Run analysis</h2>
          <p className="text-sm text-gray-500">
            No analysis has been run for this test yet.
          </p>
        </div>
        <div className="border-t border-gray-100 px-6 py-5">
          <AnalysisTrigger
            testId={test.id}
            onComplete={(r) => setResult(r)}
          />
        </div>
      </Card>
    );
  }

  // ── Results available ───────────────────────────────────────────────────────
  return (
    <div className="space-y-4">
      {/* Executive summary — always open */}
      <Card>
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
          <h2 className="text-base font-semibold text-gray-900">Results summary</h2>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleDownloadPdf}
            isLoading={isDownloading}
          >
            <Download className="h-4 w-4" />
            Export PDF
          </Button>
        </div>
        <ExecutiveSummary result={result} />
      </Card>

      {/* Progressive disclosure sections */}
      <Card>
        <CollapsibleSection title="AI narrative" defaultOpen={true}>
          <NarrativeDisplay
            testId={test.id}
            jobId={result.job_id}
          />
        </CollapsibleSection>

        <CollapsibleSection title="Statistical detail">
          <StatisticalDetail result={result} />
        </CollapsibleSection>

        <CollapsibleSection title="Data quality">
          <DataQuality result={result} />
        </CollapsibleSection>

        <CollapsibleSection title="Upload data">
          <div className="space-y-6">
            <UploadSection testId={test.id} uploadType="historical" />
            <UploadSection testId={test.id} uploadType="results" />
          </div>
        </CollapsibleSection>

        <CollapsibleSection title="Run a new analysis">
          <AnalysisTrigger
            testId={test.id}
            onComplete={(r) => setResult(r)}
          />
        </CollapsibleSection>
      </Card>
    </div>
  );
}
