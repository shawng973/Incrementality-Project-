"""
Alembic async environment configuration.

Reads DATABASE_URL from the environment (via app.core.config.Settings) and
runs migrations using SQLAlchemy's async engine.

All ORM models must be imported here (or transitively via app.models.workspace)
so that `target_metadata` reflects the current schema.
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ---------------------------------------------------------------------------
# Import all models so metadata is populated before autogenerate runs
# ---------------------------------------------------------------------------
from app.db.base import Base
import app.models.workspace  # noqa: F401 — registers all ORM models

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Alembic config object
# ---------------------------------------------------------------------------

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Resolve the database URL from the environment
# ---------------------------------------------------------------------------


def _get_url() -> str:
    """
    Read DATABASE_URL from the environment and convert to the asyncpg scheme.
    Falls back to a local dev URL if DATABASE_URL is not set.
    """
    from app.core.config import settings

    url = settings.database_url or "postgresql://postgres:postgres@localhost/incremental_tool_dev"
    return (
        url.replace("postgres://", "postgresql+asyncpg://")
           .replace("postgresql://", "postgresql+asyncpg://")
    )


# ---------------------------------------------------------------------------
# Offline mode — generate SQL without a live connection
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """Emit migration SQL to stdout without connecting to the database."""
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode — connect and run
# ---------------------------------------------------------------------------


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
