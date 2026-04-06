"""
Column Mapping — resolves user-uploaded column names to internal canonical names.

Users upload CSVs with arbitrary column headers (e.g., "Revenue", "Sales $",
"DMA Code", "Week Ending"). This module normalizes them to the internal schema:
    region, period, metric, spend (optional), prior_metric (optional)

Strategy:
1. Exact match on canonical names (case-insensitive).
2. Alias matching: a curated dictionary of common synonyms.
3. If ambiguous or unresolvable, return an error with suggestions.

The caller (API layer) can also pass an explicit override mapping
(e.g., {"revenue_total": "metric", "market": "region"}) from the UI form.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Internal canonical column names
CANONICAL_REGION = "region"
CANONICAL_PERIOD = "period"
CANONICAL_METRIC = "metric"
CANONICAL_SPEND = "spend"
CANONICAL_PRIOR_METRIC = "prior_metric"

REQUIRED_CANONICAL = [CANONICAL_REGION, CANONICAL_PERIOD, CANONICAL_METRIC]
OPTIONAL_CANONICAL = [CANONICAL_SPEND, CANONICAL_PRIOR_METRIC]

# Alias dictionary: alias (lowercase) → canonical name
COLUMN_ALIASES: dict[str, str] = {
    # region
    "region": CANONICAL_REGION,
    "geo": CANONICAL_REGION,
    "geography": CANONICAL_REGION,
    "market": CANONICAL_REGION,
    "state": CANONICAL_REGION,
    "dma": CANONICAL_REGION,
    "dma_code": CANONICAL_REGION,
    "dma code": CANONICAL_REGION,
    "zip": CANONICAL_REGION,
    "zip_code": CANONICAL_REGION,
    "zip code": CANONICAL_REGION,
    "location": CANONICAL_REGION,
    # period
    "period": CANONICAL_PERIOD,
    "week": CANONICAL_PERIOD,
    "date": CANONICAL_PERIOD,
    "week_ending": CANONICAL_PERIOD,
    "week ending": CANONICAL_PERIOD,
    "week_start": CANONICAL_PERIOD,
    "week start": CANONICAL_PERIOD,
    "month": CANONICAL_PERIOD,
    "date_period": CANONICAL_PERIOD,
    "time_period": CANONICAL_PERIOD,
    # metric
    "metric": CANONICAL_METRIC,
    "revenue": CANONICAL_METRIC,
    "sales": CANONICAL_METRIC,
    "conversions": CANONICAL_METRIC,
    "orders": CANONICAL_METRIC,
    "transactions": CANONICAL_METRIC,
    "revenue_total": CANONICAL_METRIC,
    "total_revenue": CANONICAL_METRIC,
    "total revenue": CANONICAL_METRIC,
    "sales $": CANONICAL_METRIC,
    "revenue ($)": CANONICAL_METRIC,
    "primary_metric": CANONICAL_METRIC,
    # spend
    "spend": CANONICAL_SPEND,
    "ad_spend": CANONICAL_SPEND,
    "ad spend": CANONICAL_SPEND,
    "media_spend": CANONICAL_SPEND,
    "media spend": CANONICAL_SPEND,
    "cost": CANONICAL_SPEND,
    "investment": CANONICAL_SPEND,
    "budget": CANONICAL_SPEND,
    "impressions_cost": CANONICAL_SPEND,
    # prior_metric
    "prior_metric": CANONICAL_PRIOR_METRIC,
    "prior_year_revenue": CANONICAL_PRIOR_METRIC,
    "prior year revenue": CANONICAL_PRIOR_METRIC,
    "py_revenue": CANONICAL_PRIOR_METRIC,
    "last_year_revenue": CANONICAL_PRIOR_METRIC,
    "yoy_baseline": CANONICAL_PRIOR_METRIC,
    "prior_period_metric": CANONICAL_PRIOR_METRIC,
}


@dataclass
class MappingResult:
    """Output of resolve_column_mapping()."""

    mapping: dict[str, str]      # upload_col_name → canonical_name
    unmapped_upload_cols: list[str]     # columns in upload not mapped
    missing_canonical: list[str]        # required canonical cols not resolved
    is_complete: bool                   # True if all required canonicals resolved
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def resolve_column_mapping(
    upload_columns: list[str],
    explicit_overrides: dict[str, str] | None = None,
) -> MappingResult:
    """
    Resolve uploaded column names to canonical names.

    Args:
        upload_columns:    List of column names from the uploaded CSV.
        explicit_overrides: UI-provided mapping: {upload_col: canonical_col}.
                            Takes priority over alias matching.

    Returns:
        MappingResult with the resolved mapping and any issues.
    """
    if explicit_overrides is None:
        explicit_overrides = {}

    mapping: dict[str, str] = {}
    overrides_lower = {k.lower(): v for k, v in explicit_overrides.items()}

    for col in upload_columns:
        col_lower = col.lower().strip()

        # 1. Explicit override (case-insensitive key match)
        if col_lower in overrides_lower:
            canonical = overrides_lower[col_lower]
            mapping[col] = canonical
            continue

        # 2. Alias match
        if col_lower in COLUMN_ALIASES:
            mapping[col] = COLUMN_ALIASES[col_lower]

    # Check for duplicate canonical targets (two columns mapped to same canonical)
    canonical_counts: dict[str, list[str]] = {}
    for upload_col, canonical in mapping.items():
        canonical_counts.setdefault(canonical, []).append(upload_col)

    errors: list[str] = []
    warnings: list[str] = []

    for canonical, cols in canonical_counts.items():
        if len(cols) > 1:
            errors.append(
                f"Multiple columns map to '{canonical}': {cols}. "
                f"Use the column mapping form to specify which one to use."
            )

    # Determine which required canonicals are resolved
    resolved_canonicals = set(mapping.values())
    missing = [c for c in REQUIRED_CANONICAL if c not in resolved_canonicals]
    unmapped = [c for c in upload_columns if c not in mapping]

    # Warn about unmapped columns
    if unmapped:
        warnings.append(
            f"The following columns were not recognized and will be ignored: "
            f"{unmapped}. Use the column mapping form to include them."
        )

    is_complete = len(missing) == 0 and len(errors) == 0

    return MappingResult(
        mapping=mapping,
        unmapped_upload_cols=unmapped,
        missing_canonical=missing,
        is_complete=is_complete,
        errors=errors,
        warnings=warnings,
    )


def apply_mapping(df: "pd.DataFrame", mapping: dict[str, str]) -> "pd.DataFrame":  # noqa: F821
    """
    Rename DataFrame columns according to the resolved mapping.
    Returns a new DataFrame with canonical column names.
    """
    import pandas as pd

    rename_map = {k: v for k, v in mapping.items() if k in df.columns}
    return df.rename(columns=rename_map)
