"""
Tests for feature_engineering.py

Strategy: all tests use either synthetic DataFrames with known properties
or the shared conftest fixtures. Every assertion has a numeric ground truth
derived analytically — no magic numbers.
"""

import numpy as np
import pandas as pd
import pytest

from app.services.statistical.feature_engineering import (
    compute_geo_features,
    normalize_features,
    _ols_slope,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_simple_panel(
    n_geos: int = 4,
    n_periods: int = 12,
    base: float = 100.0,
    slope: float = 0.0,
    noise: float = 0.0,
    seed: int = 0,
) -> pd.DataFrame:
    """Minimal panel with controllable properties."""
    rng = np.random.default_rng(seed)
    rows = []
    for g in range(n_geos):
        for t in range(n_periods):
            val = base + slope * t + rng.normal(0, noise)
            rows.append({"geo": f"GEO_{g}", "week": t, "revenue": val})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# _ols_slope unit tests
# ---------------------------------------------------------------------------


def test_ols_slope_flat_series_returns_zero():
    x = np.arange(10, dtype=float)
    y = np.full(10, 5.0)
    assert _ols_slope(x, y) == pytest.approx(0.0, abs=1e-10)


def test_ols_slope_perfectly_linear():
    """y = 3x + 2 → slope should be exactly 3."""
    x = np.arange(10, dtype=float)
    y = 3.0 * x + 2.0
    assert _ols_slope(x, y) == pytest.approx(3.0, rel=1e-9)


def test_ols_slope_negative_trend():
    x = np.arange(8, dtype=float)
    y = -2.0 * x + 50.0
    assert _ols_slope(x, y) == pytest.approx(-2.0, rel=1e-9)


def test_ols_slope_single_unique_x_returns_zero():
    """All x equal → no slope information, return 0."""
    x = np.ones(5)
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    assert _ols_slope(x, y) == 0.0


# ---------------------------------------------------------------------------
# compute_geo_features — input validation
# ---------------------------------------------------------------------------


def test_missing_required_column_raises_value_error():
    df = pd.DataFrame({"geo": ["A", "A"], "week": [0, 1]})  # no "revenue"
    with pytest.raises(ValueError, match="Missing required columns"):
        compute_geo_features(df)


def test_empty_dataframe_raises_value_error():
    df = pd.DataFrame(columns=["geo", "week", "revenue"])
    with pytest.raises(ValueError, match="empty"):
        compute_geo_features(df)


def test_geo_with_fewer_than_3_obs_raises_value_error():
    df = pd.DataFrame({"geo": ["A", "A"], "week": [0, 1], "revenue": [100.0, 110.0]})
    with pytest.raises(ValueError, match="minimum 3 required"):
        compute_geo_features(df)


# ---------------------------------------------------------------------------
# compute_geo_features — known-output tests
# ---------------------------------------------------------------------------


def test_avg_metric_equals_mean():
    """avg_metric should be the arithmetic mean of the metric column."""
    revenues = [80.0, 100.0, 120.0, 100.0]  # mean = 100
    df = pd.DataFrame(
        {"geo": ["A"] * 4, "week": [0, 1, 2, 3], "revenue": revenues}
    )
    features = compute_geo_features(df)
    assert features.loc["A", "avg_metric"] == pytest.approx(100.0, rel=1e-9)


def test_volatility_is_cv():
    """volatility = std / mean."""
    revenues = [80.0, 100.0, 120.0]
    df = pd.DataFrame({"geo": ["A"] * 3, "week": [0, 1, 2], "revenue": revenues})
    features = compute_geo_features(df)
    mu = np.mean(revenues)
    sigma = np.std(revenues, ddof=1)
    expected_cv = sigma / mu
    assert features.loc["A", "volatility"] == pytest.approx(expected_cv, rel=1e-6)


def test_volatility_zero_for_constant_series():
    """Constant series → std = 0 → CV = 0."""
    df = pd.DataFrame(
        {"geo": ["A"] * 5, "week": list(range(5)), "revenue": [100.0] * 5}
    )
    features = compute_geo_features(df)
    assert features.loc["A", "volatility"] == pytest.approx(0.0, abs=1e-10)


def test_growth_trend_matches_known_slope():
    """Perfectly linear series → growth_trend should match the slope."""
    slope = 5.0
    df = pd.DataFrame(
        {
            "geo": ["A"] * 10,
            "week": list(range(10)),
            "revenue": [100.0 + slope * t for t in range(10)],
        }
    )
    features = compute_geo_features(df)
    assert features.loc["A", "growth_trend"] == pytest.approx(slope, rel=1e-6)


def test_growth_trend_negative_for_declining_series():
    df = pd.DataFrame(
        {
            "geo": ["A"] * 6,
            "week": list(range(6)),
            "revenue": [200.0 - 10.0 * t for t in range(6)],
        }
    )
    features = compute_geo_features(df)
    assert features.loc["A", "growth_trend"] < 0


def test_market_size_equals_sum():
    revenues = [100.0, 150.0, 200.0, 50.0]
    df = pd.DataFrame(
        {"geo": ["A"] * 4, "week": list(range(4)), "revenue": revenues}
    )
    features = compute_geo_features(df)
    assert features.loc["A", "market_size"] == pytest.approx(sum(revenues), rel=1e-9)


def test_seasonality_stability_constant_series_equals_one():
    df = pd.DataFrame(
        {"geo": ["A"] * 5, "week": list(range(5)), "revenue": [100.0] * 5}
    )
    features = compute_geo_features(df)
    assert features.loc["A", "seasonality_stability"] == pytest.approx(1.0, rel=1e-9)


def test_seasonality_stability_increases_with_peak_trough_ratio():
    """Larger peak/trough spread → higher stability value."""
    low_swing = pd.DataFrame(
        {"geo": ["A"] * 4, "week": list(range(4)), "revenue": [90.0, 100.0, 110.0, 100.0]}
    )
    high_swing = pd.DataFrame(
        {"geo": ["A"] * 4, "week": list(range(4)), "revenue": [50.0, 100.0, 200.0, 100.0]}
    )
    low_feat = compute_geo_features(low_swing)
    high_feat = compute_geo_features(high_swing)
    assert high_feat.loc["A", "seasonality_stability"] > low_feat.loc["A", "seasonality_stability"]


def test_returns_one_row_per_geo():
    df = make_simple_panel(n_geos=10)
    features = compute_geo_features(df)
    assert len(features) == 10


def test_feature_index_matches_geo_ids(dataset_positive_effect):
    """Index of feature DataFrame should be the geo identifiers from input."""
    baseline = dataset_positive_effect[dataset_positive_effect["period"] == 0]
    features = compute_geo_features(baseline, metric_col="revenue")
    geo_ids_in = set(baseline["geo"].unique())
    geo_ids_out = set(features.index)
    assert geo_ids_in == geo_ids_out


def test_all_volatility_values_are_non_negative(dataset_positive_effect):
    baseline = dataset_positive_effect[dataset_positive_effect["period"] == 0]
    features = compute_geo_features(baseline)
    assert (features["volatility"] >= 0).all()


# ---------------------------------------------------------------------------
# normalize_features tests
# ---------------------------------------------------------------------------


def test_normalized_columns_have_zero_mean_and_unit_std():
    df = make_simple_panel(n_geos=20, noise=5.0, seed=99)
    baseline = df[df["week"] < 12]
    features = compute_geo_features(baseline)
    normed = normalize_features(features)
    for col in normed.columns:
        assert normed[col].mean() == pytest.approx(0.0, abs=1e-9)
        assert normed[col].std(ddof=1) == pytest.approx(1.0, rel=1e-6)


def test_normalize_zero_variance_column_becomes_zero():
    """Column with identical values should normalize to all zeros (not NaN or error)."""
    df = pd.DataFrame(
        {
            "avg_metric": [100.0, 100.0, 100.0],  # zero variance
            "volatility": [0.1, 0.2, 0.3],
        },
        index=["A", "B", "C"],
    )
    normed = normalize_features(df)
    assert (normed["avg_metric"] == 0.0).all()


def test_normalize_does_not_modify_original():
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0]}, index=["A", "B", "C"])
    original_values = df["x"].copy()
    normalize_features(df)
    pd.testing.assert_series_equal(df["x"], original_values)
