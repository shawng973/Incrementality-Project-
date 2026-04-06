/**
 * Number formatting utilities for the results dashboard.
 */

/** Format a dollar amount: $1,234,567 */
export function formatDollars(value: number | undefined | null): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

/** Format a proportion as a percentage: 0.153 → "15.3%" */
export function formatPct(value: number | undefined | null, decimals = 1): string {
  if (value == null) return "—";
  return `${(value * 100).toFixed(decimals)}%`;
}

/** Format a ROAS multiplier: 2.35 → "2.35x" */
export function formatROAS(value: number | undefined | null): string {
  if (value == null) return "—";
  return `${value.toFixed(2)}x`;
}

/** Format a p-value: 0.023 → "0.023", tiny values → "< 0.001" */
export function formatPValue(value: number | undefined | null): string {
  if (value == null) return "—";
  if (value < 0.001) return "< 0.001";
  return value.toFixed(3);
}

/** True when p-value indicates significance at the 5% level. */
export function isSignificant(pValue: number | undefined | null): boolean {
  return pValue != null && pValue < 0.05;
}
