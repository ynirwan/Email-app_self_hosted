# backend/routes/deliverability.py
"""
Deliverability health dashboard API.

Single endpoint: GET /api/deliverability/health
Optional query param: ?days=30  (7, 14, 30, 60, 90 supported)

Response is cached in Redis for 5 minutes to avoid re-aggregating
large email_logs collections on every page load.
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Query

from services.deliverability_service import get_deliverability_health

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/deliverability", tags=["Deliverability"])

CACHE_TTL  = 300          # 5 minutes
CACHE_KEY  = "deliverability:health:{days}"
VALID_DAYS = {7, 14, 30, 60, 90}


async def _try_cache_get(key: str):
    try:
        from core.redis_client import get_async_redis
        async with get_async_redis() as r:
            raw = await r.get(key)
            return json.loads(raw) if raw else None
    except Exception:
        return None


async def _try_cache_set(key: str, data: dict, ttl: int):
    try:
        from core.redis_client import get_async_redis
        async with get_async_redis() as r:
            await r.setex(key, ttl, json.dumps(data, default=str))
    except Exception:
        pass   # cache failure is non-fatal


@router.get("/health")
async def get_health(
    days: int = Query(default=30, ge=7, le=90, description="Rolling window in days"),
):
    """
    Returns the deliverability health score, per-metric breakdown,
    trend lines, domain verification status, and actionable recommendations.

    Cached for 5 minutes in Redis. Pass ?days=7|14|30|60|90.
    """
    # Snap to nearest valid bucket
    if days not in VALID_DAYS:
        days = min(VALID_DAYS, key=lambda d: abs(d - days))

    cache_key = CACHE_KEY.format(days=days)
    cached = await _try_cache_get(cache_key)
    if cached:
        cached["_cached"] = True
        return cached

    try:
        data = await get_deliverability_health(days=days)
    except Exception as exc:
        logger.exception("Deliverability health aggregation failed")
        raise HTTPException(
            status_code=500,
            detail="Failed to compute deliverability health",
        ) from exc

    data["_cached"] = False
    await _try_cache_set(cache_key, data, CACHE_TTL)
    return data
