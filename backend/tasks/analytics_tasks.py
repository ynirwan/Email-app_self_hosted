# backend/tasks/analytics_tasks.py - FIXED VERSION
import logging
from datetime import datetime, timedelta
from bson import ObjectId
from celery_app import celery_app
from database_sync import get_sync_analytics_collection, get_sync_campaigns_collection, get_sync_email_logs_collection

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, queue="analytics", name="tasks.update_campaign_analytics")
def update_campaign_analytics(self):
    """Update campaign analytics periodically"""
    try:
        campaigns_collection = get_sync_campaigns_collection()
        analytics_collection = get_sync_analytics_collection()
        email_logs_collection = get_sync_email_logs_collection()
        
        # Get active campaigns
        active_campaigns = campaigns_collection.find({
            "status": {"$in": ["sending", "completed"]},
            "started_at": {"$gte": datetime.utcnow() - timedelta(hours=24)}
        })
        
        updated_count = 0
        
        for campaign in active_campaigns:
            campaign_id = campaign["_id"]
            
            # Aggregate email stats
            pipeline = [
                {"$match": {"campaign_id": campaign_id}},
                {"$group": {
                    "_id": "$latest_status",
                    "count": {"$sum": 1}
                }}
            ]
            
            stats = list(email_logs_collection.aggregate(pipeline))
            status_counts = {stat["_id"]: stat["count"] for stat in stats}
            
            # Update analytics
            analytics_collection.update_one(
                {"campaign_id": campaign_id},
                {"$set": {
                    "sent_count": status_counts.get("sent", 0),
                    "delivered_count": status_counts.get("delivered", 0),
                    "failed_count": status_counts.get("failed", 0),
                    "bounce_count": status_counts.get("bounced", 0),
                    "complaint_count": status_counts.get("complained", 0),
                    "open_count": status_counts.get("opened", 0),
                    "click_count": status_counts.get("clicked", 0),
                    "updated_at": datetime.utcnow()
                }},
                upsert=True
            )
            updated_count += 1
        
        logger.info(f"Campaign analytics updated for {updated_count} campaigns")
        return {"status": "completed", "updated_campaigns": updated_count}
        
    except Exception as e:
        logger.exception("Analytics update error")
        raise

@celery_app.task(bind=True, queue="analytics", name="tasks.generate_reports")
def generate_reports(self, report_type: str, campaign_id: str = None):
    """Generate analytics reports"""
    try:
        analytics_collection = get_sync_analytics_collection()
        campaigns_collection = get_sync_campaigns_collection()
        
        if report_type == "campaign_summary":
            if campaign_id:
                # Single campaign report
                analytics = analytics_collection.find_one({"campaign_id": ObjectId(campaign_id)})
                campaign = campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
                
                if analytics and campaign:
                    report = {
                        "campaign_title": campaign.get("title"),
                        "total_sent": analytics.get("sent_count", 0),
                        "total_delivered": analytics.get("delivered_count", 0),
                        "delivery_rate": (analytics.get("delivered_count", 0) / max(analytics.get("sent_count", 0), 1)) * 100,
                        "bounce_rate": (analytics.get("bounce_count", 0) / max(analytics.get("sent_count", 0), 1)) * 100,
                        "complaint_rate": (analytics.get("complaint_count", 0) / max(analytics.get("sent_count", 0), 1)) * 100,
                        "generated_at": datetime.utcnow()
                    }
                    return {"status": "completed", "report": report}
            
            # All campaigns summary
            pipeline = [
                {"$group": {
                    "_id": None,
                    "total_campaigns": {"$sum": 1},
                    "total_sent": {"$sum": "$sent_count"},
                    "total_delivered": {"$sum": "$delivered_count"},
                    "total_bounced": {"$sum": "$bounce_count"},
                    "total_complaints": {"$sum": "$complaint_count"}
                }}
            ]
            
            result = list(analytics_collection.aggregate(pipeline))
            if result:
                summary = result[0]
                report = {
                    "total_campaigns": summary.get("total_campaigns", 0),
                    "overall_sent": summary.get("total_sent", 0),
                    "overall_delivered": summary.get("total_delivered", 0),
                    "overall_delivery_rate": (summary.get("total_delivered", 0) / max(summary.get("total_sent", 0), 1)) * 100,
                    "generated_at": datetime.utcnow()
                }
                return {"status": "completed", "report": report}
        
        logger.info(f"Report generated: {report_type}")
        return {"status": "completed", "report_type": report_type}
        
    except Exception as e:
        logger.exception("Report generation error")
        raise

@celery_app.task(bind=True, queue="analytics", name="tasks.track_email_sending_throughput")
def track_email_sending_throughput(self):
    """Track email sending throughput - simplified version"""
    try:
        email_logs_collection = get_sync_email_logs_collection()
        campaigns_collection = get_sync_campaigns_collection()
        
        # Count emails sent in the last 5 minutes
        five_minutes_ago = datetime.utcnow() - timedelta(minutes=5)
        
        recent_sent = email_logs_collection.count_documents({
            "latest_status": "sent",
            "sent_at": {"$gte": five_minutes_ago}
        })
        
        # Count active campaigns
        active_campaigns = campaigns_collection.count_documents({
            "status": "sending"
        })
        
        throughput_per_hour = (recent_sent / 5) * 60
        
        logger.info(f"Email throughput: {recent_sent} emails in 5 min, ~{throughput_per_hour:.0f}/hour")
        
        return {
            "emails_per_minute": recent_sent / 5,
            "emails_per_hour_projection": throughput_per_hour,
            "active_campaigns": active_campaigns,
            "timestamp": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"Throughput tracking failed: {e}")
        return {"error": str(e)}

