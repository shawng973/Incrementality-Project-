"""
POST /api/tests/{test_id}/narrative

Generates an LLM-authored Markdown narrative for the most recent (or a
specified) completed analysis result.

Results are persisted in the `narrative_results` table on first generation
and returned from cache on subsequent requests. Pass `force_refresh=true`
in the request body to re-generate even if a cached narrative exists.

The underlying LLM model is hot-swappable: set LLM_MODEL in the environment
to any OpenRouter-supported model slug (e.g. "openai/gpt-4o",
"google/gemini-2.0-flash") without redeploying.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.db.session import get_db
from app.models.workspace import (
    AnalysisJob,
    AnalysisResult,
    JobStatus,
    NarrativeResult,
    Test,
)
from app.schemas.narrative_schemas import NarrativeRequest, NarrativeResponse
from app.services.llm.client import OpenRouterClient, client_from_settings
from app.services.llm.narrative import generate_narrative

router = APIRouter(prefix="/api/tests/{test_id}/narrative", tags=["narrative"])


def get_llm_client() -> OpenRouterClient:
    """FastAPI dependency — returns a client built from current settings."""
    return client_from_settings()


@router.post(
    "",
    response_model=NarrativeResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate (or retrieve cached) LLM narrative for a test's analysis results",
)
async def generate_test_narrative(
    test_id: uuid.UUID,
    body: NarrativeRequest,
    auth: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    llm: Annotated[OpenRouterClient, Depends(get_llm_client)],
) -> NarrativeResponse:
    """
    Returns a plain-English narrative interpreting the analysis results.

    On first call the narrative is generated via LLM and persisted. Subsequent
    calls return the cached version unless `force_refresh=true` is set.
    """
    # Verify test exists and belongs to this workspace
    test_q = await db.execute(select(Test).where(Test.id == test_id))
    test = test_q.scalar_one_or_none()
    if test is None:
        raise HTTPException(status_code=404, detail="Test not found.")
    if not auth.is_super_admin and test.workspace_id != auth.workspace_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    # Resolve the job to narrate
    if body.job_id is not None:
        job_q = await db.execute(
            select(AnalysisJob).where(
                AnalysisJob.id == body.job_id,
                AnalysisJob.test_id == test_id,
                AnalysisJob.status == JobStatus.COMPLETED,
            )
        )
        job = job_q.scalar_one_or_none()
        if job is None:
            raise HTTPException(
                status_code=404,
                detail="Specified job not found or not yet completed.",
            )
    else:
        # Latest completed job
        latest_q = await db.execute(
            select(AnalysisJob)
            .where(
                AnalysisJob.test_id == test_id,
                AnalysisJob.status == JobStatus.COMPLETED,
            )
            .order_by(AnalysisJob.completed_at.desc())
            .limit(1)
        )
        job = latest_q.scalar_one_or_none()
        if job is None:
            raise HTTPException(
                status_code=404,
                detail="No completed analysis found. Run an analysis first.",
            )

    # ── Return cached narrative unless force_refresh requested ────────────
    if not body.force_refresh:
        cached_q = await db.execute(
            select(NarrativeResult).where(NarrativeResult.job_id == job.id)
        )
        cached = cached_q.scalar_one_or_none()
        if cached is not None:
            return NarrativeResponse(
                test_id=test_id,
                job_id=job.id,
                headline=cached.headline,
                body_markdown=cached.body,
                model=cached.model,
                prompt_tokens=cached.prompt_tokens,
                completion_tokens=cached.completion_tokens,
                cached=True,
            )

    # ── Load the result record ─────────────────────────────────────────────
    result_q = await db.execute(
        select(AnalysisResult).where(AnalysisResult.job_id == job.id)
    )
    result_row = result_q.scalar_one_or_none()
    if result_row is None:
        raise HTTPException(status_code=404, detail="Analysis result record missing.")

    result_dict = {
        col.name: getattr(result_row, col.name)
        for col in result_row.__table__.columns
    }

    # ── Call LLM ───────────────────────────────────────────────────────────
    narrative = await generate_narrative(result_dict, llm)

    # ── Persist (upsert: delete old, insert new) ───────────────────────────
    existing_q = await db.execute(
        select(NarrativeResult).where(NarrativeResult.job_id == job.id)
    )
    existing = existing_q.scalar_one_or_none()
    if existing is not None:
        await db.delete(existing)
        await db.flush()

    narr_row = NarrativeResult(
        job_id=job.id,
        test_id=test_id,
        workspace_id=test.workspace_id,
        headline=narrative.headline,
        body=narrative.body_markdown,
        model=narrative.model,
        prompt_tokens=narrative.prompt_tokens,
        completion_tokens=narrative.completion_tokens,
    )
    db.add(narr_row)
    await db.commit()

    return NarrativeResponse(
        test_id=test_id,
        job_id=job.id,
        headline=narrative.headline,
        body_markdown=narrative.body_markdown,
        model=narrative.model,
        prompt_tokens=narrative.prompt_tokens,
        completion_tokens=narrative.completion_tokens,
        cached=False,
    )
