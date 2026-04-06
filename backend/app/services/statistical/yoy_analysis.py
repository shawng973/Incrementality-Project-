"""
Year-over-Year (YoY) Analysis — controls for seasonality.

YoY%_i = (Metric_current_i − Metric_prior_i) / Metric_prior_i × 100

YoY DiD = YoY% of test cell − YoY% of control cell
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class YoYResult:
    """Output of run_yoy_analysis()."""

    yoy_treatment: float          # YoY% for treatment cell (proportion)
    yoy_control: float            # YoY% for control cell
    yoy_did_proportion: float     # yoy_treatment - yoy_control
    yoy_did_dollars: float        # yoy DiD in dollar terms
    weekly_yoy: pd.DataFrame      # week × (yoy_treat, yoy_ctrl, yoy_did)


def run_yoy_analysis(
    df: pd.DataFrame,
    treatment_col: str = "is_treatment",
    post_col: str = "period",
    metric_col: str = "revenue",
    prior_metric_col: str = "revenue_prior",
    time_col: str = "week",
) -> YoYResult:
    """
    Compute YoY DiD.

    Args:
        df:               Panel with current and prior-year metric columns.
                          Must contain both baseline (period=0) and test (period=1) rows.
        treatment_col:    Binary treatment indicator.
        post_col:         Binary post period indicator.
        metric_col:       Current-year outcome column.
        prior_metric_col: Prior-year equivalent period outcome column.
        time_col:         Time index.

    Returns:
        YoYResult.
    """
    required = {treatment_col, post_col, metric_col, prior_metric_col, time_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    test_df = df[df[post_col] == 1].copy()
    if len(test_df) == 0:
        raise ValueError("No test-period observations (post_col == 1).")

    if test_df[prior_metric_col].isna().any():
        raise ValueError(f"'{prior_metric_col}' contains NaN values.")

    def yoy_cell(treat: int) -> float:
        mask = test_df[treatment_col] == treat
        current = test_df.loc[mask, metric_col].mean()
        prior = test_df.loc[mask, prior_metric_col].mean()
        if prior == 0:
            raise ValueError(f"Prior year metric is 0 for treat={treat}; cannot compute YoY.")
        return (current - prior) / prior

    yoy_treat = yoy_cell(1)
    yoy_ctrl = yoy_cell(0)
    yoy_did = yoy_treat - yoy_ctrl

    avg_prior_treat = test_df.loc[test_df[treatment_col] == 1, prior_metric_col].mean()
    yoy_did_dollars = yoy_did * avg_prior_treat

    weekly = _compute_weekly_yoy(test_df, treatment_col, metric_col, prior_metric_col, time_col)

    return YoYResult(
        yoy_treatment=yoy_treat,
        yoy_control=yoy_ctrl,
        yoy_did_proportion=yoy_did,
        yoy_did_dollars=yoy_did_dollars,
        weekly_yoy=weekly,
    )


def _compute_weekly_yoy(
    test_df: pd.DataFrame,
    treatment_col: str,
    metric_col: str,
    prior_metric_col: str,
    time_col: str,
) -> pd.DataFrame:
    rows = []
    for week, grp in test_df.groupby(time_col):
        for treat, label in [(1, "treatment"), (0, "control")]:
            mask = grp[treatment_col] == treat
            current = grp.loc[mask, metric_col].mean()
            prior = grp.loc[mask, prior_metric_col].mean()
            yoy = (current - prior) / prior if prior != 0 else np.nan
            rows.append({time_col: week, "cell": label, "yoy": yoy})

    wide = (
        pd.DataFrame(rows)
        .pivot(index=time_col, columns="cell", values="yoy")
        .rename(columns={"treatment": "yoy_treatment", "control": "yoy_control"})
    )
    wide["yoy_did"] = wide["yoy_treatment"] - wide["yoy_control"]
    return wide
