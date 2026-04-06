"""
RLS Policy Tests — Layer 4 (Security).

These tests bypass all application code and connect directly to PostgreSQL,
setting JWT claims to simulate authenticated requests from different workspaces.

All tests are auto-skipped unless SUPABASE_TEST_DATABASE_URL is set.
Run with: pytest tests/security/ -v

Core principle: RLS returns empty sets for cross-workspace queries
(it does NOT raise errors — it silently filters). This is by PostgreSQL design.
"""

import uuid
import pytest

from tests.security.conftest import (
    REQUIRES_DB,
    get_conn_for_workspace,
    get_super_admin_conn,
)


# =============================================================================
# tests TABLE
# =============================================================================


@REQUIRES_DB
def test_rls_blocks_cross_workspace_select_on_tests(
    db_url, workspace_a_id, workspace_b_id, test_in_workspace_a, test_in_workspace_b
):
    """
    User with workspace_A JWT cannot see workspace_B tests.
    RLS returns empty result (not an error).
    """
    conn = get_conn_for_workspace(db_url, workspace_a_id)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM tests WHERE workspace_id = %s",
                [str(workspace_b_id)],
            )
            rows = cur.fetchall()
        assert len(rows) == 0, "RLS should block cross-workspace SELECT on tests"
    finally:
        conn.rollback()
        conn.close()


@REQUIRES_DB
def test_rls_allows_own_workspace_select_on_tests(
    db_url, workspace_a_id, test_in_workspace_a
):
    """User with workspace_A JWT can see their own tests."""
    conn = get_conn_for_workspace(db_url, workspace_a_id)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM tests WHERE workspace_id = %s",
                [str(workspace_a_id)],
            )
            rows = cur.fetchall()
        assert len(rows) >= 1, "RLS should allow own workspace SELECT on tests"
    finally:
        conn.rollback()
        conn.close()


@REQUIRES_DB
def test_rls_blocks_cross_workspace_insert_on_tests(
    db_url, workspace_b_id
):
    """
    User with workspace_A JWT cannot INSERT a test into workspace_B.
    RLS raises a permission error on INSERT WITH CHECK violations.
    """
    workspace_a_id = uuid.uuid4()  # a fresh workspace not in the DB
    conn = get_conn_for_workspace(db_url, workspace_a_id)
    try:
        with conn.cursor() as cur:
            with pytest.raises(Exception, match="new row violates row-level security"):
                cur.execute(
                    """
                    INSERT INTO tests (workspace_id, name, primary_metric, created_by)
                    VALUES (%s, %s, %s, %s)
                    """,
                    [str(workspace_b_id), "Injected Test", "revenue", str(uuid.uuid4())],
                )
    finally:
        conn.rollback()
        conn.close()


@REQUIRES_DB
def test_rls_blocks_cross_workspace_update_on_tests(
    db_url, workspace_a_id, workspace_b_id, test_in_workspace_b
):
    """User with workspace_A JWT cannot UPDATE workspace_B tests."""
    conn = get_conn_for_workspace(db_url, workspace_a_id)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE tests SET name = 'HIJACKED' WHERE id = %s",
                [str(test_in_workspace_b)],
            )
            # UPDATE should affect 0 rows (RLS hides workspace_B rows)
            assert cur.rowcount == 0
    finally:
        conn.rollback()
        conn.close()


@REQUIRES_DB
def test_rls_blocks_cross_workspace_delete_on_tests(
    db_url, workspace_a_id, test_in_workspace_b
):
    """User with workspace_A JWT cannot DELETE workspace_B tests."""
    conn = get_conn_for_workspace(db_url, workspace_a_id)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM tests WHERE id = %s",
                [str(test_in_workspace_b)],
            )
            assert cur.rowcount == 0
    finally:
        conn.rollback()
        conn.close()


# =============================================================================
# workspaces TABLE
# =============================================================================


@REQUIRES_DB
def test_rls_blocks_cross_workspace_select_on_workspaces(
    db_url, workspace_a_id, workspace_b_id
):
    """User with workspace_A JWT cannot see workspace_B's workspace record."""
    conn = get_conn_for_workspace(db_url, workspace_a_id)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM workspaces WHERE id = %s",
                [str(workspace_b_id)],
            )
            rows = cur.fetchall()
        assert len(rows) == 0
    finally:
        conn.rollback()
        conn.close()


@REQUIRES_DB
def test_rls_allows_own_workspace_select_on_workspaces(
    db_url, workspace_a_id
):
    """User can see their own workspace record."""
    conn = get_conn_for_workspace(db_url, workspace_a_id)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM workspaces WHERE id = %s",
                [str(workspace_a_id)],
            )
            rows = cur.fetchall()
        assert len(rows) == 1
    finally:
        conn.rollback()
        conn.close()


# =============================================================================
# Super Admin
# =============================================================================


@REQUIRES_DB
def test_super_admin_can_select_all_tests(
    db_url, workspace_a_id, workspace_b_id,
    test_in_workspace_a, test_in_workspace_b
):
    """Super Admin JWT sees all workspaces."""
    conn = get_super_admin_conn(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM tests WHERE workspace_id IN (%s, %s)",
                        [str(workspace_a_id), str(workspace_b_id)])
            rows = cur.fetchall()
        assert len(rows) >= 2
    finally:
        conn.rollback()
        conn.close()


@REQUIRES_DB
def test_super_admin_can_select_all_workspaces(
    db_url, workspace_a_id, workspace_b_id
):
    """Super Admin can see multiple workspaces in a single query."""
    conn = get_super_admin_conn(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM workspaces WHERE id IN (%s, %s)",
                [str(workspace_a_id), str(workspace_b_id)],
            )
            rows = cur.fetchall()
        assert len(rows) == 2
    finally:
        conn.rollback()
        conn.close()


# =============================================================================
# No JWT (unauthenticated)
# =============================================================================


@REQUIRES_DB
def test_no_jwt_cannot_select_tests(db_url, workspace_a_id, test_in_workspace_a):
    """Request with no workspace_id in claims sees no tests."""
    import psycopg2, json
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    with conn.cursor() as cur:
        cur.execute(
            "SELECT set_config('request.jwt.claims', %s, true)",
            [json.dumps({})],
        )
        cur.execute("SET ROLE authenticated")
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM tests WHERE workspace_id = %s",
                [str(workspace_a_id)],
            )
            rows = cur.fetchall()
        assert len(rows) == 0
    finally:
        conn.rollback()
        conn.close()


# =============================================================================
# RLS coverage check: verify RLS is enabled on all tables
# =============================================================================


@REQUIRES_DB
def test_rls_enabled_on_all_workspace_tables(db_url):
    """
    Verify that every table containing workspace data has RLS enabled.
    This is the '100% of all tables' coverage requirement.
    """
    import psycopg2

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    tables_requiring_rls = [
        "workspaces",
        "workspace_users",
        "tests",
        "geo_assignments",
        "csv_uploads",
        "analysis_jobs",
        "analysis_results",
        "llm_outputs",
        "audit_log",
    ]
    with conn.cursor() as cur:
        for table in tables_requiring_rls:
            cur.execute(
                """
                SELECT relrowsecurity
                FROM pg_class
                WHERE relname = %s
                """,
                [table],
            )
            row = cur.fetchone()
            assert row is not None, f"Table '{table}' not found in pg_class"
            assert row[0] is True, f"RLS is NOT enabled on table '{table}'"
    conn.close()
