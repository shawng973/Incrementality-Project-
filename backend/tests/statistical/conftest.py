"""
Shared synthetic dataset fixtures for statistical engine tests.

Design principles:
- All datasets have pre-calculated ground truth so tests can assert exact outcomes.
- Positive-effect datasets inject a known +15% lift into treatment geos.
- Null-effect datasets have no injected signal; DiD should be ≈ 0.
- Panel structure: geo × week, with baseline weeks and test weeks.
- Random seeds are fixed so every test run is deterministic.
"""

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

N_GEOS = 50          # 25 control, 25 treatment
N_BASELINE_WEEKS = 12
N_TEST_WEEKS = 8
TRUE_LIFT = 0.15     # 15% lift injected in treatment test period
BASE_REVENUE = 100_000.0  # $100k/week/geo baseline
GEO_NOISE_SD = 0.10  # ±10% geo-level noise
WEEK_NOISE_SD = 0.05  # ±5% week-level noise
SEED = 42


def _make_panel(
    n_geos: int = N_GEOS,
    n_baseline_weeks: int = N_BASELINE_WEEKS,
    n_test_weeks: int = N_TEST_WEEKS,
    lift: float = 0.0,
    pre_trend_slope: float = 0.0,
    high_variance: bool = False,
    seed: int = SEED,
) -> pd.DataFrame:
    """
    Generate a balanced geo × week panel DataFrame.

    Args:
        n_geos:            Total number of geos (half control, half treatment).
        n_baseline_weeks:  Number of pre-test weeks.
        n_test_weeks:      Number of post-test weeks.
        lift:              True incremental lift to inject into treatment × post cells.
        pre_trend_slope:   Adds a weekly trend differential to treatment geos in the
                           pre-period (simulates parallel-trends violation).
        high_variance:     Inflates geo and week noise 3×.
        seed:              Random seed for reproducibility.

    Returns:
        DataFrame with columns:
            geo, week, period (0=baseline, 1=test), is_treatment,
            revenue, spend
    """
    rng = np.random.default_rng(seed)
    noise_scale = 3.0 if high_variance else 1.0

    n_treatment = n_geos // 2
    n_control = n_geos - n_treatment
    total_weeks = n_baseline_weeks + n_test_weeks

    geo_ids = [f"GEO_{i:03d}" for i in range(n_geos)]
    is_treatment = np.array([1] * n_treatment + [0] * n_control)

    # Fixed geo-level effects (persistent differences between markets)
    geo_effects = rng.normal(0, GEO_NOISE_SD * noise_scale, size=n_geos)

    rows = []
    for g_idx, geo in enumerate(geo_ids):
        treat = is_treatment[g_idx]
        geo_effect = geo_effects[g_idx]

        for w in range(total_weeks):
            is_post = int(w >= n_baseline_weeks)
            week_noise = rng.normal(0, WEEK_NOISE_SD * noise_scale)

            # Pre-trend differential: treatment geos drift upward in baseline
            pre_trend = pre_trend_slope * w * treat * (1 - is_post)

            # Injected lift: only in treatment × post period
            treatment_effect = lift * treat * is_post

            revenue = BASE_REVENUE * (
                1 + geo_effect + week_noise + pre_trend + treatment_effect
            )
            revenue = max(revenue, 0.0)  # no negative revenue

            spend = BASE_REVENUE * 0.20 * treat * is_post  # spend only in treatment, post

            rows.append(
                {
                    "geo": geo,
                    "week": w,
                    "period": is_post,
                    "is_treatment": treat,
                    "revenue": revenue,
                    "spend": spend,
                }
            )

    df = pd.DataFrame(rows)
    df["geo"] = df["geo"].astype("category")
    return df


# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def dataset_positive_effect() -> pd.DataFrame:
    """
    50 geos, 12 baseline weeks, 8 test weeks.
    Treatment cell has a known +15% lift injected.

    Ground truth:
    - TWFE β₃ ≈ 0.15 (within 1%)
    - p-value < 0.05
    - 90% CI lower bound > 0
    """
    return _make_panel(lift=TRUE_LIFT)


@pytest.fixture(scope="session")
def dataset_null_effect() -> pd.DataFrame:
    """
    50 geos, same structure. No lift injected.

    Ground truth:
    - TWFE β₃ ≈ 0 (|β₃| < 0.05)
    - p-value should not be < 0.05 (no false positive)
    """
    return _make_panel(lift=0.0, seed=SEED + 1)


@pytest.fixture(scope="session")
def dataset_pretrend_violation() -> pd.DataFrame:
    """
    Treatment geos have a diverging upward pre-period trend (+2% per week).
    Parallel trends test should flag this (p < 0.10 on interaction).
    """
    return _make_panel(lift=TRUE_LIFT, pre_trend_slope=0.02, seed=SEED + 2)


@pytest.fixture(scope="session")
def dataset_clean_pretrend() -> pd.DataFrame:
    """
    Positive lift but no pre-trend differential.
    Parallel trends test should pass (p > 0.10).
    """
    return _make_panel(lift=TRUE_LIFT, pre_trend_slope=0.0, seed=SEED + 3)


@pytest.fixture(scope="session")
def dataset_underpowered() -> pd.DataFrame:
    """
    Only 8 geos total (4 per cell), high variance.
    Power analysis should return < 80% power at 15% MDE.
    """
    return _make_panel(n_geos=8, high_variance=True, lift=TRUE_LIFT, seed=SEED + 4)


@pytest.fixture(scope="session")
def dataset_low_variance() -> pd.DataFrame:
    """Low-variance dataset for bootstrap CI width comparison."""
    return _make_panel(lift=TRUE_LIFT, high_variance=False, seed=SEED + 5)


@pytest.fixture(scope="session")
def dataset_high_variance() -> pd.DataFrame:
    """High-variance dataset — bootstrap CIs should be wider than low_variance."""
    return _make_panel(lift=TRUE_LIFT, high_variance=True, seed=SEED + 6)


@pytest.fixture(scope="session")
def dataset_yoy() -> pd.DataFrame:
    """
    Panel with prior-year data attached for YoY analysis.
    Returns a dict with 'current' and 'prior_year' DataFrames.
    Uses same lift as positive_effect so YoY DiD should also ≈ 0.15.
    """
    current = _make_panel(lift=TRUE_LIFT, seed=SEED)
    # Prior year: same structure, no lift, slightly different noise
    prior = _make_panel(lift=0.0, seed=SEED + 10)
    prior = prior.rename(columns={"revenue": "revenue_prior", "spend": "spend_prior"})
    merged = current.merge(
        prior[["geo", "week", "revenue_prior"]],
        on=["geo", "week"],
    )
    return merged


# ---------------------------------------------------------------------------
# Scalar helpers used by individual test files
# ---------------------------------------------------------------------------

TOTAL_TEST_PERIOD_SPEND = (
    BASE_REVENUE * 0.20   # spend per treatment geo per week
    * (N_GEOS // 2)       # number of treatment geos
    * N_TEST_WEEKS
)
TRUE_INCREMENTAL_REVENUE = (
    BASE_REVENUE * TRUE_LIFT
    * (N_GEOS // 2)
    * N_TEST_WEEKS
)
TRUE_ROAS_MID = TRUE_INCREMENTAL_REVENUE / TOTAL_TEST_PERIOD_SPEND
