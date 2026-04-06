"""
Tests for twfe_did.py — the primary causal estimator.

These are the highest-stakes tests in the entire suite.
Every test has analytically derived ground truth.
"""

import numpy as np
import pandas as pd
import pytest

from app.services.statistical.twfe_did import (
    run_twfe_did,
    _absorb_fixed_effects,
    _clustered_se,
    TWFEResult,
)
from tests.statistical.conftest import TRUE_LIFT


# ---------------------------------------------------------------------------
# Known-output tests (core correctness)
# ---------------------------------------------------------------------------


def test_twfe_positive_effect_detected(dataset_positive_effect):
    """
    50 geos, 12 baseline weeks, 8 test weeks, known +15% lift injected.
    β₃ should be within 1% of 0.15.
    """
    result = run_twfe_did(dataset_positive_effect)
    assert abs(result.treatment_effect - TRUE_LIFT) < 0.01, (
        f"Expected treatment_effect ≈ {TRUE_LIFT}, got {result.treatment_effect:.4f}"
    )


def test_twfe_positive_effect_is_significant(dataset_positive_effect):
    result = run_twfe_did(dataset_positive_effect)
    assert result.p_value < 0.05


def test_twfe_positive_effect_90_ci_excludes_zero(dataset_positive_effect):
    result = run_twfe_did(dataset_positive_effect)
    assert result.ci_90_lower > 0, (
        f"90% CI lower bound should be > 0, got {result.ci_90_lower:.4f}"
    )


def test_twfe_null_effect_not_significant(dataset_null_effect):
    """
    No lift injected. β₃ should be ≈ 0 and p-value should not be < 0.05.
    """
    result = run_twfe_did(dataset_null_effect)
    assert abs(result.treatment_effect) < 0.05, (
        f"Expected β₃ ≈ 0, got {result.treatment_effect:.4f}"
    )
    assert result.p_value > 0.05, (
        f"Expected non-significant result, got p={result.p_value:.4f}"
    )


def test_twfe_treatment_effect_direction_positive_for_positive_lift(dataset_positive_effect):
    result = run_twfe_did(dataset_positive_effect)
    assert result.treatment_effect > 0


def test_twfe_treatment_effect_direction_near_zero_for_null(dataset_null_effect):
    result = run_twfe_did(dataset_null_effect)
    # Should be small in magnitude, either direction
    assert abs(result.treatment_effect) < 0.10


# ---------------------------------------------------------------------------
# Fixed effects
# ---------------------------------------------------------------------------


def test_twfe_geo_fixed_effects_count(dataset_positive_effect):
    result = run_twfe_did(dataset_positive_effect)
    n_geos = dataset_positive_effect["geo"].nunique()
    assert result.geo_fixed_effects_count == n_geos


def test_twfe_time_fixed_effects_count(dataset_positive_effect):
    result = run_twfe_did(dataset_positive_effect)
    n_weeks = dataset_positive_effect["week"].nunique()  # 12 baseline + 8 test = 20
    assert result.time_fixed_effects_count == n_weeks


# ---------------------------------------------------------------------------
# Clustered standard errors
# ---------------------------------------------------------------------------


def test_clustered_se_greater_than_or_equal_unclustered(dataset_positive_effect):
    """
    Geo-clustered SEs should be >= OLS SEs (intra-cluster correlation inflates SE).
    This is the fundamental property of clustered SEs.
    """
    result_clustered = run_twfe_did(dataset_positive_effect, cluster=True)
    result_unclustered = run_twfe_did(dataset_positive_effect, cluster=False)
    assert result_clustered.standard_error >= result_unclustered.standard_error * 0.95  # small tolerance


def test_clustered_flag_is_recorded(dataset_positive_effect):
    r_clustered = run_twfe_did(dataset_positive_effect, cluster=True)
    r_unclustered = run_twfe_did(dataset_positive_effect, cluster=False)
    assert r_clustered.clustered_se_used is True
    assert r_unclustered.clustered_se_used is False


# ---------------------------------------------------------------------------
# Confidence intervals
# ---------------------------------------------------------------------------


def test_ci_ordering_is_correct(dataset_positive_effect):
    """CIs should widen as confidence level increases: 80% ⊂ 90% ⊂ 95%."""
    r = run_twfe_did(dataset_positive_effect)
    assert r.ci_80_lower >= r.ci_90_lower >= r.ci_95_lower
    assert r.ci_80_upper <= r.ci_90_upper <= r.ci_95_upper


def test_treatment_effect_inside_all_cis(dataset_positive_effect):
    r = run_twfe_did(dataset_positive_effect)
    for lower, upper in [
        (r.ci_80_lower, r.ci_80_upper),
        (r.ci_90_lower, r.ci_90_upper),
        (r.ci_95_lower, r.ci_95_upper),
    ]:
        assert lower <= r.treatment_effect <= upper


def test_ci_symmetric_around_point_estimate(dataset_positive_effect):
    """CIs should be symmetric: (β₃ - lower) ≈ (upper - β₃)."""
    r = run_twfe_did(dataset_positive_effect)
    for lower, upper in [
        (r.ci_80_lower, r.ci_80_upper),
        (r.ci_90_lower, r.ci_90_upper),
        (r.ci_95_lower, r.ci_95_upper),
    ]:
        half_width = (upper - lower) / 2
        assert abs((r.treatment_effect - lower) - half_width) < 1e-9


# ---------------------------------------------------------------------------
# Dollar translation
# ---------------------------------------------------------------------------


def test_treatment_effect_dollars_sign_matches_effect(dataset_positive_effect):
    r = run_twfe_did(dataset_positive_effect)
    assert r.treatment_effect_dollars > 0


def test_treatment_effect_dollars_near_expected(dataset_positive_effect):
    """treatment_effect_dollars ≈ treatment_effect (proportion) × avg_baseline_mean."""
    r = run_twfe_did(dataset_positive_effect)
    baseline = dataset_positive_effect[
        (dataset_positive_effect["is_treatment"] == 1) &
        (dataset_positive_effect["period"] == 0)
    ]
    avg_baseline = baseline["revenue"].mean()
    # treatment_effect_dollars = beta3 * avg_baseline
    # For a 15% lift: ≈ 0.15 * 100_000 = $15,000 per geo per week
    expected_dollars = r.treatment_effect * avg_baseline
    assert abs(r.treatment_effect_dollars - expected_dollars) / abs(expected_dollars) < 0.01


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_missing_column_raises_value_error(dataset_positive_effect):
    df = dataset_positive_effect.drop(columns=["revenue"])
    with pytest.raises(ValueError, match="Missing required columns"):
        run_twfe_did(df)


def test_single_treatment_value_raises(dataset_positive_effect):
    df = dataset_positive_effect.copy()
    df["is_treatment"] = 0  # all control
    with pytest.raises(ValueError, match="treatment_col"):
        run_twfe_did(df)


def test_single_period_value_raises(dataset_positive_effect):
    df = dataset_positive_effect[dataset_positive_effect["period"] == 0].copy()
    with pytest.raises(ValueError, match="post_col"):
        run_twfe_did(df)


# ---------------------------------------------------------------------------
# _absorb_fixed_effects
# ---------------------------------------------------------------------------


def test_demeaned_column_has_near_zero_group_means():
    """After within-transformation, geo means and time means should be ≈ 0."""
    df = pd.DataFrame({
        "geo": ["A", "A", "B", "B"],
        "week": [0, 1, 0, 1],
        "revenue": [100.0, 110.0, 200.0, 210.0],
    })
    df_out = _absorb_fixed_effects(df, "revenue", "geo", "week")
    geo_means = df_out.groupby("geo")["revenue_demeaned"].mean()
    time_means = df_out.groupby("week")["revenue_demeaned"].mean()
    assert (geo_means.abs() < 1e-9).all()
    assert (time_means.abs() < 1e-9).all()


# ---------------------------------------------------------------------------
# _clustered_se
# ---------------------------------------------------------------------------


def test_clustered_se_shape():
    """Should return one SE per parameter."""
    rng = np.random.default_rng(0)
    n = 60
    X = np.column_stack([np.ones(n), rng.normal(size=n)])
    y = rng.normal(size=n)
    params = np.linalg.lstsq(X, y, rcond=None)[0]
    groups = np.repeat(np.arange(20), 3)  # 20 geos, 3 obs each
    ses = _clustered_se(y, X, params, groups)
    assert ses.shape == (2,)
    assert (ses >= 0).all()


def test_clustered_se_positive():
    rng = np.random.default_rng(42)
    n = 40
    X = np.column_stack([np.ones(n), rng.standard_normal(n)])
    y = X @ np.array([1.0, 2.0]) + rng.standard_normal(n) * 0.5
    params = np.linalg.lstsq(X, y, rcond=None)[0]
    groups = np.repeat(np.arange(10), 4)
    ses = _clustered_se(y, X, params, groups)
    assert (ses > 0).all()
