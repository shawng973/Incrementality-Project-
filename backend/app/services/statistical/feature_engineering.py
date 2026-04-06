"""
Feature Engineering — pre-test step.

Takes a geo × period panel of historical data and computes per-geo features
used downstream by the K-means clustering step.

All functions are pure: DataFrame in → DataFrame / Series out. No side effects.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass


@dataclass(frozen=True)
class GeoFeatures:
    """Per-geo feature vector produced by compute_geo_features()."""

    geo: str
    avg_metric: float          # mean of primary metric over baseline period
    volatility: float          # coefficient of variation: σ / μ
    growth_trend: float        # linear regression slope (units per period)
    seasonality_stability: float  # peak / trough ratio within baseline
    market_size: float         # total baseline volume


def compute_geo_features(
    df: pd.DataFrame,
    metric_col: str = "revenue",
    geo_col: str = "geo",
    period_col: str = "week",
) -> pd.DataFrame:
    """
    Compute per-geo features from a historical (baseline) panel.

    Args:
        df:          DataFrame with geo × period observations.
                     Should contain ONLY the baseline period rows.
        metric_col:  Column name for the primary metric.
        geo_col:     Column name for geo identifiers.
        period_col:  Column name for the time period (integer index or date).

    Returns:
        DataFrame indexed by geo with columns:
            avg_metric, volatility, growth_trend,
            seasonality_stability, market_size

    Raises:
        ValueError: if required columns are missing or any geo has < 3 observations.
    """
    required = {geo_col, period_col, metric_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    if df.empty:
        raise ValueError("Input DataFrame is empty.")

    results: list[dict] = []

    for geo, group in df.groupby(geo_col, observed=True):
        group = group.sort_values(period_col).reset_index(drop=True)
        values = group[metric_col].to_numpy(dtype=float)
        n = len(values)

        if n < 3:
            raise ValueError(
                f"Geo '{geo}' has only {n} observations; minimum 3 required for "
                "feature computation."
            )

        mu = float(np.mean(values))
        sigma = float(np.std(values, ddof=1))

        avg_metric = mu
        volatility = sigma / mu if mu != 0 else 0.0
        market_size = float(np.sum(values))

        # Growth trend: OLS slope of metric ~ period index
        x = np.arange(n, dtype=float)
        growth_trend = float(_ols_slope(x, values))

        # Seasonality stability: ratio of max to min (robust to scale)
        vmin = float(np.min(values))
        vmax = float(np.max(values))
        seasonality_stability = vmax / vmin if vmin > 0 else float("inf")

        results.append(
            {
                geo_col: geo,
                "avg_metric": avg_metric,
                "volatility": volatility,
                "growth_trend": growth_trend,
                "seasonality_stability": seasonality_stability,
                "market_size": market_size,
            }
        )

    return pd.DataFrame(results).set_index(geo_col)


def _ols_slope(x: np.ndarray, y: np.ndarray) -> float:
    """Return OLS slope of y ~ x (no intercept bias, pure computation)."""
    x_demean = x - x.mean()
    denom = float(np.dot(x_demean, x_demean))
    if denom == 0:
        return 0.0
    return float(np.dot(x_demean, y - y.mean()) / denom)


def normalize_features(features_df: pd.DataFrame) -> pd.DataFrame:
    """
    Z-score normalize all feature columns.

    Returns a DataFrame of the same shape with standardized values.
    Columns with zero variance are set to 0 (no information).
    """
    result = features_df.copy()
    for col in result.columns:
        mu = result[col].mean()
        sigma = result[col].std(ddof=1)
        if sigma == 0:
            result[col] = 0.0
        else:
            result[col] = (result[col] - mu) / sigma
    return result
