"""Pydantic schemas for the analysis trigger and results endpoints."""
from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, Field


class AnalysisTriggerRequest(BaseModel):
    spend: float = Field(..., gt=0, description="Total test-period media spend ($)")
    has_prior_year: bool = Field(default=False)
    n_bootstrap_resamples: int = Field(default=1000, ge=100, le=5000)


class AnalysisJobResponse(BaseModel):
    job_id: uuid.UUID
    test_id: uuid.UUID
    status: str
    message: str


class AnalysisResultResponse(BaseModel):
    job_id: uuid.UUID
    test_id: uuid.UUID
    status: str

    # Parallel trends
    parallel_trends_passes: Optional[bool] = None
    parallel_trends_p_value: Optional[float] = None
    parallel_trends_flag: Optional[str] = None

    # TWFE
    twfe_treatment_effect: Optional[float] = None
    twfe_treatment_effect_dollars: Optional[float] = None
    twfe_p_value: Optional[float] = None
    twfe_ci_80: Optional[dict] = None
    twfe_ci_90: Optional[dict] = None
    twfe_ci_95: Optional[dict] = None

    # Simple DiD
    simple_did_estimate: Optional[float] = None
    simple_did_dollars: Optional[float] = None

    # YoY
    yoy_did_proportion: Optional[float] = None
    yoy_did_dollars: Optional[float] = None

    # Pre-trend adjustment
    is_causally_clean: Optional[bool] = None
    adjusted_yoy_did_dollars: Optional[float] = None

    # Reconciled
    incremental_revenue_midpoint: Optional[float] = None
    incremental_revenue_weighted: Optional[float] = None

    # ROAS
    roas_low: Optional[float] = None
    roas_mid: Optional[float] = None
    roas_high: Optional[float] = None
    roas_ci_95: Optional[dict] = None
    total_spend: Optional[float] = None

    # Power analysis
    power_analysis_json: Optional[dict] = None

    model_config = {"from_attributes": True}
