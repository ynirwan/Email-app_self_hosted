# backend/tasks/__init__.py - COMPLETE TASK REGISTRATION
"""
Unified task registration for all Celery tasks
✅ UPDATED: Added automation trigger tasks
"""

# Import all task modules to register them with Celery
try:
    from .campaign import email_campaign_tasks
    print("✅ Loaded email_campaign_tasks")
except ImportError as e:
    print(f"❌ Failed to load email_campaign_tasks: {e}")

try:
    from . import startup_recovery
    print("✅ Loaded campaign_recovery")
except ImportError as e:
    print(f"❌ Failed to load campaign_recovery: {e}")

# ✅ NEW: Import automation tasks
try:
    from .automation import automation_tasks
    print("✅ Loaded automation_tasks")
    AUTOMATION_AVAILABLE = True
except ImportError as e:
    print(f"❌ Failed to load automation_tasks: {e}")
    AUTOMATION_AVAILABLE = False

try:
    from . import ses_webhook_tasks
    print("✅ Loaded ses_webhook_tasks")
except ImportError as e:
    print(f"❌ Failed to load ses_webhook_tasks: {e}")

try:
    from . import analytics_tasks
    print("✅ Loaded analytics_tasks")
except ImportError as e:
    print(f"❌ Failed to load analytics_tasks: {e}")

try:
    from . import cleanup_tasks
    print("✅ Loaded cleanup_tasks")
except ImportError as e:
    print(f"❌ Failed to load cleanup_tasks: {e}")

try:
    from . import suppression_tasks
    print("✅ Loaded suppression_tasks")
except ImportError as e:
    print(f"❌ Failed to load suppression_tasks: {e}")

# Add file-first recovery
try:
    from .simple_file_recovery import simple_file_recovery
    print("✅ Loaded simple_file_recovery")
    FILE_FIRST_AVAILABLE = True
except ImportError as e:
    print(f"❌ Failed to load simple_file_recovery: {e}")
    FILE_FIRST_AVAILABLE = False

# ✅ NEW: Build __all__ with available tasks
__all__ = []

if FILE_FIRST_AVAILABLE:
    __all__.append('simple_file_recovery')

if AUTOMATION_AVAILABLE:
    __all__.extend([
        'automation_tasks',
        'process_automation_trigger',
        'start_automation_workflow',
        'execute_automation_step',
        'cancel_automation_workflow',
        'process_scheduled_automations',
        'check_welcome_automations',
        'check_birthday_automations',
        'check_abandoned_cart_automations',
        'check_inactive_subscriber_automations',
        'check_daily_birthdays',
        'detect_at_risk_subscribers',
        'cleanup_old_events',
    ])

print("✅ All task modules loaded successfully")
print(f"📊 Registered tasks: {', '.join(__all__) if __all__ else 'None'}")

# ✅ NEW: Verify automation tasks are callable
if AUTOMATION_AVAILABLE:
    try:
        from .automation.automation_tasks import (
            check_welcome_automations,
            check_daily_birthdays,
            process_scheduled_automations
        )
        print("✅ Automation trigger tasks verified and callable")
    except ImportError as e:
        print(f"⚠️ Warning: Some automation tasks not available: {e}")


from .automation.automation_email_tasks import *        
