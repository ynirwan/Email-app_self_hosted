# backend/routes/analytics.py
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from datetime import datetime, timedelta
from database import get_analytics_collection, get_email_events_collection, get_campaigns_collection
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/campaigns/{campaign_id}/analytics")
async def get_campaign_analytics(campaign_id: str):
    """Get comprehensive analytics for a specific campaign"""
    try:
        analytics_collection = get_analytics_collection()
        events_collection = get_email_events_collection()
        campaigns_collection = get_campaigns_collection()
        
        # Get campaign info
        campaign = await campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        # Get or create analytics record
        analytics = await analytics_collection.find_one({"campaign_id": campaign_id})
        if not analytics:
            # Create initial analytics record
            analytics = {
                "campaign_id": campaign_id,
                "total_sent": 0,
                "total_delivered": 0,
                "total_bounced": 0,
                "total_opened": 0,
                "total_clicked": 0,
                "total_unsubscribed": 0,
                "total_spam_reports": 0,
                "delivery_rate": 0.0,
                "open_rate": 0.0,
                "click_rate": 0.0,
                "bounce_rate": 0.0,
                "unsubscribe_rate": 0.0,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            await analytics_collection.insert_one(analytics)
        
        # Get recent events for timeline
        recent_events = []
        async for event in events_collection.find(
            {"campaign_id": campaign_id}
        ).sort("timestamp", -1).limit(50):
            event["_id"] = str(event["_id"])
            recent_events.append(event)
        
        # Get hourly breakdown for charts
        hourly_stats = await get_hourly_campaign_stats(campaign_id)
        
        # Get top clicked links
        top_links = await get_top_clicked_links(campaign_id)
        
        # Get geographic data
        geographic_data = await get_geographic_breakdown(campaign_id)
        
        # Convert ObjectId to string
        analytics["_id"] = str(analytics["_id"])
        campaign["_id"] = str(campaign["_id"])
        
        return {
            "campaign": campaign,
            "analytics": analytics,
            "recent_events": recent_events,
            "hourly_stats": hourly_stats,
            "top_links": top_links,
            "geographic_data": geographic_data
        }
        
    except Exception as e:
        logger.error(f"Error getting campaign analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/dashboard")
async def get_analytics_dashboard(
    days: int = Query(default=30, ge=1, le=365)
):
    """Get dashboard analytics for multiple campaigns"""
    try:
        campaigns_collection = get_campaigns_collection()
        analytics_collection = get_analytics_collection()
        
        # Get date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        # Get campaigns in date range
        campaigns = []
        async for campaign in campaigns_collection.find({
            "created_at": {"$gte": start_date, "$lte": end_date}
        }).sort("created_at", -1):
            campaign["_id"] = str(campaign["_id"])
            
            # Get analytics for this campaign
            analytics = await analytics_collection.find_one({"campaign_id": str(campaign["_id"])})
            if analytics:
                analytics["_id"] = str(analytics["_id"])
                campaign["analytics"] = analytics
            else:
                campaign["analytics"] = {
                    "total_sent": 0,
                    "total_opened": 0,
                    "total_clicked": 0,
                    "open_rate": 0.0,
                    "click_rate": 0.0
                }
            
            campaigns.append(campaign)
        
        # Calculate summary metrics
        total_campaigns = len(campaigns)
        total_sent = sum(c["analytics"]["total_sent"] for c in campaigns)
        total_opened = sum(c["analytics"]["total_opened"] for c in campaigns)
        total_clicked = sum(c["analytics"]["total_clicked"] for c in campaigns)
        
        avg_open_rate = (total_opened / total_sent * 100) if total_sent > 0 else 0
        avg_click_rate = (total_clicked / total_sent * 100) if total_sent > 0 else 0
        
        return {
            "summary": {
                "total_campaigns": total_campaigns,
                "total_emails_sent": total_sent,
                "total_opens": total_opened,
                "total_clicks": total_clicked,
                "average_open_rate": round(avg_open_rate, 2),
                "average_click_rate": round(avg_click_rate, 2)
            },
            "campaigns": campaigns,
            "date_range": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": days
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting dashboard analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/track/email-event")
async def track_email_event(event_data: dict):
    """Track email events (opens, clicks, etc.)"""
    try:
        events_collection = get_email_events_collection()
        analytics_collection = get_analytics_collection()
        
        # Insert event
        event_data["timestamp"] = datetime.utcnow()
        await events_collection.insert_one(event_data)
        
        # Update analytics counters
        await update_campaign_analytics(event_data["campaign_id"], event_data["event_type"])
        
        return {"status": "success", "message": "Event tracked"}
        
    except Exception as e:
        logger.error(f"Error tracking email event: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def update_campaign_analytics(campaign_id: str, event_type: str):
    """Update campaign analytics when events occur"""
    analytics_collection = get_analytics_collection()
    
    update_field = {
        "sent": "total_sent",
        "delivered": "total_delivered", 
        "opened": "total_opened",
        "clicked": "total_clicked",
        "bounced": "total_bounced",
        "unsubscribed": "total_unsubscribed",
        "spam": "total_spam_reports"
    }.get(event_type)
    
    if update_field:
        await analytics_collection.update_one(
            {"campaign_id": campaign_id},
            {
                "$inc": {update_field: 1},
                "$set": {"updated_at": datetime.utcnow()}
            },
            upsert=True
        )
        
        # Recalculate rates
        await recalculate_campaign_rates(campaign_id)

async def recalculate_campaign_rates(campaign_id: str):
    """Recalculate percentage rates for campaign analytics"""
    analytics_collection = get_analytics_collection()
    
    analytics = await analytics_collection.find_one({"campaign_id": campaign_id})
    if not analytics:
        return
    
    total_sent = analytics.get("total_sent", 0)
    total_delivered = analytics.get("total_delivered", 0)
    
    if total_sent > 0:
        delivery_rate = (total_delivered / total_sent) * 100
        bounce_rate = (analytics.get("total_bounced", 0) / total_sent) * 100
        unsubscribe_rate = (analytics.get("total_unsubscribed", 0) / total_sent) * 100
    else:
        delivery_rate = bounce_rate = unsubscribe_rate = 0.0
    
    if total_delivered > 0:
        open_rate = (analytics.get("total_opened", 0) / total_delivered) * 100
        click_rate = (analytics.get("total_clicked", 0) / total_delivered) * 100
    else:
        open_rate = click_rate = 0.0
    
    await analytics_collection.update_one(
        {"campaign_id": campaign_id},
        {
            "$set": {
                "delivery_rate": round(delivery_rate, 2),
                "open_rate": round(open_rate, 2),
                "click_rate": round(click_rate, 2),
                "bounce_rate": round(bounce_rate, 2),
                "unsubscribe_rate": round(unsubscribe_rate, 2),
                "updated_at": datetime.utcnow()
            }
        }
    )

async def get_hourly_campaign_stats(campaign_id: str):
    """Get hourly breakdown of campaign events"""
    events_collection = get_email_events_collection()
    
    # Get last 24 hours of data
    start_time = datetime.utcnow() - timedelta(hours=24)
    
    pipeline = [
        {
            "$match": {
                "campaign_id": campaign_id,
                "timestamp": {"$gte": start_time}
            }
        },
        {
            "$group": {
                "_id": {
                    "hour": {"$hour": "$timestamp"},
                    "event_type": "$event_type"
                },
                "count": {"$sum": 1}
            }
        },
        {
            "$sort": {"_id.hour": 1}
        }
    ]
    
    hourly_data = {}
    async for doc in events_collection.aggregate(pipeline):
        hour = doc["_id"]["hour"]
        event_type = doc["_id"]["event_type"]
        count = doc["count"]
        
        if hour not in hourly_data:
            hourly_data[hour] = {}
        hourly_data[hour][event_type] = count
    
    return hourly_data

async def get_top_clicked_links(campaign_id: str):
    """Get most clicked links in campaign"""
    events_collection = get_email_events_collection()
    
    pipeline = [
        {
            "$match": {
                "campaign_id": campaign_id,
                "event_type": "clicked"
            }
        },
        {
            "$group": {
                "_id": "$event_data.url",
                "clicks": {"$sum": 1}
            }
        },
        {
            "$sort": {"clicks": -1}
        },
        {
            "$limit": 10
        }
    ]
    
    top_links = []
    async for doc in events_collection.aggregate(pipeline):
        top_links.append({
            "url": doc["_id"],
            "clicks": doc["clicks"]
        })
    
    return top_links

async def get_geographic_breakdown(campaign_id: str):
    """Get geographic breakdown of campaign opens"""
    events_collection = get_email_events_collection()
    
    # This would require IP geolocation - simplified version
    pipeline = [
        {
            "$match": {
                "campaign_id": campaign_id,
                "event_type": "opened"
            }
        },
        {
            "$group": {
                "_id": "$event_data.country",
                "opens": {"$sum": 1}
            }
        },
        {
            "$sort": {"opens": -1}
        }
    ]
    
    geo_data = []
    async for doc in events_collection.aggregate(pipeline):
        geo_data.append({
            "country": doc["_id"] or "Unknown",
            "opens": doc["opens"]
        })
    
    return geo_data

