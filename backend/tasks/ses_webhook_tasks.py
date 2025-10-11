# backend/tasks/ses_webhook_tasks.py - FIXED VERSION
import json
import logging
from datetime import datetime
from bson import ObjectId
from celery_app import celery_app
from database_sync import (
    get_sync_email_logs_collection, 
    get_sync_analytics_collection, 
    get_sync_subscribers_collection
)
import redis
from pymongo import UpdateOne
import os

logger = logging.getLogger(__name__)
redis_client = redis.Redis(host='redis', port=6379, db=0, decode_responses=True)

BATCH_SIZE = int(os.getenv("SES_BATCH_SIZE", "200"))
CRITICAL_BATCH_SIZE = int(os.getenv("SES_CRITICAL_BATCH_SIZE", "50"))

@celery_app.task(bind=True, max_retries=3, queue="ses_events", name="tasks.process_ses_events_batch")
def process_ses_events_batch(self):
    """Process SES webhook events in batches"""
    try:
        events = []
        
        # Get events from Redis queue
        for _ in range(BATCH_SIZE):
            event_data = redis_client.rpop("ses_events_normal")
            if not event_data:
                break
            try:
                event = json.loads(event_data)
                events.append(event)
            except json.JSONDecodeError:
                continue
        
        if not events:
            return {"processed": 0, "message": "no_events"}
        
        # Process events
        results = process_ses_batch(events, is_critical=False)
        
        # Schedule next task if more events pending
        remaining = redis_client.llen("ses_events_normal")
        if remaining > 0:
            process_ses_events_batch.apply_async(countdown=0.1)
        
        return results
        
    except Exception as e:
        logger.exception("SES batch processing error")
        raise self.retry(countdown=60, exc=e)

@celery_app.task(bind=True, max_retries=3, queue="ses_critical", name="tasks.process_critical_ses_events")
def process_critical_ses_events(self):
    """Process critical SES events (bounces/complaints)"""
    try:
        events = []
        
        # Get critical events
        for _ in range(CRITICAL_BATCH_SIZE):
            event_data = redis_client.rpop("ses_events_critical")
            if not event_data:
                break
            try:
                event = json.loads(event_data)
                events.append(event)
            except json.JSONDecodeError:
                continue
        
        if not events:
            return {"processed": 0, "message": "no_critical_events"}
        
        # Process critical events
        results = process_ses_batch(events, is_critical=True)
        
        # Process remaining immediately
        remaining = redis_client.llen("ses_events_critical")
        if remaining > 0:
            process_critical_ses_events.apply_async(countdown=0.1)
        
        return results
        
    except Exception as e:
        logger.exception("Critical SES events processing error")
        raise self.retry(countdown=30, exc=e)

def process_ses_batch(events, is_critical=False):
    """Process SES events batch with implementation"""
    email_logs_collection = get_sync_email_logs_collection()
    analytics_collection = get_sync_analytics_collection()
    subscribers_collection = get_sync_subscribers_collection()
    
    email_log_operations = []
    subscriber_updates = []
    analytics_updates = {}
    
    processed_count = 0
    failed_count = 0
    
    for event in events:
        try:
            message_data = json.loads(event["Message"])
            event_type = message_data.get("eventType", "").lower()
            message_id = message_data.get("mail", {}).get("messageId")
            
            if not message_id:
                failed_count += 1
                continue
            
            # Find email log
            email_log = email_logs_collection.find_one({"message_id": message_id})
            if not email_log:
                failed_count += 1
                continue
            
            # Prepare updates
            email_update = prepare_email_log_update(email_log, event_type, message_data)
            if email_update:
                email_log_operations.append(email_update)
            
            # Prepare subscriber updates for critical events
            if is_critical and event_type in ["bounce", "complaint"]:
                subscriber_update = prepare_subscriber_update(email_log, event_type, message_data)
                if subscriber_update:
                    subscriber_updates.append(subscriber_update)
            
            # Aggregate analytics updates
            campaign_id = str(email_log["campaign_id"])
            if campaign_id not in analytics_updates:
                analytics_updates[campaign_id] = {}
            
            analytics_field = map_ses_event_to_analytics(event_type)
            if analytics_field:
                analytics_updates[campaign_id][analytics_field] = analytics_updates[campaign_id].get(analytics_field, 0) + 1
            
            processed_count += 1
            
        except Exception as e:
            logger.error(f"SES event processing error: {e}")
            failed_count += 1
    
    # Execute bulk operations
    bulk_results = {}
    
    if email_log_operations:
        try:
            result = email_logs_collection.bulk_write(email_log_operations, ordered=False)
            bulk_results["email_logs_modified"] = result.modified_count
        except Exception as e:
            logger.error(f"Email logs bulk write error: {e}")
    
    if subscriber_updates:
        try:
            result = subscribers_collection.bulk_write(subscriber_updates, ordered=False)
            bulk_results["subscribers_modified"] = result.modified_count
        except Exception as e:
            logger.error(f"Subscribers bulk write error: {e}")
    
    if analytics_updates:
        try:
            bulk_update_analytics(analytics_updates, analytics_collection)
            bulk_results["analytics_campaigns_updated"] = len(analytics_updates)
        except Exception as e:
            logger.error(f"Analytics update error: {e}")
    
    return {
        "processed": processed_count,
        "failed": failed_count,
        "total": len(events),
        "is_critical": is_critical,
        "bulk_results": bulk_results
    }

def prepare_email_log_update(email_log, event_type, message_data):
    """Prepare email log update operation"""
    from pymongo import UpdateOne
    
    update_doc = {
        "latest_status": event_type,
        "last_event_at": datetime.utcnow()
    }
    
    push_doc = {
        "status_history": {
            "status": event_type,
            "ts": datetime.utcnow(),
            "message_id": message_data.get("mail", {}).get("messageId")
        }
    }
    
    if event_type == "delivery":
        update_doc["delivered_at"] = datetime.utcnow()
    elif event_type == "open":
        update_doc["opened_at"] = datetime.utcnow()
        return UpdateOne(
            {"_id": email_log["_id"]}, 
            {"$set": update_doc, "$inc": {"open_count": 1}, "$push": push_doc}
        )
    elif event_type == "click":
        update_doc["clicked_at"] = datetime.utcnow()
        click_data = message_data.get("click", {})
        if click_data.get("link"):
            push_doc["status_history"]["clicked_link"] = click_data["link"]
        return UpdateOne(
            {"_id": email_log["_id"]}, 
            {"$set": update_doc, "$inc": {"click_count": 1}, "$push": push_doc}
        )
    elif event_type == "bounce":
        update_doc["bounced_at"] = datetime.utcnow()
        bounce_data = message_data.get("bounce", {})
        push_doc["status_history"]["bounce_type"] = bounce_data.get("bounceType", "unknown")
        if bounce_data.get("bounceType") == "Permanent":
            update_doc["permanent_bounce"] = True
    elif event_type == "complaint":
        update_doc["complained_at"] = datetime.utcnow()
        complaint_data = message_data.get("complaint", {})
        push_doc["status_history"]["complaint_type"] = complaint_data.get("complaintFeedbackType", "unknown")
    
    return UpdateOne({"_id": email_log["_id"]}, {"$set": update_doc, "$push": push_doc})

def prepare_subscriber_update(email_log, event_type, message_data):
    """Prepare subscriber status update for suppressions"""
    from pymongo import UpdateOne
    
    if event_type == "bounce":
        bounce_data = message_data.get("bounce", {})
        if bounce_data.get("bounceType") == "Permanent":
            return UpdateOne(
                {"_id": ObjectId(email_log["subscriber_id"])},
                {"$set": {
                    "status": "bounced",
                    "bounced_at": datetime.utcnow(),
                    "bounce_reason": bounce_data.get("bounceSubType", "unknown"),
                    "is_suppressed": True
                }}
            )
    elif event_type == "complaint":
        complaint_data = message_data.get("complaint", {})
        return UpdateOne(
            {"_id": ObjectId(email_log["subscriber_id"])},
            {"$set": {
                "status": "complained",
                "complained_at": datetime.utcnow(),
                "complaint_type": complaint_data.get("complaintFeedbackType", "unknown"),
                "is_suppressed": True
            }}
        )
    
    return None

def map_ses_event_to_analytics(event_type):
    """Map SES event types to analytics fields"""
    mapping = {
        "delivery": "total_delivered",
        "open": "total_opened", 
        "click": "total_clicked",
        "bounce": "total_bounced",
        "complaint": "total_spam_reports"
    }
    return mapping.get(event_type)

def bulk_update_analytics(analytics_updates, analytics_collection):
    """Bulk update analytics collection"""
    from pymongo import UpdateOne
    
    operations = []
    for campaign_id, updates in analytics_updates.items():
        inc_doc = {}
        for field, count in updates.items():
            inc_doc[field] = count
        
        if inc_doc:
            operations.append(UpdateOne(
                {"campaign_id": ObjectId(campaign_id)},
                {"$inc": inc_doc, "$set": {"updated_at": datetime.utcnow()}},
                upsert=True
            ))
    
    if operations:
        try:
            result = analytics_collection.bulk_write(operations, ordered=False)
            logger.info(f"Analytics bulk update: {result.modified_count} campaigns updated")
        except Exception as e:
            logger.error(f"Analytics bulk update error: {e}")

