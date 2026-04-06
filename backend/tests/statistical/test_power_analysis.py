"""
Tests for power_analysis.py
"""

import math

import pytest

from app.services.statistical.power_analysis import (
    compute_power,
    estimate_baseline_stats,
    _find_required_weeks,
    VALID_ALPHA,
)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_zero_geos_raises():
    with pytest.raises(ValueError, match="n_geos_per_cell"):
        compute_power(n_geos_per_cell=0, baseline_weekly_variance=1000.0, baseline_weekly_mean=100.0)


def test_negative_variance_raises():
    with pytest.raises(ValueError, match="variance"):
        compute_power(n_geos_per_cell=10, baseline_weekly_variance=-1.0, baseline_weekly_mean=100.0)


def test_zero_mean_raises():
    with pytest.raises(ValueError, match="mean"):
        compute_power(n_geos_per_cell=10, baseline_weekly_variance=100.0, baseline_weekly_mean=0.0)


def test_mde_zero_raises():
    with pytest.raises(ValueError, match="mde"):
        compute_power(n_geos_per_cell=10, baseline_weekly_variance=100.0, baseline_weekly_mean=100.0, mde=0.0)


def test_mde_one_raises():
    with pytest.raises(ValueError, match="mde"):
        compute_power(n_geos_per_cell=10, baseline_weekly_variance=100.0, baseline_weekly_mean=100.0, mde=1.0)


def test_invalid_alpha_raises():
    with pytest.raises(ValueError, match="alpha"):
        compute_power(n_geos_per_cell=10, baseline_weekly_variance=100.0, baseline_weekly_mean=100.0, alpha=0.01)


# ---------------------------------------------------------------------------
# Monotonicity tests (direction checks)
# ---------------------------------------------------------------------------


def test_power_increases_with_more_geos():
    kwargs = dict(baseline_weekly_variance=5000.0, baseline_weekly_mean=100.0, mde=0.10, n_test_weeks=8)
    r5 = compute_power(n_geos_per_cell=5, **kwargs)
    r25 = compute_power(n_geos_per_cell=25, **kwargs)
    assert r25.power > r5.power


def test_power_increases_with_more_weeks():
    kwargs = dict(n_geos_per_cell=10, baseline_weekly_variance=5000.0, baseline_weekly_mean=100.0, mde=0.10)
    r4 = compute_power(n_test_weeks=4, **kwargs)
    r16 = compute_power(n_test_weeks=16, **kwargs)
    assert r16.power > r4.power


def test_power_increases_with_larger_mde():
    """Larger effect → easier to detect → more power."""
    kwargs = dict(n_geos_per_cell=10, baseline_weekly_variance=5000.0, baseline_weekly_mean=100.0, n_test_weeks=8)
    r5pct = compute_power(mde=0.05, **kwargs)
    r25pct = compute_power(mde=0.25, **kwargs)
    assert r25pct.power > r5pct.power


def test_power_decreases_with_higher_variance():
    kwargs = dict(n_geos_per_cell=15, baseline_weekly_mean=100.0, mde=0.10, n_test_weeks=8)
    r_low = compute_power(baseline_weekly_variance=500.0, **kwargs)
    r_high = compute_power(baseline_weekly_variance=50000.0, **kwargs)
    assert r_low.power > r_high.power


def test_power_decreases_with_stricter_alpha():
    """Stricter alpha (smaller) → higher threshold → lower power."""
    kwargs = dict(n_geos_per_cell=10, baseline_weekly_variance=5000.0, baseline_weekly_mean=100.0, mde=0.10, n_test_weeks=8)
    r_lenient = compute_power(alpha=0.20, **kwargs)  # 80% CI
    r_strict = compute_power(alpha=0.05, **kwargs)   # 95% CI
    assert r_lenient.power > r_strict.power


# ---------------------------------------------------------------------------
# Adequacy flags
# ---------------------------------------------------------------------------


def test_well_powered_test_is_flagged_adequate():
    """50 geos/cell, 12 weeks, low variance → should be well powered."""
    result = compute_power(
        n_geos_per_cell=50,
        baseline_weekly_variance=500.0,
        baseline_weekly_mean=100_000.0,
        mde=0.10,
        n_test_weeks=12,
        alpha=0.10,
        target_power=0.80,
    )
    assert result.is_adequately_powered
    assert result.warning_message is None


def test_underpowered_test_is_flagged(dataset_underpowered):
    """
    4 geos per cell, high variance → power < 80% at 15% MDE.
    Uses the underpowered fixture from conftest.
    """
    baseline = dataset_underpowered[dataset_underpowered["period"] == 0]
    mean, var = estimate_baseline_stats(baseline, metric_col="revenue")
    n_geos_per_cell = 4  # 8 geos total, 2 cells

    result = compute_power(
        n_geos_per_cell=n_geos_per_cell,
        baseline_weekly_variance=var,
        baseline_weekly_mean=mean,
        mde=0.15,
        n_test_weeks=8,
        alpha=0.10,
        target_power=0.80,
    )
    assert not result.is_adequately_powered
    assert result.warning_message is not None
    assert result.power < 0.80


def test_underpowered_warning_contains_recommendations():
    result = compute_power(
        n_geos_per_cell=2,
        baseline_weekly_variance=100_000.0,
        baseline_weekly_mean=1_000.0,
        mde=0.05,
        n_test_weeks=4,
        alpha=0.10,
        target_power=0.80,
    )
    assert not result.is_adequately_powered
    assert "weeks" in result.warning_message
    assert "geos" in result.warning_message


# ---------------------------------------------------------------------------
# Power bounds
# ---------------------------------------------------------------------------


def test_power_is_between_0_and_1():
    for n in [1, 5, 25, 100]:
        result = compute_power(
            n_geos_per_cell=n,
            baseline_weekly_variance=5_000.0,
            baseline_weekly_mean=100.0,
            mde=0.10,
            n_test_weeks=8,
        )
        assert 0.0 <= result.power <= 1.0


def test_zero_variance_yields_power_one():
    """If there is no noise, any effect is detectable."""
    result = compute_power(
        n_geos_per_cell=5,
        baseline_weekly_variance=0.0,
        baseline_weekly_mean=100.0,
        mde=0.10,
        n_test_weeks=8,
    )
    assert result.power == pytest.approx(1.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Required weeks
# ---------------------------------------------------------------------------


def test_required_weeks_decreases_with_more_geos():
    kwargs = dict(
        baseline_weekly_variance=5_000.0,
        baseline_weekly_mean=100.0,
        mde=0.10,
        alpha=0.10,
        target_power=0.80,
    )
    w5 = _find_required_weeks(n_geos_per_cell=5, **kwargs)
    w25 = _find_required_weeks(n_geos_per_cell=25, **kwargs)
    assert w5 >= w25


def test_required_weeks_is_positive_integer():
    w = _find_required_weeks(
        n_geos_per_cell=10,
        baseline_weekly_variance=5_000.0,
        baseline_weekly_mean=100.0,
        mde=0.10,
        alpha=0.10,
        target_power=0.80,
    )
    assert isinstance(w, int)
    assert w >= 1


# ---------------------------------------------------------------------------
# estimate_baseline_stats
# ---------------------------------------------------------------------------


def test_estimate_baseline_stats_returns_mean_and_variance(dataset_positive_effect):
    baseline = dataset_positive_effect[dataset_positive_effect["period"] == 0]
    mean, var = estimate_baseline_stats(baseline, metric_col="revenue")
    assert mean > 0
    assert var >= 0


def test_estimate_baseline_stats_mean_close_to_base_revenue(dataset_positive_effect):
    """Mean should be near BASE_REVENUE (100_000) from conftest."""
    baseline = dataset_positive_effect[dataset_positive_effect["period"] == 0]
    mean, _ = estimate_baseline_stats(baseline, metric_col="revenue")
    assert abs(mean - 100_000.0) / 100_000.0 < 0.15  # within 15%
