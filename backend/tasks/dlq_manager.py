# backend/tasks/dlq_manager.py - COMPLETE DLQ SYSTEM
"""
Production-ready Dead Letter Queue system
Handles failed tasks, retry logic, and failure analysis
"""
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from bson import ObjectId
from celery_app import celery_app
from database_pool import get_sync_campaigns_collection, get_sync_dlq_collection, get_sync_email_logs_collection
from core.campaign_config import settings, get_redis_key
import redis

logger = logging.getLogger(__name__)

class DLQManager:
    """Dead Letter Queue manager for failed email tasks"""
    
    def __init__(self):
        self.redis_client = redis.Redis.from_url(settings.REDIS_URL)
    
    def send_to_dlq(self, campaign_id: str, subscriber_id: str, email: str, 
                    error_info: Dict, retry_count: int = 0) -> Dict[str, Any]:
        """Send failed email to Dead Letter Queue"""
        try:
            dlq_collection = get_sync_dlq_collection()
            
            dlq_record = {
                "campaign_id": ObjectId(campaign_id),
                "subscriber_id": subscriber_id,
                "email": email,
                "error_info": error_info,
                "retry_count": retry_count,
                "created_at": datetime.utcnow(),
                "last_attempt_at": datetime.utcnow(),
                "status": "dlq_pending",
                "failure_type": self._classify_failure(error_info),
                "can_retry": self._can_retry(error_info),
                "next_retry_at": self._calculate_next_retry(retry_count) if self._can_retry(error_info) else None,
                "metadata": {
                    "original_task_id": error_info.get("task_id"),
                    "worker_name": error_info.get("worker_name"),
                    "queue_name": error_info.get("queue_name", "campaigns")
                }
            }
            
            result = dlq_collection.insert_one(dlq_record)
            dlq_id = str(result.inserted_id)
            
            # Update campaign DLQ statistics
            self._update_campaign_dlq_stats(campaign_id)
            
            # Store in Redis for quick access
            redis_key = get_redis_key("dlq_recent", dlq_id)
            self.redis_client.setex(redis_key, 3600, json.dumps({
                "campaign_id": campaign_id,
                "subscriber_id": subscriber_id,
                "email": email,
                "failure_type": dlq_record["failure_type"],
                "created_at": dlq_record["created_at"].isoformat()
            }))
            
            logger.warning(f"Email sent to DLQ: {campaign_id}/{subscriber_id} - {dlq_record['failure_type']}")
            
            return {
                "dlq_id": dlq_id,
                "status": "dlq_created",
                "failure_type": dlq_record["failure_type"],
                "can_retry": dlq_record["can_retry"],
                "next_retry_at": dlq_record["next_retry_at"].isoformat() if dlq_record["next_retry_at"] else None
            }
            
        except Exception as e:
            logger.error(f"Failed to send to DLQ: {e}")
            return {"error": str(e), "status": "dlq_failed"}
    
    def _classify_failure(self, error_info: Dict) -> str:
        """Classify the type of failure"""
        error_message = str(error_info.get("error", "")).lower()
        
        # SMTP/Email service errors
        if any(keyword in error_message for keyword in ['535', 'authentication', 'credential']):
            return "smtp_auth_error"
        elif any(keyword in error_message for keyword in ['550', 'mailbox', 'recipient']):
            return "invalid_recipient"
        elif any(keyword in error_message for keyword in ['552', 'mailbox full', 'quota']):
            return "mailbox_full"
        elif any(keyword in error_message for keyword in ['554', 'spam', 'blocked']):
            return "spam_blocked"
        elif any(keyword in error_message for keyword in ['timeout', 'connection']):
            return "connection_timeout"
        elif any(keyword in error_message for keyword in ['rate', 'throttle', '429']):
            return "rate_limited"
        
        # System errors
        elif any(keyword in error_message for keyword in ['memory', 'oom']):
            return "system_memory_error"
        elif any(keyword in error_message for keyword in ['database', 'mongo']):
            return "database_error"
        elif any(keyword in error_message for keyword in ['redis', 'cache']):
            return "cache_error"
        
        # Content errors
        elif any(keyword in error_message for keyword in ['template', 'render']):
            return "template_error"
        elif any(keyword in error_message for keyword in ['encoding', 'character']):
            return "encoding_error"
        
        else:
            return "unknown_error"
    
    def _can_retry(self, error_info: Dict) -> bool:
        """Determine if the error can be retried"""
        error_message = str(error_info.get("error", "")).lower()
        
        # Non-retryable errors (permanent failures)
        non_retryable = [
            'invalid_recipient', 'mailbox_full', 'spam_blocked', 
            'template_error', 'encoding_error'
        ]
        
        failure_type = self._classify_failure(error_info)
        
        if failure_type in non_retryable:
            return False
        
        # Check retry count
        retry_count = error_info.get("retry_count", 0)
        if retry_count >= settings.MAX_EMAIL_RETRIES:
            return False
        
        return True
    
    def _calculate_next_retry(self, retry_count: int) -> datetime:
        """Calculate next retry time with exponential backoff"""
        delay_seconds = settings.RETRY_BACKOFF_BASE_SECONDS * (2 ** retry_count)
        max_delay = 3600 * 4  # Maximum 4 hours
        delay_seconds = min(delay_seconds, max_delay)
        
        return datetime.utcnow() + timedelta(seconds=delay_seconds)
    
    def _update_campaign_dlq_stats(self, campaign_id: str):
        """Update campaign DLQ statistics"""
        try:
            campaigns_collection = get_sync_campaigns_collection()
            campaigns_collection.update_one(
                {"_id": ObjectId(campaign_id)},
                {"$inc": {"dlq_count": 1, "failed_count": 1}}
            )
        except Exception as e:
            logger.error(f"Failed to update campaign DLQ stats: {e}")

@celery_app.task(bind=True, queue="dlq", name="tasks.handle_failed_email")
def handle_failed_email(self, campaign_id: str, subscriber_id: str, email: str, error_info: Dict):
    """Handle emails that failed after all retries"""
    try:
        dlq_manager = DLQManager()
        
        # Enhance error info
        enhanced_error_info = {
            **error_info,
            "worker_name": self.request.hostname,
            "task_id": self.request.id,
            "queue_name": getattr(self.request, 'delivery_info', {}).get('routing_key', 'unknown')
        }
        
        result = dlq_manager.send_to_dlq(campaign_id, subscriber_id, email, enhanced_error_info)
        
        return result
        
    except Exception as e:
        logger.error(f"DLQ handling failed: {e}")
        return {"status": "dlq_handler_failed", "error": str(e)}

@celery_app.task(bind=True, queue="dlq", name="tasks.process_dlq_retries")
def process_dlq_retries(self):
    """Process DLQ entries that are ready for retry"""
    try:
        dlq_collection = get_sync_dlq_collection()
        
        # Find DLQ entries ready for retry
        now = datetime.utcnow()
        retry_candidates = dlq_collection.find({
            "status": "dlq_pending",
            "can_retry": True,
            "next_retry_at": {"$lte": now},
            "retry_count": {"$lt": settings.MAX_EMAIL_RETRIES}
        }).limit(100)  # Process up to 100 retries at once
        
        processed = 0
        failed = 0
        
        for dlq_entry in retry_candidates:
            try:
                # Update retry count and status
                new_retry_count = dlq_entry["retry_count"] + 1
                
                dlq_collection.update_one(
                    {"_id": dlq_entry["_id"]},
                    {
                        "$set": {
                            "status": "retrying",
                            "retry_count": new_retry_count,
                            "last_attempt_at": now
                        }
                    }
                )
                
                # Queue the email for retry
                from tasks.email_campaign_tasks import send_single_campaign_email
                
                retry_task = send_single_campaign_email.apply_async(
                    args=[str(dlq_entry["campaign_id"]), dlq_entry["subscriber_id"]],
                    queue="campaigns",
                    retry_policy={
                        'max_retries': 1,
                        'interval_start': 0,
                        'interval_step': 0
                    }
                )
                
                # Update DLQ entry with retry task info
                dlq_collection.update_one(
                    {"_id": dlq_entry["_id"]},
                    {
                        "$set": {
                            "retry_task_id": retry_task.id,
                            "next_retry_at": DLQManager()._calculate_next_retry(new_retry_count) if new_retry_count < settings.MAX_EMAIL_RETRIES else None
                        }
                    }
                )
                
                processed += 1
                
            except Exception as e:
                logger.error(f"Failed to process DLQ retry for {dlq_entry['_id']}: {e}")
                failed += 1
                
                # Mark as failed
                dlq_collection.update_one(
                    {"_id": dlq_entry["_id"]},
                    {"$set": {"status": "retry_failed", "retry_error": str(e)}}
                )
        
        logger.info(f"DLQ retry processing: {processed} processed, {failed} failed")
        
        return {
            "processed": processed,
            "failed": failed,
            "total_found": processed + failed
        }
        
    except Exception as e:
        logger.error(f"DLQ retry processing failed: {e}")
        return {"error": str(e)}

@celery_app.task(bind=True, queue="cleanup", name="tasks.cleanup_old_dlq_entries")
def cleanup_old_dlq_entries(self):
    """Clean up old DLQ entries"""
    try:
        dlq_collection = get_sync_dlq_collection()
        
        # Remove entries older than retention period
        cutoff_date = datetime.utcnow() - timedelta(days=settings.DLQ_RETENTION_DAYS)
        
        # Clean up completed/failed entries first
        result = dlq_collection.delete_many({
            "status": {"$in": ["completed", "permanently_failed", "retry_failed"]},
            "created_at": {"$lt": cutoff_date}
        })
        
        cleaned_count = result.deleted_count
        
        # Archive old pending entries (don't delete in case they're needed)
        archive_result = dlq_collection.update_many(
            {
                "status": "dlq_pending",
                "created_at": {"$lt": cutoff_date}
            },
            {
                "$set": {
                    "status": "archived",
                    "archived_at": datetime.utcnow()
                }
            }
        )
        
        archived_count = archive_result.modified_count
        
        logger.info(f"DLQ cleanup: {cleaned_count} deleted, {archived_count} archived")
        
        return {
            "deleted": cleaned_count,
            "archived": archived_count,
            "total_processed": cleaned_count + archived_count
        }
        
    except Exception as e:
        logger.error(f"DLQ cleanup failed: {e}")
        return {"error": str(e)}

@celery_app.task(bind=True, queue="analytics", name="tasks.generate_dlq_analytics")
def generate_dlq_analytics(self):
    """Generate DLQ analytics and failure patterns"""
    try:
        dlq_collection = get_sync_dlq_collection()
        
        # Analyze failure patterns from last 24 hours
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        
        # Failure type analysis
        failure_type_pipeline = [
            {"$match": {"created_at": {"$gte": twenty_four_hours_ago}}},
            {"$group": {
                "_id": "$failure_type",
                "count": {"$sum": 1},
                "avg_retry_count": {"$avg": "$retry_count"},
                "can_retry_count": {"$sum": {"$cond": ["$can_retry", 1, 0]}}
            }},
            {"$sort": {"count": -1}}
        ]
        
        failure_types = list(dlq_collection.aggregate(failure_type_pipeline))
        
        # Campaign failure analysis
        campaign_pipeline = [
            {"$match": {"created_at": {"$gte": twenty_four_hours_ago}}},
            {"$group": {
                "_id": "$campaign_id",
                "failure_count": {"$sum": 1},
                "failure_types": {"$addToSet": "$failure_type"},
                "latest_failure": {"$max": "$created_at"}
            }},
            {"$sort": {"failure_count": -1}},
            {"$limit": 10}
        ]
        
        campaign_failures = list(dlq_collection.aggregate(campaign_pipeline))
        
        # Hourly failure trend
        hourly_pipeline = [
            {"$match": {"created_at": {"$gte": twenty_four_hours_ago}}},
            {"$group": {
                "_id": {
                    "hour": {"$hour": "$created_at"},
                    "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}
                },
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id": 1}}
        ]
        
        hourly_trend = list(dlq_collection.aggregate(hourly_pipeline))
        
        # Overall statistics
        total_dlq = dlq_collection.count_documents({"created_at": {"$gte": twenty_four_hours_ago}})
        retryable_count = dlq_collection.count_documents({
            "created_at": {"$gte": twenty_four_hours_ago},
            "can_retry": True
        })
        
        analytics = {
            "generated_at": datetime.utcnow().isoformat(),
            "period": "last_24_hours",
            "summary": {
                "total_dlq_entries": total_dlq,
                "retryable_entries": retryable_count,
                "non_retryable_entries": total_dlq - retryable_count,
                "retry_rate": (retryable_count / total_dlq * 100) if total_dlq > 0 else 0
            },
            "failure_types": failure_types,
            "top_failing_campaigns": campaign_failures,
            "hourly_trend": hourly_trend
        }
        
        # Store analytics in Redis
        analytics_key = get_redis_key("dlq_analytics", "latest")
        redis_client = redis.Redis.from_url(settings.REDIS_URL)
        redis_client.setex(analytics_key, 3600, json.dumps(analytics, default=str))
        
        logger.info(f"DLQ analytics generated: {total_dlq} entries analyzed")
        
        return analytics
        
    except Exception as e:
        logger.error(f"DLQ analytics generation failed: {e}")
        return {"error": str(e)}

# Global DLQ manager instance
dlq_manager = DLQManager()

