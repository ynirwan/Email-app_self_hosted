# backend/tasks/automation/__init__.py
"""
Automation task package.

Importing this module registers all automation Celery tasks via the
@shared_task decorators in the submodules.

Module structure:
  automation_tasks.py            — entry points + linear step handlers
                                   (process_automation_trigger,
                                    start_automation_workflow,
                                    execute_automation_step,
                                    cancel_automation_workflow,
                                    process_scheduled_automations,
                                    beat-driven trigger checkers)

  automation_advanced_tasks.py   — branched / advanced step handlers
                                   (execute_conditional_step,
                                    execute_ab_test_step,
                                    wait_for_event_step,
                                    send_webhook_step,
                                    update_field_step,
                                    goal_check_step,
                                    optimize_send_time,
                                    check_goal_achievement,
                                    analyze_optimal_send_times)

  automation_email_tasks.py      — send_automation_email
                                   (the actual SMTP/SES send path)

Order matters here: automation_tasks imports advanced_tasks and email_tasks
via lazy imports inside functions to avoid circular import issues at module
load time. We just import all three modules so Celery's auto-discovery picks
up every @shared_task.
"""

from . import automation_tasks  # noqa: F401
from . import automation_advanced_tasks  # noqa: F401
from . import automation_email_tasks  # noqa: F401

__all__ = [
    "automation_tasks",
    "automation_advanced_tasks",
    "automation_email_tasks",
]