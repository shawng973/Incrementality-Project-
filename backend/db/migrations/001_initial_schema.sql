-- =============================================================================
-- Migration 001 — Initial Schema
-- Incremental Tool — Multi-Tenant Database
--
-- All tables include workspace_id for tenant isolation.
-- Row Level Security (RLS) policies are defined at the bottom of this file.
-- The Supabase service_role key bypasses RLS; all other JWT-authenticated
-- requests are scoped to their workspace automatically.
-- =============================================================================

-- Enable UUID extension (Supabase provides this by default)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- =============================================================================
-- ENUM TYPES
-- =============================================================================

CREATE TYPE test_status AS ENUM ('draft', 'active', 'completed');
CREATE TYPE test_type AS ENUM ('geo_split', 'pre_post');
CREATE TYPE region_granularity AS ENUM ('state', 'dma', 'zip');
CREATE TYPE job_status AS ENUM ('pending', 'running', 'completed', 'failed');
CREATE TYPE user_role AS ENUM ('super_admin', 'practitioner', 'c_suite');


-- =============================================================================
-- WORKSPACES
-- =============================================================================

CREATE TABLE workspaces (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,    -- URL-safe identifier
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE workspaces IS 'One row per client organization. Created manually by Terroir Super Admin.';


-- =============================================================================
-- WORKSPACE USERS
-- =============================================================================

CREATE TABLE workspace_users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL,          -- Supabase Auth user ID
    role            user_role NOT NULL DEFAULT 'practitioner',
    invited_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, user_id)
);

CREATE INDEX idx_workspace_users_user_id ON workspace_users(user_id);
CREATE INDEX idx_workspace_users_workspace_id ON workspace_users(workspace_id);

COMMENT ON TABLE workspace_users IS 'Links Supabase Auth users to workspaces with a role.';


-- =============================================================================
-- TESTS
-- =============================================================================

CREATE TABLE tests (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id        UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    description         TEXT,
    test_type           test_type NOT NULL DEFAULT 'geo_split',
    status              test_status NOT NULL DEFAULT 'draft',
    channel             TEXT,                   -- e.g., 'paid_search', 'ctv'
    region_granularity  region_granularity NOT NULL DEFAULT 'state',
    primary_metric      TEXT NOT NULL DEFAULT 'revenue',
    start_date          DATE,
    end_date            DATE,
    cooldown_weeks      INT,
    n_cells             INT NOT NULL DEFAULT 2 CHECK (n_cells BETWEEN 2 AND 4),
    created_by          UUID NOT NULL,          -- Supabase Auth user ID
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tests_workspace_id ON tests(workspace_id);
CREATE INDEX idx_tests_status ON tests(status);

COMMENT ON TABLE tests IS 'One row per incrementality test (geo split or pre/post).';


-- =============================================================================
-- GEO ASSIGNMENTS
-- =============================================================================

CREATE TABLE geo_assignments (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    test_id         UUID NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    geo             TEXT NOT NULL,      -- normalized region identifier
    cell_id         INT NOT NULL,       -- 0 = control, 1..n = treatment cells
    cluster_id      INT,                -- K-Means cluster this geo belongs to
    avg_metric      DOUBLE PRECISION,   -- baseline avg metric for reference
    UNIQUE (test_id, geo)
);

CREATE INDEX idx_geo_assignments_test_id ON geo_assignments(test_id);
CREATE INDEX idx_geo_assignments_workspace_id ON geo_assignments(workspace_id);


-- =============================================================================
-- CSV UPLOADS
-- =============================================================================

CREATE TABLE csv_uploads (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    test_id         UUID NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    upload_type     TEXT NOT NULL CHECK (upload_type IN ('historical', 'post_test')),
    storage_path    TEXT NOT NULL,      -- Supabase Storage object path
    filename        TEXT NOT NULL,
    row_count       INT,
    geo_count       INT,
    period_count    INT,
    column_mapping  JSONB,              -- resolved column name mapping
    validation_warnings JSONB,          -- non-blocking validation messages
    uploaded_by     UUID NOT NULL,
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_csv_uploads_test_id ON csv_uploads(test_id);
CREATE INDEX idx_csv_uploads_workspace_id ON csv_uploads(workspace_id);


-- =============================================================================
-- ANALYSIS JOBS
-- =============================================================================

CREATE TABLE analysis_jobs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    test_id         UUID NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    workspace_id    UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    status          job_status NOT NULL DEFAULT 'pending',
    triggered_by    UUID NOT NULL,
    enqueued_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    error_message   TEXT,
    error_detail    JSONB               -- stack trace / debug info
);

CREATE INDEX idx_analysis_jobs_test_id ON analysis_jobs(test_id);
CREATE INDEX idx_analysis_jobs_workspace_id ON analysis_jobs(workspace_id);
CREATE INDEX idx_analysis_jobs_status ON analysis_jobs(status);


-- =============================================================================
-- ANALYSIS RESULTS
-- =============================================================================

CREATE TABLE analysis_results (
    id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id                      UUID NOT NULL REFERENCES analysis_jobs(id) ON DELETE CASCADE,
    test_id                     UUID NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    workspace_id                UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,

    -- Parallel trends
    parallel_trends_passes      BOOLEAN,
    parallel_trends_p_value     DOUBLE PRECISION,
    parallel_trends_flag        TEXT,

    -- TWFE DiD (primary)
    twfe_treatment_effect       DOUBLE PRECISION,   -- proportion
    twfe_treatment_effect_dollars DOUBLE PRECISION,
    twfe_p_value                DOUBLE PRECISION,
    twfe_ci_80                  JSONB,              -- {lower, upper}
    twfe_ci_90                  JSONB,
    twfe_ci_95                  JSONB,
    twfe_se                     DOUBLE PRECISION,

    -- Simple DiD (secondary)
    simple_did_estimate         DOUBLE PRECISION,
    simple_did_dollars          DOUBLE PRECISION,

    -- YoY
    yoy_did_proportion          DOUBLE PRECISION,
    yoy_did_dollars             DOUBLE PRECISION,

    -- Pre-trend adjustment
    beta_pre                    DOUBLE PRECISION,
    beta_pre_p_value            DOUBLE PRECISION,
    adjusted_yoy_did_dollars    DOUBLE PRECISION,
    is_causally_clean           BOOLEAN,

    -- Reconciled incrementality
    incremental_revenue_midpoint    DOUBLE PRECISION,
    incremental_revenue_weighted    DOUBLE PRECISION,

    -- ROAS
    roas_low                    DOUBLE PRECISION,
    roas_mid                    DOUBLE PRECISION,
    roas_high                   DOUBLE PRECISION,
    roas_ci_95                  JSONB,

    -- Spend
    total_spend                 DOUBLE PRECISION,

    -- Raw output blobs (for full result tables)
    delta_vs_baseline_json      JSONB,
    weekly_did_json             JSONB,
    weekly_yoy_json             JSONB,
    power_analysis_json         JSONB,
    cluster_summary_json        JSONB,

    computed_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_analysis_results_job_id ON analysis_results(job_id);
CREATE INDEX idx_analysis_results_test_id ON analysis_results(test_id);
CREATE INDEX idx_analysis_results_workspace_id ON analysis_results(workspace_id);


-- =============================================================================
-- LLM OUTPUTS
-- =============================================================================

CREATE TABLE llm_outputs (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    analysis_result_id  UUID NOT NULL REFERENCES analysis_results(id) ON DELETE CASCADE,
    workspace_id        UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    output_type         TEXT NOT NULL,      -- 'executive_narrative', 'anomaly_flag', etc.
    content             TEXT,               -- generated text
    model               TEXT,               -- e.g., 'claude-sonnet-4-6'
    input_tokens        INT,
    output_tokens       INT,
    error_message       TEXT,               -- non-null if generation failed
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_llm_outputs_result_id ON llm_outputs(analysis_result_id);
CREATE INDEX idx_llm_outputs_workspace_id ON llm_outputs(workspace_id);


-- =============================================================================
-- AUDIT LOG
-- =============================================================================

CREATE TABLE audit_log (
    id              BIGSERIAL PRIMARY KEY,
    workspace_id    UUID REFERENCES workspaces(id) ON DELETE SET NULL,
    user_id         UUID,
    action          TEXT NOT NULL,      -- e.g., 'test.created', 'upload.completed'
    resource_type   TEXT,               -- e.g., 'test', 'upload'
    resource_id     UUID,
    detail          JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_log_workspace_id ON audit_log(workspace_id);
CREATE INDEX idx_audit_log_user_id ON audit_log(user_id);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at);


-- =============================================================================
-- ROW LEVEL SECURITY POLICIES
-- =============================================================================
-- All tables default to DENY. Policies grant access based on workspace_id.
-- The service_role key (used by the backend worker) bypasses RLS entirely.
-- JWT-authenticated requests (Supabase Auth) use the anon/authenticated role.
-- =============================================================================


-- Helper function: extract workspace_id from JWT claims
-- Supabase sets app_metadata.workspace_id on each user's JWT via an Edge Function
-- or server-side RLS helper.
CREATE OR REPLACE FUNCTION auth.workspace_id()
RETURNS UUID AS $$
    SELECT NULLIF(
        current_setting('request.jwt.claims', true)::jsonb -> 'app_metadata' ->> 'workspace_id',
        ''
    )::UUID;
$$ LANGUAGE sql STABLE;


-- Helper: check if current user is super_admin (Terroir operator)
CREATE OR REPLACE FUNCTION auth.is_super_admin()
RETURNS BOOLEAN AS $$
    SELECT COALESCE(
        (current_setting('request.jwt.claims', true)::jsonb -> 'app_metadata' ->> 'role') = 'super_admin',
        false
    );
$$ LANGUAGE sql STABLE;


-- ── workspaces ────────────────────────────────────────────────────────────────
ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY;

CREATE POLICY "workspace_select_own"
    ON workspaces FOR SELECT
    USING (
        id = auth.workspace_id()
        OR auth.is_super_admin()
    );

-- Only service_role can INSERT/UPDATE/DELETE workspaces (via backend, not direct JWT)


-- ── workspace_users ───────────────────────────────────────────────────────────
ALTER TABLE workspace_users ENABLE ROW LEVEL SECURITY;

CREATE POLICY "workspace_users_select_own"
    ON workspace_users FOR SELECT
    USING (
        workspace_id = auth.workspace_id()
        OR auth.is_super_admin()
    );


-- ── tests ─────────────────────────────────────────────────────────────────────
ALTER TABLE tests ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tests_select_own"
    ON tests FOR SELECT
    USING (workspace_id = auth.workspace_id() OR auth.is_super_admin());

CREATE POLICY "tests_insert_own"
    ON tests FOR INSERT
    WITH CHECK (workspace_id = auth.workspace_id());

CREATE POLICY "tests_update_own"
    ON tests FOR UPDATE
    USING (workspace_id = auth.workspace_id())
    WITH CHECK (workspace_id = auth.workspace_id());

CREATE POLICY "tests_delete_own"
    ON tests FOR DELETE
    USING (workspace_id = auth.workspace_id());


-- ── geo_assignments ───────────────────────────────────────────────────────────
ALTER TABLE geo_assignments ENABLE ROW LEVEL SECURITY;

CREATE POLICY "geo_assignments_select_own"
    ON geo_assignments FOR SELECT
    USING (workspace_id = auth.workspace_id() OR auth.is_super_admin());

CREATE POLICY "geo_assignments_insert_own"
    ON geo_assignments FOR INSERT
    WITH CHECK (workspace_id = auth.workspace_id());

CREATE POLICY "geo_assignments_update_own"
    ON geo_assignments FOR UPDATE
    USING (workspace_id = auth.workspace_id())
    WITH CHECK (workspace_id = auth.workspace_id());

CREATE POLICY "geo_assignments_delete_own"
    ON geo_assignments FOR DELETE
    USING (workspace_id = auth.workspace_id());


-- ── csv_uploads ───────────────────────────────────────────────────────────────
ALTER TABLE csv_uploads ENABLE ROW LEVEL SECURITY;

CREATE POLICY "csv_uploads_select_own"
    ON csv_uploads FOR SELECT
    USING (workspace_id = auth.workspace_id() OR auth.is_super_admin());

CREATE POLICY "csv_uploads_insert_own"
    ON csv_uploads FOR INSERT
    WITH CHECK (workspace_id = auth.workspace_id());


-- ── analysis_jobs ─────────────────────────────────────────────────────────────
ALTER TABLE analysis_jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "analysis_jobs_select_own"
    ON analysis_jobs FOR SELECT
    USING (workspace_id = auth.workspace_id() OR auth.is_super_admin());

CREATE POLICY "analysis_jobs_insert_own"
    ON analysis_jobs FOR INSERT
    WITH CHECK (workspace_id = auth.workspace_id());


-- ── analysis_results ──────────────────────────────────────────────────────────
ALTER TABLE analysis_results ENABLE ROW LEVEL SECURITY;

CREATE POLICY "analysis_results_select_own"
    ON analysis_results FOR SELECT
    USING (workspace_id = auth.workspace_id() OR auth.is_super_admin());


-- ── llm_outputs ───────────────────────────────────────────────────────────────
ALTER TABLE llm_outputs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "llm_outputs_select_own"
    ON llm_outputs FOR SELECT
    USING (workspace_id = auth.workspace_id() OR auth.is_super_admin());


-- ── audit_log ─────────────────────────────────────────────────────────────────
-- Audit log is write-only for normal users; only super_admin can read.
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY "audit_log_select_super_admin"
    ON audit_log FOR SELECT
    USING (auth.is_super_admin());

CREATE POLICY "audit_log_insert_own"
    ON audit_log FOR INSERT
    WITH CHECK (
        workspace_id = auth.workspace_id()
        OR auth.is_super_admin()
    );


-- =============================================================================
-- TRIGGERS: updated_at
-- =============================================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_workspaces_updated_at
    BEFORE UPDATE ON workspaces
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_tests_updated_at
    BEFORE UPDATE ON tests
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
