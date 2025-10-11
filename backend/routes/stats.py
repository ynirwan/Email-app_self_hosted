from fastapi import APIRouter, HTTPException, status
from database import get_subscribers_collection, get_campaigns_collection  # ✅ Standardized imports
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/summary")  # Changed from "/stats/summary" to "/summary" since prefix is already "/api/stats"
async def stats_summary():
    try:
        # ✅ Use standardized AsyncIOMotorClient collection getters
        subscribers_collection = get_subscribers_collection()
        campaigns_collection = get_campaigns_collection()
        
        # Get counts using AsyncIOMotorClient
        subscribers_count = await subscribers_collection.count_documents({})
        campaigns_count = await campaigns_collection.count_documents({})
        
        # Additional stats
        active_subscribers = await subscribers_collection.count_documents({"status": "active"})
        
        # Get subscriber counts by list
        pipeline = [
            {"$group": {"_id": "$list", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        lists_stats = await subscribers_collection.aggregate(pipeline).to_list(None)
        
        return {
            "total_subscribers": subscribers_count,
            "active_subscribers": active_subscribers,
            "total_campaigns": campaigns_count,
            "lists": lists_stats,
            "summary": {
                "subscribers": subscribers_count,
                "campaigns": campaigns_count,
                "active_rate": round((active_subscribers / subscribers_count * 100) if subscribers_count > 0 else 0, 2)
            }
        }
        
    except Exception as e:
        logger.error(f"Stats summary failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch stats: {str(e)}"
        )

@router.get("/subscribers")
async def subscriber_stats():
    try:
        subscribers_collection = get_subscribers_collection()
        
        # Subscriber statistics
        total = await subscribers_collection.count_documents({})
        active = await subscribers_collection.count_documents({"status": "active"})
        inactive = await subscribers_collection.count_documents({"status": {"$ne": "active"}})
        
        # Subscribers by list
        pipeline = [
            {"$group": {"_id": "$list", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        by_list = await subscribers_collection.aggregate(pipeline).to_list(None)
        
        return {
            "total": total,
            "active": active,
            "inactive": inactive,
            "by_list": by_list
        }
        
    except Exception as e:
        logger.error(f"Subscriber stats failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch subscriber stats: {str(e)}")

@router.get("/campaigns")
async def campaign_stats():
    try:
        campaigns_collection = get_campaigns_collection()
        
        # Campaign statistics
        total = await campaigns_collection.count_documents({})
        active = await campaigns_collection.count_documents({"status": "active"})
        draft = await campaigns_collection.count_documents({"status": "draft"})
        sent = await campaigns_collection.count_documents({"status": "sent"})
        
        return {
            "total": total,
            "active": active,
            "draft": draft,
            "sent": sent
        }
        
    except Exception as e:
        logger.error(f"Campaign stats failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch campaign stats: {str(e)}")

