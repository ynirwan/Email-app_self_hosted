# backend/tasks/automation/automation_advanced_tasks.py
"""
Celery tasks for advanced automation step types.

These tasks are dispatched FROM execute_automation_step in
automation_tasks.py — they should not be invoked directly from the
trigger pipeline.

Tasks in this module:
  execute_conditional_step  — evaluate condition, route to true/false branch
  execute_ab_test_step      — randomly assign variant, dispatch send
  wait_for_event_step       — poll for event, handle timeout
  send_webhook_step         — POST to webhook URL with HMAC signing & retry
  update_field_step         — update subscriber custom/standard fields
  goal_check_step           — evaluate goal, optionally cancel workflow
  optimize_send_time        — compute ideal hour, reschedule email step
  check_goal_achievement    — manual/scheduled goal eval (legacy entry point)
  analyze_optimal_send_times — beat task: per-rule send-time analysis

Conventions:
  - Every step task receives workflow_instance_id; uses it to mark completion
  - Every step task uses the chained-step helper (schedule_specific_next_steps
    or _schedule_next_step) to advance the workflow
  - Every step task records a final execution document for analytics
  - Webhook signing uses HMAC-SHA256 with rule.webhook_secret (or workspace
    settings); requests retry on 5xx and timeouts only

Fix log:
  2026-04-22  Added missing get_sync_templates_collection import
              (previously caused NameError in execute_ab_test_step).
  2026-04-22  Replaced dead send_single_campaign_email reference with
              send_automation_email.delay().
  2026-04-28  Full rewrite for the chained-scheduling architecture.
              Conditional steps now correctly enforce wait_time_hours.
              segment_match now evaluates segment criteria dynamically.
              All step types now increment workflow.completed_steps and
              terminate the workflow correctly when no next step exists.
              Webhook step gets HMAC signing and proper retry policy.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import requests
from bson import ObjectId
from celery import shared_task

from database import (
    get_sync_automation_executions_collection,
    get_sync_automation_rules_collection,
    get_sync_automation_steps_collection,
    get_sync_email_events_collection,
    get_sync_segments_collection,
    get_sync_subscribers_collection,
    get_sync_templates_collection,
    get_sync_workflow_instances_collection,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CONDITIONAL BRANCHING
# =============================================================================

@shared_task(name="tasks.execute_conditional_step", bind=True, max_retries=3)
def execute_conditional_step(
    self,
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    workflow_instance_id: str,
    trigger_data: Optional[dict] = None,
):
    """
    Execute a conditional branching step.

    Two-phase execution if wait_time_hours > 0:
      Phase 1 (first call): record wait_started_at, reschedule self with
                            countdown = wait_time_hours * 3600
      Phase 2 (after wait): evaluate condition, route to true/false branch

    If wait_time_hours == 0, evaluate immediately on the first call.
    """
    try:
        steps_collection = get_sync_automation_steps_collection()
        executions_collection = get_sync_automation_executions_collection()
        rules_collection = get_sync_automation_rules_collection()

        step = steps_collection.find_one({"_id": ObjectId(step_id)})
        if not step or step.get("step_type") != "condition":
            logger.error(f"Invalid conditional step: {step_id}")
            _record_step_failure(
                automation_rule_id, step_id, subscriber_id, workflow_instance_id,
                "invalid_conditional_step",
            )
            return {"status": "invalid_step"}

        rule = rules_collection.find_one({"_id": ObjectId(automation_rule_id)})
        if not rule:
            logger.error(f"Rule not found: {automation_rule_id}")
            return {"status": "rule_not_found"}

        # Cancellation check
        if _workflow_cancelled(workflow_instance_id):
            return {"status": "workflow_cancelled"}

        conditional_config = step.get("conditional_branch") or {}
        condition_type = conditional_config.get("condition_type")
        wait_hours = int(conditional_config.get("wait_time_hours", 0) or 0)

        # ── PHASE 1: Schedule deferred evaluation if wait > 0 ──────────────
        if wait_hours > 0:
            existing_wait = executions_collection.find_one({
                "automation_rule_id": automation_rule_id,
                "automation_step_id": step_id,
                "subscriber_id": subscriber_id,
                "workflow_instance_id": workflow_instance_id,
                "status": "awaiting_evaluation",
            })

            if not existing_wait:
                # First call — record wait and reschedule
                executions_collection.insert_one({
                    "_id": ObjectId(),
                    "automation_rule_id": automation_rule_id,
                    "automation_step_id": step_id,
                    "subscriber_id": subscriber_id,
                    "workflow_instance_id": workflow_instance_id,
                    "step_type": "condition",
                    "step_order": step.get("step_order"),
                    "status": "awaiting_evaluation",
                    "wait_started_at": datetime.utcnow(),
                    "wait_until": datetime.utcnow() + timedelta(hours=wait_hours),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                })

                execute_conditional_step.apply_async(
                    args=[],
                    kwargs={
                        "automation_rule_id": automation_rule_id,
                        "step_id": step_id,
                        "subscriber_id": subscriber_id,
                        "workflow_instance_id": workflow_instance_id,
                        "trigger_data": trigger_data or {},
                    },
                    countdown=wait_hours * 3600,
                )

                logger.info(
                    f"Conditional step {step_id} deferred for {wait_hours}h "
                    f"(workflow {workflow_instance_id})"
                )
                return {"status": "deferred", "wait_hours": wait_hours}

            # Mark the awaiting record as evaluating
            executions_collection.update_one(
                {"_id": existing_wait["_id"]},
                {"$set": {"status": "evaluating", "updated_at": datetime.utcnow()}},
            )

        # ── PHASE 2: Evaluate condition ────────────────────────────────────
        condition_met = _evaluate_condition(
            condition_type=condition_type,
            conditional_config=conditional_config,
            automation_rule_id=automation_rule_id,
            subscriber_id=subscriber_id,
        )

        # Record condition outcome
        executions_collection.insert_one({
            "_id": ObjectId(),
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id,
            "workflow_instance_id": workflow_instance_id,
            "step_type": "condition",
            "step_order": step.get("step_order"),
            "condition_type": condition_type,
            "condition_result": condition_met,
            "path_taken": "true" if condition_met else "false",
            "status": "completed",
            "executed_at": datetime.utcnow(),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })

        # Increment workflow completion counter
        from tasks.automation.automation_tasks import (
            mark_step_completed,
            mark_workflow_completed,
            schedule_specific_next_steps,
        )
        mark_step_completed(workflow_instance_id, was_email=False)

        # Route to selected branch
        next_step_ids = (
            conditional_config.get("true_path_step_ids", [])
            if condition_met
            else conditional_config.get("false_path_step_ids", [])
        )

        scheduled = schedule_specific_next_steps(
            rule=rule,
            automation_rule_id=automation_rule_id,
            subscriber_id=subscriber_id,
            workflow_instance_id=workflow_instance_id,
            trigger_data=trigger_data or {},
            next_step_ids=next_step_ids,
        )

        if scheduled == 0:
            # Branch is empty — workflow ends here
            mark_workflow_completed(workflow_instance_id)

        logger.info(
            f"Conditional step {step_id}: condition={condition_met}, "
            f"branch={'true' if condition_met else 'false'}, "
            f"next_steps_scheduled={scheduled}"
        )

        return {
            "status": "success",
            "condition_met": condition_met,
            "next_steps_scheduled": scheduled,
        }

    except Exception as exc:
        logger.error(f"Error in execute_conditional_step: {exc}", exc_info=True)
        raise self.retry(exc=exc)


def _evaluate_condition(
    *,
    condition_type: str,
    conditional_config: dict,
    automation_rule_id: str,
    subscriber_id: str,
) -> bool:
    """Evaluate a condition for the current subscriber. Returns True/False."""
    executions_collection = get_sync_automation_executions_collection()
    email_events_collection = get_sync_email_events_collection()
    subscribers_collection = get_sync_subscribers_collection()

    # ── opened_email / clicked_link / not_opened ─────────────────────────
    if condition_type in ("opened_email", "clicked_link", "not_opened"):
        # We look at the most recent email-step execution for this rule+subscriber
        previous_execution = executions_collection.find_one(
            {
                "automation_rule_id": automation_rule_id,
                "subscriber_id": subscriber_id,
                "step_type": {"$in": ["email", "ab_split"]},
                "status": {"$in": ["sent", "completed"]},
            },
            sort=[("executed_at", -1)],
        )
        if not previous_execution:
            return False

        if condition_type == "opened_email":
            return previous_execution.get("opened_at") is not None
        if condition_type == "clicked_link":
            return previous_execution.get("clicked_at") is not None
        if condition_type == "not_opened":
            return previous_execution.get("opened_at") is None

    # ── segment_match (DYNAMIC EVALUATION) ───────────────────────────────
    if condition_type == "segment_match":
        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not subscriber:
            return False

        required = conditional_config.get("condition_value")
        if isinstance(required, str):
            required = [required]
        elif not isinstance(required, list):
            required = []

        if not required:
            return False

        from tasks.automation.automation_tasks import subscriber_matches_segment_criteria
        segments_collection = get_sync_segments_collection()

        for seg_id in required:
            try:
                segment = segments_collection.find_one({"_id": ObjectId(str(seg_id))})
                if not segment:
                    continue
                if subscriber_matches_segment_criteria(subscriber, segment.get("criteria", {})):
                    return True
            except Exception as e:
                logger.warning(f"Segment lookup failed for {seg_id}: {e}")

        return False

    # ── field_equals / field_contains / field exists ─────────────────────
    if condition_type in ("field_equals", "field_contains", "field_not_equals", "field_exists", "field_not_exists"):
        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not subscriber:
            return False

        field_name = conditional_config.get("field_name")
        if not field_name:
            logger.warning(f"field condition without field_name: {conditional_config}")
            return False

        field_tier = conditional_config.get("field_tier", "custom")
        expected_value = conditional_config.get("condition_value")

        if field_tier == "standard":
            actual_value = subscriber.get("standard_fields", {}).get(field_name)
        else:
            actual_value = subscriber.get("custom_fields", {}).get(field_name)

        if condition_type == "field_exists":
            return actual_value not in (None, "")
        if condition_type == "field_not_exists":
            return actual_value in (None, "")

        if expected_value is None:
            return False

        actual_str = str(actual_value).lower() if actual_value is not None else ""
        expected_str = str(expected_value).lower()

        if condition_type == "field_equals":
            return actual_str == expected_str
        if condition_type == "field_not_equals":
            return actual_str != expected_str
        if condition_type == "field_contains":
            return expected_str in actual_str

    # ── tag_has ──────────────────────────────────────────────────────────
    if condition_type == "tag_has":
        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not subscriber:
            return False
        required_tag = conditional_config.get("condition_value")
        if not required_tag:
            return False
        tags = subscriber.get("tags", []) or []
        return required_tag in tags

    # ── custom_event ─────────────────────────────────────────────────────
    if condition_type == "custom_event":
        event_name = conditional_config.get("condition_value")
        if not event_name:
            return False
        # Look for the event in the past 30 days by default
        lookback_days = int(conditional_config.get("lookback_days", 30) or 30)
        since = datetime.utcnow() - timedelta(days=lookback_days)
        event = email_events_collection.find_one({
            "subscriber_id": subscriber_id,
            "event_type": event_name,
            "timestamp": {"$gte": since},
        })
        return event is not None

    logger.warning(f"Unknown condition_type: {condition_type}")
    return False


# =============================================================================
# A/B TEST
# =============================================================================

@shared_task(name="tasks.execute_ab_test_step", bind=True, max_retries=3)
def execute_ab_test_step(
    self,
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    workflow_instance_id: str,
    trigger_data: Optional[dict] = None,
):
    """
    Execute an A/B test step.

    Deterministically assigns a variant based on a hash of subscriber_id +
    step_id (stable across retries — same subscriber always gets same variant).
    """
    try:
        steps_collection = get_sync_automation_steps_collection()
        templates_collection = get_sync_templates_collection()
        executions_collection = get_sync_automation_executions_collection()
        rules_collection = get_sync_automation_rules_collection()

        step = steps_collection.find_one({"_id": ObjectId(step_id)})
        if not step:
            return {"status": "step_not_found"}

        rule = rules_collection.find_one({"_id": ObjectId(automation_rule_id)})
        if not rule:
            return {"status": "rule_not_found"}

        if _workflow_cancelled(workflow_instance_id):
            return {"status": "workflow_cancelled"}

        ab_config = step.get("ab_test_config") or {}
        if not ab_config:
            logger.error(f"A/B step {step_id} missing ab_test_config")
            _record_step_failure(
                automation_rule_id, step_id, subscriber_id, workflow_instance_id,
                "missing_ab_config",
            )
            return {"status": "no_ab_config"}

        variant_a_pct = int(ab_config.get("variant_a_percentage", 50))

        # Stable variant assignment: hash of (subscriber_id, step_id) → 0..99
        bucket = _stable_bucket(subscriber_id, step_id)

        if bucket < variant_a_pct:
            variant = "A"
            template_id = ab_config.get("variant_a_template_id")
            ab_subject = ab_config.get("variant_a_subject")
        else:
            variant = "B"
            template_id = ab_config.get("variant_b_template_id")
            ab_subject = ab_config.get("variant_b_subject")

        if not template_id:
            logger.error(f"A/B step {step_id} variant {variant} has no template_id")
            _record_step_failure(
                automation_rule_id, step_id, subscriber_id, workflow_instance_id,
                f"missing_variant_{variant}_template",
            )
            return {"status": "missing_template"}

        template = templates_collection.find_one({"_id": ObjectId(template_id)})
        if not template:
            logger.error(f"A/B template not found: {template_id}")
            _record_step_failure(
                automation_rule_id, step_id, subscriber_id, workflow_instance_id,
                "ab_template_not_found",
            )
            return {"status": "template_not_found"}

        final_subject = ab_subject or template.get("subject", "")

        email_config_data = rule.get("email_config", {})
        email_config = {
            "from_email": email_config_data.get("sender_email", ""),
            "from_name": email_config_data.get("sender_name", ""),
            "reply_to": email_config_data.get("reply_to"),
            "subject": final_subject,
        }

        # Insert execution record (variant + dispatched state)
        execution_doc = {
            "_id": ObjectId(),
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id,
            "workflow_instance_id": workflow_instance_id,
            "step_type": "ab_split",
            "step_order": step.get("step_order"),
            "ab_variant": variant,
            "ab_bucket": bucket,
            "template_id": template_id,
            "status": "dispatched",
            "executed_at": datetime.utcnow(),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        executions_collection.insert_one(execution_doc)

        # Dispatch send via the canonical automation send task
        from tasks.automation.automation_email_tasks import send_automation_email

        result = send_automation_email.delay(
            subscriber_id=subscriber_id,
            template_id=template_id,
            automation_rule_id=automation_rule_id,
            step_id=step_id,
            workflow_instance_id=workflow_instance_id,
            email_config=email_config,
            field_map=step.get("field_map", {}),
            fallback_values=step.get("fallback_values", {}),
        )

        executions_collection.update_one(
            {"_id": execution_doc["_id"]},
            {"$set": {
                "status": "sent",
                "email_task_id": result.id,
                "updated_at": datetime.utcnow(),
            }},
        )

        # Workflow accounting
        from tasks.automation.automation_tasks import (
            _schedule_next_step,
            mark_step_completed,
            mark_workflow_completed,
        )
        mark_step_completed(workflow_instance_id, was_email=True)

        scheduled = _schedule_next_step(
            rule=rule,
            current_step=step,
            automation_rule_id=automation_rule_id,
            subscriber_id=subscriber_id,
            workflow_instance_id=workflow_instance_id,
            trigger_data=trigger_data or {},
        )
        if not scheduled:
            mark_workflow_completed(workflow_instance_id)

        logger.info(
            f"A/B step {step_id}: variant={variant} bucket={bucket} "
            f"task={result.id} workflow={workflow_instance_id}"
        )

        return {
            "status": "success",
            "variant": variant,
            "template_id": template_id,
            "email_task_id": result.id,
            "next_step_scheduled": scheduled,
        }

    except Exception as exc:
        logger.error(f"Error in execute_ab_test_step: {exc}", exc_info=True)
        raise self.retry(exc=exc)


def _stable_bucket(subscriber_id: str, step_id: str) -> int:
    """Deterministic 0..99 bucket from (subscriber_id, step_id)."""
    h = hashlib.sha256(f"{subscriber_id}:{step_id}".encode("utf-8")).hexdigest()
    return int(h[:8], 16) % 100


# =============================================================================
# WAIT FOR EVENT
# =============================================================================

@shared_task(name="tasks.wait_for_event_step", bind=True, max_retries=3)
def wait_for_event_step(
    self,
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    workflow_instance_id: str,
    trigger_data: Optional[dict] = None,
):
    """
    Wait for a specific event before continuing the automation.

    Recursively reschedules itself every hour until either the event occurs
    or the max wait window is exceeded. On timeout, takes one of:
      - continue        : schedule next sequential step
      - exit            : terminate workflow
      - alternate_path  : schedule alternate_step_ids
    """
    try:
        steps_collection = get_sync_automation_steps_collection()
        executions_collection = get_sync_automation_executions_collection()
        email_events_collection = get_sync_email_events_collection()
        rules_collection = get_sync_automation_rules_collection()

        step = steps_collection.find_one({"_id": ObjectId(step_id)})
        if not step:
            return {"status": "step_not_found"}

        rule = rules_collection.find_one({"_id": ObjectId(automation_rule_id)})
        if not rule:
            return {"status": "rule_not_found"}

        if _workflow_cancelled(workflow_instance_id):
            return {"status": "workflow_cancelled"}

        wait_config = step.get("wait_for_event") or {}
        event_type = wait_config.get("event_type")
        max_wait_hours = int(wait_config.get("max_wait_hours", 168))  # 7d default

        # Find or create the waiting execution record
        execution = executions_collection.find_one({
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id,
            "workflow_instance_id": workflow_instance_id,
            "status": "waiting",
        })

        if not execution:
            execution_doc = {
                "_id": ObjectId(),
                "automation_rule_id": automation_rule_id,
                "automation_step_id": step_id,
                "subscriber_id": subscriber_id,
                "workflow_instance_id": workflow_instance_id,
                "step_type": "wait_for_event",
                "step_order": step.get("step_order"),
                "status": "waiting",
                "waiting_for_event": event_type,
                "wait_started_at": datetime.utcnow(),
                "max_wait_until": datetime.utcnow() + timedelta(hours=max_wait_hours),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
            executions_collection.insert_one(execution_doc)
            execution = execution_doc

        # Has the event occurred?
        event_occurred = False
        if event_type == "opened_email":
            event = email_events_collection.find_one({
                "subscriber_id": subscriber_id,
                "event_type": "open",
                "automation_rule_id": automation_rule_id,
                "timestamp": {"$gte": execution["wait_started_at"]},
            })
            event_occurred = event is not None
        elif event_type == "clicked_link":
            event = email_events_collection.find_one({
                "subscriber_id": subscriber_id,
                "event_type": "click",
                "automation_rule_id": automation_rule_id,
                "timestamp": {"$gte": execution["wait_started_at"]},
            })
            event_occurred = event is not None
        elif event_type == "made_purchase":
            event = email_events_collection.find_one({
                "subscriber_id": subscriber_id,
                "event_type": "purchase",
                "timestamp": {"$gte": execution["wait_started_at"]},
            })
            event_occurred = event is not None
        else:
            # Custom event type
            event = email_events_collection.find_one({
                "subscriber_id": subscriber_id,
                "event_type": event_type,
                "timestamp": {"$gte": execution["wait_started_at"]},
            })
            event_occurred = event is not None

        timeout = datetime.utcnow() > execution.get(
            "max_wait_until", datetime.utcnow() + timedelta(hours=max_wait_hours)
        )

        from tasks.automation.automation_tasks import (
            _schedule_next_step,
            mark_step_completed,
            mark_workflow_completed,
            schedule_specific_next_steps,
        )

        # ── EVENT OCCURRED ────────────────────────────────────────────────
        if event_occurred:
            executions_collection.update_one(
                {"_id": execution["_id"]},
                {"$set": {
                    "status": "completed",
                    "event_occurred_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }},
            )
            mark_step_completed(workflow_instance_id, was_email=False)

            scheduled = _schedule_next_step(
                rule=rule,
                current_step=step,
                automation_rule_id=automation_rule_id,
                subscriber_id=subscriber_id,
                workflow_instance_id=workflow_instance_id,
                trigger_data=trigger_data or {},
            )
            if not scheduled:
                mark_workflow_completed(workflow_instance_id)

            return {"status": "event_occurred", "next_step_scheduled": scheduled}

        # ── TIMEOUT ───────────────────────────────────────────────────────
        if timeout:
            timeout_action = wait_config.get("timeout_action", "continue")

            executions_collection.update_one(
                {"_id": execution["_id"]},
                {"$set": {
                    "status": "timeout",
                    "timed_out_at": datetime.utcnow(),
                    "timeout_action": timeout_action,
                    "updated_at": datetime.utcnow(),
                }},
            )
            mark_step_completed(workflow_instance_id, was_email=False)

            if timeout_action == "exit":
                mark_workflow_completed(workflow_instance_id)
                return {"status": "timeout", "action": "exit"}

            if timeout_action == "alternate_path":
                alternate_step_ids = wait_config.get("alternate_step_ids", []) or []
                scheduled = schedule_specific_next_steps(
                    rule=rule,
                    automation_rule_id=automation_rule_id,
                    subscriber_id=subscriber_id,
                    workflow_instance_id=workflow_instance_id,
                    trigger_data=trigger_data or {},
                    next_step_ids=alternate_step_ids,
                )
                if scheduled == 0:
                    mark_workflow_completed(workflow_instance_id)
                return {"status": "timeout", "action": "alternate_path", "scheduled": scheduled}

            # default: continue
            scheduled = _schedule_next_step(
                rule=rule,
                current_step=step,
                automation_rule_id=automation_rule_id,
                subscriber_id=subscriber_id,
                workflow_instance_id=workflow_instance_id,
                trigger_data=trigger_data or {},
            )
            if not scheduled:
                mark_workflow_completed(workflow_instance_id)
            return {"status": "timeout", "action": "continue", "next_step_scheduled": scheduled}

        # ── STILL WAITING ─────────────────────────────────────────────────
        # Reschedule self in 1 hour. The atomic check above ensures only
        # one waiting record per (rule, step, subscriber, workflow).
        wait_for_event_step.apply_async(
            kwargs={
                "automation_rule_id": automation_rule_id,
                "step_id": step_id,
                "subscriber_id": subscriber_id,
                "workflow_instance_id": workflow_instance_id,
                "trigger_data": trigger_data or {},
            },
            countdown=3600,
        )
        return {"status": "waiting", "next_check_in_seconds": 3600}

    except Exception as exc:
        logger.error(f"Error in wait_for_event_step: {exc}", exc_info=True)
        raise self.retry(exc=exc)


# =============================================================================
# WEBHOOK STEP (with HMAC signing + proper retry)
# =============================================================================

@shared_task(
    name="tasks.send_webhook_step",
    bind=True,
    max_retries=5,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def send_webhook_step(
    self,
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    workflow_instance_id: str,
    trigger_data: Optional[dict] = None,
):
    """
    Send a webhook as a step in the automation workflow.

    HMAC signs the request body if a webhook_secret is configured on the rule.
    Retries on 5xx and timeouts (transient); does not retry on 4xx (permanent).
    """
    executions_collection = get_sync_automation_executions_collection()

    try:
        steps_collection = get_sync_automation_steps_collection()
        rules_collection = get_sync_automation_rules_collection()
        subscribers_collection = get_sync_subscribers_collection()

        step = steps_collection.find_one({"_id": ObjectId(step_id)})
        if not step:
            return {"status": "step_not_found"}

        rule = rules_collection.find_one({"_id": ObjectId(automation_rule_id)})
        if not rule:
            return {"status": "rule_not_found"}

        if _workflow_cancelled(workflow_instance_id):
            return {"status": "workflow_cancelled"}

        webhook_url = step.get("webhook_url")
        if not webhook_url:
            logger.error(f"Webhook step {step_id} has no webhook_url")
            _record_step_failure(
                automation_rule_id, step_id, subscriber_id, workflow_instance_id,
                "missing_webhook_url",
            )
            return {"status": "missing_webhook_url"}

        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not subscriber:
            return {"status": "subscriber_not_found"}

        custom_payload = step.get("webhook_payload") or {}
        payload = {
            **custom_payload,
            "subscriber": {
                "id": subscriber_id,
                "email": subscriber.get("email"),
                "standard_fields": subscriber.get("standard_fields", {}),
                "custom_fields": subscriber.get("custom_fields", {}),
            },
            "automation_rule_id": automation_rule_id,
            "step_id": step_id,
            "workflow_instance_id": workflow_instance_id,
            "timestamp": datetime.utcnow().isoformat(),
            "trigger_data": trigger_data or {},
        }

        body_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ZeniPost-Automation/1.0",
            "X-ZeniPost-Event": "automation.step.webhook",
            "X-ZeniPost-Delivery": str(ObjectId()),
            "X-ZeniPost-Timestamp": str(int(datetime.utcnow().timestamp())),
        }

        # HMAC signing if a secret is configured
        webhook_secret = rule.get("webhook_secret") or _get_workspace_webhook_secret(rule)
        if webhook_secret:
            signature = hmac.new(
                webhook_secret.encode("utf-8"),
                body_bytes,
                hashlib.sha256,
            ).hexdigest()
            headers["X-ZeniPost-Signature"] = f"sha256={signature}"
        else:
            logger.warning(
                f"Webhook step {step_id} sending UNSIGNED — "
                f"no webhook_secret on rule {automation_rule_id}"
            )

        try:
            response = requests.post(
                webhook_url,
                data=body_bytes,
                headers=headers,
                timeout=10,
            )
        except requests.Timeout as e:
            logger.warning(f"Webhook timeout for {webhook_url}: {e}")
            executions_collection.insert_one({
                "_id": ObjectId(),
                "automation_rule_id": automation_rule_id,
                "automation_step_id": step_id,
                "subscriber_id": subscriber_id,
                "workflow_instance_id": workflow_instance_id,
                "step_type": "send_webhook",
                "status": "retrying",
                "webhook_url": webhook_url,
                "error": f"timeout: {e}",
                "attempt": self.request.retries + 1,
                "executed_at": datetime.utcnow(),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            })
            raise self.retry(exc=e)
        except requests.ConnectionError as e:
            logger.warning(f"Webhook connection error for {webhook_url}: {e}")
            raise self.retry(exc=e)

        # 5xx → retry; 4xx → permanent failure (don't retry)
        if 500 <= response.status_code < 600:
            err = f"server_error_{response.status_code}"
            executions_collection.insert_one({
                "_id": ObjectId(),
                "automation_rule_id": automation_rule_id,
                "automation_step_id": step_id,
                "subscriber_id": subscriber_id,
                "workflow_instance_id": workflow_instance_id,
                "step_type": "send_webhook",
                "status": "retrying",
                "webhook_url": webhook_url,
                "webhook_response_status": response.status_code,
                "error": err,
                "attempt": self.request.retries + 1,
                "executed_at": datetime.utcnow(),
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            })
            raise self.retry(exc=requests.HTTPError(err))

        ok = 200 <= response.status_code < 300
        status_str = "sent" if ok else "failed"

        executions_collection.insert_one({
            "_id": ObjectId(),
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id,
            "workflow_instance_id": workflow_instance_id,
            "step_type": "send_webhook",
            "status": status_str,
            "webhook_url": webhook_url,
            "webhook_response_status": response.status_code,
            "webhook_response_snippet": response.text[:500] if response.text else "",
            "executed_at": datetime.utcnow(),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })

        # Always advance the workflow even on 4xx (it's a permanent client
        # error, not a workflow error — proceeding is the documented behavior)
        from tasks.automation.automation_tasks import (
            _schedule_next_step,
            mark_step_completed,
            mark_workflow_completed,
        )
        mark_step_completed(workflow_instance_id, was_email=False)

        scheduled = _schedule_next_step(
            rule=rule,
            current_step=step,
            automation_rule_id=automation_rule_id,
            subscriber_id=subscriber_id,
            workflow_instance_id=workflow_instance_id,
            trigger_data=trigger_data or {},
        )
        if not scheduled:
            mark_workflow_completed(workflow_instance_id)

        logger.info(
            f"Webhook step {step_id}: status={response.status_code} "
            f"workflow={workflow_instance_id} next_scheduled={scheduled}"
        )

        return {
            "status": status_str,
            "response_status": response.status_code,
            "next_step_scheduled": scheduled,
        }

    except self.MaxRetriesExceededError:
        logger.error(f"Webhook step {step_id} exhausted retries")
        _record_step_failure(
            automation_rule_id, step_id, subscriber_id, workflow_instance_id,
            "webhook_max_retries_exceeded",
        )
        return {"status": "max_retries_exceeded"}

    except Exception as exc:
        logger.error(f"Error in send_webhook_step: {exc}", exc_info=True)
        raise


def _get_workspace_webhook_secret(rule: dict) -> Optional[str]:
    """Look up workspace-level webhook secret if rule doesn't have one."""
    try:
        from database import get_sync_settings_collection
        settings_doc = get_sync_settings_collection().find_one(
            {"type": "automation_webhooks"}
        )
        if settings_doc:
            return settings_doc.get("config", {}).get("webhook_secret")
    except Exception as e:
        logger.warning(f"Failed to load workspace webhook secret: {e}")
    return None


# =============================================================================
# UPDATE FIELD STEP
# =============================================================================

@shared_task(name="tasks.update_field_step", bind=True, max_retries=3)
def update_field_step(
    self,
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    workflow_instance_id: str,
    trigger_data: Optional[dict] = None,
):
    """Update subscriber fields as part of an automation step."""
    try:
        steps_collection = get_sync_automation_steps_collection()
        subscribers_collection = get_sync_subscribers_collection()
        executions_collection = get_sync_automation_executions_collection()
        rules_collection = get_sync_automation_rules_collection()

        step = steps_collection.find_one({"_id": ObjectId(step_id)})
        if not step:
            return {"status": "step_not_found"}

        rule = rules_collection.find_one({"_id": ObjectId(automation_rule_id)})
        if not rule:
            return {"status": "rule_not_found"}

        if _workflow_cancelled(workflow_instance_id):
            return {"status": "workflow_cancelled"}

        field_updates = step.get("field_updates") or {}
        if not field_updates:
            logger.warning(f"update_field step {step_id} has no field_updates")
            _record_step_failure(
                automation_rule_id, step_id, subscriber_id, workflow_instance_id,
                "missing_field_updates",
            )
            return {"status": "no_updates"}

        # Build $set update doc with safe field paths
        STANDARD_FIELDS = {
            "first_name", "last_name", "phone", "company",
            "city", "country", "timezone", "birthday",
        }
        update_data = {}
        for field, value in field_updates.items():
            if field in STANDARD_FIELDS:
                update_data[f"standard_fields.{field}"] = value
            elif field == "tags" and isinstance(value, list):
                update_data["tags"] = value
            elif field == "status" and value in ("active", "unsubscribed", "bounced"):
                update_data["status"] = value
            else:
                update_data[f"custom_fields.{field}"] = value

        update_data["updated_at"] = datetime.utcnow()

        result = subscribers_collection.update_one(
            {"_id": ObjectId(subscriber_id)},
            {"$set": update_data},
        )

        executions_collection.insert_one({
            "_id": ObjectId(),
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id,
            "workflow_instance_id": workflow_instance_id,
            "step_type": "update_field",
            "step_order": step.get("step_order"),
            "status": "completed" if result.modified_count else "no_change",
            "fields_updated": list(field_updates.keys()),
            "executed_at": datetime.utcnow(),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })

        from tasks.automation.automation_tasks import (
            _schedule_next_step,
            mark_step_completed,
            mark_workflow_completed,
        )
        mark_step_completed(workflow_instance_id, was_email=False)

        scheduled = _schedule_next_step(
            rule=rule,
            current_step=step,
            automation_rule_id=automation_rule_id,
            subscriber_id=subscriber_id,
            workflow_instance_id=workflow_instance_id,
            trigger_data=trigger_data or {},
        )
        if not scheduled:
            mark_workflow_completed(workflow_instance_id)

        logger.info(
            f"update_field step {step_id}: modified={result.modified_count} "
            f"fields={list(field_updates.keys())} next_scheduled={scheduled}"
        )

        return {
            "status": "success",
            "fields_updated": list(field_updates.keys()),
            "modified_count": result.modified_count,
            "next_step_scheduled": scheduled,
        }

    except Exception as exc:
        logger.error(f"Error in update_field_step: {exc}", exc_info=True)
        raise self.retry(exc=exc)


# =============================================================================
# GOAL CHECK STEP
# =============================================================================

@shared_task(name="tasks.goal_check_step", bind=True, max_retries=3)
def goal_check_step(
    self,
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    workflow_instance_id: str,
    trigger_data: Optional[dict] = None,
):
    """
    Mid-workflow goal check step.

    Evaluates the rule's primary_goal (or step-level goal_tracking) and
    cancels the workflow if the goal is met and exit_on_goal_achieved is set.
    Otherwise advances to the next step.
    """
    try:
        steps_collection = get_sync_automation_steps_collection()
        rules_collection = get_sync_automation_rules_collection()

        step = steps_collection.find_one({"_id": ObjectId(step_id)})
        if not step:
            return {"status": "step_not_found"}

        rule = rules_collection.find_one({"_id": ObjectId(automation_rule_id)})
        if not rule:
            return {"status": "rule_not_found"}

        if _workflow_cancelled(workflow_instance_id):
            return {"status": "workflow_cancelled"}

        goal_config = step.get("goal_tracking") or rule.get("primary_goal") or {}

        from tasks.automation.automation_tasks import (
            _schedule_next_step,
            cancel_automation_workflow,
            check_if_goal_achieved,
            mark_step_completed,
            mark_workflow_completed,
        )

        achieved = check_if_goal_achieved(automation_rule_id, subscriber_id, goal_config)

        executions_collection = get_sync_automation_executions_collection()
        executions_collection.insert_one({
            "_id": ObjectId(),
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id,
            "workflow_instance_id": workflow_instance_id,
            "step_type": "goal_check",
            "step_order": step.get("step_order"),
            "status": "completed",
            "goal_achieved": achieved,
            "goal_type": goal_config.get("goal_type"),
            "executed_at": datetime.utcnow(),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })

        mark_step_completed(workflow_instance_id, was_email=False)

        if achieved and rule.get("exit_on_goal_achieved", True):
            cancel_automation_workflow(automation_rule_id, subscriber_id)
            return {"status": "goal_achieved_workflow_cancelled"}

        scheduled = _schedule_next_step(
            rule=rule,
            current_step=step,
            automation_rule_id=automation_rule_id,
            subscriber_id=subscriber_id,
            workflow_instance_id=workflow_instance_id,
            trigger_data=trigger_data or {},
        )
        if not scheduled:
            mark_workflow_completed(workflow_instance_id)

        return {
            "status": "success",
            "goal_achieved": achieved,
            "next_step_scheduled": scheduled,
        }

    except Exception as exc:
        logger.error(f"Error in goal_check_step: {exc}", exc_info=True)
        raise self.retry(exc=exc)


# =============================================================================
# OPTIMIZE SEND TIME (smart send-time wrapper for email steps)
# =============================================================================

@shared_task(name="tasks.optimize_send_time", bind=True, max_retries=3)
def optimize_send_time(
    self,
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    workflow_instance_id: str,
    trigger_data: Optional[dict] = None,
):
    """
    Compute the ideal send-hour for a subscriber based on historical
    engagement, then reschedule execute_automation_step at that hour with
    trigger_data._smart_send_resolved=True so the email step proceeds without
    re-deferring.
    """
    try:
        from tasks.automation.automation_tasks import execute_automation_step

        email_events_collection = get_sync_email_events_collection()
        steps_collection = get_sync_automation_steps_collection()

        step = steps_collection.find_one({"_id": ObjectId(step_id)})
        if not step:
            return {"status": "step_not_found"}

        if _workflow_cancelled(workflow_instance_id):
            return {"status": "workflow_cancelled"}

        smart_config = step.get("smart_send_time") or {}
        if not smart_config.get("enabled"):
            # Disabled — just dispatch immediately
            execute_automation_step.delay(
                automation_rule_id, step_id, subscriber_id, workflow_instance_id,
                {**(trigger_data or {}), "_smart_send_resolved": True},
            )
            return {"status": "smart_send_disabled"}

        optimize_for = smart_config.get("optimize_for", "opens")
        win_start = int(smart_config.get("time_window_start", 8))
        win_end = int(smart_config.get("time_window_end", 20))
        fallback_hour = int(smart_config.get("fallback_time", 10))

        event_type = "open" if optimize_for == "opens" else "click"
        historical = list(
            email_events_collection.find({
                "subscriber_id": subscriber_id,
                "event_type": event_type,
            })
            .sort("timestamp", -1)
            .limit(50)
        )

        if len(historical) >= 5:
            hour_counts: dict[int, int] = {}
            for event in historical:
                ts = event.get("timestamp")
                if ts:
                    hour_counts[ts.hour] = hour_counts.get(ts.hour, 0) + 1

            best_hour = fallback_hour
            best_count = 0
            for h in range(win_start, win_end + 1):
                c = hour_counts.get(h, 0)
                if c > best_count:
                    best_count = c
                    best_hour = h
            optimal_hour = best_hour
        else:
            optimal_hour = fallback_hour

        # Compute ETA
        now = datetime.utcnow()
        target = now.replace(hour=optimal_hour, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)

        execute_automation_step.apply_async(
            args=[
                automation_rule_id, step_id, subscriber_id, workflow_instance_id,
                {**(trigger_data or {}), "_smart_send_resolved": True},
            ],
            eta=target,
        )

        logger.info(
            f"Smart-send: subscriber {subscriber_id} optimal_hour={optimal_hour} "
            f"target={target.isoformat()} (sample_size={len(historical)})"
        )

        return {
            "status": "success",
            "optimal_hour": optimal_hour,
            "scheduled_for": target.isoformat(),
            "sample_size": len(historical),
        }

    except Exception as exc:
        logger.error(f"Error in optimize_send_time: {exc}", exc_info=True)
        raise self.retry(exc=exc)


# =============================================================================
# LEGACY GOAL CHECK ENTRY POINT (for direct invocation; kept for compat)
# =============================================================================

@shared_task(name="tasks.check_goal_achievement")
def check_goal_achievement(
    automation_rule_id: str,
    subscriber_id: str,
    goal_config: dict,
):
    """
    Standalone goal-achievement check.

    Used by external callers (e.g., manual ops). For mid-workflow goal
    checks, use the goal_check_step task which is reachable via the step
    dispatcher.
    """
    try:
        from tasks.automation.automation_tasks import (
            cancel_automation_workflow,
            check_if_goal_achieved,
        )

        achieved = check_if_goal_achieved(automation_rule_id, subscriber_id, goal_config)

        if achieved:
            rule = get_sync_automation_rules_collection().find_one(
                {"_id": ObjectId(automation_rule_id)}
            )
            if rule and rule.get("exit_on_goal_achieved"):
                cancel_automation_workflow.delay(automation_rule_id, subscriber_id)

            logger.info(
                f"Goal achieved for automation {automation_rule_id} "
                f"subscriber {subscriber_id}"
            )

        return {"status": "success", "goal_achieved": achieved}

    except Exception as e:
        logger.error(f"Error in check_goal_achievement: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


# =============================================================================
# BEAT TASK: per-rule send-time analysis
# =============================================================================

@shared_task(name="tasks.analyze_optimal_send_times", bind=True)
def analyze_optimal_send_times(self):
    """
    Analyze optimal send times across active automations. Optional beat task
    that pre-computes engagement-by-hour stats per rule and stores them on
    the rule document for later use by smart-send-time.
    """
    try:
        rules_collection = get_sync_automation_rules_collection()
        events_collection = get_sync_email_events_collection()

        active_rules = list(rules_collection.find({
            "status": "active",
            "deleted_at": {"$exists": False},
        }))

        analyzed = 0
        for rule in active_rules:
            rule_id = str(rule["_id"])
            since = datetime.utcnow() - timedelta(days=30)

            pipeline = [
                {"$match": {
                    "automation_rule_id": rule_id,
                    "event_type": {"$in": ["open", "click"]},
                    "timestamp": {"$gte": since},
                }},
                {"$group": {
                    "_id": {"hour": {"$hour": "$timestamp"}},
                    "count": {"$sum": 1},
                }},
                {"$sort": {"count": -1}},
            ]

            try:
                results = list(events_collection.aggregate(pipeline))
                if results:
                    rules_collection.update_one(
                        {"_id": ObjectId(rule_id)},
                        {"$set": {
                            "engagement_by_hour": [
                                {"hour": r["_id"]["hour"], "count": r["count"]}
                                for r in results
                            ],
                            "engagement_analyzed_at": datetime.utcnow(),
                        }},
                    )
                analyzed += 1
            except Exception as e:
                logger.warning(f"Failed to analyze rule {rule_id}: {e}")

        return {"analyzed": analyzed}

    except Exception as e:
        logger.error(f"analyze_optimal_send_times failed: {e}", exc_info=True)
        return {"error": str(e), "analyzed": 0}


# =============================================================================
# SHARED HELPERS
# =============================================================================

def _workflow_cancelled(workflow_instance_id: str) -> bool:
    """Check if the workflow has been cancelled. Cheap status query."""
    try:
        wf = get_sync_workflow_instances_collection().find_one(
            {"_id": ObjectId(workflow_instance_id)},
            {"status": 1},
        )
        if not wf:
            return True  # missing = treat as cancelled to be safe
        return wf.get("status") in ("cancelled", "completed", "failed")
    except Exception:
        return False


def _record_step_failure(
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    workflow_instance_id: str,
    reason: str,
) -> None:
    """Record a failed step execution and increment workflow completion counter."""
    try:
        get_sync_automation_executions_collection().insert_one({
            "_id": ObjectId(),
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id,
            "workflow_instance_id": workflow_instance_id,
            "status": "failed",
            "error": reason,
            "failed_at": datetime.utcnow(),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
        # Failed steps still count toward completion so the workflow can finish
        from tasks.automation.automation_tasks import mark_step_completed
        mark_step_completed(workflow_instance_id, was_email=False)
    except Exception as e:
        logger.error(f"Failed to record step failure: {e}", exc_info=True)