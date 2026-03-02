# backend/tasks/automation_tasks.py
"""
Enhanced Celery tasks for automation workflow execution with critical fixes
"""
from celery import shared_task
from datetime import datetime, timedelta
from bson import ObjectId
import logging
import pytz
from typing import Dict


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
            # FIX C7: subscriber.segments[] is a static array that is never populated.
            # Instead, query the segments collection and evaluate each segment's criteria
            # dynamically against the subscriber.
            target_segments = rule.get("target_segments", [])
            if target_segments:
                segments_collection = get_sync_segments_collection()
                subscriber_in_segment = False
                for seg_id in target_segments:
                    try:
                        segment = segments_collection.find_one({"_id": ObjectId(str(seg_id))})
                        if not segment:
                            continue
                        criteria = segment.get("criteria", {})
                        if _subscriber_matches_segment_criteria(subscriber, criteria):
                            subscriber_in_segment = True
                            break
                    except Exception as _seg_err:
                        logger.warning(f"Segment lookup failed for {seg_id}: {_seg_err}")
                if not subscriber_in_segment:
                    logger.info(f"Subscriber not in target segments for rule: {rule['name']}")
                    continue
            
            # FIX H5: use 'lists' (plural) consistently — check_subscriber_matches_rule also uses 'lists'.
            # Keep a fallback to the legacy 'list' (singular) field for older records.
            target_lists = rule.get("target_lists", [])
            if target_lists:
                subscriber_lists = subscriber.get("lists") or []
                if not subscriber_lists:
                    # Legacy single-list field
                    legacy = subscriber.get("list")
                    subscriber_lists = [legacy] if legacy else []
                target_lists_str = [str(l) for l in target_lists]
                subscriber_lists_str = [str(l) for l in subscriber_lists]
                if not any(l in subscriber_lists_str for l in target_lists_str):
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
        email_config_data = rule.get("email_config", {})
        
        step_subject = step.get("subject_line")
        template_subject = template.get("subject", "")
        final_subject = step_subject if step_subject else template_subject
        
        email_config_for_send = {
            "from_email": email_config_data.get("sender_email"),
            "from_name": email_config_data.get("sender_name"),
            "reply_to": email_config_data.get("reply_to"),
            "subject": final_subject
        }
        
        # Send email via automation email task
        from tasks.automation_email_tasks import send_automation_email
        
        result = send_automation_email.delay(
            subscriber_id=subscriber_id,
            template_id=str(template["_id"]),
            automation_rule_id=automation_rule_id,
            step_id=step_id,
            workflow_instance_id=workflow_instance_id,
            email_config=email_config_for_send,
            field_map=step.get("field_map", {}),
            fallback_values=step.get("fallback_values", {})
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
        if workflow and workflow["completed_steps"] >= workflow["total_steps"]:
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
        try:
            skip_on_failure = rule.get("skip_step_on_failure", False)
            
            if self.request.retries >= self.max_retries:
                if skip_on_failure:
                    logger.info(f"Skipping failed step and continuing workflow")
                    mark_step_failed(executions_collection, step_id, subscriber_id, str(exc))
                else:
                    logger.error(f"Max retries reached, cancelling workflow")
                    mark_step_failed(executions_collection, step_id, subscriber_id, str(exc))
                    cancel_automation_workflow(automation_rule_id, subscriber_id)
                    
                    # Notify admin if enabled
                    if rule.get("notify_on_failure", True):
                        send_failure_notification(automation_rule_id, subscriber_id, str(exc))
        except:
            pass
        
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


@shared_task(name="tasks.check_welcome_automations", bind=True)
def check_welcome_automations(self):
    """Check for new subscribers and trigger welcome automations"""
    try:
        from database import (
            get_sync_subscribers_collection,
            get_sync_automation_rules_collection,
            get_sync_automation_executions_collection
        )
        
        subscribers_collection = get_sync_subscribers_collection()
        automation_rules = get_sync_automation_rules_collection()
        automation_executions = get_sync_automation_executions_collection()
        
        # Get active welcome automations with workflow
        welcome_rules = list(automation_rules.find({
            "trigger": "welcome",
            "status": "active",
        }))
        
        if not welcome_rules:
            logger.info("No active welcome automations found")
            return {"message": "No active welcome automations", "triggered": 0}
        
        logger.info(f"Found {len(welcome_rules)} active welcome automations")
        
        # Get new subscribers from last 10 minutes (to catch any missed)
        ten_minutes_ago = datetime.utcnow() - timedelta(minutes=10)
        new_subscribers = list(subscribers_collection.find({
            "created_at": {"$gte": ten_minutes_ago},
            "status": "active"
        }))
        
        if not new_subscribers:
            logger.info("No new subscribers found")
            return {"message": "No new subscribers", "triggered": 0}
        
        logger.info(f"Found {len(new_subscribers)} new subscribers")
        
        triggered_count = 0
        
        for subscriber in new_subscribers:
            subscriber_id = str(subscriber["_id"])
            subscriber_email = subscriber.get("email", "unknown")
            
            for rule in welcome_rules:
                rule_id = str(rule["_id"])
                rule_name = rule.get("name", "Unnamed")
                
                # Check if already triggered
                existing = automation_executions.find_one({
                    "automation_rule_id": rule_id,
                    "subscriber_id": subscriber_id
                })
                
                if existing:
                    logger.debug(f"Welcome automation {rule_id} already triggered for {subscriber_email}")
                    continue
                
                # Check segment matching
                if not check_subscriber_matches_rule(subscriber_id, rule):
                    continue
                
                # Trigger the automation
                try:
                    logger.info(f"🚀 Triggering welcome automation '{rule_name}' ({rule_id}) for {subscriber_email}")
                    
                    process_automation_trigger.delay("welcome", subscriber_id, {
                        "subscriber_email": subscriber_email,
                        "trigger_time": datetime.utcnow().isoformat()
                    })
                    
                    triggered_count += 1
                    
                except Exception as e:
                    logger.error(f"Failed to trigger automation {rule_id} for {subscriber_id}: {e}")
        
        result = {
            "checked_rules": len(welcome_rules),
            "checked_subscribers": len(new_subscribers),
            "triggered_count": triggered_count
        }
        
        logger.info(f"✅ Welcome automation check complete: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Welcome automation check failed: {e}", exc_info=True)
        return {"error": str(e), "triggered": 0}


@shared_task(name="tasks.check_abandoned_cart_automations", bind=True)
def check_abandoned_cart_automations(self):
    """Check for abandoned carts and trigger automations"""
    try:
        from database import get_sync_automation_rules_collection
        
        automation_rules = get_sync_automation_rules_collection()
        
        abandoned_cart_rules = list(automation_rules.find({
            "trigger": "abandoned_cart",
            "status": "active",
        }))
        
        if not abandoned_cart_rules:
            return {"message": "No active abandoned cart automations", "triggered": 0}
        
        logger.info(f"Checked {len(abandoned_cart_rules)} abandoned cart automations")
        
        return {
            "checked_rules": len(abandoned_cart_rules),
            "triggered_count": 0,
            "message": "Abandoned cart integration pending"
        }
        
    except Exception as e:
        logger.error(f"Abandoned cart automation check failed: {e}")
        return {"error": str(e), "triggered": 0}


@shared_task(name="tasks.check_inactive_subscriber_automations", bind=True)
def check_inactive_subscriber_automations(self):
    """Check for inactive subscribers and trigger re-engagement automations"""
    try:
        from database import (
            get_sync_subscribers_collection,
            get_sync_automation_rules_collection,
            get_sync_automation_executions_collection,
            get_sync_email_logs_collection
        )
        
        subscribers_collection = get_sync_subscribers_collection()
        automation_rules = get_sync_automation_rules_collection()
        automation_executions = get_sync_automation_executions_collection()
        email_logs = get_sync_email_logs_collection()
        
        # Get active inactive subscriber automations
        inactive_rules = list(automation_rules.find({
            "trigger": "inactive",
            "status": "active",
        }))
        
        if not inactive_rules:
            return {"message": "No active inactive subscriber automations", "triggered": 0}
        
        triggered_count = 0
        
        for rule in inactive_rules:
            rule_id = str(rule["_id"])
            
            # Get inactivity threshold (default 30 days)
            trigger_conditions = rule.get("trigger_conditions", {})
            inactive_days = trigger_conditions.get("inactive_days", 30)
            
            cutoff_date = datetime.utcnow() - timedelta(days=inactive_days)
            
            # Find subscribers who haven't opened/clicked any email since cutoff
            active_subscribers = email_logs.distinct("subscriber_id", {
                "created_at": {"$gte": cutoff_date},
                "latest_status": {"$in": ["opened", "clicked"]}
            })
            
            # Get all active subscribers
            all_subscribers = list(subscribers_collection.find({
                "status": "active"
            }, {"_id": 1}))
            
            # Find inactive subscribers (not in active list)
            inactive_subscribers = [
                str(sub["_id"]) for sub in all_subscribers
                if str(sub["_id"]) not in active_subscribers
            ]
            
            for subscriber_id in inactive_subscribers:
                # Check if already triggered
                existing = automation_executions.find_one({
                    "automation_rule_id": rule_id,
                    "subscriber_id": subscriber_id,
                    "started_at": {"$gte": cutoff_date}
                })
                
                if existing:
                    continue
                
                # Trigger re-engagement automation
                process_automation_trigger.delay("inactive", subscriber_id, {
                    "inactive_days": inactive_days,
                    "last_activity": None
                })
                
                triggered_count += 1
        
        return {
            "checked_rules": len(inactive_rules),
            "triggered_count": triggered_count
        }
        
    except Exception as e:
        logger.error(f"Inactive subscriber automation check failed: {e}")
        return {"error": str(e), "triggered": 0}


def _subscriber_matches_segment_criteria(subscriber: Dict, criteria: Dict) -> bool:
    """
    Evaluate whether a subscriber satisfies a segment's stored criteria.

    Supports a simple AND-of-conditions schema:
        {
          "conditions": [
            {"field": "standard.country", "operator": "equals", "value": "US"},
            {"field": "custom.plan",      "operator": "contains", "value": "pro"}
          ]
        }
    If no criteria are defined the segment is considered open (matches everyone).
    """
    if not criteria:
        return True

    conditions = criteria.get("conditions", [])
    if not conditions:
        return True

    for cond in conditions:
        field_path = cond.get("field", "")
        operator = cond.get("operator", "equals")
        expected = cond.get("value", "")

        # Resolve field value from subscriber
        if field_path == "email":
            actual = subscriber.get("email", "")
        elif field_path.startswith("standard."):
            key = field_path[len("standard."):]
            actual = subscriber.get("standard_fields", {}).get(key, "")
        elif field_path.startswith("custom."):
            key = field_path[len("custom."):]
            actual = subscriber.get("custom_fields", {}).get(key, "")
        else:
            actual = subscriber.get(field_path, "")

        actual_str = str(actual).lower() if actual is not None else ""
        expected_str = str(expected).lower()

        if operator in ("equals", "eq"):
            if actual_str != expected_str:
                return False
        elif operator in ("not_equals", "ne", "neq"):
            if actual_str == expected_str:
                return False
        elif operator == "contains":
            if expected_str not in actual_str:
                return False
        elif operator == "not_contains":
            if expected_str in actual_str:
                return False
        elif operator in ("starts_with", "startswith"):
            if not actual_str.startswith(expected_str):
                return False
        elif operator in ("ends_with", "endswith"):
            if not actual_str.endswith(expected_str):
                return False
        elif operator in ("greater_than", "gt"):
            try:
                if not (float(actual_str) > float(expected_str)):
                    return False
            except (ValueError, TypeError):
                return False
        elif operator in ("less_than", "lt"):
            try:
                if not (float(actual_str) < float(expected_str)):
                    return False
            except (ValueError, TypeError):
                return False
        # Unknown operators pass through (don't block)

    return True


def evaluate_trigger_conditions(conditions: Dict, subscriber: Dict, trigger_data: Dict = None) -> bool:
    """
    Evaluate if subscriber meets trigger conditions
    """
    if not conditions:
        return True
    
    try:
        # Check subscriber status
        if conditions.get("status") and subscriber.get("status") != conditions["status"]:
            return False
        
        # Check custom field conditions
        custom_conditions = conditions.get("custom_fields", {})
        subscriber_custom = subscriber.get("custom_fields", {})
        
        for field, expected_value in custom_conditions.items():
            actual_value = subscriber_custom.get(field)
            
            if isinstance(expected_value, dict):
                # Operator-based comparison
                if "$eq" in expected_value and actual_value != expected_value["$eq"]:
                    return False
                if "$ne" in expected_value and actual_value == expected_value["$ne"]:
                    return False
                if "$in" in expected_value and actual_value not in expected_value["$in"]:
                    return False
                if "$gt" in expected_value and not (actual_value and actual_value > expected_value["$gt"]):
                    return False
                if "$gte" in expected_value and not (actual_value and actual_value >= expected_value["$gte"]):
                    return False
                if "$lt" in expected_value and not (actual_value and actual_value < expected_value["$lt"]):
                    return False
                if "$lte" in expected_value and not (actual_value and actual_value <= expected_value["$lte"]):
                    return False
            else:
                if actual_value != expected_value:
                    return False
        
        # Check standard field conditions
        standard_conditions = conditions.get("standard_fields", {})
        subscriber_standard = subscriber.get("standard_fields", {})
        
        for field, expected_value in standard_conditions.items():
            if subscriber_standard.get(field) != expected_value:
                return False
        
        # Check trigger data conditions
        if trigger_data:
            trigger_conditions = conditions.get("trigger_data", {})
            for field, expected_value in trigger_conditions.items():
                if trigger_data.get(field) != expected_value:
                    return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error evaluating trigger conditions: {e}")
        return False


def check_subscriber_matches_rule(subscriber_id: str, rule: Dict) -> bool:
    """
    Check if subscriber matches automation rule's target segments and lists
    """
    try:
        from database import get_sync_subscribers_collection, get_sync_segments_collection
        
        subscribers_collection = get_sync_subscribers_collection()
        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        
        if not subscriber:
            logger.warning(f"Subscriber {subscriber_id} not found")
            return False
        
        # Check status
        if subscriber.get("status") != "active":
            logger.debug(f"Subscriber {subscriber_id} is not active")
            return False
        
        # Get target segments and lists from rule
        target_segments = rule.get("target_segments", [])
        target_lists = rule.get("target_lists", [])
        
        # If no targets specified, match all active subscribers
        if not target_segments and not target_lists:
            logger.debug(f"Rule has no target restrictions, subscriber matches")
            return True
        
        # Check segment matching
        # FIX C7: evaluate segment criteria dynamically instead of reading the static
        # subscriber.segments[] array which is never populated.
        if target_segments:
            segments_collection = get_sync_segments_collection()
            subscriber_in_segment = False
            for seg_id in target_segments:
                try:
                    segment = segments_collection.find_one({"_id": ObjectId(str(seg_id))})
                    if segment and _subscriber_matches_segment_criteria(
                        subscriber, segment.get("criteria", {})
                    ):
                        subscriber_in_segment = True
                        break
                except Exception as _se:
                    logger.warning(f"Segment lookup failed for {seg_id}: {_se}")
            if not subscriber_in_segment:
                logger.debug(f"Subscriber {subscriber_id} not in target segments")
                return False
        
        # Check list matching
        subscriber_lists = subscriber.get("lists", [])
        if target_lists:
            target_lists_str = [str(lst) for lst in target_lists]
            subscriber_lists_str = [str(lst) for lst in subscriber_lists]
            
            matches_list = any(lst in subscriber_lists_str for lst in target_lists_str)
            
            if not matches_list:
                logger.debug(f"Subscriber {subscriber_id} not in target lists")
                return False
        
        logger.debug(f"Subscriber {subscriber_id} matches rule targeting")
        return True
        
    except Exception as e:
        logger.error(f"Error checking subscriber rule match: {e}")
        return False


def get_subscriber_timezone(subscriber: Dict) -> str:
    """
    Get subscriber's timezone, with fallback to UTC
    """
    try:
        timezone = subscriber.get("custom_fields", {}).get("timezone")
        if timezone:
            return timezone
        
        country = subscriber.get("custom_fields", {}).get("country")
        if country:
            country_timezones = {
                "US": "America/New_York",
                "UK": "Europe/London",
                "FR": "Europe/Paris",
                "DE": "Europe/Berlin",
                "JP": "Asia/Tokyo",
                "AU": "Australia/Sydney",
                "CA": "America/Toronto",
                "IN": "Asia/Kolkata",
                "BR": "America/Sao_Paulo",
                "MX": "America/Mexico_City",
            }
            return country_timezones.get(country, "UTC")
        
        return "UTC"
        
    except Exception as e:
        logger.error(f"Error getting subscriber timezone: {e}")
        return "UTC"


@shared_task(name="tasks.process_scheduled_automations", bind=True)
def process_scheduled_automations(self):
    """
    Process scheduled automation steps that are due for execution
    """
    try:
        from database import get_sync_automation_executions_collection
        
        automation_executions = get_sync_automation_executions_collection()
        
        now = datetime.utcnow()
        
        pending_executions = list(automation_executions.find({
            "status": "scheduled",
            "scheduled_for": {"$lte": now}
        }))
        
        if not pending_executions:
            logger.info("No scheduled automation steps due for execution")
            return {"message": "No pending steps", "processed": 0}
        
        logger.info(f"Found {len(pending_executions)} automation steps due for execution")
        
        processed_count = 0

        for execution in pending_executions:
            try:
                execution_id = execution["_id"]

                # FIX H4: atomically claim the execution record before dispatching.
                # If Celery ETA already ran this step it will have updated the status,
                # so this find_one_and_update will return None and we skip safely.
                claimed = automation_executions.find_one_and_update(
                    {"_id": execution_id, "status": "scheduled"},
                    {"$set": {"status": "dispatched_by_poller", "dispatched_at": datetime.utcnow()}},
                    return_document=False  # we only need to know if it matched
                )
                if claimed is None:
                    logger.debug(f"Execution {execution_id} already claimed or completed, skipping")
                    continue

                automation_rule_id = execution.get("automation_rule_id")
                subscriber_id = execution.get("subscriber_id")
                step_id = execution.get("automation_step_id")
                workflow_instance_id = execution.get("workflow_instance_id")

                logger.info(f"Processing automation execution {execution_id}")

                # Execute the step
                execute_automation_step.delay(
                    automation_rule_id,
                    step_id,
                    subscriber_id,
                    workflow_instance_id,
                    execution.get("trigger_data", {})
                )

                processed_count += 1

            except Exception as e:
                logger.error(f"Failed to process execution {execution.get('_id')}: {e}")
        
        result = {
            "processed": processed_count,
            "total_pending": len(pending_executions)
        }
        
        logger.info(f"✅ Processed {processed_count} scheduled automation steps")
        return result
        
    except Exception as e:
        logger.error(f"Failed to process scheduled automations: {e}")
        return {"error": str(e), "processed": 0}


@shared_task(name="tasks.check_daily_birthdays", bind=True)
def check_daily_birthdays(self):
    """Check for subscribers with birthdays today and trigger birthday automations"""
    try:
        from database import (
            get_sync_subscribers_collection,
            get_sync_automation_rules_collection,
            get_sync_automation_executions_collection
        )
        
        subscribers_collection = get_sync_subscribers_collection()
        automation_rules = get_sync_automation_rules_collection()
        automation_executions = get_sync_automation_executions_collection()
        
        birthday_rules = list(automation_rules.find({
            "trigger": "birthday",
            "status": "active",
        }))
        
        if not birthday_rules:
            return {"message": "No active birthday automations", "triggered": 0}
        
        today = datetime.utcnow()
        today_month = today.month
        today_day = today.day
        
        birthday_subscribers = list(subscribers_collection.find({
            "status": "active",
            "custom_fields.birthday": {"$exists": True}
        }))
        
        triggered_count = 0
        
        for subscriber in birthday_subscribers:
            birthday_str = subscriber.get("custom_fields", {}).get("birthday")
            if not birthday_str:
                continue
            
            try:
                if len(birthday_str) == 10:
                    birthday_date = datetime.strptime(birthday_str, "%Y-%m-%d")
                elif len(birthday_str) == 5:
                    birthday_date = datetime.strptime(f"2000-{birthday_str}", "%Y-%m-%d")
                else:
                    continue
                
                if birthday_date.month != today_month or birthday_date.day != today_day:
                    continue
                
                subscriber_id = str(subscriber["_id"])
                
                for rule in birthday_rules:
                    rule_id = str(rule["_id"])
                    
                    if not check_subscriber_matches_rule(subscriber_id, rule):
                        continue
                    
                    start_of_year = datetime(today.year, 1, 1)
                    existing = automation_executions.find_one({
                        "automation_rule_id": rule_id,
                        "subscriber_id": subscriber_id,
                        "started_at": {"$gte": start_of_year}
                    })
                    
                    if existing:
                        continue
                    
                    process_automation_trigger.delay("birthday", subscriber_id, {
                        "birthday": birthday_str,
                        "age": today.year - birthday_date.year if len(birthday_str) == 10 else None
                    })
                    
                    triggered_count += 1
                
            except Exception as e:
                logger.error(f"Failed to process birthday for {subscriber.get('email')}: {e}")
        
        return {
            "checked_rules": len(birthday_rules),
            "checked_subscribers": len(birthday_subscribers),
            "triggered_count": triggered_count
        }
        
    except Exception as e:
        logger.error(f"Birthday automation check failed: {e}")
        return {"error": str(e), "triggered": 0}


@shared_task(name="tasks.detect_at_risk_subscribers", bind=True)
def detect_at_risk_subscribers(self):
    """Detect subscribers at risk of churning"""
    try:
        from database import (
            get_sync_subscribers_collection,
            get_sync_email_logs_collection
        )
        
        subscribers_collection = get_sync_subscribers_collection()
        email_logs = get_sync_email_logs_collection()
        
        days_threshold = 14
        cutoff_date = datetime.utcnow() - timedelta(days=days_threshold)
        
        recently_sent = email_logs.distinct("subscriber_id", {
            "created_at": {"$gte": cutoff_date},
            "latest_status": {"$in": ["sent", "delivered"]}
        })
        
        recently_opened = email_logs.distinct("subscriber_id", {
            "created_at": {"$gte": cutoff_date},
            "latest_status": {"$in": ["opened", "clicked"]}
        })
        
        at_risk_ids = [sid for sid in recently_sent if sid not in recently_opened]
        
        if at_risk_ids:
            subscribers_collection.update_many(
                {"_id": {"$in": [ObjectId(sid) for sid in at_risk_ids]}},
                {"$set": {
                    "custom_fields.at_risk": True,
                    "custom_fields.at_risk_since": datetime.utcnow()
                }}
            )
        
        if recently_opened:
            subscribers_collection.update_many(
                {"_id": {"$in": [ObjectId(sid) for sid in recently_opened]}},
                {"$unset": {
                    "custom_fields.at_risk": "",
                    "custom_fields.at_risk_since": ""
                }}
            )
        
        return {
            "at_risk_count": len(at_risk_ids),
            "engaged_count": len(recently_opened),
            "days_threshold": days_threshold
        }
        
    except Exception as e:
        logger.error(f"At-risk detection failed: {e}")
        return {"error": str(e)}


@shared_task(name="tasks.cleanup_old_events", bind=True)
def cleanup_old_events(self):
    """Cleanup old automation events and executions"""
    try:
        from database import get_sync_automation_executions_collection
        
        automation_executions = get_sync_automation_executions_collection()
        
        cutoff_date = datetime.utcnow() - timedelta(days=90)
        
        result = automation_executions.delete_many({
            "created_at": {"$lt": cutoff_date},
            "status": {"$in": ["completed", "cancelled", "failed"]}
        })
        
        return {
            "deleted_count": result.deleted_count,
            "cutoff_date": cutoff_date.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Event cleanup failed: {e}")
        return {"error": str(e), "deleted_count": 0}
