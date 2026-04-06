"""Tests for yoy_analysis.py"""

import numpy as np
import pytest

from app.services.statistical.yoy_analysis import run_yoy_analysis
from tests.statistical.conftest import TRUE_LIFT


def test_yoy_did_positive_for_positive_effect(dataset_yoy):
    result = run_yoy_analysis(dataset_yoy)
    assert result.yoy_did_proportion > 0


def test_yoy_did_close_to_true_lift(dataset_yoy):
    """
    YoY DiD should be in the right ballpark of +15%.
    Prior year has no lift, current year has +15% in treatment → YoY DiD ≈ TRUE_LIFT.
    """
    result = run_yoy_analysis(dataset_yoy)
    assert abs(result.yoy_did_proportion - TRUE_LIFT) < 0.08


def test_yoy_did_is_treatment_minus_control(dataset_yoy):
    result = run_yoy_analysis(dataset_yoy)
    expected = result.yoy_treatment - result.yoy_control
    assert result.yoy_did_proportion == pytest.approx(expected, rel=1e-9)


def test_weekly_yoy_shape(dataset_yoy):
    result = run_yoy_analysis(dataset_yoy)
    n_test_weeks = dataset_yoy[dataset_yoy["period"] == 1]["week"].nunique()
    assert len(result.weekly_yoy) == n_test_weeks


def test_weekly_yoy_columns(dataset_yoy):
    result = run_yoy_analysis(dataset_yoy)
    assert "yoy_treatment" in result.weekly_yoy.columns
    assert "yoy_control" in result.weekly_yoy.columns
    assert "yoy_did" in result.weekly_yoy.columns


def test_yoy_did_dollars_sign_matches_proportion(dataset_yoy):
    result = run_yoy_analysis(dataset_yoy)
    assert (result.yoy_did_dollars > 0) == (result.yoy_did_proportion > 0)


def test_missing_prior_col_raises(dataset_positive_effect):
    with pytest.raises(ValueError, match="Missing required columns"):
        run_yoy_analysis(dataset_positive_effect, prior_metric_col="revenue_prior")


def test_no_test_period_rows_raises(dataset_yoy):
    df_baseline_only = dataset_yoy[dataset_yoy["period"] == 0]
    with pytest.raises(ValueError, match="No test-period"):
        run_yoy_analysis(df_baseline_only)
