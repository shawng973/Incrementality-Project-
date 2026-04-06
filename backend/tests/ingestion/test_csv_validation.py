"""
Tests for csv_validation.py — Layer 2 data ingestion.
"""

import pandas as pd
import pytest

from app.services.ingestion.csv_validation import (
    validate_upload,
    ValidationResult,
    MIN_ROWS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_valid_df(n_rows: int = 50, n_geos: int = 5) -> pd.DataFrame:
    """Minimal valid DataFrame that passes all checks."""
    rows_per_geo = n_rows // n_geos
    records = []
    for g in range(n_geos):
        for t in range(rows_per_geo):
            records.append(
                {
                    "region": f"CA_{g:02d}",
                    "period": t,
                    "metric": 10_000.0 + g * 1000 + t * 100,
                    "spend": 1_000.0,
                }
            )
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Empty / missing column guards
# ---------------------------------------------------------------------------


def test_empty_dataframe_is_invalid():
    df = pd.DataFrame(columns=["region", "period", "metric"])
    result = validate_upload(df)
    assert not result.is_valid
    assert any("no data" in e.lower() for e in result.errors)


def test_missing_required_column_raises_clear_error():
    df = pd.DataFrame({"region": ["CA"], "metric": [100]})  # missing "period"
    result = validate_upload(df)
    assert not result.is_valid
    assert any("period" in e for e in result.errors)
    assert any("missing" in e.lower() for e in result.errors)


def test_missing_two_required_columns_reports_both():
    df = pd.DataFrame({"region": ["CA"]})  # missing period and metric
    result = validate_upload(df)
    assert not result.is_valid
    error_text = " ".join(result.errors)
    assert "period" in error_text
    assert "metric" in error_text


def test_valid_dataframe_passes():
    df = make_valid_df()
    result = validate_upload(df)
    assert result.is_valid
    assert len(result.errors) == 0


# ---------------------------------------------------------------------------
# Row count
# ---------------------------------------------------------------------------


def test_below_minimum_rows_is_invalid():
    df = make_valid_df(n_rows=10, n_geos=2)
    result = validate_upload(df, min_rows=MIN_ROWS)
    assert not result.is_valid
    assert any("minimum" in e.lower() for e in result.errors)


def test_exact_minimum_rows_is_valid():
    df = make_valid_df(n_rows=MIN_ROWS, n_geos=5)
    result = validate_upload(df, min_rows=MIN_ROWS)
    # may still have other issues but row count check passes
    assert not any("minimum" in e.lower() for e in result.errors)


# ---------------------------------------------------------------------------
# Geo column
# ---------------------------------------------------------------------------


def test_null_geo_values_are_invalid():
    df = make_valid_df()
    df.loc[0, "region"] = None
    result = validate_upload(df)
    assert not result.is_valid
    assert any("region" in e and "missing" in e.lower() for e in result.errors)


def test_all_null_geo_column_reports_count():
    df = make_valid_df()
    df["region"] = None
    result = validate_upload(df)
    assert not result.is_valid


# ---------------------------------------------------------------------------
# Period column
# ---------------------------------------------------------------------------


def test_integer_period_column_is_valid():
    df = make_valid_df()
    df["period"] = range(len(df))
    result = validate_upload(df)
    assert result.is_valid


def test_iso_date_period_column_is_valid():
    df = make_valid_df()
    import datetime
    base = datetime.date(2024, 1, 1)
    df["period"] = [(base + datetime.timedelta(weeks=i)).isoformat() for i in range(len(df))]
    result = validate_upload(df)
    assert not any("period" in e and "parsed" in e for e in result.errors)


def test_garbage_period_column_is_invalid():
    df = make_valid_df()
    df["period"] = ["not_a_date"] * len(df)
    result = validate_upload(df)
    assert not result.is_valid
    assert any("period" in e for e in result.errors)


def test_mixed_date_formats_flagged_as_invalid():
    """
    Mixed date formats (e.g., ISO + US) cannot be reliably parsed and should
    produce a period column error. Users must use a consistent date format.
    """
    n = 50
    periods = ["2024-01-01"] * (n // 2) + ["01/15/2024"] * (n - n // 2)
    df = pd.DataFrame({
        "region": [f"GEO_{i}" for i in range(n)],
        "period": periods,
        "metric": [1000.0] * n,
    })
    result = validate_upload(df)
    # Mixed formats are ambiguous — validation should flag the period column
    assert not result.is_valid
    assert any("period" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Numeric column
# ---------------------------------------------------------------------------


def test_non_numeric_metric_is_invalid():
    df = make_valid_df()
    # Cast metric to object first so pandas 3.x accepts the string assignment
    df["metric"] = df["metric"].astype(object)
    df.loc[0, "metric"] = "N/A"
    result = validate_upload(df)
    assert not result.is_valid
    assert any("metric" in e and "non-numeric" in e.lower() for e in result.errors)


def test_numeric_metric_as_string_is_valid():
    """Stringified numbers should be coercible."""
    df = make_valid_df()
    df["metric"] = df["metric"].astype(str)
    result = validate_upload(df)
    assert result.is_valid


def test_negative_metric_generates_warning_not_error():
    df = make_valid_df()
    df.loc[0, "metric"] = -500.0
    result = validate_upload(df)
    assert result.is_valid  # warnings don't block
    assert any("negative" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


def test_duplicate_region_period_flagged():
    df = pd.DataFrame(
        {
            "region": ["CA", "CA", "NY"],
            "period": ["2024-01-01", "2024-01-01", "2024-01-01"],
            "metric": [100.0, 200.0, 300.0],
        }
    )
    result = validate_upload(df, min_rows=1)
    assert any("duplicate" in w.lower() for w in result.warnings)


def test_no_duplicates_no_warning():
    df = make_valid_df()
    result = validate_upload(df)
    assert not any("duplicate" in w.lower() for w in result.warnings)


# ---------------------------------------------------------------------------
# Optional spend column
# ---------------------------------------------------------------------------


def test_non_numeric_spend_generates_warning():
    df = make_valid_df()
    df["spend"] = df["spend"].astype(object)
    df.loc[0, "spend"] = "unknown"
    result = validate_upload(df)
    # spend is optional — errors become warnings
    assert any("spend" in w.lower() for w in result.warnings)


def test_missing_spend_column_does_not_block():
    """spend is optional; omitting it should not cause errors."""
    df = make_valid_df().drop(columns=["spend"])
    result = validate_upload(df)
    assert result.is_valid


# ---------------------------------------------------------------------------
# Summary stats
# ---------------------------------------------------------------------------


def test_result_populates_row_count():
    df = make_valid_df(n_rows=50, n_geos=5)
    result = validate_upload(df)
    assert result.row_count == len(df)


def test_result_populates_geo_count():
    df = make_valid_df(n_rows=50, n_geos=5)
    result = validate_upload(df)
    assert result.geo_count == 5


def test_result_populates_period_count():
    df = make_valid_df(n_rows=50, n_geos=5)
    result = validate_upload(df)
    n_periods = df["period"].nunique()
    assert result.period_count == n_periods


# ---------------------------------------------------------------------------
# Custom column names
# ---------------------------------------------------------------------------


def test_custom_required_cols_respected():
    df = pd.DataFrame({"state": ["CA"] * 40, "week": range(40), "revenue": [1000.0] * 40})
    result = validate_upload(
        df,
        required_cols=["state", "week", "revenue"],
        numeric_cols=["revenue"],
        geo_col="state",
        period_col="week",
        metric_col="revenue",
        min_rows=30,
    )
    assert result.is_valid


def test_missing_custom_col_reported_by_name():
    df = pd.DataFrame({"state": ["CA"] * 40, "revenue": [1000.0] * 40})
    result = validate_upload(
        df,
        required_cols=["state", "week", "revenue"],
        geo_col="state",
        period_col="week",
        metric_col="revenue",
        min_rows=30,
    )
    assert not result.is_valid
    assert any("week" in e for e in result.errors)
