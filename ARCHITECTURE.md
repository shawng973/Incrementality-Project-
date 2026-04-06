# Incremental Tool — Complete Technical Architecture

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLIENT BROWSER                               │
│                   Next.js App (Vercel CDN)                          │
│         React + TypeScript + Recharts + Mapbox/RSM                  │
└─────────────────┬──────────────────────────┬────────────────────────┘
                  │ HTTPS REST               │ Supabase Realtime WS
                  │                          │ (job status updates)
┌─────────────────▼──────────────────────────▼────────────────────────┐
│                     SUPABASE (Managed)                              │
│   ┌──────────────┐   ┌──────────────┐   ┌───────────────────────┐  │
│   │  Auth (JWT)  │   │  PostgreSQL  │   │  Storage (CSV files)  │  │
│   │  + RLS       │   │  + RLS       │   │  + signed URLs        │  │
│   └──────────────┘   └──────────────┘   └───────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                  │                          │
         JWT auth │                 DB reads │ service_role key
                  │                          │
┌─────────────────▼──────────────────────────▼────────────────────────┐
│                   RAILWAY — FastAPI Backend                          │
│                                                                      │
│  ┌─────────────────┐     ┌───────────────────────────────────────┐  │
│  │   FastAPI App   │────▶│  ARQ Job Queue (Redis-backed async)   │  │
│  │  (API process)  │     │  Worker process (same Railway svc)    │  │
│  └─────────────────┘     └───────────────────────────────────────┘  │
│                                    │                                 │
│                          ┌─────────▼──────────┐                     │
│                          │  Statistical Engine │                     │
│                          │  pandas, statsmodels│                     │
│                          │  scikit-learn, scipy│                     │
│                          │  numpy              │                     │
│                          └─────────────────────┘                    │
│                                    │                                 │
│                          ┌─────────▼──────────┐                     │
│                          │   Claude API        │                     │
│                          │   (Anthropic)       │                     │
│                          └─────────────────────┘                    │
└─────────────────────────────────────────────────────────────────────┘
                  │
         ┌────────▼────────┐
         │  Railway Redis  │
         │  (ARQ queue +   │
         │   job state)    │
         └─────────────────┘
```

**Key data flows:**

1. User authenticates via Supabase Auth. The JWT contains `workspace_id` and `role` as custom claims.
2. Browser calls FastAPI with the Supabase JWT in `Authorization: Bearer`. FastAPI verifies it using the Supabase JWT secret.
3. FastAPI writes job records to PostgreSQL (via service_role key, bypassing RLS so the worker can also write results). All other reads enforce RLS via anon/user role.
4. CSV files are uploaded directly from the browser to Supabase Storage using a short-lived signed upload URL obtained from FastAPI. The backend never proxies the file bytes.
5. The worker fetches CSVs from Supabase Storage using a signed download URL, processes them in memory, and writes structured results back to PostgreSQL.
6. Supabase Realtime notifies the browser when the `analysis_jobs` row transitions to `completed` or `failed`.
7. PDF export is rendered server-side by the FastAPI worker (WeasyPrint) and uploaded to Supabase Storage; the browser receives a signed download URL.

---

## 2. Database Schema

All tables live in a single PostgreSQL database managed by Supabase. The `auth.users` table is Supabase-managed. Every application table carries a `workspace_id` that is the primary lever for Row-Level Security.

### RLS Enforcement Strategy

Three Postgres roles are in play:

- `anon` — unauthenticated; no access.
- `authenticated` — maps to every logged-in user; RLS policies consult `auth.jwt() ->> 'workspace_id'` and `auth.jwt() ->> 'app_role'`.
- `service_role` — used by the FastAPI worker; bypasses RLS entirely.

```sql
-- JWT claim helper (set once)
CREATE OR REPLACE FUNCTION public.current_workspace_id()
RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT (auth.jwt() ->> 'workspace_id')::uuid;
$$;

CREATE OR REPLACE FUNCTION public.current_app_role()
RETURNS text LANGUAGE sql STABLE AS $$
  SELECT auth.jwt() ->> 'app_role';
$$;
```

---

### Table: `workspaces`

```sql
CREATE TABLE public.workspaces (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name            text NOT NULL,
    slug            text NOT NULL UNIQUE,          -- URL-safe identifier
    plan            text NOT NULL DEFAULT 'starter' CHECK (plan IN ('starter','growth','enterprise')),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Super Admin sees all; authenticated users see only their own workspace.
ALTER TABLE public.workspaces ENABLE ROW LEVEL SECURITY;

CREATE POLICY "workspace_isolation" ON public.workspaces
    FOR ALL TO authenticated
    USING (
        id = public.current_workspace_id()
        OR public.current_app_role() = 'super_admin'
    );
```

---

### Table: `workspace_users`

Bridges Supabase `auth.users` to workspaces and carries the application role.

```sql
CREATE TABLE public.workspace_users (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    app_role        text NOT NULL CHECK (app_role IN ('super_admin','practitioner','c_suite')),
    display_name    text,
    invited_by      uuid REFERENCES auth.users(id),
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, user_id)
);

CREATE INDEX ON public.workspace_users(workspace_id);
CREATE INDEX ON public.workspace_users(user_id);

ALTER TABLE public.workspace_users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "workspace_users_isolation" ON public.workspace_users
    FOR ALL TO authenticated
    USING (
        workspace_id = public.current_workspace_id()
        OR public.current_app_role() = 'super_admin'
    );
```

A Supabase Auth hook (Database Webhook on `auth.users` insert) or a FastAPI endpoint called after user creation reads `workspace_users` and mints the custom JWT claims `workspace_id` and `app_role` via Supabase's `app_metadata`.

---

### Table: `tests`

```sql
CREATE TABLE public.tests (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id        uuid NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    name                text NOT NULL,
    test_type           text NOT NULL CHECK (test_type IN ('geo_split','pre_post')),
    status              text NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft','geo_assigned','running','results_uploaded','analysis_complete','failed')),
    region_granularity  text NOT NULL CHECK (region_granularity IN ('state','dma','zip_cluster')),

    -- Test window
    test_start_date     date,
    test_end_date       date,
    pre_period_start    date,
    pre_period_end      date,

    -- Geo split config
    num_test_cells      int DEFAULT 1,
    holdout_fraction    numeric(4,3) DEFAULT 0.20,  -- e.g. 0.20 = 20% holdout

    -- Metadata
    advertiser_name     text,
    channel             text,                        -- 'paid_search','paid_social','display', etc.
    kpi_name            text NOT NULL DEFAULT 'revenue',
    currency_code       char(3) DEFAULT 'USD',

    created_by          uuid REFERENCES auth.users(id),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON public.tests(workspace_id);
CREATE INDEX ON public.tests(workspace_id, status);

ALTER TABLE public.tests ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tests_isolation" ON public.tests
    FOR ALL TO authenticated
    USING (
        workspace_id = public.current_workspace_id()
        OR public.current_app_role() = 'super_admin'
    );
```

---

### Table: `csv_uploads`

Tracks every file uploaded to Supabase Storage.

```sql
CREATE TABLE public.csv_uploads (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    test_id         uuid NOT NULL REFERENCES public.tests(id) ON DELETE CASCADE,
    upload_type     text NOT NULL CHECK (upload_type IN ('baseline','results')),
    storage_path    text NOT NULL,           -- path within Supabase Storage bucket
    original_name   text NOT NULL,
    file_size_bytes bigint,
    row_count       int,                     -- populated after validation
    column_map      jsonb,                   -- user's mapping: {geo_col, date_col, kpi_col, spend_col}
    validation_errors jsonb,                 -- array of {row, message} if parse failed
    status          text NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','validated','invalid')),
    uploaded_by     uuid REFERENCES auth.users(id),
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON public.csv_uploads(test_id);

ALTER TABLE public.csv_uploads ENABLE ROW LEVEL SECURITY;

CREATE POLICY "csv_uploads_isolation" ON public.csv_uploads
    FOR ALL TO authenticated
    USING (
        workspace_id = public.current_workspace_id()
        OR public.current_app_role() = 'super_admin'
    );
```

Storage bucket layout:
```
incremental-tool/
  {workspace_id}/
    {test_id}/
      baseline_{upload_id}.csv
      results_{upload_id}.csv
      report_{analysis_job_id}.pdf
```

---

### Table: `geo_regions`

Reference table — static, loaded once from Census/FCC data. Not tenant-isolated (shared lookup).

```sql
CREATE TABLE public.geo_regions (
    id              serial PRIMARY KEY,
    region_type     text NOT NULL CHECK (region_type IN ('state','dma','zip')),
    code            text NOT NULL,           -- FIPS code, DMA code, or ZIP code
    name            text NOT NULL,
    state_code      char(2),
    lat             numeric(9,6),
    lon             numeric(9,6),
    population      int,
    UNIQUE (region_type, code)
);
-- No RLS; this is a public reference table
```

---

### Table: `geo_assignments`

The output of the K-means clustering step.

```sql
CREATE TABLE public.geo_assignments (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    test_id         uuid NOT NULL REFERENCES public.tests(id) ON DELETE CASCADE,
    geo_region_id   int REFERENCES public.geo_regions(id),
    region_code     text NOT NULL,           -- denormalized for query speed
    region_name     text NOT NULL,
    cell_label      text NOT NULL CHECK (cell_label IN ('test','control','excluded')),
    cluster_id      int,                     -- K-means cluster number
    balance_score   numeric(8,6),            -- similarity metric vs control
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON public.geo_assignments(test_id);
CREATE INDEX ON public.geo_assignments(test_id, cell_label);

ALTER TABLE public.geo_assignments ENABLE ROW LEVEL SECURITY;

CREATE POLICY "geo_assignments_isolation" ON public.geo_assignments
    FOR ALL TO authenticated
    USING (
        workspace_id = public.current_workspace_id()
        OR public.current_app_role() = 'super_admin'
    );
```

---

### Table: `analysis_jobs`

One row per statistical computation run.

```sql
CREATE TABLE public.analysis_jobs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    test_id         uuid NOT NULL REFERENCES public.tests(id) ON DELETE CASCADE,
    job_type        text NOT NULL CHECK (job_type IN ('geo_clustering','statistical_analysis','power_analysis','pdf_export')),
    status          text NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued','running','completed','failed')),
    arq_job_id      text,                    -- ARQ internal job ID for polling
    queued_at       timestamptz NOT NULL DEFAULT now(),
    started_at      timestamptz,
    completed_at    timestamptz,
    error_message   text,
    input_snapshot  jsonb,                   -- parameters frozen at queue time
    created_by      uuid REFERENCES auth.users(id)
);

CREATE INDEX ON public.analysis_jobs(test_id, status);
CREATE INDEX ON public.analysis_jobs(workspace_id);

ALTER TABLE public.analysis_jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "analysis_jobs_isolation" ON public.analysis_jobs
    FOR ALL TO authenticated
    USING (
        workspace_id = public.current_workspace_id()
        OR public.current_app_role() = 'super_admin'
    );
```

---

### Table: `analysis_results`

Stores every computed metric as structured JSONB, plus scalar summary fields for efficient queries.

```sql
CREATE TABLE public.analysis_results (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id            uuid NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    test_id                 uuid NOT NULL REFERENCES public.tests(id) ON DELETE CASCADE,
    analysis_job_id         uuid NOT NULL REFERENCES public.analysis_jobs(id) ON DELETE CASCADE,

    -- High-level summary scalars (for list views, C-suite dashboard)
    incremental_revenue     numeric(18,2),
    incremental_revenue_lower_ci numeric(18,2),
    incremental_revenue_upper_ci numeric(18,2),
    roas                    numeric(10,4),
    roas_lower_ci           numeric(10,4),
    roas_upper_ci           numeric(10,4),
    p_value                 numeric(8,6),
    is_significant          boolean,
    confidence_level        numeric(4,3) DEFAULT 0.90,

    -- Full structured output (practitioner view)
    twfe_results            jsonb,   -- coefficients, std errors, t-stats, geo-clustered SE
    parallel_trends         jsonb,   -- pre-period test stats, pass/fail flag
    pre_trend_adjustment    jsonb,   -- adjustment factor, adjusted estimates
    yoy_analysis            jsonb,   -- yoy lift by region
    yoy_did                 jsonb,   -- yoy DiD table
    reconciled_incrementality jsonb, -- midpoint + variance-weighted estimates
    bootstrap_ci            jsonb,   -- ROAS distribution, 1000 resamples
    power_analysis          jsonb,   -- MDE, required n, achieved power
    geo_level_detail        jsonb,   -- per-region contributions

    -- LLM narrative
    llm_narrative           text,
    llm_generated_at        timestamptz,

    -- PDF export
    pdf_storage_path        text,
    pdf_generated_at        timestamptz,

    created_at              timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON public.analysis_results(test_id);

ALTER TABLE public.analysis_results ENABLE ROW LEVEL SECURITY;

CREATE POLICY "analysis_results_isolation" ON public.analysis_results
    FOR ALL TO authenticated
    USING (
        workspace_id = public.current_workspace_id()
        OR public.current_app_role() = 'super_admin'
    );
```

---

### Table: `power_analysis_runs`

Pre-test power analysis is triggered independently before a test launches.

```sql
CREATE TABLE public.power_analysis_runs (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id    uuid NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
    test_id         uuid NOT NULL REFERENCES public.tests(id) ON DELETE CASCADE,
    analysis_job_id uuid REFERENCES public.analysis_jobs(id),
    mde_relative    numeric(6,4),    -- minimum detectable effect (e.g. 0.05 = 5%)
    alpha           numeric(4,3) DEFAULT 0.10,
    achieved_power  numeric(4,3),
    required_geos   int,
    available_geos  int,
    recommendation  text,
    detail          jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.power_analysis_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "power_analysis_isolation" ON public.power_analysis_runs
    FOR ALL TO authenticated
    USING (workspace_id = public.current_workspace_id() OR public.current_app_role() = 'super_admin');
```

---

### Supabase Auth Custom Claims Setup

After Terroir creates a user via the admin API, a Postgres function updates `auth.users.raw_app_meta_data`:

```sql
CREATE OR REPLACE FUNCTION public.set_user_claims(
    p_user_id uuid,
    p_workspace_id uuid,
    p_app_role text
) RETURNS void LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    UPDATE auth.users
    SET raw_app_meta_data = raw_app_meta_data ||
        jsonb_build_object(
            'workspace_id', p_workspace_id::text,
            'app_role', p_app_role
        )
    WHERE id = p_user_id;
END;
$$;
```

Supabase automatically embeds `app_metadata` fields into the JWT, making `workspace_id` and `app_role` available to both RLS policies and the FastAPI JWT decoder.

---

## 3. Async Job Pipeline

### Technology Choice: ARQ (Async Redis Queue)

ARQ is selected over Celery for the following reasons relevant to Railway deployment:

- Pure Python async, compatible with FastAPI's async event loop.
- Single dependency: Redis (Railway has a managed Redis add-on).
- Worker process is the same Docker image as the API — one Railway service with a start command override, not a separate service requiring its own Docker build.
- No Celery broker/backend configuration complexity.
- Supports job retries, timeouts, and cron-style scheduled jobs.

### Infrastructure Layout on Railway

```
Railway Project: incremental-tool
  ├── Service: api          (uvicorn app.main:app)
  ├── Service: worker       (python -m arq app.worker.WorkerSettings)
  └── Service: redis        (Railway managed Redis)
```

Both `api` and `worker` use the same Docker image. The worker service's start command is overridden to `python -m arq app.worker.WorkerSettings`.

### Job Flow (Step by Step)

```
Browser                  FastAPI API             PostgreSQL          Redis              ARQ Worker
  │                          │                       │                 │                    │
  │──POST /analyses ────────▶│                       │                 │                    │
  │                          │──INSERT analysis_jobs─▶│                 │                    │
  │                          │   status='queued'      │                 │                    │
  │                          │──arq.enqueue_job()────────────────────▶│                    │
  │◀─────202 {job_id} ───────│                       │                 │                    │
  │                          │                       │                 │──dequeue──────────▶│
  │                          │                       │                 │                    │──UPDATE status='running'
  │                          │                       │◀───────────────────────────────────── │
  │                          │                       │                 │                    │
  │  [Supabase Realtime WS]  │                       │                 │                    │──run pipeline──▶
  │◀──status='running' ──────────────────────────────│                 │                    │
  │                          │                       │                 │                    │──write results──▶
  │                          │                       │◀───────────────────────────────────── │
  │◀──status='completed' ────────────────────────────│                 │                    │
  │                          │                       │                 │                    │
  │──GET /analyses/{id} ────▶│                       │                 │                    │
  │◀──full results JSON ─────│                       │                 │                    │
```

### ARQ Worker Definition

```python
# app/worker.py (structure only — no file creation)

class WorkerSettings:
    functions = [run_geo_clustering, run_statistical_analysis, run_power_analysis, run_pdf_export]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 4          # parallel jobs per worker instance
    job_timeout = 900     # 15 min max per job
    retry_jobs = True
    max_tries = 2
```

### Job Types and Their Tasks

```
geo_clustering:
  1. Fetch baseline CSV from Supabase Storage (signed URL)
  2. Parse and validate with pandas
  3. Aggregate to region level (sum KPI by region)
  4. Run K-means (scikit-learn) on normalized baseline metrics
  5. Assign test/control/excluded labels
  6. Compute balance score (Euclidean distance of cluster centroids)
  7. Write rows to geo_assignments
  8. Update analysis_jobs status, update tests.status = 'geo_assigned'

statistical_analysis:
  1. Fetch baseline + results CSVs
  2. Merge with geo_assignments
  3. Run full statistical pipeline (see Section 6)
  4. Call Claude API for narrative (see Section 7)
  5. Write to analysis_results
  6. Update analysis_jobs status, tests.status = 'analysis_complete'
  7. Optionally enqueue pdf_export job

power_analysis:
  1. Fetch baseline CSV
  2. Compute variance of KPI across geos
  3. Run power calculation
  4. Write to power_analysis_runs
  5. Update analysis_jobs

pdf_export:
  1. Fetch analysis_results row
  2. Render HTML template (Jinja2 + WeasyPrint)
  3. Upload PDF to Supabase Storage
  4. Update analysis_results.pdf_storage_path
  5. Update analysis_jobs status
```

### Realtime Notification

Supabase Realtime is enabled on `analysis_jobs`. The frontend subscribes to:

```javascript
supabase
  .channel(`job:${jobId}`)
  .on('postgres_changes', {
    event: 'UPDATE',
    schema: 'public',
    table: 'analysis_jobs',
    filter: `id=eq.${jobId}`
  }, handleStatusChange)
  .subscribe()
```

No polling needed. When the worker updates `status` to `completed`, the browser receives the event immediately and fetches the full results.

---

## 4. API Endpoint Map

All endpoints are prefixed `/api/v1`. All endpoints except `/health` require `Authorization: Bearer <supabase_jwt>`. FastAPI middleware decodes the JWT using the Supabase JWT secret and injects a `CurrentUser` dependency with `user_id`, `workspace_id`, and `app_role`.

### Auth & Workspace

```
GET    /health
       Auth: none
       Response: {status: "ok", version: string}

GET    /workspaces
       Auth: super_admin only
       Response: {items: Workspace[], total: int}

GET    /workspaces/{workspace_id}
       Auth: super_admin, or member of that workspace
       Response: Workspace

POST   /workspaces
       Auth: super_admin only
       Body: {name, slug, plan}
       Response: Workspace

PATCH  /workspaces/{workspace_id}
       Auth: super_admin only
       Body: Partial<Workspace>
       Response: Workspace

POST   /workspaces/{workspace_id}/users
       Auth: super_admin only
       Body: {email, app_role, display_name}
       Action: creates Supabase auth user, sets claims, sends invite email
       Response: WorkspaceUser

GET    /workspaces/{workspace_id}/users
       Auth: super_admin, or practitioner in that workspace
       Response: {items: WorkspaceUser[]}

DELETE /workspaces/{workspace_id}/users/{user_id}
       Auth: super_admin only
       Response: 204

GET    /me
       Auth: any
       Response: {user_id, email, display_name, workspace_id, app_role, workspace: Workspace}
```

### Tests

```
GET    /tests
       Auth: any workspace member
       Query: ?status=&test_type=&page=&per_page=
       Response: {items: TestSummary[], total: int}
       Note: RLS scopes to current workspace; c_suite gets same list but fewer fields

POST   /tests
       Auth: practitioner, super_admin
       Body: {
         name, test_type, region_granularity,
         test_start_date, test_end_date,
         pre_period_start, pre_period_end,
         num_test_cells, holdout_fraction,
         advertiser_name, channel, kpi_name, currency_code
       }
       Response: Test (status='draft')

GET    /tests/{test_id}
       Auth: any workspace member
       Response: Test (full detail for practitioner; summary subset for c_suite)

PATCH  /tests/{test_id}
       Auth: practitioner, super_admin
       Body: Partial<Test> (only draft-stage fields)
       Response: Test

DELETE /tests/{test_id}
       Auth: practitioner, super_admin
       Constraint: only if status='draft'
       Response: 204
```

### CSV Uploads

```
POST   /tests/{test_id}/uploads/init
       Auth: practitioner, super_admin
       Body: {upload_type: 'baseline'|'results', filename, file_size_bytes}
       Action: creates csv_uploads row, generates Supabase Storage signed upload URL
       Response: {upload_id, signed_upload_url, storage_path}

POST   /tests/{test_id}/uploads/{upload_id}/confirm
       Auth: practitioner, super_admin
       Action: marks upload complete, triggers async validation job
       Response: {upload_id, status: 'pending'}

GET    /tests/{test_id}/uploads/{upload_id}/status
       Auth: practitioner, super_admin
       Response: {status, row_count, column_map, validation_errors}

POST   /tests/{test_id}/uploads/{upload_id}/column-map
       Auth: practitioner, super_admin
       Body: {geo_col, date_col, kpi_col, spend_col, impression_col?}
       Action: saves mapping, re-triggers validation
       Response: {upload_id, status}

GET    /tests/{test_id}/uploads
       Auth: practitioner, super_admin
       Response: {items: CsvUpload[]}
```

### Geo Clustering

```
POST   /tests/{test_id}/clustering/run
       Auth: practitioner, super_admin
       Body: {num_clusters?, holdout_fraction?, exclude_regions?: string[]}
       Action: enqueues geo_clustering job
       Response: {job_id, status: 'queued'}

GET    /tests/{test_id}/clustering/status
       Auth: any workspace member
       Response: {job_id, status, started_at, completed_at, error_message}

GET    /tests/{test_id}/clustering/results
       Auth: any workspace member
       Response: {
         assignments: GeoAssignment[],    -- [{region_code, region_name, cell_label, cluster_id}]
         balance_metrics: {
           test_baseline_mean, control_baseline_mean,
           balance_score, similarity_pct
         },
         map_data: GeoJSON               -- for Mapbox/RSM rendering
       }

PATCH  /tests/{test_id}/clustering/results
       Auth: practitioner, super_admin
       Body: {overrides: [{region_code, new_cell_label}]}
       Action: allows manual reassignment; recalculates balance_score
       Response: updated balance_metrics

POST   /tests/{test_id}/clustering/approve
       Auth: practitioner, super_admin
       Action: freezes assignments, transitions tests.status to 'running'
       Response: Test
```

### Analysis

```
POST   /tests/{test_id}/analyses
       Auth: practitioner, super_admin
       Body: {confidence_level?: 0.90, bootstrap_n?: 1000, run_power_analysis?: bool}
       Action: enqueues statistical_analysis job
       Response: {job_id, status: 'queued'}

GET    /tests/{test_id}/analyses/latest
       Auth: any workspace member
       Response: AnalysisResult (role-filtered: c_suite gets summary fields only)

GET    /tests/{test_id}/analyses/{analysis_job_id}
       Auth: any workspace member
       Response: AnalysisResult

GET    /tests/{test_id}/analyses/{analysis_job_id}/status
       Auth: any workspace member
       Response: {status, queued_at, started_at, completed_at, error_message}

GET    /tests/{test_id}/analyses/{analysis_job_id}/export/pdf
       Auth: any workspace member
       Action: if PDF exists, returns signed URL; else enqueues pdf_export job
       Response: {pdf_url?, job_id?, status}
```

### Power Analysis

```
POST   /tests/{test_id}/power-analysis
       Auth: practitioner, super_admin
       Body: {mde_relative, alpha?, confidence_level?}
       Action: enqueues power_analysis job
       Response: {job_id, status: 'queued'}

GET    /tests/{test_id}/power-analysis/latest
       Auth: any workspace member
       Response: PowerAnalysisRun
```

### Super Admin

```
GET    /admin/workspaces
       Auth: super_admin
       Response: {items: WorkspaceWithStats[]}   -- includes test counts, user counts

GET    /admin/jobs
       Auth: super_admin
       Query: ?status=&workspace_id=&limit=
       Response: {items: AnalysisJob[]}           -- cross-workspace job monitor

POST   /admin/workspaces/{workspace_id}/impersonate
       Auth: super_admin
       Action: returns a short-lived JWT scoped to that workspace (for support)
       Response: {access_token, expires_at}
```

---

## 5. Frontend Page Map

### Routing Structure

```
/                          → redirect to /dashboard or /login
/login                     → Login page
/dashboard                 → Workspace dashboard (test list)
/tests/new                 → Test creation wizard
/tests/[testId]            → Test detail (tab-based)
  /tests/[testId]/setup    → Test config (dates, channels)
  /tests/[testId]/data     → CSV upload + column mapping
  /tests/[testId]/geo      → Geo clustering + map
  /tests/[testId]/results  → Analysis results
  /tests/[testId]/power    → Power analysis
/admin                     → Super Admin workspace list (super_admin only)
/admin/workspaces/[id]     → Workspace detail + user management
/admin/jobs                → Global job monitor
```

---

### Page: `/login`

Renders: Terroir-branded login form. Email + password only (no social). Uses Supabase Auth `signInWithPassword`. On success, Supabase SDK stores JWT in localStorage; the app reads `workspace_id` and `app_role` from the JWT payload to configure the UI.

API calls: None (Supabase SDK direct).

---

### Page: `/dashboard`

Renders: List of tests for the current workspace. Cards show test name, type, status badge, last updated. Practitioner sees "New Test" button. C-Suite sees read-only list. Super Admin sees a workspace switcher and can view any workspace.

API calls:
- `GET /api/v1/tests?page=1&per_page=20`
- `GET /api/v1/me`

Role behavior: C-Suite sees same list but the "New Test" and "Delete" actions are hidden. Status badges use the same data.

---

### Page: `/tests/new` (Wizard)

A 3-step wizard:

**Step 1 — Test Type & Basic Info**
- Test name, test type (geo_split / pre_post), region granularity
- Channel, advertiser name, KPI name
API calls: None (local state until submit)

**Step 2 — Test Dates**
- Test window (start/end), pre-period window
- Holdout fraction, number of test cells
API calls: None (local state)

**Step 3 — Review & Create**
- Summary of all settings
- "Create Test" button
API calls:
- `POST /api/v1/tests` on submit
- Redirects to `/tests/[testId]/data`

---

### Page: `/tests/[testId]/setup`

Renders: Editable form of all test configuration fields. Save button. Delete button (draft only). Status chip.

API calls:
- `GET /api/v1/tests/{testId}` (on mount)
- `PATCH /api/v1/tests/{testId}` (on save)

---

### Page: `/tests/[testId]/data`

Renders: Two upload panels — "Baseline Data" and "Results Data". Each panel shows: upload button, filename if uploaded, validation status, column mapping UI (dropdowns matching parsed headers to required fields), error list.

Upload flow:
1. User selects file in browser
2. `POST /uploads/init` → get signed URL
3. Browser `PUT` directly to Supabase Storage signed URL (no FastAPI proxy)
4. `POST /uploads/{id}/confirm` → triggers async validation
5. Poll `GET /uploads/{id}/status` every 3s until validated
6. Show column mapping form if `status='validated'`
7. `POST /uploads/{id}/column-map` to save mapping

API calls:
- `GET /api/v1/tests/{testId}/uploads`
- `POST /api/v1/tests/{testId}/uploads/init`
- `POST /api/v1/tests/{testId}/uploads/{uploadId}/confirm`
- `GET /api/v1/tests/{testId}/uploads/{uploadId}/status` (polled)
- `POST /api/v1/tests/{testId}/uploads/{uploadId}/column-map`

---

### Page: `/tests/[testId]/geo`

Renders: Left panel with clustering controls (# clusters, holdout %, exclude list). Right panel with a choropleth map (Mapbox or React Simple Maps) colored by cell assignment (test = orange, control = blue, excluded = grey). Below map: balance metrics table. "Run Clustering" button, "Approve & Lock" button.

Manual override: clicking a region on the map opens a dropdown to reassign it.

Realtime: subscribes to `analysis_jobs` for the clustering job to show a loading spinner.

API calls:
- `GET /api/v1/tests/{testId}/clustering/results` (if exists)
- `POST /api/v1/tests/{testId}/clustering/run`
- `GET /api/v1/tests/{testId}/clustering/status` (polled or via Realtime)
- `PATCH /api/v1/tests/{testId}/clustering/results` (manual overrides)
- `POST /api/v1/tests/{testId}/clustering/approve`

---

### Page: `/tests/[testId]/results`

This is the most complex page. Tab-based layout.

**Tab: Summary** (visible to all roles)
- Incrementality KPI card (revenue + CI)
- ROAS card (with CI)
- Significance badge
- LLM narrative paragraph
- Export PDF button

**Tab: Statistical Detail** (practitioner + super_admin only)
- TWFE regression table (coefficients, std errors, t-stats, p-values)
- Parallel trends chart (pre-period test vs control trend lines via Recharts)
- Pre-trend bias adjustment section (adjustment factor applied)
- Bootstrap ROAS distribution histogram
- Reconciled estimates table (midpoint, variance-weighted)

**Tab: YoY Analysis** (practitioner + super_admin)
- YoY lift table by region
- YoY DiD chart

**Tab: Geo Detail** (practitioner + super_admin)
- Per-region contribution table
- Choropleth map colored by contribution magnitude

**Tab: Power Analysis** (practitioner + super_admin)
- MDE chart, achieved power, recommendation text

Realtime: subscribes to `analysis_jobs` for the analysis job. Shows "Analysis running..." skeleton while job is in progress.

API calls:
- `GET /api/v1/tests/{testId}/analyses/latest`
- `GET /api/v1/tests/{testId}/analyses/{jobId}/status` (or Realtime)
- `POST /api/v1/tests/{testId}/analyses` (trigger re-run)
- `GET /api/v1/tests/{testId}/analyses/{jobId}/export/pdf`

Role gating: C-Suite sees only the Summary tab. The frontend reads `app_role` from the JWT and conditionally renders tabs. This is a UI convenience only — the API also enforces role filtering in the response shape.

---

### Page: `/tests/[testId]/power`

Renders: Form with MDE % input, alpha input. "Run Power Analysis" button. Results section: achieved power gauge chart, required vs available geos bar chart, recommendation text.

API calls:
- `POST /api/v1/tests/{testId}/power-analysis`
- `GET /api/v1/tests/{testId}/power-analysis/latest`
- Realtime subscription for job completion

---

### Page: `/admin` (super_admin only)

Renders: Table of all workspaces with columns: name, plan, # users, # tests, last activity. "New Workspace" button. "Impersonate" button per row.

API calls:
- `GET /api/v1/admin/workspaces`

---

### Page: `/admin/workspaces/[id]`

Renders: Workspace settings form (name, plan). User table (email, role, last login). "Invite User" modal (email, role). "Remove User" button.

API calls:
- `GET /api/v1/workspaces/{id}`
- `GET /api/v1/workspaces/{id}/users`
- `POST /api/v1/workspaces/{id}/users`
- `DELETE /api/v1/workspaces/{id}/users/{userId}`

---

### Page: `/admin/jobs`

Renders: Cross-workspace job monitor. Table with columns: workspace, test name, job type, status, queued at, duration, error. Filter by status, workspace.

API calls:
- `GET /api/v1/admin/jobs?status=&workspace_id=`

---

## 6. Statistical Computation Pipeline

### Input Data Contract

After CSV parsing and column mapping, the worker normalizes both CSVs into a canonical DataFrame:

```
columns: [region_code, date, kpi_value, spend, impressions (optional)]
types:   [str,        date, float64,   float64, float64]
```

The worker merges this with `geo_assignments` to add `cell_label` (test/control) and `cluster_id`.

### Full Pipeline Sequence

```
Step 1: Data Assembly
  - Load baseline CSV (pandas.read_csv via Supabase Storage signed URL)
  - Load results CSV
  - Merge with geo_assignments on region_code
  - Filter to test and control cells only (exclude 'excluded')
  - Validate: no missing dates in test window, no duplicate region+date rows
  - Create panel DataFrame: index = (region_code, date)
  Library: pandas

Step 2: Pre-Period Validation — Parallel Trends Test
  - Subset to pre-period dates
  - Compute weekly KPI trends for test and control groups
  - Run Augmented Dickey-Fuller test for stationarity (statsmodels.tsa.stattools.adfuller)
  - Compute correlation of pre-period trends (numpy.corrcoef)
  - Run F-test for joint pre-period treatment coefficients (see TWFE step)
  - Output: {correlation, f_stat, f_p_value, is_parallel: bool, trend_series: [{date, test_mean, control_mean}]}
  Library: statsmodels, numpy, pandas

Step 3: Pre-Trend Bias Adjustment
  - If parallel trends test fails (p < 0.10), compute adjustment:
    - Fit OLS on pre-period: KPI ~ treatment + date_trend (statsmodels.OLS)
    - Extract pre-period treatment coefficient β_pre
    - Adjustment factor = 1 - (β_pre / control_pre_mean)
    - Apply adjustment to post-period treatment effect estimate
  - Output: {adjustment_applied: bool, adjustment_factor, adjusted_lift}
  Library: statsmodels

Step 4: Two-Way Fixed Effects (TWFE) DiD Regression
  - Full panel regression:
    KPI_it = α_i + λ_t + δ·(Treated_i × Post_t) + ε_it
    where α_i = geo fixed effects, λ_t = time fixed effects
  - Implementation:
    - Demean by geo (within transformation): subtract geo mean from KPI and regressors
    - Demean by time: subtract time mean
    - OLS on demeaned data (statsmodels.OLS)
  - Geo-Clustered Standard Errors:
    - Cluster residuals by geo_region cluster_id (from K-means step)
    - Compute cluster-robust variance-covariance matrix manually:
      V_cluster = (X'X)^-1 · (Σ_g X_g'ε_g·ε_g'X_g) · (X'X)^-1
    - t-statistics and p-values recomputed from clustered SE
  - Output: {did_coefficient, did_se_clustered, did_t_stat, did_p_value,
             n_geos, n_periods, r_squared, fe_coefficients}
  Library: statsmodels, numpy, pandas

Step 5: YoY Analysis
  - Require: baseline has prior-year dates matching the test window structure
  - Compute YoY lift per region: (test_period_kpi / prior_year_kpi) - 1
  - Compute YoY DiD: (test_yoy_lift - control_yoy_lift)
  - Aggregate to test vs control group
  - Output: {yoy_did_lift, yoy_by_region: [{region_code, test_yoy, control_yoy, yoy_did}]}
  Library: pandas

Step 6: Reconciled Incrementality
  - Compute two independent estimates:
    A = TWFE DiD estimate (from Step 4)
    B = YoY DiD estimate (from Step 5)
  - Variance of A: σ²_A = did_se_clustered²
  - Variance of B: compute from bootstrap in Step 7, or use analytical SE if bootstrap not yet run
  - Midpoint estimate: (A + B) / 2
  - Variance-weighted estimate: (A/σ²_A + B/σ²_B) / (1/σ²_A + 1/σ²_B)
  - Output: {twfe_estimate, yoy_estimate, midpoint, variance_weighted, variance_weighted_se}
  Library: numpy

Step 7: Bootstrap Confidence Intervals on ROAS
  - For n=1000 resamples:
    - Resample geo units (cluster-level bootstrap: resample clusters, not individual geos)
    - Re-run TWFE regression on each resample (use demeaned within-estimator for speed)
    - Compute ROAS = (incremental_kpi / total_spend) for each resample
  - From bootstrap distribution:
    - 5th and 95th percentiles → 90% CI
    - 2.5th and 97.5th → 95% CI
    - Store full distribution (histogram bins) for chart rendering
  - Output: {roas_point, roas_lower_90, roas_upper_90, roas_lower_95, roas_upper_95,
             bootstrap_distribution: [{bin_edge, count}]}
  Library: numpy, statsmodels (lightweight OLS in loop)

Step 8: Power Analysis (pre-test, also standalone)
  - Inputs: baseline KPI variance across geos, number of geos, alpha, desired MDE
  - Compute: minimum detectable effect at given power (0.80 default)
    - Use two-sample t-test power formula (scipy.stats.ttest_ind power approximation)
    - Or G-Power equivalent: n = f(σ², α, β, MDE)
  - Sweep: generate power curve over MDE range 1%–50%
  - Output: {mde_pct, achieved_power, required_geos, available_geos, power_curve: [{mde, power}]}
  Library: scipy.stats, numpy

Step 9: Results Serialization
  - Compute scalar summary fields (incremental_revenue, roas, p_value, is_significant)
  - Serialize all structured outputs to JSONB-compatible dicts
  - Write single row to analysis_results via psycopg2 or SQLAlchemy
  - Update analysis_jobs.status = 'completed', analysis_jobs.completed_at = now()
  - Update tests.status = 'analysis_complete'
  Library: psycopg2-binary, SQLAlchemy

Step 10: LLM Narrative Generation (see Section 7)
  - Called after Step 9 writes results
  - Narrative written back to analysis_results.llm_narrative
```

### Python Dependencies (requirements.txt additions)

```
pandas>=2.1
numpy>=1.26
statsmodels>=0.14
scikit-learn>=1.4     # K-means
scipy>=1.12           # power analysis
psycopg2-binary>=2.9
httpx>=0.27           # async Supabase Storage requests
arq>=0.25
redis>=5.0
anthropic>=0.28       # Claude API
weasyprint>=61.0      # PDF export
jinja2>=3.1
```

---

## 7. LLM Integration Architecture

### When Claude Is Called

Claude is called exactly once per `statistical_analysis` job, after all statistical computations are complete (Step 10 in the pipeline). It is not called during clustering, power analysis, or PDF export.

There is no streaming — the worker makes a synchronous `client.messages.create()` call and awaits the full response before writing to the database.

### Context Passed to Claude

The prompt is constructed from a structured context dict that is serialized to JSON and injected into the user turn. No raw CSV data is ever sent to the API.

```
System prompt (static, ~400 tokens):
  "You are an expert marketing analyst interpreting geo split test results for a
   marketing agency report. Write in clear business language. Be precise with numbers.
   Acknowledge uncertainty where it exists. Do not invent numbers not in the data.
   Structure your response as: [1-sentence headline], [3-sentence body], [1-sentence
   recommendation]. Maximum 150 words total."

User turn (dynamic, ~800 tokens):
  {
    "test_name": "...",
    "channel": "Paid Search",
    "kpi_name": "Revenue",
    "test_period": "2025-01-01 to 2025-03-31",
    "test_geos_count": 18,
    "control_geos_count": 24,
    "twfe_did_coefficient": 142500.00,
    "did_p_value": 0.031,
    "is_significant": true,
    "confidence_level": 0.90,
    "roas_point": 3.42,
    "roas_ci_lower": 2.18,
    "roas_ci_upper": 4.89,
    "parallel_trends_passed": true,
    "pre_trend_adjustment_applied": false,
    "reconciled_estimate_variance_weighted": 138200.00,
    "incremental_revenue": 142500.00,
    "incremental_revenue_ci_lower": 89000.00,
    "incremental_revenue_ci_upper": 196000.00
  }
```

### Claude API Call Parameters

```python
model = "claude-sonnet-4-6"
max_tokens = 300
temperature = 0   # deterministic, reproducible narratives
```

### Output Handling

The raw text response is written directly to `analysis_results.llm_narrative`. The `llm_generated_at` timestamp is recorded. No post-processing or parsing is applied to the narrative — it is rendered as plain text in the UI.

### Error Handling

If the Claude API call fails (timeout, rate limit, API error), the worker logs the error but does NOT fail the entire analysis job. The `llm_narrative` field remains null. The frontend checks for null and displays a "Narrative not available" placeholder. A Terroir practitioner can trigger a re-generation by re-running the analysis.

### Retry / Rate Limit Strategy

- The `anthropic` SDK has built-in retry with exponential backoff.
- The worker sets `max_retries=2` on the client.
- If the narrative still fails after retries, the job still completes successfully (partial results are better than no results).

### Cost Control

- Narrative generation: ~1,200 input tokens + 300 output tokens = ~1,500 tokens per analysis run.
- At claude-sonnet-4-6 pricing (~$3/$15 per M tokens), this is approximately $0.0082 per analysis.
- No caching needed at this volume; if usage grows, the static system prompt qualifies for Anthropic prompt caching.

---

## 8. File Storage Architecture

### Supabase Storage Bucket Configuration

```
Bucket name:    incremental-data
Access:         Private (no public URLs)
Allowed MIME:   text/csv, application/pdf
Max file size:  50MB (CSV), 25MB (PDF)
```

### Storage Path Convention

```
{workspace_id}/{test_id}/baseline_{upload_id}.csv
{workspace_id}/{test_id}/results_{upload_id}.csv
{workspace_id}/{test_id}/report_{analysis_job_id}.pdf
```

This path structure means Supabase Storage policies can be written as:

```sql
-- Storage RLS policy (set in Supabase Storage policies UI)
-- Allow authenticated users to read/write only under their workspace_id prefix
CREATE POLICY "workspace_storage_isolation"
ON storage.objects FOR ALL TO authenticated
USING (
    bucket_id = 'incremental-data'
    AND (storage.foldername(name))[1] = (auth.jwt() ->> 'workspace_id')
);
```

This is enforced at the Storage layer — a user with workspace A's JWT cannot generate a valid signed URL for workspace B's path.

### Upload Flow (Browser-Direct, No Proxy)

```
Browser                        FastAPI                    Supabase Storage
   │                              │                              │
   │─POST /uploads/init──────────▶│                              │
   │  {filename, size, type}      │                              │
   │                              │─createSignedUploadUrl()─────▶│
   │                              │  path: {ws}/{test}/file.csv  │
   │◀─{upload_id, signed_url}─────│◀─{signedUrl, token}──────────│
   │                              │                              │
   │─PUT {signed_url}─────────────────────────────────────────▶ │
   │  [raw CSV bytes]             │                              │
   │◀─200 OK───────────────────────────────────────────────────  │
   │                              │                              │
   │─POST /uploads/{id}/confirm──▶│                              │
   │                              │─enqueue validation job───────▶
```

Signed upload URLs expire after 60 seconds. The `init` endpoint and the browser upload must happen within that window. The URL is single-use.

### Backend (Worker) Access Pattern

The ARQ worker uses the Supabase **service_role** key to generate signed download URLs. The service_role key bypasses Storage RLS.

```python
# Worker pseudo-code for fetching a CSV
storage_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
signed = storage_client.storage.from_("incremental-data").create_signed_url(
    path=upload.storage_path,
    expires_in=300  # 5 minutes — enough for download
)
response = httpx.get(signed["signedURL"])
df = pd.read_csv(io.BytesIO(response.content))
```

The service_role key is stored as an environment variable in Railway and is never exposed to the frontend or included in any JWT.

### PDF Export Storage

After WeasyPrint generates the PDF bytes in memory:

```python
pdf_bytes = weasyprint.HTML(string=rendered_html).write_pdf()
path = f"{workspace_id}/{test_id}/report_{job_id}.pdf"
storage_client.storage.from_("incremental-data").upload(
    path=path,
    file=pdf_bytes,
    file_options={"content-type": "application/pdf"}
)
# Update analysis_results.pdf_storage_path = path
```

To serve the PDF to the browser, the API endpoint generates a short-lived signed download URL (expires in 300 seconds) and returns it. The browser navigates to or downloads from that URL directly — FastAPI never proxies the bytes.

### CSV Retention Policy

- Raw CSVs are retained indefinitely in Phase 1 (storage is cheap, clients may re-run analysis).
- A Supabase Storage lifecycle policy should be added in Phase 2 to delete CSVs for tests older than 2 years, or when a workspace is deleted.
- When a workspace is deleted (cascade), a cleanup function should also delete the `{workspace_id}/` prefix from Storage (must be done in application code; Supabase Storage does not auto-delete on DB cascade).

---

## Implementation Sequencing Recommendation

Given this architecture, here is the recommended build order:

**Sprint 1 — Foundation**
Database schema (all tables + RLS policies), Supabase Auth + custom claims setup, FastAPI project skeleton with JWT middleware, workspace + user CRUD endpoints, `/me` endpoint.

**Sprint 2 — Test & Upload**
Test CRUD, CSV upload init/confirm flow, column mapping, async CSV validation job (ARQ + Redis wired up).

**Sprint 3 — Geo Clustering**
K-means pipeline, geo_assignments writes, clustering API endpoints, frontend geo page with map.

**Sprint 4 — Statistical Engine**
Full Steps 1–9 of the computation pipeline, analysis API endpoints, Realtime subscriptions in frontend, results page (practitioner view).

**Sprint 5 — LLM + Export**
Claude narrative integration, WeasyPrint PDF export, C-Suite role-filtered views.

**Sprint 6 — Super Admin + Polish**
Admin pages, impersonation, global job monitor, power analysis standalone page, pre/post test type support.

---

### Critical Files for Implementation

- `/app/worker/pipeline/statistical_analysis.py` — Core statistical computation pipeline (Steps 1–9); all of TWFE, bootstrap, parallel trends, YoY, reconciliation in one module.
- `/app/api/routes/tests.py` — Test CRUD and the analysis trigger endpoints; the primary request/response contract between frontend and backend.
- `/supabase/migrations/001_initial_schema.sql` — All table definitions, RLS policies, and the `set_user_claims` function; the entire multi-tenant security model lives here.
- `/app/worker/tasks.py` — ARQ task definitions (`run_geo_clustering`, `run_statistical_analysis`, `run_power_analysis`, `run_pdf_export`) and `WorkerSettings`; the async job backbone.
- `/src/app/tests/[testId]/results/page.tsx` — The results page with role-filtered tabs, Recharts visualizations, Realtime subscription, and the most complex frontend rendering logic.
