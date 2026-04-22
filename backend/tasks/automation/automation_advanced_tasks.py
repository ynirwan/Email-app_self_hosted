# backend/tasks/automation/automation_advanced_tasks.py
"""
Celery tasks for advanced automation features:
  - execute_conditional_step   — evaluate condition, route to true/false path
  - execute_ab_test_step       — assign variant, send appropriate email
  - wait_for_event_step        — poll for event, handle timeout
  - check_goal_achievement     — check if automation goal met, cancel if exit_on_goal
  - optimize_send_time         — smart-send-time based on historical engagement
  - send_webhook               — send webhook as part of automation
  - update_subscriber_field    — update subscriber fields as part of automation
  - analyze_optimal_send_times — per-rule send-time analysis for beat

Fix log:
  2026-04-22  Add missing get_sync_templates_collection import (NameError on A/B step).
  2026-04-22  execute_ab_test_step: replace dead send_single_campaign_email import
              with send_automation_email.delay() — the correct automation send task.
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
    get_sync_templates_collection,  # ← was missing; caused NameError in execute_ab_test_step
    get_sync_email_events_collection,
)

logger = logging.getLogger(__name__)


@shared_task(name="tasks.execute_conditional_step")
def execute_conditional_step(
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    trigger_data: dict = None,
):
    """
    Execute a conditional branching step.
    Evaluates condition and routes to appropriate path.
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
        check_time = datetime.utcnow() - timedelta(hours=wait_hours)  # noqa: F841

        condition_met = False

        if condition_type == "opened_email":
            previous_execution = executions_collection.find_one(
                {
                    "automation_rule_id": automation_rule_id,
                    "subscriber_id": subscriber_id,
                    "step_order": step["step_order"] - 1,
                }
            )
            if previous_execution:
                condition_met = previous_execution.get("opened_at") is not None

        elif condition_type == "clicked_link":
            previous_execution = executions_collection.find_one(
                {
                    "automation_rule_id": automation_rule_id,
                    "subscriber_id": subscriber_id,
                    "step_order": step["step_order"] - 1,
                }
            )
            if previous_execution:
                condition_met = previous_execution.get("clicked_at") is not None

        elif condition_type == "segment_match":
            subscribers_collection = get_sync_subscribers_collection()
            subscriber = subscribers_collection.find_one(
                {"_id": ObjectId(subscriber_id)}
            )
            if not subscriber:
                logger.error("Subscriber not found: %s", subscriber_id)
                condition_met = False
            else:
                required_segments = conditional_config.get("condition_value", [])
                subscriber_segments = subscriber.get("segments", [])
                if isinstance(required_segments, list):
                    condition_met = any(
                        seg in subscriber_segments for seg in required_segments
                    )
                else:
                    condition_met = required_segments in subscriber_segments

                logger.info(
                    "Segment match check: subscriber_segments=%s required=%s met=%s",
                    subscriber_segments,
                    required_segments,
                    condition_met,
                )

        elif condition_type == "field_equals":
            subscribers_collection = get_sync_subscribers_collection()
            subscriber = subscribers_collection.find_one(
                {"_id": ObjectId(subscriber_id)}
            )
            if not subscriber:
                logger.error("Subscriber not found: %s", subscriber_id)
                condition_met = False
            else:
                field_name = conditional_config.get("field_name")
                field_config = conditional_config.get("field_config", {})
                field_tier = field_config.get("field_tier", "custom")
                expected_value = conditional_config.get("condition_value")

                if not field_name or expected_value is None:
                    logger.error("Invalid field_equals config: %s", field_config)
                    condition_met = False
                else:
                    if field_tier == "standard":
                        actual_value = subscriber.get("standard_fields", {}).get(
                            field_name
                        )
                    else:
                        actual_value = subscriber.get("custom_fields", {}).get(
                            field_name
                        )

                    if isinstance(actual_value, str) and isinstance(
                        expected_value, str
                    ):
                        condition_met = actual_value.lower() == expected_value.lower()
                    else:
                        condition_met = actual_value == expected_value

                    logger.info(
                        "Field equals check: %s=%s expected=%s met=%s",
                        field_name,
                        actual_value,
                        expected_value,
                        condition_met,
                    )

        elif condition_type == "field_contains":
            subscribers_collection = get_sync_subscribers_collection()
            subscriber = subscribers_collection.find_one(
                {"_id": ObjectId(subscriber_id)}
            )
            if not subscriber:
                logger.error("Subscriber not found: %s", subscriber_id)
                condition_met = False
            else:
                field_config = conditional_config.get("field_config", {})
                field_name = field_config.get("field_name")
                search_text = field_config.get("search_text", "")
                field_tier = field_config.get("field_tier", "custom")

                if not field_name or not search_text:
                    logger.error("Invalid field_contains config: %s", field_config)
                    condition_met = False
                else:
                    if field_tier == "standard":
                        actual_value = subscriber.get("standard_fields", {}).get(
                            field_name, ""
                        )
                    else:
                        actual_value = subscriber.get("custom_fields", {}).get(
                            field_name, ""
                        )

                    if isinstance(actual_value, str):
                        condition_met = search_text.lower() in actual_value.lower()
                    else:
                        condition_met = search_text.lower() in str(actual_value).lower()

                    logger.info(
                        "Field contains check: %s contains '%s' actual='%s' met=%s",
                        field_name,
                        search_text,
                        actual_value,
                        condition_met,
                    )

        # Record condition result
        executions_collection.insert_one(
            {
                "_id": ObjectId(),
                "automation_rule_id": automation_rule_id,
                "automation_step_id": step_id,
                "subscriber_id": subscriber_id,
                "step_type": "condition",
                "step_order": step["step_order"],
                "condition_result": condition_met,
                "path_taken": "true" if condition_met else "false",
                "executed_at": datetime.utcnow(),
                "created_at": datetime.utcnow(),
            }
        )

        # Schedule next steps based on path
        next_step_ids = (
            conditional_config.get("true_path_step_ids", [])
            if condition_met
            else conditional_config.get("false_path_step_ids", [])
        )

        for next_step_id in next_step_ids:
            from tasks.automation.automation_tasks import execute_automation_step

            execute_automation_step.delay(
                automation_rule_id,
                next_step_id,
                subscriber_id,
                trigger_data or {},
            )

        return {
            "status": "success",
            "condition_met": condition_met,
            "next_steps_scheduled": len(next_step_ids),
        }

    except Exception as e:
        logger.error("Error executing conditional step: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}


@shared_task(name="tasks.execute_ab_test_step")
def execute_ab_test_step(
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    trigger_data: dict = None,
):
    """
    Execute an A/B test step.
    Randomly assigns variant and dispatches the automation email task.

    Fix: replaced dead import of send_single_campaign_email with
    send_automation_email.delay() which is the correct send path for automation.
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

        # Randomly assign variant by percentage
        variant_a_pct = ab_config.get("variant_a_percentage", 50)
        random_value = random.randint(1, 100)

        if random_value <= variant_a_pct:
            variant = "A"
            template_id = ab_config["variant_a_template_id"]
        else:
            variant = "B"
            template_id = ab_config["variant_b_template_id"]

        # Verify subscriber exists (get_sync_templates_collection now properly imported)
        subscribers_collection = get_sync_subscribers_collection()
        templates_collection = get_sync_templates_collection()

        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not subscriber:
            return {"status": "subscriber_not_found"}

        template = templates_collection.find_one({"_id": ObjectId(template_id)})
        if not template:
            return {"status": "template_not_found"}

        # Resolve subject: per-variant override takes precedence over template subject
        variant_key = f"variant_{variant.lower()}_subject"
        ab_subject = ab_config.get(variant_key)
        final_subject = ab_subject if ab_subject else template.get("subject", "")

        # Build email_config from the parent automation rule
        from database import get_sync_automation_rules_collection

        rule = get_sync_automation_rules_collection().find_one(
            {"_id": ObjectId(automation_rule_id)}
        )
        if not rule:
            return {"status": "rule_not_found"}

        email_config_data = rule.get("email_config", {})
        email_config = {
            "from_email": email_config_data.get("sender_email", ""),
            "from_name": email_config_data.get("sender_name", ""),
            "reply_to": email_config_data.get("reply_to"),
            "subject": final_subject,
        }

        # Record execution with variant before dispatching send
        execution_doc = {
            "_id": ObjectId(),
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id,
            "step_type": "ab_split",
            "step_order": step["step_order"],
            "ab_variant": variant,
            "template_id": template_id,
            "status": "dispatched",
            "executed_at": datetime.utcnow(),
            "created_at": datetime.utcnow(),
        }
        executions_collection.insert_one(execution_doc)

        # Dispatch via the proper automation send task (not campaign send)
        from tasks.automation.automation_email_tasks import send_automation_email

        result = send_automation_email.delay(
            subscriber_id=subscriber_id,
            template_id=template_id,
            automation_rule_id=automation_rule_id,
            step_id=step_id,
            workflow_instance_id=str(
                execution_doc["_id"]
            ),  # use execution doc as instance ref
            email_config=email_config,
            field_map=step.get("field_map", {}),
            fallback_values=step.get("fallback_values", {}),
        )

        # Update execution with the dispatched task ID
        executions_collection.update_one(
            {"_id": execution_doc["_id"]},
            {"$set": {"email_task_id": result.id, "status": "sent"}},
        )

        logger.info(
            "A/B test email dispatched: variant %s for subscriber %s task %s",
            variant,
            subscriber_id,
            result.id,
        )

        return {
            "status": "success",
            "variant": variant,
            "template_id": template_id,
            "email_task_id": result.id,
        }

    except Exception as e:
        logger.error("Error executing A/B test step: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}


@shared_task(name="tasks.wait_for_event_step")
def wait_for_event_step(
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    trigger_data: dict = None,
):
    """
    Wait for a specific event before continuing automation.
    Schedules a periodic check until event occurs or max wait exceeded.
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

        # Find or create the waiting execution record
        execution = executions_collection.find_one(
            {
                "automation_rule_id": automation_rule_id,
                "automation_step_id": step_id,
                "subscriber_id": subscriber_id,
            }
        )

        if not execution:
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
                "created_at": datetime.utcnow(),
            }
            executions_collection.insert_one(execution)

        email_events_collection = get_sync_email_events_collection()

        event_occurred = False
        if event_type == "opened_email":
            event = email_events_collection.find_one(
                {
                    "subscriber_id": subscriber_id,
                    "event_type": "open",
                    "automation_rule_id": automation_rule_id,
                    "timestamp": {"$gte": execution["wait_started_at"]},
                }
            )
            event_occurred = event is not None

        elif event_type == "clicked_link":
            event = email_events_collection.find_one(
                {
                    "subscriber_id": subscriber_id,
                    "event_type": "click",
                    "automation_rule_id": automation_rule_id,
                    "timestamp": {"$gte": execution["wait_started_at"]},
                }
            )
            event_occurred = event is not None

        timeout = datetime.utcnow() > execution.get("max_wait_until", datetime.utcnow())

        if event_occurred:
            executions_collection.update_one(
                {"_id": execution["_id"]},
                {
                    "$set": {
                        "status": "completed",
                        "event_occurred_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                    }
                },
            )

            next_step_order = step["step_order"] + 1
            next_step = steps_collection.find_one(
                {
                    "automation_rule_id": automation_rule_id,
                    "step_order": next_step_order,
                }
            )

            if next_step:
                from tasks.automation.automation_tasks import execute_automation_step

                execute_automation_step.delay(
                    automation_rule_id,
                    str(next_step["_id"]),
                    subscriber_id,
                    trigger_data or {},
                )

            return {"status": "event_occurred", "continue": True}

        elif timeout:
            timeout_action = wait_config.get("timeout_action", "continue")

            executions_collection.update_one(
                {"_id": execution["_id"]},
                {"$set": {"status": "timeout", "updated_at": datetime.utcnow()}},
            )

            if timeout_action == "continue":
                next_step_order = step["step_order"] + 1
                next_step = steps_collection.find_one(
                    {
                        "automation_rule_id": automation_rule_id,
                        "step_order": next_step_order,
                    }
                )
                if next_step:
                    from tasks.automation.automation_tasks import (
                        execute_automation_step,
                    )

                    execute_automation_step.delay(
                        automation_rule_id,
                        str(next_step["_id"]),
                        subscriber_id,
                        trigger_data or {},
                    )

            elif timeout_action == "alternate_path":
                alternate_step_ids = wait_config.get("alternate_step_ids", [])
                for alt_step_id in alternate_step_ids:
                    from tasks.automation.automation_tasks import (
                        execute_automation_step,
                    )

                    execute_automation_step.delay(
                        automation_rule_id,
                        alt_step_id,
                        subscriber_id,
                        trigger_data or {},
                    )

            return {"status": "timeout", "action": timeout_action}

        else:
            # Still waiting — reschedule check in 1 hour
            wait_for_event_step.apply_async(
                args=[automation_rule_id, step_id, subscriber_id, trigger_data],
                countdown=3600,
            )
            return {"status": "waiting", "next_check": "1 hour"}

    except Exception as e:
        logger.error("Error in wait_for_event_step: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}


@shared_task(name="tasks.check_goal_achievement")
def check_goal_achievement(
    automation_rule_id: str,
    subscriber_id: str,
    goal_config: dict,
):
    """
    Check if the automation goal has been achieved.
    Updates execution records and cancels workflow if exit_on_goal_achieved is set.
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
            event = email_events_collection.find_one(
                {
                    "subscriber_id": subscriber_id,
                    "event_type": "purchase",
                    "automation_rule_id": automation_rule_id,
                    "timestamp": {"$gte": start_date},
                }
            )
            if event:
                goal_achieved = True
                goal_value = event.get("purchase_amount", 0)

        elif goal_type == "click":
            conversion_url = goal_config.get("conversion_url")
            event = email_events_collection.find_one(
                {
                    "subscriber_id": subscriber_id,
                    "event_type": "click",
                    "automation_rule_id": automation_rule_id,
                    "url": conversion_url,
                    "timestamp": {"$gte": start_date},
                }
            )
            goal_achieved = event is not None

        elif goal_type == "custom":
            event = email_events_collection.find_one(
                {
                    "subscriber_id": subscriber_id,
                    "event_type": "custom",
                    "automation_rule_id": automation_rule_id,
                    "custom_goal_type": goal_config.get("custom_event_name"),
                    "timestamp": {"$gte": start_date},
                }
            )
            goal_achieved = event is not None

        if goal_achieved:
            executions_collection.update_many(
                {
                    "automation_rule_id": automation_rule_id,
                    "subscriber_id": subscriber_id,
                },
                {
                    "$set": {
                        "goal_achieved": True,
                        "goal_achieved_at": datetime.utcnow(),
                        "goal_value": goal_value,
                        "updated_at": datetime.utcnow(),
                    }
                },
            )

            rules_collection = get_sync_automation_rules_collection()
            rule = rules_collection.find_one({"_id": ObjectId(automation_rule_id)})

            if rule and rule.get("exit_on_goal_achieved"):
                from tasks.automation.automation_tasks import cancel_automation_workflow

                cancel_automation_workflow.delay(automation_rule_id, subscriber_id)

            logger.info(
                "Goal achieved for automation %s subscriber %s",
                automation_rule_id,
                subscriber_id,
            )

        return {
            "status": "success",
            "goal_achieved": goal_achieved,
            "goal_value": goal_value,
        }

    except Exception as e:
        logger.error("Error checking goal achievement: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}


@shared_task(name="tasks.optimize_send_time")
def optimize_send_time(
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    trigger_data: dict = None,
):
    """
    Calculate optimal send time for a subscriber based on historical engagement
    and schedule execute_automation_step at that time.
    """
    try:
        email_events_collection = get_sync_email_events_collection()
        subscribers_collection = get_sync_subscribers_collection()
        steps_collection = get_sync_automation_steps_collection()

        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not subscriber:
            return {"status": "subscriber_not_found"}

        step = steps_collection.find_one({"_id": ObjectId(step_id)})
        if not step:
            return {"status": "step_not_found"}

        smart_send_config = step.get("smart_send_time", {})

        if not smart_send_config.get("enabled"):
            from tasks.automation.automation_tasks import execute_automation_step

            execute_automation_step.delay(
                automation_rule_id, step_id, subscriber_id, trigger_data or {}
            )
            return {"status": "smart_send_disabled"}

        optimize_for = smart_send_config.get("optimize_for", "opens")
        time_window_start = smart_send_config.get("time_window_start", 8)
        time_window_end = smart_send_config.get("time_window_end", 20)

        historical_events = list(
            email_events_collection.find(
                {
                    "subscriber_id": subscriber_id,
                    "event_type": "open" if optimize_for == "opens" else "click",
                }
            )
            .sort("timestamp", -1)
            .limit(20)
        )

        if len(historical_events) >= 5:
            hour_engagement = {}
            for event in historical_events:
                event_time = event.get("timestamp")
                if event_time:
                    hour = event_time.hour
                    hour_engagement[hour] = hour_engagement.get(hour, 0) + 1

            best_hour = time_window_start
            max_engagement = 0
            for hour in range(time_window_start, time_window_end + 1):
                engagement = hour_engagement.get(hour, 0)
                if engagement > max_engagement:
                    max_engagement = engagement
                    best_hour = hour

            optimal_send_hour = best_hour
        else:
            optimal_send_hour = smart_send_config.get("fallback_time", 10)

        now = datetime.utcnow()
        target_time = now.replace(
            hour=optimal_send_hour, minute=0, second=0, microsecond=0
        )

        if target_time <= now:
            target_time += timedelta(days=1)

        delay_seconds = int((target_time - now).total_seconds())

        from tasks.automation.automation_tasks import execute_automation_step

        execute_automation_step.apply_async(
            args=[automation_rule_id, step_id, subscriber_id, trigger_data or {}],
            countdown=delay_seconds,
        )

        logger.info(
            "Optimized send time: %d:00 for subscriber %s (delay %ds)",
            optimal_send_hour,
            subscriber_id,
            delay_seconds,
        )

        return {
            "status": "success",
            "optimal_hour": optimal_send_hour,
            "scheduled_for": target_time.isoformat(),
            "delay_seconds": delay_seconds,
        }

    except Exception as e:
        logger.error("Error optimizing send time: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}


@shared_task(name="tasks.send_webhook")
def send_webhook(
    webhook_url: str,
    webhook_payload: dict,
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
):
    """Send a webhook notification as part of an automation step."""
    try:
        executions_collection = get_sync_automation_executions_collection()
        subscribers_collection = get_sync_subscribers_collection()

        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not subscriber:
            return {"status": "subscriber_not_found"}

        payload = {
            **webhook_payload,
            "subscriber": {
                "id": subscriber_id,
                "email": subscriber.get("email"),
                "standard_fields": subscriber.get("standard_fields", {}),
                "custom_fields": subscriber.get("custom_fields", {}),
            },
            "automation_rule_id": automation_rule_id,
            "step_id": step_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

        response = requests.post(
            webhook_url,
            json=payload,
            timeout=10,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()

        executions_collection.insert_one(
            {
                "_id": ObjectId(),
                "automation_rule_id": automation_rule_id,
                "automation_step_id": step_id,
                "subscriber_id": subscriber_id,
                "step_type": "webhook",
                "status": "sent",
                "webhook_url": webhook_url,
                "webhook_response_status": response.status_code,
                "executed_at": datetime.utcnow(),
                "created_at": datetime.utcnow(),
            }
        )

        logger.info("Webhook sent to %s (status %d)", webhook_url, response.status_code)

        return {
            "status": "success",
            "response_status": response.status_code,
            "response_body": response.text[:500],
        }

    except requests.RequestException as e:
        logger.error("Error sending webhook to %s: %s", webhook_url, e)

        get_sync_automation_executions_collection().insert_one(
            {
                "_id": ObjectId(),
                "automation_rule_id": automation_rule_id,
                "automation_step_id": step_id,
                "subscriber_id": subscriber_id,
                "step_type": "webhook",
                "status": "failed",
                "webhook_url": webhook_url,
                "error": str(e),
                "executed_at": datetime.utcnow(),
                "created_at": datetime.utcnow(),
            }
        )

        return {"status": "error", "error": str(e)}


@shared_task(name="tasks.update_subscriber_field")
def update_subscriber_field(
    subscriber_id: str,
    field_updates: dict,
    automation_rule_id: str,
    step_id: str,
):
    """Update subscriber fields as part of an automation step."""
    try:
        subscribers_collection = get_sync_subscribers_collection()
        executions_collection = get_sync_automation_executions_collection()

        update_data = {}
        for field, value in field_updates.items():
            if field in ("first_name", "last_name"):
                update_data[f"standard_fields.{field}"] = value
            else:
                update_data[f"custom_fields.{field}"] = value

        update_data["updated_at"] = datetime.utcnow()

        result = subscribers_collection.update_one(
            {"_id": ObjectId(subscriber_id)},
            {"$set": update_data},
        )

        executions_collection.insert_one(
            {
                "_id": ObjectId(),
                "automation_rule_id": automation_rule_id,
                "automation_step_id": step_id,
                "subscriber_id": subscriber_id,
                "step_type": "update_field",
                "status": "completed",
                "field_updates": field_updates,
                "executed_at": datetime.utcnow(),
                "created_at": datetime.utcnow(),
            }
        )

        logger.info("Updated fields for subscriber %s", subscriber_id)

        return {
            "status": "success",
            "updated_fields": list(field_updates.keys()),
            "matched_count": result.matched_count,
            "modified_count": result.modified_count,
        }

    except Exception as e:
        logger.error("Error updating subscriber field: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}


@shared_task(name="tasks.analyze_optimal_send_times")
def analyze_optimal_send_times(automation_rule_id: str):
    """
    Analyse historical execution data to determine optimal send hours.
    Results are stored on the automation rule document.
    """
    try:
        executions_collection = get_sync_automation_executions_collection()

        pipeline = [
            {
                "$match": {
                    "automation_rule_id": automation_rule_id,
                    "executed_at": {"$exists": True},
                }
            },
            {"$addFields": {"hour_of_day": {"$hour": "$executed_at"}}},
            {
                "$group": {
                    "_id": "$hour_of_day",
                    "total_sent": {"$sum": 1},
                    "total_opened": {
                        "$sum": {"$cond": [{"$ifNull": ["$opened_at", False]}, 1, 0]}
                    },
                    "total_clicked": {
                        "$sum": {"$cond": [{"$ifNull": ["$clicked_at", False]}, 1, 0]}
                    },
                }
            },
            {
                "$project": {
                    "hour": "$_id",
                    "total_sent": 1,
                    "open_rate": {
                        "$multiply": [
                            {
                                "$cond": [
                                    {"$gt": ["$total_sent", 0]},
                                    {"$divide": ["$total_opened", "$total_sent"]},
                                    0,
                                ]
                            },
                            100,
                        ]
                    },
                    "click_rate": {
                        "$multiply": [
                            {
                                "$cond": [
                                    {"$gt": ["$total_sent", 0]},
                                    {"$divide": ["$total_clicked", "$total_sent"]},
                                    0,
                                ]
                            },
                            100,
                        ]
                    },
                }
            },
            {"$sort": {"open_rate": -1}},
        ]

        results = list(executions_collection.aggregate(pipeline))

        optimal_hours = [
            {
                "hour": r["hour"],
                "open_rate": round(r["open_rate"], 2),
                "click_rate": round(r["click_rate"], 2),
                "total_sent": r["total_sent"],
            }
            for r in results[:3]
        ]

        rules_collection = get_sync_automation_rules_collection()
        rules_collection.update_one(
            {"_id": ObjectId(automation_rule_id)},
            {
                "$set": {
                    "send_time_analysis": {
                        "analyzed_at": datetime.utcnow(),
                        "optimal_hours": optimal_hours,
                        "recommendation": (
                            f"Best send time: {optimal_hours[0]['hour']}:00"
                            if optimal_hours
                            else "Insufficient data"
                        ),
                    },
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        logger.info(
            "Send time analysis completed for automation %s", automation_rule_id
        )

        return {"status": "success", "optimal_hours": optimal_hours}

    except Exception as e:
        logger.error("Error analyzing optimal send times: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
