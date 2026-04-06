"""Tests for reconciled_incrementality.py"""

import pytest

from app.services.statistical.reconciled_incrementality import (
    reconcile_incrementality,
    LARGE_DIVERGENCE_THRESHOLD,
)


def test_midpoint_is_average_of_two_estimates():
    result = reconcile_incrementality(
        twfe_did_dollars=400_000.0,
        adjusted_yoy_dollars=600_000.0,
        twfe_se=20_000.0,
        yoy_se=30_000.0,
    )
    assert result.midpoint_dollars == pytest.approx(500_000.0, rel=1e-9)


def test_variance_weighted_closer_to_lower_variance_estimate():
    """Lower SE (higher precision) → variance-weighted should be pulled toward that estimate."""
    # twfe_se=10k (precise), yoy_se=100k (imprecise)
    result = reconcile_incrementality(
        twfe_did_dollars=400_000.0,
        adjusted_yoy_dollars=600_000.0,
        twfe_se=10_000.0,
        yoy_se=100_000.0,
    )
    # Variance-weighted should be closer to twfe (lower variance)
    assert abs(result.variance_weighted_dollars - 400_000.0) < abs(result.variance_weighted_dollars - 600_000.0)


def test_equal_variance_variance_weighted_equals_midpoint():
    result = reconcile_incrementality(
        twfe_did_dollars=400_000.0,
        adjusted_yoy_dollars=600_000.0,
        twfe_se=25_000.0,
        yoy_se=25_000.0,
    )
    assert result.variance_weighted_dollars == pytest.approx(result.midpoint_dollars, rel=1e-6)


def test_zero_se_trusts_that_estimate():
    """If twfe_se=0, variance-weighted should equal twfe_did exactly."""
    result = reconcile_incrementality(
        twfe_did_dollars=400_000.0,
        adjusted_yoy_dollars=600_000.0,
        twfe_se=0.0,
        yoy_se=25_000.0,
    )
    assert result.variance_weighted_dollars == pytest.approx(400_000.0, rel=1e-9)


def test_both_zero_se_falls_back_to_midpoint():
    result = reconcile_incrementality(
        twfe_did_dollars=400_000.0,
        adjusted_yoy_dollars=600_000.0,
        twfe_se=0.0,
        yoy_se=0.0,
    )
    assert result.variance_weighted_dollars == pytest.approx(500_000.0, rel=1e-9)


def test_negative_se_raises():
    with pytest.raises(ValueError, match="non-negative"):
        reconcile_incrementality(
            twfe_did_dollars=400_000.0,
            adjusted_yoy_dollars=600_000.0,
            twfe_se=-1.0,
            yoy_se=25_000.0,
        )


def test_large_divergence_flagged():
    # Force large divergence: one estimate 10x the other
    result = reconcile_incrementality(
        twfe_did_dollars=100_000.0,
        adjusted_yoy_dollars=1_000_000.0,
        twfe_se=5_000.0,
        yoy_se=500_000.0,  # high YoY SE → weighted toward twfe
    )
    assert result.has_large_divergence


def test_small_divergence_not_flagged():
    result = reconcile_incrementality(
        twfe_did_dollars=490_000.0,
        adjusted_yoy_dollars=510_000.0,
        twfe_se=20_000.0,
        yoy_se=20_000.0,
    )
    assert not result.has_large_divergence


def test_divergence_pct_is_non_negative():
    result = reconcile_incrementality(
        twfe_did_dollars=400_000.0,
        adjusted_yoy_dollars=600_000.0,
        twfe_se=20_000.0,
        yoy_se=20_000.0,
    )
    assert result.divergence_pct >= 0
