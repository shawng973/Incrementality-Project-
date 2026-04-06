"""
Two-Way Fixed Effects Difference-in-Differences (TWFE DiD)

Primary causal estimator. Model:

    Y_it = α + β₁(Treat_i) + β₂(Post_t) + β₃(Treat_i × Post_t) + γ_i + δ_t + ε_it

where:
    γ_i   = geo fixed effects  (absorbed via within-geo demeaning)
    δ_t   = time fixed effects (absorbed via within-period demeaning)
    β₃    = treatment effect   (the coefficient we report)
    ε_it  = errors clustered at the geo level

Implementation uses statsmodels OLS with entity and time dummies explicitly,
then re-estimates standard errors using HC3-based geo-level clustering.
This is the "Liang-Zeger" approach: regress on FE-absorbed residuals,
cluster SEs at geo level.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats as scipy_stats


@dataclass(frozen=True)
class TWFEResult:
    """Output of run_twfe_did()."""

    treatment_effect: float        # β₃ as a proportion (e.g., 0.15 = 15%)
    treatment_effect_dollars: float  # β₃ * avg_baseline_revenue
    standard_error: float          # clustered SE of β₃
    p_value: float                 # two-tailed p-value for β₃
    ci_80_lower: float
    ci_80_upper: float
    ci_90_lower: float
    ci_90_upper: float
    ci_95_lower: float
    ci_95_upper: float
    geo_fixed_effects_count: int
    time_fixed_effects_count: int
    n_observations: int
    r_squared: float
    clustered_se_used: bool


def run_twfe_did(
    df: pd.DataFrame,
    treatment_col: str = "is_treatment",
    post_col: str = "period",
    metric_col: str = "revenue",
    geo_col: str = "geo",
    time_col: str = "week",
    cluster: bool = True,
) -> TWFEResult:
    """
    Estimate the TWFE DiD treatment effect.

    Args:
        df:             Panel DataFrame with geo × week observations.
                        Must include both baseline (period=0) and test (period=1) rows.
        treatment_col:  Binary indicator: 1 = treatment geo, 0 = control.
        post_col:       Binary indicator: 1 = test period, 0 = baseline.
        metric_col:     Outcome variable (revenue, conversions, etc.).
        geo_col:        Geo identifier column.
        time_col:       Time period column (integer index).
        cluster:        If True, cluster standard errors at geo level.

    Returns:
        TWFEResult with treatment effect, SEs, p-values, and CIs.

    Raises:
        ValueError: if required columns are missing or dataset is malformed.
    """
    required = {treatment_col, post_col, metric_col, geo_col, time_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    if df[treatment_col].nunique() < 2:
        raise ValueError("treatment_col must contain both 0 and 1 values.")

    if df[post_col].nunique() < 2:
        raise ValueError("post_col must contain both 0 and 1 values.")

    df = df.copy()
    df["treat_post"] = df[treatment_col] * df[post_col]

    # Normalize outcome by treatment baseline mean so β₃ is a proportion (e.g. 0.15 = 15% lift)
    avg_baseline = _avg_baseline_metric(df, metric_col, treatment_col, post_col)
    if avg_baseline == 0:
        raise ValueError("avg_baseline_metric is 0; cannot normalize outcome.")
    df[f"{metric_col}_norm"] = df[metric_col] / avg_baseline

    # Absorb fixed effects via within-transformation (Frisch-Waugh)
    # Center each variable by geo mean + time mean - grand mean
    df = _absorb_fixed_effects(df, f"{metric_col}_norm", geo_col, time_col)
    df = _absorb_fixed_effects(df, "treat_post", geo_col, time_col)

    y = df[f"{metric_col}_norm_demeaned"].to_numpy(dtype=float)
    X = df["treat_post_demeaned"].to_numpy(dtype=float)
    X_with_const = sm.add_constant(X, has_constant="add")

    model = sm.OLS(y, X_with_const)
    fit = model.fit()

    # β₃ is the coefficient on treat_post_demeaned — proportional (e.g. 0.15 = 15% lift)
    beta3 = float(fit.params[1])

    if cluster:
        # Geo-clustered SE using sandwich estimator
        groups = df[geo_col].to_numpy()
        se_clustered = _clustered_se(y, X_with_const, fit.params, groups)
        se = float(se_clustered[1])
    else:
        se = float(fit.bse[1])

    t_stat = beta3 / se if se > 0 else float("inf")
    n_obs = len(df)
    n_geos = df[geo_col].nunique()
    df_resid = n_geos - 2  # cluster-corrected degrees of freedom

    # Use t-distribution with cluster-corrected df
    p_value = float(2 * scipy_stats.t.sf(abs(t_stat), df=df_resid))

    def ci(alpha: float) -> tuple[float, float]:
        t_crit = float(scipy_stats.t.ppf(1 - alpha / 2, df=df_resid))
        return beta3 - t_crit * se, beta3 + t_crit * se

    geo_fe_count = df[geo_col].nunique()
    time_fe_count = df[time_col].nunique()

    return TWFEResult(
        treatment_effect=beta3,
        treatment_effect_dollars=beta3 * avg_baseline,
        standard_error=se,
        p_value=p_value,
        ci_80_lower=ci(0.20)[0],
        ci_80_upper=ci(0.20)[1],
        ci_90_lower=ci(0.10)[0],
        ci_90_upper=ci(0.10)[1],
        ci_95_lower=ci(0.05)[0],
        ci_95_upper=ci(0.05)[1],
        geo_fixed_effects_count=geo_fe_count,
        time_fixed_effects_count=time_fe_count,
        n_observations=n_obs,
        r_squared=float(fit.rsquared),
        clustered_se_used=cluster,
    )


# ---------------------------------------------------------------------------
# Fixed-effects absorption (Mundlak / within-transformation)
# ---------------------------------------------------------------------------


def _absorb_fixed_effects(
    df: pd.DataFrame,
    col: str,
    geo_col: str,
    time_col: str,
) -> pd.DataFrame:
    """
    Apply the two-way within-transformation to `col`.

    Demeaned value = Y_it - ȳ_i - ȳ_t + ȳ
    where ȳ_i = geo mean, ȳ_t = time mean, ȳ = grand mean.

    Adds column `{col}_demeaned` to df.
    """
    df = df.copy()
    grand_mean = df[col].mean()
    geo_means = df.groupby(geo_col, observed=True)[col].transform("mean")
    time_means = df.groupby(time_col)[col].transform("mean")
    df[f"{col}_demeaned"] = df[col] - geo_means - time_means + grand_mean
    return df


# ---------------------------------------------------------------------------
# Geo-clustered standard errors (Liang-Zeger sandwich)
# ---------------------------------------------------------------------------


def _clustered_se(
    y: np.ndarray,
    X: np.ndarray,
    params: np.ndarray,
    groups: np.ndarray,
) -> np.ndarray:
    """
    Compute cluster-robust (Liang-Zeger) standard errors.

    Formula:
        Var(β) = (X'X)⁻¹ · B · (X'X)⁻¹
        B = Σ_g (X_g' ε_g ε_g' X_g)
    """
    n, k = X.shape
    resid = y - X @ params
    XtX_inv = np.linalg.pinv(X.T @ X)

    unique_groups = np.unique(groups)
    B = np.zeros((k, k))

    for g in unique_groups:
        mask = groups == g
        Xg = X[mask]
        eg = resid[mask]
        score_g = Xg.T @ eg
        B += np.outer(score_g, score_g)

    # Small-sample correction: G/(G-1) * (N-1)/(N-K)
    G = len(unique_groups)
    correction = (G / (G - 1)) * ((n - 1) / (n - k))
    V = correction * XtX_inv @ B @ XtX_inv

    return np.sqrt(np.diag(V))


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _avg_baseline_metric(
    df: pd.DataFrame,
    metric_col: str,
    treatment_col: str,
    post_col: str,
) -> float:
    """Average metric in the treatment group during the baseline period."""
    mask = (df[treatment_col] == 1) & (df[post_col] == 0)
    vals = df.loc[mask, metric_col]
    return float(vals.mean()) if len(vals) > 0 else 1.0
