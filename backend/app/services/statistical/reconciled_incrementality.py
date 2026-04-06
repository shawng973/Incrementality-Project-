"""
Reconciled Incrementality — triangulates between TWFE DiD and Adjusted YoY DiD.

Standard (midpoint):
    Final_$ = (TWFE_DiD_$ + Adjusted_YoY_$) / 2

Advanced (variance-weighted):
    Final_$ = (TWFE_DiD_$ / Var_TWFE + Adjusted_YoY_$ / Var_YoY)
              / (1/Var_TWFE + 1/Var_YoY)

Both are computed. Midpoint is the headline figure.
Variance-weighted is surfaced in the "Advanced" collapsible section.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReconciledResult:
    """Output of reconcile_incrementality()."""

    twfe_did_dollars: float
    adjusted_yoy_dollars: float
    midpoint_dollars: float           # headline figure
    variance_weighted_dollars: float  # advanced figure
    twfe_variance: float
    yoy_variance: float
    divergence_pct: float             # |midpoint - variance_weighted| / midpoint
    has_large_divergence: bool        # True if divergence > 20%


LARGE_DIVERGENCE_THRESHOLD = 0.20


def reconcile_incrementality(
    twfe_did_dollars: float,
    adjusted_yoy_dollars: float,
    twfe_se: float,
    yoy_se: float,
) -> ReconciledResult:
    """
    Combine TWFE DiD and Adjusted YoY DiD into a reconciled estimate.

    Args:
        twfe_did_dollars:     TWFE DiD estimate in dollars.
        adjusted_yoy_dollars: Adjusted YoY DiD estimate in dollars.
        twfe_se:              Standard error of TWFE estimate (used as variance proxy).
        yoy_se:               Standard error of YoY estimate.

    Returns:
        ReconciledResult with both midpoint and variance-weighted estimates.

    Raises:
        ValueError: if standard errors are negative.
    """
    if twfe_se < 0 or yoy_se < 0:
        raise ValueError("Standard errors must be non-negative.")

    midpoint = (twfe_did_dollars + adjusted_yoy_dollars) / 2.0

    # Variance-weighted: use SE² as variance
    twfe_var = twfe_se**2
    yoy_var = yoy_se**2

    if twfe_var == 0 and yoy_var == 0:
        # Both deterministic — fallback to midpoint
        variance_weighted = midpoint
    elif twfe_var == 0:
        variance_weighted = twfe_did_dollars  # zero variance → trust completely
    elif yoy_var == 0:
        variance_weighted = adjusted_yoy_dollars
    else:
        w_twfe = 1.0 / twfe_var
        w_yoy = 1.0 / yoy_var
        variance_weighted = (twfe_did_dollars * w_twfe + adjusted_yoy_dollars * w_yoy) / (
            w_twfe + w_yoy
        )

    divergence = (
        abs(midpoint - variance_weighted) / abs(midpoint)
        if midpoint != 0
        else 0.0
    )

    return ReconciledResult(
        twfe_did_dollars=twfe_did_dollars,
        adjusted_yoy_dollars=adjusted_yoy_dollars,
        midpoint_dollars=midpoint,
        variance_weighted_dollars=variance_weighted,
        twfe_variance=twfe_var,
        yoy_variance=yoy_var,
        divergence_pct=divergence,
        has_large_divergence=divergence > LARGE_DIVERGENCE_THRESHOLD,
    )
