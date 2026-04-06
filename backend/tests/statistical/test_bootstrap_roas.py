"""Tests for bootstrap_roas.py"""

import pytest

from app.services.statistical.bootstrap_roas import run_bootstrap_roas
from tests.statistical.conftest import (
    TRUE_LIFT,
    TOTAL_TEST_PERIOD_SPEND,
    TRUE_ROAS_MID,
    BASE_REVENUE,
    N_GEOS,
    N_TEST_WEEKS,
)


# Approximate incremental revenue for test fixtures
_APPROX_TWFE = BASE_REVENUE * TRUE_LIFT * (N_GEOS // 2) * N_TEST_WEEKS
_APPROX_YOY = _APPROX_TWFE * 1.02   # slight variation
_APPROX_RECONCILED = (_APPROX_TWFE + _APPROX_YOY) / 2


def test_roas_mid_between_low_and_high(dataset_positive_effect):
    result = run_bootstrap_roas(
        df=dataset_positive_effect,
        twfe_did_dollars=_APPROX_TWFE,
        reconciled_dollars=_APPROX_RECONCILED,
        adjusted_yoy_dollars=_APPROX_YOY,
        spend=TOTAL_TEST_PERIOD_SPEND,
        n_resamples=500,
    )
    assert result.roas_low <= result.roas_mid <= result.roas_high


def test_roas_mid_near_true_value(dataset_positive_effect):
    """roas_mid should be within 20% of the analytically known ROAS."""
    result = run_bootstrap_roas(
        df=dataset_positive_effect,
        twfe_did_dollars=_APPROX_TWFE,
        reconciled_dollars=_APPROX_RECONCILED,
        adjusted_yoy_dollars=_APPROX_YOY,
        spend=TOTAL_TEST_PERIOD_SPEND,
        n_resamples=500,
    )
    assert abs(result.roas_mid - TRUE_ROAS_MID) / TRUE_ROAS_MID < 0.20


def test_ci_ordering_95_wider_than_80(dataset_positive_effect):
    result = run_bootstrap_roas(
        df=dataset_positive_effect,
        twfe_did_dollars=_APPROX_TWFE,
        reconciled_dollars=_APPROX_RECONCILED,
        adjusted_yoy_dollars=_APPROX_YOY,
        spend=TOTAL_TEST_PERIOD_SPEND,
        n_resamples=500,
    )
    width_95 = result.ci_95_upper - result.ci_95_lower
    width_80 = result.ci_80_upper - result.ci_80_lower
    assert width_95 >= width_80


def test_ci_width_increases_with_variance(dataset_low_variance, dataset_high_variance):
    kwargs = dict(
        twfe_did_dollars=_APPROX_TWFE,
        reconciled_dollars=_APPROX_RECONCILED,
        adjusted_yoy_dollars=_APPROX_YOY,
        spend=TOTAL_TEST_PERIOD_SPEND,
        n_resamples=500,
    )
    low_result = run_bootstrap_roas(df=dataset_low_variance, **kwargs)
    high_result = run_bootstrap_roas(df=dataset_high_variance, **kwargs)
    low_width = low_result.ci_95_upper - low_result.ci_95_lower
    high_width = high_result.ci_95_upper - high_result.ci_95_lower
    assert high_width > low_width


def test_roas_values_are_positive(dataset_positive_effect):
    result = run_bootstrap_roas(
        df=dataset_positive_effect,
        twfe_did_dollars=_APPROX_TWFE,
        reconciled_dollars=_APPROX_RECONCILED,
        adjusted_yoy_dollars=_APPROX_YOY,
        spend=TOTAL_TEST_PERIOD_SPEND,
        n_resamples=200,
    )
    assert result.roas_low > 0
    assert result.roas_mid > 0
    assert result.roas_high > 0


def test_results_deterministic(dataset_positive_effect):
    kwargs = dict(
        df=dataset_positive_effect,
        twfe_did_dollars=_APPROX_TWFE,
        reconciled_dollars=_APPROX_RECONCILED,
        adjusted_yoy_dollars=_APPROX_YOY,
        spend=TOTAL_TEST_PERIOD_SPEND,
        n_resamples=200,
        seed=99,
    )
    r1 = run_bootstrap_roas(**kwargs)
    r2 = run_bootstrap_roas(**kwargs)
    assert r1.ci_95_lower == pytest.approx(r2.ci_95_lower, rel=1e-9)
    assert r1.ci_95_upper == pytest.approx(r2.ci_95_upper, rel=1e-9)


def test_zero_spend_raises(dataset_positive_effect):
    with pytest.raises(ValueError, match="spend must be positive"):
        run_bootstrap_roas(
            df=dataset_positive_effect,
            twfe_did_dollars=_APPROX_TWFE,
            reconciled_dollars=_APPROX_RECONCILED,
            adjusted_yoy_dollars=_APPROX_YOY,
            spend=0.0,
        )


def test_too_few_resamples_raises(dataset_positive_effect):
    with pytest.raises(ValueError, match="n_resamples must be"):
        run_bootstrap_roas(
            df=dataset_positive_effect,
            twfe_did_dollars=_APPROX_TWFE,
            reconciled_dollars=_APPROX_RECONCILED,
            adjusted_yoy_dollars=_APPROX_YOY,
            spend=TOTAL_TEST_PERIOD_SPEND,
            n_resamples=50,
        )


def test_n_resamples_recorded(dataset_positive_effect):
    result = run_bootstrap_roas(
        df=dataset_positive_effect,
        twfe_did_dollars=_APPROX_TWFE,
        reconciled_dollars=_APPROX_RECONCILED,
        adjusted_yoy_dollars=_APPROX_YOY,
        spend=TOTAL_TEST_PERIOD_SPEND,
        n_resamples=200,
    )
    assert result.n_resamples == 200
