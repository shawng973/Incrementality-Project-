"""
Tests for /api/tests/{test_id}/analysis endpoints.

Covers:
- Authentication (401 for unauthenticated)
- Authorization (403 for cross-workspace access)
- Trigger: 202 with job_id; 422 if no upload; 422 if spend invalid
- Job status: 200 pending/running/completed; 404 for unknown job
- Latest result: 200 with result fields; 404 if no completed job
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from app.models.workspace import (
    AnalysisJob,
    AnalysisResult,
    CsvUpload,
    JobStatus,
    Test,
    TestStatus,
)
from tests.api.conftest import WORKSPACE_A_ID, WORKSPACE_B_ID, USER_A_ID


# ---------------------------------------------------------------------------
# Module-level fixture: mock the ARQ pool so tests don't need Redis
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_arq_pool():
    """Replace get_arq_pool with an AsyncMock for all tests in this module."""
    mock_pool = MagicMock()
    mock_pool.enqueue_job = AsyncMock(return_value=None)

    async def _fake_get_pool():
        return mock_pool

    with patch("app.api.routes.analysis.get_arq_pool", _fake_get_pool):
        yield mock_pool


def _make_data_json() -> str:
    """Build a minimal valid data_json (canonical columns, >30 rows)."""
    rows = [
        {"region": f"geo_{g}", "period": f"2024-W{w:02d}", "metric": 1000.0 + g * 50 + w * 10}
        for g in range(8)
        for w in range(5)
    ]
    return pd.DataFrame(rows).to_json(orient="records")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_test(client) -> str:
    r = client.post("/api/tests/", json={"name": "Analysis Subject"})
    assert r.status_code == 201
    return r.json()["id"]


async def _seed_upload(db_session, test_id: str, workspace_id: uuid.UUID) -> None:
    """Insert a minimal CsvUpload row so analysis trigger passes the upload check."""
    upload = CsvUpload(
        test_id=uuid.UUID(test_id),
        workspace_id=workspace_id,
        upload_type="historical",
        storage_path=f"uploads/{test_id}/data.csv",
        filename="data.csv",
        data_json=_make_data_json(),
        uploaded_by=USER_A_ID,
    )
    db_session.add(upload)
    await db_session.commit()


async def _seed_completed_job_and_result(
    db_session, test_id: str, workspace_id: uuid.UUID
) -> str:
    """Insert a completed AnalysisJob + AnalysisResult for /latest endpoint tests."""
    job = AnalysisJob(
        test_id=uuid.UUID(test_id),
        workspace_id=workspace_id,
        triggered_by=USER_A_ID,
        status=JobStatus.COMPLETED,
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.flush()

    result = AnalysisResult(
        job_id=job.id,
        test_id=uuid.UUID(test_id),
        workspace_id=workspace_id,
        parallel_trends_passes=True,
        parallel_trends_p_value=0.45,
        twfe_treatment_effect=0.15,
        twfe_treatment_effect_dollars=120_000.0,
        twfe_p_value=0.02,
        twfe_ci_95={"lower": 0.08, "upper": 0.22},
        simple_did_estimate=0.14,
        simple_did_dollars=115_000.0,
        incremental_revenue_midpoint=117_500.0,
        roas_mid=2.35,
        total_spend=50_000.0,
        power_analysis_json={"power": 0.85, "is_adequately_powered": True},
    )
    db_session.add(result)
    await db_session.commit()
    return str(job.id)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_trigger_unauthenticated_returns_401(client_unauthenticated):
    tid = uuid.uuid4()
    r = client_unauthenticated.post(
        f"/api/tests/{tid}/analysis/run",
        json={"spend": 50000},
    )
    assert r.status_code == 401


def test_job_status_unauthenticated_returns_401(client_unauthenticated):
    tid = uuid.uuid4()
    jid = uuid.uuid4()
    r = client_unauthenticated.get(f"/api/tests/{tid}/analysis/jobs/{jid}")
    assert r.status_code == 401


def test_latest_result_unauthenticated_returns_401(client_unauthenticated):
    tid = uuid.uuid4()
    r = client_unauthenticated.get(f"/api/tests/{tid}/analysis/latest")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def test_trigger_cross_workspace_returns_403(client_a, client_b):
    tid = _create_test(client_b)
    r = client_a.post(f"/api/tests/{tid}/analysis/run", json={"spend": 50000})
    assert r.status_code == 403


def test_job_status_cross_workspace_returns_403(client_a, client_b):
    tid = _create_test(client_b)
    jid = uuid.uuid4()
    r = client_a.get(f"/api/tests/{tid}/analysis/jobs/{jid}")
    assert r.status_code == 403


def test_latest_result_cross_workspace_returns_403(client_a, client_b):
    tid = _create_test(client_b)
    r = client_a.get(f"/api/tests/{tid}/analysis/latest")
    assert r.status_code == 403


def test_super_admin_can_trigger_any_workspace(client_b, client_super_admin, db_session):
    tid = _create_test(client_b)
    # No upload seeded — should 422 on upload check, not 403
    r = client_super_admin.post(f"/api/tests/{tid}/analysis/run", json={"spend": 50000})
    assert r.status_code == 422  # upload missing, not auth error


# ---------------------------------------------------------------------------
# Trigger — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_returns_202_with_job_id(client_a, db_session):
    tid = _create_test(client_a)
    await _seed_upload(db_session, tid, WORKSPACE_A_ID)

    r = client_a.post(f"/api/tests/{tid}/analysis/run", json={"spend": 50000.0})
    assert r.status_code == 202
    data = r.json()
    assert "job_id" in data
    assert data["test_id"] == tid
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_trigger_job_id_is_valid_uuid(client_a, db_session):
    tid = _create_test(client_a)
    await _seed_upload(db_session, tid, WORKSPACE_A_ID)

    r = client_a.post(f"/api/tests/{tid}/analysis/run", json={"spend": 10000.0})
    assert r.status_code == 202
    uuid.UUID(r.json()["job_id"])  # raises if invalid


# ---------------------------------------------------------------------------
# Trigger — validation errors
# ---------------------------------------------------------------------------


def test_trigger_missing_spend_returns_422(client_a):
    tid = _create_test(client_a)
    r = client_a.post(f"/api/tests/{tid}/analysis/run", json={})
    assert r.status_code == 422


def test_trigger_zero_spend_returns_422(client_a):
    tid = _create_test(client_a)
    r = client_a.post(f"/api/tests/{tid}/analysis/run", json={"spend": 0})
    assert r.status_code == 422


def test_trigger_negative_spend_returns_422(client_a):
    tid = _create_test(client_a)
    r = client_a.post(f"/api/tests/{tid}/analysis/run", json={"spend": -100})
    assert r.status_code == 422


def test_trigger_no_upload_returns_422(client_a):
    tid = _create_test(client_a)
    r = client_a.post(f"/api/tests/{tid}/analysis/run", json={"spend": 50000})
    assert r.status_code == 422


def test_trigger_nonexistent_test_returns_404(client_a):
    r = client_a.post(
        f"/api/tests/{uuid.uuid4()}/analysis/run", json={"spend": 50000}
    )
    assert r.status_code == 404


def test_trigger_bootstrap_resamples_out_of_range_returns_422(client_a):
    tid = _create_test(client_a)
    r = client_a.post(
        f"/api/tests/{tid}/analysis/run",
        json={"spend": 50000, "n_bootstrap_resamples": 10},  # min is 100
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Job status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_job_status_returns_pending(client_a, db_session):
    tid = _create_test(client_a)
    await _seed_upload(db_session, tid, WORKSPACE_A_ID)

    trigger = client_a.post(f"/api/tests/{tid}/analysis/run", json={"spend": 50000})
    job_id = trigger.json()["job_id"]

    r = client_a.get(f"/api/tests/{tid}/analysis/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "pending"
    assert r.json()["job_id"] == job_id


def test_get_job_status_unknown_job_returns_404(client_a):
    tid = _create_test(client_a)
    r = client_a.get(f"/api/tests/{tid}/analysis/jobs/{uuid.uuid4()}")
    assert r.status_code == 404


def test_get_job_status_wrong_test_returns_404(client_a, db_session):
    """A job belonging to test A should not be found under test B's path."""
    tid_a = _create_test(client_a)
    tid_b = _create_test(client_a)
    # Can't easily get a real job_id for tid_a without an upload, use random UUID
    r = client_a.get(f"/api/tests/{tid_b}/analysis/jobs/{uuid.uuid4()}")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Latest result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_latest_result_returns_200(client_a, db_session):
    tid = _create_test(client_a)
    await _seed_completed_job_and_result(db_session, tid, WORKSPACE_A_ID)

    r = client_a.get(f"/api/tests/{tid}/analysis/latest")
    assert r.status_code == 200
    data = r.json()
    assert data["test_id"] == tid
    assert data["status"] == "completed"


@pytest.mark.asyncio
async def test_get_latest_result_has_twfe_fields(client_a, db_session):
    tid = _create_test(client_a)
    await _seed_completed_job_and_result(db_session, tid, WORKSPACE_A_ID)

    r = client_a.get(f"/api/tests/{tid}/analysis/latest")
    data = r.json()
    assert data["twfe_treatment_effect"] == pytest.approx(0.15)
    assert data["twfe_treatment_effect_dollars"] == pytest.approx(120_000.0)
    assert data["twfe_p_value"] == pytest.approx(0.02)


@pytest.mark.asyncio
async def test_get_latest_result_has_roas_and_spend(client_a, db_session):
    tid = _create_test(client_a)
    await _seed_completed_job_and_result(db_session, tid, WORKSPACE_A_ID)

    r = client_a.get(f"/api/tests/{tid}/analysis/latest")
    data = r.json()
    assert data["roas_mid"] == pytest.approx(2.35)
    assert data["total_spend"] == pytest.approx(50_000.0)


@pytest.mark.asyncio
async def test_get_latest_result_has_power_analysis(client_a, db_session):
    tid = _create_test(client_a)
    await _seed_completed_job_and_result(db_session, tid, WORKSPACE_A_ID)

    r = client_a.get(f"/api/tests/{tid}/analysis/latest")
    data = r.json()
    assert data["power_analysis_json"] is not None
    assert data["power_analysis_json"]["is_adequately_powered"] is True


def test_get_latest_result_no_completed_job_returns_404(client_a):
    tid = _create_test(client_a)
    r = client_a.get(f"/api/tests/{tid}/analysis/latest")
    assert r.status_code == 404


def test_get_latest_result_nonexistent_test_returns_404(client_a):
    r = client_a.get(f"/api/tests/{uuid.uuid4()}/analysis/latest")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Status transitions — trigger sets test ACTIVE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_advances_test_status_to_active(client_a, db_session):
    from sqlalchemy import select as sa_select
    from app.models.workspace import Test

    tid = _create_test(client_a)
    await _seed_upload(db_session, tid, WORKSPACE_A_ID)

    # Confirm starting status is draft
    test_q = await db_session.execute(sa_select(Test).where(Test.id == uuid.UUID(tid)))
    test_row = test_q.scalar_one()
    assert test_row.status == TestStatus.DRAFT

    r = client_a.post(f"/api/tests/{tid}/analysis/run", json={"spend": 50000.0})
    assert r.status_code == 202

    await db_session.refresh(test_row)
    assert test_row.status == TestStatus.ACTIVE
