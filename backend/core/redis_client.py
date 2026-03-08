# backend/core/redis_client.py
"""
Single shared Redis connection pool for the entire application.
All files must import from here — never create Redis.from_url() directly.

Usage:
    from core.redis_client import get_redis, get_async_redis

Sync (Celery tasks, blocking code):
    r = get_redis()
    r.set("key", "value")

Async (FastAPI routes):
    async with get_async_redis() as r:
        await r.set("key", "value")
"""
import logging
import redis
import redis.asyncio as aioredis
from contextlib import asynccontextmanager
from typing import Optional
from core.config import settings

logger = logging.getLogger(__name__)

# ============================================
# POOL SIZING
# ============================================
# Redis Cloud free tier: 30 max connections
# Redis Cloud paid:      varies by plan
#
# Budget per container (total must stay under plan limit):
#   backend      : 5  (async pool for FastAPI routes)
#   celery_main  : 10 (sync pool for tasks — most activity here)
#   celery_beat  : 3  (just schedules tasks, minimal Redis use)
#   flower       : 2  (monitoring only)
#   Total        : 20 (leaves 10 headroom on free tier)
#
# Override via .env:
#   REDIS_MAX_CONNECTIONS=10
# ============================================

SYNC_POOL_MAX  = int(settings.REDIS_MAX_CONNECTIONS)   # default 10 from settings
ASYNC_POOL_MAX = max(3, SYNC_POOL_MAX // 2)            # async pool is half of sync

# ── Sync pool (used by Celery tasks) ────────────────────────────────────────
_sync_pool: Optional[redis.ConnectionPool] = None

def _get_sync_pool() -> redis.ConnectionPool:
    global _sync_pool
    if _sync_pool is None:
        _sync_pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=SYNC_POOL_MAX,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=10,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        logger.info(f"✅ Redis sync pool created (max={SYNC_POOL_MAX})")
    return _sync_pool


def get_redis() -> redis.Redis:
    """
    Get a sync Redis client from the shared pool.
    Use in Celery tasks and any synchronous code.
    Do NOT call .close() on the returned client — it returns to the pool automatically.
    """
    return redis.Redis(connection_pool=_get_sync_pool())


# ── Async pool (used by FastAPI routes) ─────────────────────────────────────
_async_pool: Optional[aioredis.ConnectionPool] = None

def _get_async_pool() -> aioredis.ConnectionPool:
    global _async_pool
    if _async_pool is None:
        _async_pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=ASYNC_POOL_MAX,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=10,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        logger.info(f"✅ Redis async pool created (max={ASYNC_POOL_MAX})")
    return _async_pool


@asynccontextmanager
async def get_async_redis():
    """
    Async context manager for Redis in FastAPI routes.

    Usage:
        async with get_async_redis() as r:
            await r.set("key", "value")
    """
    client = aioredis.Redis(connection_pool=_get_async_pool())
    try:
        yield client
    finally:
        await client.aclose()


# ── Standalone async client for routes that prefer direct assignment ─────────
def get_async_redis_client() -> aioredis.Redis:
    """
    Returns an async Redis client from the shared pool.
    Use when you need to hold the client across multiple awaits.
    Call await client.aclose() when done.
    """
    return aioredis.Redis(connection_pool=_get_async_pool())


# ── Health check ─────────────────────────────────────────────────────────────
def ping_redis() -> bool:
    try:
        return get_redis().ping()
    except Exception as e:
        logger.error(f"Redis ping failed: {e}")
        return False


__all__ = [
    "get_redis",
    "get_async_redis",
    "get_async_redis_client",
    "ping_redis",
]
