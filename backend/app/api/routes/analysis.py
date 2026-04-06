"""
/api/tests/{test_id}/analysis — trigger and poll analysis jobs.

POST /api/tests/{test_id}/analysis/run
    Enqueues an ARQ job and returns the job_id immediately.
    Client polls via GET or listens on Supabase Realtime.

GET /api/tests/{test_id}/analysis/latest
    Returns the most recent analysis result for the test.

GET /api/tests/{test_id}/analysis/jobs/{job_id}
    Returns status of a specific job.
"""
from __future__ import annotations

import io
import uuid
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.arq_pool import get_arq_pool
from app.core.auth import CurrentUser
from app.db.session import get_db
from app.models.workspace import AnalysisJob, AnalysisResult, CsvUpload, JobStatus, Test, TestStatus
from app.schemas.analysis_schemas import (
    AnalysisJobResponse,
    AnalysisResultResponse,
    AnalysisTriggerRequest,
)

router = APIRouter(prefix="/api/tests/{test_id}/analysis", tags=["analysis"])


@router.post("/run", response_model=AnalysisJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_analysis(
    test_id: uuid.UUID,
    body: AnalysisTriggerRequest,
    auth: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AnalysisJobResponse:
    """
    Enqueue an analysis job for the given test.
    Returns immediately with job_id; analysis runs asynchronously.
    """
    test = await _get_test_or_403(test_id, auth, db)

    # ── Load historical upload (required) ──────────────────────────────────
    hist_q = await db.execute(
        select(CsvUpload)
        .where(CsvUpload.test_id == test_id, CsvUpload.upload_type == "historical")
        .order_by(CsvUpload.uploaded_at.desc())
        .limit(1)
    )
    hist_upload = hist_q.scalar_one_or_none()
    if hist_upload is None or not hist_upload.data_json:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No historical data uploaded for this test. Upload baseline data before running analysis.",
        )

    # ── Load results upload (optional) ─────────────────────────────────────
    res_q = await db.execute(
        select(CsvUpload)
        .where(CsvUpload.test_id == test_id, CsvUpload.upload_type == "results")
        .order_by(CsvUpload.uploaded_at.desc())
        .limit(1)
    )
    res_upload = res_q.scalar_one_or_none()

    # ── Build panel DataFrame ───────────────────────────────────────────────
    panel = _build_panel(hist_upload.data_json, res_upload.data_json if res_upload else None)

    # ── Create job record + advance test status ─────────────────────────────
    job = AnalysisJob(
        test_id=test_id,
        workspace_id=test.workspace_id,
        triggered_by=auth.user_id,
        status=JobStatus.PENDING,
    )
    db.add(job)
    test.status = TestStatus.ACTIVE
    await db.commit()
    await db.refresh(job)

    # ── Enqueue via ARQ ─────────────────────────────────────────────────────
    arq_pool = await get_arq_pool()
    await arq_pool.enqueue_job(
        "run_analysis",
        job_id=str(job.id),
        test_id=str(test_id),
        workspace_id=str(test.workspace_id),
        df_json=panel.to_json(orient="records"),
        spend=body.spend,
        has_prior_year=body.has_prior_year,
        n_cells=test.n_cells,
        n_bootstrap_resamples=body.n_bootstrap_resamples,
    )

    return AnalysisJobResponse(
        job_id=job.id,
        test_id=test_id,
        status=job.status.value,
        message="Analysis job queued. Results will be available shortly.",
    )


@router.get("/jobs/{job_id}", response_model=AnalysisJobResponse)
async def get_job_status(
    test_id: uuid.UUID,
    job_id: uuid.UUID,
    auth: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AnalysisJobResponse:
    """Poll status of a specific analysis job."""
    await _get_test_or_403(test_id, auth, db)

    result = await db.execute(
        select(AnalysisJob).where(
            AnalysisJob.id == job_id,
            AnalysisJob.test_id == test_id,
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    return AnalysisJobResponse(
        job_id=job.id,
        test_id=test_id,
        status=job.status.value,
        message=job.error_message or "",
    )


@router.get("/latest", response_model=AnalysisResultResponse)
async def get_latest_result(
    test_id: uuid.UUID,
    auth: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AnalysisResultResponse:
    """Return the most recent completed analysis result."""
    await _get_test_or_403(test_id, auth, db)

    # Get the most recent completed job
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
        raise HTTPException(
            status_code=404,
            detail="No completed analysis found for this test.",
        )

    result_q = await db.execute(
        select(AnalysisResult).where(AnalysisResult.job_id == job.id)
    )
    result = result_q.scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Analysis result record missing.")

    return AnalysisResultResponse(
        job_id=job.id,
        test_id=test_id,
        status=job.status.value,
        parallel_trends_passes=result.parallel_trends_passes,
        parallel_trends_p_value=result.parallel_trends_p_value,
        parallel_trends_flag=result.parallel_trends_flag,
        twfe_treatment_effect=result.twfe_treatment_effect,
        twfe_treatment_effect_dollars=result.twfe_treatment_effect_dollars,
        twfe_p_value=result.twfe_p_value,
        twfe_ci_80=result.twfe_ci_80,
        twfe_ci_90=result.twfe_ci_90,
        twfe_ci_95=result.twfe_ci_95,
        simple_did_estimate=result.simple_did_estimate,
        simple_did_dollars=result.simple_did_dollars,
        yoy_did_proportion=result.yoy_did_proportion,
        yoy_did_dollars=result.yoy_did_dollars,
        is_causally_clean=result.is_causally_clean,
        adjusted_yoy_did_dollars=result.adjusted_yoy_did_dollars,
        incremental_revenue_midpoint=result.incremental_revenue_midpoint,
        incremental_revenue_weighted=result.incremental_revenue_weighted,
        roas_low=result.roas_low,
        roas_mid=result.roas_mid,
        roas_high=result.roas_high,
        roas_ci_95=result.roas_ci_95,
        total_spend=result.total_spend,
        power_analysis_json=result.power_analysis_json,
    )


def _build_panel(hist_json: str, res_json: str | None) -> pd.DataFrame:
    """
    Combine historical and results upload DataFrames into the panel format
    expected by the analysis pipeline.

    Canonical column names from the upload (region, period, metric, spend,
    prior_metric) are renamed to pipeline names (geo, week, revenue, spend,
    revenue_prior).  A new `period` column is added: 0 = pre-test baseline,
    1 = post-test results.
    """
    _RENAME = {
        "region": "geo",
        "period": "week",
        "metric": "revenue",
        "prior_metric": "revenue_prior",
    }

    def _load(json_str: str, period_flag: int) -> pd.DataFrame:
        df = pd.read_json(io.StringIO(json_str), orient="records")
        df = df.rename(columns=_RENAME)
        df["period"] = period_flag
        return df

    hist_df = _load(hist_json, 0)

    if res_json:
        res_df = _load(res_json, 1)
        return pd.concat([hist_df, res_df], ignore_index=True)

    return hist_df


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
