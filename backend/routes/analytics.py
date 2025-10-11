# backend/routes/analytics.py
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import datetime, timedelta
from database import (
    get_analytics_collection,
    get_email_events_collection,
    get_campaigns_collection
)
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/campaigns/{campaign_id}")
async def get_campaign_analytics(campaign_id: str):
    """Get comprehensive analytics for a specific campaign"""
    try:
        analytics_collection = get_analytics_collection()
        events_collection = get_email_events_collection()
        campaigns_collection = get_campaigns_collection()

        # Get campaign details and sent count from campaigns collection
        campaign = await campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # Convert ObjectId to string for JSON serialization
        campaign["_id"] = str(campaign["_id"])

        # Get analytics data from analytics collection (opens, clicks, bounces, etc.)
        analytics = await analytics_collection.find_one({"campaign_id": ObjectId(campaign_id)})

        if not analytics:
            # Create basic analytics structure if it doesn't exist
            analytics = {
                "campaign_id": ObjectId(campaign_id),
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

        # Convert ObjectId to string for JSON serialization
        analytics["_id"] = str(analytics["_id"])
        analytics["campaign_id"] = str(analytics["campaign_id"])

        # Calculate rates based on campaign sent_count (from campaigns collection)
        total_sent = campaign.get("sent_count", 0)
        if total_sent > 0:
            analytics["delivery_rate"] = round(((total_sent - analytics.get("total_bounced", 0)) / total_sent) * 100, 1)
            analytics["open_rate"] = round((analytics.get("total_opened", 0) / total_sent) * 100, 1)
            analytics["click_rate"] = round((analytics.get("total_clicked", 0) / total_sent) * 100, 1)
            analytics["bounce_rate"] = round((analytics.get("total_bounced", 0) / total_sent) * 100, 1)
            analytics["unsubscribe_rate"] = round((analytics.get("total_unsubscribed", 0) / total_sent) * 100, 1)

        # Get recent events (limit to 20 for performance)
        recent_events = []
        async for event in events_collection.find(
            {"campaign_id": ObjectId(campaign_id)}
        ).sort("timestamp", -1).limit(20):
            event["_id"] = str(event["_id"])
            event["campaign_id"] = str(event["campaign_id"])
            recent_events.append(event)

        # Get top clicked links
        top_links = await get_top_clicked_links(campaign_id)

        # Combine campaign data with analytics
        response_data = {
            "campaign": {
                "_id": campaign["_id"],
                "title": campaign.get("title"),
                "subject": campaign.get("subject"),
                "sender_name": campaign.get("sender_name"),
                "sender_email": campaign.get("sender_email"),
                "status": campaign.get("status"),
                "target_lists": campaign.get("target_lists", []),
                "target_list_count": campaign.get("target_list_count", 0),
                "sent_count": campaign.get("sent_count", 0),  # From campaigns collection
                "processed_count": campaign.get("processed_count", 0),
                "queued_count": campaign.get("queued_count", 0),
                "created_at": campaign.get("created_at"),
                "started_at": campaign.get("started_at"),
                "completed_at": campaign.get("completed_at"),
                "last_batch_at": campaign.get("last_batch_at")
            },
            "analytics": {
                "_id": analytics["_id"],
                "campaign_id": analytics["campaign_id"],
                "total_sent": total_sent,  # From campaigns collection
                "total_delivered": analytics.get("total_delivered", 0),
                "total_bounced": analytics.get("total_bounced", 0),
                "total_opened": analytics.get("total_opened", 0),
                "total_clicked": analytics.get("total_clicked", 0),
                "total_unsubscribed": analytics.get("total_unsubscribed", 0),
                "total_spam_reports": analytics.get("total_spam_reports", 0),
                "delivery_rate": analytics.get("delivery_rate", 0.0),
                "open_rate": analytics.get("open_rate", 0.0),
                "click_rate": analytics.get("click_rate", 0.0),
                "bounce_rate": analytics.get("bounce_rate", 0.0),
                "unsubscribe_rate": analytics.get("unsubscribe_rate", 0.0)
            },
            "recent_events": recent_events,
            "top_links": top_links
        }

        return response_data

    except Exception as e:
        logger.error(f"Error getting campaign analytics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

async def get_top_clicked_links(campaign_id: str, limit: int = 10):
    """Get top clicked links for a campaign"""
    events_collection = get_email_events_collection()

    pipeline = [
        {"$match": {"campaign_id": ObjectId(campaign_id), "event_type": "clicked"}},
        {"$group": {"_id": "$url", "clicks": {"$sum": 1}}},
        {"$sort": {"clicks": -1}},
        {"$limit": limit},
        {"$project": {"url": "$_id", "clicks": 1, "_id": 0}}
    ]

    top_links = []
    async for link in events_collection.aggregate(pipeline):
        top_links.append(link)

    return top_links

# Helper function to update analytics when events occur
async def update_analytics_counters(campaign_id: str, event_type: str, increment: int = 1):
    """Update analytics counters based on email events"""
    analytics_collection = get_analytics_collection()
    campaigns_collection = get_campaigns_collection()

    # Get campaign sent count for rate calculations
    campaign = await campaigns_collection.find_one(
        {"_id": ObjectId(campaign_id)},
        {"sent_count": 1}
    )
    total_sent = campaign.get("sent_count", 0) if campaign else 0

    # Map event types to analytics fields
    field_mapping = {
        "delivered": "total_delivered",
        "opened": "total_opened",
        "clicked": "total_clicked",
        "bounced": "total_bounced",
        "unsubscribed": "total_unsubscribed",
        "spam_report": "total_spam_reports"
    }

    if event_type not in field_mapping:
        return

    field_name = field_mapping[event_type]

    # Update the counter
    update_result = await analytics_collection.update_one(
        {"campaign_id": ObjectId(campaign_id)},
        {
            "$inc": {field_name: increment},
            "$set": {"updated_at": datetime.utcnow()}
        },
        upsert=True
    )

    # Recalculate rates if we have sent count
    if total_sent > 0:
        # Get updated analytics to calculate rates
        analytics = await analytics_collection.find_one({"campaign_id": ObjectId(campaign_id)})
        if analytics:
            rates_update = {
                "delivery_rate": round(((total_sent - analytics.get("total_bounced", 0)) / total_sent) * 100, 1),
                "open_rate": round((analytics.get("total_opened", 0) / total_sent) * 100, 1),
                "click_rate": round((analytics.get("total_clicked", 0) / total_sent) * 100, 1),
                "bounce_rate": round((analytics.get("total_bounced", 0) / total_sent) * 100, 1),
                "unsubscribe_rate": round((analytics.get("total_unsubscribed", 0) / total_sent) * 100, 1),
                "updated_at": datetime.utcnow()
            }

            await analytics_collection.update_one(
                {"campaign_id": ObjectId(campaign_id)},
                {"$set": rates_update}
            )


@router.get("/dashboard")
async def get_analytics_dashboard(days: int = Query(default=30, ge=1, le=365)):
    """Get dashboard analytics for multiple campaigns"""
    try:
        campaigns_collection = get_campaigns_collection()
        analytics_collection = get_analytics_collection()

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        campaigns = []
        async for campaign in campaigns_collection.find(
            {"created_at": {"$gte": start_date, "$lte": end_date}}
        ).sort("created_at", -1):
            campaign["_id"] = str(campaign["_id"])

            analytics = await analytics_collection.find_one({"campaign_id": campaign["_id"]})
            if analytics:
                analytics["_id"] = str(analytics["_id"])
                analytics["campaign_id"] = str(analytics["campaign_id"])
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

        # Summary metrics
        total_campaigns = len(campaigns)
        total_sent = sum(c["analytics"].get("total_sent", 0) for c in campaigns)
        total_opened = sum(c["analytics"].get("total_opened", 0) for c in campaigns)
        total_clicked = sum(c["analytics"].get("total_clicked", 0) for c in campaigns)

        avg_open_rate = (total_opened / total_sent * 100) if total_sent else 0
        avg_click_rate = (total_clicked / total_sent * 100) if total_sent else 0

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
        logger.error(f"Error getting dashboard analytics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
