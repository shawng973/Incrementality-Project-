import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { TestCard } from "@/components/tests/TestCard";
import { Button } from "@/components/ui/button";
import type { PaginatedResponse, Test } from "@/types";

async function fetchTests(accessToken: string): Promise<PaginatedResponse<Test>> {
  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const res = await fetch(`${apiBase}/api/tests/?page_size=50`, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });

  if (!res.ok) return { items: [], total: 0, page: 1, page_size: 50 };
  return res.json();
}

export default async function TestsPage() {
  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  const { items: tests, total } = session
    ? await fetchTests(session.access_token)
    : { items: [], total: 0 };

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Tests</h1>
          {total > 0 && (
            <p className="mt-0.5 text-sm text-gray-500">
              {total} test{total !== 1 ? "s" : ""}
            </p>
          )}
        </div>
        <Button asChild>
          <Link href="/tests/new">New test</Link>
        </Button>
      </div>

      {/* List */}
      {tests.length === 0 ? (
        <EmptyState />
      ) : (
        <ul className="space-y-3">
          {tests.map((test) => (
            <li key={test.id}>
              <TestCard test={test} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-lg border-2 border-dashed border-gray-200 p-12 text-center">
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-brand-50">
        <div className="h-6 w-6 rounded bg-brand-200" />
      </div>
      <h3 className="text-sm font-semibold text-gray-900">No tests yet</h3>
      <p className="mt-1 text-sm text-gray-500">
        Create your first geo split test to get started.
      </p>
      <div className="mt-6">
        <Button asChild>
          <Link href="/tests/new">Create test</Link>
        </Button>
      </div>
    </div>
  );
}
