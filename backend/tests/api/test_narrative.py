"""
Tests for POST /api/tests/{test_id}/narrative

Covers:
- Auth / authz (401, 403)
- 404 when no test / no completed analysis
- 200 first generation (LLM called, result persisted)
- 200 cache hit (LLM NOT called, cached=True)
- force_refresh=True bypasses cache and re-calls LLM
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.models.workspace import AnalysisJob, AnalysisResult, JobStatus, NarrativeResult
from tests.api.conftest import WORKSPACE_A_ID, USER_A_ID

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_test(client, name: str = "Narrative Test") -> str:
    r = client.post("/api/tests/", json={"name": name})
    assert r.status_code == 201
    return r.json()["id"]


async def _seed_completed_job(db_session, test_id: str):
    """Insert a completed AnalysisJob + AnalysisResult. Returns job_id."""
    job = AnalysisJob(
        test_id=uuid.UUID(test_id),
        workspace_id=WORKSPACE_A_ID,
        triggered_by=USER_A_ID,
        status=JobStatus.COMPLETED,
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(job)
    await db_session.flush()

    result = AnalysisResult(
        job_id=job.id,
        test_id=uuid.UUID(test_id),
        workspace_id=WORKSPACE_A_ID,
        parallel_trends_passes=True,
        twfe_treatment_effect=0.12,
        twfe_treatment_effect_dollars=95_000.0,
        twfe_p_value=0.03,
        incremental_revenue_midpoint=91_500.0,
        roas_mid=1.83,
        total_spend=50_000.0,
    )
    db_session.add(result)
    await db_session.commit()
    return job.id


def _fake_narrative():
    """Build a fake NarrativeOutput-like object returned by generate_narrative."""
    n = MagicMock()
    n.headline = "Strong lift detected"
    n.body_markdown = "## Results\n\nSignificant incrementality observed."
    n.model = "openai/gpt-4o"
    n.prompt_tokens = 500
    n.completion_tokens = 200
    return n


# ---------------------------------------------------------------------------
# Fixture: mock generate_narrative so no LLM calls happen
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_generate():
    """Patches generate_narrative and returns the mock so tests can assert call counts."""
    mock = AsyncMock(return_value=_fake_narrative())
    with patch("app.api.routes.narrative.generate_narrative", mock):
        yield mock


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_narrative_unauthenticated_returns_401(client_unauthenticated):
    tid = uuid.uuid4()
    r = client_unauthenticated.post(f"/api/tests/{tid}/narrative", json={})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def test_narrative_cross_workspace_returns_403(client_a, client_b, mock_generate):
    tid = _create_test(client_b)
    r = client_a.post(f"/api/tests/{tid}/narrative", json={})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# 404 paths
# ---------------------------------------------------------------------------


def test_narrative_nonexistent_test_returns_404(client_a, mock_generate):
    r = client_a.post(f"/api/tests/{uuid.uuid4()}/narrative", json={})
    assert r.status_code == 404


def test_narrative_no_completed_analysis_returns_404(client_a, mock_generate):
    tid = _create_test(client_a)
    r = client_a.post(f"/api/tests/{tid}/narrative", json={})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Happy path — first generation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_narrative_first_call_generates_and_persists(client_a, db_session, mock_generate):
    tid = _create_test(client_a)
    job_id = await _seed_completed_job(db_session, tid)

    r = client_a.post(f"/api/tests/{tid}/narrative", json={})
    assert r.status_code == 200

    data = r.json()
    assert data["headline"] == "Strong lift detected"
    assert data["body_markdown"].startswith("## Results")
    assert data["cached"] is False
    assert data["model"] == "openai/gpt-4o"

    # LLM should have been called exactly once
    mock_generate.assert_awaited_once()

    # Row should now be persisted in DB
    from sqlalchemy import select
    narr_q = await db_session.execute(
        select(NarrativeResult).where(NarrativeResult.job_id == job_id)
    )
    narr = narr_q.scalar_one_or_none()
    assert narr is not None
    assert narr.headline == "Strong lift detected"
    assert narr.body == "## Results\n\nSignificant incrementality observed."


# ---------------------------------------------------------------------------
# Cache hit — second call should NOT call LLM
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_narrative_second_call_returns_cached(client_a, db_session, mock_generate):
    tid = _create_test(client_a, name="Cache Test")
    await _seed_completed_job(db_session, tid)

    # First call generates
    r1 = client_a.post(f"/api/tests/{tid}/narrative", json={})
    assert r1.status_code == 200
    assert r1.json()["cached"] is False

    # Reset call count
    mock_generate.reset_mock()

    # Second call should be cached
    r2 = client_a.post(f"/api/tests/{tid}/narrative", json={})
    assert r2.status_code == 200
    assert r2.json()["cached"] is True
    assert r2.json()["headline"] == "Strong lift detected"

    # LLM should NOT have been called again
    mock_generate.assert_not_awaited()


# ---------------------------------------------------------------------------
# force_refresh bypasses cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_narrative_force_refresh_regenerates(client_a, db_session, mock_generate):
    tid = _create_test(client_a, name="Refresh Test")
    await _seed_completed_job(db_session, tid)

    # First call populates cache
    r1 = client_a.post(f"/api/tests/{tid}/narrative", json={})
    assert r1.status_code == 200

    mock_generate.reset_mock()

    # force_refresh=True should call LLM again
    r2 = client_a.post(f"/api/tests/{tid}/narrative", json={"force_refresh": True})
    assert r2.status_code == 200
    assert r2.json()["cached"] is False
    mock_generate.assert_awaited_once()
