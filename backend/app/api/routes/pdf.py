"""
PDF export endpoint.

GET /api/tests/{test_id}/analysis/latest/pdf
    Returns the most recent completed analysis result as a formatted PDF report.
    Optionally includes the LLM narrative if one exists for the same job.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.db.session import get_db
from app.models.workspace import AnalysisJob, AnalysisResult, JobStatus, NarrativeResult, Test
from app.services.pdf.render import render_report

router = APIRouter(prefix="/api/tests/{test_id}/analysis", tags=["pdf"])


@router.get("/latest/pdf")
async def download_latest_pdf(
    test_id: uuid.UUID,
    auth: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """
    Download the most recent completed analysis as a PDF report.

    Returns 404 if no completed analysis exists for the test.
    """
    test = await _get_test_or_403(test_id, auth, db)

    # ── Fetch latest completed job ──────────────────────────────────────
    job_q = await db.execute(
        select(AnalysisJob)
        .where(
            AnalysisJob.test_id == test_id,
            AnalysisJob.status == JobStatus.COMPLETED,
        )
        .order_by(AnalysisJob.completed_at.desc())
        .limit(1)
    )
    job = job_q.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="No completed analysis found.")

    # ── Fetch result record ─────────────────────────────────────────────
    result_q = await db.execute(
        select(AnalysisResult).where(AnalysisResult.job_id == job.id)
    )
    result = result_q.scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Analysis result record missing.")

    # ── Optionally fetch narrative ──────────────────────────────────────
    narrative: str | None = None
    narr_q = await db.execute(
        select(NarrativeResult).where(NarrativeResult.job_id == job.id)
    )
    narr = narr_q.scalar_one_or_none()
    if narr:
        narrative = narr.body

    # ── Render PDF ───────────────────────���───────────────────────���──────
    pdf_bytes = render_report(
        test=test,
        result=result,
        job_id=str(job.id),
        narrative=narrative,
    )

    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in test.name)
    filename = f"{safe_name}_analysis.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _get_test_or_403(
    test_id: uuid.UUID, auth: CurrentUser, db: AsyncSession
) -> Test:
    result = await db.execute(select(Test).where(Test.id == test_id))
    test = result.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=404, detail="Test not found.")
    if not auth.is_super_admin and test.workspace_id != auth.workspace_id:
        raise HTTPException(status_code=403, detail="Access denied.")
    return test
