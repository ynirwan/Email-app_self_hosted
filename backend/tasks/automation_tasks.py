# backend/tasks/automation_tasks.py
"""
Enhanced Celery tasks for automation workflow execution with critical fixes
"""
from celery import shared_task
from datetime import datetime, timedelta
from bson import ObjectId
import logging
import pytz

from database import (
    get_sync_automation_rules_collection,
    get_sync_automation_steps_collection,
    get_sync_automation_executions_collection,
    get_sync_subscribers_collection,
    get_sync_templates_collection,
    get_sync_segments_collection,
    get_sync_suppressions_collection,
    get_sync_workflow_instances_collection
)

logger = logging.getLogger(__name__)


@shared_task(
    name="tasks.process_automation_trigger",
    bind=True,
    max_retries=3,
    default_retry_delay=300
)
def process_automation_trigger(self, trigger_type: str, subscriber_id: str, trigger_data: dict = None):
    """
    Process automation trigger with all critical checks
    """
    try:
        rules_collection = get_sync_automation_rules_collection()
        subscribers_collection = get_sync_subscribers_collection()
        executions_collection = get_sync_automation_executions_collection()
        suppressions_collection = get_sync_suppressions_collection()
        workflow_instances_collection = get_sync_workflow_instances_collection()
        
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
        
        # ⭐ CRITICAL CHECK 1: Subscriber status
        if subscriber.get("status") != "active":
            logger.info(f"Subscriber {subscriber_id} is not active, skipping automation")
            return {"status": "subscriber_inactive"}
        
        # ⭐ CRITICAL CHECK 2: Suppression/Unsubscribe status
        subscriber_email = subscriber.get("email")
        is_suppressed = suppressions_collection.find_one({
            "email": subscriber_email,
            "is_active": True
        })
        
        if is_suppressed:
            logger.info(f"Subscriber {subscriber_email} is suppressed, skipping automation")
            return {"status": "subscriber_suppressed"}
        
        # Process each matching rule
        results = []
        for rule in rules:
            rule_id = str(rule["_id"])
            
            # ⭐ CRITICAL CHECK 3: Check for active workflows
            active_workflow = workflow_instances_collection.find_one({
                "automation_rule_id": rule_id,
                "subscriber_id": subscriber_id,
                "status": "in_progress"
            })
            
            if active_workflow:
                cancel_previous = rule.get("cancel_previous_on_retrigger", True)
                
                if cancel_previous:
                    logger.info(f"Cancelling previous workflow for subscriber {subscriber_id}")
                    cancel_automation_workflow(rule_id, subscriber_id)
                else:
                    logger.info(f"Active workflow exists, skipping new trigger")
                    continue
            
            # ⭐ CRITICAL CHECK 4: Re-trigger policy
            allow_retrigger = rule.get("allow_retrigger", False)
            retrigger_delay_hours = rule.get("retrigger_delay_hours", 24)
            
            if not allow_retrigger and trigger_type not in ["birthday"]:
                already_sent = workflow_instances_collection.find_one({
                    "automation_rule_id": rule_id,
                    "subscriber_id": subscriber_id,
                    "status": {"$in": ["completed"]}
                })
                
                if already_sent:
                    logger.info(f"Automation {rule_id} already completed for {subscriber_id}, skipping")
                    continue
            
            # For retriggerable automations, check minimum delay
            if allow_retrigger and retrigger_delay_hours > 0:
                delay_threshold = datetime.utcnow() - timedelta(hours=retrigger_delay_hours)
                
                recent_execution = workflow_instances_collection.find_one({
                    "automation_rule_id": rule_id,
                    "subscriber_id": subscriber_id,
                    "started_at": {"$gte": delay_threshold}
                })
                
                if recent_execution:
                    logger.info(f"Automation triggered too recently (delay: {retrigger_delay_hours}h)")
                    continue
            
            # ⭐ CRITICAL CHECK 5: Birthday annual check (for birthday automations)
            if trigger_type == "birthday":
                current_year = datetime.utcnow().year
                year_start = datetime(current_year, 1, 1)
                
                sent_this_year = workflow_instances_collection.find_one({
                    "automation_rule_id": rule_id,
                    "subscriber_id": subscriber_id,
                    "status": {"$in": ["completed", "in_progress"]},
                    "started_at": {"$gte": year_start}
                })
                
                if sent_this_year:
                    logger.info(f"Birthday automation already sent this year")
                    continue
            
            # ⭐ CRITICAL CHECK 6: Daily frequency cap
            max_emails_per_day = rule.get("max_emails_per_day", 3)
            if max_emails_per_day > 0:
                today_start = datetime.utcnow().replace(hour=0, minute=0, second=0)
                
                emails_sent_today = executions_collection.count_documents({
                    "subscriber_id": subscriber_id,
                    "status": "sent",
                    "executed_at": {"$gte": today_start}
                })
                
                if emails_sent_today >= max_emails_per_day:
                    logger.info(f"Frequency cap reached ({emails_sent_today}/{max_emails_per_day})")
                    # Schedule for tomorrow
                    tomorrow = today_start + timedelta(days=1, hours=9)  # 9 AM tomorrow
                    
                    start_automation_workflow.apply_async(
                        args=[rule_id, subscriber_id, trigger_data or {}],
                        eta=tomorrow
                    )
                    
                    results.append({
                        "rule_id": rule_id,
                        "rule_name": rule["name"],
                        "status": "scheduled_tomorrow",
                        "reason": "frequency_cap"
                    })
                    continue
            
            # Check targeting (segments/lists)
            target_segments = rule.get("target_segments", [])
            if target_segments:
                subscriber_segments = subscriber.get("segments", [])
                if not any(seg in subscriber_segments for seg in target_segments):
                    logger.info(f"Subscriber not in target segments for rule: {rule['name']}")
                    continue
            
            target_lists = rule.get("target_lists", [])
            if target_lists:
                subscriber_list = subscriber.get("list")
                if subscriber_list not in target_lists:
                    logger.info(f"Subscriber not in target lists for rule: {rule['name']}")
                    continue
            
            # Check trigger conditions
            trigger_conditions = rule.get("trigger_conditions", {})
            if not evaluate_trigger_conditions(trigger_conditions, subscriber, trigger_data):
                logger.info(f"Trigger conditions not met for rule: {rule['name']}")
                continue
            
            # ⭐ All checks passed - Start automation workflow
            logger.info(f"✅ Starting automation workflow for subscriber {subscriber_id}")
            
            result = start_automation_workflow.delay(
                automation_rule_id=rule_id,
                subscriber_id=subscriber_id,
                trigger_data=trigger_data or {}
            )
            
            results.append({
                "rule_id": rule_id,
                "rule_name": rule["name"],
                "task_id": result.id,
                "status": "triggered"
            })
        
        return {
            "status": "success",
            "trigger": trigger_type,
            "subscriber_id": subscriber_id,
            "rules_triggered": len([r for r in results if r.get("status") == "triggered"]),
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
    Start an automation workflow with timezone support and workflow tracking
    """
    try:
        rules_collection = get_sync_automation_rules_collection()
        steps_collection = get_sync_automation_steps_collection()
        executions_collection = get_sync_automation_executions_collection()
        subscribers_collection = get_sync_subscribers_collection()
        workflow_instances_collection = get_sync_workflow_instances_collection()
        
        # Get automation rule
        rule = rules_collection.find_one({"_id": ObjectId(automation_rule_id)})
        if not rule:
            logger.error(f"Automation rule not found: {automation_rule_id}")
            return {"status": "rule_not_found"}
        
        # Get subscriber
        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not subscriber:
            logger.error(f"Subscriber not found: {subscriber_id}")
            return {"status": "subscriber_not_found"}
        
        # Get all steps for this automation
        steps = list(steps_collection.find({
            "automation_rule_id": automation_rule_id
        }).sort("step_order", 1))
        
        if not steps:
            logger.warning(f"No steps found for automation: {automation_rule_id}")
            return {"status": "no_steps"}
        
        # ⭐ CREATE WORKFLOW INSTANCE
        workflow_instance_id = str(ObjectId())
        workflow_instance = {
            "_id": ObjectId(workflow_instance_id),
            "automation_rule_id": automation_rule_id,
            "subscriber_id": subscriber_id,
            "status": "in_progress",
            "started_at": datetime.utcnow(),
            "completed_at": None,
            "total_steps": len(steps),
            "completed_steps": 0,
            "emails_sent": 0,
            "emails_opened": 0,
            "emails_clicked": 0,
            "trigger_data": trigger_data or {},
            "created_at": datetime.utcnow()
        }
        workflow_instances_collection.insert_one(workflow_instance)
        
        # ⭐ DETERMINE TIMEZONE
        automation_timezone = rule.get("timezone", "UTC")
        use_subscriber_tz = rule.get("use_subscriber_timezone", False)
        
        if use_subscriber_tz:
            subscriber_tz = subscriber.get("standard_fields", {}).get("timezone") or \
                           subscriber.get("timezone") or \
                           automation_timezone
        else:
            subscriber_tz = automation_timezone
        
        try:
            tz = pytz.timezone(subscriber_tz)
            current_time = datetime.now(tz)
        except:
            # Fallback to UTC if timezone invalid
            tz = pytz.UTC
            current_time = datetime.now(tz)
            logger.warning(f"Invalid timezone {subscriber_tz}, using UTC")
        
        logger.info(f"Using timezone: {subscriber_tz} (current time: {current_time})")
        
        # Get quiet hours settings
        respect_quiet_hours = rule.get("respect_quiet_hours", True)
        quiet_hours_start = rule.get("quiet_hours_start", 22)  # 10 PM
        quiet_hours_end = rule.get("quiet_hours_end", 8)  # 8 AM
        
        # Schedule each step
        scheduled_tasks = []
        for step in steps:
            delay_hours = step.get("delay_hours", 0)
            
            # Calculate ETA in subscriber's timezone
            eta_local = current_time + timedelta(hours=delay_hours)
            
            # ⭐ CHECK QUIET HOURS
            if respect_quiet_hours and delay_hours > 0:
                hour = eta_local.hour
                
                # Check if in quiet hours
                if quiet_hours_start > quiet_hours_end:
                    # Quiet hours cross midnight (e.g., 22:00 - 08:00)
                    in_quiet_hours = hour >= quiet_hours_start or hour < quiet_hours_end
                else:
                    # Normal quiet hours (e.g., 00:00 - 06:00)
                    in_quiet_hours = quiet_hours_start <= hour < quiet_hours_end
                
                if in_quiet_hours:
                    # Reschedule to end of quiet hours
                    eta_local = eta_local.replace(
                        hour=quiet_hours_end,
                        minute=0,
                        second=0
                    )
                    
                    # If we went backwards in time, add a day
                    if eta_local < current_time:
                        eta_local += timedelta(days=1)
                    
                    logger.info(f"Adjusted for quiet hours: {eta_local}")
            
            # Convert back to UTC for Celery
            eta_utc = eta_local.astimezone(pytz.UTC).replace(tzinfo=None)
            
            result = execute_automation_step.apply_async(
                args=[
                    automation_rule_id,
                    str(step["_id"]),
                    subscriber_id,
                    workflow_instance_id,
                    trigger_data or {}
                ],
                eta=eta_utc
            )
            
            # Record the scheduled execution
            execution_record = {
                "_id": ObjectId(),
                "workflow_instance_id": workflow_instance_id,
                "automation_rule_id": automation_rule_id,
                "automation_step_id": str(step["_id"]),
                "subscriber_id": subscriber_id,
                "task_id": result.id,
                "scheduled_at": datetime.utcnow(),
                "scheduled_for": eta_utc,
                "scheduled_for_local": eta_local.strftime("%Y-%m-%d %H:%M:%S %Z"),
                "timezone": subscriber_tz,
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
                "scheduled_for_utc": eta_utc.isoformat(),
                "scheduled_for_local": eta_local.strftime("%Y-%m-%d %H:%M:%S %Z")
            })
        
        logger.info(f"Started automation workflow: {automation_rule_id} for subscriber: {subscriber_id}")
        logger.info(f"Workflow instance: {workflow_instance_id}, Timezone: {subscriber_tz}")
        
        return {
            "status": "success",
            "workflow_instance_id": workflow_instance_id,
            "automation_rule_id": automation_rule_id,
            "subscriber_id": subscriber_id,
            "timezone": subscriber_tz,
            "steps_scheduled": len(scheduled_tasks),
            "tasks": scheduled_tasks
        }
        
    except Exception as exc:
        logger.error(f"Error starting automation workflow: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    name="tasks.execute_automation_step",
    bind=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=3600,
    retry_jitter=True
)
def execute_automation_step(
    self,
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    workflow_instance_id: str,
    trigger_data: dict = None
):
    """
    Execute automation step with critical checks and failure handling
    """
    try:
        rules_collection = get_sync_automation_rules_collection()
        steps_collection = get_sync_automation_steps_collection()
        executions_collection = get_sync_automation_executions_collection()
        subscribers_collection = get_sync_subscribers_collection()
        templates_collection = get_sync_templates_collection()
        suppressions_collection = get_sync_suppressions_collection()
        workflow_instances_collection = get_sync_workflow_instances_collection()
        
        # Get automation rule
        rule = rules_collection.find_one({"_id": ObjectId(automation_rule_id)})
        if not rule:
            logger.error(f"Automation rule not found: {automation_rule_id}")
            return {"status": "rule_not_found"}
        
        # Get step details
        step = steps_collection.find_one({"_id": ObjectId(step_id)})
        if not step:
            logger.error(f"Step not found: {step_id}")
            return {"status": "step_not_found"}
        
        # ⭐ CRITICAL CHECK: Subscriber still active and not suppressed
        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not subscriber:
            logger.error(f"Subscriber not found: {subscriber_id}")
            mark_step_failed(executions_collection, step_id, subscriber_id, "subscriber_not_found")
            return {"status": "subscriber_not_found"}
        
        subscriber_email = subscriber.get("email")
        
        # Check if subscriber unsubscribed
        if subscriber.get("status") != "active":
            logger.info(f"Subscriber {subscriber_id} is no longer active")
            
            if rule.get("exit_on_unsubscribe", True):
                cancel_automation_workflow(automation_rule_id, subscriber_id)
            
            mark_step_failed(executions_collection, step_id, subscriber_id, "subscriber_inactive")
            return {"status": "subscriber_inactive"}
        
        # Check suppression
        is_suppressed = suppressions_collection.find_one({
            "email": subscriber_email,
            "is_active": True
        })
        
        if is_suppressed:
            logger.info(f"Subscriber {subscriber_email} is suppressed")
            
            if rule.get("exit_on_unsubscribe", True):
                cancel_automation_workflow(automation_rule_id, subscriber_id)
            
            mark_step_failed(executions_collection, step_id, subscriber_id, "subscriber_suppressed")
            return {"status": "subscriber_suppressed"}
        
        # ⭐ CRITICAL CHECK: Check if goal already achieved
        if rule.get("exit_on_goal_achieved", True):
            primary_goal = rule.get("primary_goal")
            
            if primary_goal:
                goal_achieved = check_if_goal_achieved(
                    automation_rule_id,
                    subscriber_id,
                    primary_goal
                )
                
                if goal_achieved:
                    logger.info(f"Goal already achieved, cancelling workflow")
                    cancel_automation_workflow(automation_rule_id, subscriber_id)
                    return {"status": "goal_achieved"}
        
        # Get template
        template = templates_collection.find_one({"_id": ObjectId(step["email_template_id"])})
        if not template:
            logger.error(f"Template not found: {step['email_template_id']}")
            mark_step_failed(executions_collection, step_id, subscriber_id, "template_not_found")
            return {"status": "template_not_found"}
        
        # Prepare email data
        email_config = rule.get("email_config", {})
        
        email_data = {
            "to_email": subscriber_email,
            "from_email": email_config.get("sender_email"),
            "from_name": email_config.get("sender_name"),
            "reply_to": email_config.get("reply_to"),
            "subject": template.get("subject", ""),
            "html_content": template.get("content_html", ""),
            "text_content": template.get("content_text", ""),
            "subscriber_id": subscriber_id,
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "workflow_instance_id": workflow_instance_id,
            "template_id": str(template["_id"]),
            "personalization": {
                **subscriber.get("standard_fields", {}),
                **subscriber.get("custom_fields", {}),
                **(trigger_data or {})
            }
        }
        
        # Send email via campaign task
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
                "workflow_instance_id": workflow_instance_id,
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
        
        # Update workflow instance
        workflow_instances_collection.update_one(
            {"_id": ObjectId(workflow_instance_id)},
            {
                "$inc": {
                    "completed_steps": 1,
                    "emails_sent": 1
                },
                "$set": {
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Check if workflow completed
        workflow = workflow_instances_collection.find_one({"_id": ObjectId(workflow_instance_id)})
        if workflow["completed_steps"] >= workflow["total_steps"]:
            workflow_instances_collection.update_one(
                {"_id": ObjectId(workflow_instance_id)},
                {
                    "$set": {
                        "status": "completed",
                        "completed_at": datetime.utcnow()
                    }
                }
            )
            logger.info(f"Workflow {workflow_instance_id} completed!")
        
        logger.info(f"Executed automation step {step_id} for subscriber {subscriber_id}")
        
        return {
            "status": "success",
            "step_id": step_id,
            "subscriber_id": subscriber_id,
            "workflow_instance_id": workflow_instance_id,
            "email_task_id": result.id
        }
        
    except Exception as exc:
        logger.error(f"Error executing automation step: {exc}")
        
        # Check if we should retry or skip
        skip_on_failure = rule.get("skip_step_on_failure", False)
        
        if self.request.retries >= self.max_retries:
            if skip_on_failure:
                logger.info(f"Skipping failed step and continuing workflow")
                mark_step_failed(executions_collection, step_id, subscriber_id, str(exc))
                # Continue to next step
                # TODO: Implement next step logic
            else:
                logger.error(f"Max retries reached, cancelling workflow")
                mark_step_failed(executions_collection, step_id, subscriber_id, str(exc))
                cancel_automation_workflow(automation_rule_id, subscriber_id)
                
                # Notify admin if enabled
                if rule.get("notify_on_failure", True):
                    send_failure_notification(automation_rule_id, subscriber_id, str(exc))
        
        raise self.retry(exc=exc)


# Helper functions
def mark_step_failed(executions_collection, step_id, subscriber_id, reason):
    """Mark a step as failed"""
    executions_collection.update_one(
        {
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id,
            "status": "scheduled"
        },
        {
            "$set": {
                "status": "failed",
                "error": reason,
                "failed_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
        }
    )


def check_if_goal_achieved(automation_rule_id, subscriber_id, goal_config):
    """Check if automation goal has been achieved"""
    from database import get_sync_email_events_collection
    
    if not goal_config:
        return False
    
    events_collection = get_sync_email_events_collection()
    goal_type = goal_config.get("goal_type")
    tracking_window_days = goal_config.get("tracking_window_days", 30)
    
    start_date = datetime.utcnow() - timedelta(days=tracking_window_days)
    
    if goal_type == "purchase":
        # Check for purchase events
        purchase_event = events_collection.find_one({
            "subscriber_id": subscriber_id,
            "event_type": "purchase",
            "automation_rule_id": automation_rule_id,
            "timestamp": {"$gte": start_date}
        })
        return purchase_event is not None
    
    elif goal_type == "click":
        # Check for click events
        click_event = events_collection.find_one({
            "subscriber_id": subscriber_id,
            "event_type": "click",
            "automation_rule_id": automation_rule_id,
            "timestamp": {"$gte": start_date}
        })
        return click_event is not None
    
    return False


def send_failure_notification(automation_rule_id, subscriber_id, error_message):
    """Send failure notification to admin"""
    # TODO: Implement admin notification
    logger.error(f"ADMIN ALERT: Automation {automation_rule_id} failed for subscriber {subscriber_id}: {error_message}")


@shared_task(name="tasks.cancel_automation_workflow")
def cancel_automation_workflow(automation_rule_id: str, subscriber_id: str):
    """Cancel all pending automation steps for a subscriber"""
    try:
        executions_collection = get_sync_automation_executions_collection()
        workflow_instances_collection = get_sync_workflow_instances_collection()
        
        # Find active workflow instance
        workflow = workflow_instances_collection.find_one({
            "automation_rule_id": automation_rule_id,
            "subscriber_id": subscriber_id,
            "status": "in_progress"
        })
        
        if not workflow:
            return {"status": "no_active_workflow"}
        
        workflow_instance_id = str(workflow["_id"])
        
        # Find all scheduled executions
        scheduled_executions = list(executions_collection.find({
            "workflow_instance_id": workflow_instance_id,
            "status": "scheduled"
        }))
        
        # Revoke Celery tasks
        from celery_app import celery_app
        for execution in scheduled_executions:
            if execution.get("task_id"):
                celery_app.control.revoke(execution["task_id"], terminate=True)
        
        # Update execution status
        result = executions_collection.update_many(
            {
                "workflow_instance_id": workflow_instance_id,
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
        
        # Update workflow instance
        workflow_instances_collection.update_one(
            {"_id": ObjectId(workflow_instance_id)},
            {
                "$set": {
                    "status": "cancelled",
                    "completed_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        logger.info(f"Cancelled {result.modified_count} automation steps for workflow {workflow_instance_id}")
        
        return {
            "status": "success",
            "workflow_instance_id": workflow_instance_id,
            "cancelled_count": result.modified_count
        }
        
    except Exception as e:
        logger.error(f"Error cancelling automation workflow: {e}")
        return {"status": "error", "error": str(e)}
    
@shared_task(name="tasks.check_daily_birthdays")
def check_daily_birthdays():
    """
    Daily task to check for subscribers with birthdays today
    Respects automation timezone settings
    """
    try:
        subscribers_collection = get_sync_subscribers_collection()
        rules_collection = get_sync_automation_rules_collection()
        
        # Get today's date
        today = datetime.utcnow()
        today_month = today.month
        today_day = today.day
        
        logger.info(f"🎂 Checking birthdays for {today_month}/{today_day}")
        
        # Find active birthday automation rules
        birthday_rules = list(rules_collection.find({
            "trigger": "birthday",
            "status": "active",
            "deleted_at": {"$exists": False}
        }))
        
        if not birthday_rules:
            logger.info("No active birthday automation rules found")
            return {"status": "no_rules"}
        
        # For each rule, check in its timezone
        triggered_count = 0
        
        for rule in birthday_rules:
            rule_timezone = rule.get("timezone", "UTC")
            
            try:
                tz = pytz.timezone(rule_timezone)
                rule_today = datetime.now(tz)
                rule_month = rule_today.month
                rule_day = rule_today.day
            except:
                rule_month = today_month
                rule_day = today_day
            
            logger.info(f"Checking rule '{rule['name']}' in timezone {rule_timezone} ({rule_month}/{rule_day})")
            
            # Find subscribers with birthday today in this timezone
            # Assuming birthday stored as "YYYY-MM-DD" in standard_fields.birthday
            subscribers = list(subscribers_collection.find({
                "status": "active",
                "$or": [
                    {
                        "$expr": {
                            "$and": [
                                {"$eq": [{"$month": {"$toDate": "$standard_fields.birthday"}}, rule_month]},
                                {"$eq": [{"$dayOfMonth": {"$toDate": "$standard_fields.birthday"}}, rule_day]}
                            ]
                        }
                    },
                    {
                        # Fallback for string format "MM-DD"
                        "standard_fields.birthday": f"{rule_month:02d}-{rule_day:02d}"
                    }
                ]
            }))
            
            logger.info(f"Found {len(subscribers)} subscribers with birthdays today in {rule_timezone}")
            
            for subscriber in subscribers:
                subscriber_id = str(subscriber["_id"])
                
                # Trigger birthday automation
                result = process_automation_trigger.delay(
                    trigger_type="birthday",
                    subscriber_id=subscriber_id,
                    trigger_data={
                        "trigger_type": "birthday",
                        "birthday_date": subscriber.get("standard_fields", {}).get("birthday"),
                        "year": rule_today.year
                    }
                )
                
                triggered_count += 1
        
        return {
            "status": "success",
            "rules_checked": len(birthday_rules),
            "automations_triggered": triggered_count,
            "date": f"{today_month}/{today_day}/{today.year}"
        }
        
    except Exception as e:
        logger.error(f"Error checking daily birthdays: {e}")
        return {"status": "error", "error": str(e)}

@shared_task(name="tasks.cleanup_old_events")
def cleanup_old_events(days_to_keep: int = 90):
    """
    Clean up old events to prevent database bloat
    Keeps events for specified days (default 90 days)
    """
    try:
        events_collection = get_sync_events_collection()
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        result = events_collection.delete_many({
            "created_at": {"$lt": cutoff_date},
            "processed": True
        })
        
        logger.info(f"🧹 Cleaned up {result.deleted_count} old events (older than {days_to_keep} days)")
        
        return {
            "status": "success",
            "deleted_count": result.deleted_count,
            "cutoff_date": cutoff_date.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Event cleanup failed: {e}")
        return {"status": "error", "error": str(e)}   

@shared_task(name="tasks.check_inactive_subscribers")
def check_inactive_subscribers():
    """
    Daily task to detect inactive subscribers and trigger re-engagement automations
    Checks for subscribers who haven't opened/clicked emails in X days
    """
    try:
        subscribers_collection = get_sync_subscribers_collection()
        rules_collection = get_sync_automation_rules_collection()
        email_events_collection = get_sync_email_events_collection()
        
        logger.info("🔍 Checking for inactive subscribers...")
        
        # Find active automation rules for inactive triggers
        inactive_rules = list(rules_collection.find({
            "trigger": {"$in": ["inactive_30_days", "inactive_60_days", "inactive_90_days"]},
            "status": "active",
            "deleted_at": {"$exists": False}
        }))
        
        if not inactive_rules:
            logger.info("No active inactive subscriber automation rules found")
            return {"status": "no_rules"}
        
        triggered_count = 0
        
        for rule in inactive_rules:
            rule_id = str(rule["_id"])
            trigger = rule["trigger"]
            
            # Extract days from trigger name
            days_map = {
                "inactive_30_days": 30,
                "inactive_60_days": 60,
                "inactive_90_days": 90
            }
            
            inactive_days = days_map.get(trigger, 30)
            cutoff_date = datetime.utcnow() - timedelta(days=inactive_days)
            
            logger.info(f"Checking rule '{rule['name']}' for {inactive_days} days inactivity")
            
            # Find subscribers who:
            # 1. Are active
            # 2. Haven't had any email events (open/click) since cutoff date
            # 3. Match target segments (if specified)
            
            target_segments = rule.get("target_segments", [])
            target_lists = rule.get("target_lists", [])
            
            # Build base query
            query = {
                "status": "active",
                "created_at": {"$lt": cutoff_date}  # Account older than inactive period
            }
            
            if target_segments:
                query["segments"] = {"$in": target_segments}
            
            if target_lists:
                query["list"] = {"$in": target_lists}
            
            # Find all potentially inactive subscribers
            potential_inactive = list(subscribers_collection.find(query))
            
            logger.info(f"Found {len(potential_inactive)} potential inactive subscribers")
            
            # Check each subscriber's email activity
            for subscriber in potential_inactive:
                subscriber_id = str(subscriber["_id"])
                
                # Check for recent email events
                recent_activity = email_events_collection.find_one({
                    "subscriber_id": subscriber_id,
                    "event_type": {"$in": ["opened", "clicked"]},
                    "timestamp": {"$gte": cutoff_date}
                })
                
                if recent_activity:
                    # Subscriber is active, skip
                    continue
                
                # Check if automation already triggered for this subscriber
                from database import get_sync_workflow_instances_collection
                workflow_instances = get_sync_workflow_instances_collection()
                
                # Check if already triggered in the last 30 days
                recent_trigger = workflow_instances.find_one({
                    "automation_rule_id": rule_id,
                    "subscriber_id": subscriber_id,
                    "started_at": {"$gte": datetime.utcnow() - timedelta(days=30)}
                })
                
                if recent_trigger:
                    logger.info(f"Inactive automation recently triggered for {subscriber_id}")
                    continue
                
                # Trigger inactive automation
                logger.info(f"📧 Triggering inactive automation for subscriber {subscriber_id}")
                
                result = process_automation_trigger.delay(
                    trigger_type=trigger,
                    subscriber_id=subscriber_id,
                    trigger_data={
                        "trigger_type": trigger,
                        "inactive_days": inactive_days,
                        "last_activity": cutoff_date.isoformat(),
                        "subscriber_email": subscriber.get("email")
                    }
                )
                
                triggered_count += 1
        
        logger.info(f"✅ Inactive check complete. Triggered {triggered_count} automations")
        
        return {
            "status": "success",
            "rules_checked": len(inactive_rules),
            "automations_triggered": triggered_count,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error checking inactive subscribers: {e}")
        return {"status": "error", "error": str(e)}


@shared_task(name="tasks.detect_at_risk_subscribers")
def detect_at_risk_subscribers():
    """
    Detect subscribers at risk of becoming inactive
    Marks subscribers who haven't engaged in 15-20 days
    """
    try:
        subscribers_collection = get_sync_subscribers_collection()
        email_events_collection = get_sync_email_events_collection()
        
        logger.info("⚠️ Detecting at-risk subscribers...")
        
        # Find subscribers with no engagement in 15-20 days
        warning_start = datetime.utcnow() - timedelta(days=20)
        warning_end = datetime.utcnow() - timedelta(days=15)
        
        active_subscribers = list(subscribers_collection.find({
            "status": "active",
            "created_at": {"$lt": warning_start}
        }))
        
        at_risk_count = 0
        
        for subscriber in active_subscribers:
            subscriber_id = str(subscriber["_id"])
            
            # Check last engagement
            last_engagement = email_events_collection.find_one(
                {
                    "subscriber_id": subscriber_id,
                    "event_type": {"$in": ["opened", "clicked"]}
                },
                sort=[("timestamp", -1)]
            )
            
            if last_engagement:
                last_activity = last_engagement["timestamp"]
                
                # Check if in at-risk window
                if warning_start >= last_activity >= warning_end:
                    # Mark as at-risk
                    subscribers_collection.update_one(
                        {"_id": ObjectId(subscriber_id)},
                        {
                            "$set": {
                                "at_risk": True,
                                "at_risk_since": datetime.utcnow(),
                                "last_engagement": last_activity
                            }
                        }
                    )
                    at_risk_count += 1
            else:
                # No engagement ever - mark as at-risk
                if (datetime.utcnow() - subscriber["created_at"]).days >= 15:
                    subscribers_collection.update_one(
                        {"_id": ObjectId(subscriber_id)},
                        {
                            "$set": {
                                "at_risk": True,
                                "at_risk_since": datetime.utcnow(),
                                "last_engagement": None
                            }
                        }
                    )
                    at_risk_count += 1
        
        logger.info(f"✅ Marked {at_risk_count} subscribers as at-risk")
        
        return {
            "status": "success",
            "at_risk_count": at_risk_count,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error detecting at-risk subscribers: {e}")
        return {"status": "error", "error": str(e)}     
