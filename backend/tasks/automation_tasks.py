# backend/tasks/automation_tasks.py
"""
Celery tasks for automation workflow execution
"""
from celery import shared_task
from datetime import datetime, timedelta
from bson import ObjectId
import logging

from database import (
    get_sync_automation_rules_collection,
    get_sync_automation_steps_collection,
    get_sync_automation_executions_collection,
    get_sync_subscribers_collection,
    get_sync_templates_collection,
    get_sync_segments_collection
)

logger = logging.getLogger(__name__)


@shared_task(
    name="tasks.process_automation_trigger",
    bind=True,
    max_retries=3,
    default_retry_delay=300  # 5 minutes
)
def process_automation_trigger(self, trigger_type: str, subscriber_id: str, trigger_data: dict = None):
    """
    Process automation trigger for a subscriber
    
    Args:
        trigger_type: Type of trigger (welcome, birthday, abandoned_cart, etc.)
        subscriber_id: Subscriber ObjectId string
        trigger_data: Additional trigger context
    """
    try:
        rules_collection = get_sync_automation_rules_collection()
        subscribers_collection = get_sync_subscribers_collection()
        
        # Find active automation rules for this trigger
        rules = list(rules_collection.find({
            "trigger": trigger_type,
            "status": "active",
            "deleted_at": {"$exists": False}
        }))
        
        if not rules:
            logger.info(f"No active automation rules for trigger: {trigger_type}")
            return {"status": "no_rules", "trigger": trigger_type}
        
        # Get subscriber info
        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not subscriber:
            logger.error(f"Subscriber not found: {subscriber_id}")
            return {"status": "subscriber_not_found"}
        
        # Check subscriber status
        if subscriber.get("status") != "active":
            logger.info(f"Subscriber {subscriber_id} is not active, skipping automation")
            return {"status": "subscriber_inactive"}
        
        # Process each matching rule
        results = []
        for rule in rules:
            # Check if subscriber matches target segments
            target_segments = rule.get("target_segments", [])
            if target_segments:
                subscriber_segments = subscriber.get("segments", [])
                if not any(seg in subscriber_segments for seg in target_segments):
                    logger.info(f"Subscriber not in target segments for rule: {rule['name']}")
                    continue
            
            # Check trigger conditions
            trigger_conditions = rule.get("trigger_conditions", {})
            if not evaluate_trigger_conditions(trigger_conditions, subscriber, trigger_data):
                logger.info(f"Trigger conditions not met for rule: {rule['name']}")
                continue
            
            # Start automation workflow
            result = start_automation_workflow.delay(
                automation_rule_id=str(rule["_id"]),
                subscriber_id=subscriber_id,
                trigger_data=trigger_data or {}
            )
            
            results.append({
                "rule_id": str(rule["_id"]),
                "rule_name": rule["name"],
                "task_id": result.id
            })
        
        return {
            "status": "success",
            "trigger": trigger_type,
            "subscriber_id": subscriber_id,
            "rules_triggered": len(results),
            "results": results
        }
        
    except Exception as exc:
        logger.error(f"Error processing automation trigger: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    name="tasks.start_automation_workflow",
    bind=True,
    max_retries=3
)
def start_automation_workflow(self, automation_rule_id: str, subscriber_id: str, trigger_data: dict = None):
    """
    Start an automation workflow for a subscriber
    Schedules all steps with appropriate delays
    """
    try:
        steps_collection = get_sync_automation_steps_collection()
        executions_collection = get_sync_automation_executions_collection()
        
        # Get all steps for this automation
        steps = list(steps_collection.find({
            "automation_rule_id": automation_rule_id
        }).sort("step_order", 1))
        
        if not steps:
            logger.warning(f"No steps found for automation: {automation_rule_id}")
            return {"status": "no_steps"}
        
        # Schedule each step
        scheduled_tasks = []
        for step in steps:
            delay_hours = step.get("delay_hours", 0)
            
            # Schedule the step execution
            eta = datetime.utcnow() + timedelta(hours=delay_hours)
            
            result = execute_automation_step.apply_async(
                args=[
                    automation_rule_id,
                    str(step["_id"]),
                    subscriber_id,
                    trigger_data or {}
                ],
                eta=eta
            )
            
            # Record the scheduled execution
            execution_record = {
                "_id": ObjectId(),
                "automation_rule_id": automation_rule_id,
                "automation_step_id": str(step["_id"]),
                "subscriber_id": subscriber_id,
                "task_id": result.id,
                "scheduled_at": datetime.utcnow(),
                "scheduled_for": eta,
                "status": "scheduled",
                "step_order": step["step_order"],
                "trigger_data": trigger_data or {},
                "created_at": datetime.utcnow()
            }
            
            executions_collection.insert_one(execution_record)
            
            scheduled_tasks.append({
                "step_id": str(step["_id"]),
                "step_order": step["step_order"],
                "task_id": result.id,
                "scheduled_for": eta.isoformat()
            })
        
        logger.info(f"Started automation workflow: {automation_rule_id} for subscriber: {subscriber_id}")
        
        return {
            "status": "success",
            "automation_rule_id": automation_rule_id,
            "subscriber_id": subscriber_id,
            "steps_scheduled": len(scheduled_tasks),
            "tasks": scheduled_tasks
        }
        
    except Exception as exc:
        logger.error(f"Error starting automation workflow: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    name="tasks.execute_automation_step",
    bind=True,
    max_retries=3
)
def execute_automation_step(
    self,
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    trigger_data: dict = None
):
    """
    Execute a single automation step (send email)
    """
    try:
        steps_collection = get_sync_automation_steps_collection()
        executions_collection = get_sync_automation_executions_collection()
        subscribers_collection = get_sync_subscribers_collection()
        templates_collection = get_sync_templates_collection()
        segments_collection = get_sync_segments_collection()
        
        # Get step details
        step = steps_collection.find_one({"_id": ObjectId(step_id)})
        if not step:
            logger.error(f"Step not found: {step_id}")
            return {"status": "step_not_found"}
        
        # Get subscriber
        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not subscriber:
            logger.error(f"Subscriber not found: {subscriber_id}")
            return {"status": "subscriber_not_found"}
        
        # Check if subscriber is still active
        if subscriber.get("status") != "active":
            logger.info(f"Subscriber {subscriber_id} is no longer active, skipping step")
            executions_collection.update_one(
                {
                    "automation_step_id": step_id,
                    "subscriber_id": subscriber_id,
                    "status": "scheduled"
                },
                {
                    "$set": {
                        "status": "skipped",
                        "skipped_reason": "subscriber_inactive",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            return {"status": "skipped", "reason": "subscriber_inactive"}
        
        # Check segment conditions
        segment_conditions = step.get("segment_conditions", [])
        if segment_conditions:
            subscriber_segments = subscriber.get("segments", [])
            if not any(seg in subscriber_segments for seg in segment_conditions):
                logger.info(f"Subscriber not in required segments, skipping step")
                executions_collection.update_one(
                    {
                        "automation_step_id": step_id,
                        "subscriber_id": subscriber_id,
                        "status": "scheduled"
                    },
                    {
                        "$set": {
                            "status": "skipped",
                            "skipped_reason": "segment_mismatch",
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                return {"status": "skipped", "reason": "segment_mismatch"}
        
        # Get template
        template = templates_collection.find_one({"_id": ObjectId(step["email_template_id"])})
        if not template:
            logger.error(f"Template not found: {step['email_template_id']}")
            return {"status": "template_not_found"}
        
        # Prepare email data
        email_data = {
            "to_email": subscriber.get("email"),
            "subject": template.get("subject", ""),
            "html_content": template.get("content_html", ""),
            "text_content": template.get("content_text", ""),
            "subscriber_id": subscriber_id,
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "template_id": str(template["_id"]),
            "personalization": {
                **subscriber.get("standard_fields", {}),
                **subscriber.get("custom_fields", {}),
                **trigger_data
            }
        }
        
        # Send email via your existing email sending task
        from tasks.email_campaign_tasks import send_single_campaign_email
        
        result = send_single_campaign_email.delay(
            campaign_id=f"automation_{automation_rule_id}",
            subscriber_data=email_data
        )
        
        # Update execution record
        executions_collection.update_one(
            {
                "automation_step_id": step_id,
                "subscriber_id": subscriber_id,
                "status": "scheduled"
            },
            {
                "$set": {
                    "status": "sent",
                    "executed_at": datetime.utcnow(),
                    "email_task_id": result.id,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        logger.info(f"Executed automation step {step_id} for subscriber {subscriber_id}")
        
        return {
            "status": "success",
            "step_id": step_id,
            "subscriber_id": subscriber_id,
            "email_task_id": result.id
        }
        
    except Exception as exc:
        logger.error(f"Error executing automation step: {exc}")
        
        # Mark as failed
        executions_collection = get_sync_automation_executions_collection()
        executions_collection.update_one(
            {
                "automation_step_id": step_id,
                "subscriber_id": subscriber_id,
                "status": "scheduled"
            },
            {
                "$set": {
                    "status": "failed",
                    "error": str(exc),
                    "failed_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        raise self.retry(exc=exc)


def evaluate_trigger_conditions(conditions: dict, subscriber: dict, trigger_data: dict = None) -> bool:
    """
    Evaluate if trigger conditions are met for a subscriber
    
    Example conditions:
    {
        "field": "signup_date",
        "operator": "older_than",
        "value": 7,
        "unit": "days"
    }
    """
    if not conditions:
        return True
    
    try:
        field = conditions.get("field")
        operator = conditions.get("operator")
        value = conditions.get("value")
        
        # Get field value from subscriber or trigger data
        subscriber_value = subscriber.get(field)
        if subscriber_value is None and trigger_data:
            subscriber_value = trigger_data.get(field)
        
        if subscriber_value is None:
            return False
        
        # Evaluate based on operator
        if operator == "equals":
            return subscriber_value == value
        elif operator == "not_equals":
            return subscriber_value != value
        elif operator == "contains":
            return value in str(subscriber_value)
        elif operator == "greater_than":
            return float(subscriber_value) > float(value)
        elif operator == "less_than":
            return float(subscriber_value) < float(value)
        elif operator == "older_than":
            # For date fields
            if isinstance(subscriber_value, datetime):
                unit = conditions.get("unit", "days")
                if unit == "days":
                    threshold = datetime.utcnow() - timedelta(days=int(value))
                elif unit == "hours":
                    threshold = datetime.utcnow() - timedelta(hours=int(value))
                else:
                    threshold = datetime.utcnow() - timedelta(days=int(value))
                return subscriber_value < threshold
        
        return True
        
    except Exception as e:
        logger.error(f"Error evaluating trigger conditions: {e}")
        return False


@shared_task(name="tasks.cancel_automation_workflow")
def cancel_automation_workflow(automation_rule_id: str, subscriber_id: str):
    """Cancel all pending automation steps for a subscriber"""
    try:
        executions_collection = get_sync_automation_executions_collection()
        
        # Find all scheduled executions
        scheduled_executions = list(executions_collection.find({
            "automation_rule_id": automation_rule_id,
            "subscriber_id": subscriber_id,
            "status": "scheduled"
        }))
        
        # Revoke Celery tasks
        from celery_app import celery_app
        for execution in scheduled_executions:
            if execution.get("task_id"):
                celery_app.control.revoke(execution["task_id"], terminate=True)
        
        # Update status
        result = executions_collection.update_many(
            {
                "automation_rule_id": automation_rule_id,
                "subscriber_id": subscriber_id,
                "status": "scheduled"
            },
            {
                "$set": {
                    "status": "cancelled",
                    "cancelled_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        logger.info(f"Cancelled {result.modified_count} automation steps")
        
        return {
            "status": "success",
            "cancelled_count": result.modified_count
        }
        
    except Exception as e:
        logger.error(f"Error cancelling automation workflow: {e}")
        return {"status": "error", "error": str(e)}