# backend/tasks/campaign_control.py - COMPLETE CAMPAIGN MANAGEMENT
"""
Production-ready campaign control system
Handles pause/resume, lifecycle management, and state consistency
"""
import logging
import redis
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from bson import ObjectId
from celery_app import celery_app
from database_pool import (
    get_sync_campaigns_collection, get_sync_email_logs_collection, 
    get_sync_subscribers_collection
)
from core.campaign_config import settings, get_redis_key
import json

logger = logging.getLogger(__name__)

class CampaignState:
    """Campaign state constants"""
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"
    CANCELLED = "cancelled"

class CampaignController:
    """Campaign lifecycle management"""
    
    def __init__(self):
        self.redis_client = redis.Redis.from_url(settings.REDIS_URL)
    
    def pause_campaign(self, campaign_id: str, reason: str = "manual_pause", 
                      user_id: str = None) -> Dict[str, Any]:
        """Safely pause a running campaign"""
        try:
            campaigns_collection = get_sync_campaigns_collection()
            
            # Get current campaign state
            campaign = campaigns_collection.find_one(
                {"_id": ObjectId(campaign_id)},
                {"status": 1, "title": 1, "started_at": 1}
            )
            
            if not campaign:
                return {"success": False, "error": "campaign_not_found"}
            
            current_status = campaign.get("status")
            
            # Only allow pausing of active campaigns
            if current_status not in [CampaignState.SENDING, CampaignState.SCHEDULED]:
                return {
                    "success": False, 
                    "error": f"cannot_pause_campaign_in_{current_status}_state"
                }
            
            # Set pause flag in Redis for immediate effect
            pause_key = get_redis_key("campaign_paused", campaign_id)
            pause_data = {
                "paused_at": datetime.utcnow().isoformat(),
                "reason": reason,
                "user_id": user_id,
                "previous_status": current_status
            }
            self.redis_client.setex(pause_key, settings.CAMPAIGN_PAUSE_TIMEOUT_SECONDS, 
                                   json.dumps(pause_data))
            
            # Update campaign status in database
            update_result = campaigns_collection.update_one(
                {"_id": ObjectId(campaign_id), "status": current_status},
                {
                    "$set": {
                        "status": CampaignState.PAUSED,
                        "paused_at": datetime.utcnow(),
                        "pause_reason": reason,
                        "paused_by": user_id,
                        "previous_status": current_status,
                        "last_action_at": datetime.utcnow()
                    }
                }
            )
            
            if update_result.modified_count > 0:
                # Log the pause action
                self._log_campaign_action(campaign_id, "pause", {
                    "reason": reason,
                    "user_id": user_id,
                    "previous_status": current_status
                })
                
                # Get current progress
                progress = self._get_campaign_progress(campaign_id)
                
                logger.info(f"Campaign {campaign_id} paused: {reason}")
                
                return {
                    "success": True,
                    "campaign_id": campaign_id,
                    "action": "paused",
                    "reason": reason,
                    "previous_status": current_status,
                    "current_progress": progress,
                    "paused_at": datetime.utcnow().isoformat()
                }
            else:
                # Campaign state changed between checks
                return {"success": False, "error": "campaign_state_changed"}
            
        except Exception as e:
            logger.error(f"Failed to pause campaign {campaign_id}: {e}")
            return {"success": False, "error": str(e)}
    
    def resume_campaign(self, campaign_id: str, user_id: str = None) -> Dict[str, Any]:
        """Resume a paused campaign"""
        try:
            campaigns_collection = get_sync_campaigns_collection()
            
            # Get current campaign state
            campaign = campaigns_collection.find_one(
                {"_id": ObjectId(campaign_id)},
                {"status": 1, "previous_status": 1, "title": 1, "paused_at": 1}
            )
            
            if not campaign:
                return {"success": False, "error": "campaign_not_found"}
            
            current_status = campaign.get("status")
            
            if current_status != CampaignState.PAUSED:
                return {
                    "success": False, 
                    "error": f"cannot_resume_campaign_in_{current_status}_state"
                }
            
            previous_status = campaign.get("previous_status", CampaignState.SENDING)
            
            # Clear pause flag in Redis
            pause_key = get_redis_key("campaign_paused", campaign_id)
            self.redis_client.delete(pause_key)
            
            # Update campaign status
            update_result = campaigns_collection.update_one(
                {"_id": ObjectId(campaign_id), "status": CampaignState.PAUSED},
                {
                    "$set": {
                        "status": previous_status,
                        "resumed_at": datetime.utcnow(),
                        "resumed_by": user_id,
                        "last_batch_at": datetime.utcnow(),
                        "last_action_at": datetime.utcnow()
                    },
                    "$unset": {
                        "paused_at": "",
                        "pause_reason": "",
                        "paused_by": ""
                    }
                }
            )
            
            if update_result.modified_count > 0:
                # Restart campaign processing if it was sending
                if previous_status == CampaignState.SENDING:
                    self._restart_campaign_processing(campaign_id)
                
                # Log the resume action
                self._log_campaign_action(campaign_id, "resume", {
                    "user_id": user_id,
                    "resumed_to_status": previous_status
                })
                
                # Get current progress
                progress = self._get_campaign_progress(campaign_id)
                
                logger.info(f"Campaign {campaign_id} resumed to {previous_status}")
                
                return {
                    "success": True,
                    "campaign_id": campaign_id,
                    "action": "resumed",
                    "status": previous_status,
                    "current_progress": progress,
                    "resumed_at": datetime.utcnow().isoformat()
                }
            else:
                return {"success": False, "error": "campaign_state_changed"}
            
        except Exception as e:
            logger.error(f"Failed to resume campaign {campaign_id}: {e}")
            return {"success": False, "error": str(e)}
    
    def stop_campaign(self, campaign_id: str, reason: str = "manual_stop", 
                     user_id: str = None, force: bool = False) -> Dict[str, Any]:
        """Stop a running campaign permanently"""
        try:
            campaigns_collection = get_sync_campaigns_collection()
            
            # Get current campaign state
            campaign = campaigns_collection.find_one(
                {"_id": ObjectId(campaign_id)},
                {"status": 1, "title": 1, "started_at": 1}
            )
            
            if not campaign:
                return {"success": False, "error": "campaign_not_found"}
            
            current_status = campaign.get("status")
            
            # Check if campaign can be stopped
            stoppable_states = [CampaignState.SENDING, CampaignState.PAUSED, CampaignState.SCHEDULED]
            if current_status not in stoppable_states and not force:
                return {
                    "success": False, 
                    "error": f"cannot_stop_campaign_in_{current_status}_state"
                }
            
            # Set stop flag in Redis for immediate effect
            stop_key = get_redis_key("campaign_stopped", campaign_id)
            stop_data = {
                "stopped_at": datetime.utcnow().isoformat(),
                "reason": reason,
                "user_id": user_id,
                "previous_status": current_status,
                "force_stopped": force
            }
            self.redis_client.setex(stop_key, 3600, json.dumps(stop_data))
            
            # Get final progress before stopping
            progress = self._get_campaign_progress(campaign_id)
            
            # Update campaign status
            update_result = campaigns_collection.update_one(
                {"_id": ObjectId(campaign_id)},
                {
                    "$set": {
                        "status": CampaignState.STOPPED,
                        "stopped_at": datetime.utcnow(),
                        "stop_reason": reason,
                        "stopped_by": user_id,
                        "previous_status": current_status,
                        "force_stopped": force,
                        "final_progress": progress,
                        "last_action_at": datetime.utcnow(),
                        "queued_count": 0  # Clear any remaining queue count
                    }
                }
            )
            
            if update_result.modified_count > 0:
                # Clear any pause flags
                pause_key = get_redis_key("campaign_paused", campaign_id)
                self.redis_client.delete(pause_key)
                
                # Log the stop action
                self._log_campaign_action(campaign_id, "stop", {
                    "reason": reason,
                    "user_id": user_id,
                    "previous_status": current_status,
                    "force_stopped": force,
                    "final_progress": progress
                })
                
                logger.info(f"Campaign {campaign_id} stopped: {reason} (force: {force})")
                
                return {
                    "success": True,
                    "campaign_id": campaign_id,
                    "action": "stopped",
                    "reason": reason,
                    "previous_status": current_status,
                    "final_progress": progress,
                    "stopped_at": datetime.utcnow().isoformat(),
                    "force_stopped": force
                }
            else:
                return {"success": False, "error": "campaign_update_failed"}
            
        except Exception as e:
            logger.error(f"Failed to stop campaign {campaign_id}: {e}")
            return {"success": False, "error": str(e)}
    
    def cancel_campaign(self, campaign_id: str, reason: str = "manual_cancel", 
                       user_id: str = None) -> Dict[str, Any]:
        """Cancel a campaign (only for draft/scheduled campaigns)"""
        try:
            campaigns_collection = get_sync_campaigns_collection()
            
            # Get current campaign state
            campaign = campaigns_collection.find_one(
                {"_id": ObjectId(campaign_id)},
                {"status": 1, "title": 1, "scheduled_at": 1}
            )
            
            if not campaign:
                return {"success": False, "error": "campaign_not_found"}
            
            current_status = campaign.get("status")
            
            # Only allow cancellation of draft/scheduled campaigns
            if current_status not in [CampaignState.DRAFT, CampaignState.SCHEDULED]:
                return {
                    "success": False, 
                    "error": f"cannot_cancel_campaign_in_{current_status}_state"
                }
            
            # Update campaign status
            update_result = campaigns_collection.update_one(
                {"_id": ObjectId(campaign_id), "status": current_status},
                {
                    "$set": {
                        "status": CampaignState.CANCELLED,
                        "cancelled_at": datetime.utcnow(),
                        "cancel_reason": reason,
                        "cancelled_by": user_id,
                        "previous_status": current_status,
                        "last_action_at": datetime.utcnow()
                    }
                }
            )
            
            if update_result.modified_count > 0:
                # Log the cancel action
                self._log_campaign_action(campaign_id, "cancel", {
                    "reason": reason,
                    "user_id": user_id,
                    "previous_status": current_status
                })
                
                logger.info(f"Campaign {campaign_id} cancelled: {reason}")
                
                return {
                    "success": True,
                    "campaign_id": campaign_id,
                    "action": "cancelled",
                    "reason": reason,
                    "previous_status": current_status,
                    "cancelled_at": datetime.utcnow().isoformat()
                }
            else:
                return {"success": False, "error": "campaign_update_failed"}
            
        except Exception as e:
            logger.error(f"Failed to cancel campaign {campaign_id}: {e}")
            return {"success": False, "error": str(e)}
    
    def _restart_campaign_processing(self, campaign_id: str):
        """Restart campaign processing after resume"""
        try:
            # Find where the campaign left off
            email_logs_collection = get_sync_email_logs_collection()
            last_processed = email_logs_collection.find_one(
                {"campaign_id": ObjectId(campaign_id)},
                sort=[("_id", -1)]
            )
            
            last_subscriber_id = None
            if last_processed:
                last_subscriber_id = last_processed.get("subscriber_id")
            
            # Restart batch processing
            from tasks.email_campaign_tasks import send_campaign_batch
            task = send_campaign_batch.delay(campaign_id, 100, last_subscriber_id)
            
            logger.info(f"Campaign {campaign_id} processing restarted, task: {task.id}")
            
        except Exception as e:
            logger.error(f"Failed to restart campaign processing for {campaign_id}: {e}")
    
    def _get_campaign_progress(self, campaign_id: str) -> Dict[str, Any]:
        """Get current campaign progress statistics"""
        try:
            campaigns_collection = get_sync_campaigns_collection()
            email_logs_collection = get_sync_email_logs_collection()
            
            # Get campaign info
            campaign = campaigns_collection.find_one(
                {"_id": ObjectId(campaign_id)},
                {
                    "target_list_count": 1, "sent_count": 1, "failed_count": 1, 
                    "processed_count": 1, "queued_count": 1, "started_at": 1
                }
            )
            
            if not campaign:
                return {}
            
            # Get actual email log statistics
            email_stats_pipeline = [
                {"$match": {"campaign_id": ObjectId(campaign_id)}},
                {"$group": {
                    "_id": "$latest_status",
                    "count": {"$sum": 1}
                }}
            ]
            
            email_stats = list(email_logs_collection.aggregate(email_stats_pipeline))
            status_counts = {stat["_id"]: stat["count"] for stat in email_stats}
            
            # Calculate progress
            target_count = campaign.get("target_list_count", 0)
            total_processed = sum(status_counts.values())
            
            progress = {
                "target_count": target_count,
                "processed_count": total_processed,
                "sent_count": status_counts.get("sent", 0),
                "failed_count": status_counts.get("failed", 0),
                "delivered_count": status_counts.get("delivered", 0),
                "queued_count": campaign.get("queued_count", 0),
                "completion_percentage": (total_processed / max(target_count, 1)) * 100,
                "remaining_count": max(0, target_count - total_processed),
                "status_breakdown": status_counts
            }
            
            # Calculate rate if campaign started
            if campaign.get("started_at"):
                elapsed_seconds = (datetime.utcnow() - campaign["started_at"]).total_seconds()
                if elapsed_seconds > 0:
                    progress["processing_rate"] = {
                        "emails_per_second": total_processed / elapsed_seconds,
                        "emails_per_hour": (total_processed / elapsed_seconds) * 3600,
                        "estimated_completion": campaign["started_at"] + timedelta(
                            seconds=(target_count / (total_processed / elapsed_seconds)) if total_processed > 0 else 0
                        )
                    }
            
            return progress
            
        except Exception as e:
            logger.error(f"Failed to get campaign progress for {campaign_id}: {e}")
            return {"error": str(e)}
    
    def _log_campaign_action(self, campaign_id: str, action: str, details: Dict[str, Any]):
        """Log campaign control actions for audit"""
        try:
            if not settings.ENABLE_AUDIT_LOGGING:
                return
            
            from database_pool import get_sync_audit_collection
            audit_collection = get_sync_audit_collection()
            
            audit_record = {
                "campaign_id": ObjectId(campaign_id),
                "action": action,
                "timestamp": datetime.utcnow(),
                "details": details,
                "source": "campaign_controller"
            }
            
            audit_collection.insert_one(audit_record)
            
        except Exception as e:
            logger.error(f"Failed to log campaign action: {e}")
    
    def is_campaign_paused(self, campaign_id: str) -> bool:
        """Check if campaign is currently paused"""
        try:
            pause_key = get_redis_key("campaign_paused", campaign_id)
            return self.redis_client.exists(pause_key)
        except:
            return False
    
    def is_campaign_stopped(self, campaign_id: str) -> bool:
        """Check if campaign is currently stopped"""
        try:
            stop_key = get_redis_key("campaign_stopped", campaign_id)
            return self.redis_client.exists(stop_key)
        except:
            return False
    
    def get_campaign_control_info(self, campaign_id: str) -> Dict[str, Any]:
        """Get campaign control status information"""
        try:
            campaigns_collection = get_sync_campaigns_collection()
            
            campaign = campaigns_collection.find_one(
                {"_id": ObjectId(campaign_id)},
                {
                    "status": 1, "paused_at": 1, "stopped_at": 1, "cancelled_at": 1,
                    "pause_reason": 1, "stop_reason": 1, "cancel_reason": 1,
                    "paused_by": 1, "stopped_by": 1, "cancelled_by": 1,
                    "previous_status": 1, "last_action_at": 1
                }
            )
            
            if not campaign:
                return {"error": "campaign_not_found"}
            
            control_info = {
                "campaign_id": campaign_id,
                "current_status": campaign.get("status"),
                "is_paused": self.is_campaign_paused(campaign_id),
                "is_stopped": self.is_campaign_stopped(campaign_id),
                "can_pause": campaign.get("status") in [CampaignState.SENDING, CampaignState.SCHEDULED],
                "can_resume": campaign.get("status") == CampaignState.PAUSED,
                "can_stop": campaign.get("status") in [CampaignState.SENDING, CampaignState.PAUSED, CampaignState.SCHEDULED],
                "can_cancel": campaign.get("status") in [CampaignState.DRAFT, CampaignState.SCHEDULED],
                "last_action_at": campaign.get("last_action_at"),
                "control_history": []
            }
            
            # Add control history
            if campaign.get("paused_at"):
                control_info["control_history"].append({
                    "action": "paused",
                    "timestamp": campaign["paused_at"],
                    "reason": campaign.get("pause_reason"),
                    "user": campaign.get("paused_by")
                })
            
            if campaign.get("stopped_at"):
                control_info["control_history"].append({
                    "action": "stopped", 
                    "timestamp": campaign["stopped_at"],
                    "reason": campaign.get("stop_reason"),
                    "user": campaign.get("stopped_by")
                })
            
            if campaign.get("cancelled_at"):
                control_info["control_history"].append({
                    "action": "cancelled",
                    "timestamp": campaign["cancelled_at"],
                    "reason": campaign.get("cancel_reason"),
                    "user": campaign.get("cancelled_by")
                })
            
            return control_info
            
        except Exception as e:
            logger.error(f"Failed to get campaign control info: {e}")
            return {"error": str(e)}

# Celery tasks for campaign control
@celery_app.task(bind=True, queue="campaigns", name="tasks.pause_campaign")
def pause_campaign_task(self, campaign_id: str, reason: str = "api_request", user_id: str = None):
    """Celery task to pause campaign"""
    controller = CampaignController()
    return controller.pause_campaign(campaign_id, reason, user_id)

@celery_app.task(bind=True, queue="campaigns", name="tasks.resume_campaign")
def resume_campaign_task(self, campaign_id: str, user_id: str = None):
    """Celery task to resume campaign"""
    controller = CampaignController()
    return controller.resume_campaign(campaign_id, user_id)

@celery_app.task(bind=True, queue="campaigns", name="tasks.stop_campaign")
def stop_campaign_task(self, campaign_id: str, reason: str = "api_request", 
                      user_id: str = None, force: bool = False):
    """Celery task to stop campaign"""
    controller = CampaignController()
    return controller.stop_campaign(campaign_id, reason, user_id, force)

@celery_app.task(bind=True, queue="campaigns", name="tasks.cancel_campaign")
def cancel_campaign_task(self, campaign_id: str, reason: str = "api_request", user_id: str = None):
    """Celery task to cancel campaign"""
    controller = CampaignController()
    return controller.cancel_campaign(campaign_id, reason, user_id)

@celery_app.task(bind=True, queue="cleanup", name="tasks.cleanup_campaign_flags")
def cleanup_campaign_flags(self):
    """Clean up expired campaign control flags"""
    try:
        redis_client = redis.Redis.from_url(settings.REDIS_URL)
        
        # Clean up expired pause flags
        pause_pattern = get_redis_key("campaign_paused", "*")
        cleaned_pause = 0
        
        for key in redis_client.scan_iter(match=pause_pattern):
            ttl = redis_client.ttl(key)
            if ttl == -1:  # No TTL set, remove old entries
                redis_client.delete(key)
                cleaned_pause += 1
        
        # Clean up expired stop flags  
        stop_pattern = get_redis_key("campaign_stopped", "*")
        cleaned_stop = 0
        
        for key in redis_client.scan_iter(match=stop_pattern):
            ttl = redis_client.ttl(key)
            if ttl == -1:
                redis_client.delete(key)
                cleaned_stop += 1
        
        logger.info(f"Campaign flags cleanup: {cleaned_pause} pause flags, {cleaned_stop} stop flags")
        
        return {
            "cleaned_pause_flags": cleaned_pause,
            "cleaned_stop_flags": cleaned_stop
        }
        
    except Exception as e:
        logger.error(f"Campaign flags cleanup failed: {e}")
        return {"error": str(e)}

# Global campaign controller instance
campaign_controller = CampaignController()

