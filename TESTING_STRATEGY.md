# Incremental Tool — Testing Strategy

**Version:** 1.0
**Status:** Active — applies to all development phases

---

## Philosophy

Every feature is built test-first or test-alongside. No component is considered complete until its tests pass. The statistical engine, tenant isolation, and async pipeline are the three highest-risk areas and receive the most rigorous coverage.

**Rule:** If it can be wrong, it must be tested.

---

## Testing Layers

### Layer 1 — Statistical Engine (Highest Priority)
### Layer 2 — Data Validation & Ingestion
### Layer 3 — API Endpoints & Auth
### Layer 4 — Tenant Isolation (RLS)
### Layer 5 — Async Job Pipeline
### Layer 6 — LLM Integration
### Layer 7 — Frontend Components
### Layer 8 — End-to-End Workflows

---

## Frameworks & Tools

### Backend (Python / FastAPI)
| Tool | Purpose |
|------|---------|
| `pytest` | Primary test runner |
| `pytest-asyncio` | Async test support |
| `httpx` + FastAPI `TestClient` | API endpoint testing |
| `pytest-cov` | Coverage reporting |
| `factory_boy` | Test data factories (workspaces, users, tests) |
| `numpy` / `pandas` | Synthetic dataset generation for statistical tests |

### Frontend (Next.js / TypeScript)
| Tool | Purpose |
|------|---------|
| `Jest` | Unit and integration test runner |
| `React Testing Library` | Component testing |
| `MSW` (Mock Service Worker) | API mocking in frontend tests |
| `Playwright` | End-to-end browser tests |

### Database
| Tool | Purpose |
|------|---------|
| `pytest` + test schema | RLS policy verification |
| Supabase local dev | Isolated test database |

---

## Layer 1 — Statistical Engine

The most critical layer. Mathematical correctness is non-negotiable. All statistical functions are pure Python functions that take DataFrames and return result objects — they have no side effects and are straightforward to test.

### Approach
Each statistical module has a corresponding test file with:
1. **Known-output tests** — synthetic datasets with pre-calculated correct answers (verified against R's `fixest` package or manual calculation)
2. **Edge case tests** — zero effect, perfect parallel trends, single geo per cell, missing weeks
3. **Direction tests** — positive effect should return positive DiD, negative should return negative
4. **Numerical precision tests** — results within acceptable tolerance (1e-6)

### Test Files
```
backend/
  tests/
    statistical/
      test_feature_engineering.py
      test_kmeans_clustering.py
      test_cell_assignment.py
      test_power_analysis.py
      test_parallel_trends.py
      test_twfe_did.py
      test_simple_did.py
      test_yoy_analysis.py
      test_pretrend_adjustment.py
      test_reconciled_incrementality.py
      test_bootstrap_roas.py
      conftest.py          ← shared synthetic datasets
```

### Synthetic Dataset Strategy
`conftest.py` defines reusable fixtures:

```python
# Known true effect of +15% in test cells
@pytest.fixture
def dataset_positive_effect():
    """50 geos, 12 baseline weeks, 8 test weeks.
    Test cell has a known +15% lift injected.
    TWFE should return β₃ ≈ 0.15 (within 1%)."""

# Known zero effect (should not be falsely significant)
@pytest.fixture
def dataset_null_effect():
    """50 geos, same structure. No lift injected.
    TWFE β₃ should be ≈ 0, p-value should not be < 0.05."""

# Parallel trends violation
@pytest.fixture
def dataset_pretrend_violation():
    """Test cell has a diverging pre-period trend.
    Parallel trends test should flag this."""

# Underpowered test
@pytest.fixture
def dataset_underpowered():
    """Only 4 geos per cell, high variance.
    Power analysis should return < 80% power."""
```

### Critical Tests: TWFE DiD
```python
def test_twfe_positive_effect_detected(dataset_positive_effect):
    result = run_twfe_did(dataset_positive_effect)
    assert abs(result.treatment_effect - 0.15) < 0.01
    assert result.p_value < 0.05
    assert result.ci_90_lower > 0  # CI excludes zero

def test_twfe_null_effect_not_significant(dataset_null_effect):
    result = run_twfe_did(dataset_null_effect)
    assert abs(result.treatment_effect) < 0.05
    assert result.p_value > 0.05

def test_twfe_standard_errors_clustered_at_geo_level(dataset_positive_effect):
    # Clustered SEs should be >= homoskedastic SEs
    result_clustered = run_twfe_did(dataset_positive_effect, cluster=True)
    result_unclustered = run_twfe_did(dataset_positive_effect, cluster=False)
    assert result_clustered.standard_error >= result_unclustered.standard_error

def test_twfe_fixed_effects_absorbed(dataset_positive_effect):
    # Adding a geo-level constant should not change β₃
    result = run_twfe_did(dataset_positive_effect)
    assert result.geo_fixed_effects_count == 50
    assert result.time_fixed_effects_count == 20  # 12 baseline + 8 test weeks
```

### Critical Tests: Bootstrap ROAS CIs
```python
def test_bootstrap_ci_width_increases_with_variance(low_var_dataset, high_var_dataset):
    low_var_result = run_bootstrap_roas(low_var_dataset, n_resamples=1000)
    high_var_result = run_bootstrap_roas(high_var_dataset, n_resamples=1000)
    low_width = low_var_result.ci_95_upper - low_var_result.ci_95_lower
    high_width = high_var_result.ci_95_upper - high_var_result.ci_95_lower
    assert high_width > low_width

def test_bootstrap_roas_mid_between_low_and_high(dataset_positive_effect):
    result = run_bootstrap_roas(dataset_positive_effect, spend=375000, n_resamples=1000)
    assert result.roas_low <= result.roas_mid <= result.roas_high
```

---

## Layer 2 — Data Validation & Ingestion

### What We Test
- Required column presence
- Date format parsing
- Region identifier normalization (state abbreviations, DMA codes, ZIP formats)
- Missing value detection and error messaging
- Duplicate region-period combinations
- Numeric column type enforcement
- Minimum row count validation

### Test File
```
backend/tests/ingestion/
  test_csv_validation.py
  test_column_mapping.py
  test_region_normalization.py
```

### Example Tests
```python
def test_missing_required_column_raises_clear_error():
    df = pd.DataFrame({"region": ["CA"], "metric": [100]})  # missing "period"
    with pytest.raises(ValidationError) as exc:
        validate_upload(df, required_cols=["region", "period", "metric"])
    assert "period" in str(exc.value)
    assert "missing" in str(exc.value).lower()

def test_duplicate_region_period_flagged():
    df = pd.DataFrame({
        "region": ["CA", "CA"],
        "period": ["2024-01-01", "2024-01-01"],
        "metric": [100, 200]
    })
    result = validate_upload(df)
    assert len(result.warnings) > 0
    assert "duplicate" in result.warnings[0].lower()
```

---

## Layer 3 — API Endpoints & Auth

### What We Test
- Every endpoint returns the correct status code for valid input
- Every endpoint returns 401 for unauthenticated requests
- Every endpoint returns 403 when a user attempts to access another workspace's data
- Request validation (missing fields, wrong types) returns 422 with clear messages
- Pagination works correctly on list endpoints

### Test File
```
backend/tests/api/
  test_auth.py
  test_workspaces.py
  test_tests.py
  test_uploads.py
  test_analysis.py
  test_reports.py
```

### Example Tests
```python
def test_unauthenticated_request_returns_401(client):
    response = client.get("/api/tests/")
    assert response.status_code == 401

def test_user_cannot_access_other_workspace_test(client, user_a, user_b, test_in_workspace_b):
    client.authenticate(user_a)
    response = client.get(f"/api/tests/{test_in_workspace_b.id}")
    assert response.status_code == 403

def test_create_test_returns_201_with_id(client, authenticated_user):
    response = client.post("/api/tests/", json={
        "name": "Q1 CTV Test",
        "test_type": "geo_split",
        "channel": "ctv",
        "region_granularity": "state"
    })
    assert response.status_code == 201
    assert "id" in response.json()
```

---

## Layer 4 — Tenant Isolation (RLS)

This layer tests the database directly — bypassing application code — to verify that RLS policies work correctly at the PostgreSQL level.

### What We Test
- A user with workspace_A's JWT cannot SELECT rows from workspace_B
- A user with workspace_A's JWT cannot INSERT into workspace_B
- A user with workspace_A's JWT cannot UPDATE workspace_B rows
- Super Admin (service role key) can access all workspaces
- RLS is enforced on every table that contains workspace data

### Test File
```
backend/tests/security/
  test_rls_policies.py
```

### Example Tests
```python
def test_rls_blocks_cross_workspace_select(db_workspace_a, db_workspace_b, jwt_workspace_a):
    """Connect to DB with workspace_A's JWT and attempt to read workspace_B data."""
    conn = get_db_connection(jwt=jwt_workspace_a)
    result = conn.execute(
        "SELECT * FROM tests WHERE workspace_id = %s",
        [db_workspace_b.id]
    ).fetchall()
    assert len(result) == 0  # RLS returns empty, not an error

def test_rls_allows_own_workspace_select(db_workspace_a, jwt_workspace_a, test_in_workspace_a):
    conn = get_db_connection(jwt=jwt_workspace_a)
    result = conn.execute(
        "SELECT * FROM tests WHERE workspace_id = %s",
        [db_workspace_a.id]
    ).fetchall()
    assert len(result) == 1

def test_service_role_bypasses_rls(db_workspace_a, db_workspace_b, service_role_key):
    conn = get_db_connection(key=service_role_key)
    result = conn.execute("SELECT * FROM tests").fetchall()
    assert len(result) >= 2  # sees both workspaces
```

---

## Layer 5 — Async Job Pipeline

### What We Test
- Job is enqueued when analysis is triggered
- Job status transitions: `pending` → `running` → `completed` / `failed`
- Results are written to DB on completion
- Failed jobs store error details and do not corrupt partial results
- Job is idempotent — re-running the same job produces the same result

### Test File
```
backend/tests/jobs/
  test_job_enqueueing.py
  test_job_execution.py
  test_job_failure_handling.py
```

### Example Tests
```python
async def test_analysis_trigger_enqueues_job(client, authenticated_user, completed_upload):
    response = client.post(f"/api/analysis/run/{completed_upload.test_id}")
    assert response.status_code == 202
    job = await get_latest_job(completed_upload.test_id)
    assert job.status == "pending"

async def test_failed_job_stores_error_without_partial_results(worker, bad_csv_job):
    await worker.run_job(bad_csv_job)
    job = await get_job(bad_csv_job.id)
    assert job.status == "failed"
    assert job.error_message is not None
    result = await get_analysis_result(bad_csv_job.test_id)
    assert result is None  # no partial result stored
```

---

## Layer 6 — LLM Integration

### What We Test
- The correct context is passed to Claude (result values, test metadata)
- Output is stored correctly in `llm_outputs` table
- If Claude API fails, the analysis result is still returned (LLM output is non-blocking)
- Narrative contains expected key metrics from the analysis result

### Test File
```
backend/tests/llm/
  test_narrative_generation.py
  test_llm_failure_graceful_degradation.py
```

### Example Tests
```python
def test_narrative_includes_key_metrics(mock_claude, sample_analysis_result):
    narrative = generate_executive_narrative(sample_analysis_result)
    assert str(round(sample_analysis_result.incremental_revenue)) in narrative
    assert str(round(sample_analysis_result.roas_mid, 2)) in narrative

def test_llm_failure_does_not_block_result(mock_claude_raises_exception, sample_analysis_result):
    result = run_full_pipeline_with_llm(sample_analysis_result)
    assert result.analysis is not None      # analysis result present
    assert result.llm_narrative is None     # narrative absent but not blocking
    assert result.llm_error is not None     # error captured
```

---

## Layer 7 — Frontend Components

### What We Test
- Executive summary card renders correct values from API response
- Collapsible sections open and close correctly
- Charts render without errors given valid data
- Upload form validates file type before submission
- Error states display correctly (failed job, API error)
- Loading states display during async operations

### Test Files
```
frontend/
  __tests__/
    components/
      ExecutiveSummary.test.tsx
      AnalysisDetail.test.tsx
      GeoMap.test.tsx
      UploadForm.test.tsx
      TestList.test.tsx
    pages/
      dashboard.test.tsx
      test-setup.test.tsx
```

### Example Tests
```tsx
test('executive summary displays incremental revenue', () => {
  render(<ExecutiveSummary result={mockResult} />)
  expect(screen.getByText('$483,000')).toBeInTheDocument()
  expect(screen.getByText('1.29x')).toBeInTheDocument()
})

test('analysis detail section is hidden by default', () => {
  render(<AnalysisDetail result={mockResult} />)
  expect(screen.queryByTestId('twfe-table')).not.toBeVisible()
})

test('upload form rejects non-csv files', async () => {
  render(<UploadForm />)
  const file = new File(['data'], 'test.xlsx', { type: 'application/vnd.ms-excel' })
  fireEvent.change(screen.getByLabelText('Upload CSV'), { target: { files: [file] } })
  expect(await screen.findByText(/csv files only/i)).toBeInTheDocument()
})
```

---

## Layer 8 — End-to-End Workflows

Full browser tests using Playwright covering the two critical user journeys.

### Journey 1: Geo Split Test (Practitioner)
1. Log in
2. Create a new test
3. Upload historical CSV
4. Review cluster assignments
5. Configure test cells
6. Review power analysis
7. Download test setup summary
8. Upload post-test CSV
9. Trigger analysis
10. Wait for results
11. View dashboard (executive summary + analysis detail)
12. Download PDF report

### Journey 2: Super Admin
1. Log in as Super Admin
2. View global dashboard (all clients)
3. Enter a client workspace
4. View a completed test result

### Test Files
```
e2e/
  geo-split-test.spec.ts
  pre-post-test.spec.ts
  super-admin.spec.ts
  auth.spec.ts
```

---

## Coverage Targets

| Layer | Target Coverage |
|-------|----------------|
| Statistical engine | 95%+ |
| Data validation | 90%+ |
| API endpoints | 90%+ |
| RLS security | 100% of all tables |
| Async job pipeline | 85%+ |
| LLM integration | 80%+ |
| Frontend components | 80%+ |
| End-to-end | 2 full user journeys |

---

## What "Done" Means

A component is done when:
1. Its feature code is written
2. Its test file is written and all tests pass
3. Coverage meets the target for its layer
4. `pytest --cov` (backend) or `jest --coverage` (frontend) passes in CI

No code is merged without passing tests. No exceptions.

---

## Build Order

Tests are written in this order alongside the code:

1. Statistical engine tests → statistical engine code
2. Data validation tests → validation code
3. RLS policy tests → database schema + RLS policies
4. API tests → API endpoints
5. Job pipeline tests → async worker
6. LLM integration tests → LLM layer
7. Frontend component tests → components
8. End-to-end tests → final integration

---

*This document is authoritative. All contributors follow this strategy.*
