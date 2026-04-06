"""
Power Analysis — pre-test sample size and power calculation.

Uses the standard two-sample t-test power formula adapted for geo-level data.

For geo-split tests, the unit of observation is the geo (not the individual
transaction). Power is determined by:
  - Number of geos per cell
  - Baseline variance of the primary metric at the geo level
  - Minimum Detectable Effect (MDE) as a proportion of baseline mean
  - Desired significance level (α)

This is intentionally conservative: it uses the geo-level variance (not
individual-level), matching how TWFE DiD treats geo as the unit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats


@dataclass(frozen=True)
class PowerResult:
    """Output of compute_power()."""

    power: float                      # probability of detecting true effect (0–1)
    required_weeks: int               # minimum weeks to achieve target_power
    n_geos_per_cell: int
    mde: float                        # minimum detectable effect (proportion)
    alpha: float                      # significance level
    target_power: float
    is_adequately_powered: bool       # True if power >= target_power
    warning_message: str | None       # non-None if underpowered


VALID_ALPHA = {0.05, 0.10, 0.20}  # corresponding to 95%, 90%, 80% CIs


def compute_power(
    n_geos_per_cell: int,
    baseline_weekly_variance: float,
    baseline_weekly_mean: float,
    mde: float = 0.10,
    n_test_weeks: int = 8,
    alpha: float = 0.10,
    target_power: float = 0.80,
) -> PowerResult:
    """
    Compute statistical power for a geo-split test.

    The effective test statistic is the mean of the primary metric across
    n_geos_per_cell geos, averaged over n_test_weeks. The standard error
    accounts for both geo-level variation and temporal averaging.

    Args:
        n_geos_per_cell:          Number of geos in each cell.
        baseline_weekly_variance: Variance of weekly metric at geo level (σ²).
        baseline_weekly_mean:     Mean weekly metric at geo level (μ).
        mde:                      Minimum detectable effect as proportion of mean.
        n_test_weeks:             Number of test period weeks.
        alpha:                    Two-tailed significance level (0.05 / 0.10 / 0.20).
        target_power:             Desired power (default 0.80).

    Returns:
        PowerResult with power estimate and recommendations.

    Raises:
        ValueError: if inputs are out of valid range.
    """
    if n_geos_per_cell < 1:
        raise ValueError(f"n_geos_per_cell must be >= 1, got {n_geos_per_cell}.")
    if baseline_weekly_variance < 0:
        raise ValueError("baseline_weekly_variance must be >= 0.")
    if baseline_weekly_mean <= 0:
        raise ValueError("baseline_weekly_mean must be > 0.")
    if not 0 < mde < 1:
        raise ValueError(f"mde must be in (0, 1), got {mde}.")
    if n_test_weeks < 1:
        raise ValueError(f"n_test_weeks must be >= 1, got {n_test_weeks}.")
    if alpha not in VALID_ALPHA:
        raise ValueError(f"alpha must be one of {VALID_ALPHA}, got {alpha}.")
    if not 0 < target_power < 1:
        raise ValueError(f"target_power must be in (0, 1), got {target_power}.")

    # Effect size in absolute units
    effect_size = mde * baseline_weekly_mean

    # Standard error of the mean difference between two cells:
    # SE = sqrt(2 * σ² / (n_geos * n_weeks))
    # (pooling variance across n_geos geos, averaged over n_test_weeks)
    se = math.sqrt(2.0 * baseline_weekly_variance / (n_geos_per_cell * n_test_weeks))

    if se == 0:
        power = 1.0 if effect_size > 0 else 0.0
    else:
        # Non-centrality parameter
        ncp = effect_size / se
        # Critical value (two-tailed)
        z_alpha_half = stats.norm.ppf(1 - alpha / 2)
        # Power = P(reject H0 | H1 true)
        power = float(
            stats.norm.sf(z_alpha_half - ncp) + stats.norm.cdf(-z_alpha_half - ncp)
        )

    power = min(max(power, 0.0), 1.0)

    # Compute minimum weeks needed to reach target_power
    required_weeks = _find_required_weeks(
        n_geos_per_cell=n_geos_per_cell,
        baseline_weekly_variance=baseline_weekly_variance,
        baseline_weekly_mean=baseline_weekly_mean,
        mde=mde,
        alpha=alpha,
        target_power=target_power,
    )

    is_adequate = power >= target_power

    warning = None
    if not is_adequate:
        cv = math.sqrt(baseline_weekly_variance) / baseline_weekly_mean
        warning = (
            f"This test is likely underpowered (estimated power: {power:.0%}). "
            f"To achieve {target_power:.0%} power, consider: "
            f"(1) extending the test to at least {required_weeks} weeks, "
            f"(2) increasing geos per cell above {n_geos_per_cell}, or "
            f"(3) increasing spend contrast to amplify the detectable effect. "
            f"Current geo-level CV is {cv:.1%}."
        )

    return PowerResult(
        power=power,
        required_weeks=required_weeks,
        n_geos_per_cell=n_geos_per_cell,
        mde=mde,
        alpha=alpha,
        target_power=target_power,
        is_adequately_powered=is_adequate,
        warning_message=warning,
    )


def _find_required_weeks(
    n_geos_per_cell: int,
    baseline_weekly_variance: float,
    baseline_weekly_mean: float,
    mde: float,
    alpha: float,
    target_power: float,
    max_weeks: int = 52,
) -> int:
    """
    Binary-search for the minimum number of weeks to achieve target_power.
    Returns max_weeks if not achievable within that window.
    """
    effect_size = mde * baseline_weekly_mean
    z_alpha_half = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(target_power)

    if baseline_weekly_variance == 0:
        return 1

    # Analytical formula: n_weeks = 2σ² / (n_geos * δ²) * (z_α/2 + z_β)²
    required = (
        2.0
        * baseline_weekly_variance
        * (z_alpha_half + z_beta) ** 2
        / (n_geos_per_cell * effect_size**2)
    )
    weeks = math.ceil(required)
    return min(weeks, max_weeks)


def estimate_baseline_stats(
    df: "pd.DataFrame",  # noqa: F821
    metric_col: str = "revenue",
    geo_col: str = "geo",
    period_col: str = "week",
) -> tuple[float, float]:
    """
    Estimate baseline mean and variance at the geo-week level.

    Returns:
        (mean, variance) of the metric across all geo × week observations.
    """
    import pandas as pd  # local import to keep module dependency-light for tests

    values = df[metric_col].to_numpy(dtype=float)
    return float(np.mean(values)), float(np.var(values, ddof=1))
