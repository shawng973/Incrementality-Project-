"""Tests for pretrend_adjustment.py"""

import pytest

from app.services.statistical.pretrend_adjustment import (
    compute_pretrend_adjustment,
    P_THRESHOLD,
)


def test_clean_experiment_is_flagged_causally_clean(dataset_clean_pretrend):
    result = compute_pretrend_adjustment(
        df=dataset_clean_pretrend,
        raw_yoy_did_dollars=500_000.0,
    )
    assert result.is_causally_clean
    assert "causally clean" in result.diagnostic_note.lower()


def test_violated_experiment_is_not_clean(dataset_pretrend_violation):
    result = compute_pretrend_adjustment(
        df=dataset_pretrend_violation,
        raw_yoy_did_dollars=500_000.0,
    )
    assert not result.is_causally_clean


def test_clean_experiment_adjustment_is_small(dataset_clean_pretrend):
    """With no pre-trend, adjustment should be minimal."""
    raw = 500_000.0
    result = compute_pretrend_adjustment(
        df=dataset_clean_pretrend,
        raw_yoy_did_dollars=raw,
    )
    assert abs(result.adjustment_pct_of_raw) < 0.30  # < 30% shift


def test_adjusted_dollars_equals_raw_minus_adjustment(dataset_clean_pretrend):
    raw = 400_000.0
    result = compute_pretrend_adjustment(
        df=dataset_clean_pretrend,
        raw_yoy_did_dollars=raw,
    )
    expected = raw - result.adjustment_dollars
    assert result.adjusted_yoy_did_dollars == pytest.approx(expected, rel=1e-9)


def test_p_value_in_range(dataset_positive_effect):
    result = compute_pretrend_adjustment(
        df=dataset_positive_effect,
        raw_yoy_did_dollars=300_000.0,
    )
    assert 0.0 <= result.beta_pre_p_value <= 1.0


def test_missing_column_raises(dataset_positive_effect):
    df = dataset_positive_effect.drop(columns=["revenue"])
    with pytest.raises(ValueError, match="Missing required columns"):
        compute_pretrend_adjustment(df=df, raw_yoy_did_dollars=100_000.0)


def test_insufficient_baseline_raises(dataset_positive_effect):
    df = dataset_positive_effect.head(5)
    with pytest.raises(ValueError, match="Insufficient baseline"):
        compute_pretrend_adjustment(df=df, raw_yoy_did_dollars=100_000.0)


def test_diagnostic_note_contains_beta(dataset_positive_effect):
    result = compute_pretrend_adjustment(
        df=dataset_positive_effect,
        raw_yoy_did_dollars=300_000.0,
    )
    assert "β_pre" in result.diagnostic_note
