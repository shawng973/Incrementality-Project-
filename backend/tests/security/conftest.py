"""
RLS test fixtures.

These tests require a running PostgreSQL instance (Supabase local dev).
They are skipped automatically if SUPABASE_TEST_DATABASE_URL is not set.

To run locally:
    1. Start Supabase: `supabase start`
    2. Run migrations: `supabase db reset`
    3. Export: export SUPABASE_TEST_DATABASE_URL="postgresql://postgres:postgres@localhost:54322/postgres"
    4. Run: pytest tests/security/ -v

The tests use raw psycopg2 connections (not SQLAlchemy) to directly set
the JWT claims context variable and verify RLS enforcement.
"""

import os
import uuid
import json
import pytest


# Skip all security tests if the test database is not available
REQUIRES_DB = pytest.mark.skipif(
    not os.getenv("SUPABASE_TEST_DATABASE_URL"),
    reason="SUPABASE_TEST_DATABASE_URL not set — skipping RLS tests (requires Supabase local dev)",
)


def _get_connection(database_url: str, workspace_id: str | None = None, is_super_admin: bool = False):
    """
    Return a psycopg2 connection with JWT claims set.

    Simulates what Supabase does when an authenticated request arrives:
    - Sets request.jwt.claims with app_metadata.workspace_id
    - Optionally sets role = 'super_admin'
    """
    try:
        import psycopg2
    except ImportError:
        pytest.skip("psycopg2 not installed")

    conn = psycopg2.connect(database_url)
    conn.autocommit = False
    cur = conn.cursor()

    # Build JWT claims context
    claims: dict = {"app_metadata": {}}
    if workspace_id:
        claims["app_metadata"]["workspace_id"] = str(workspace_id)
    if is_super_admin:
        claims["app_metadata"]["role"] = "super_admin"

    # Set the GUC that Supabase/PostgREST uses for RLS
    cur.execute(
        "SELECT set_config('request.jwt.claims', %s, true)",
        [json.dumps(claims)],
    )
    # Switch to the authenticated role (not service_role)
    cur.execute("SET ROLE authenticated")
    cur.close()
    return conn


@pytest.fixture(scope="session")
def db_url():
    url = os.getenv("SUPABASE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("SUPABASE_TEST_DATABASE_URL not set")
    return url


@pytest.fixture(scope="session")
def workspace_a_id(db_url):
    """Create workspace A and return its UUID. Cleaned up after session."""
    import psycopg2

    wid = uuid.uuid4()
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO workspaces (id, name, slug) VALUES (%s, %s, %s)",
            [str(wid), "Test Workspace A", f"test-workspace-a-{wid.hex[:8]}"],
        )
    conn.close()
    yield wid
    # Cleanup
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DELETE FROM workspaces WHERE id = %s", [str(wid)])
    conn.close()


@pytest.fixture(scope="session")
def workspace_b_id(db_url):
    """Create workspace B."""
    import psycopg2

    wid = uuid.uuid4()
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO workspaces (id, name, slug) VALUES (%s, %s, %s)",
            [str(wid), "Test Workspace B", f"test-workspace-b-{wid.hex[:8]}"],
        )
    conn.close()
    yield wid
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DELETE FROM workspaces WHERE id = %s", [str(wid)])
    conn.close()


@pytest.fixture(scope="session")
def test_in_workspace_a(db_url, workspace_a_id):
    """Insert a test row in workspace A."""
    import psycopg2

    tid = uuid.uuid4()
    user_id = uuid.uuid4()
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tests (id, workspace_id, name, primary_metric, created_by)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [str(tid), str(workspace_a_id), "RLS Test A", "revenue", str(user_id)],
        )
    conn.close()
    yield tid
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DELETE FROM tests WHERE id = %s", [str(tid)])
    conn.close()


@pytest.fixture(scope="session")
def test_in_workspace_b(db_url, workspace_b_id):
    """Insert a test row in workspace B."""
    import psycopg2

    tid = uuid.uuid4()
    user_id = uuid.uuid4()
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tests (id, workspace_id, name, primary_metric, created_by)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [str(tid), str(workspace_b_id), "RLS Test B", "revenue", str(user_id)],
        )
    conn.close()
    yield tid
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DELETE FROM tests WHERE id = %s", [str(tid)])
    conn.close()


def get_conn_for_workspace(db_url: str, workspace_id) -> "psycopg2.connection":  # noqa: F821
    return _get_connection(db_url, workspace_id=str(workspace_id))


def get_super_admin_conn(db_url: str) -> "psycopg2.connection":  # noqa: F821
    return _get_connection(db_url, is_super_admin=True)
