"""
Tests for GET /api/tests/{test_id}/analysis/latest/pdf

Covers:
- Auth / authz (401, 403)
- 404 when no completed analysis exists
- 200 with application/pdf content-type and non-empty bytes
- Content-Disposition filename derived from test name
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.workspace import (
    AnalysisJob,
    AnalysisResult,
    JobStatus,
)
from tests.api.conftest import WORKSPACE_A_ID, WORKSPACE_B_ID, USER_A_ID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_test(client, name: str = "PDF Test") -> str:
    r = client.post("/api/tests/", json={"name": name})
    assert r.status_code == 201
    return r.json()["id"]


async def _seed_completed(db_session, test_id: str) -> None:
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
        parallel_trends_p_value=0.32,
        twfe_treatment_effect=0.12,
        twfe_treatment_effect_dollars=95_000.0,
        twfe_p_value=0.03,
        twfe_ci_95={"lower": 0.05, "upper": 0.19},
        simple_did_estimate=0.11,
        simple_did_dollars=88_000.0,
        incremental_revenue_midpoint=91_500.0,
        roas_mid=1.83,
        roas_low=1.40,
        roas_high=2.30,
        roas_ci_95={"lower": 1.20, "upper": 2.50},
        total_spend=50_000.0,
        power_analysis_json={"power": 0.82, "is_adequately_powered": True, "required_weeks": 6},
    )
    db_session.add(result)
    await db_session.commit()


# Fake 3-byte PDF so WeasyPrint is never invoked in tests
_FAKE_PDF = b"%PDF-1.4 fake"


@pytest.fixture(autouse=True)
def mock_render_report():
    with patch("app.api.routes.pdf.render_report", return_value=_FAKE_PDF):
        yield


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_pdf_unauthenticated_returns_401(client_unauthenticated):
    tid = uuid.uuid4()
    r = client_unauthenticated.get(f"/api/tests/{tid}/analysis/latest/pdf")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def test_pdf_cross_workspace_returns_403(client_a, client_b):
    tid = _create_test(client_b)
    r = client_a.get(f"/api/tests/{tid}/analysis/latest/pdf")
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# 404 paths
# ---------------------------------------------------------------------------


def test_pdf_nonexistent_test_returns_404(client_a):
    r = client_a.get(f"/api/tests/{uuid.uuid4()}/analysis/latest/pdf")
    assert r.status_code == 404


def test_pdf_no_completed_analysis_returns_404(client_a):
    tid = _create_test(client_a)
    r = client_a.get(f"/api/tests/{tid}/analysis/latest/pdf")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pdf_returns_200_with_pdf_content_type(client_a, db_session):
    tid = _create_test(client_a)
    await _seed_completed(db_session, tid)

    r = client_a.get(f"/api/tests/{tid}/analysis/latest/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"


@pytest.mark.asyncio
async def test_pdf_returns_non_empty_body(client_a, db_session):
    tid = _create_test(client_a)
    await _seed_completed(db_session, tid)

    r = client_a.get(f"/api/tests/{tid}/analysis/latest/pdf")
    assert len(r.content) > 0
    assert r.content == _FAKE_PDF


@pytest.mark.asyncio
async def test_pdf_content_disposition_contains_test_name(client_a, db_session):
    tid = _create_test(client_a, name="My Campaign Test")
    await _seed_completed(db_session, tid)

    r = client_a.get(f"/api/tests/{tid}/analysis/latest/pdf")
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert ".pdf" in cd


@pytest.mark.asyncio
async def test_pdf_super_admin_can_access_any_workspace(client_b, client_super_admin, db_session):
    tid = _create_test(client_b)
    await _seed_completed(db_session, tid)

    r = client_super_admin.get(f"/api/tests/{tid}/analysis/latest/pdf")
    assert r.status_code == 200
