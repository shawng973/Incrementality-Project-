"""
Simple Difference-in-Differences — secondary method.

DiD_simple = Δ_TestCell − Δ_Control

where Δ = Avg(Post) − Avg(Baseline) per cell.

Reported alongside TWFE for transparency. This method does not control
for geo or time fixed effects, making it less rigorous but more interpretable.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SimpleDiDResult:
    """Output of run_simple_did()."""

    delta_treatment: float       # Δ for treatment cell (post mean - baseline mean)
    delta_control: float         # Δ for control cell
    did_estimate: float          # delta_treatment - delta_control (proportion)
    did_dollars: float           # did_estimate × avg_baseline_treatment_revenue
    weekly_did: pd.DataFrame     # weekly DiD values (week × did_weekly)


def run_simple_did(
    df: pd.DataFrame,
    treatment_col: str = "is_treatment",
    post_col: str = "period",
    metric_col: str = "revenue",
    time_col: str = "week",
) -> SimpleDiDResult:
    """
    Compute simple mean-comparison DiD.

    Args:
        df:            Panel with baseline and test period rows.
        treatment_col: Binary: 1 = treatment, 0 = control.
        post_col:      Binary: 1 = post period, 0 = baseline.
        metric_col:    Outcome variable.
        time_col:      Time index for weekly breakdown.

    Returns:
        SimpleDiDResult.
    """
    required = {treatment_col, post_col, metric_col, time_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    def cell_mean(treat: int, post: int) -> float:
        mask = (df[treatment_col] == treat) & (df[post_col] == post)
        vals = df.loc[mask, metric_col]
        if len(vals) == 0:
            raise ValueError(f"No observations for treat={treat}, post={post}.")
        return float(vals.mean())

    avg_treat_baseline = cell_mean(1, 0)
    avg_treat_post = cell_mean(1, 1)
    avg_ctrl_baseline = cell_mean(0, 0)
    avg_ctrl_post = cell_mean(0, 1)

    # Normalize by baseline means to get proportional deltas
    delta_treat = (avg_treat_post - avg_treat_baseline) / avg_treat_baseline
    delta_ctrl = (avg_ctrl_post - avg_ctrl_baseline) / avg_ctrl_baseline
    did = delta_treat - delta_ctrl

    did_dollars = did * avg_treat_baseline

    # Weekly DiD: for each test-period week, compare vs baseline mean
    weekly_did = _compute_weekly_did(df, treatment_col, post_col, metric_col, time_col)

    return SimpleDiDResult(
        delta_treatment=delta_treat,
        delta_control=delta_ctrl,
        did_estimate=did,
        did_dollars=did_dollars,
        weekly_did=weekly_did,
    )


def _compute_weekly_did(
    df: pd.DataFrame,
    treatment_col: str,
    post_col: str,
    metric_col: str,
    time_col: str,
) -> pd.DataFrame:
    """Per-week DiD: (treat_week_avg - treat_baseline_avg) - (ctrl_week_avg - ctrl_baseline_avg)."""
    treat_baseline_mean = df.loc[
        (df[treatment_col] == 1) & (df[post_col] == 0), metric_col
    ].mean()
    ctrl_baseline_mean = df.loc[
        (df[treatment_col] == 0) & (df[post_col] == 0), metric_col
    ].mean()

    test_df = df[df[post_col] == 1]
    rows = []
    for week, grp in test_df.groupby(time_col):
        treat_avg = grp.loc[grp[treatment_col] == 1, metric_col].mean()
        ctrl_avg = grp.loc[grp[treatment_col] == 0, metric_col].mean()

        delta_treat = (treat_avg - treat_baseline_mean) / treat_baseline_mean
        delta_ctrl = (ctrl_avg - ctrl_baseline_mean) / ctrl_baseline_mean
        rows.append(
            {
                time_col: week,
                "delta_treatment": delta_treat,
                "delta_control": delta_ctrl,
                "did_weekly": delta_treat - delta_ctrl,
            }
        )
    return pd.DataFrame(rows).set_index(time_col)
