"""Tests for parallel_trends.py"""

import pytest

from app.services.statistical.parallel_trends import (
    test_parallel_trends as run_parallel_trends,
    P_VALUE_THRESHOLD,
)


def test_clean_pretrend_passes(dataset_clean_pretrend):
    result = run_parallel_trends(dataset_clean_pretrend)
    assert result.passes, f"Expected parallel trends to pass, p={result.p_value:.3f}"
    assert result.flag_message is None


def test_violated_pretrend_fails(dataset_pretrend_violation):
    result = run_parallel_trends(dataset_pretrend_violation)
    assert not result.passes, f"Expected parallel trends to fail, p={result.p_value:.3f}"
    assert result.flag_message is not None
    assert "biased" in result.flag_message.lower()


def test_p_value_in_range(dataset_positive_effect):
    result = run_parallel_trends(dataset_positive_effect)
    assert 0.0 <= result.p_value <= 1.0


def test_violation_has_positive_trend_coefficient(dataset_pretrend_violation):
    """pre_trend_slope=+0.02 → positive β_pre expected."""
    result = run_parallel_trends(dataset_pretrend_violation)
    assert result.trend_coefficient > 0


def test_clean_trend_coefficient_is_not_significant(dataset_clean_pretrend):
    """No pre-trend injected → p-value should be > 0.10 (regardless of coefficient magnitude)."""
    result = run_parallel_trends(dataset_clean_pretrend)
    assert result.p_value > P_VALUE_THRESHOLD


def test_missing_column_raises(dataset_positive_effect):
    df = dataset_positive_effect.drop(columns=["revenue"])
    with pytest.raises(ValueError, match="Missing required columns"):
        run_parallel_trends(df)


def test_insufficient_baseline_raises(dataset_positive_effect):
    df = dataset_positive_effect.head(5)
    with pytest.raises(ValueError, match="Insufficient baseline"):
        run_parallel_trends(df)


def test_flag_message_contains_p_value(dataset_pretrend_violation):
    result = run_parallel_trends(dataset_pretrend_violation)
    if not result.passes:
        assert "p=" in result.flag_message
