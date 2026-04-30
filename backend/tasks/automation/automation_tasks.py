# backend/tasks/automation/automation_tasks.py
"""
Celery tasks for automation workflow execution.

This is the canonical automation task module. The legacy
backend/tasks/automation_tasks.py file is deprecated and must be removed —
both files registered tasks under identical names (e.g. tasks.execute_automation_step)
and which one won the registry was non-deterministic across worker restarts.

Architecture:
  - process_automation_trigger : entry point from triggers (welcome, birthday, etc.)
  - start_automation_workflow  : creates workflow instance, schedules FIRST step only
  - execute_automation_step    : routes by step_type to the appropriate handler;
                                 each handler chains the next step on success
  - cancel_automation_workflow : revokes future steps for a (rule, subscriber)

Step dispatch:
  email          → _handle_email_step (sends via send_automation_email)
  delay          → _handle_delay_step (no-op; just schedules next step)
  condition      → execute_conditional_step (advanced)
  ab_split       → execute_ab_test_step    (advanced)
  wait_for_event → wait_for_event_step     (advanced)
  send_webhook   → send_webhook            (advanced)
  update_field   → update_subscriber_field (advanced)
  goal_check     → check_goal_achievement  (advanced)

Completion model:
  - completed_steps is incremented for EVERY step type that completes,
    not just emails (fix for prior bug)
  - emails_sent is incremented only for email-type steps
  - Workflow is marked completed when a step's handler determines there
    is no next step in the chain — NOT by counting against total_steps,
    because total_steps is meaningless for branched (conditional/A-B) flows.

Cancellation model:
  - cancel_automation_workflow flips workflow_instance.status = "cancelled"
  - Every step handler checks workflow status as its first action and
    no-ops if cancelled. This makes cancellation safe even though we
    can no longer revoke all future task IDs (we don't pre-schedule them).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

import pytz
from bson import ObjectId
from celery import shared_task

from database import (
    get_sync_automation_executions_collection,
    get_sync_automation_rules_collection,
    get_sync_automation_steps_collection,
    get_sync_segments_collection,
    get_sync_subscribers_collection,
    get_sync_suppressions_collection,
    get_sync_templates_collection,
    get_sync_workflow_instances_collection,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

# Step types that always need a template
EMAIL_STEP_TYPES = {"email"}

# Step types whose handlers live in automation_advanced_tasks.py
ADVANCED_STEP_TYPES = {
    "condition",
    "ab_split",
    "wait_for_event",
    "send_webhook",
    "update_field",
    "goal_check",
}

# Pure pass-through; just schedule the next step
PASSTHROUGH_STEP_TYPES = {"delay"}


# =============================================================================
# TRIGGER ENTRY POINT
# =============================================================================


@shared_task(
    name="tasks.process_automation_trigger",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def process_automation_trigger(
    self,
    trigger_type: str,
    subscriber_id: str,
    trigger_data: Optional[dict] = None,
):
    """
    Process an automation trigger event.

    Finds active automation rules matching trigger_type, validates subscriber
    eligibility against each rule, and spawns start_automation_workflow.delay()
    for every rule the subscriber qualifies for.
    """
    try:
        rules_collection = get_sync_automation_rules_collection()
        subscribers_collection = get_sync_subscribers_collection()
        suppressions_collection = get_sync_suppressions_collection()
        workflow_instances_collection = get_sync_workflow_instances_collection()

        rules = list(
            rules_collection.find(
                {
                    "trigger": trigger_type,
                    "status": "active",
                    "deleted_at": {"$exists": False},
                }
            )
        )

        if not rules:
            logger.info(f"No active automation rules for trigger: {trigger_type}")
            return {"status": "no_rules", "trigger": trigger_type}

        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not subscriber:
            logger.error(f"Subscriber not found: {subscriber_id}")
            return {"status": "subscriber_not_found"}

        # Global eligibility checks
        if subscriber.get("status") != "active":
            logger.info(
                f"Subscriber {subscriber_id} is not active, skipping automation"
            )
            return {"status": "subscriber_inactive"}

        subscriber_email = subscriber.get("email")
        if suppressions_collection.find_one(
            {"email": subscriber_email, "is_active": True}
        ):
            logger.info(
                f"Subscriber {subscriber_email} is suppressed, skipping automation"
            )
            return {"status": "subscriber_suppressed"}

        results = []

        for rule in rules:
            rule_id = str(rule["_id"])

            # Active workflow handling
            active_workflow = workflow_instances_collection.find_one(
                {
                    "automation_rule_id": rule_id,
                    "subscriber_id": subscriber_id,
                    "status": "in_progress",
                }
            )

            if active_workflow:
                if rule.get("cancel_previous_on_retrigger", True):
                    logger.info(
                        f"Cancelling previous workflow for subscriber {subscriber_id}"
                    )
                    cancel_automation_workflow(rule_id, subscriber_id)
                else:
                    logger.info("Active workflow exists, skipping new trigger")
                    continue

            # Re-trigger policy
            allow_retrigger = rule.get("allow_retrigger", False)
            retrigger_delay_hours = rule.get("retrigger_delay_hours", 24)

            if not allow_retrigger and trigger_type not in ("birthday",):
                already_completed = workflow_instances_collection.find_one(
                    {
                        "automation_rule_id": rule_id,
                        "subscriber_id": subscriber_id,
                        "status": "completed",
                    }
                )
                if already_completed:
                    logger.info(
                        f"Automation {rule_id} already completed for {subscriber_id}, skipping"
                    )
                    continue

            if allow_retrigger and retrigger_delay_hours > 0:
                threshold = datetime.utcnow() - timedelta(hours=retrigger_delay_hours)
                recent = workflow_instances_collection.find_one(
                    {
                        "automation_rule_id": rule_id,
                        "subscriber_id": subscriber_id,
                        "started_at": {"$gte": threshold},
                    }
                )
                if recent:
                    logger.info(
                        f"Automation triggered too recently (delay: {retrigger_delay_hours}h)"
                    )
                    continue

            # Birthday: once per calendar year
            if trigger_type == "birthday":
                year_start = datetime(datetime.utcnow().year, 1, 1)
                already_this_year = workflow_instances_collection.find_one(
                    {
                        "automation_rule_id": rule_id,
                        "subscriber_id": subscriber_id,
                        "started_at": {"$gte": year_start},
                    }
                )
                if already_this_year:
                    logger.info(
                        f"Birthday automation already triggered this year for {subscriber_id}"
                    )
                    continue

            # Target segment / list filtering (dynamic segment evaluation)
            if not _subscriber_matches_rule_targets(subscriber, rule):
                logger.info(
                    f"Subscriber not in target segments/lists for rule: {rule['name']}"
                )
                continue

            # Trigger conditions
            if not evaluate_trigger_conditions(
                rule.get("trigger_conditions", {}), subscriber, trigger_data
            ):
                logger.info(f"Trigger conditions not met for rule: {rule['name']}")
                continue

            # All checks passed — start workflow
            logger.info(
                f"Starting automation workflow for subscriber {subscriber_id} on rule {rule_id}"
            )
            result = start_automation_workflow.delay(
                automation_rule_id=rule_id,
                subscriber_id=subscriber_id,
                trigger_data=trigger_data or {},
            )

            results.append(
                {
                    "rule_id": rule_id,
                    "rule_name": rule["name"],
                    "task_id": result.id,
                    "status": "triggered",
                }
            )

        return {
            "status": "success",
            "trigger": trigger_type,
            "subscriber_id": subscriber_id,
            "rules_triggered": sum(
                1 for r in results if r.get("status") == "triggered"
            ),
            "results": results,
        }

    except Exception as exc:
        logger.error(f"Error processing automation trigger: {exc}", exc_info=True)
        raise self.retry(exc=exc)


# =============================================================================
# WORKFLOW START
# =============================================================================


@shared_task(
    name="tasks.start_automation_workflow",
    bind=True,
    max_retries=3,
)
def start_automation_workflow(
    self,
    automation_rule_id: str,
    subscriber_id: str,
    trigger_data: Optional[dict] = None,
):
    """
    Start an automation workflow.

    Creates a workflow instance and schedules ONLY the first step. Subsequent
    steps are scheduled by each step's handler on completion. This is required
    for branched (conditional / A-B) workflows where the next step is decided
    at runtime — pre-scheduling all steps would either be wrong or wasteful.
    """
    try:
        rules_collection = get_sync_automation_rules_collection()
        steps_collection = get_sync_automation_steps_collection()
        subscribers_collection = get_sync_subscribers_collection()
        workflow_instances_collection = get_sync_workflow_instances_collection()

        rule = rules_collection.find_one({"_id": ObjectId(automation_rule_id)})
        if not rule:
            logger.error(f"Automation rule not found: {automation_rule_id}")
            return {"status": "rule_not_found"}

        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not subscriber:
            logger.error(f"Subscriber not found: {subscriber_id}")
            return {"status": "subscriber_not_found"}

        # Order steps; first step is the entry point
        steps = list(
            steps_collection.find({"automation_rule_id": automation_rule_id}).sort(
                "step_order", 1
            )
        )

        if not steps:
            logger.warning(f"No steps found for automation: {automation_rule_id}")
            return {"status": "no_steps"}

        first_step = steps[0]

        # Create workflow instance
        workflow_instance_id = str(ObjectId())
        workflow_instances_collection.insert_one(
            {
                "_id": ObjectId(workflow_instance_id),
                "automation_rule_id": automation_rule_id,
                "subscriber_id": subscriber_id,
                "status": "in_progress",
                "started_at": datetime.utcnow(),
                "completed_at": None,
                "total_steps": len(
                    steps
                ),  # informational only; not used for completion
                "completed_steps": 0,
                "emails_sent": 0,
                "emails_opened": 0,
                "emails_clicked": 0,
                "trigger_data": trigger_data or {},
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
        )

        # Resolve timezone
        tz = _resolve_subscriber_timezone(rule, subscriber)
        current_time = datetime.now(tz)

        # Compute ETA for the first step (respect delay_hours and quiet hours)
        eta_utc = _compute_step_eta(
            rule, current_time, first_step.get("delay_hours", 0)
        )

        # Insert execution record and schedule
        _schedule_step_execution(
            automation_rule_id=automation_rule_id,
            step=first_step,
            subscriber_id=subscriber_id,
            workflow_instance_id=workflow_instance_id,
            trigger_data=trigger_data or {},
            eta_utc=eta_utc,
            timezone_name=str(tz),
        )

        logger.info(
            f"Started automation workflow {workflow_instance_id} "
            f"for subscriber {subscriber_id} on rule {automation_rule_id}; "
            f"first step {first_step.get('step_type')} scheduled for {eta_utc.isoformat()}"
        )

        return {
            "status": "success",
            "workflow_instance_id": workflow_instance_id,
            "automation_rule_id": automation_rule_id,
            "subscriber_id": subscriber_id,
            "first_step_id": str(first_step["_id"]),
            "first_step_eta_utc": eta_utc.isoformat(),
        }

    except Exception as exc:
        logger.error(f"Error starting automation workflow: {exc}", exc_info=True)
        raise self.retry(exc=exc)


# =============================================================================
# STEP EXECUTOR (DISPATCH)
# =============================================================================


@shared_task(
    name="tasks.execute_automation_step",
    bind=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=3600,
    retry_jitter=True,
)
def execute_automation_step(
    self,
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    workflow_instance_id: str,
    trigger_data: Optional[dict] = None,
):
    """
    Execute a single automation step.

    Routes by step_type:
      - email           : _handle_email_step (inline)
      - delay           : _handle_delay_step (inline; just chains next step)
      - condition       : execute_conditional_step (advanced module)
      - ab_split        : execute_ab_test_step
      - wait_for_event  : wait_for_event_step
      - send_webhook    : send_webhook (as a step)
      - update_field    : update_subscriber_field (as a step)
      - goal_check      : check_goal_achievement (as a step)

    All step types share the same pre-checks: workflow not cancelled,
    subscriber active and not suppressed, and goal not yet achieved
    (if exit_on_goal_achieved is set).
    """
    rule = None
    step = None
    executions_collection = get_sync_automation_executions_collection()

    try:
        rules_collection = get_sync_automation_rules_collection()
        steps_collection = get_sync_automation_steps_collection()
        subscribers_collection = get_sync_subscribers_collection()
        suppressions_collection = get_sync_suppressions_collection()
        workflow_instances_collection = get_sync_workflow_instances_collection()

        # ── ATOMIC CLAIM ───────────────────────────────────────────────────
        # Prevents double-execution when ETA and the scheduled-poller race.
        claimed = executions_collection.find_one_and_update(
            {
                "automation_step_id": step_id,
                "subscriber_id": subscriber_id,
                "workflow_instance_id": workflow_instance_id,
                "status": {"$in": ["scheduled", "dispatched_by_poller"]},
            },
            {"$set": {"status": "running", "started_at": datetime.utcnow()}},
            return_document=False,
        )
        if claimed is None:
            logger.info(
                f"Execution for step {step_id} / subscriber {subscriber_id} "
                f"already claimed; skipping"
            )
            return {"status": "already_claimed"}

        # ── WORKFLOW CANCELLATION CHECK ────────────────────────────────────
        workflow = workflow_instances_collection.find_one(
            {"_id": ObjectId(workflow_instance_id)}
        )
        if not workflow:
            logger.error(f"Workflow instance not found: {workflow_instance_id}")
            _mark_step_failed(
                executions_collection, step_id, subscriber_id, "workflow_not_found"
            )
            return {"status": "workflow_not_found"}

        if workflow.get("status") in ("cancelled", "completed", "failed"):
            logger.info(
                f"Workflow {workflow_instance_id} is {workflow['status']}; "
                f"skipping step {step_id}"
            )
            _mark_step_failed(
                executions_collection,
                step_id,
                subscriber_id,
                f"workflow_{workflow['status']}",
            )
            return {"status": f"workflow_{workflow['status']}"}

        # ── LOAD RULE AND STEP ─────────────────────────────────────────────
        rule = rules_collection.find_one({"_id": ObjectId(automation_rule_id)})
        if not rule:
            logger.error(f"Automation rule not found: {automation_rule_id}")
            _mark_step_failed(
                executions_collection, step_id, subscriber_id, "rule_not_found"
            )
            return {"status": "rule_not_found"}

        step = steps_collection.find_one({"_id": ObjectId(step_id)})
        if not step:
            logger.error(f"Step not found: {step_id}")
            _mark_step_failed(
                executions_collection, step_id, subscriber_id, "step_not_found"
            )
            return {"status": "step_not_found"}

        # ── SUBSCRIBER ELIGIBILITY ─────────────────────────────────────────
        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not subscriber:
            logger.error(f"Subscriber not found: {subscriber_id}")
            _mark_step_failed(
                executions_collection, step_id, subscriber_id, "subscriber_not_found"
            )
            return {"status": "subscriber_not_found"}

        if subscriber.get("status") != "active":
            logger.info(f"Subscriber {subscriber_id} is no longer active")
            if rule.get("exit_on_unsubscribe", True):
                cancel_automation_workflow(automation_rule_id, subscriber_id)
            _mark_step_failed(
                executions_collection, step_id, subscriber_id, "subscriber_inactive"
            )
            return {"status": "subscriber_inactive"}

        subscriber_email = subscriber.get("email")
        if suppressions_collection.find_one(
            {"email": subscriber_email, "is_active": True}
        ):
            logger.info(f"Subscriber {subscriber_email} is suppressed")
            if rule.get("exit_on_unsubscribe", True):
                cancel_automation_workflow(automation_rule_id, subscriber_id)
            _mark_step_failed(
                executions_collection, step_id, subscriber_id, "subscriber_suppressed"
            )
            return {"status": "subscriber_suppressed"}

        # ── GOAL ACHIEVEMENT CHECK ─────────────────────────────────────────
        if rule.get("exit_on_goal_achieved", True):
            primary_goal = rule.get("primary_goal")
            if primary_goal and check_if_goal_achieved(
                automation_rule_id, subscriber_id, primary_goal
            ):
                logger.info(
                    f"Goal already achieved for {subscriber_id}, cancelling workflow"
                )
                cancel_automation_workflow(automation_rule_id, subscriber_id)
                return {"status": "goal_achieved"}

        # ── DISPATCH BY STEP TYPE ──────────────────────────────────────────
        step_type = step.get("step_type", "email")  # legacy default

        logger.info(
            f"Executing step {step_id} (type={step_type}, order={step.get('step_order')}) "
            f"for subscriber {subscriber_id} in workflow {workflow_instance_id}"
        )

        if step_type in EMAIL_STEP_TYPES:
            # Smart-send-time wrapper: if enabled and not yet processed, defer
            # to optimize_send_time which will compute ideal hour and reschedule
            # this same execute_automation_step task at that time.
            smart = step.get("smart_send_time") or {}
            if smart.get("enabled") and not (trigger_data or {}).get(
                "_smart_send_resolved"
            ):
                from tasks.automation.automation_advanced_tasks import (
                    optimize_send_time,
                )

                optimize_send_time.delay(
                    automation_rule_id=automation_rule_id,
                    step_id=step_id,
                    subscriber_id=subscriber_id,
                    workflow_instance_id=workflow_instance_id,
                    trigger_data={**(trigger_data or {}), "_smart_send_resolved": True},
                )
                # Mark this execution as deferred-to-smart-send so it doesn't
                # double-count toward completion.
                executions_collection.update_one(
                    {
                        "automation_step_id": step_id,
                        "subscriber_id": subscriber_id,
                        "workflow_instance_id": workflow_instance_id,
                        "status": "running",
                    },
                    {
                        "$set": {
                            "status": "deferred_smart_send",
                            "updated_at": datetime.utcnow(),
                        }
                    },
                )
                return {"status": "deferred_smart_send"}

            return _handle_email_step(
                rule=rule,
                step=step,
                subscriber=subscriber,
                automation_rule_id=automation_rule_id,
                step_id=step_id,
                subscriber_id=subscriber_id,
                workflow_instance_id=workflow_instance_id,
                trigger_data=trigger_data or {},
            )

        if step_type in PASSTHROUGH_STEP_TYPES:
            return _handle_delay_step(
                rule=rule,
                step=step,
                automation_rule_id=automation_rule_id,
                step_id=step_id,
                subscriber_id=subscriber_id,
                workflow_instance_id=workflow_instance_id,
                trigger_data=trigger_data or {},
            )

        if step_type in ADVANCED_STEP_TYPES:
            return _dispatch_advanced_step(
                step_type=step_type,
                rule=rule,
                step=step,
                automation_rule_id=automation_rule_id,
                step_id=step_id,
                subscriber_id=subscriber_id,
                workflow_instance_id=workflow_instance_id,
                trigger_data=trigger_data or {},
            )

        logger.error(f"Unknown step_type '{step_type}' for step {step_id}")
        _mark_step_failed(
            executions_collection,
            step_id,
            subscriber_id,
            f"unknown_step_type:{step_type}",
        )
        return {"status": "unknown_step_type", "step_type": step_type}

    except Exception as exc:
        logger.error(f"Error executing automation step {step_id}: {exc}", exc_info=True)

        # Retry / skip / cancel decision
        try:
            if self.request.retries >= self.max_retries:
                _mark_step_failed(
                    executions_collection, step_id, subscriber_id, str(exc)
                )
                if rule and rule.get("skip_step_on_failure", False):
                    logger.info("Max retries reached; skipping step and continuing")
                    if step:
                        _schedule_next_step(
                            rule=rule,
                            current_step=step,
                            automation_rule_id=automation_rule_id,
                            subscriber_id=subscriber_id,
                            workflow_instance_id=workflow_instance_id,
                            trigger_data=(trigger_data or {}),
                        )
                else:
                    logger.error("Max retries reached; cancelling workflow")
                    cancel_automation_workflow(automation_rule_id, subscriber_id)
                    if rule and rule.get("notify_on_failure", True):
                        _send_failure_notification(
                            automation_rule_id, subscriber_id, str(exc)
                        )
                return {"status": "failed_after_max_retries", "error": str(exc)}
        except Exception as inner:
            logger.error(f"Error in retry/cancel branch: {inner}", exc_info=True)

        raise self.retry(exc=exc)


# =============================================================================
# STEP HANDLERS
# =============================================================================


def _handle_email_step(
    *,
    rule: dict,
    step: dict,
    subscriber: dict,
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    workflow_instance_id: str,
    trigger_data: dict,
) -> dict:
    """Send the email associated with this step, then schedule the next step."""
    templates_collection = get_sync_templates_collection()
    executions_collection = get_sync_automation_executions_collection()

    template_id = step.get("email_template_id")
    if not template_id:
        logger.error(f"Email step {step_id} has no email_template_id")
        _mark_step_failed(
            executions_collection, step_id, subscriber_id, "missing_template_id"
        )
        return {"status": "missing_template_id"}

    template = templates_collection.find_one({"_id": ObjectId(template_id)})
    if not template:
        logger.error(f"Template not found: {template_id}")
        _mark_step_failed(
            executions_collection, step_id, subscriber_id, "template_not_found"
        )
        return {"status": "template_not_found"}

    email_config_data = rule.get("email_config", {})
    final_subject = step.get("subject_line") or template.get("subject", "")

    email_config = {
        "from_email": email_config_data.get("sender_email"),
        "from_name": email_config_data.get("sender_name"),
        "reply_to": email_config_data.get("reply_to"),
        "subject": final_subject,
    }

    # Dispatch the actual send
    from tasks.automation.automation_email_tasks import send_automation_email

    result = send_automation_email.delay(
        subscriber_id=subscriber_id,
        template_id=str(template["_id"]),
        automation_rule_id=automation_rule_id,
        step_id=step_id,
        workflow_instance_id=workflow_instance_id,
        email_config=email_config,
        field_map=step.get("field_map", {}),
        fallback_values=step.get("fallback_values", {}),
    )

    # Update execution record
    executions_collection.update_one(
        {
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id,
            "workflow_instance_id": workflow_instance_id,
            "status": "running",
        },
        {
            "$set": {
                "status": "sent",
                "executed_at": datetime.utcnow(),
                "email_task_id": result.id,
                "updated_at": datetime.utcnow(),
            }
        },
    )

    # Increment workflow counters
    _mark_step_completed(workflow_instance_id, was_email=True)

    # Schedule next step in the chain
    next_scheduled = _schedule_next_step(
        rule=rule,
        current_step=step,
        automation_rule_id=automation_rule_id,
        subscriber_id=subscriber_id,
        workflow_instance_id=workflow_instance_id,
        trigger_data=trigger_data,
    )

    if not next_scheduled:
        _mark_workflow_completed(workflow_instance_id)

    logger.info(f"Email step {step_id} dispatched (task {result.id})")

    return {
        "status": "success",
        "step_type": "email",
        "step_id": step_id,
        "email_task_id": result.id,
        "next_step_scheduled": next_scheduled,
    }


def _handle_delay_step(
    *,
    rule: dict,
    step: dict,
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    workflow_instance_id: str,
    trigger_data: dict,
) -> dict:
    """
    Delay step is a no-op — its delay_hours is already baked into the ETA
    that scheduled this execution. Just record completion and schedule next.
    """
    executions_collection = get_sync_automation_executions_collection()

    executions_collection.update_one(
        {
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id,
            "workflow_instance_id": workflow_instance_id,
            "status": "running",
        },
        {
            "$set": {
                "status": "completed",
                "executed_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
        },
    )

    _mark_step_completed(workflow_instance_id, was_email=False)

    next_scheduled = _schedule_next_step(
        rule=rule,
        current_step=step,
        automation_rule_id=automation_rule_id,
        subscriber_id=subscriber_id,
        workflow_instance_id=workflow_instance_id,
        trigger_data=trigger_data,
    )

    if not next_scheduled:
        _mark_workflow_completed(workflow_instance_id)

    return {
        "status": "success",
        "step_type": "delay",
        "next_step_scheduled": next_scheduled,
    }


def _dispatch_advanced_step(
    *,
    step_type: str,
    rule: dict,
    step: dict,
    automation_rule_id: str,
    step_id: str,
    subscriber_id: str,
    workflow_instance_id: str,
    trigger_data: dict,
) -> dict:
    """
    Hand off to the matching task in automation_advanced_tasks.

    The advanced handler is responsible for:
      - performing its own logic (evaluation, send, wait, etc.)
      - calling _mark_step_completed when it terminates
      - calling _schedule_next_step (for sequential advanced steps) or
        _schedule_specific_next_steps (for branched conditional steps)

    We pass workflow_instance_id explicitly to every advanced task.
    """
    executions_collection = get_sync_automation_executions_collection()

    # Update execution to indicate hand-off; advanced task will finalize status
    executions_collection.update_one(
        {
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id,
            "workflow_instance_id": workflow_instance_id,
            "status": "running",
        },
        {"$set": {"status": "in_advanced_handler", "updated_at": datetime.utcnow()}},
    )

    if step_type == "condition":
        from tasks.automation.automation_advanced_tasks import execute_conditional_step

        execute_conditional_step.delay(
            automation_rule_id=automation_rule_id,
            step_id=step_id,
            subscriber_id=subscriber_id,
            workflow_instance_id=workflow_instance_id,
            trigger_data=trigger_data,
        )
    elif step_type == "ab_split":
        from tasks.automation.automation_advanced_tasks import execute_ab_test_step

        execute_ab_test_step.delay(
            automation_rule_id=automation_rule_id,
            step_id=step_id,
            subscriber_id=subscriber_id,
            workflow_instance_id=workflow_instance_id,
            trigger_data=trigger_data,
        )
    elif step_type == "wait_for_event":
        from tasks.automation.automation_advanced_tasks import wait_for_event_step

        wait_for_event_step.delay(
            automation_rule_id=automation_rule_id,
            step_id=step_id,
            subscriber_id=subscriber_id,
            workflow_instance_id=workflow_instance_id,
            trigger_data=trigger_data,
        )
    elif step_type == "send_webhook":
        from tasks.automation.automation_advanced_tasks import send_webhook_step

        send_webhook_step.delay(
            automation_rule_id=automation_rule_id,
            step_id=step_id,
            subscriber_id=subscriber_id,
            workflow_instance_id=workflow_instance_id,
            trigger_data=trigger_data,
        )
    elif step_type == "update_field":
        from tasks.automation.automation_advanced_tasks import update_field_step

        update_field_step.delay(
            automation_rule_id=automation_rule_id,
            step_id=step_id,
            subscriber_id=subscriber_id,
            workflow_instance_id=workflow_instance_id,
            trigger_data=trigger_data,
        )
    elif step_type == "goal_check":
        from tasks.automation.automation_advanced_tasks import goal_check_step

        goal_check_step.delay(
            automation_rule_id=automation_rule_id,
            step_id=step_id,
            subscriber_id=subscriber_id,
            workflow_instance_id=workflow_instance_id,
            trigger_data=trigger_data,
        )
    else:
        logger.error(f"Advanced step_type '{step_type}' has no dispatch")
        _mark_step_failed(
            executions_collection,
            step_id,
            subscriber_id,
            f"no_dispatch_for:{step_type}",
        )
        return {"status": "no_dispatch", "step_type": step_type}

    return {"status": "dispatched_to_advanced", "step_type": step_type}


# =============================================================================
# CHAINED STEP SCHEDULING
# =============================================================================


def _schedule_step_execution(
    *,
    automation_rule_id: str,
    step: dict,
    subscriber_id: str,
    workflow_instance_id: str,
    trigger_data: dict,
    eta_utc: datetime,
    timezone_name: str,
) -> str:
    """
    Insert a 'scheduled' execution record and dispatch execute_automation_step
    with the given ETA. Returns the Celery task_id.
    """
    executions_collection = get_sync_automation_executions_collection()

    step_id = str(step["_id"])

    result = execute_automation_step.apply_async(
        args=[
            automation_rule_id,
            step_id,
            subscriber_id,
            workflow_instance_id,
            trigger_data,
        ],
        eta=eta_utc,
    )

    executions_collection.insert_one(
        {
            "_id": ObjectId(),
            "workflow_instance_id": workflow_instance_id,
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id,
            "task_id": result.id,
            "scheduled_at": datetime.utcnow(),
            "scheduled_for": eta_utc,
            "timezone": timezone_name,
            "status": "scheduled",
            "step_order": step.get("step_order"),
            "step_type": step.get("step_type", "email"),
            "trigger_data": trigger_data,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
    )

    return result.id


def _schedule_next_step(
    *,
    rule: dict,
    current_step: dict,
    automation_rule_id: str,
    subscriber_id: str,
    workflow_instance_id: str,
    trigger_data: dict,
) -> bool:
    """
    Schedule the next sequential step (step_order + 1) if one exists.
    Used by all linear step types (email, delay, ab_split, wait_for_event,
    send_webhook, update_field, goal_check).

    Conditional steps DO NOT call this — they call _schedule_specific_next_steps
    with the chosen branch's step IDs.

    Returns True if a next step was scheduled, False if the workflow has
    reached its end.
    """
    steps_collection = get_sync_automation_steps_collection()

    next_step = steps_collection.find_one(
        {
            "automation_rule_id": automation_rule_id,
            "step_order": current_step.get("step_order", 0) + 1,
        }
    )

    if not next_step:
        logger.info(
            f"No next step after order {current_step.get('step_order')} "
            f"in workflow {workflow_instance_id}"
        )
        return False

    # Resolve timezone for next step's ETA
    subscribers_collection = get_sync_subscribers_collection()
    subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
    tz = _resolve_subscriber_timezone(rule, subscriber or {})
    current_time = datetime.now(tz)

    eta_utc = _compute_step_eta(rule, current_time, next_step.get("delay_hours", 0))

    _schedule_step_execution(
        automation_rule_id=automation_rule_id,
        step=next_step,
        subscriber_id=subscriber_id,
        workflow_instance_id=workflow_instance_id,
        trigger_data=trigger_data,
        eta_utc=eta_utc,
        timezone_name=str(tz),
    )

    logger.info(
        f"Scheduled next step {next_step['_id']} (order={next_step['step_order']}) "
        f"at {eta_utc.isoformat()} for workflow {workflow_instance_id}"
    )
    return True


def schedule_specific_next_steps(
    *,
    rule: dict,
    automation_rule_id: str,
    subscriber_id: str,
    workflow_instance_id: str,
    trigger_data: dict,
    next_step_ids: list,
) -> int:
    """
    Schedule a specific set of next steps by ID. Used by conditional branching
    where the next step depends on which branch was taken.

    Public (non-underscore) so the advanced module can import it.
    Returns count of steps scheduled.
    """
    if not next_step_ids:
        return 0

    steps_collection = get_sync_automation_steps_collection()
    subscribers_collection = get_sync_subscribers_collection()
    subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)}) or {}
    tz = _resolve_subscriber_timezone(rule, subscriber)
    current_time = datetime.now(tz)

    scheduled_count = 0
    for next_step_id in next_step_ids:
        try:
            next_step = steps_collection.find_one({"_id": ObjectId(next_step_id)})
            if not next_step:
                logger.warning(f"Branch target step not found: {next_step_id}")
                continue

            eta_utc = _compute_step_eta(
                rule, current_time, next_step.get("delay_hours", 0)
            )
            _schedule_step_execution(
                automation_rule_id=automation_rule_id,
                step=next_step,
                subscriber_id=subscriber_id,
                workflow_instance_id=workflow_instance_id,
                trigger_data=trigger_data,
                eta_utc=eta_utc,
                timezone_name=str(tz),
            )
            scheduled_count += 1
        except Exception as e:
            logger.error(
                f"Failed to schedule branch step {next_step_id}: {e}", exc_info=True
            )

    return scheduled_count


# =============================================================================
# WORKFLOW STATE HELPERS
# =============================================================================


def mark_step_completed(workflow_instance_id: str, *, was_email: bool) -> None:
    """
    Increment completed_steps (and emails_sent if was_email).

    Public alias for _mark_step_completed so advanced tasks can call it
    without touching a private name.
    """
    _mark_step_completed(workflow_instance_id, was_email=was_email)


def _mark_step_completed(workflow_instance_id: str, *, was_email: bool) -> None:
    workflow_instances_collection = get_sync_workflow_instances_collection()
    inc = {"completed_steps": 1}
    if was_email:
        inc["emails_sent"] = 1

    workflow_instances_collection.update_one(
        {"_id": ObjectId(workflow_instance_id)},
        {"$inc": inc, "$set": {"updated_at": datetime.utcnow()}},
    )


def mark_workflow_completed(workflow_instance_id: str) -> None:
    """Public alias for advanced tasks."""
    _mark_workflow_completed(workflow_instance_id)


def _mark_workflow_completed(workflow_instance_id: str) -> None:
    """
    Mark workflow as completed. Called when a step handler determines
    there's no next step in the chain. Idempotent (won't downgrade
    cancelled or failed states).
    """
    workflow_instances_collection = get_sync_workflow_instances_collection()
    result = workflow_instances_collection.update_one(
        {
            "_id": ObjectId(workflow_instance_id),
            "status": "in_progress",
        },
        {
            "$set": {
                "status": "completed",
                "completed_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
        },
    )
    if result.modified_count:
        logger.info(f"Workflow {workflow_instance_id} marked completed")


def _mark_step_failed(executions_collection, step_id, subscriber_id, reason):
    """Mark all running/scheduled executions for this step+subscriber as failed."""
    executions_collection.update_many(
        {
            "automation_step_id": step_id,
            "subscriber_id": subscriber_id,
            "status": {
                "$in": [
                    "scheduled",
                    "dispatched_by_poller",
                    "running",
                    "in_advanced_handler",
                ]
            },
        },
        {
            "$set": {
                "status": "failed",
                "error": reason,
                "failed_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
        },
    )


def mark_step_failed(executions_collection, step_id, subscriber_id, reason):
    """Public alias for backwards-compat with any external callers."""
    _mark_step_failed(executions_collection, step_id, subscriber_id, reason)


# =============================================================================
# CANCELLATION
# =============================================================================


@shared_task(name="tasks.cancel_automation_workflow")
def cancel_automation_workflow(automation_rule_id: str, subscriber_id: str):
    """
    Cancel an in-progress automation workflow for a (rule, subscriber).

    Two-pronged approach:
      1. Mark the workflow_instance status = "cancelled". Every step handler
         checks workflow status as its first action and no-ops if cancelled.
         This is the durable mechanism — it works even if Celery task
         revocation is unreliable.
      2. Best-effort revoke of any scheduled task IDs we know about.

    Note: with the new chained-scheduling model, only the *next* scheduled
    step exists in the queue at any given time, so revocation has limited
    surface area. The status-flip is the real cancellation mechanism.
    """
    try:
        executions_collection = get_sync_automation_executions_collection()
        workflow_instances_collection = get_sync_workflow_instances_collection()

        workflow = workflow_instances_collection.find_one(
            {
                "automation_rule_id": automation_rule_id,
                "subscriber_id": subscriber_id,
                "status": "in_progress",
            }
        )

        if not workflow:
            return {"status": "no_active_workflow"}

        workflow_instance_id = str(workflow["_id"])

        # Best-effort revoke
        scheduled_executions = list(
            executions_collection.find(
                {
                    "workflow_instance_id": workflow_instance_id,
                    "status": {"$in": ["scheduled", "dispatched_by_poller"]},
                }
            )
        )

        try:
            from celery_app import celery_app

            for execution in scheduled_executions:
                if execution.get("task_id"):
                    try:
                        celery_app.control.revoke(execution["task_id"], terminate=False)
                    except Exception as e:
                        logger.warning(
                            f"Failed to revoke task {execution['task_id']}: {e}"
                        )
        except Exception as e:
            logger.warning(f"Celery revoke unavailable: {e}")

        # Flip execution statuses
        result = executions_collection.update_many(
            {
                "workflow_instance_id": workflow_instance_id,
                "status": {
                    "$in": [
                        "scheduled",
                        "dispatched_by_poller",
                        "running",
                        "in_advanced_handler",
                    ]
                },
            },
            {
                "$set": {
                    "status": "cancelled",
                    "cancelled_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        # Flip workflow status
        workflow_instances_collection.update_one(
            {"_id": ObjectId(workflow_instance_id)},
            {
                "$set": {
                    "status": "cancelled",
                    "completed_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        logger.info(
            f"Cancelled workflow {workflow_instance_id}: "
            f"{result.modified_count} pending executions marked cancelled"
        )

        return {
            "status": "success",
            "workflow_instance_id": workflow_instance_id,
            "cancelled_count": result.modified_count,
        }

    except Exception as e:
        logger.error(f"Error cancelling automation workflow: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


# =============================================================================
# SCHEDULED-EXECUTION POLLER (safety net for missed ETAs)
# =============================================================================


@shared_task(name="tasks.process_scheduled_automations", bind=True)
def process_scheduled_automations(self):
    """
    Beat-driven safety net: claim any executions whose ETA has passed but
    that haven't been picked up (e.g., worker outage during ETA window).

    The atomic claim in execute_automation_step prevents double-execution
    when the regular ETA-driven task and this poller race.
    """
    try:
        executions_collection = get_sync_automation_executions_collection()

        now = datetime.utcnow()
        # Look back up to 24 hours for missed ETAs
        cutoff = now - timedelta(hours=24)

        pending = list(
            executions_collection.find(
                {
                    "status": "scheduled",
                    "scheduled_for": {"$lte": now, "$gte": cutoff},
                }
            ).limit(500)
        )

        if not pending:
            return {"processed": 0, "total_pending": 0}

        logger.info(f"Found {len(pending)} pending executions due for processing")

        processed = 0
        for execution in pending:
            try:
                claimed = executions_collection.find_one_and_update(
                    {"_id": execution["_id"], "status": "scheduled"},
                    {
                        "$set": {
                            "status": "dispatched_by_poller",
                            "dispatched_at": datetime.utcnow(),
                        }
                    },
                    return_document=False,
                )
                if claimed is None:
                    continue

                execute_automation_step.delay(
                    execution.get("automation_rule_id"),
                    execution.get("automation_step_id"),
                    execution.get("subscriber_id"),
                    execution.get("workflow_instance_id"),
                    execution.get("trigger_data", {}),
                )
                processed += 1
            except Exception as e:
                logger.error(
                    f"Failed to dispatch execution {execution.get('_id')}: {e}"
                )

        return {"processed": processed, "total_pending": len(pending)}

    except Exception as e:
        logger.error(f"process_scheduled_automations failed: {e}", exc_info=True)
        return {"error": str(e), "processed": 0}


# =============================================================================
# TIMEZONE / QUIET-HOURS / ETA HELPERS
# =============================================================================


def _resolve_subscriber_timezone(
    rule: dict, subscriber: dict
) -> "pytz.tzinfo.BaseTzInfo":
    """Resolve which timezone to use for a subscriber under a rule."""
    automation_tz_name = rule.get("timezone", "UTC")
    use_subscriber_tz = rule.get("use_subscriber_timezone", False)

    if use_subscriber_tz:
        candidate = (
            subscriber.get("standard_fields", {}).get("timezone")
            or subscriber.get("timezone")
            or automation_tz_name
        )
    else:
        candidate = automation_tz_name

    try:
        return pytz.timezone(candidate)
    except Exception:
        logger.warning(f"Invalid timezone {candidate}; falling back to UTC")
        return pytz.UTC


def _compute_step_eta(rule: dict, base_time: datetime, delay_hours: int) -> datetime:
    """
    Compute the UTC ETA for a step given a base time (timezone-aware) and
    a delay in hours. Respects quiet hours if configured on the rule.
    """
    eta_local = base_time + timedelta(hours=int(delay_hours or 0))

    respect_quiet_hours = rule.get("respect_quiet_hours", True)
    quiet_start = rule.get("quiet_hours_start", 22)
    quiet_end = rule.get("quiet_hours_end", 8)

    if respect_quiet_hours and (delay_hours or 0) > 0:
        hour = eta_local.hour
        if quiet_start > quiet_end:
            in_quiet = hour >= quiet_start or hour < quiet_end
        else:
            in_quiet = quiet_start <= hour < quiet_end

        if in_quiet:
            eta_local = eta_local.replace(
                hour=quiet_end, minute=0, second=0, microsecond=0
            )
            if eta_local < base_time:
                eta_local += timedelta(days=1)
            logger.info(f"Adjusted ETA for quiet hours to {eta_local}")

    return eta_local.astimezone(pytz.UTC).replace(tzinfo=None)


# =============================================================================
# MATCHING / EVALUATION HELPERS
# =============================================================================


def _subscriber_matches_rule_targets(subscriber: dict, rule: dict) -> bool:
    """
    Check if a subscriber satisfies a rule's target_segments and target_lists.

    target_segments are evaluated DYNAMICALLY against each segment's stored
    criteria — never against the static (and often empty) subscriber.segments[]
    array.
    """
    target_segments = rule.get("target_segments", []) or []
    target_lists = rule.get("target_lists", []) or []

    # No targets → match everyone active
    if not target_segments and not target_lists:
        return True

    # Segment match: subscriber must satisfy at least one target segment's criteria
    if target_segments:
        segments_collection = get_sync_segments_collection()
        any_match = False
        for seg_id in target_segments:
            try:
                segment = segments_collection.find_one({"_id": ObjectId(str(seg_id))})
                if not segment:
                    continue
                criteria = segment.get("criteria", {})
                if _subscriber_matches_segment_criteria(subscriber, criteria):
                    any_match = True
                    break
            except Exception as e:
                logger.warning(f"Segment lookup failed for {seg_id}: {e}")
        if not any_match:
            return False

    # List match: subscriber's lists[] must intersect target_lists
    if target_lists:
        subscriber_lists = subscriber.get("lists") or []
        if not subscriber_lists:
            legacy = subscriber.get("list")
            subscriber_lists = [legacy] if legacy else []
        target_lists_str = [str(x) for x in target_lists]
        subscriber_lists_str = [str(x) for x in subscriber_lists]
        if not any(x in subscriber_lists_str for x in target_lists_str):
            return False

    return True


def _subscriber_matches_segment_criteria(subscriber: Dict, criteria: Dict) -> bool:
    """
    Evaluate whether a subscriber satisfies a segment's stored criteria.

    Supported schema (AND of conditions):
        {
          "conditions": [
            {"field": "standard.country", "operator": "equals", "value": "US"},
            {"field": "custom.plan",      "operator": "contains", "value": "pro"}
          ]
        }

    Operators:
      equals/eq, not_equals/ne/neq, contains, not_contains,
      starts_with/startswith, ends_with/endswith,
      greater_than/gt, less_than/lt,
      exists, not_exists

    No criteria → matches everyone.
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

        # Resolve actual value
        if field_path == "email":
            actual = subscriber.get("email", "")
        elif field_path.startswith("standard."):
            actual = subscriber.get("standard_fields", {}).get(
                field_path[len("standard.") :], ""
            )
        elif field_path.startswith("custom."):
            actual = subscriber.get("custom_fields", {}).get(
                field_path[len("custom.") :], ""
            )
        else:
            actual = subscriber.get(field_path, "")

        # Existence operators don't compare values
        if operator == "exists":
            if actual in (None, "", []):
                return False
            continue
        if operator == "not_exists":
            if actual not in (None, "", []):
                return False
            continue

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
        # Unknown operators pass through

    return True


# Public alias used by advanced tasks for segment_match conditional checks
def subscriber_matches_segment_criteria(subscriber: Dict, criteria: Dict) -> bool:
    return _subscriber_matches_segment_criteria(subscriber, criteria)


def evaluate_trigger_conditions(
    conditions: Dict,
    subscriber: Dict,
    trigger_data: Optional[Dict] = None,
) -> bool:
    """Evaluate whether subscriber meets trigger conditions."""
    if not conditions:
        return True

    try:
        # Status-related top-level conditions
        if "status" in conditions and subscriber.get("status") != conditions["status"]:
            return False

        # Custom field conditions (supports MongoDB-style range operators)
        custom_conditions = conditions.get("custom_fields", {})
        subscriber_custom = subscriber.get("custom_fields", {})

        for field, expected_value in custom_conditions.items():
            actual_value = subscriber_custom.get(field)

            if isinstance(expected_value, dict):
                if "$gte" in expected_value and not (
                    actual_value is not None and actual_value >= expected_value["$gte"]
                ):
                    return False
                if "$lte" in expected_value and not (
                    actual_value is not None and actual_value <= expected_value["$lte"]
                ):
                    return False
            else:
                if actual_value != expected_value:
                    return False

        # Standard field conditions
        standard_conditions = conditions.get("standard_fields", {})
        subscriber_standard = subscriber.get("standard_fields", {})
        for field, expected_value in standard_conditions.items():
            if subscriber_standard.get(field) != expected_value:
                return False

        # Trigger data conditions
        if trigger_data:
            trigger_conditions = conditions.get("trigger_data", {})
            for field, expected_value in trigger_conditions.items():
                if trigger_data.get(field) != expected_value:
                    return False

        return True

    except Exception as e:
        logger.error(f"Error evaluating trigger conditions: {e}", exc_info=True)
        return False


def check_subscriber_matches_rule(subscriber_id: str, rule: Dict) -> bool:
    """Public helper: re-evaluate subscriber eligibility against a rule."""
    try:
        subscribers_collection = get_sync_subscribers_collection()
        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})

        if not subscriber:
            return False
        if subscriber.get("status") != "active":
            return False

        return _subscriber_matches_rule_targets(subscriber, rule)
    except Exception as e:
        logger.error(f"check_subscriber_matches_rule error: {e}", exc_info=True)
        return False


# =============================================================================
# GOAL ACHIEVEMENT CHECK (used by execute_automation_step pre-check)
# =============================================================================


def check_if_goal_achieved(automation_rule_id, subscriber_id, goal_config):
    """Check if automation goal has been achieved within the tracking window."""
    if not goal_config:
        return False

    from database import get_sync_email_events_collection

    events_collection = get_sync_email_events_collection()
    goal_type = goal_config.get("goal_type")
    tracking_window_days = goal_config.get("tracking_window_days", 30)
    start_date = datetime.utcnow() - timedelta(days=tracking_window_days)

    if goal_type == "purchase":
        return (
            events_collection.find_one(
                {
                    "subscriber_id": subscriber_id,
                    "event_type": "purchase",
                    "automation_rule_id": automation_rule_id,
                    "timestamp": {"$gte": start_date},
                }
            )
            is not None
        )

    if goal_type == "click":
        return (
            events_collection.find_one(
                {
                    "subscriber_id": subscriber_id,
                    "event_type": "click",
                    "automation_rule_id": automation_rule_id,
                    "timestamp": {"$gte": start_date},
                }
            )
            is not None
        )

    if goal_type == "open":
        return (
            events_collection.find_one(
                {
                    "subscriber_id": subscriber_id,
                    "event_type": "open",
                    "automation_rule_id": automation_rule_id,
                    "timestamp": {"$gte": start_date},
                }
            )
            is not None
        )

    if goal_type in ("signup", "download", "custom"):
        return (
            events_collection.find_one(
                {
                    "subscriber_id": subscriber_id,
                    "event_type": goal_type,
                    "automation_rule_id": automation_rule_id,
                    "timestamp": {"$gte": start_date},
                }
            )
            is not None
        )

    return False


def _send_failure_notification(automation_rule_id, subscriber_id, error_message):
    """Send failure notification to admin (placeholder; wire to your alerting)."""
    logger.error(
        f"ADMIN ALERT: Automation {automation_rule_id} failed for "
        f"subscriber {subscriber_id}: {error_message}"
    )


# =============================================================================
# BEAT-DRIVEN TRIGGER CHECKERS
# =============================================================================


@shared_task(name="tasks.check_welcome_automations", bind=True)
def check_welcome_automations(self):
    """Find new subscribers and trigger welcome automations."""
    try:
        subscribers_collection = get_sync_subscribers_collection()
        rules_collection = get_sync_automation_rules_collection()
        executions_collection = get_sync_automation_executions_collection()

        welcome_rules = list(
            rules_collection.find(
                {
                    "trigger": "welcome",
                    "status": "active",
                }
            )
        )

        if not welcome_rules:
            return {"message": "No active welcome automations", "triggered": 0}

        ten_minutes_ago = datetime.utcnow() - timedelta(minutes=10)
        new_subscribers = list(
            subscribers_collection.find(
                {
                    "created_at": {"$gte": ten_minutes_ago},
                    "status": "active",
                }
            )
        )

        if not new_subscribers:
            return {"message": "No new subscribers", "triggered": 0}

        triggered = 0
        for subscriber in new_subscribers:
            sub_id = str(subscriber["_id"])
            for rule in welcome_rules:
                rule_id = str(rule["_id"])
                already = executions_collection.find_one(
                    {
                        "automation_rule_id": rule_id,
                        "subscriber_id": sub_id,
                    }
                )
                if already:
                    continue

                process_automation_trigger.delay(
                    "welcome",
                    sub_id,
                    {
                        "subscriber_email": subscriber.get("email"),
                    },
                )
                triggered += 1

        return {"message": "Welcome automations triggered", "triggered": triggered}

    except Exception as e:
        logger.error(f"check_welcome_automations failed: {e}", exc_info=True)
        return {"error": str(e), "triggered": 0}


@shared_task(name="tasks.check_daily_birthdays", bind=True)
def check_daily_birthdays(self):
    """Find subscribers with birthdays today and trigger birthday automations."""
    try:
        subscribers_collection = get_sync_subscribers_collection()
        rules_collection = get_sync_automation_rules_collection()

        birthday_rules = list(
            rules_collection.find(
                {
                    "trigger": "birthday",
                    "status": "active",
                }
            )
        )
        if not birthday_rules:
            return {"message": "No active birthday automations", "triggered": 0}

        today = datetime.utcnow()
        birthday_subscribers = list(
            subscribers_collection.find(
                {
                    "status": "active",
                    "$or": [
                        {
                            "standard_fields.birthday": {
                                "$regex": f"-{today.month:02d}-{today.day:02d}$"
                            }
                        },
                        {
                            "custom_fields.birthday": {
                                "$regex": f"-{today.month:02d}-{today.day:02d}$"
                            }
                        },
                    ],
                }
            )
        )

        triggered = 0
        for subscriber in birthday_subscribers:
            sub_id = str(subscriber["_id"])
            process_automation_trigger.delay(
                "birthday",
                sub_id,
                {
                    "subscriber_email": subscriber.get("email"),
                    "today": today.strftime("%Y-%m-%d"),
                },
            )
            triggered += 1

        return {"message": "Birthday automations triggered", "triggered": triggered}

    except Exception as e:
        logger.error(f"check_daily_birthdays failed: {e}", exc_info=True)
        return {"error": str(e), "triggered": 0}


@shared_task(name="tasks.check_abandoned_cart_automations", bind=True)
def check_abandoned_cart_automations(self):
    """Find recent abandoned-cart events and trigger automations."""
    try:
        from database import get_sync_email_events_collection

        events_collection = get_sync_email_events_collection()
        rules_collection = get_sync_automation_rules_collection()
        executions_collection = get_sync_automation_executions_collection()

        cart_rules = list(
            rules_collection.find(
                {
                    "trigger": "abandoned_cart",
                    "status": "active",
                }
            )
        )
        if not cart_rules:
            return {"message": "No abandoned cart automations", "triggered": 0}

        # Default abandonment window 1 hour; configurable per rule
        triggered = 0
        for rule in cart_rules:
            window_minutes = rule.get("trigger_conditions", {}).get(
                "abandonment_window_minutes", 60
            )
            cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)

            cart_events = list(
                events_collection.find(
                    {
                        "event_type": "cart_abandoned",
                        "timestamp": {"$gte": cutoff},
                        "automation_processed": {"$ne": True},
                    }
                )
            )

            for event in cart_events:
                subscriber_id = event.get("subscriber_id")
                if not subscriber_id:
                    continue

                process_automation_trigger.delay(
                    "abandoned_cart",
                    subscriber_id,
                    {
                        "cart_id": event.get("cart_id"),
                        "cart_value": event.get("cart_value"),
                    },
                )

                events_collection.update_one(
                    {"_id": event["_id"]},
                    {"$set": {"automation_processed": True}},
                )
                triggered += 1

        return {
            "message": "Abandoned cart automations triggered",
            "triggered": triggered,
        }

    except Exception as e:
        logger.error(f"check_abandoned_cart_automations failed: {e}", exc_info=True)
        return {"error": str(e), "triggered": 0}


@shared_task(name="tasks.check_inactive_subscriber_automations", bind=True)
def check_inactive_subscriber_automations(self):
    """Find subscribers inactive past a threshold and trigger re-engagement."""
    try:
        from database import get_sync_email_logs_collection

        subscribers_collection = get_sync_subscribers_collection()
        rules_collection = get_sync_automation_rules_collection()
        email_logs_collection = get_sync_email_logs_collection()
        executions_collection = get_sync_automation_executions_collection()

        inactive_rules = list(
            rules_collection.find(
                {
                    "trigger": "inactive",
                    "status": "active",
                }
            )
        )
        if not inactive_rules:
            return {"message": "No inactive automations", "triggered": 0}

        triggered = 0
        for rule in inactive_rules:
            inactive_days = rule.get("trigger_conditions", {}).get("inactive_days", 30)
            cutoff = datetime.utcnow() - timedelta(days=inactive_days)

            recently_engaged = email_logs_collection.distinct(
                "subscriber_id",
                {
                    "created_at": {"$gte": cutoff},
                    "latest_status": {"$in": ["opened", "clicked"]},
                },
            )

            all_active = list(
                subscribers_collection.find({"status": "active"}, {"_id": 1})
            )
            inactive_ids = [
                str(sub["_id"])
                for sub in all_active
                if str(sub["_id"]) not in recently_engaged
            ]

            for subscriber_id in inactive_ids:
                already = executions_collection.find_one(
                    {
                        "automation_rule_id": str(rule["_id"]),
                        "subscriber_id": subscriber_id,
                        "started_at": {"$gte": cutoff},
                    }
                )
                if already:
                    continue

                process_automation_trigger.delay(
                    "inactive",
                    subscriber_id,
                    {
                        "inactive_days": inactive_days,
                    },
                )
                triggered += 1

        return {"message": "Inactive automations triggered", "triggered": triggered}

    except Exception as e:
        logger.error(
            f"check_inactive_subscriber_automations failed: {e}", exc_info=True
        )
        return {"error": str(e), "triggered": 0}
