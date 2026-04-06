"""
K-Means Clustering — geo grouping step.

Evaluates k = 2 through MAX_K, scores each with silhouette coefficient,
recommends the best k, and exposes cluster assignments and diagnostics.

All computation is deterministic (fixed random_state). Pure functions only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

MAX_K = 6
MIN_K = 2
KMEANS_RANDOM_STATE = 42
KMEANS_N_INIT = 20  # more inits → more stable centroids


@dataclass(frozen=True)
class ClusterResult:
    """Outcome for a single value of k."""

    k: int
    labels: np.ndarray                   # shape (n_geos,), dtype int
    silhouette: float                     # higher is better; range [-1, 1]
    inertia: float                        # within-cluster sum of squares
    centroids: np.ndarray                 # shape (k, n_features)
    within_cluster_cv: list[float]        # CV of primary metric per cluster


@dataclass
class ClusteringOutput:
    """Full output from run_kmeans_sweep()."""

    results: list[ClusterResult]          # one per k evaluated
    best_k: int                           # k with highest silhouette score
    recommended_labels: np.ndarray        # labels for best_k
    feature_names: list[str]


def run_kmeans_sweep(
    features_df: pd.DataFrame,
    min_k: int = MIN_K,
    max_k: int = MAX_K,
) -> ClusteringOutput:
    """
    Run K-Means for k = min_k through max_k on normalized feature matrix.
    Select best k by silhouette score.

    Args:
        features_df: Normalized feature DataFrame (geos × features).
                     Must already be z-score normalized.
        min_k:       Minimum number of clusters to evaluate.
        max_k:       Maximum number of clusters to evaluate.

    Returns:
        ClusteringOutput with results for all k and the best recommendation.

    Raises:
        ValueError: if fewer geos than max_k + 1, or empty input.
    """
    if features_df.empty:
        raise ValueError("features_df is empty.")

    n_geos = len(features_df)
    if n_geos < min_k + 1:
        raise ValueError(
            f"Need at least {min_k + 1} geos for clustering with min_k={min_k}, "
            f"got {n_geos}."
        )

    # Cap max_k to avoid more clusters than geos - 1
    effective_max_k = min(max_k, n_geos - 1)

    X = features_df.to_numpy(dtype=float)
    feature_names = list(features_df.columns)

    results: list[ClusterResult] = []

    for k in range(min_k, effective_max_k + 1):
        km = KMeans(
            n_clusters=k,
            n_init=KMEANS_N_INIT,
            random_state=KMEANS_RANDOM_STATE,
        )
        labels = km.fit_predict(X)
        sil = float(silhouette_score(X, labels))
        inertia = float(km.inertia_)

        # Compute within-cluster CV on the first feature (avg_metric proxy)
        # Full CV per cluster uses the raw scale of feature 0
        within_cv = _within_cluster_cv(X[:, 0], labels, k)

        results.append(
            ClusterResult(
                k=k,
                labels=labels,
                silhouette=sil,
                inertia=inertia,
                centroids=km.cluster_centers_.copy(),
                within_cluster_cv=within_cv,
            )
        )

    best = max(results, key=lambda r: r.silhouette)

    return ClusteringOutput(
        results=results,
        best_k=best.k,
        recommended_labels=best.labels,
        feature_names=feature_names,
    )


def _within_cluster_cv(
    values: np.ndarray,
    labels: np.ndarray,
    k: int,
) -> list[float]:
    """
    Compute the Coefficient of Variation (σ/μ) within each cluster
    for a single feature vector.
    """
    cvs: list[float] = []
    for cluster_id in range(k):
        mask = labels == cluster_id
        cluster_vals = values[mask]
        if len(cluster_vals) < 2:
            cvs.append(0.0)
            continue
        mu = float(np.mean(cluster_vals))
        sigma = float(np.std(cluster_vals, ddof=1))
        cvs.append(sigma / mu if mu != 0 else 0.0)
    return cvs


def get_cluster_summary(
    features_df: pd.DataFrame,
    labels: np.ndarray,
) -> pd.DataFrame:
    """
    Return a summary DataFrame with cluster statistics for each geo.

    Args:
        features_df:  Original (non-normalized) feature DataFrame indexed by geo.
        labels:       Integer cluster labels aligned with features_df rows.

    Returns:
        features_df with a 'cluster' column added.
    """
    result = features_df.copy()
    result["cluster"] = labels
    return result
