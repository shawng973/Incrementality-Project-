import { clsx } from "clsx";
import type { TestStatus, JobStatus } from "@/types";

export type BadgeVariant = "draft" | "active" | "completed" | "pending" | "running" | "failed" | "neutral";

const variantClasses: Record<BadgeVariant, string> = {
  draft: "bg-gray-100 text-gray-700",
  active: "bg-blue-100 text-blue-700",
  completed: "bg-green-100 text-green-700",
  pending: "bg-yellow-100 text-yellow-700",
  running: "bg-blue-100 text-blue-700 animate-pulse",
  failed: "bg-red-100 text-red-700",
  neutral: "bg-gray-100 text-gray-600",
};

interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  className?: string;
}

export function Badge({ variant = "neutral", children, className }: BadgeProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        variantClasses[variant],
        className
      )}
    >
      {children}
    </span>
  );
}

export function TestStatusBadge({ status }: { status: TestStatus }) {
  const labels: Record<TestStatus, string> = {
    draft: "Draft",
    active: "Active",
    completed: "Completed",
  };
  return <Badge variant={status}>{labels[status]}</Badge>;
}

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const labels: Record<JobStatus, string> = {
    pending: "Queued",
    running: "Running",
    completed: "Completed",
    failed: "Failed",
  };
  return <Badge variant={status}>{labels[status]}</Badge>;
}
