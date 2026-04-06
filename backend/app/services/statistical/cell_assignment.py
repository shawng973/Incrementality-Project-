"""
Stratified Cell Assignment — assigns geos to test cells within each cluster.

Algorithm:
1. Within each K-Means cluster, randomly assign geos to n_cells cells.
2. Evaluate balance by computing the Coefficient of Variation (CV) of the
   primary metric across cells.
3. Repeat N_ITERATIONS times; keep the assignment with the lowest max CV.
4. Report balance metrics: mean metric, total volume, spend, and CV per cell.

All computation is deterministic given a fixed seed. Pure functions only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

N_ITERATIONS = 500
CV_THRESHOLD = 0.15   # warn if best CV > 15%


@dataclass(frozen=True)
class CellAssignmentResult:
    """Output of assign_cells()."""

    geo_assignments: pd.DataFrame  # geo → cell_id, cluster_id, avg_metric
    cell_balance: pd.DataFrame     # cell_id → mean_metric, total_volume, cv
    best_cv: float                 # max CV across cells (minimized metric)
    is_balanced: bool              # True if best_cv < CV_THRESHOLD
    n_cells: int
    n_iterations_run: int


def assign_cells(
    features_df: pd.DataFrame,
    cluster_labels: np.ndarray,
    n_cells: int = 2,
    metric_col: str = "avg_metric",
    n_iterations: int = N_ITERATIONS,
    seed: int = 42,
) -> CellAssignmentResult:
    """
    Stratified random assignment: geos within each cluster are distributed
    across n_cells test cells. Runs n_iterations and returns the configuration
    with the lowest Coefficient of Variation across cells.

    Args:
        features_df:    Feature DataFrame indexed by geo (must include metric_col).
        cluster_labels: Integer cluster labels aligned with features_df rows.
        n_cells:        Number of test cells (2–4).
        metric_col:     Feature column used to evaluate balance.
        n_iterations:   Number of random assignment attempts.
        seed:           Base random seed; iteration seeds are seed + i.

    Returns:
        CellAssignmentResult with geo assignments and balance metrics.

    Raises:
        ValueError: if n_cells < 2, n_cells > 4, or fewer geos than n_cells.
    """
    if n_cells < 2 or n_cells > 4:
        raise ValueError(f"n_cells must be between 2 and 4, got {n_cells}.")

    n_geos = len(features_df)
    if n_geos < n_cells:
        raise ValueError(
            f"Cannot assign {n_geos} geos to {n_cells} cells — not enough geos."
        )

    if metric_col not in features_df.columns:
        raise ValueError(f"metric_col '{metric_col}' not found in features_df.")

    geo_ids = features_df.index.tolist()
    metric_values = features_df[metric_col].to_numpy(dtype=float)
    n_clusters = len(np.unique(cluster_labels))

    best_assignments: Optional[np.ndarray] = None
    best_cv = float("inf")

    for i in range(n_iterations):
        rng = np.random.default_rng(seed + i)
        cell_ids = np.empty(n_geos, dtype=int)

        # Stratified: shuffle within each cluster then assign round-robin
        for cluster_id in range(n_clusters):
            cluster_mask = cluster_labels == cluster_id
            cluster_indices = np.where(cluster_mask)[0]
            shuffled = rng.permutation(cluster_indices)
            for rank, idx in enumerate(shuffled):
                cell_ids[idx] = rank % n_cells

        cv = _max_cv_across_cells(metric_values, cell_ids, n_cells)
        if cv < best_cv:
            best_cv = cv
            best_assignments = cell_ids.copy()

    assert best_assignments is not None  # guaranteed because n_iterations >= 1

    # Build output DataFrames
    geo_df = pd.DataFrame(
        {
            "geo": geo_ids,
            "cell_id": best_assignments,
            "cluster_id": cluster_labels,
            metric_col: metric_values,
        }
    ).set_index("geo")

    balance_df = _compute_cell_balance(metric_values, best_assignments, n_cells)

    return CellAssignmentResult(
        geo_assignments=geo_df,
        cell_balance=balance_df,
        best_cv=best_cv,
        is_balanced=best_cv < CV_THRESHOLD,
        n_cells=n_cells,
        n_iterations_run=n_iterations,
    )


def _max_cv_across_cells(
    metric_values: np.ndarray,
    cell_ids: np.ndarray,
    n_cells: int,
) -> float:
    """
    Compute the maximum Coefficient of Variation of cell means
    as the balance criterion (lower = better).
    """
    cell_means = np.array(
        [metric_values[cell_ids == c].mean() for c in range(n_cells)]
    )
    if cell_means.mean() == 0:
        return 0.0
    return float(np.std(cell_means, ddof=1) / np.mean(cell_means))


def _compute_cell_balance(
    metric_values: np.ndarray,
    cell_ids: np.ndarray,
    n_cells: int,
) -> pd.DataFrame:
    """Return per-cell balance statistics."""
    rows = []
    for c in range(n_cells):
        mask = cell_ids == c
        vals = metric_values[mask]
        mu = float(np.mean(vals))
        sigma = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0
        cv = sigma / mu if mu != 0 else 0.0
        rows.append(
            {
                "cell_id": c,
                "n_geos": int(np.sum(mask)),
                "mean_metric": mu,
                "total_volume": float(np.sum(vals)),
                "cv": cv,
            }
        )
    return pd.DataFrame(rows).set_index("cell_id")


def reassign_geo(
    result: CellAssignmentResult,
    geo: str,
    new_cell_id: int,
) -> CellAssignmentResult:
    """
    Manually reassign a single geo to a different cell and recompute balance.

    This supports the UI's manual override feature without re-running the
    full 500-iteration search.
    """
    if geo not in result.geo_assignments.index:
        raise ValueError(f"Geo '{geo}' not found in current assignments.")

    if new_cell_id < 0 or new_cell_id >= result.n_cells:
        raise ValueError(
            f"new_cell_id {new_cell_id} is out of range for {result.n_cells} cells."
        )

    updated = result.geo_assignments.copy()
    updated.loc[geo, "cell_id"] = new_cell_id

    metric_col = [c for c in updated.columns if c not in ("cell_id", "cluster_id")][0]
    metric_values = updated[metric_col].to_numpy(dtype=float)
    cell_ids = updated["cell_id"].to_numpy(dtype=int)

    new_cv = _max_cv_across_cells(metric_values, cell_ids, result.n_cells)
    balance_df = _compute_cell_balance(metric_values, cell_ids, result.n_cells)

    return CellAssignmentResult(
        geo_assignments=updated,
        cell_balance=balance_df,
        best_cv=new_cv,
        is_balanced=new_cv < CV_THRESHOLD,
        n_cells=result.n_cells,
        n_iterations_run=result.n_iterations_run,
    )
