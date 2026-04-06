"""
API test fixtures.

Uses FastAPI TestClient with:
- Per-request JWT tokens (signed with TEST_JWT_SECRET) so concurrent clients
  don't interfere with each other's auth state.
- In-memory SQLite database via SQLAlchemy for speed and isolation.
- get_db overridden with a shared in-memory session within each test function.
"""
from __future__ import annotations

import os
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.workspace import Workspace, Test  # noqa: F401 — registers models

# ---------------------------------------------------------------------------
# Fixed test JWT secret — set before importing auth module
# ---------------------------------------------------------------------------

TEST_JWT_SECRET = "test-secret-do-not-use-in-production"
os.environ["JWT_SECRET"] = TEST_JWT_SECRET
settings.jwt_secret = TEST_JWT_SECRET


# ---------------------------------------------------------------------------
# In-memory SQLite engine
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    TestSession = async_sessionmaker(test_engine, expire_on_commit=False)
    async with TestSession() as session:
        yield session
        await session.rollback()


# ---------------------------------------------------------------------------
# Per-request JWT helpers
# ---------------------------------------------------------------------------

WORKSPACE_A_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WORKSPACE_B_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
USER_A_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_B_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
SUPER_ADMIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


def _mint_token(
    user_id: uuid.UUID,
    workspace_id: uuid.UUID | None,
    role: str = "practitioner",
) -> str:
    payload = {
        "sub": str(user_id),
        "app_metadata": {
            "role": role,
        },
    }
    if workspace_id:
        payload["app_metadata"]["workspace_id"] = str(workspace_id)
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")


TOKEN_A = _mint_token(USER_A_ID, WORKSPACE_A_ID)
TOKEN_B = _mint_token(USER_B_ID, WORKSPACE_B_ID)
TOKEN_SUPER_ADMIN = _mint_token(SUPER_ADMIN_ID, None, role="super_admin")


# ---------------------------------------------------------------------------
# TestClient factories
# ---------------------------------------------------------------------------


def _make_client(token: str, db_session: AsyncSession) -> TestClient:
    """Build a TestClient that sends the given Bearer token and uses db_session."""
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(
        app,
        headers={"Authorization": f"Bearer {token}"},
        raise_server_exceptions=True,
    )
    return client


@pytest.fixture
def client_a(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(
        app,
        headers={"Authorization": f"Bearer {TOKEN_A}"},
        raise_server_exceptions=True,
    ) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client_b(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(
        app,
        headers={"Authorization": f"Bearer {TOKEN_B}"},
        raise_server_exceptions=True,
    ) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client_super_admin(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(
        app,
        headers={"Authorization": f"Bearer {TOKEN_SUPER_ADMIN}"},
        raise_server_exceptions=True,
    ) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client_unauthenticated():
    """TestClient with no Authorization header — will 401."""
    app.dependency_overrides.pop(get_db, None)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
