# backend/tasks/__init__.py
"""
Unified task registration for all Celery tasks.

Importing this package registers every @shared_task with Celery via side
effect of the submodule imports below. Failures to import any individual
module are logged but don't crash worker startup — the rest of the app
should still come up so observability and admin endpoints remain available.

IMPORTANT: We deliberately import from `.automation` (the package), NOT from
the legacy top-level `automation_tasks.py` and `automation_advanced_tasks.py`.
Those legacy files registered tasks under identical names as the new package
modules, causing non-deterministic task-routing depending on import order.
The legacy files should be deleted from the codebase.
"""

import logging

logger = logging.getLogger(__name__)

# ── CAMPAIGN TASKS ──────────────────────────────────────────────────────────
try:
    from .campaign import email_campaign_tasks  # noqa: F401
    logger.info("✅ Loaded email_campaign_tasks")
except ImportError as e:
    logger.error(f"❌ Failed to load email_campaign_tasks: {e}")

# ── AUTOMATION TASKS ────────────────────────────────────────────────────────
# This single import registers:
#   - automation_tasks.py          (entry/dispatch/linear handlers)
#   - automation_advanced_tasks.py (branched/advanced handlers)
#   - automation_email_tasks.py    (send_automation_email)
AUTOMATION_AVAILABLE = False
try:
    from . import automation  # noqa: F401
    AUTOMATION_AVAILABLE = True
    logger.info("✅ Loaded automation tasks package")
except ImportError as e:
    logger.error(f"❌ Failed to load automation tasks: {e}")

# ── SES WEBHOOKS ────────────────────────────────────────────────────────────
try:
    from . import ses_webhook_tasks  # noqa: F401
    logger.info("✅ Loaded ses_webhook_tasks")
except ImportError as e:
    logger.error(f"❌ Failed to load ses_webhook_tasks: {e}")

# ── ANALYTICS ───────────────────────────────────────────────────────────────
try:
    from . import analytics_tasks  # noqa: F401
    logger.info("✅ Loaded analytics_tasks")
except ImportError as e:
    logger.error(f"❌ Failed to load analytics_tasks: {e}")

# ── CLEANUP ─────────────────────────────────────────────────────────────────
try:
    from . import cleanup_tasks  # noqa: F401
    logger.info("✅ Loaded cleanup_tasks")
except ImportError as e:
    logger.error(f"❌ Failed to load cleanup_tasks: {e}")

# ── SUPPRESSIONS ────────────────────────────────────────────────────────────
try:
    from . import suppression_tasks  # noqa: F401
    logger.info("✅ Loaded suppression_tasks")
except ImportError as e:
    logger.error(f"❌ Failed to load suppression_tasks: {e}")


# ── EXPORTS ────────────────────────────────────────────────────────────────
__all__ = []

if AUTOMATION_AVAILABLE:
    __all__.extend([
        # entry points
        "process_automation_trigger",
        "start_automation_workflow",
        "execute_automation_step",
        "cancel_automation_workflow",
        "process_scheduled_automations",
        # beat trigger checkers
        "check_welcome_automations",
        "check_daily_birthdays",
        "check_abandoned_cart_automations",
        "check_inactive_subscriber_automations",
        # advanced step handlers
        "execute_conditional_step",
        "execute_ab_test_step",
        "wait_for_event_step",
        "send_webhook_step",
        "update_field_step",
        "goal_check_step",
        "optimize_send_time",
        "check_goal_achievement",
        "analyze_optimal_send_times",
        # send path
        "send_automation_email",
    ])

# ── VERIFY (best-effort sanity check) ──────────────────────────────────────
if AUTOMATION_AVAILABLE:
    try:
        from .automation.automation_tasks import (  # noqa: F401
            process_automation_trigger,
            start_automation_workflow,
            execute_automation_step,
            cancel_automation_workflow,
            process_scheduled_automations,
            check_welcome_automations,
            check_daily_birthdays,
        )
        from .automation.automation_advanced_tasks import (  # noqa: F401
            execute_conditional_step,
            execute_ab_test_step,
            wait_for_event_step,
            send_webhook_step,
            update_field_step,
            goal_check_step,
        )
        from .automation.automation_email_tasks import send_automation_email  # noqa: F401
        logger.info("✅ Automation tasks verified and callable")
    except ImportError as e:
        logger.warning(f"⚠️  Automation task verification failed: {e}")

logger.info(f"📊 Task registration complete: {len(__all__)} tasks exported")