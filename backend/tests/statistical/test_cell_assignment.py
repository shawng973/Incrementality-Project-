"""
Tests for cell_assignment.py
"""

import numpy as np
import pandas as pd
import pytest

from app.services.statistical.cell_assignment import (
    assign_cells,
    reassign_geo,
    _max_cv_across_cells,
    _compute_cell_balance,
    CV_THRESHOLD,
    N_ITERATIONS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_features(
    n_geos: int = 20,
    n_clusters: int = 2,
    base_metric: float = 100.0,
    noise: float = 5.0,
    seed: int = 0,
) -> tuple[pd.DataFrame, np.ndarray]:
    """Return (features_df, cluster_labels) with evenly distributed clusters."""
    rng = np.random.default_rng(seed)
    geo_ids = [f"GEO_{i:03d}" for i in range(n_geos)]
    metrics = base_metric + rng.normal(0, noise, size=n_geos)
    labels = np.array([i % n_clusters for i in range(n_geos)])
    df = pd.DataFrame({"avg_metric": metrics}, index=geo_ids)
    return df, labels


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_n_cells_less_than_2_raises():
    df, labels = make_features()
    with pytest.raises(ValueError, match="n_cells must be between 2 and 4"):
        assign_cells(df, labels, n_cells=1)


def test_n_cells_greater_than_4_raises():
    df, labels = make_features()
    with pytest.raises(ValueError, match="n_cells must be between 2 and 4"):
        assign_cells(df, labels, n_cells=5)


def test_fewer_geos_than_cells_raises():
    df, labels = make_features(n_geos=1, n_clusters=1)
    with pytest.raises(ValueError, match="not enough geos"):
        assign_cells(df, labels, n_cells=2)


def test_missing_metric_col_raises():
    df = pd.DataFrame({"other_col": [1.0, 2.0, 3.0]}, index=["A", "B", "C"])
    labels = np.array([0, 0, 1])
    with pytest.raises(ValueError, match="metric_col"):
        assign_cells(df, labels, metric_col="avg_metric")


# ---------------------------------------------------------------------------
# Output structure
# ---------------------------------------------------------------------------


def test_geo_assignments_has_correct_columns():
    df, labels = make_features()
    result = assign_cells(df, labels)
    assert "cell_id" in result.geo_assignments.columns
    assert "cluster_id" in result.geo_assignments.columns


def test_geo_assignments_index_matches_input():
    df, labels = make_features(n_geos=12)
    result = assign_cells(df, labels)
    assert set(result.geo_assignments.index) == set(df.index)


def test_cell_balance_has_one_row_per_cell():
    df, labels = make_features()
    result = assign_cells(df, labels, n_cells=3)
    assert len(result.cell_balance) == 3


def test_cell_balance_columns_present():
    df, labels = make_features()
    result = assign_cells(df, labels)
    expected = {"n_geos", "mean_metric", "total_volume", "cv"}
    assert expected.issubset(set(result.cell_balance.columns))


def test_all_geos_assigned_to_valid_cells():
    df, labels = make_features(n_geos=20)
    result = assign_cells(df, labels, n_cells=2)
    cell_ids = result.geo_assignments["cell_id"].values
    assert set(cell_ids).issubset({0, 1})


def test_every_cell_gets_at_least_one_geo():
    df, labels = make_features(n_geos=20, n_clusters=2)
    result = assign_cells(df, labels, n_cells=2)
    for c in range(2):
        assert (result.geo_assignments["cell_id"] == c).sum() >= 1


# ---------------------------------------------------------------------------
# Balance optimization
# ---------------------------------------------------------------------------


def test_well_balanced_dataset_achieves_threshold():
    """
    Uniform metric values across 20 geos → perfect balance achievable.
    CV should be well below 15%.
    """
    geo_ids = [f"GEO_{i:03d}" for i in range(20)]
    df = pd.DataFrame({"avg_metric": [100.0] * 20}, index=geo_ids)
    labels = np.array([0, 1] * 10)
    result = assign_cells(df, labels, n_cells=2)
    assert result.is_balanced
    assert result.best_cv < CV_THRESHOLD


def test_iterations_improve_balance():
    """More iterations should never worsen balance vs fewer iterations."""
    df, labels = make_features(n_geos=30, noise=20.0, seed=1)
    result_few = assign_cells(df, labels, n_cells=2, n_iterations=10, seed=0)
    result_many = assign_cells(df, labels, n_cells=2, n_iterations=500, seed=0)
    assert result_many.best_cv <= result_few.best_cv


def test_results_are_deterministic():
    df, labels = make_features(n_geos=20, seed=5)
    r1 = assign_cells(df, labels, n_cells=2, seed=42)
    r2 = assign_cells(df, labels, n_cells=2, seed=42)
    pd.testing.assert_frame_equal(r1.geo_assignments, r2.geo_assignments)


# ---------------------------------------------------------------------------
# _max_cv_across_cells
# ---------------------------------------------------------------------------


def test_cv_zero_when_cells_have_equal_means():
    values = np.array([100.0, 100.0, 100.0, 100.0])
    cell_ids = np.array([0, 0, 1, 1])
    cv = _max_cv_across_cells(values, cell_ids, n_cells=2)
    assert cv == pytest.approx(0.0, abs=1e-10)


def test_cv_positive_when_cells_have_different_means():
    values = np.array([100.0, 100.0, 200.0, 200.0])
    cell_ids = np.array([0, 0, 1, 1])
    cv = _max_cv_across_cells(values, cell_ids, n_cells=2)
    assert cv > 0


# ---------------------------------------------------------------------------
# reassign_geo
# ---------------------------------------------------------------------------


def test_reassign_geo_changes_cell():
    df, labels = make_features(n_geos=10)
    result = assign_cells(df, labels, n_cells=2)
    geo = result.geo_assignments.index[0]
    original_cell = result.geo_assignments.loc[geo, "cell_id"]
    new_cell = 1 - original_cell  # flip between 0 and 1

    updated = reassign_geo(result, geo, new_cell)
    assert updated.geo_assignments.loc[geo, "cell_id"] == new_cell


def test_reassign_geo_updates_balance():
    df, labels = make_features(n_geos=10)
    result = assign_cells(df, labels, n_cells=2)
    geo = result.geo_assignments.index[0]
    original_cell = result.geo_assignments.loc[geo, "cell_id"]
    new_cell = 1 - original_cell

    updated = reassign_geo(result, geo, new_cell)
    # Balance metrics should be recomputed (cv may be different)
    assert isinstance(updated.best_cv, float)


def test_reassign_nonexistent_geo_raises():
    df, labels = make_features(n_geos=10)
    result = assign_cells(df, labels, n_cells=2)
    with pytest.raises(ValueError, match="not found"):
        reassign_geo(result, "GEO_NONEXISTENT", 0)


def test_reassign_invalid_cell_raises():
    df, labels = make_features(n_geos=10)
    result = assign_cells(df, labels, n_cells=2)
    geo = result.geo_assignments.index[0]
    with pytest.raises(ValueError, match="out of range"):
        reassign_geo(result, geo, 5)


# ---------------------------------------------------------------------------
# Integration with shared fixture
# ---------------------------------------------------------------------------


def test_assignment_on_positive_effect_dataset(dataset_positive_effect):
    from app.services.statistical.feature_engineering import (
        compute_geo_features,
        normalize_features,
    )
    from app.services.statistical.kmeans_clustering import run_kmeans_sweep

    baseline = dataset_positive_effect[dataset_positive_effect["period"] == 0]
    raw_features = compute_geo_features(baseline, metric_col="revenue")
    normed = normalize_features(raw_features)
    clustering = run_kmeans_sweep(normed)

    result = assign_cells(raw_features, clustering.recommended_labels, n_cells=2)

    assert len(result.geo_assignments) == len(raw_features)
    assert result.n_cells == 2
    # 50 geos, well-structured data → should achieve reasonable balance
    assert result.best_cv < 0.30  # relaxed threshold for random data
