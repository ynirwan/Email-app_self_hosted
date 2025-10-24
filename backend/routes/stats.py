"""
Complete Stats Routes for Email Marketing Platform
Production-ready with Redis caching, performance optimization, and comprehensive analytics

Matches Dashboard.jsx and Analytics.jsx requirements
Author: Generated for Email Marketing Platform
Version: 2.0 - Production Ready
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import json
import logging
import asyncio
from collections import defaultdict

# Configure logging
logger = logging.getLogger(__name__)

# Create router (no prefix - main.py adds /api/stats)
router = APIRouter()

# ===== CACHE CONFIGURATION =====
class CacheConfig:
    """Centralized cache TTL configuration"""
    QUICK_STATS = 30        # 30 seconds - very fast refresh
    SUMMARY = 180           # 3 minutes - dashboard main stats
    SUBSCRIBERS = 300       # 5 minutes - subscriber details
    CAMPAIGNS = 300         # 5 minutes - campaign details
    ANALYTICS = 600         # 10 minutes - analytics data
    LISTS = 300             # 5 minutes - list stats
    TRENDS = 1800           # 30 minutes - trend data (changes slowly)
    DAILY = 3600            # 1 hour - historical daily stats


class CacheKeys:
    """Cache key templates for Redis"""
    QUICK = "stats:quick"
    SUMMARY = "stats:summary"
    SUBSCRIBERS = "stats:subscribers"
    SUBSCRIBERS_DETAIL = "stats:subscribers:detail"
    CAMPAIGNS = "stats:campaigns"
    CAMPAIGNS_DETAIL = "stats:campaigns:detail"
    LISTS = "stats:lists"
    DAILY = "stats:daily:{date}"
    WEEKLY = "stats:weekly"
    MONTHLY = "stats:monthly:{month}"
    TRENDS = "stats:trends:{days}"
    ANALYTICS = "stats:analytics:{days}"
    ENGAGEMENT = "stats:engagement"


# ===== DEPENDENCY HELPERS =====
def get_db():
    """Get MongoDB database instance"""
    from database import db
    return db


def get_redis():
    """Get Redis client instance"""
    try:
        from database import redis_client
        return redis_client
    except ImportError:
        return None


def get_subscribers_collection():
    """Get subscribers collection"""
    from database import get_subscribers_collection as get_col
    return get_col()


def get_campaigns_collection():
    """Get campaigns collection"""
    from database import get_campaigns_collection as get_col
    return get_col()


# ===== CACHE HELPER CLASS =====
class StatsCache:
    """Smart caching layer for stats data"""
    
    @staticmethod
    async def get(key: str) -> Optional[Dict]:
        """
        Get cached data with error handling
        Returns None if cache miss or error
        """
        try:
            redis_client = get_redis()
            if not redis_client:
                return None
                
            cached = await redis_client.get(key)
            if cached:
                logger.debug(f"✅ Cache HIT: {key}")
                return json.loads(cached)
            
            logger.debug(f"❌ Cache MISS: {key}")
            return None
            
        except Exception as e:
            logger.warning(f"Cache read error for {key}: {e}")
            return None
    
    @staticmethod
    async def set(key: str, data: Dict, ttl: int = 300) -> bool:
        """
        Set cached data with TTL
        Returns True if successful, False otherwise
        """
        try:
            redis_client = get_redis()
            if not redis_client:
                return False
                
            await redis_client.setex(
                key,
                ttl,
                json.dumps(data, default=str)
            )
            logger.debug(f"💾 Cached: {key} (TTL: {ttl}s)")
            return True
            
        except Exception as e:
            logger.warning(f"Cache write error for {key}: {e}")
            return False
    
    @staticmethod
    async def delete(*keys: str) -> int:
        """
        Delete specific cache keys
        Returns number of keys deleted
        """
        try:
            redis_client = get_redis()
            if not redis_client or not keys:
                return 0
                
            deleted = await redis_client.delete(*keys)
            logger.info(f"🗑️ Deleted {deleted} cache keys")
            return deleted
            
        except Exception as e:
            logger.warning(f"Cache delete error: {e}")
            return 0
    
    @staticmethod
    async def clear_pattern(pattern: str) -> int:
        """
        Clear all keys matching pattern
        Returns number of keys deleted
        """
        try:
            redis_client = get_redis()
            if not redis_client:
                return 0
                
            cursor = 0
            deleted_count = 0
            
            while True:
                cursor, keys = await redis_client.scan(cursor, match=pattern, count=100)
                if keys:
                    deleted = await redis_client.delete(*keys)
                    deleted_count += deleted
                if cursor == 0:
                    break
            
            logger.info(f"🗑️ Cleared {deleted_count} keys matching '{pattern}'")
            return deleted_count
            
        except Exception as e:
            logger.warning(f"Cache clear error: {e}")
            return 0


# ===== DATA FETCHING FUNCTIONS =====

async def fetch_quick_stats() -> Dict[str, Any]:
    """
    Ultra-fast basic stats for initial page load
    Uses estimated counts for maximum speed
    """
    try:
        subscribers_collection = get_subscribers_collection()
        campaigns_collection = get_campaigns_collection()
        
        # Concurrent estimated counts (very fast)
        subscriber_count, campaign_count = await asyncio.gather(
            subscribers_collection.estimated_document_count(),
            campaigns_collection.estimated_document_count()
        )
        
        return {
            "total_subscribers": subscriber_count,
            "total_campaigns": campaign_count,
            "type": "quick_stats",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Quick stats error: {e}")
        return {
            "total_subscribers": 0,
            "total_campaigns": 0,
            "error": str(e)
        }


async def fetch_dashboard_summary() -> Dict[str, Any]:
    """
    Complete dashboard summary - matches Dashboard.jsx expectations
    Optimized with concurrent queries
    """
    try:
        subscribers_collection = get_subscribers_collection()
        campaigns_collection = get_campaigns_collection()
        
        # Run all queries concurrently for maximum speed
        results = await asyncio.gather(
            # Total subscribers
            subscribers_collection.count_documents({}),
            
            # Active subscribers
            subscribers_collection.count_documents({"status": "active"}),
            
            # Total campaigns
            campaigns_collection.count_documents({}),
            
            # Campaign status breakdown
            campaigns_collection.aggregate([
                {
                    "$group": {
                        "_id": "$status",
                        "count": {"$sum": 1}
                    }
                }
            ]).to_list(None),
            
            # Top 5 lists by subscriber count
            subscribers_collection.aggregate([
                {
                    "$group": {
                        "_id": "$list",
                        "count": {"$sum": 1}
                    }
                },
                {"$sort": {"count": -1}},
                {"$limit": 5}
            ]).to_list(5),
            
            # Recent campaign performance (last 10 campaigns)
            campaigns_collection.aggregate([
                {"$match": {"status": "completed"}},
                {"$sort": {"sent_at": -1}},
                {"$limit": 10},
                {
                    "$project": {
                        "title": 1,
                        "sent_count": 1,
                        "open_rate": 1,
                        "click_rate": 1,
                        "sent_at": 1
                    }
                }
            ]).to_list(10)
        )
        
        total_subs, active_subs, total_campaigns, campaign_statuses, top_lists, recent_campaigns = results
        
        # Process campaign status counts
        draft_count = 0
        scheduled_count = 0
        sending_count = 0
        completed_count = 0
        failed_count = 0
        
        for status in campaign_statuses:
            status_name = status.get('_id', '').lower()
            count = status.get('count', 0)
            
            if status_name == 'draft':
                draft_count = count
            elif status_name == 'scheduled':
                scheduled_count = count
            elif status_name == 'sending':
                sending_count = count
            elif status_name == 'completed':
                completed_count = count
            elif status_name == 'failed':
                failed_count = count
        
        # Calculate rates
        active_rate = round((active_subs / total_subs * 100) if total_subs > 0 else 0, 1)
        
        # Calculate average performance from recent campaigns
        avg_open_rate = 0
        avg_click_rate = 0
        if recent_campaigns:
            open_rates = [c.get('open_rate', 0) for c in recent_campaigns if c.get('open_rate')]
            click_rates = [c.get('click_rate', 0) for c in recent_campaigns if c.get('click_rate')]
            
            avg_open_rate = round(sum(open_rates) / len(open_rates), 2) if open_rates else 0
            avg_click_rate = round(sum(click_rates) / len(click_rates), 2) if click_rates else 0
        
        # Return format matching Dashboard.jsx expectations
        return {
            "total_subscribers": total_subs,
            "active_subscribers": active_subs,
            "total_campaigns": total_campaigns,
            "draft_campaigns": draft_count,
            "scheduled_campaigns": scheduled_count,
            "sending_campaigns": sending_count,
            "completed_campaigns": completed_count,
            "failed_campaigns": failed_count,
            "summary": {
                "active_rate": active_rate,
                "avg_open_rate": avg_open_rate,
                "avg_click_rate": avg_click_rate
            },
            "lists": top_lists,
            "recent_performance": recent_campaigns[:5],  # Top 5 recent
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Dashboard summary error: {e}", exc_info=True)
        # Return safe defaults
        return {
            "total_subscribers": 0,
            "active_subscribers": 0,
            "total_campaigns": 0,
            "draft_campaigns": 0,
            "scheduled_campaigns": 0,
            "sending_campaigns": 0,
            "completed_campaigns": 0,
            "failed_campaigns": 0,
            "summary": {
                "active_rate": 0,
                "avg_open_rate": 0,
                "avg_click_rate": 0
            },
            "lists": [],
            "recent_performance": [],
            "error": str(e)
        }


async def fetch_subscriber_stats_detailed() -> Dict[str, Any]:
    """
    Detailed subscriber statistics with breakdowns
    """
    try:
        subscribers_collection = get_subscribers_collection()
        
        # Comprehensive subscriber pipeline
        pipeline = [
            {
                "$facet": {
                    # Total count
                    "total": [
                        {"$count": "count"}
                    ],
                    
                    # Status breakdown
                    "by_status": [
                        {
                            "$group": {
                                "_id": "$status",
                                "count": {"$sum": 1}
                            }
                        }
                    ],
                    
                    # List breakdown
                    "by_list": [
                        {
                            "$group": {
                                "_id": "$list",
                                "count": {"$sum": 1}
                            }
                        },
                        {"$sort": {"count": -1}},
                        {"$limit": 10}
                    ],
                    
                    # Growth trend (last 30 days)
                    "growth_trend": [
                        {
                            "$match": {
                                "created_at": {
                                    "$gte": datetime.utcnow() - timedelta(days=30)
                                }
                            }
                        },
                        {
                            "$group": {
                                "_id": {
                                    "$dateToString": {
                                        "format": "%Y-%m-%d",
                                        "date": "$created_at"
                                    }
                                },
                                "count": {"$sum": 1}
                            }
                        },
                        {"$sort": {"_id": 1}}
                    ],
                    
                    # New subscribers today
                    "new_today": [
                        {
                            "$match": {
                                "created_at": {
                                    "$gte": datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                                }
                            }
                        },
                        {"$count": "count"}
                    ]
                }
            }
        ]
        
        result = await subscribers_collection.aggregate(pipeline).to_list(1)
        
        if result:
            data = result[0]
            
            # Extract totals
            total = data['total'][0]['count'] if data['total'] else 0
            new_today = data['new_today'][0]['count'] if data['new_today'] else 0
            
            # Process status counts
            status_counts = {
                'active': 0,
                'inactive': 0,
                'bounced': 0,
                'unsubscribed': 0
            }
            
            for item in data['by_status']:
                status = item['_id'].lower() if item['_id'] else 'unknown'
                if status in status_counts:
                    status_counts[status] = item['count']
            
            return {
                "total": total,
                "new_today": new_today,
                "status_breakdown": status_counts,
                "by_list": data['by_list'],
                "growth_trend": data['growth_trend'],
                "engagement_rate": round((status_counts['active'] / total * 100) if total > 0 else 0, 2),
                "churn_rate": round((status_counts['unsubscribed'] / total * 100) if total > 0 else 0, 2),
                "timestamp": datetime.utcnow().isoformat()
            }
        
        return {
            "total": 0,
            "new_today": 0,
            "status_breakdown": {},
            "by_list": [],
            "growth_trend": [],
            "engagement_rate": 0,
            "churn_rate": 0
        }
        
    except Exception as e:
        logger.error(f"Detailed subscriber stats error: {e}")
        raise


async def fetch_campaign_stats_detailed() -> Dict[str, Any]:
    """
    Detailed campaign statistics with performance metrics
    """
    try:
        campaigns_collection = get_campaigns_collection()
        
        pipeline = [
            {
                "$facet": {
                    # Total campaigns
                    "total": [
                        {"$count": "count"}
                    ],
                    
                    # Status breakdown
                    "by_status": [
                        {
                            "$group": {
                                "_id": "$status",
                                "count": {"$sum": 1}
                            }
                        }
                    ],
                    
                    # Performance metrics (completed campaigns only)
                    "performance": [
                        {
                            "$match": {
                                "status": "completed"
                            }
                        },
                        {
                            "$group": {
                                "_id": None,
                                "total_sent": {"$sum": "$sent_count"},
                                "avg_open_rate": {"$avg": "$open_rate"},
                                "avg_click_rate": {"$avg": "$click_rate"},
                                "campaigns_count": {"$sum": 1}
                            }
                        }
                    ],
                    
                    # Recent campaigns (last 20)
                    "recent": [
                        {"$sort": {"created_at": -1}},
                        {"$limit": 20},
                        {
                            "$project": {
                                "title": 1,
                                "status": 1,
                                "sent_count": 1,
                                "open_rate": 1,
                                "click_rate": 1,
                                "created_at": 1,
                                "sent_at": 1
                            }
                        }
                    ],
                    
                    # Campaigns sent today
                    "sent_today": [
                        {
                            "$match": {
                                "sent_at": {
                                    "$gte": datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                                }
                            }
                        },
                        {"$count": "count"}
                    ]
                }
            }
        ]
        
        result = await campaigns_collection.aggregate(pipeline).to_list(1)
        
        if result:
            data = result[0]
            
            # Extract counts
            total = data['total'][0]['count'] if data['total'] else 0
            sent_today = data['sent_today'][0]['count'] if data['sent_today'] else 0
            
            # Process status breakdown
            status_breakdown = {}
            for item in data['by_status']:
                status_breakdown[item['_id']] = item['count']
            
            # Get performance metrics
            perf = data['performance'][0] if data['performance'] else {}
            
            return {
                "total": total,
                "sent_today": sent_today,
                "status_breakdown": status_breakdown,
                "performance": {
                    "total_emails_sent": perf.get('total_sent', 0),
                    "avg_open_rate": round(perf.get('avg_open_rate', 0), 2),
                    "avg_click_rate": round(perf.get('avg_click_rate', 0), 2),
                    "completed_campaigns": perf.get('campaigns_count', 0)
                },
                "recent_campaigns": data['recent'],
                "timestamp": datetime.utcnow().isoformat()
            }
        
        return {
            "total": 0,
            "sent_today": 0,
            "status_breakdown": {},
            "performance": {},
            "recent_campaigns": []
        }
        
    except Exception as e:
        logger.error(f"Detailed campaign stats error: {e}")
        raise


# NOTE: fetch_analytics_dashboard() removed - analytics.py handles this
# See analytics.py for campaign analytics functionality

async def fetch_engagement_stats() -> Dict[str, Any]:
    """
    Engagement statistics - open rates, click rates, trends
    """
    try:
        campaigns_collection = get_campaigns_collection()
        
        # Get engagement data from last 30 days
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        
        pipeline = [
            {
                "$match": {
                    "status": "completed",
                    "sent_at": {"$gte": thirty_days_ago}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_sent": {"$sum": "$sent_count"},
                    "avg_open_rate": {"$avg": "$open_rate"},
                    "avg_click_rate": {"$avg": "$click_rate"},
                    "max_open_rate": {"$max": "$open_rate"},
                    "min_open_rate": {"$min": "$open_rate"}
                }
            }
        ]
        
        result = await campaigns_collection.aggregate(pipeline).to_list(1)
        
        if result:
            data = result[0]
            return {
                "total_emails_sent": data.get('total_sent', 0),
                "avg_open_rate": round(data.get('avg_open_rate', 0), 2),
                "avg_click_rate": round(data.get('avg_click_rate', 0), 2),
                "best_open_rate": round(data.get('max_open_rate', 0), 2),
                "worst_open_rate": round(data.get('min_open_rate', 0), 2),
                "period": "last_30_days",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        return {
            "total_emails_sent": 0,
            "avg_open_rate": 0,
            "avg_click_rate": 0,
            "best_open_rate": 0,
            "worst_open_rate": 0,
            "period": "last_30_days"
        }
        
    except Exception as e:
        logger.error(f"Engagement stats error: {e}")
        raise


# ===== API ENDPOINTS =====

@router.get("/quick")
async def get_quick_stats():
    """
    Ultra-fast quick stats for initial page load
    Uses estimated counts and aggressive caching
    
    Returns:
        Basic subscriber and campaign counts
    """
    try:
        # Try cache first
        cached = await StatsCache.get(CacheKeys.QUICK)
        if cached:
            return cached
        
        # Fetch fresh data
        logger.info("Fetching quick stats from database")
        data = await fetch_quick_stats()
        
        # Cache in background (non-blocking)
        asyncio.create_task(
            StatsCache.set(CacheKeys.QUICK, data, CacheConfig.QUICK_STATS)
        )
        
        return data
        
    except Exception as e:
        logger.error(f"Quick stats endpoint failed: {e}")
        return {
            "total_subscribers": 0,
            "total_campaigns": 0,
            "error": "Stats temporarily unavailable"
        }


@router.get("/summary")
async def get_dashboard_summary(background_tasks: BackgroundTasks):
    """
    Complete dashboard summary - PRIMARY ENDPOINT for Dashboard.jsx
    
    Returns comprehensive stats including:
    - Total/active subscribers
    - Campaign counts by status
    - Engagement metrics
    - Top lists
    - Recent performance
    
    Uses smart caching with background refresh
    """
    try:
        # Try cache first
        cached = await StatsCache.get(CacheKeys.SUMMARY)
        if cached:
            logger.info("✅ Returning cached dashboard summary")
            return cached
        
        # Fetch fresh data
        logger.info("📊 Fetching fresh dashboard summary from database")
        data = await fetch_dashboard_summary()
        
        # Cache in background task (non-blocking)
        background_tasks.add_task(
            StatsCache.set,
            CacheKeys.SUMMARY,
            data,
            CacheConfig.SUMMARY
        )
        
        return data
        
    except Exception as e:
        logger.error(f"Dashboard summary endpoint failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to load dashboard summary"
        )


@router.get("/subscribers")
async def get_subscriber_stats(background_tasks: BackgroundTasks):
    """
    Detailed subscriber statistics
    
    Returns:
    - Total subscribers
    - Status breakdown
    - List distribution
    - Growth trends
    - Engagement metrics
    """
    try:
        # Try cache
        cached = await StatsCache.get(CacheKeys.SUBSCRIBERS_DETAIL)
        if cached:
            return cached
        
        # Fetch fresh data
        logger.info("Fetching detailed subscriber stats")
        data = await fetch_subscriber_stats_detailed()
        
        # Cache in background
        background_tasks.add_task(
            StatsCache.set,
            CacheKeys.SUBSCRIBERS_DETAIL,
            data,
            CacheConfig.SUBSCRIBERS
        )
        
        return data
        
    except Exception as e:
        logger.error(f"Subscriber stats endpoint failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to load subscriber statistics"
        )


@router.get("/campaigns")
async def get_campaign_stats(background_tasks: BackgroundTasks):
    """
    Detailed campaign statistics
    
    Returns:
    - Total campaigns
    - Status breakdown
    - Performance metrics
    - Recent campaigns
    - Sending statistics
    """
    try:
        # Try cache
        cached = await StatsCache.get(CacheKeys.CAMPAIGNS_DETAIL)
        if cached:
            return cached
        
        # Fetch fresh data
        logger.info("Fetching detailed campaign stats")
        data = await fetch_campaign_stats_detailed()
        
        # Cache in background
        background_tasks.add_task(
            StatsCache.set,
            CacheKeys.CAMPAIGNS_DETAIL,
            data,
            CacheConfig.CAMPAIGNS
        )
        
        return data
        
    except Exception as e:
        logger.error(f"Campaign stats endpoint failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to load campaign statistics"
        )


# NOTE: /analytics/dashboard endpoint removed - already exists in analytics.py
# Analytics.jsx uses /api/analytics/dashboard which is handled by analytics.py
# This avoids duplication and keeps clear separation of concerns


@router.get("/engagement")
async def get_engagement_stats(background_tasks: BackgroundTasks):
    """
    Engagement statistics - open rates, click rates, trends
    
    Returns:
        Overall engagement metrics for the platform
    """
    try:
        # Try cache
        cached = await StatsCache.get(CacheKeys.ENGAGEMENT)
        if cached:
            return cached
        
        # Fetch fresh data
        logger.info("Fetching engagement stats")
        data = await fetch_engagement_stats()
        
        # Cache in background
        background_tasks.add_task(
            StatsCache.set,
            CacheKeys.ENGAGEMENT,
            data,
            CacheConfig.ANALYTICS
        )
        
        return data
        
    except Exception as e:
        logger.error(f"Engagement stats endpoint failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to load engagement statistics"
        )


# ===== CACHE MANAGEMENT ENDPOINTS =====

@router.post("/cache/invalidate")
async def invalidate_stats_cache():
    """
    Invalidate all stats cache
    
    Call this after operations that change statistics:
    - New subscriber added
    - Campaign sent
    - Subscriber status changed
    - Campaign status changed
    
    Returns:
        Number of cache keys invalidated
    """
    try:
        deleted = await StatsCache.delete(
            CacheKeys.QUICK,
            CacheKeys.SUMMARY,
            CacheKeys.SUBSCRIBERS_DETAIL,
            CacheKeys.CAMPAIGNS_DETAIL,
            CacheKeys.ENGAGEMENT
        )
        
        logger.info(f"✅ Invalidated {deleted} stats cache keys")
        
        return {
            "success": True,
            "message": f"Invalidated {deleted} cache keys",
            "keys_cleared": deleted
        }
        
    except Exception as e:
        logger.error(f"Cache invalidation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to invalidate cache"
        )


@router.delete("/cache")
async def clear_all_stats_cache():
    """
    Clear ALL stats-related cache keys
    
    Use for:
    - Testing
    - Troubleshooting
    - After bulk operations
    - Manual cache reset
    
    Returns:
        Number of cache keys cleared
    """
    try:
        deleted = await StatsCache.clear_pattern("stats:*")
        
        logger.info(f"✅ Cleared {deleted} total cache keys")
        
        return {
            "success": True,
            "message": f"Cleared {deleted} cache keys",
            "keys_cleared": deleted
        }
        
    except Exception as e:
        logger.error(f"Cache clear failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to clear cache"
        )


@router.get("/cache/status")
async def get_cache_status():
    """
    Get cache status and statistics
    
    Returns:
        Information about cached keys and their status
    """
    try:
        redis_client = get_redis()
        if not redis_client:
            return {
                "cache_enabled": False,
                "message": "Redis not configured"
            }
        
        # Get all stats keys
        all_keys = []
        cursor = 0
        
        while True:
            cursor, keys = await redis_client.scan(cursor, match="stats:*", count=100)
            all_keys.extend(keys)
            if cursor == 0:
                break
        
        # Get TTLs for sample keys
        sample_ttls = {}
        for key in all_keys[:10]:  # Sample first 10 keys
            ttl = await redis_client.ttl(key)
            sample_ttls[key] = ttl
        
        return {
            "cache_enabled": True,
            "total_keys": len(all_keys),
            "sample_keys": list(sample_ttls.keys()),
            "sample_ttls": sample_ttls,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Cache status check failed: {e}")
        return {
            "cache_enabled": False,
            "error": str(e)
        }


# ===== HEALTH CHECK =====

@router.get("/health")
async def stats_health_check():
    """
    Health check for stats service
    
    Returns:
        Service health status including database and cache connectivity
    """
    try:
        # Check database
        subscribers_collection = get_subscribers_collection()
        await subscribers_collection.estimated_document_count()
        db_healthy = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_healthy = False
    
    # Check cache
    try:
        redis_client = get_redis()
        if redis_client:
            await redis_client.ping()
            cache_healthy = True
        else:
            cache_healthy = False
    except Exception as e:
        logger.error(f"Cache health check failed: {e}")
        cache_healthy = False
    
    # Overall status
    status = "healthy" if (db_healthy and cache_healthy) else "degraded"
    
    return {
        "service": "stats",
        "status": status,
        "database_healthy": db_healthy,
        "cache_healthy": cache_healthy,
        "cache_enabled": cache_healthy,
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0"
    }


# ===== HELPER FUNCTION FOR OTHER ROUTES =====

async def invalidate_stats_on_change(change_type: str = "all"):
    """
    Helper function to invalidate stats cache when data changes
    
    Call this from other routes when:
    - Subscribers are added/updated/deleted
    - Campaigns are created/sent/updated
    
    Args:
        change_type: Type of change ('subscriber', 'campaign', or 'all')
    """
    if change_type == "subscriber":
        await StatsCache.delete(
            CacheKeys.QUICK,
            CacheKeys.SUMMARY,
            CacheKeys.SUBSCRIBERS_DETAIL
        )
    elif change_type == "campaign":
        await StatsCache.delete(
            CacheKeys.QUICK,
            CacheKeys.SUMMARY,
            CacheKeys.CAMPAIGNS_DETAIL,
            CacheKeys.ENGAGEMENT
        )
    else:
        # Invalidate everything
        await StatsCache.clear_pattern("stats:*")
    
    logger.info(f"✅ Invalidated cache for change_type: {change_type}")
