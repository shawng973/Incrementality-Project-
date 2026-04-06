"""
Bootstrap ROAS / iROAS with Confidence Intervals.

ROAS_low  = TWFE_DiD_$ / Spend
ROAS_mid  = Reconciled_$ / Spend
ROAS_high = Adjusted_YoY_$ / Spend

Bootstrap CIs (1,000 resamples by default) resample geo-level observations
to propagate uncertainty in the incremental revenue estimate into the ROAS range.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BootstrapROASResult:
    """Output of run_bootstrap_roas()."""

    roas_low: float          # TWFE DiD / spend
    roas_mid: float          # Reconciled (midpoint) / spend
    roas_high: float         # Adjusted YoY / spend

    ci_95_lower: float       # 2.5th percentile of bootstrap distribution (roas_mid)
    ci_95_upper: float       # 97.5th percentile
    ci_90_lower: float
    ci_90_upper: float
    ci_80_lower: float
    ci_80_upper: float

    bootstrap_mean: float    # mean of bootstrap ROAS_mid distribution
    n_resamples: int
    spend: float


def run_bootstrap_roas(
    df: pd.DataFrame,
    twfe_did_dollars: float,
    reconciled_dollars: float,
    adjusted_yoy_dollars: float,
    spend: float,
    treatment_col: str = "is_treatment",
    post_col: str = "period",
    metric_col: str = "revenue",
    geo_col: str = "geo",
    n_resamples: int = 1000,
    seed: int = 42,
) -> BootstrapROASResult:
    """
    Compute ROAS estimates and bootstrap CIs.

    Bootstrap procedure:
      1. Resample geos (with replacement) within each cell (treatment/control).
      2. For each resample, compute the simple DiD as a proxy for incremental revenue.
      3. Divide by spend to get a ROAS draw.
      4. Report percentile CIs of the resulting distribution.

    Args:
        df:                   Panel DataFrame (baseline + test periods).
        twfe_did_dollars:     TWFE DiD estimate in dollars.
        reconciled_dollars:   Reconciled midpoint estimate in dollars.
        adjusted_yoy_dollars: Adjusted YoY DiD estimate in dollars.
        spend:                Total test-period spend for the treatment cell.
        n_resamples:          Number of bootstrap resamples.
        seed:                 Random seed.

    Returns:
        BootstrapROASResult.

    Raises:
        ValueError: if spend <= 0.
    """
    if spend <= 0:
        raise ValueError(f"spend must be positive, got {spend}.")
    if n_resamples < 100:
        raise ValueError(f"n_resamples must be >= 100, got {n_resamples}.")

    required = {treatment_col, post_col, metric_col, geo_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    roas_low = twfe_did_dollars / spend
    roas_mid = reconciled_dollars / spend
    roas_high = adjusted_yoy_dollars / spend

    # Bootstrap distribution of roas_mid proxy
    bootstrap_roas = _bootstrap_roas_distribution(
        df=df,
        treatment_col=treatment_col,
        post_col=post_col,
        metric_col=metric_col,
        geo_col=geo_col,
        spend=spend,
        n_resamples=n_resamples,
        seed=seed,
    )

    def pct_ci(alpha: float) -> tuple[float, float]:
        lower = float(np.percentile(bootstrap_roas, 100 * alpha / 2))
        upper = float(np.percentile(bootstrap_roas, 100 * (1 - alpha / 2)))
        return lower, upper

    ci95 = pct_ci(0.05)
    ci90 = pct_ci(0.10)
    ci80 = pct_ci(0.20)

    return BootstrapROASResult(
        roas_low=roas_low,
        roas_mid=roas_mid,
        roas_high=roas_high,
        ci_95_lower=ci95[0],
        ci_95_upper=ci95[1],
        ci_90_lower=ci90[0],
        ci_90_upper=ci90[1],
        ci_80_lower=ci80[0],
        ci_80_upper=ci80[1],
        bootstrap_mean=float(np.mean(bootstrap_roas)),
        n_resamples=n_resamples,
        spend=spend,
    )


def _bootstrap_roas_distribution(
    df: pd.DataFrame,
    treatment_col: str,
    post_col: str,
    metric_col: str,
    geo_col: str,
    spend: float,
    n_resamples: int,
    seed: int,
) -> np.ndarray:
    """
    Generate bootstrap ROAS distribution by resampling geos within each cell.

    Uses simple DiD as the per-resample incremental revenue estimate.
    """
    rng = np.random.default_rng(seed)

    test_df = df[df[post_col] == 1]
    baseline_df = df[df[post_col] == 0]

    treat_geos = test_df[test_df[treatment_col] == 1][geo_col].unique()
    ctrl_geos = test_df[test_df[treatment_col] == 0][geo_col].unique()

    treat_base_mean = baseline_df[baseline_df[treatment_col] == 1][metric_col].mean()
    ctrl_base_mean = baseline_df[baseline_df[treatment_col] == 0][metric_col].mean()

    # Pre-compute per-geo post-period means for speed
    treat_post_by_geo = (
        test_df[test_df[treatment_col] == 1]
        .groupby(geo_col, observed=True)[metric_col]
        .mean()
    )
    ctrl_post_by_geo = (
        test_df[test_df[treatment_col] == 0]
        .groupby(geo_col, observed=True)[metric_col]
        .mean()
    )

    bootstrap_roas = np.empty(n_resamples)

    for i in range(n_resamples):
        treat_sample = rng.choice(treat_geos, size=len(treat_geos), replace=True)
        ctrl_sample = rng.choice(ctrl_geos, size=len(ctrl_geos), replace=True)

        treat_post_mean = float(np.mean(treat_post_by_geo.loc[treat_sample].values))
        ctrl_post_mean = float(np.mean(ctrl_post_by_geo.loc[ctrl_sample].values))

        delta_treat = (treat_post_mean - treat_base_mean) / treat_base_mean
        delta_ctrl = (ctrl_post_mean - ctrl_base_mean) / ctrl_base_mean
        did = delta_treat - delta_ctrl

        incremental = did * treat_base_mean
        bootstrap_roas[i] = incremental / spend

    return bootstrap_roas
