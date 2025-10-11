# backend/tasks/startup_recovery.py - CREATE THIS NEW FILE
import logging
from datetime import datetime, timedelta
from bson import ObjectId
import redis
import os
from database import (
    get_sync_campaigns_collection,
    get_sync_email_logs_collection,
    get_sync_subscribers_collection
)
from celery_app import celery_app

logger = logging.getLogger(__name__)
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

@celery_app.task(bind=True, queue="cleanup", name="tasks.startup_recovery_only")
def startup_recovery_only(self):
    """
    STARTUP RECOVERY ONLY - Runs only on system restart/reboot
    More conservative recovery - only handles truly stuck campaigns
    """
    try:
        campaigns_collection = get_sync_campaigns_collection()
        
        # ✅ MUCH MORE CONSERVATIVE - Only recover campaigns that are REALLY stuck
        # Look for campaigns stuck for MORE than 2 HOURS (not 10 minutes)
        really_stuck_threshold = datetime.utcnow() - timedelta(hours=2)
        
        stuck_campaigns = list(campaigns_collection.find({
            "status": "sending",
            "$or": [
                # Campaign started more than 2 hours ago but no recent activity
                {
                    "started_at": {"$lt": really_stuck_threshold},
                    "last_batch_at": {"$lt": really_stuck_threshold}
                },
                # Campaign has no last_batch_at but started over 2 hours ago
                {
                    "started_at": {"$lt": really_stuck_threshold},
                    "last_batch_at": {"$exists": False}
                }
            ],
            # ✅ ADDITIONAL SAFETY: Only recover if not recovered recently
            "$or": [
                {"recovered_at": {"$exists": False}},
                {"recovered_at": {"$lt": datetime.utcnow() - timedelta(hours=1)}}
            ]
        }).limit(10))  # Limit to 10 campaigns max
        
        logger.info(f"Startup recovery: Found {len(stuck_campaigns)} truly stuck campaigns")
        
        if len(stuck_campaigns) == 0:
            return {"message": "No stuck campaigns found on startup", "recovered": 0}
        
        recovery_results = []
        
        for campaign in stuck_campaigns:
            campaign_id = str(campaign["_id"])
            
            try:
                logger.info(f"Startup recovery: Analyzing campaign {campaign_id}")
                
                # ✅ SMART RECOVERY DECISION
                should_recover, reason = should_startup_recover_campaign(campaign)
                
                if not should_recover:
                    logger.info(f"Startup recovery: Skipping {campaign_id} - {reason}")
                    recovery_results.append({
                        "campaign_id": campaign_id,
                        "action": "skipped",
                        "reason": reason,
                        "success": False
                    })
                    continue
                
                # ✅ PERFORM RECOVERY
                result = perform_startup_recovery(campaign_id, campaign)
                recovery_results.append(result)
                
                logger.info(f"Startup recovery: Completed for {campaign_id}")
                
            except Exception as e:
                logger.error(f"Startup recovery failed for {campaign_id}: {e}")
                recovery_results.append({
                    "campaign_id": campaign_id,
                    "action": "recovery_error",
                    "error": str(e),
                    "success": False
                })
        
        successful_recoveries = len([r for r in recovery_results if r.get("success")])
        
        logger.info(f"Startup recovery completed: {successful_recoveries}/{len(stuck_campaigns)} campaigns recovered")
        
        return {
            "message": "Startup recovery completed",
            "total_candidates": len(stuck_campaigns),
            "successfully_recovered": successful_recoveries,
            "results": recovery_results,
            "recovery_type": "startup_only"
        }
        
    except Exception as e:
        logger.error(f"Startup recovery system error: {e}")
        return {"error": str(e), "recovery_type": "startup_only"}

def should_startup_recover_campaign(campaign):
    """Determine if campaign should be recovered on startup"""
    
    # ✅ CHECK 1: Don't recover if SMTP is clearly broken
    failed_count = campaign.get("failed_count", 0)
    sent_count = campaign.get("sent_count", 0)
    
    # If we have many failures and zero successes, SMTP is likely broken
    if failed_count > 50 and sent_count == 0:
        return False, "smtp_appears_broken_high_failures_zero_sent"
    
    # ✅ CHECK 2: Don't recover if recovered too recently 
    recovered_at = campaign.get("recovered_at")
    if recovered_at:
        time_since_recovery = (datetime.utcnow() - recovered_at).total_seconds() / 3600  # hours
        if time_since_recovery < 1:  # Less than 1 hour ago
            return False, f"recovered_recently_{time_since_recovery:.1f}h_ago"
    
    # ✅ CHECK 3: Don't recover if too many recovery attempts
    recovery_count = campaign.get("recovery_count", 0)
    if recovery_count >= 5:  # Allow more attempts since this is startup only
        return False, f"max_recovery_attempts_reached_{recovery_count}"
    
    # ✅ CHECK 4: Only recover if campaign has reasonable progress OR is fresh start
    processed_count = campaign.get("processed_count", 0)
    target_count = campaign.get("target_list_count", 0)
    
    # If campaign processed more than 10% but is stuck, it's worth recovering
    if processed_count > 0:
        return True, f"campaign_has_progress_{processed_count}_processed"
    
    # If fresh campaign with no progress but stuck for 2+ hours, recover
    started_at = campaign.get("started_at")
    if started_at:
        hours_since_start = (datetime.utcnow() - started_at).total_seconds() / 3600
        if hours_since_start >= 2:
            return True, f"fresh_campaign_stuck_for_{hours_since_start:.1f}h"
    
    return False, "no_clear_reason_to_recover"

def perform_startup_recovery(campaign_id: str, campaign: dict):
    """Perform actual startup recovery"""
    campaigns_collection = get_sync_campaigns_collection()
    email_logs_collection = get_sync_email_logs_collection()
    
    try:
        # ✅ STEP 1: Get actual progress from email logs
        pipeline = [
            {"$match": {"campaign_id": ObjectId(campaign_id)}},
            {"$group": {
                "_id": "$latest_status",
                "count": {"$sum": 1}
            }}
        ]
        
        status_results = list(email_logs_collection.aggregate(pipeline))
        status_counts = {result["_id"]: result["count"] for result in status_results}
        
        sent_count = status_counts.get("sent", 0)
        failed_count = status_counts.get("failed", 0)
        delivered_count = status_counts.get("delivered", 0)
        total_processed = sum(status_counts.values())
        
        # ✅ STEP 2: Find last processed subscriber for resume point
        last_processed = email_logs_collection.find_one(
            {"campaign_id": ObjectId(campaign_id)},
            sort=[("_id", -1)]
        )
        
        last_subscriber_id = None
        if last_processed:
            last_subscriber_id = last_processed.get("subscriber_id")
        
        # ✅ STEP 3: Clear any SMTP circuit breakers (fresh start after reboot)
        redis_client.delete(f"campaign_smtp_errors:{campaign_id}")
        
        # ✅ STEP 4: Update campaign with accurate counters and restart
        campaigns_collection.update_one(
            {"_id": ObjectId(campaign_id)},
            {
                "$set": {
                    "status": "sending",
                    "last_batch_at": datetime.utcnow(),
                    "sent_count": sent_count,
                    "failed_count": failed_count,
                    "delivered_count": delivered_count,
                    "processed_count": total_processed,
                    "queued_count": 0,  # Fresh start
                    "recovered_at": datetime.utcnow(),
                    "recovery_action": "startup_recovery",
                    "recovery_type": "system_reboot",
                    "last_processed_subscriber": last_subscriber_id,
                    "smtp_errors_cleared": True
                },
                "$inc": {"recovery_count": 1}
            }
        )
        
        # ✅ STEP 5: Resume campaign from checkpoint
        from tasks.email_campaign_tasks import send_campaign_batch
        task = send_campaign_batch.delay(campaign_id, 500, last_subscriber_id)
        
        logger.info(f"Startup recovery: Campaign {campaign_id} resumed from {last_subscriber_id}, task: {task.id}")
        
        return {
            "campaign_id": campaign_id,
            "action": "startup_recovery_successful",
            "task_id": task.id,
            "resume_from_subscriber": last_subscriber_id,
            "progress_at_recovery": {
                "sent": sent_count,
                "failed": failed_count,
                "delivered": delivered_count,
                "total_processed": total_processed
            },
            "success": True
        }
        
    except Exception as e:
        logger.error(f"Startup recovery execution failed for {campaign_id}: {e}")
        # Mark campaign as failed rather than leaving it stuck
        campaigns_collection.update_one(
            {"_id": ObjectId(campaign_id)},
            {"$set": {
                "status": "failed",
                "failed_at": datetime.utcnow(),
                "failure_reason": f"startup_recovery_failed: {str(e)}",
                "recovery_action": "marked_failed_on_startup_recovery"
            }}
        )
        
        return {
            "campaign_id": campaign_id,
            "action": "startup_recovery_failed_marked_failed",
            "error": str(e),
            "success": False
        }

