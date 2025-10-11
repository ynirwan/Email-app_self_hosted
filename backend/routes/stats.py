# backend/routes/stats.py
from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from database import get_subscribers_collection, get_campaigns_collection
from typing import Dict, Any, Optional
import logging
import json
import redis.asyncio as redis  # 🔥 NEW: Modern Redis asyncio support
from datetime import datetime
import asyncio
import os

logger = logging.getLogger(__name__)
router = APIRouter()

# Redis configuration from Docker
REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))

# Database separation
CELERY_DB = 0      # Celery tasks (unchanged)
DASHBOARD_DB = 1   # Dashboard cache

# Redis client for dashboard caching
dashboard_redis: Optional[redis.Redis] = None

async def get_dashboard_redis():
    """Get async Redis client for dashboard (database 1)"""
    global dashboard_redis
    if not dashboard_redis:
        try:
            dashboard_redis = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=DASHBOARD_DB,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
                health_check_interval=30
            )
            # Test connection
            await dashboard_redis.ping()
            logger.info(f"✅ Dashboard Redis connected: {REDIS_HOST}:{REDIS_PORT}/db{DASHBOARD_DB}")
        except Exception as e:
            logger.warning(f"❌ Dashboard Redis failed: {e}")
            dashboard_redis = None
    return dashboard_redis

class DashboardCache:
    """High-performance dashboard caching"""
    
    CACHE_KEYS = {
        "summary": "dash:summary",
        "subscribers": "dash:subscribers",
        "campaigns": "dash:campaigns", 
        "quick": "dash:quick"
    }
    
    CACHE_TTL = {
        "summary": 300,      # 5 minutes
        "subscribers": 180,  # 3 minutes
        "campaigns": 120,    # 2 minutes
        "quick": 60          # 1 minute
    }
    
    @staticmethod
    async def get(key: str) -> Optional[Dict]:
        """Get cached data"""
        try:
            redis_client = await get_dashboard_redis()
            if not redis_client:
                return None
                
            cached = await redis_client.get(DashboardCache.CACHE_KEYS[key])
            if cached:
                data = json.loads(cached)
                logger.info(f"📊 Cache HIT: {key}")
                return data
                
            logger.info(f"📊 Cache MISS: {key}")
            return None
        except Exception as e:
            logger.warning(f"Cache get error {key}: {e}")
            return None
    
    @staticmethod
    async def set(key: str, data: Dict) -> bool:
        """Cache data with TTL"""
        try:
            redis_client = await get_dashboard_redis()
            if not redis_client:
                return False
                
            cache_data = {
                **data,
                "cached_at": datetime.utcnow().isoformat(),
                "redis_info": f"{REDIS_HOST}:{REDIS_PORT}/db{DASHBOARD_DB}"
            }
            
            success = await redis_client.set(
                DashboardCache.CACHE_KEYS[key],
                json.dumps(cache_data, default=str),
                ex=DashboardCache.CACHE_TTL[key]
            )
            
            if success:
                logger.info(f"💾 Cached: {key} (TTL: {DashboardCache.CACHE_TTL[key]}s)")
            return success
        except Exception as e:
            logger.warning(f"Cache set error {key}: {e}")
            return False
    
    @staticmethod
    async def clear_all():
        """Clear dashboard cache"""
        try:
            redis_client = await get_dashboard_redis()
            if redis_client:
                keys = list(DashboardCache.CACHE_KEYS.values())
                deleted = await redis_client.delete(*keys)
                logger.info(f"🗑️ Cleared {deleted} cache keys")
                return deleted
            return 0
        except Exception as e:
            logger.warning(f"Cache clear error: {e}")
            return 0

# Fast data fetching functions
async def fetch_quick_stats() -> Dict[str, Any]:
    """Lightning-fast basic stats"""
    try:
        subscribers_collection = get_subscribers_collection()
        campaigns_collection = get_campaigns_collection()
        
        # Fast concurrent counts
        subscriber_count, campaign_count = await asyncio.gather(
            subscribers_collection.estimated_document_count(),
            campaigns_collection.estimated_document_count()
        )
        
        return {
            "total_subscribers": subscriber_count,
            "total_campaigns": campaign_count,
            "type": "quick_stats",
            "fetched_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Quick stats error: {e}")
        return {
            "total_subscribers": 0,
            "total_campaigns": 0, 
            "error": str(e)
        }

async def fetch_detailed_summary() -> Dict[str, Any]:
    """Detailed dashboard summary"""
    try:
        subscribers_collection = get_subscribers_collection()
        campaigns_collection = get_campaigns_collection()
        
        # Optimized concurrent queries
        results = await asyncio.gather(
            subscribers_collection.count_documents({}),
            subscribers_collection.count_documents({"status": "active"}),
            campaigns_collection.count_documents({}),
            subscribers_collection.aggregate([
                {"$group": {"_id": "$list", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": 5}
            ]).to_list(5)
        )
        
        total_subs, active_subs, total_campaigns, list_stats = results
        
        return {
            "total_subscribers": total_subs,
            "active_subscribers": active_subs,
            "total_campaigns": total_campaigns,
            "lists": list_stats,
            "metrics": {
                "active_rate": round(
                    (active_subs / total_subs * 100) if total_subs > 0 else 0, 1
                )
            },
            "fetched_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Detailed summary error: {e}")
        raise

# API Endpoints
@router.get("/quick")
async def quick_stats():
    """Ultra-fast initial stats"""
    try:
        # Check cache first
        cached = await DashboardCache.get("quick")
        if cached:
            return cached
        
        # Fetch and cache
        data = await fetch_quick_stats()
        asyncio.create_task(DashboardCache.set("quick", data))
        
        return data
    except Exception as e:
        logger.error(f"Quick stats failed: {e}")
        return {
            "total_subscribers": 0,
            "total_campaigns": 0,
            "error": "Stats temporarily unavailable"
        }

@router.get("/summary")
async def dashboard_summary(background_tasks: BackgroundTasks):
    """Complete dashboard summary"""
    try:
        cached = await DashboardCache.get("summary")
        if cached:
            return cached
        
        data = await fetch_detailed_summary()
        background_tasks.add_task(DashboardCache.set, "summary", data)
        
        return data
    except Exception as e:
        logger.error(f"Dashboard summary failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to load dashboard")

@router.get("/subscribers")
async def subscriber_stats(background_tasks: BackgroundTasks):
    """Subscriber stats with caching"""
    try:
        cached = await DashboardCache.get("subscribers")
        if cached:
            return cached
        
        # Add your subscriber stats fetching logic here
        data = {"message": "Implement subscriber stats"}
        background_tasks.add_task(DashboardCache.set, "subscribers", data)
        
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/campaigns")
async def campaign_stats(background_tasks: BackgroundTasks):
    """Campaign stats with caching"""
    try:
        cached = await DashboardCache.get("campaigns")
        if cached:
            return cached
        
        # Add your campaign stats fetching logic here
        data = {"message": "Implement campaign stats"}
        background_tasks.add_task(DashboardCache.set, "campaigns", data)
        
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Cache management
@router.post("/cache/clear")
async def clear_cache():
    """Clear dashboard cache"""
    try:
        cleared = await DashboardCache.clear_all()
        return {
            "message": f"Dashboard cache cleared ({cleared} keys)",
            "redis_host": REDIS_HOST
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/redis/info")
async def redis_info():
    """Redis connection info"""
    try:
        redis_client = await get_dashboard_redis()
        
        return {
            "redis_host": REDIS_HOST,
            "redis_port": REDIS_PORT,
            "dashboard_db": DASHBOARD_DB,
            "dashboard_connected": redis_client is not None,
            "celery_db": CELERY_DB,
            "library": "redis-py (modern asyncio support)"
        }
    except Exception as e:
        return {"error": str(e)}

