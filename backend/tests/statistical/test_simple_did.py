"""Tests for simple_did.py"""

import numpy as np
import pytest

from app.services.statistical.simple_did import run_simple_did
from tests.statistical.conftest import TRUE_LIFT


def test_simple_did_positive_effect_direction(dataset_positive_effect):
    result = run_simple_did(dataset_positive_effect)
    assert result.did_estimate > 0


def test_simple_did_estimate_close_to_true_lift(dataset_positive_effect):
    """Simple DiD should be in the right ballpark (±5pp) of 0.15."""
    result = run_simple_did(dataset_positive_effect)
    assert abs(result.did_estimate - TRUE_LIFT) < 0.05


def test_simple_did_null_effect_near_zero(dataset_null_effect):
    result = run_simple_did(dataset_null_effect)
    assert abs(result.did_estimate) < 0.05


def test_delta_treatment_minus_delta_control_equals_did(dataset_positive_effect):
    result = run_simple_did(dataset_positive_effect)
    expected = result.delta_treatment - result.delta_control
    assert result.did_estimate == pytest.approx(expected, rel=1e-9)


def test_weekly_did_shape(dataset_positive_effect):
    """Should have one row per test-period week."""
    result = run_simple_did(dataset_positive_effect)
    n_test_weeks = dataset_positive_effect[dataset_positive_effect["period"] == 1]["week"].nunique()
    assert len(result.weekly_did) == n_test_weeks


def test_weekly_did_columns_present(dataset_positive_effect):
    result = run_simple_did(dataset_positive_effect)
    assert "did_weekly" in result.weekly_did.columns
    assert "delta_treatment" in result.weekly_did.columns
    assert "delta_control" in result.weekly_did.columns


def test_did_dollars_same_sign_as_did_estimate(dataset_positive_effect):
    result = run_simple_did(dataset_positive_effect)
    assert (result.did_dollars > 0) == (result.did_estimate > 0)


def test_missing_column_raises(dataset_positive_effect):
    df = dataset_positive_effect.drop(columns=["revenue"])
    with pytest.raises(ValueError, match="Missing required columns"):
        run_simple_did(df)
