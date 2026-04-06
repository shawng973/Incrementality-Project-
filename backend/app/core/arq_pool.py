"""
ARQ Redis pool — FastAPI dependency.

Provides a lazy-initialised ARQ pool so the API can enqueue jobs.
The pool is created on first use and reused across requests.

Usage:
    from app.core.arq_pool import get_arq_pool
    pool = await get_arq_pool()
    await pool.enqueue_job("run_analysis", ...)
"""
from __future__ import annotations

from typing import Optional

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import settings

_pool: Optional[ArqRedis] = None


async def get_arq_pool() -> ArqRedis:
    """Return the shared ARQ pool, creating it on first call."""
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool
