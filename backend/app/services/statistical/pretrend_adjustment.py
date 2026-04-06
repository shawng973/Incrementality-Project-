"""
Pre-Trend Bias Adjustment — regression-based.

Estimates any pre-existing trend differential between test and control,
then adjusts the raw YoY DiD:

    Adjusted_YoY_DiD_$ = Raw_YoY_DiD_$ − (β_pre × Prior_Year_Baseline_$)

If β_pre is not statistically significant (p > 0.10), the adjustment
is noted as minimal and the experiment is flagged as "causally clean."
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats as scipy_stats


@dataclass(frozen=True)
class PretrendAdjustmentResult:
    """Output of compute_pretrend_adjustment()."""

    beta_pre: float                 # pre-trend slope coefficient
    beta_pre_se: float
    beta_pre_p_value: float
    raw_yoy_did_dollars: float
    adjusted_yoy_did_dollars: float
    adjustment_dollars: float       # = raw - adjusted
    adjustment_pct_of_raw: float    # how much the adjustment shifted the estimate
    is_causally_clean: bool         # True if p_value > 0.10
    diagnostic_note: str


P_THRESHOLD = 0.10


def compute_pretrend_adjustment(
    df: pd.DataFrame,
    raw_yoy_did_dollars: float,
    treatment_col: str = "is_treatment",
    post_col: str = "period",
    metric_col: str = "revenue",
    prior_metric_col: str = "revenue_prior",
    geo_col: str = "geo",
    time_col: str = "week",
) -> PretrendAdjustmentResult:
    """
    Estimate pre-trend coefficient and adjust YoY DiD.

    Args:
        df:                  Full panel (baseline + test periods).
        raw_yoy_did_dollars: Raw YoY DiD estimate in dollars (from yoy_analysis).
        treatment_col:       Binary treatment indicator.
        post_col:            Binary post period indicator.
        metric_col:          Current-year outcome.
        prior_metric_col:    Prior-year outcome.
        geo_col:             Geo identifier.
        time_col:            Time index.

    Returns:
        PretrendAdjustmentResult.
    """
    required = {treatment_col, post_col, metric_col, geo_col, time_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    baseline = df[df[post_col] == 0].copy()

    if len(baseline) < 10:
        raise ValueError("Insufficient baseline observations for pre-trend estimation.")

    # Absorb geo fixed effects
    geo_means_metric = baseline.groupby(geo_col, observed=True)[metric_col].transform("mean")
    geo_means_time = baseline.groupby(geo_col, observed=True)[time_col].transform("mean")
    baseline["metric_demeaned"] = baseline[metric_col] - geo_means_metric
    baseline["time_demeaned"] = baseline[time_col] - geo_means_time
    baseline["treat_time"] = baseline[treatment_col] * baseline["time_demeaned"]

    y = baseline["metric_demeaned"].to_numpy(dtype=float)
    X = sm.add_constant(baseline["treat_time"].to_numpy(dtype=float))

    fit = sm.OLS(y, X).fit()
    beta_pre = float(fit.params[1])
    se_pre = float(fit.bse[1])
    n_geos = baseline[geo_col].nunique()
    df_resid = max(n_geos - 2, 1)
    t_stat = beta_pre / se_pre if se_pre > 0 else 0.0
    p_value = float(2 * scipy_stats.t.sf(abs(t_stat), df=df_resid))

    # Prior-year baseline: mean of prior_metric for treatment geos in baseline
    if prior_metric_col in df.columns:
        prior_baseline_mask = (df[post_col] == 0) & (df[treatment_col] == 1)
        prior_baseline_dollars = float(df.loc[prior_baseline_mask, prior_metric_col].mean())
    else:
        # Fallback: use current baseline
        baseline_mask = (df[post_col] == 0) & (df[treatment_col] == 1)
        prior_baseline_dollars = float(df.loc[baseline_mask, metric_col].mean())

    adjustment = beta_pre * prior_baseline_dollars
    adjusted_did = raw_yoy_did_dollars - adjustment
    adj_pct = abs(adjustment / raw_yoy_did_dollars) if raw_yoy_did_dollars != 0 else 0.0

    is_clean = p_value > P_THRESHOLD

    if is_clean:
        note = (
            f"Pre-trend coefficient β_pre = {beta_pre:.4f} (p={p_value:.3f} > 0.10). "
            "No statistically significant trend differential detected. "
            "This experiment is causally clean — the DiD estimate is unlikely to be biased by pre-existing trends."
        )
    else:
        note = (
            f"Pre-trend coefficient β_pre = {beta_pre:.4f} (p={p_value:.3f} < 0.10). "
            f"Adjustment of ${adjustment:,.0f} applied to raw YoY DiD. "
            f"This shifted the estimate by {adj_pct:.1%}. "
            "Interpret adjusted YoY DiD as the primary estimate."
        )

    return PretrendAdjustmentResult(
        beta_pre=beta_pre,
        beta_pre_se=se_pre,
        beta_pre_p_value=p_value,
        raw_yoy_did_dollars=raw_yoy_did_dollars,
        adjusted_yoy_did_dollars=adjusted_did,
        adjustment_dollars=adjustment,
        adjustment_pct_of_raw=adj_pct,
        is_causally_clean=is_clean,
        diagnostic_note=note,
    )
