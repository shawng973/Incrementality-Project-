"""
Tests for column_mapping.py
"""

import pandas as pd
import pytest

from app.services.ingestion.column_mapping import (
    resolve_column_mapping,
    apply_mapping,
    COLUMN_ALIASES,
    REQUIRED_CANONICAL,
    CANONICAL_REGION,
    CANONICAL_PERIOD,
    CANONICAL_METRIC,
    CANONICAL_SPEND,
)


# ---------------------------------------------------------------------------
# Exact / alias matching
# ---------------------------------------------------------------------------


def test_canonical_names_map_to_themselves():
    cols = ["region", "period", "metric"]
    result = resolve_column_mapping(cols)
    assert result.mapping["region"] == CANONICAL_REGION
    assert result.mapping["period"] == CANONICAL_PERIOD
    assert result.mapping["metric"] == CANONICAL_METRIC


def test_alias_revenue_maps_to_metric():
    result = resolve_column_mapping(["revenue", "week", "state"])
    assert result.mapping.get("revenue") == CANONICAL_METRIC


def test_alias_geo_maps_to_region():
    result = resolve_column_mapping(["geo", "period", "metric"])
    assert result.mapping.get("geo") == CANONICAL_REGION


def test_alias_dma_maps_to_region():
    result = resolve_column_mapping(["dma", "period", "metric"])
    assert result.mapping.get("dma") == CANONICAL_REGION


def test_alias_spend_variants():
    for alias in ["spend", "ad_spend", "media_spend", "cost"]:
        result = resolve_column_mapping(["region", "period", "metric", alias])
        assert result.mapping.get(alias) == CANONICAL_SPEND, f"Failed for alias '{alias}'"


def test_case_insensitive_matching():
    result = resolve_column_mapping(["REVENUE", "WEEK", "STATE"])
    assert result.mapping.get("REVENUE") == CANONICAL_METRIC
    assert result.mapping.get("WEEK") == CANONICAL_PERIOD
    assert result.mapping.get("STATE") == CANONICAL_REGION


def test_whitespace_trimmed_in_matching():
    result = resolve_column_mapping(["revenue", " week ", "state"])
    # " week " should trim to "week" → period
    assert result.mapping.get(" week ") == CANONICAL_PERIOD


# ---------------------------------------------------------------------------
# Completeness
# ---------------------------------------------------------------------------


def test_complete_mapping_is_valid():
    result = resolve_column_mapping(["state", "week", "revenue"])
    assert result.is_complete
    assert len(result.missing_canonical) == 0


def test_missing_metric_reported():
    result = resolve_column_mapping(["state", "week"])  # no metric
    assert CANONICAL_METRIC in result.missing_canonical
    assert not result.is_complete


def test_all_required_missing_reported():
    result = resolve_column_mapping(["irrelevant_col"])
    for canonical in REQUIRED_CANONICAL:
        assert canonical in result.missing_canonical


def test_unmapped_columns_reported():
    result = resolve_column_mapping(["state", "week", "revenue", "custom_kpi"])
    assert "custom_kpi" in result.unmapped_upload_cols


def test_unmapped_generates_warning():
    result = resolve_column_mapping(["state", "week", "revenue", "custom_kpi"])
    assert any("custom_kpi" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Explicit overrides
# ---------------------------------------------------------------------------


def test_explicit_override_takes_priority_over_alias():
    # "revenue" normally maps to metric; override sends it to spend
    result = resolve_column_mapping(
        ["revenue", "week", "state"],
        explicit_overrides={"revenue": "spend"},
    )
    assert result.mapping.get("revenue") == CANONICAL_SPEND


def test_explicit_override_resolves_unrecognized_column():
    result = resolve_column_mapping(
        ["custom_revenue_col", "week", "state"],
        explicit_overrides={"custom_revenue_col": "metric"},
    )
    assert result.mapping.get("custom_revenue_col") == CANONICAL_METRIC
    assert result.is_complete


def test_explicit_override_case_insensitive():
    result = resolve_column_mapping(
        ["Revenue_Total", "week", "state"],
        explicit_overrides={"revenue_total": "metric"},
    )
    assert result.mapping.get("Revenue_Total") == CANONICAL_METRIC


# ---------------------------------------------------------------------------
# Collision detection
# ---------------------------------------------------------------------------


def test_two_columns_mapping_to_same_canonical_is_error():
    # "revenue" → metric AND "sales" → metric → collision
    result = resolve_column_mapping(["revenue", "sales", "week", "state"])
    assert len(result.errors) > 0
    assert any("metric" in e for e in result.errors)
    assert not result.is_complete


# ---------------------------------------------------------------------------
# apply_mapping
# ---------------------------------------------------------------------------


def test_apply_mapping_renames_columns():
    df = pd.DataFrame({"revenue": [100.0], "week": [1], "state": ["CA"]})
    mapping = {"revenue": "metric", "week": "period", "state": "region"}
    result_df = apply_mapping(df, mapping)
    assert "metric" in result_df.columns
    assert "period" in result_df.columns
    assert "region" in result_df.columns


def test_apply_mapping_ignores_unmapped_columns():
    df = pd.DataFrame({"revenue": [100.0], "custom_col": ["X"]})
    mapping = {"revenue": "metric"}
    result_df = apply_mapping(df, mapping)
    assert "custom_col" in result_df.columns  # unchanged
    assert "metric" in result_df.columns


def test_apply_mapping_does_not_modify_original():
    df = pd.DataFrame({"revenue": [100.0]})
    original_cols = list(df.columns)
    apply_mapping(df, {"revenue": "metric"})
    assert list(df.columns) == original_cols


def test_apply_mapping_returns_dataframe():
    df = pd.DataFrame({"revenue": [100.0]})
    result = apply_mapping(df, {"revenue": "metric"})
    assert isinstance(result, pd.DataFrame)


# ---------------------------------------------------------------------------
# Alias dictionary integrity
# ---------------------------------------------------------------------------


def test_all_alias_values_are_valid_canonical_names():
    """Every alias must map to one of the known canonical column names."""
    from app.services.ingestion.column_mapping import REQUIRED_CANONICAL, OPTIONAL_CANONICAL
    all_canonical = set(REQUIRED_CANONICAL + OPTIONAL_CANONICAL)
    for alias, canonical in COLUMN_ALIASES.items():
        assert canonical in all_canonical, (
            f"Alias '{alias}' maps to '{canonical}' which is not a known canonical column"
        )
