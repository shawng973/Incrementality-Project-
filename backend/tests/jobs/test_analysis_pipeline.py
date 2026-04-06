"""
Tests for analysis_pipeline.py — the ARQ job orchestrator.

Split into two sections:

1. Pure pipeline tests — call _run_pipeline_steps() directly.
   No DB, no ARQ. Fast, deterministic.

2. Worker integration tests — call run_analysis() with a mock DB context.
   Verifies that job status transitions and AnalysisResult rows are saved.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from app.jobs.analysis_pipeline import (
    _run_pipeline_steps,
    _validate_panel_columns,
    run_analysis,
)
from tests.statistical.conftest import TOTAL_TEST_PERIOD_SPEND, TRUE_LIFT


def _j(df: pd.DataFrame) -> str:
    return df.to_json(orient="records")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_ctx():
    """Build a fake ARQ ctx with an in-memory mock DB session factory."""
    from app.models.workspace import AnalysisJob, JobStatus

    job_id = uuid.uuid4()

    # Fake AnalysisJob that tracks status transitions
    mock_job = MagicMock(spec=AnalysisJob)
    mock_job.id = job_id
    mock_job.status = JobStatus.PENDING
    mock_job.started_at = None
    mock_job.completed_at = None
    mock_job.error_message = None
    mock_job.error_detail = None

    # Fake DB session
    mock_db = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=False)

    # scalar_one() on execute() returns the mock job
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one.return_value = mock_job
    mock_db.execute = AsyncMock(return_value=mock_execute_result)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    # Session factory returns the mock session as a context manager
    mock_factory = MagicMock()
    mock_factory.return_value = mock_db

    ctx = {"db_session_factory": mock_factory}
    return ctx, mock_job, mock_db, str(job_id)


# ---------------------------------------------------------------------------
# 1. Column validation (pure)
# ---------------------------------------------------------------------------


def test_validate_passes_with_all_required(dataset_positive_effect):
    _validate_panel_columns(dataset_positive_effect, has_prior_year=False)


def test_validate_raises_on_missing_column():
    df = pd.DataFrame({"geo": ["A"], "week": [0], "period": [0]})
    with pytest.raises(ValueError, match="missing required columns"):
        _validate_panel_columns(df, has_prior_year=False)


def test_validate_raises_when_prior_year_expected_but_absent(dataset_positive_effect):
    with pytest.raises(ValueError, match="revenue_prior"):
        _validate_panel_columns(dataset_positive_effect, has_prior_year=True)


# ---------------------------------------------------------------------------
# 2. Pure pipeline computation (_run_pipeline_steps)
# ---------------------------------------------------------------------------


def test_pipeline_completes_without_error(dataset_positive_effect):
    result = _run_pipeline_steps(_j(dataset_positive_effect), TOTAL_TEST_PERIOD_SPEND,
                                  n_bootstrap_resamples=200)
    assert "twfe_treatment_effect" in result


def test_pipeline_twfe_close_to_true_lift(dataset_positive_effect):
    result = _run_pipeline_steps(_j(dataset_positive_effect), TOTAL_TEST_PERIOD_SPEND,
                                  n_bootstrap_resamples=200)
    assert abs(result["twfe_treatment_effect"] - TRUE_LIFT) < 0.02


def test_pipeline_twfe_significant(dataset_positive_effect):
    result = _run_pipeline_steps(_j(dataset_positive_effect), TOTAL_TEST_PERIOD_SPEND,
                                  n_bootstrap_resamples=200)
    assert result["twfe_p_value"] < 0.05


def test_pipeline_parallel_trends_pass(dataset_clean_pretrend):
    result = _run_pipeline_steps(_j(dataset_clean_pretrend), TOTAL_TEST_PERIOD_SPEND,
                                  n_bootstrap_resamples=200)
    assert result["parallel_trends_passes"] is True
    assert result["parallel_trends_flag"] is None


def test_pipeline_parallel_trends_fail(dataset_pretrend_violation):
    result = _run_pipeline_steps(_j(dataset_pretrend_violation), TOTAL_TEST_PERIOD_SPEND,
                                  n_bootstrap_resamples=200)
    assert result["parallel_trends_passes"] is False
    assert result["parallel_trends_flag"] is not None


def test_pipeline_roas_ordering(dataset_positive_effect):
    result = _run_pipeline_steps(_j(dataset_positive_effect), TOTAL_TEST_PERIOD_SPEND,
                                  n_bootstrap_resamples=200)
    assert result["roas_mid"] > 0
    assert result["roas_low"] > 0 and result["roas_high"] > 0


def test_pipeline_roas_absent_when_spend_zero(dataset_positive_effect):
    result = _run_pipeline_steps(_j(dataset_positive_effect), spend=0.0,
                                  n_bootstrap_resamples=200)
    assert "roas_mid" not in result


def test_pipeline_ci_keys_present(dataset_positive_effect):
    result = _run_pipeline_steps(_j(dataset_positive_effect), TOTAL_TEST_PERIOD_SPEND,
                                  n_bootstrap_resamples=200)
    for key in ["twfe_ci_80", "twfe_ci_90", "twfe_ci_95"]:
        assert "lower" in result[key] and "upper" in result[key]


def test_pipeline_power_analysis_present(dataset_positive_effect):
    result = _run_pipeline_steps(_j(dataset_positive_effect), TOTAL_TEST_PERIOD_SPEND,
                                  n_bootstrap_resamples=200)
    pa = result["power_analysis_json"]
    assert 0.0 <= pa["power"] <= 1.0
    assert "is_adequately_powered" in pa


def test_pipeline_prior_year(dataset_yoy):
    result = _run_pipeline_steps(_j(dataset_yoy), TOTAL_TEST_PERIOD_SPEND,
                                  has_prior_year=True, n_bootstrap_resamples=200)
    assert "yoy_did_proportion" in result
    assert "is_causally_clean" in result


def test_pipeline_raises_bad_columns():
    df = pd.DataFrame({"geo": ["A"] * 20, "week": range(20)})
    with pytest.raises(ValueError, match="missing required columns"):
        _run_pipeline_steps(df.to_json(orient="records"), spend=10_000.0)


def test_pipeline_null_effect_non_significant(dataset_null_effect):
    result = _run_pipeline_steps(_j(dataset_null_effect), TOTAL_TEST_PERIOD_SPEND,
                                  n_bootstrap_resamples=200)
    assert result["twfe_p_value"] > 0.05


# ---------------------------------------------------------------------------
# 3. Worker wrapper (run_analysis) — DB persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_analysis_marks_job_running_then_completed(dataset_positive_effect):
    ctx, mock_job, mock_db, job_id = _make_mock_ctx()
    test_id = str(uuid.uuid4())
    workspace_id = str(uuid.uuid4())

    with patch("app.jobs.analysis_pipeline._run_pipeline_steps",
               return_value={"twfe_treatment_effect": 0.1, "twfe_p_value": 0.02}):
        await run_analysis(
            ctx, job_id, test_id, workspace_id,
            _j(dataset_positive_effect), spend=50_000.0, n_bootstrap_resamples=100,
        )

    from app.models.workspace import JobStatus
    assert mock_job.status == JobStatus.COMPLETED
    assert mock_job.started_at is not None
    assert mock_job.completed_at is not None
    # AnalysisResult was added to the session
    mock_db.add.assert_called_once()


@pytest.mark.asyncio
async def test_run_analysis_marks_job_failed_on_error(dataset_positive_effect):
    ctx, mock_job, mock_db, job_id = _make_mock_ctx()
    test_id = str(uuid.uuid4())
    workspace_id = str(uuid.uuid4())

    with patch("app.jobs.analysis_pipeline._run_pipeline_steps",
               side_effect=RuntimeError("pipeline blew up")):
        with pytest.raises(RuntimeError, match="pipeline blew up"):
            await run_analysis(
                ctx, job_id, test_id, workspace_id,
                _j(dataset_positive_effect), spend=50_000.0,
            )

    from app.models.workspace import JobStatus
    assert mock_job.status == JobStatus.FAILED
    assert mock_job.error_message == "pipeline blew up"
    assert mock_job.completed_at is not None
    # No AnalysisResult row added on failure
    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_run_analysis_persists_roas_fields(dataset_positive_effect):
    ctx, mock_job, mock_db, job_id = _make_mock_ctx()

    pipeline_output = {
        "twfe_treatment_effect": 0.12,
        "twfe_p_value": 0.019,
        "roas_mid": 2.1,
        "roas_low": 1.5,
        "roas_high": 2.8,
        "total_spend": 50_000.0,
        "incremental_revenue_midpoint": 105_000.0,
    }

    with patch("app.jobs.analysis_pipeline._run_pipeline_steps",
               return_value=pipeline_output):
        await run_analysis(
            ctx, job_id, str(uuid.uuid4()), str(uuid.uuid4()),
            _j(dataset_positive_effect), spend=50_000.0,
        )

    # Verify the AnalysisResult passed to db.add has the right roas_mid
    added_result = mock_db.add.call_args[0][0]
    assert added_result.roas_mid == 2.1
    assert added_result.total_spend == 50_000.0
    assert added_result.incremental_revenue_midpoint == 105_000.0


@pytest.mark.asyncio
async def test_run_analysis_sets_test_status_completed(dataset_positive_effect):
    """Worker sets test.status = COMPLETED after a successful run."""
    from app.models.workspace import JobStatus, Test, TestStatus

    ctx, mock_job, mock_db, job_id = _make_mock_ctx()

    # Give the mock execute a fake Test row as well
    mock_test_row = MagicMock(spec=Test)
    mock_test_row.status = TestStatus.ACTIVE

    execute_results = iter([
        # First execute: fetch AnalysisJob
        MagicMock(**{"scalar_one.return_value": mock_job}),
        # Second execute: fetch Test
        MagicMock(**{"scalar_one_or_none.return_value": mock_test_row}),
    ])
    mock_db.execute = AsyncMock(side_effect=lambda *a, **kw: next(execute_results))

    with patch("app.jobs.analysis_pipeline._run_pipeline_steps", return_value={}):
        await run_analysis(
            ctx, job_id, str(uuid.uuid4()), str(uuid.uuid4()),
            _j(dataset_positive_effect), spend=50_000.0, n_bootstrap_resamples=100,
        )

    assert mock_test_row.status == TestStatus.COMPLETED
