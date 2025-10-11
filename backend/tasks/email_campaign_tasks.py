# backend/tasks/email_campaign_tasks.py - COMPLETE PRODUCTION-READY EMAIL SYSTEM
"""
Production-ready email campaign tasks with all optimizations
Integrates all systems: resource management, rate limiting, DLQ, metrics, etc.
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from bson import ObjectId
from celery import Celery
from celery_app import celery_app

# Import all production systems
from core.config import settings
from database import (
    get_sync_campaigns_collection, get_sync_email_logs_collection,
    get_sync_subscribers_collection, get_sync_templates_collection
)
from tasks.resource_manager import resource_manager
from tasks.rate_limiter import rate_limiter, EmailProvider, RateLimitResult
from tasks.dlq_manager import dlq_manager
from tasks.campaign_control import campaign_controller
from tasks.metrics_collector import metrics_collector
from tasks.template_cache import template_processor
from tasks.provider_manager import email_provider_manager
from tasks.audit_logger import (
    log_campaign_event, log_email_event, log_system_event,
    AuditEventType, AuditSeverity
)

logger = logging.getLogger(__name__)

def log_email_status(campaign_id: str, subscriber_id: str, email: str, status: str,
                    message_id: str = None, error_reason: str = None, 
                    provider: str = None, cost: float = 0.0):
    """Enhanced email status logging with all production features"""
    try:
        email_logs_collection = get_sync_email_logs_collection()
        
        log_entry = {
            "campaign_id": ObjectId(campaign_id),
            "subscriber_id": subscriber_id,
            "email": email,
            "latest_status": status,
            "message_id": message_id,
            "provider": provider,
            "cost": cost,
            "last_attempted_at": datetime.utcnow(),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        if status == "sent":
            log_entry["sent_at"] = datetime.utcnow()
        elif status == "delivered":
            log_entry["delivered_at"] = datetime.utcnow()
        elif status == "failed":
            log_entry["failure_reason"] = error_reason
            log_entry["failed_at"] = datetime.utcnow()
        
        # Store log entry
        email_logs_collection.insert_one(log_entry)
        
        # Log audit event
        if settings.ENABLE_AUDIT_LOGGING:
            audit_details = {
                "status": status,
                "provider": provider,
                "message_id": message_id,
                "cost": cost
            }
            
            if error_reason:
                audit_details["error"] = error_reason
            
            if status == "sent":
                log_email_event(AuditEventType.EMAIL_SENT, campaign_id, subscriber_id, email, audit_details)
            elif status == "delivered":
                log_email_event(AuditEventType.EMAIL_DELIVERED, campaign_id, subscriber_id, email, audit_details)
            elif status == "failed":
                log_email_event(AuditEventType.EMAIL_FAILED, campaign_id, subscriber_id, email, audit_details)
        
    except Exception as e:
        logger.error(f"Failed to log email status: {e}")

@celery_app.task(
    bind=True,
    max_retries=settings.MAX_EMAIL_RETRIES if hasattr(settings, 'MAX_EMAIL_RETRIES') else 3,
    queue="campaigns",
    name="tasks.send_single_campaign_email",
    soft_time_limit=settings.TASK_TIMEOUT_SECONDS if hasattr(settings, 'TASK_TIMEOUT_SECONDS') else 30
)
def send_single_campaign_email(self, campaign_id: str, subscriber_id: str):
    """
    Production-ready single email sending with all optimizations
    Integrates: resource management, rate limiting, DLQ, provider failover, etc.
    """
    start_time = time.time()
    
    try:
        # ===== STEP 1: RESOURCE AND HEALTH CHECKS =====
        
        # Check system resources
        can_process, reason, health_info = resource_manager.can_process_batch(1, campaign_id)
        if not can_process:
            if reason == "campaign_paused":
                return {"status": "paused", "reason": reason, "campaign_id": campaign_id}
            elif reason == "memory_limit_exceeded":
                # Delay task and retry
                raise self.retry(countdown=60, exc=Exception(f"System overloaded: {reason}"))
            else:
                return {"status": "resource_unavailable", "reason": reason, "health": health_info}
        
        # Check if campaign is stopped or paused
        if campaign_controller.is_campaign_paused(campaign_id):
            return {"status": "paused", "reason": "campaign_paused"}
        
        if campaign_controller.is_campaign_stopped(campaign_id):
            return {"status": "stopped", "reason": "campaign_stopped"}
        
        # ===== STEP 2: DATA RETRIEVAL =====
        
        campaigns_collection = get_sync_campaigns_collection()
        subscribers_collection = get_sync_subscribers_collection()
        email_logs_collection = get_sync_email_logs_collection()
        
        # Get campaign data
        campaign = campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
        if not campaign:
            error_msg = f"Campaign not found: {campaign_id}"
            logger.error(error_msg)
            return {"status": "failed", "reason": "campaign_not_found"}
        
        # Get subscriber data
        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not subscriber:
            error_msg = f"Subscriber not found: {subscriber_id}"
            logger.error(error_msg)
            return {"status": "failed", "reason": "subscriber_not_found"}
        
        recipient_email = subscriber.get("email")
        if not recipient_email:
            error_msg = f"Subscriber email missing: {subscriber_id}"
            logger.error(error_msg)
            return {"status": "failed", "reason": "email_missing"}
        
        # ===== STEP 3: DUPLICATE CHECK WITH OPTIMIZED INDEX =====
        
        # Check if email already sent successfully (uses optimized index)
        existing_sent = email_logs_collection.find_one({
            "campaign_id": ObjectId(campaign_id),
            "subscriber_id": subscriber_id,
            "latest_status": {"$in": ["sent", "delivered"]}
        }, {"_id": 1})
        
        if existing_sent:
            return {"status": "skipped", "reason": "already_sent"}
        
        # ===== STEP 4: RATE LIMITING CHECK =====
        
        if settings.ENABLE_RATE_LIMITING:
            # Determine email provider for rate limiting
            provider_type = EmailProvider.DEFAULT
            email_settings = campaign.get("email_settings", {})
            if email_settings:
                if "sendgrid" in str(email_settings).lower():
                    provider_type = EmailProvider.SENDGRID
                elif "ses" in str(email_settings).lower():
                    provider_type = EmailProvider.SES
                elif "mailgun" in str(email_settings).lower():
                    provider_type = EmailProvider.MAILGUN
                elif "smtp" in str(email_settings).lower():
                    provider_type = EmailProvider.SMTP
            
            # Check rate limits
            can_send, rate_info = rate_limiter.can_send_email(provider_type, campaign_id)
            
            if can_send == RateLimitResult.RATE_LIMITED:
                # Delay and retry
                delay = 60  # Wait 1 minute
                raise self.retry(countdown=delay, exc=Exception(f"Rate limited: {rate_info}"))
            elif can_send == RateLimitResult.CIRCUIT_BREAKER_OPEN:
                # Circuit breaker is open, send to DLQ
                if settings.ENABLE_DLQ:
                    dlq_result = dlq_manager.send_to_dlq(
                        campaign_id, subscriber_id, recipient_email,
                        {"error": "Circuit breaker open", "provider": provider_type.value}
                    )
                    return {"status": "dlq", "reason": "circuit_breaker_open", "dlq_result": dlq_result}
                else:
                    return {"status": "failed", "reason": "circuit_breaker_open"}
        
        # ===== STEP 5: TEMPLATE PROCESSING =====
        
        template_id = campaign.get("template_id")
        if not template_id:
            error_msg = f"Template ID missing for campaign: {campaign_id}"
            logger.error(error_msg)
            return {"status": "failed", "reason": "template_missing"}
        
        # Get template with caching
        template = template_processor.get_template(template_id)
        if not template:
            error_msg = f"Template not found: {template_id}"
            logger.error(error_msg)
            return {"status": "failed", "reason": "template_not_found"}
        
        # Personalize template
        fallback_values = campaign.get("fallback_values", {})
        personalized = template_processor.personalize_template(
            template, subscriber, fallback_values
        )
        
        if "error" in personalized:
            logger.error(f"Template personalization failed: {personalized['error']}")
            return {"status": "failed", "reason": "template_personalization_failed"}
        
        # ===== STEP 6: EMAIL SENDING WITH PROVIDER FAILOVER =====
        
        sender_email = campaign.get("sender_email", "noreply@example.com")
        sender_name = campaign.get("sender_name", "")
        reply_to = campaign.get("reply_to", sender_email)
        
        # Format sender
        from_email = f"{sender_name} <{sender_email}>" if sender_name else sender_email
        
        try:
            # Send email with automatic provider failover
            send_result = email_provider_manager.send_email_with_failover(
                sender_email=from_email,
                recipient_email=recipient_email,
                subject=personalized["subject"],
                html_content=personalized["html_content"],
                text_content=personalized.get("text_content"),
                campaign_id=campaign_id,
                reply_to=reply_to,
                timeout=settings.EMAIL_SEND_TIMEOUT_SECONDS
            )
            
            # ===== STEP 7: RESULT PROCESSING =====
            
            execution_time = time.time() - start_time
            
            if send_result.get("success"):
                # Success - log and update counters
                message_id = send_result.get("message_id")
                provider = send_result.get("selected_provider", "unknown")
                cost = send_result.get("cost", 0.0)
                
                log_email_status(campaign_id, subscriber_id, recipient_email, 
                               "sent", message_id, None, provider, cost)
                
                # Update campaign counters atomically
                campaigns_collection.update_one(
                    {"_id": ObjectId(campaign_id)},
                    {
                        "$inc": {
                            "sent_count": 1,
                            "processed_count": 1,
                            "queued_count": -1
                        },
                        "$set": {"last_batch_at": datetime.utcnow()}
                    }
                )
                
                # Record rate limiter success
                if settings.ENABLE_RATE_LIMITING:
                    rate_limiter.record_email_result(True, provider_type, None, campaign_id)
                
                logger.debug(f"Email sent successfully: {campaign_id}/{subscriber_id}")
                
                return {
                    "status": "sent",
                    "message_id": message_id,
                    "provider": provider,
                    "execution_time": execution_time,
                    "cost": cost,
                    "attempted_providers": send_result.get("attempted_providers", []),
                    "email": recipient_email
                }
            
            else:
                # Failed - handle error
                error_reason = send_result.get("error", "Unknown error")
                attempted_providers = send_result.get("attempted_providers", [])
                
                # Check if this is a permanent failure
                is_permanent = send_result.get("permanent_failure", False)
                
                if is_permanent or self.request.retries >= self.max_retries:
                    # Send to DLQ or mark as permanently failed
                    if settings.ENABLE_DLQ and not is_permanent:
                        dlq_result = dlq_manager.send_to_dlq(
                            campaign_id, subscriber_id, recipient_email,
                            {
                                "error": error_reason,
                                "retry_count": self.request.retries,
                                "attempted_providers": attempted_providers,
                                "task_id": self.request.id
                            }
                        )
                    
                    # Log failure
                    log_email_status(campaign_id, subscriber_id, recipient_email,
                                   "failed", None, error_reason, 
                                   attempted_providers[0] if attempted_providers else "unknown")
                    
                    # Update campaign counters
                    campaigns_collection.update_one(
                        {"_id": ObjectId(campaign_id)},
                        {
                            "$inc": {
                                "failed_count": 1,
                                "processed_count": 1,
                                "queued_count": -1
                            },
                            "$set": {"last_batch_at": datetime.utcnow()}
                        }
                    )
                    
                    # Record rate limiter failure
                    if settings.ENABLE_RATE_LIMITING:
                        rate_limiter.record_email_result(False, provider_type, error_reason, campaign_id)
                    
                    return {
                        "status": "failed" if is_permanent else "dlq",
                        "reason": "permanent_failure" if is_permanent else "max_retries_exceeded",
                        "error": error_reason,
                        "execution_time": execution_time,
                        "attempted_providers": attempted_providers,
                        "retry_count": self.request.retries
                    }
                
                else:
                    # Retry with exponential backoff
                    countdown = settings.RETRY_BACKOFF_BASE_SECONDS * (2 ** self.request.retries)
                    max_countdown = 3600  # Max 1 hour
                    countdown = min(countdown, max_countdown)
                    
                    logger.warning(f"Email send failed, retrying in {countdown}s: {error_reason}")
                    
                    raise self.retry(countdown=countdown, exc=Exception(error_reason))
        
        except Exception as e:
            if self.request.retries >= self.max_retries:
                # Final failure
                error_msg = str(e)
                
                if settings.ENABLE_DLQ:
                    dlq_result = dlq_manager.send_to_dlq(
                        campaign_id, subscriber_id, recipient_email,
                        {
                            "error": error_msg,
                            "retry_count": self.request.retries,
                            "task_id": self.request.id,
                            "exception": "send_exception"
                        }
                    )
                
                log_email_status(campaign_id, subscriber_id, recipient_email,
                               "failed", None, error_msg, "unknown")
                
                campaigns_collection.update_one(
                    {"_id": ObjectId(campaign_id)},
                    {
                        "$inc": {
                            "failed_count": 1,
                            "processed_count": 1,
                            "queued_count": -1
                        },
                        "$set": {"last_batch_at": datetime.utcnow()}
                    }
                )
                
                return {
                    "status": "failed",
                    "reason": "send_exception",
                    "error": error_msg,
                    "execution_time": time.time() - start_time,
                    "retry_count": self.request.retries
                }
            else:
                # Retry
                raise self.retry(countdown=60, exc=e)
    
    except Exception as e:
        # Catch-all exception handler
        execution_time = time.time() - start_time
        error_msg = str(e)
        
        logger.error(f"Email task failed with exception: {error_msg}")
        
        return {
            "status": "failed",
            "reason": "task_exception",
            "error": error_msg,
            "execution_time": execution_time,
            "campaign_id": campaign_id,
            "subscriber_id": subscriber_id
        }

@celery_app.task(
    bind=True,
    queue="campaigns",
    name="tasks.send_campaign_batch",
    soft_time_limit=300  # 5 minutes
)
def send_campaign_batch(self, campaign_id: str, batch_size: int = None, last_id: str = None):
    """
    Production-ready batch processing with resource management
    """
    try:
        start_time = time.time()
        
        # ===== RESOURCE MANAGEMENT =====
        
        if not batch_size:
            batch_size = settings.MAX_BATCH_SIZE
        
        # Get optimal batch size based on current system resources
        optimal_batch_size = resource_manager.get_optimal_batch_size(batch_size, campaign_id)
        
        if optimal_batch_size < batch_size:
            logger.info(f"Reduced batch size from {batch_size} to {optimal_batch_size} due to system resources")
            batch_size = optimal_batch_size
        
        # ===== CAMPAIGN STATUS CHECK =====
        
        campaigns_collection = get_sync_campaigns_collection()
        campaign = campaigns_collection.find_one(
            {"_id": ObjectId(campaign_id)},
            {"status": 1, "target_lists": 1, "target_list_count": 1, "processed_count": 1}
        )
        
        if not campaign:
            return {"error": "campaign_not_found", "campaign_id": campaign_id}
        
        if campaign.get("status") != "sending":
            return {
                "status": "campaign_not_sending",
                "current_status": campaign.get("status"),
                "campaign_id": campaign_id
            }
        
        # Check if campaign is paused or stopped
        if campaign_controller.is_campaign_paused(campaign_id):
            return {"status": "paused", "campaign_id": campaign_id}
        
        if campaign_controller.is_campaign_stopped(campaign_id):
            return {"status": "stopped", "campaign_id": campaign_id}
        
        # ===== GET SUBSCRIBERS =====
        
        subscribers = get_subscribers_for_campaign(campaign_id, batch_size, last_id)
        
        if not subscribers:
            # No more subscribers - check if campaign is complete
            processed_count = campaign.get("processed_count", 0)
            target_count = campaign.get("target_list_count", 0)
            
            if processed_count >= target_count or not target_count:
                # Campaign complete
                finalize_campaign_result = finalize_campaign(campaign_id)
                return {
                    "status": "campaign_completed",
                    "processed_count": processed_count,
                    "target_count": target_count,
                    "finalize_result": finalize_campaign_result
                }
            else:
                return {
                    "status": "no_subscribers_found",
                    "processed_count": processed_count,
                    "target_count": target_count
                }
        
        # ===== BATCH DUPLICATE CHECK =====
        
        # Get subscriber IDs for batch duplicate check
        subscriber_ids = [str(sub["_id"]) for sub in subscribers]
        
        # Check for already sent emails in batch
        email_logs_collection = get_sync_email_logs_collection()
        already_sent = email_logs_collection.find({
            "campaign_id": ObjectId(campaign_id),
            "subscriber_id": {"$in": subscriber_ids},
            "latest_status": {"$in": ["sent", "delivered"]}
        }, {"subscriber_id": 1})
        
        already_sent_ids = {log["subscriber_id"] for log in already_sent}
        
        # Filter out already sent subscribers
        new_subscribers = [
            sub for sub in subscribers 
            if str(sub["_id"]) not in already_sent_ids
        ]
        
        logger.info(f"Batch {campaign_id}: {len(subscribers)} total, {len(already_sent_ids)} already sent, {len(new_subscribers)} new")
        
        if not new_subscribers:
            # All subscribers already processed, continue to next batch
            last_subscriber = subscribers[-1]
            next_task = send_campaign_batch.delay(campaign_id, batch_size, str(last_subscriber["_id"]))
            
            return {
                "status": "batch_already_processed",
                "total_subscribers": len(subscribers),
                "next_task_id": next_task.id
            }
        
        # ===== QUEUE INDIVIDUAL EMAILS =====
        
        queued_tasks = []
        
        for subscriber in new_subscribers:
            try:
                task = send_single_campaign_email.delay(campaign_id, str(subscriber["_id"]))
                queued_tasks.append(task.id)
            except Exception as e:
                logger.error(f"Failed to queue email task: {e}")
        
        # ===== UPDATE CAMPAIGN COUNTERS =====
        
        campaigns_collection.update_one(
            {"_id": ObjectId(campaign_id)},
            {
                "$inc": {"queued_count": len(queued_tasks)},
                "$set": {"last_batch_at": datetime.utcnow()}
            }
        )
        
        # ===== SCHEDULE NEXT BATCH =====
        
        if len(subscribers) == batch_size:  # Full batch means there might be more
            last_subscriber = subscribers[-1]
            next_batch_delay = 30  # Wait 30 seconds between batches
            
            next_task = send_campaign_batch.apply_async(
                args=[campaign_id, batch_size, str(last_subscriber["_id"])],
                countdown=next_batch_delay
            )
            
            next_task_id = next_task.id
        else:
            next_task_id = None
        
        execution_time = time.time() - start_time
        
        return {
            "status": "batch_processed",
            "campaign_id": campaign_id,
            "batch_size": len(new_subscribers),
            "queued_tasks": len(queued_tasks),
            "already_sent": len(already_sent_ids),
            "next_task_id": next_task_id,
            "execution_time": execution_time,
            "last_subscriber_id": str(subscribers[-1]["_id"]) if subscribers else None
        }
        
    except Exception as e:
        logger.error(f"Batch processing failed for {campaign_id}: {e}")
        return {
            "error": str(e),
            "campaign_id": campaign_id,
            "batch_size": batch_size,
            "last_id": last_id
        }

def get_subscribers_for_campaign(campaign_id: str, batch_size: int, last_id: str = None) -> List[Dict]:
    """Get subscribers for campaign batch with pagination"""
    try:
        campaigns_collection = get_sync_campaigns_collection()
        subscribers_collection = get_sync_subscribers_collection()
        
        # Get campaign target lists
        campaign = campaigns_collection.find_one(
            {"_id": ObjectId(campaign_id)},
            {"target_lists": 1, "target_segments": 1}
        )
        
        if not campaign:
            return []
        
        target_lists = campaign.get("target_lists", [])
        target_segments = campaign.get("target_segments", [])
        
        # Build query
        query = {"email": {"$exists": True, "$ne": ""}}
        
        # Add list filter
        if target_lists:
            query["$or"] = [
                {"lists": {"$in": target_lists}},
                {"list": {"$in": target_lists}}  # Legacy field
            ]
        
        # Add pagination
        if last_id:
            query["_id"] = {"$gt": ObjectId(last_id)}
        
        # Get subscribers
        subscribers = list(subscribers_collection.find(query)
                         .sort("_id", 1)
                         .limit(batch_size))
        
        return subscribers
        
    except Exception as e:
        logger.error(f"Failed to get subscribers for campaign {campaign_id}: {e}")
        return []

def finalize_campaign(campaign_id: str) -> Dict[str, Any]:
    """Finalize completed campaign"""
    try:
        campaigns_collection = get_sync_campaigns_collection()
        email_logs_collection = get_sync_email_logs_collection()
        
        # Get final statistics from email logs
        stats_pipeline = [
            {"$match": {"campaign_id": ObjectId(campaign_id)}},
            {"$group": {"_id": "$latest_status", "count": {"$sum": 1}}}
        ]
        
        final_stats = list(email_logs_collection.aggregate(stats_pipeline))
        status_counts = {stat["_id"]: stat["count"] for stat in final_stats}
        
        total_processed = sum(status_counts.values())
        sent_count = status_counts.get("sent", 0)
        delivered_count = status_counts.get("delivered", 0)
        failed_count = status_counts.get("failed", 0)
        
        # Determine final campaign status
        if sent_count > 0 or delivered_count > 0:
            final_status = "completed"
        else:
            final_status = "failed"
        
        # Update campaign
        campaigns_collection.update_one(
            {"_id": ObjectId(campaign_id)},
            {
                "$set": {
                    "status": final_status,
                    "completed_at": datetime.utcnow(),
                    "sent_count": sent_count,
                    "delivered_count": delivered_count,
                    "failed_count": failed_count,
                    "processed_count": total_processed,
                    "queued_count": 0,
                    "final_stats": status_counts
                }
            }
        )
        
        # Log campaign completion
        if settings.ENABLE_AUDIT_LOGGING:
            log_campaign_event(
                AuditEventType.CAMPAIGN_COMPLETED,
                campaign_id,
                {
                    "final_status": final_status,
                    "total_processed": total_processed,
                    "sent_count": sent_count,
                    "failed_count": failed_count,
                    "final_stats": status_counts
                }
            )
        
        logger.info(f"Campaign {campaign_id} finalized: {final_status} - {total_processed} processed")
        
        return {
            "status": final_status,
            "total_processed": total_processed,
            "final_stats": status_counts,
            "completed_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Campaign finalization failed for {campaign_id}: {e}")
        return {"error": str(e)}

@celery_app.task(bind=True, queue="campaigns", name="tasks.start_campaign")
def start_campaign(self, campaign_id: str):
    """Start a campaign with production safety checks"""
    try:
        campaigns_collection = get_sync_campaigns_collection()
        
        # Update campaign status
        result = campaigns_collection.update_one(
            {"_id": ObjectId(campaign_id), "status": {"$in": ["draft", "scheduled"]}},
            {
                "$set": {
                    "status": "sending",
                    "started_at": datetime.utcnow(),
                    "last_batch_at": datetime.utcnow(),
                    "sent_count": 0,
                    "failed_count": 0,
                    "delivered_count": 0,
                    "processed_count": 0,
                    "queued_count": 0
                }
            }
        )
        
        if result.modified_count == 0:
            return {"error": "campaign_not_startable", "campaign_id": campaign_id}
        
        # Log campaign start
        if settings.ENABLE_AUDIT_LOGGING:
            log_campaign_event(
                AuditEventType.CAMPAIGN_STARTED,
                campaign_id,
                {"started_by": "system", "started_at": datetime.utcnow().isoformat()}
            )
        
        # Start first batch
        initial_batch_task = send_campaign_batch.delay(campaign_id, settings.MAX_BATCH_SIZE, None)
        
        return {
            "status": "campaign_started",
            "campaign_id": campaign_id,
            "initial_batch_task_id": initial_batch_task.id,
            "started_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Campaign start failed for {campaign_id}: {e}")
        return {"error": str(e)}

