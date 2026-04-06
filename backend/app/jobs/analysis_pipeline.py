"""
Analysis Pipeline Orchestrator.

Runs the full statistical analysis for a geo-split test as a single ARQ job.
Called by the ARQ worker when a job is dequeued.

Pipeline order:
  1. Load data from storage (df_json passed by caller)
  2. Validate + normalize inputs
  3. Parallel trends test (pre-check)
  4. Feature engineering
  5. K-Means clustering
  6. Cell assignment validation + is_treatment derivation
  7. Power analysis
  8. TWFE DiD (primary causal estimate)
  9. Simple DiD (secondary)
  10. YoY analysis (if prior-year data present)
  11. Pre-trend bias adjustment
  12. Reconciled incrementality
  13. Bootstrap ROAS
  14. Persist results to analysis_results table       ← wired here
  15. Update job status to completed / failed         ← wired here

Errors at any step mark the job as 'failed' and persist the error message.
"""
from __future__ import annotations

import io
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from app.services.statistical.bootstrap_roas import run_bootstrap_roas
from app.services.statistical.cell_assignment import assign_cells
from app.services.statistical.feature_engineering import (
    compute_geo_features,
    normalize_features,
)
from app.services.statistical.kmeans_clustering import run_kmeans_sweep
from app.services.statistical.parallel_trends import test_parallel_trends
from app.services.statistical.power_analysis import compute_power, estimate_baseline_stats
from app.services.statistical.pretrend_adjustment import compute_pretrend_adjustment
from app.services.statistical.reconciled_incrementality import reconcile_incrementality
from app.services.statistical.simple_did import run_simple_did
from app.services.statistical.twfe_did import run_twfe_did
from app.services.statistical.yoy_analysis import run_yoy_analysis


# ---------------------------------------------------------------------------
# ARQ worker lifecycle
# ---------------------------------------------------------------------------


async def startup(ctx: dict) -> None:
    """
    Called once when the ARQ worker process starts.

    Creates the async SQLAlchemy engine + session factory and stores them in
    `ctx` so every task invocation can open a DB session without re-creating
    the connection pool each time.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import settings

    db_url = settings.database_url
    if db_url:
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
    else:
        db_url = "postgresql+asyncpg://localhost/incremental_tool_dev"

    engine = create_async_engine(db_url, pool_pre_ping=True)
    ctx["db_engine"] = engine
    ctx["db_session_factory"] = async_sessionmaker(engine, expire_on_commit=False)


async def shutdown(ctx: dict) -> None:
    """Called once when the ARQ worker shuts down. Disposes the DB pool."""
    if "db_engine" in ctx:
        await ctx["db_engine"].dispose()


# ---------------------------------------------------------------------------
# ARQ task entry point
# ---------------------------------------------------------------------------


async def run_analysis(
    ctx: dict,
    job_id: str,
    test_id: str,
    workspace_id: str,
    df_json: str,
    spend: float,
    has_prior_year: bool = False,
    n_cells: int = 2,
    n_bootstrap_resamples: int = 1000,
) -> None:
    """
    ARQ task entry point.

    Runs the full statistical pipeline and persists the result to the database.
    Updates AnalysisJob.status to RUNNING → COMPLETED (or FAILED on error).

    Args:
        ctx:                  ARQ context dict (db_session_factory set in startup).
        job_id:               UUID string of the analysis_jobs row to update.
        test_id:              UUID string of the tests row.
        workspace_id:         UUID string of the owning workspace.
        df_json:              Panel DataFrame serialized as JSON (orient='records').
        spend:                Total test-period media spend for the treatment cell.
        has_prior_year:       Whether df includes 'revenue_prior' column.
        n_cells:              Number of test cells.
        n_bootstrap_resamples: Bootstrap iterations for ROAS CIs.
    """
    from sqlalchemy import select

    from app.models.workspace import AnalysisJob, AnalysisResult, JobStatus, Test, TestStatus

    session_factory = ctx["db_session_factory"]
    job_uuid = uuid.UUID(job_id)

    async with session_factory() as db:
        # ── Mark job as RUNNING ─────────────────────────────────────────────
        job_q = await db.execute(select(AnalysisJob).where(AnalysisJob.id == job_uuid))
        job = job_q.scalar_one()
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            # ── Run the pure computation pipeline ───────────────────────────
            result = _run_pipeline_steps(
                df_json=df_json,
                spend=spend,
                has_prior_year=has_prior_year,
                n_cells=n_cells,
                n_bootstrap_resamples=n_bootstrap_resamples,
            )

            # ── Persist AnalysisResult ──────────────────────────────────────
            analysis_result = AnalysisResult(
                job_id=job_uuid,
                test_id=uuid.UUID(test_id),
                workspace_id=uuid.UUID(workspace_id),
                # Parallel trends
                parallel_trends_passes=result.get("parallel_trends_passes"),
                parallel_trends_p_value=result.get("parallel_trends_p_value"),
                parallel_trends_flag=result.get("parallel_trends_flag"),
                # TWFE
                twfe_treatment_effect=result.get("twfe_treatment_effect"),
                twfe_treatment_effect_dollars=result.get("twfe_treatment_effect_dollars"),
                twfe_p_value=result.get("twfe_p_value"),
                twfe_ci_80=result.get("twfe_ci_80"),
                twfe_ci_90=result.get("twfe_ci_90"),
                twfe_ci_95=result.get("twfe_ci_95"),
                twfe_se=result.get("twfe_se"),
                # Simple DiD
                simple_did_estimate=result.get("simple_did_estimate"),
                simple_did_dollars=result.get("simple_did_dollars"),
                # YoY
                yoy_did_proportion=result.get("yoy_did_proportion"),
                yoy_did_dollars=result.get("yoy_did_dollars"),
                # Pre-trend adjustment
                beta_pre=result.get("beta_pre"),
                beta_pre_p_value=result.get("beta_pre_p_value"),
                adjusted_yoy_did_dollars=result.get("adjusted_yoy_did_dollars"),
                is_causally_clean=result.get("is_causally_clean"),
                # Reconciled
                incremental_revenue_midpoint=result.get("incremental_revenue_midpoint"),
                incremental_revenue_weighted=result.get("incremental_revenue_weighted"),
                # ROAS
                roas_low=result.get("roas_low"),
                roas_mid=result.get("roas_mid"),
                roas_high=result.get("roas_high"),
                roas_ci_95=result.get("roas_ci_95"),
                total_spend=result.get("total_spend"),
                # Raw blobs
                weekly_did_json=result.get("weekly_did_json"),
                weekly_yoy_json=result.get("weekly_yoy_json"),
                power_analysis_json=result.get("power_analysis_json"),
                cluster_summary_json=result.get("cluster_summary_json"),
            )
            db.add(analysis_result)

            # ── Mark job COMPLETED + advance test status ────────────────────
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)

            test_q = await db.execute(select(Test).where(Test.id == uuid.UUID(test_id)))
            test_row = test_q.scalar_one_or_none()
            if test_row is not None:
                test_row.status = TestStatus.COMPLETED

            await db.commit()

        except Exception as exc:
            # ── Mark job FAILED ─────────────────────────────────────────────
            job.status = JobStatus.FAILED
            job.error_message = str(exc)
            job.error_detail = {"traceback": traceback.format_exc()}
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            raise


# ---------------------------------------------------------------------------
# ARQ worker settings
# ---------------------------------------------------------------------------


class WorkerSettings:
    """ARQ worker configuration."""

    functions = [run_analysis]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 4
    job_timeout = 300       # 5 minutes max per analysis
    keep_result = 86400     # 24 hours


# ---------------------------------------------------------------------------
# Pure computation pipeline (no DB — unit-testable)
# ---------------------------------------------------------------------------


def _run_pipeline_steps(
    df_json: str,
    spend: float,
    has_prior_year: bool = False,
    n_cells: int = 2,
    n_bootstrap_resamples: int = 1000,
) -> dict[str, Any]:
    """
    Run all statistical pipeline steps and return a results dict.

    This is a pure synchronous function with no I/O, making it easy to
    unit-test independently of the ARQ/DB infrastructure.

    Returns:
        Dict of computed result fields keyed by AnalysisResult column names.
    """
    result: dict[str, Any] = {}

    df = pd.read_json(io.StringIO(df_json), orient="records")
    _validate_panel_columns(df, has_prior_year)

    # ── Step 3: Parallel trends ─────────────────────────────────────────────
    pt = test_parallel_trends(df)
    result.update({
        "parallel_trends_passes": pt.passes,
        "parallel_trends_p_value": pt.p_value,
        "parallel_trends_flag": pt.flag_message,
    })

    # ── Step 4–6: Clustering + assignment ───────────────────────────────────
    baseline = df[df["period"] == 0]
    raw_features = compute_geo_features(baseline, metric_col="revenue")
    normed = normalize_features(raw_features)
    clustering = run_kmeans_sweep(normed)
    assignment = assign_cells(raw_features, clustering.recommended_labels, n_cells=n_cells)

    result["cluster_summary_json"] = clustering.results[0].labels.tolist()

    # Derive is_treatment from clustering if not already in df (cell_id 0 = treatment)
    if "is_treatment" not in df.columns:
        geo_cell = assignment.geo_assignments.reset_index()[["geo", "cell_id"]]
        treatment_geos = set(geo_cell.loc[geo_cell["cell_id"] == 0, "geo"])
        df = df.copy()
        df["is_treatment"] = df["geo"].isin(treatment_geos)

    # ── Step 7: Power analysis ───────────────────────────────────────────────
    mean_baseline, var_baseline = estimate_baseline_stats(baseline)
    n_geos_per_cell = len(raw_features) // n_cells
    power_result = compute_power(
        n_geos_per_cell=max(n_geos_per_cell, 1),
        baseline_weekly_variance=var_baseline,
        baseline_weekly_mean=mean_baseline,
    )
    result["power_analysis_json"] = {
        "power": power_result.power,
        "is_adequately_powered": power_result.is_adequately_powered,
        "required_weeks": power_result.required_weeks,
        "warning_message": power_result.warning_message,
    }

    # ── Step 8: TWFE DiD ─────────────────────────────────────────────────────
    twfe = run_twfe_did(df)
    result.update({
        "twfe_treatment_effect": twfe.treatment_effect,
        "twfe_treatment_effect_dollars": twfe.treatment_effect_dollars,
        "twfe_p_value": twfe.p_value,
        "twfe_ci_80": {"lower": twfe.ci_80_lower, "upper": twfe.ci_80_upper},
        "twfe_ci_90": {"lower": twfe.ci_90_lower, "upper": twfe.ci_90_upper},
        "twfe_ci_95": {"lower": twfe.ci_95_lower, "upper": twfe.ci_95_upper},
        "twfe_se": twfe.standard_error,
    })

    # ── Step 9: Simple DiD ───────────────────────────────────────────────────
    simple = run_simple_did(df)
    result.update({
        "simple_did_estimate": simple.did_estimate,
        "simple_did_dollars": simple.did_dollars,
        "weekly_did_json": simple.weekly_did.reset_index().to_dict(orient="records"),
    })

    # ── Step 10–11: YoY + pre-trend adjustment ───────────────────────────────
    if has_prior_year and "revenue_prior" in df.columns:
        yoy = run_yoy_analysis(df)
        result.update({
            "yoy_did_proportion": yoy.yoy_did_proportion,
            "yoy_did_dollars": yoy.yoy_did_dollars,
            "weekly_yoy_json": yoy.weekly_yoy.reset_index().to_dict(orient="records"),
        })

        pretrend = compute_pretrend_adjustment(
            df=df,
            raw_yoy_did_dollars=yoy.yoy_did_dollars,
        )
        result.update({
            "beta_pre": pretrend.beta_pre,
            "beta_pre_p_value": pretrend.beta_pre_p_value,
            "adjusted_yoy_did_dollars": pretrend.adjusted_yoy_did_dollars,
            "is_causally_clean": pretrend.is_causally_clean,
        })
        adjusted_yoy = pretrend.adjusted_yoy_did_dollars
        yoy_se = abs(pretrend.beta_pre_se * mean_baseline) if mean_baseline else 1.0
    else:
        adjusted_yoy = simple.did_dollars
        yoy_se = twfe.standard_error * mean_baseline if mean_baseline else 1.0

    # ── Step 12: Reconciled incrementality ──────────────────────────────────
    reconciled = reconcile_incrementality(
        twfe_did_dollars=twfe.treatment_effect_dollars,
        adjusted_yoy_dollars=adjusted_yoy,
        twfe_se=twfe.standard_error * mean_baseline if mean_baseline else 1.0,
        yoy_se=yoy_se,
    )
    result.update({
        "incremental_revenue_midpoint": reconciled.midpoint_dollars,
        "incremental_revenue_weighted": reconciled.variance_weighted_dollars,
    })

    # ── Step 13: Bootstrap ROAS ──────────────────────────────────────────────
    if spend > 0:
        roas = run_bootstrap_roas(
            df=df,
            twfe_did_dollars=twfe.treatment_effect_dollars,
            reconciled_dollars=reconciled.midpoint_dollars,
            adjusted_yoy_dollars=adjusted_yoy,
            spend=spend,
            n_resamples=n_bootstrap_resamples,
        )
        result.update({
            "roas_low": roas.roas_low,
            "roas_mid": roas.roas_mid,
            "roas_high": roas.roas_high,
            "roas_ci_95": {"lower": roas.ci_95_lower, "upper": roas.ci_95_upper},
            "total_spend": spend,
        })

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


REQUIRED_PANEL_COLUMNS = {"geo", "week", "period", "is_treatment", "revenue"}
OPTIONAL_PANEL_COLUMNS = {"spend", "revenue_prior"}


def _validate_panel_columns(df: pd.DataFrame, has_prior_year: bool) -> None:
    """Raise ValueError if required columns are missing from the panel."""
    missing = REQUIRED_PANEL_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"Panel DataFrame is missing required columns: {missing}. "
            "Ensure the data was properly ingested and normalized before analysis."
        )
    if has_prior_year and "revenue_prior" not in df.columns:
        raise ValueError(
            "has_prior_year=True but 'revenue_prior' column not found in DataFrame."
        )
