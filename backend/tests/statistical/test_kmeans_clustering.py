"""
Tests for kmeans_clustering.py
"""

import numpy as np
import pandas as pd
import pytest

from app.services.statistical.feature_engineering import (
    compute_geo_features,
    normalize_features,
)
from app.services.statistical.kmeans_clustering import (
    ClusteringOutput,
    run_kmeans_sweep,
    _within_cluster_cv,
    get_cluster_summary,
    MIN_K,
    MAX_K,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_clustered_features(n_per_cluster: int = 10, seed: int = 0) -> pd.DataFrame:
    """
    Create a feature DataFrame in normalized (z-score) space with 3 well-separated clusters.
    Cluster centers are at z = -3, 0, +3 across all features.
    Within-cluster noise is tiny (σ=0.05), so silhouette peaks cleanly at k=3.
    The DataFrame is already in z-score space — no further normalization needed.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for cluster_id, center in enumerate([-3.0, 0.0, 3.0]):
        for i in range(n_per_cluster):
            rows.append(
                {
                    "geo": f"C{cluster_id}_GEO_{i:03d}",
                    "avg_metric": center + rng.normal(0, 0.05),
                    "volatility": center + rng.normal(0, 0.05),
                    "growth_trend": center + rng.normal(0, 0.05),
                    "seasonality_stability": center + rng.normal(0, 0.05),
                    "market_size": center + rng.normal(0, 0.05),
                }
            )
    return pd.DataFrame(rows).set_index("geo")


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_empty_features_raises_value_error():
    df = pd.DataFrame(columns=["avg_metric", "volatility"])
    with pytest.raises(ValueError, match="empty"):
        run_kmeans_sweep(df)


def test_too_few_geos_raises_value_error():
    df = pd.DataFrame(
        {"avg_metric": [1.0], "volatility": [0.1]}, index=["GEO_0"]
    )
    with pytest.raises(ValueError, match="at least"):
        run_kmeans_sweep(df)


# ---------------------------------------------------------------------------
# Output structure
# ---------------------------------------------------------------------------


def test_returns_clustering_output_type():
    features = make_clustered_features()
    output = run_kmeans_sweep(features)
    assert isinstance(output, ClusteringOutput)


def test_results_contains_entry_for_each_k():
    features = make_clustered_features()
    output = run_kmeans_sweep(features, min_k=2, max_k=4)
    k_values = [r.k for r in output.results]
    assert sorted(k_values) == [2, 3, 4]


def test_labels_length_equals_n_geos():
    features = make_clustered_features(n_per_cluster=8)
    output = run_kmeans_sweep(features)
    assert len(output.recommended_labels) == len(features)


def test_labels_contain_valid_cluster_ids():
    features = make_clustered_features()
    output = run_kmeans_sweep(features)
    unique_labels = set(output.recommended_labels)
    assert unique_labels == set(range(output.best_k))


def test_centroids_shape_matches_k_and_features():
    features = make_clustered_features()
    output = run_kmeans_sweep(features)
    for result in output.results:
        assert result.centroids.shape == (result.k, features.shape[1])


# ---------------------------------------------------------------------------
# Silhouette-based k selection
# ---------------------------------------------------------------------------


def test_well_separated_clusters_recommends_correct_k():
    """
    3 well-separated clusters → silhouette should peak at k=3.
    """
    features = make_clustered_features(n_per_cluster=15)
    output = run_kmeans_sweep(features, min_k=2, max_k=5)
    assert output.best_k == 3


def test_silhouette_scores_are_between_neg1_and_1():
    features = make_clustered_features()
    output = run_kmeans_sweep(features)
    for result in output.results:
        assert -1.0 <= result.silhouette <= 1.0


def test_inertia_decreases_as_k_increases():
    """More clusters → lower within-cluster sum of squares (by definition)."""
    features = make_clustered_features()
    output = run_kmeans_sweep(features, min_k=2, max_k=5)
    inertias = [r.inertia for r in sorted(output.results, key=lambda r: r.k)]
    for i in range(len(inertias) - 1):
        assert inertias[i] >= inertias[i + 1]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_results_are_deterministic():
    """Two runs with same data should produce identical labels."""
    features = make_clustered_features(seed=7)
    out1 = run_kmeans_sweep(features)
    out2 = run_kmeans_sweep(features)
    np.testing.assert_array_equal(out1.recommended_labels, out2.recommended_labels)


# ---------------------------------------------------------------------------
# _within_cluster_cv
# ---------------------------------------------------------------------------


def test_within_cluster_cv_zero_variance_cluster():
    values = np.array([100.0, 100.0, 100.0, 200.0, 200.0])
    labels = np.array([0, 0, 0, 1, 1])
    cvs = _within_cluster_cv(values, labels, k=2)
    assert cvs[0] == pytest.approx(0.0, abs=1e-10)


def test_within_cluster_cv_known_value():
    # Cluster 0: [80, 100, 120] → mean=100, std=20, CV=0.2
    values = np.array([80.0, 100.0, 120.0])
    labels = np.array([0, 0, 0])
    cvs = _within_cluster_cv(values, labels, k=1)
    expected_cv = np.std([80, 100, 120], ddof=1) / 100.0
    assert cvs[0] == pytest.approx(expected_cv, rel=1e-6)


# ---------------------------------------------------------------------------
# get_cluster_summary
# ---------------------------------------------------------------------------


def test_cluster_summary_adds_cluster_column():
    features = make_clustered_features(n_per_cluster=5)
    output = run_kmeans_sweep(features)
    summary = get_cluster_summary(features, output.recommended_labels)
    assert "cluster" in summary.columns


def test_cluster_summary_row_count_unchanged():
    features = make_clustered_features(n_per_cluster=5)
    output = run_kmeans_sweep(features)
    summary = get_cluster_summary(features, output.recommended_labels)
    assert len(summary) == len(features)


def test_cluster_summary_does_not_modify_original():
    features = make_clustered_features(n_per_cluster=5)
    output = run_kmeans_sweep(features)
    original_cols = list(features.columns)
    get_cluster_summary(features, output.recommended_labels)
    assert list(features.columns) == original_cols


# ---------------------------------------------------------------------------
# Integration: full pipeline using shared fixture
# ---------------------------------------------------------------------------


def test_full_pipeline_on_positive_effect_dataset(dataset_positive_effect):
    baseline = dataset_positive_effect[dataset_positive_effect["period"] == 0]
    from app.services.statistical.feature_engineering import compute_geo_features, normalize_features

    raw_features = compute_geo_features(baseline, metric_col="revenue")
    normed = normalize_features(raw_features)
    output = run_kmeans_sweep(normed)

    assert output.best_k >= MIN_K
    assert output.best_k <= MAX_K
    assert len(output.recommended_labels) == len(normed)
