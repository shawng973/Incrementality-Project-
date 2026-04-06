import { notFound } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { createClient } from "@/lib/supabase/server";
import { ResultsDashboard } from "@/components/results/ResultsDashboard";
import { TestStatusBadge } from "@/components/ui/badge";
import type { AnalysisResult, CsvUpload, Test, UploadListResponse } from "@/types";

interface TestDetailPageProps {
  params: { id: string };
}

async function fetchTest(id: string, token: string): Promise<Test | null> {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const res = await fetch(`${base}/api/tests/${id}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (res.status === 404 || res.status === 403) return null;
  if (!res.ok) throw new Error(`Failed to fetch test: ${res.status}`);
  return res.json();
}

async function fetchLatestResult(
  testId: string,
  token: string
): Promise<AnalysisResult | null> {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const res = await fetch(`${base}/api/tests/${testId}/analysis/latest`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (res.status === 404) return null;
  if (!res.ok) return null;
  return res.json();
}

export default async function TestDetailPage({ params }: TestDetailPageProps) {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) notFound();

  const [test, result] = await Promise.all([
    fetchTest(params.id, session.access_token),
    fetchLatestResult(params.id, session.access_token),
  ]);

  if (!test) notFound();

  const channelLabel: Record<string, string> = {
    ctv: "CTV",
    paid_search: "Paid Search",
    paid_social: "Paid Social",
    display: "Display",
    audio: "Audio",
    ooh: "OOH",
  };

  return (
    <div>
      {/* Back link */}
      <Link
        href="/tests"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-700"
      >
        <ArrowLeft className="h-4 w-4" />
        Tests
      </Link>

      {/* Test header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-gray-900">{test.name}</h1>
            <TestStatusBadge status={test.status} />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-gray-500">
            {test.channel && (
              <span>{channelLabel[test.channel] ?? test.channel}</span>
            )}
            <span className="capitalize">{test.region_granularity}-level</span>
            <span>{test.n_cells} cells</span>
            {test.start_date && test.end_date && (
              <span>
                {test.start_date} – {test.end_date}
              </span>
            )}
          </div>
          {test.description && (
            <p className="mt-1 text-sm text-gray-400">{test.description}</p>
          )}
        </div>
      </div>

      {/* Results dashboard */}
      <ResultsDashboard test={test} initialResult={result} />
    </div>
  );
}
