# backend/tasks/__init__.py - COMPLETE TASK REGISTRATION
"""
Unified task registration for all Celery tasks
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

__all__ = []
if FILE_FIRST_AVAILABLE:
    __all__.append('simple_file_recovery')


print("✅ All task modules loaded successfully")
