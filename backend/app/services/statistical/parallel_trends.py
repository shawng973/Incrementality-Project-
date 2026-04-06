"""
Parallel Trends Validation — required pre-step before reporting DiD.

Tests whether treatment and control geos have statistically similar
pre-period trends. If the trends diverge (interaction coefficients
jointly non-zero), DiD estimates may be biased.

Method:
  Regress pre-period outcome on a linear time trend interacted with
  the treatment indicator, controlling for geo fixed effects.

  Y_it = α + β₁(Treat_i × t) + γ_i + ε_it   (pre-period only)

  H₀: β₁ = 0 (no trend differential)
  Reject at p < 0.10 → flag parallel trends violation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats as scipy_stats


@dataclass(frozen=True)
class ParallelTrendsResult:
    """Output of test_parallel_trends()."""

    trend_coefficient: float      # β₁: treatment × time interaction
    standard_error: float
    p_value: float                # H₀: β₁ = 0
    passes: bool                  # True if p > 0.10 (trends are parallel)
    flag_message: str | None      # non-None if parallel trends violated


P_VALUE_THRESHOLD = 0.10


def test_parallel_trends(
    df: pd.DataFrame,
    treatment_col: str = "is_treatment",
    post_col: str = "period",
    metric_col: str = "revenue",
    geo_col: str = "geo",
    time_col: str = "week",
) -> ParallelTrendsResult:
    """
    Test for pre-period parallel trends.

    Uses baseline data only (post_col == 0). Regresses outcome on
    (treatment × time trend) after absorbing geo fixed effects.

    Args:
        df:            Full panel (baseline + test periods).
        treatment_col: Binary treatment indicator.
        post_col:      Binary post period indicator (0 = baseline).
        metric_col:    Outcome variable.
        geo_col:       Geo identifier.
        time_col:      Time index (integer).

    Returns:
        ParallelTrendsResult.

    Raises:
        ValueError: if baseline period has insufficient observations.
    """
    required = {treatment_col, post_col, metric_col, geo_col, time_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    baseline = df[df[post_col] == 0].copy()
    if len(baseline) < 10:
        raise ValueError(
            f"Insufficient baseline observations ({len(baseline)}); need at least 10."
        )

    if baseline[treatment_col].nunique() < 2:
        raise ValueError("baseline must contain both treatment and control geos.")

    # Normalize metric by baseline mean so the coefficient is a proportion per week
    baseline_mean = float(baseline[metric_col].mean())
    if baseline_mean == 0:
        raise ValueError("Baseline mean is 0; cannot normalize metric.")
    baseline["metric_norm"] = baseline[metric_col] / baseline_mean

    # Absorb geo fixed effects via within-geo demeaning
    for col in ["metric_norm", time_col]:
        geo_mean = baseline.groupby(geo_col, observed=True)[col].transform("mean")
        baseline[f"{col}_demeaned"] = baseline[col] - geo_mean

    # Interaction term: (treatment indicator) × (demeaned time)
    baseline["treat_time"] = baseline[treatment_col] * baseline[f"{time_col}_demeaned"]

    y = baseline["metric_norm_demeaned"].to_numpy(dtype=float)
    X = sm.add_constant(baseline["treat_time"].to_numpy(dtype=float))

    fit = sm.OLS(y, X).fit()
    beta = float(fit.params[1])
    se = float(fit.bse[1])
    n_geos = baseline[geo_col].nunique()
    df_resid = max(n_geos - 2, 1)
    t_stat = beta / se if se > 0 else 0.0
    p_value = float(2 * scipy_stats.t.sf(abs(t_stat), df=df_resid))

    passes = p_value > P_VALUE_THRESHOLD

    flag = None
    if not passes:
        flag = (
            f"Parallel trends assumption may be violated (p={p_value:.3f} < 0.10). "
            f"Treatment geos show a pre-period trend differential of "
            f"{beta:+.4f} per week. DiD estimates may be biased. "
            "Interpret results with caution and review pre-trend adjustment."
        )

    return ParallelTrendsResult(
        trend_coefficient=beta,
        standard_error=se,
        p_value=p_value,
        passes=passes,
        flag_message=flag,
    )
