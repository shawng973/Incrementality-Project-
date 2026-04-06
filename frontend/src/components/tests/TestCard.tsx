import Link from "next/link";
import { format, parseISO } from "date-fns";
import { ArrowRight, Calendar } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { TestStatusBadge } from "@/components/ui/badge";
import type { Test } from "@/types";

interface TestCardProps {
  test: Test;
}

const channelLabels: Record<string, string> = {
  ctv: "CTV",
  paid_search: "Paid Search",
  paid_social: "Paid Social",
  display: "Display",
  audio: "Audio",
  ooh: "OOH",
};

const granularityLabels: Record<string, string> = {
  state: "State",
  dma: "DMA",
  zip: "ZIP",
};

export function TestCard({ test }: TestCardProps) {
  const channel = test.channel ? (channelLabels[test.channel] ?? test.channel) : null;
  const granularity = granularityLabels[test.region_granularity] ?? test.region_granularity;
  const createdAt = format(parseISO(test.created_at), "MMM d, yyyy");

  return (
    <Link href={`/tests/${test.id}`} className="block group" aria-label={`View test: ${test.name}`}>
      <Card className="transition-shadow group-hover:shadow-md">
        <CardContent className="flex items-start justify-between py-5">
          <div className="min-w-0 flex-1">
            {/* Name + status */}
            <div className="flex items-center gap-2">
              <h3 className="truncate text-sm font-semibold text-gray-900">
                {test.name}
              </h3>
              <TestStatusBadge status={test.status} />
            </div>

            {/* Meta row */}
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
              {channel && <span>{channel}</span>}
              <span>{granularity}-level</span>
              <span>{test.n_cells} cells</span>
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                {createdAt}
              </span>
            </div>

            {/* Description */}
            {test.description && (
              <p className="mt-1.5 line-clamp-1 text-xs text-gray-400">
                {test.description}
              </p>
            )}
          </div>

          <ArrowRight className="ml-4 h-4 w-4 flex-shrink-0 text-gray-300 group-hover:text-brand-500 transition-colors" />
        </CardContent>
      </Card>
    </Link>
  );
}
