"""
CSV Upload Validation — Layer 2 of the data pipeline.

Validates an uploaded DataFrame before it enters the statistical engine.
Returns a structured ValidationResult rather than raising directly, so the
API layer can return all errors at once (not just the first one).

Checks performed (in order):
1. Required columns present
2. No extra-empty DataFrame
3. Date/period format parseable
4. Numeric columns are numeric
5. Geo identifier column is non-null
6. Minimum row count
7. Duplicate geo × period combinations (warning, not error)
8. Negative values in numeric columns (warning)
9. Missing values (NaN) in required columns (error)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

# Minimum acceptable rows for any statistical analysis
MIN_ROWS = 30


@dataclass
class ValidationResult:
    """Outcome of validate_upload()."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    row_count: int = 0
    geo_count: int = 0
    period_count: int = 0

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.is_valid = False

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


# Required columns and their types
REQUIRED_COLUMNS = ["region", "period", "metric"]
NUMERIC_COLUMNS = ["metric"]
OPTIONAL_NUMERIC_COLUMNS = ["spend"]

# Supported date formats
DATE_FORMATS = ["%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m-%d-%Y", "%Y%m%d"]


def validate_upload(
    df: pd.DataFrame,
    required_cols: Optional[list[str]] = None,
    numeric_cols: Optional[list[str]] = None,
    geo_col: str = "region",
    period_col: str = "period",
    metric_col: str = "metric",
    min_rows: int = MIN_ROWS,
) -> ValidationResult:
    """
    Validate an uploaded DataFrame.

    Args:
        df:            The parsed CSV DataFrame.
        required_cols: Columns that must be present. Defaults to REQUIRED_COLUMNS.
        numeric_cols:  Columns that must be numeric. Defaults to NUMERIC_COLUMNS.
        geo_col:       Name of the region/geo column.
        period_col:    Name of the date/period column.
        metric_col:    Name of the primary metric column.
        min_rows:      Minimum acceptable row count.

    Returns:
        ValidationResult with all errors and warnings.
    """
    result = ValidationResult(is_valid=True)

    if required_cols is None:
        required_cols = REQUIRED_COLUMNS
    if numeric_cols is None:
        numeric_cols = NUMERIC_COLUMNS

    # ── 1. Empty DataFrame ────────────────────────────────────────────────
    if df.empty:
        result.add_error("The uploaded file contains no data rows.")
        return result  # no further checks possible

    # ── 2. Required columns ───────────────────────────────────────────────
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        for col in missing:
            result.add_error(f"Required column '{col}' is missing from the upload.")
        return result  # can't validate further without required cols

    # ── 3. Minimum row count ──────────────────────────────────────────────
    if len(df) < min_rows:
        result.add_error(
            f"Upload contains only {len(df)} rows; minimum required is {min_rows}. "
            "Add more historical data before running analysis."
        )

    # ── 4. Geo column non-null ────────────────────────────────────────────
    null_geos = df[geo_col].isna().sum()
    if null_geos > 0:
        result.add_error(
            f"Column '{geo_col}' has {null_geos} missing value(s). "
            "Every row must have a region identifier."
        )

    # ── 5. Period column parseable ────────────────────────────────────────
    period_errors = _validate_period_column(df[period_col])
    for err in period_errors:
        result.add_error(err)

    # ── 6. Numeric columns ────────────────────────────────────────────────
    for col in numeric_cols:
        if col in df.columns:
            errors = _validate_numeric_column(df[col], col)
            for err in errors:
                result.add_error(err)

    # Optional numeric columns — warn if present but non-numeric
    for col in OPTIONAL_NUMERIC_COLUMNS:
        if col in df.columns:
            errors = _validate_numeric_column(df[col], col)
            for err in errors:
                result.add_warning(f"Optional column: {err}")

    # ── 7. Missing values in required columns ─────────────────────────────
    for col in required_cols:
        if col in df.columns:
            n_null = df[col].isna().sum()
            if n_null > 0:
                result.add_error(
                    f"Column '{col}' has {n_null} missing value(s). "
                    "Fill or remove these rows before uploading."
                )

    # ── 8. Negative metric values ─────────────────────────────────────────
    if metric_col in df.columns:
        try:
            numeric_metric = pd.to_numeric(df[metric_col], errors="coerce")
            n_negative = (numeric_metric < 0).sum()
            if n_negative > 0:
                result.add_warning(
                    f"Column '{metric_col}' has {n_negative} negative value(s). "
                    "Verify this is intentional — negative revenue or conversions "
                    "may indicate data issues."
                )
        except Exception:
            pass  # already caught by numeric validation

    # ── 9. Duplicate geo × period combinations ────────────────────────────
    if geo_col in df.columns and period_col in df.columns:
        dupes = df.duplicated(subset=[geo_col, period_col]).sum()
        if dupes > 0:
            result.add_warning(
                f"{dupes} duplicate {geo_col} × {period_col} combination(s) detected. "
                "Duplicate rows will be aggregated (summed) before analysis. "
                "Verify this is the intended behavior."
            )

    # ── Populate summary stats ─────────────────────────────────────────────
    result.row_count = len(df)
    result.geo_count = df[geo_col].nunique() if geo_col in df.columns else 0
    result.period_count = df[period_col].nunique() if period_col in df.columns else 0

    return result


# ---------------------------------------------------------------------------
# Internal validators
# ---------------------------------------------------------------------------


def _validate_period_column(series: pd.Series) -> list[str]:
    """
    Attempt to parse the period column as dates or integers.
    Returns a list of error strings (empty if valid).
    """
    errors: list[str] = []

    # Allow integer week/month indices
    try:
        pd.to_numeric(series.dropna(), downcast="integer")
        return []  # valid integer periods
    except (ValueError, TypeError):
        pass

    # Try date parsing with supported formats
    for fmt in DATE_FORMATS:
        try:
            pd.to_datetime(series.dropna(), format=fmt)
            return []  # valid date format
        except (ValueError, TypeError):
            continue

    # Try pandas flexible parser as last resort
    try:
        pd.to_datetime(series.dropna(), infer_datetime_format=True)
        return []
    except (ValueError, TypeError):
        pass

    errors.append(
        f"Column 'period' could not be parsed as a date or integer. "
        f"Supported date formats: {', '.join(DATE_FORMATS)}. "
        "Use YYYY-MM-DD or integer week indices."
    )
    return errors


def _validate_numeric_column(series: pd.Series, col_name: str) -> list[str]:
    """
    Verify a column can be coerced to numeric.
    Returns a list of error strings.
    """
    errors: list[str] = []
    coerced = pd.to_numeric(series, errors="coerce")
    n_failed = coerced.isna().sum() - series.isna().sum()
    if n_failed > 0:
        errors.append(
            f"Column '{col_name}' has {n_failed} non-numeric value(s). "
            f"This column must contain only numbers."
        )
    return errors
