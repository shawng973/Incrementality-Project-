"""
Root-level conftest.py — re-exports all shared fixtures so every test
subdirectory (jobs, llm, api) can use the synthetic statistical datasets
and the API client fixtures.
"""
from tests.statistical.conftest import (  # noqa: F401
    dataset_positive_effect,
    dataset_null_effect,
    dataset_pretrend_violation,
    dataset_clean_pretrend,
    dataset_underpowered,
    dataset_low_variance,
    dataset_high_variance,
    dataset_yoy,
)
from tests.api.conftest import (  # noqa: F401
    anyio_backend,
    test_engine,
    db_session,
    client_a,
    client_b,
    client_super_admin,
    client_unauthenticated,
)
