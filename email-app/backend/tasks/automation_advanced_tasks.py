# backend/tasks/automation_advanced_tasks.py
"""
Celery tasks for advanced automation features
"""
from celery import shared_task
from datetime import datetime, timedelta
from bson import ObjectId
import logging
import random
import requests

from database import (
    get_sync_automation_rules_collection,
    get_sync_automation_steps_collection,
    get_sync_automation_executions_collection,
    get_sync_subscribers_collection,
    get_sync_email_events_collection
)

logger = logging.getLogger(__name__)


@shared_task(name="tasks.execute_conditional_step")
def execute_conditional_step(
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    trigger_data: dict = None
):
    """
    Execute a conditional branching step
    Evaluates condition and routes to appropriate path
    """
    try:
        steps_collection = get_sync_automation_steps_collection()
        executions_collection = get_sync_automation_executions_collection()
        email_events_collection = get_sync_email_events_collection()
        
        step = steps_collection.find_one({"_id": ObjectId(step_id)})
        if not step or step.get("step_type") != "condition":
            return {"status": "invalid_step"}
        
        conditional_config = step.get("conditional_branch", {})
        condition_type = conditional_config.get("condition_type")
        wait_hours = conditional_config.get("wait_time_hours", 24)
        
        # Wait for the specified time before checking condition
        check_time = datetime.utcnow() - timedelta(hours=wait_hours)
        
        # Evaluate condition
        condition_met = False
        
        if condition_type == "opened_email":
            # Check if subscriber opened previous email
            previous_execution = executions_collection.find_one({
                "automation_rule_id": automation_rule_id,
                "subscriber_id": subscriber_id,
                "step_order": step["step_order"] - 1
            })
            
            if previous_execution:
                condition_met = previous_execution.get("opened_at") is not None
        
        elif condition_type == "clicked_link":
            # Check if subscriber clicked a link
            previous_execution = executions_collection.find_one({
                "automation_rule_id": automation_rule_id,
                "subscriber_id": subscriber_id,
                "step_order": step["step_order"] - 1
            })
            
            if previous_execution:
                condition_met = previous_execution.get("clicked_at") is not None
        
        elif condition_type == "segment_match":
            # Check if subscriber is in specific segment
            subscribers_collection = get_sync_subscribers_collection()
            subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
            if not subscriber:
                logger.error(f"Subscriber not found: {subscriber_id}")
                condition_met = False
            else:   
                required_segments = conditional_config.get("condition_value", [])
                subscriber_segments = subscriber.get("segments", [])
                if not subscriber_segments:
                    condition_met = any(seg in subscriber_segments for seg in required_segments)
                if isinstance(required_segments, list):
                    condition_met = any(seg in subscriber_segments for seg in required_segments)
                else:
                # Single segment string
                    condition_met = required_segments in subscriber_segments
        
                logger.info(f"Segment match check: subscriber_segments={subscriber_segments}, "
                    f"required={required_segments}, met={condition_met}")
                
        elif condition_type == "field_equals":
            from database import get_sync_subscribers_collection

            # Check if field equals value
            subscribers_collection = get_sync_subscribers_collection()
            subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
            if not subscriber:
                logger.error(f"Subscriber not found: {subscriber_id}")
                condition_met = False
            else:

                field_name = conditional_config.get("field_name")
                field_config = conditional_config.get("field_config", {})
                field_tier = field_config.get("field_tier", "custom")  # standard or custom
                expected_value = conditional_config.get("condition_value")

                if not field_name or expected_value is None:
                    logger.error(f"Invalid field_equals config: {field_config}")
                    condition_met = False
                else:
                    
                    # Get actual value from subscriber
                    if field_tier == "standard":
                        actual_value = subscriber.get("standard_fields", {}).get(field_name)
                    else:
                        actual_value = subscriber.get("custom_fields", {}).get(field_name)
            
            # Compare values (case-insensitive for strings)
                    if isinstance(actual_value, str) and isinstance(expected_value, str):
                        condition_met = actual_value.lower() == expected_value.lower()
                    else:
                        condition_met = actual_value == expected_value
            
                    logger.info(f"Field equals check: {field_name}={actual_value}, "
                       f"expected={expected_value}, met={condition_met}")



        # ⭐ FIX: Implement field contains condition
        elif condition_type == "field_contains":
            from database import get_sync_subscribers_collection
    
            subscribers_collection = get_sync_subscribers_collection()
            subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
    
            if not subscriber:
                logger.error(f"Subscriber not found: {subscriber_id}")
                condition_met = False
            else:
        # Get field configuration
                field_config = conditional_config.get("field_config", {})
                field_name = field_config.get("field_name")
                search_text = field_config.get("search_text", "")
                field_tier = field_config.get("field_tier", "custom")
        
                if not field_name or not search_text:
                    logger.error(f"Invalid field_contains config: {field_config}")
                    condition_met = False
                else:
            # Get actual value
                    if field_tier == "standard":
                       actual_value = subscriber.get("standard_fields", {}).get(field_name, "")
                    else:
                       actual_value = subscriber.get("custom_fields", {}).get(field_name, "")
            
            # Check if search text is in actual value (case-insensitive)
                    if isinstance(actual_value, str):
                        condition_met = search_text.lower() in actual_value.lower()
                    else:
                # Convert to string and search
                        condition_met = search_text.lower() in str(actual_value).lower()
            
                    logger.info(f"Field contains check: {field_name} contains '{search_text}', "
                        f"actual='{actual_value}', met={condition_met}")
                    
        # Record condition result
        executions_collection.insert_one({
            "_id": ObjectId(),
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id,
            "step_type": "condition",
            "step_order": step["step_order"],
            "condition_result": condition_met,
            "path_taken": "true" if condition_met else "false",
            "executed_at": datetime.utcnow(),
            "created_at": datetime.utcnow()
        })
        
        # Schedule next steps based on path
        if condition_met:
            next_step_ids = conditional_config.get("true_path_step_ids", [])
        else:
            next_step_ids = conditional_config.get("false_path_step_ids", [])
        
        # Schedule next steps
        for next_step_id in next_step_ids:
            from tasks.automation_tasks import execute_automation_step
            execute_automation_step.delay(
                automation_rule_id,
                next_step_id,
                subscriber_id,
                trigger_data or {}
            )
        
        return {
            "status": "success",
            "condition_met": condition_met,
            "next_steps_scheduled": len(next_step_ids)
        }
        
    except Exception as e:
        logger.error(f"Error executing conditional step: {e}")
        return {"status": "error", "error": str(e)}


@shared_task(name="tasks.execute_ab_test_step")
def execute_ab_test_step(
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    trigger_data: dict = None
):
    """
    Execute an A/B test step
    Randomly assigns variant and sends appropriate email
    """
    try:
        steps_collection = get_sync_automation_steps_collection()
        executions_collection = get_sync_automation_executions_collection()
        
        step = steps_collection.find_one({"_id": ObjectId(step_id)})
        if not step:
            return {"status": "step_not_found"}
        
        ab_config = step.get("ab_test_config", {})
        if not ab_config:
            return {"status": "no_ab_config"}
        
        # Randomly assign variant based on percentages
        variant_a_pct = ab_config.get("variant_a_percentage", 50)
        random_value = random.randint(1, 100)
        
        if random_value <= variant_a_pct:
            variant = "A"
            template_id = ab_config["variant_a_template_id"]
        else:
            variant = "B"
            template_id = ab_config["variant_b_template_id"]
        
        # Get subscriber and template
        subscribers_collection = get_sync_subscribers_collection()
        templates_collection = get_sync_templates_collection()
        
        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        template = templates_collection.find_one({"_id": ObjectId(template_id)})
        
        if not subscriber or not template:
            return {"status": "subscriber_or_template_not_found"}
        
        variant_key = f"variant_{variant.lower()}_subject"
        ab_subject = ab_config.get(variant_key)  # Check for variant_a_subject or variant_b_subject
        final_subject = ab_subject if ab_subject else template.get("subject", "")

        
        # Prepare email data
        email_data = {
            "to_email": subscriber.get("email"),
            "subject": final_subject,  # ✅ Use A/B variant subject if provided
            "html_content": template.get("content_html", ""),
            "subscriber_id": subscriber_id,
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "template_id": template_id,
            "ab_variant": variant,
            "personalization": {
                **subscriber.get("standard_fields", {}),
                **subscriber.get("custom_fields", {}),
                **trigger_data
            }
        }
        
        # Send email
        from tasks.email_campaign_tasks import send_single_campaign_email
        result = send_single_campaign_email.delay(
            campaign_id=f"automation_{automation_rule_id}",
            subscriber_data=email_data
        )
        
        # Record execution with variant
        executions_collection.insert_one({
            "_id": ObjectId(),
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id,
            "step_type": "ab_split",
            "step_order": step["step_order"],
            "ab_variant": variant,
            "template_id": template_id,
            "status": "sent",
            "executed_at": datetime.utcnow(),
            "email_task_id": result.id,
            "created_at": datetime.utcnow()
        })
        
        logger.info(f"A/B test email sent: variant {variant} for subscriber {subscriber_id}")
        
        return {
            "status": "success",
            "variant": variant,
            "template_id": template_id,
            "email_task_id": result.id
        }
        
    except Exception as e:
        logger.error(f"Error executing A/B test step: {e}")
        return {"status": "error", "error": str(e)}


@shared_task(name="tasks.wait_for_event_step")
def wait_for_event_step(
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    trigger_data: dict = None
):
    """
    Wait for a specific event before continuing automation
    Schedules check task to run periodically
    """
    try:
        steps_collection = get_sync_automation_steps_collection()
        executions_collection = get_sync_automation_executions_collection()
        
        step = steps_collection.find_one({"_id": ObjectId(step_id)})
        if not step:
            return {"status": "step_not_found"}
        
        wait_config = step.get("wait_for_event", {})
        event_type = wait_config.get("event_type")
        max_wait_hours = wait_config.get("max_wait_hours", 168)
        
        # Check if execution already exists
        execution = executions_collection.find_one({
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id
        })
        
        if not execution:
            # Create waiting execution record
            execution = {
                "_id": ObjectId(),
                "automation_rule_id": automation_rule_id,
                "automation_step_id": step_id,
                "subscriber_id": subscriber_id,
                "step_type": "wait_for_event",
                "step_order": step["step_order"],
                "status": "waiting",
                "waiting_for_event": event_type,
                "wait_started_at": datetime.utcnow(),
                "max_wait_until": datetime.utcnow() + timedelta(hours=max_wait_hours),
                "created_at": datetime.utcnow()
            }
            executions_collection.insert_one(execution)
        
        # Check if event has occurred
        email_events_collection = get_sync_email_events_collection()
        
        event_occurred = False
        if event_type == "opened_email":
            event = email_events_collection.find_one({
                "subscriber_id": subscriber_id,
                "event_type": "open",
                "automation_rule_id": automation_rule_id,
                "timestamp": {"$gte": execution["wait_started_at"]}
            })
            event_occurred = event is not None
        
        elif event_type == "clicked_link":
            event = email_events_collection.find_one({
                "subscriber_id": subscriber_id,
                "event_type": "click",
                "automation_rule_id": automation_rule_id,
                "timestamp": {"$gte": execution["wait_started_at"]}
            })
            event_occurred = event is not None
        
        # Check if max wait time exceeded
        timeout = datetime.utcnow() > execution.get("max_wait_until", datetime.utcnow())
        
        if event_occurred:
            # Event occurred - continue to next steps
            executions_collection.update_one(
                {"_id": execution["_id"]},
                {
                    "$set": {
                        "status": "completed",
                        "event_occurred_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            # Get next steps from step configuration
            next_step_order = step["step_order"] + 1
            next_step = steps_collection.find_one({
                "automation_rule_id": automation_rule_id,
                "step_order": next_step_order
            })
            
            if next_step:
                from tasks.automation_tasks import execute_automation_step
                execute_automation_step.delay(
                    automation_rule_id,
                    str(next_step["_id"]),
                    subscriber_id,
                    trigger_data or {}
                )
            
            return {"status": "event_occurred", "continue": True}
        
        elif timeout:
            # Timeout - handle based on configuration
            timeout_action = wait_config.get("timeout_action", "continue")
            
            executions_collection.update_one(
                {"_id": execution["_id"]},
                {
                    "$set": {
                        "status": "timeout",
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            if timeout_action == "continue":
                # Continue to next step
                next_step_order = step["step_order"] + 1
                next_step = steps_collection.find_one({
                    "automation_rule_id": automation_rule_id,
                    "step_order": next_step_order
                })
                
                if next_step:
                    from tasks.automation_tasks import execute_automation_step
                    execute_automation_step.delay(
                        automation_rule_id,
                        str(next_step["_id"]),
                        subscriber_id,
                        trigger_data or {}
                    )
            
            elif timeout_action == "alternate_path":
                # Execute alternate steps
                alternate_step_ids = wait_config.get("alternate_step_ids", [])
                for alt_step_id in alternate_step_ids:
                    from tasks.automation_tasks import execute_automation_step
                    execute_automation_step.delay(
                        automation_rule_id,
                        alt_step_id,
                        subscriber_id,
                        trigger_data or {}
                    )
            
            return {"status": "timeout", "action": timeout_action}
        
        else:
            # Still waiting - schedule next check in 1 hour
            wait_for_event_step.apply_async(
                args=[automation_rule_id, step_id, subscriber_id, trigger_data],
                countdown=3600  # Check again in 1 hour
            )
            
            return {"status": "waiting", "next_check": "1 hour"}
        
    except Exception as e:
        logger.error(f"Error in wait_for_event_step: {e}")
        return {"status": "error", "error": str(e)}


@shared_task(name="tasks.check_goal_achievement")
def check_goal_achievement(
    automation_rule_id: str,
    subscriber_id: str,
    goal_config: dict
):
    """
    Check if automation goal has been achieved
    Updates execution records and stops workflow if needed
    """
    try:
        executions_collection = get_sync_automation_executions_collection()
        email_events_collection = get_sync_email_events_collection()
        
        goal_type = goal_config.get("goal_type")
        tracking_window_days = goal_config.get("tracking_window_days", 30)
        
        start_date = datetime.utcnow() - timedelta(days=tracking_window_days)
        
        goal_achieved = False
        goal_value = 0
        
        if goal_type == "purchase":
            # Check for purchase events
            purchase_event = email_events_collection.find_one({
                "subscriber_id": subscriber_id,
                "event_type": "purchase",
                "automation_rule_id": automation_rule_id,
                "timestamp": {"$gte": start_date}
            })
            
            if purchase_event:
                goal_achieved = True
                goal_value = purchase_event.get("purchase_amount", 0)
        
        elif goal_type == "click":
            # Check for click on specific URL
            conversion_url = goal_config.get("conversion_url")
            click_event = email_events_collection.find_one({
                "subscriber_id": subscriber_id,
                "event_type": "click",
                "automation_rule_id": automation_rule_id,
                "url": conversion_url,
                "timestamp": {"$gte": start_date}
            })
            
            goal_achieved = click_event is not None
        
        elif goal_type == "custom":
            # Check for custom event
            custom_event = email_events_collection.find_one({
                "subscriber_id": subscriber_id,
                "event_type": "custom",
                "automation_rule_id": automation_rule_id,
                "custom_goal_type": goal_config.get("custom_event_name"),
                "timestamp": {"$gte": start_date}
            })
            
            goal_achieved = custom_event is not None
        
        if goal_achieved:
            # Update all executions for this subscriber
            result = executions_collection.update_many(
                {
                    "automation_rule_id": automation_rule_id,
                    "subscriber_id": subscriber_id
                },
                {
                    "$set": {
                        "goal_achieved": True,
                        "goal_achieved_at": datetime.utcnow(),
                        "goal_value": goal_value,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            # Check if we should exit automation
            rules_collection = get_sync_automation_rules_collection()
            rule = rules_collection.find_one({"_id": ObjectId(automation_rule_id)})
            
            if rule and rule.get("exit_on_goal_achieved"):
                # Cancel remaining scheduled steps
                from tasks.automation_tasks import cancel_automation_workflow
                cancel_automation_workflow.delay(automation_rule_id, subscriber_id)
            
            logger.info(f"Goal achieved for automation {automation_rule_id}, subscriber {subscriber_id}")
        
        return {
            "status": "success",
            "goal_achieved": goal_achieved,
            "goal_value": goal_value
        }
        
    except Exception as e:
        logger.error(f"Error checking goal achievement: {e}")
        return {"status": "error", "error": str(e)}


@shared_task(name="tasks.optimize_send_time")
def optimize_send_time(
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    trigger_data: dict = None
):
    """
    Calculate optimal send time for subscriber based on historical engagement
    """
    try:
        email_events_collection = get_sync_email_events_collection()
        subscribers_collection = get_sync_subscribers_collection()
        steps_collection = get_sync_automation_steps_collection()
        
        # Get subscriber timezone
        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not subscriber:
            return {"status": "subscriber_not_found"}
        
        subscriber_timezone = subscriber.get("timezone", "UTC")
        
        # Get step configuration
        step = steps_collection.find_one({"_id": ObjectId(step_id)})
        smart_send_config = step.get("smart_send_time", {})
        
        if not smart_send_config.get("enabled"):
            # Smart send not enabled, use default delay
            from tasks.automation_tasks import execute_automation_step
            execute_automation_step.delay(
                automation_rule_id,
                step_id,
                subscriber_id,
                trigger_data or {}
            )
            return {"status": "smart_send_disabled"}
        
        # Analyze historical engagement times
        optimize_for = smart_send_config.get("optimize_for", "opens")
        time_window_start = smart_send_config.get("time_window_start", 8)
        time_window_end = smart_send_config.get("time_window_end", 20)
        
        # Get historical email events for this subscriber
        historical_events = list(email_events_collection.find({
            "subscriber_id": subscriber_id,
            "event_type": "open" if optimize_for == "opens" else "click"
        }).sort("timestamp", -1).limit(20))
        
        if len(historical_events) >= 5:
            # Calculate hour distribution
            hour_engagement = {}
            for event in historical_events:
                event_time = event.get("timestamp")
                if event_time:
                    hour = event_time.hour
                    hour_engagement[hour] = hour_engagement.get(hour, 0) + 1
            
            # Find best hour within time window
            best_hour = time_window_start
            max_engagement = 0
            
            for hour in range(time_window_start, time_window_end + 1):
                engagement = hour_engagement.get(hour, 0)
                if engagement > max_engagement:
                    max_engagement = engagement
                    best_hour = hour
            
            optimal_send_time = best_hour
        else:
            # Not enough data, use fallback
            optimal_send_time = smart_send_config.get("fallback_time", 10)
        
        # Calculate delay to optimal send time
        now = datetime.utcnow()
        target_time = now.replace(hour=optimal_send_time, minute=0, second=0, microsecond=0)
        
        # If target time has passed today, schedule for tomorrow
        if target_time < now:
            target_time += timedelta(days=1)
        
        delay_seconds = int((target_time - now).total_seconds())
        
        # Schedule execution at optimal time
        from tasks.automation_tasks import execute_automation_step
        execute_automation_step.apply_async(
            args=[automation_rule_id, step_id, subscriber_id, trigger_data or {}],
            countdown=delay_seconds
        )
        
        logger.info(f"Optimized send time: {optimal_send_time}:00 for subscriber {subscriber_id}")
        
        return {
            "status": "success",
            "optimal_hour": optimal_send_time,
            "scheduled_for": target_time.isoformat(),
            "delay_seconds": delay_seconds
        }
        
    except Exception as e:
        logger.error(f"Error optimizing send time: {e}")
        return {"status": "error", "error": str(e)}


@shared_task(name="tasks.send_webhook")
def send_webhook(
    webhook_url: str,
    webhook_payload: dict,
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str
):
    """
    Send webhook notification as part of automation
    """
    try:
        executions_collection = get_sync_automation_executions_collection()
        subscribers_collection = get_sync_subscribers_collection()
        
        # Get subscriber data
        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        
        # Prepare webhook payload with subscriber data
        payload = {
            **webhook_payload,
            "subscriber": {
                "id": subscriber_id,
                "email": subscriber.get("email"),
                "standard_fields": subscriber.get("standard_fields", {}),
                "custom_fields": subscriber.get("custom_fields", {})
            },
            "automation_rule_id": automation_rule_id,
            "step_id": step_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Send webhook
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=10,
            headers={"Content-Type": "application/json"}
        )
        
        response.raise_for_status()
        
        # Record execution
        executions_collection.insert_one({
            "_id": ObjectId(),
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id,
            "step_type": "webhook",
            "status": "sent",
            "webhook_url": webhook_url,
            "webhook_response_status": response.status_code,
            "executed_at": datetime.utcnow(),
            "created_at": datetime.utcnow()
        })
        
        logger.info(f"Webhook sent successfully to {webhook_url}")
        
        return {
            "status": "success",
            "response_status": response.status_code,
            "response_body": response.text[:500]
        }
        
    except requests.RequestException as e:
        logger.error(f"Error sending webhook: {e}")
        
        # Record failed execution
        executions_collection.insert_one({
            "_id": ObjectId(),
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id,
            "step_type": "webhook",
            "status": "failed",
            "webhook_url": webhook_url,
            "error": str(e),
            "executed_at": datetime.utcnow(),
            "created_at": datetime.utcnow()
        })
        
        return {"status": "error", "error": str(e)}


@shared_task(name="tasks.update_subscriber_field")
def update_subscriber_field(
    subscriber_id: str,
    field_updates: dict,
    automation_rule_id: str,
    step_id: str
):
    """
    Update subscriber fields as part of automation
    """
    try:
        subscribers_collection = get_sync_subscribers_collection()
        executions_collection = get_sync_automation_executions_collection()
        
        # Update subscriber
        update_data = {}
        for field, value in field_updates.items():
            if field in ["first_name", "last_name"]:
                update_data[f"standard_fields.{field}"] = value
            else:
                update_data[f"custom_fields.{field}"] = value
        
        update_data["updated_at"] = datetime.utcnow()
        
        result = subscribers_collection.update_one(
            {"_id": ObjectId(subscriber_id)},
            {"$set": update_data}
        )
        
        # Record execution
        executions_collection.insert_one({
            "_id": ObjectId(),
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id,
            "step_type": "update_field",
            "status": "completed",
            "field_updates": field_updates,
            "executed_at": datetime.utcnow(),
            "created_at": datetime.utcnow()
        })
        
        logger.info(f"Updated fields for subscriber {subscriber_id}")
        
        return {
            "status": "success",
            "updated_fields": list(field_updates.keys()),
            "matched_count": result.matched_count,
            "modified_count": result.modified_count
        }
        
    except Exception as e:
        logger.error(f"Error updating subscriber field: {e}")
        return {"status": "error", "error": str(e)}


@shared_task(name="tasks.analyze_optimal_send_times")
def analyze_optimal_send_times(automation_rule_id: str):
    """
    Analyze historical performance and determine optimal send times
    """
    try:
        executions_collection = get_sync_automation_executions_collection()
        
        # Get all executions with engagement data
        pipeline = [
            {
                "$match": {
                    "automation_rule_id": automation_rule_id,
                    "executed_at": {"$exists": True}
                }
            },
            {
                "$addFields": {
                    "hour_of_day": {"$hour": "$executed_at"}
                }
            },
            {
                "$group": {
                    "_id": "$hour_of_day",
                    "total_sent": {"$sum": 1},
                    "total_opened": {
                        "$sum": {"$cond": [{"$ifNull": ["$opened_at", False]}, 1, 0]}
                    },
                    "total_clicked": {
                        "$sum": {"$cond": [{"$ifNull": ["$clicked_at", False]}, 1, 0]}
                    }
                }
            },
            {
                "$project": {
                    "hour": "$_id",
                    "total_sent": 1,
                    "open_rate": {
                        "$multiply": [
                            {"$divide": ["$total_opened", "$total_sent"]},
                            100
                        ]
                    },
                    "click_rate": {
                        "$multiply": [
                            {"$divide": ["$total_clicked", "$total_sent"]},
                            100
                        ]
                    }
                }
            },
            {"$sort": {"open_rate": -1}}
        ]
        
        results = list(executions_collection.aggregate(pipeline))
        
        # Find optimal windows
        optimal_hours = []
        for result in results[:3]:  # Top 3 hours
            optimal_hours.append({
                "hour": result["hour"],
                "open_rate": round(result["open_rate"], 2),
                "click_rate": round(result["click_rate"], 2),
                "total_sent": result["total_sent"]
            })
        
        # Store recommendations
        rules_collection = get_sync_automation_rules_collection()
        rules_collection.update_one(
            {"_id": ObjectId(automation_rule_id)},
            {
                "$set": {
                    "send_time_analysis": {
                        "analyzed_at": datetime.utcnow(),
                        "optimal_hours": optimal_hours,
                        "recommendation": f"Best send time: {optimal_hours[0]['hour']}:00" if optimal_hours else "Insufficient data"
                    },
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        logger.info(f"Send time analysis completed for automation {automation_rule_id}")
        
        return {
            "status": "success",
            "optimal_hours": optimal_hours
        }
        
    except Exception as e:
        logger.error(f"Error analyzing optimal send times: {e}")
        return {"status": "error", "error": str(e)}