# backend/tasks/automation_tasks.py
"""
Production-grade Celery tasks for email automation campaigns
Integrates with existing FastAPI, MongoDB, and email service infrastructure
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from bson import ObjectId
from pymongo import MongoClient
from celery import Task
import time

from celery_app import celery_app
from database import (
    get_sync_database,
    get_sync_automation_rules_collection,
    get_sync_automation_steps_collection,
    get_sync_automation_executions_collection,
    get_sync_subscribers_collection,
    get_sync_campaigns_collection,
    get_sync_templates_collection,
    get_sync_settings_collection,
    get_sync_audit_collection
)
from routes.smtp_services.email_service_factory import get_email_service_sync
from routes.smtp_services.email_campaign_processor import SyncEmailCampaignProcessor

# Configure logging
logger = logging.getLogger(__name__)

class AutomationBaseTask(Task):
    """Base task class for automation tasks with error handling and logging"""
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"Automation task {task_id} failed: {exc}", extra={
            "task_id": task_id,
            "args": args,
            "kwargs": kwargs,
            "error": str(exc)
        })

    def on_success(self, retval, task_id, args, kwargs):
        logger.info(f"Automation task {task_id} completed successfully", extra={
            "task_id": task_id,
            "result": retval
        })

@celery_app.task(base=AutomationBaseTask, bind=True, max_retries=3, default_retry_delay=300)
def execute_automation_step(
    self, 
    automation_rule_id: str, 
    step_id: str, 
    subscriber_id: str,
    execution_context: Dict[str, Any] = None
):
    """
    Execute a single automation step for a specific subscriber
    """
    execution_context = execution_context or {}
    
    try:
        logger.info(f"Executing automation step", extra={
            "automation_rule_id": automation_rule_id,
            "step_id": step_id,
            "subscriber_id": subscriber_id
        })

        # Get database collections
        db = get_sync_database()
        automation_rules = get_automation_rules_collection_sync()
        automation_steps = get_automation_steps_collection_sync()
        automation_executions = get_automation_executions_collection_sync()
        subscribers = get_subscribers_collection_sync()
        templates = get_templates_collection_sync()
        settings = get_settings_collection_sync()
        audit = get_audit_collection_sync()

        # Validate automation rule exists and is active
        automation_rule = automation_rules.find_one({
            "_id": ObjectId(automation_rule_id),
            "status": "active",
            "deleted_at": {"$exists": False}
        })
        
        if not automation_rule:
            logger.warning(f"Automation rule not found or inactive: {automation_rule_id}")
            return {"status": "skipped", "reason": "automation_inactive"}

        # Get automation step
        step = automation_steps.find_one({
            "_id": ObjectId(step_id),
            "automation_rule_id": automation_rule_id
        })
        
        if not step:
            logger.error(f"Automation step not found: {step_id}")
            return {"status": "error", "reason": "step_not_found"}

        # Get subscriber
        subscriber = subscribers.find_one({
            "_id": ObjectId(subscriber_id),
            "status": "active"
        })
        
        if not subscriber:
            logger.warning(f"Subscriber not found or inactive: {subscriber_id}")
            return {"status": "skipped", "reason": "subscriber_inactive"}

        # Check if execution already exists (prevent duplicates)
        existing_execution = automation_executions.find_one({
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id
        })
        
        if existing_execution:
            logger.info(f"Execution already exists for subscriber {subscriber_id} and step {step_id}")
            return {"status": "skipped", "reason": "already_executed"}

        # Check segment conditions if specified
        if step.get("segment_conditions"):
            if not _check_segment_conditions(subscriber, step["segment_conditions"]):
                logger.info(f"Subscriber {subscriber_id} doesn't match segment conditions")
                return {"status": "skipped", "reason": "segment_mismatch"}

        # Get email template
        template = templates.find_one({"_id": ObjectId(step["email_template_id"])})
        if not template:
            logger.error(f"Email template not found: {step['email_template_id']}")
            return {"status": "error", "reason": "template_not_found"}

        # Initialize email processor
        processor = SyncEmailCampaignProcessor(
            campaigns_collection=get_campaigns_collection_sync(),
            templates_collection=templates,
            subscribers_collection=subscribers
        )

        # Prepare email content with automation context
        email_data = _prepare_automation_email_content(
            processor, template, subscriber, automation_rule, execution_context
        )

        if not email_data:
            logger.error(f"Failed to prepare email content for subscriber {subscriber_id}")
            return {"status": "error", "reason": "content_preparation_failed"}

        # Get email service
        email_service = get_email_service_sync(settings)

        # Create execution record
        execution_id = ObjectId()
        execution_record = {
            "_id": execution_id,
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id,
            "email_template_id": step["email_template_id"],
            "scheduled_at": execution_context.get("scheduled_at", datetime.utcnow()),
            "executed_at": datetime.utcnow(),
            "status": "sending",
            "subject": email_data["subject"],
            "recipient_email": email_data["recipient_email"],
            "execution_context": execution_context
        }
        
        automation_executions.insert_one(execution_record)

        # Send email
        sender_email = execution_context.get("sender_email", "noreply@yourdomain.com")
        sender_name = execution_context.get("sender_name", "Your Company")
        
        email_result = email_service.send_email(
            sender_email=sender_email,
            recipient_email=email_data["recipient_email"],
            subject=email_data["subject"],
            html_content=email_data["html_content"],
            sender_name=sender_name
        )

        # Update execution record with results
        update_data = {
            "status": "sent" if email_result.success else "failed",
            "sent_at": datetime.utcnow() if email_result.success else None,
            "message_id": getattr(email_result, "message_id", None),
            "error_message": getattr(email_result, "error", None)
        }
        
        automation_executions.update_one(
            {"_id": execution_id},
            {"$set": update_data}
        )

        # Log audit trail
        audit.insert_one({
            "timestamp": datetime.utcnow(),
            "action": "automation_email_sent" if email_result.success else "automation_email_failed",
            "entity_type": "automation_execution",
            "entity_id": str(execution_id),
            "details": f"Automation '{automation_rule['name']}' step {step.get('step_order', 1)} for {email_data['recipient_email']}",
            "automation_rule_id": automation_rule_id,
            "subscriber_id": subscriber_id,
            "success": email_result.success
        })

        # Schedule next step if this one succeeded
        if email_result.success:
            _schedule_next_automation_step(
                automation_rule_id, step, subscriber_id, execution_context
            )

        result = {
            "status": "sent" if email_result.success else "failed",
            "execution_id": str(execution_id),
            "subscriber_email": email_data["recipient_email"],
            "message_id": getattr(email_result, "message_id", None),
            "error": getattr(email_result, "error", None)
        }

        logger.info(f"Automation step execution completed", extra={
            "result": result,
            "automation_rule_id": automation_rule_id,
            "step_id": step_id,
            "subscriber_id": subscriber_id
        })

        return result

    except Exception as exc:
        logger.exception(f"Error executing automation step: {exc}")
        
        # Update execution record if it exists
        try:
            if 'execution_id' in locals():
                automation_executions.update_one(
                    {"_id": execution_id},
                    {"$set": {
                        "status": "failed",
                        "error_message": str(exc),
                        "failed_at": datetime.utcnow()
                    }}
                )
        except Exception as update_exc:
            logger.error(f"Failed to update execution record: {update_exc}")

        # Retry logic
        if self.request.retries < self.max_retries:
            retry_delay = min(300 * (2 ** self.request.retries), 3600)  # Exponential backoff, max 1 hour
            logger.info(f"Retrying automation step in {retry_delay} seconds (attempt {self.request.retries + 1})")
            raise self.retry(countdown=retry_delay, exc=exc)
        
        return {"status": "error", "error": str(exc)}

@celery_app.task(base=AutomationBaseTask, bind=True)
def process_automation_trigger(
    self,
    automation_rule_id: str,
    trigger_data: Dict[str, Any],
    subscriber_ids: List[str] = None
):
    """
    Process automation trigger for subscribers
    """
    try:
        logger.info(f"Processing automation trigger", extra={
            "automation_rule_id": automation_rule_id,
            "trigger_data": trigger_data,
            "subscriber_count": len(subscriber_ids) if subscriber_ids else 0
        })

        # Get database collections
        automation_rules = get_automation_rules_collection_sync()
        automation_steps = get_automation_steps_collection_sync()
        subscribers = get_subscribers_collection_sync()

        # Get automation rule
        automation_rule = automation_rules.find_one({
            "_id": ObjectId(automation_rule_id),
            "status": "active",
            "deleted_at": {"$exists": False}
        })
        
        if not automation_rule:
            logger.warning(f"Automation rule not found or inactive: {automation_rule_id}")
            return {"status": "skipped", "reason": "automation_inactive"}

        # Get first step
        first_step = automation_steps.find_one({
            "automation_rule_id": automation_rule_id,
            "step_order": 1
        })
        
        if not first_step:
            logger.warning(f"No first step found for automation: {automation_rule_id}")
            return {"status": "skipped", "reason": "no_steps"}

        # Determine target subscribers
        if subscriber_ids:
            target_subscribers = list(subscribers.find({
                "_id": {"$in": [ObjectId(sid) for sid in subscriber_ids]},
                "status": "active"
            }))
        else:
            # Use target segments from automation rule
            target_segments = automation_rule.get("target_segments", [])
            if target_segments:
                query = {
                    "list": {"$in": target_segments},
                    "status": "active"
                }
            else:
                query = {"status": "active"}
                
            target_subscribers = list(subscribers.find(query))

        logger.info(f"Found {len(target_subscribers)} target subscribers for automation")

        # Schedule first step for each subscriber
        scheduled_count = 0
        execution_context = {
            "trigger": automation_rule["trigger"],
            "trigger_data": trigger_data,
            "scheduled_at": datetime.utcnow(),
            "sender_email": trigger_data.get("sender_email", "noreply@yourdomain.com"),
            "sender_name": trigger_data.get("sender_name", "Your Company")
        }

        for subscriber in target_subscribers:
            try:
                # Calculate delay for first step
                delay_seconds = first_step.get("delay_hours", 0) * 3600
                
                if delay_seconds > 0:
                    # Schedule for later execution
                    execute_automation_step.apply_async(
                        args=[automation_rule_id, str(first_step["_id"]), str(subscriber["_id"])],
                        kwargs={"execution_context": execution_context},
                        countdown=delay_seconds
                    )
                else:
                    # Execute immediately
                    execute_automation_step.delay(
                        automation_rule_id, str(first_step["_id"]), str(subscriber["_id"]), execution_context
                    )
                    
                scheduled_count += 1
                
            except Exception as exc:
                logger.error(f"Failed to schedule automation for subscriber {subscriber['_id']}: {exc}")

        # Log audit trail
        audit = get_audit_collection_sync()
        audit.insert_one({
            "timestamp": datetime.utcnow(),
            "action": "automation_triggered",
            "entity_type": "automation",
            "entity_id": automation_rule_id,
            "details": f"Triggered automation '{automation_rule['name']}' for {scheduled_count} subscribers",
            "trigger_data": trigger_data,
            "scheduled_count": scheduled_count
        })

        result = {
            "status": "processed",
            "automation_rule_id": automation_rule_id,
            "scheduled_count": scheduled_count,
            "total_subscribers": len(target_subscribers)
        }

        logger.info(f"Automation trigger processed successfully", extra=result)
        return result

    except Exception as exc:
        logger.exception(f"Error processing automation trigger: {exc}")
        return {"status": "error", "error": str(exc)}

@celery_app.task(base=AutomationBaseTask)
def cleanup_automation_executions():
    """
    Cleanup old automation execution records (older than 90 days)
    """
    try:
        logger.info("Starting automation executions cleanup")
        
        automation_executions = get_automation_executions_collection_sync()
        cutoff_date = datetime.utcnow() - timedelta(days=90)
        
        result = automation_executions.delete_many({
            "executed_at": {"$lt": cutoff_date},
            "status": {"$in": ["sent", "failed"]}
        })
        
        logger.info(f"Cleaned up {result.deleted_count} old automation execution records")
        
        return {
            "status": "completed",
            "deleted_count": result.deleted_count,
            "cutoff_date": cutoff_date.isoformat()
        }
        
    except Exception as exc:
        logger.exception(f"Error during automation cleanup: {exc}")
        return {"status": "error", "error": str(exc)}

# Helper functions

def _check_segment_conditions(subscriber: Dict[str, Any], segment_conditions: List[str]) -> bool:
    """
    Check if subscriber matches segment conditions
    """
    if not segment_conditions:
        return True
        
    subscriber_lists = subscriber.get("list", [])
    if isinstance(subscriber_lists, str):
        subscriber_lists = [subscriber_lists]
        
    return any(segment_id in subscriber_lists for segment_id in segment_conditions)

def _prepare_automation_email_content(
    processor: SyncEmailCampaignProcessor,
    template: Dict[str, Any],
    subscriber: Dict[str, Any],
    automation_rule: Dict[str, Any],
    execution_context: Dict[str, Any]
) -> Optional[Dict[str, str]]:
    """
    Prepare email content for automation
    """
    try:
        # Create a mock campaign object for the processor
        mock_campaign = {
            "_id": ObjectId(),
            "name": f"Automation: {automation_rule['name']}",
            "subject": template.get("subject", "Automated Email"),
            "template_id": str(template["_id"]),
            "template": template,
            "field_map": execution_context.get("field_map", {}),
            "fallback_values": execution_context.get("fallback_values", {})
        }
        
        return processor.prepare_email_content(mock_campaign, subscriber)
        
    except Exception as exc:
        logger.error(f"Error preparing automation email content: {exc}")
        return None

def _schedule_next_automation_step(
    automation_rule_id: str,
    current_step: Dict[str, Any],
    subscriber_id: str,
    execution_context: Dict[str, Any]
):
    """
    Schedule the next step in the automation sequence
    """
    try:
        automation_steps = get_automation_steps_collection_sync()
        
        # Find next step
        next_step = automation_steps.find_one({
            "automation_rule_id": automation_rule_id,
            "step_order": current_step.get("step_order", 0) + 1
        })
        
        if next_step:
            delay_seconds = next_step.get("delay_hours", 0) * 3600
            
            logger.info(f"Scheduling next automation step", extra={
                "automation_rule_id": automation_rule_id,
                "next_step_id": str(next_step["_id"]),
                "subscriber_id": subscriber_id,
                "delay_seconds": delay_seconds
            })
            
            if delay_seconds > 0:
                execute_automation_step.apply_async(
                    args=[automation_rule_id, str(next_step["_id"]), subscriber_id],
                    kwargs={"execution_context": execution_context},
                    countdown=delay_seconds
                )
            else:
                execute_automation_step.delay(
                    automation_rule_id, str(next_step["_id"]), subscriber_id, execution_context
                )
                
    except Exception as exc:
        logger.error(f"Error scheduling next automation step: {exc}")

# Periodic task for processing scheduled automations
@celery_app.task(base=AutomationBaseTask)
def process_scheduled_automations():
    """
    Process automations that should be triggered based on subscriber events
    This is a periodic task that should run every few minutes
    """
    try:
        logger.info("Processing scheduled automations")
        
        # This is where you would implement logic to:
        # 1. Check for new subscribers (welcome trigger)
        # 2. Check for birthdays (birthday trigger)
        # 3. Check for abandoned carts, etc.
        
        # Example for welcome trigger:
        subscribers = get_subscribers_collection_sync()
        automation_rules = get_automation_rules_collection_sync()
        
        # Find active welcome automations
        welcome_automations = list(automation_rules.find({
            "trigger": "welcome",
            "status": "active",
            "deleted_at": {"$exists": False}
        }))
        
        processed_count = 0
        for automation in welcome_automations:
            # Find new subscribers (within last 5 minutes to avoid duplicates)
            cutoff_time = datetime.utcnow() - timedelta(minutes=5)
            new_subscribers = list(subscribers.find({
                "status": "active",
                "created_at": {"$gte": cutoff_time}
            }))
            
            if new_subscribers:
                subscriber_ids = [str(sub["_id"]) for sub in new_subscribers]
                
                process_automation_trigger.delay(
                    str(automation["_id"]),
                    {"trigger_type": "welcome", "timestamp": datetime.utcnow().isoformat()},
                    subscriber_ids
                )
                
                processed_count += len(subscriber_ids)
        
        logger.info(f"Processed {processed_count} scheduled automations")
        
        return {
            "status": "completed",
            "processed_count": processed_count
        }
        
    except Exception as exc:
        logger.exception(f"Error processing scheduled automations: {exc}")
        return {"status": "error", "error": str(exc)}
