"""Initial schema — all tables from app.models.workspace.

Revision ID: 0001
Revises: —
Create Date: 2026-04-01
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── ENUM types ─────────────────────────────────────────────────────────
    test_status = sa.Enum("draft", "active", "completed", name="teststatus")
    test_type = sa.Enum("geo_split", "pre_post", name="testtype")
    region_granularity = sa.Enum("state", "dma", "zip", name="regiongranularity")
    job_status = sa.Enum("pending", "running", "completed", "failed", name="jobstatus")
    user_role = sa.Enum("super_admin", "practitioner", "c_suite", name="userrole")

    # ── workspaces ─────────────────────────────────────────────────────────
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ── workspace_users ────────────────────────────────────────────────────
    op.create_table(
        "workspace_users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("role", user_role, nullable=False, server_default="practitioner"),
        sa.Column("invited_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("workspace_id", "user_id"),
    )
    op.create_index("idx_workspace_users_workspace_id", "workspace_users", ["workspace_id"])
    op.create_index("idx_workspace_users_user_id", "workspace_users", ["user_id"])

    # ── tests ──────────────────────────────────────────────────────────────
    op.create_table(
        "tests",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("test_type", test_type, nullable=False, server_default="geo_split"),
        sa.Column("status", test_status, nullable=False, server_default="draft"),
        sa.Column("channel", sa.String()),
        sa.Column("region_granularity", region_granularity, nullable=False, server_default="state"),
        sa.Column("primary_metric", sa.String(), nullable=False, server_default="revenue"),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("cooldown_weeks", sa.Integer()),
        sa.Column("n_cells", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_tests_workspace_id", "tests", ["workspace_id"])
    op.create_index("idx_tests_status", "tests", ["status"])

    # ── geo_assignments ────────────────────────────────────────────────────
    op.create_table(
        "geo_assignments",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("test_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("tests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("geo", sa.String(), nullable=False),
        sa.Column("cell_id", sa.Integer(), nullable=False),
        sa.Column("cluster_id", sa.Integer()),
        sa.Column("avg_metric", sa.Float()),
        sa.UniqueConstraint("test_id", "geo"),
    )
    op.create_index("idx_geo_assignments_test_id", "geo_assignments", ["test_id"])
    op.create_index("idx_geo_assignments_workspace_id", "geo_assignments", ["workspace_id"])

    # ── csv_uploads ────────────────────────────────────────────────────────
    op.create_table(
        "csv_uploads",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("test_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("tests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("upload_type", sa.String(), nullable=False),
        sa.Column("storage_path", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("row_count", sa.Integer()),
        sa.Column("geo_count", sa.Integer()),
        sa.Column("period_count", sa.Integer()),
        sa.Column("column_mapping", sa.JSON()),
        sa.Column("validation_warnings", sa.JSON()),
        sa.Column("data_json", sa.Text()),
        sa.Column("uploaded_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_csv_uploads_test_id", "csv_uploads", ["test_id"])
    op.create_index("idx_csv_uploads_workspace_id", "csv_uploads", ["workspace_id"])

    # ── analysis_jobs ──────────────────────────────────────────────────────
    op.create_table(
        "analysis_jobs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("test_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("tests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", job_status, nullable=False, server_default="pending"),
        sa.Column("triggered_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.Column("error_detail", sa.JSON()),
    )
    op.create_index("idx_analysis_jobs_test_id", "analysis_jobs", ["test_id"])
    op.create_index("idx_analysis_jobs_workspace_id", "analysis_jobs", ["workspace_id"])
    op.create_index("idx_analysis_jobs_status", "analysis_jobs", ["status"])

    # ── analysis_results ───────────────────────────────────────────────────
    op.create_table(
        "analysis_results",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("job_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("analysis_jobs.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("test_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("tests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        # Parallel trends
        sa.Column("parallel_trends_passes", sa.Boolean()),
        sa.Column("parallel_trends_p_value", sa.Float()),
        sa.Column("parallel_trends_flag", sa.Text()),
        # TWFE
        sa.Column("twfe_treatment_effect", sa.Float()),
        sa.Column("twfe_treatment_effect_dollars", sa.Float()),
        sa.Column("twfe_p_value", sa.Float()),
        sa.Column("twfe_ci_80", sa.JSON()),
        sa.Column("twfe_ci_90", sa.JSON()),
        sa.Column("twfe_ci_95", sa.JSON()),
        sa.Column("twfe_se", sa.Float()),
        # Simple DiD
        sa.Column("simple_did_estimate", sa.Float()),
        sa.Column("simple_did_dollars", sa.Float()),
        # YoY
        sa.Column("yoy_did_proportion", sa.Float()),
        sa.Column("yoy_did_dollars", sa.Float()),
        # Pre-trend adjustment
        sa.Column("beta_pre", sa.Float()),
        sa.Column("beta_pre_p_value", sa.Float()),
        sa.Column("adjusted_yoy_did_dollars", sa.Float()),
        sa.Column("is_causally_clean", sa.Boolean()),
        # Reconciled
        sa.Column("incremental_revenue_midpoint", sa.Float()),
        sa.Column("incremental_revenue_weighted", sa.Float()),
        # ROAS
        sa.Column("roas_low", sa.Float()),
        sa.Column("roas_mid", sa.Float()),
        sa.Column("roas_high", sa.Float()),
        sa.Column("roas_ci_95", sa.JSON()),
        sa.Column("total_spend", sa.Float()),
        # Raw blobs
        sa.Column("delta_vs_baseline_json", sa.JSON()),
        sa.Column("weekly_did_json", sa.JSON()),
        sa.Column("weekly_yoy_json", sa.JSON()),
        sa.Column("power_analysis_json", sa.JSON()),
        sa.Column("cluster_summary_json", sa.JSON()),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_analysis_results_job_id", "analysis_results", ["job_id"], unique=True)
    op.create_index("idx_analysis_results_test_id", "analysis_results", ["test_id"])
    op.create_index("idx_analysis_results_workspace_id", "analysis_results", ["workspace_id"])


def downgrade() -> None:
    op.drop_table("analysis_results")
    op.drop_table("analysis_jobs")
    op.drop_table("csv_uploads")
    op.drop_table("geo_assignments")
    op.drop_table("tests")
    op.drop_table("workspace_users")
    op.drop_table("workspaces")

    op.execute("DROP TYPE IF EXISTS jobstatus")
    op.execute("DROP TYPE IF EXISTS teststatus")
    op.execute("DROP TYPE IF EXISTS testtype")
    op.execute("DROP TYPE IF EXISTS regiongranularity")
    op.execute("DROP TYPE IF EXISTS userrole")
