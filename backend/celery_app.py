from celery import Celery
from celery.signals import (
    task_failure, task_success, task_retry, task_prerun, task_postrun,
    worker_ready, worker_shutdown, after_setup_logger, worker_init
)
from celery.schedules import crontab
import os
import logging
from datetime import timedelta
from typing import Dict, Any

logger = logging.getLogger(__name__)

# ============================================
# CONFIGURATION IMPORT
# ============================================

from core.config import settings

import importlib.util as _ilu
import os as _os
_spec = _ilu.spec_from_file_location(
    "task_config",
    _os.path.join(_os.path.dirname(__file__), "tasks", "task_config.py"),
)
_task_config_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_task_config_mod)
task_settings = _task_config_mod.task_settings


# ============================================
# CREATE CELERY APP
# ============================================

celery_app = Celery(
    "email_campaign_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        # Core email campaign tasks (always included)
        "tasks.campaign.email_campaign_tasks",
    #    "tasks.startup_recovery",
    ]
)

logger.info("✅ Celery app created")


# ============================================
# INCLUDE PRODUCTION TASKS
# ============================================

# Try to include production tasks if available
production_tasks = [
    "tasks.automation_tasks",
    "tasks.ses_webhook_tasks",
    "tasks.analytics_tasks",
    "tasks.cleanup_tasks",
    "tasks.suppression_tasks",
    "tasks.campaign.resource_manager",
    "tasks.campaign.rate_limiter",
    "tasks.campaign.dlq_manager",
    "tasks.campaign.campaign_control",
    "tasks.campaign.metrics_collector",
    "tasks.campaign.health_monitor",
    "tasks.campaign.template_cache",
    "tasks.campaign.audit_logger",
    "tasks.campaign.provider_manager",
]

included_tasks = []
failed_tasks = []

for task_module in production_tasks:
    try:
        celery_app.conf.include.append(task_module)
        included_tasks.append(task_module)
    except Exception as e:
        failed_tasks.append((task_module, str(e)))

if included_tasks:
    logger.info(f"✅ Production tasks included: {', '.join(included_tasks)}")
if failed_tasks:
    logger.info(f"ℹ️  Tasks not available: {', '.join([t[0] for t in failed_tasks])}")


# ============================================
# CELERY CONFIGURATION
# ============================================

celery_app.conf.update(
    # ===== BASIC CONFIGURATION =====
    timezone='UTC',
    enable_utc=True,
    
    # ===== TASK CONFIGURATION =====
    task_acks_late=False,  # Acknowledge tasks early for better throughput
    task_reject_on_worker_lost=True,  # Reject tasks if worker is lost
    task_ignore_result=True,  # Don't store task results by default
    task_store_errors_even_if_ignored=True,  # But store errors for debugging
    task_track_started=True,  # Track when tasks start
    task_time_limit=3600,  # 1 hour hard limit
    task_soft_time_limit=3000,  # 50 minutes soft limit
    
    # ===== WORKER CONFIGURATION =====
    worker_prefetch_multiplier=max(1, task_settings.MAX_CONCURRENT_TASKS // 10),  # Optimize prefetch
    worker_max_tasks_per_child=task_settings.WORKER_MAX_TASKS_PER_CHILD,  # Prevent memory leaks
    worker_disable_rate_limits=False,  # Keep rate limits enabled
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s',
    worker_redirect_stdouts=True,
    worker_redirect_stdouts_level='INFO',
    
    # ===== BROKER CONFIGURATION =====
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
    broker_pool_limit=50,
    broker_heartbeat=30,
    broker_transport_options={
        'visibility_timeout': 3600,  # 1 hour
        'fanout_prefix': True,
        'fanout_patterns': True,
        'socket_keepalive': True,
        'socket_connect_timeout': 5,
    },
    
    # ===== RESULT BACKEND CONFIGURATION =====
    result_backend=settings.CELERY_RESULT_BACKEND,
    result_expires=3600,  # 1 hour
    result_compression='gzip',
    result_extended=True,
    
    # ===== SERIALIZATION =====
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    
    # ===== QUEUE CONFIGURATION =====
    task_default_queue='campaigns',
    task_default_exchange='campaigns',
    task_default_routing_key='campaigns',
    task_queue_max_priority=10,
    task_default_priority=5,
    
    # ===== MONITORING CONFIGURATION =====
    worker_send_task_events=True,
    task_send_sent_event=True,
    
    # ===== ROUTING CONFIGURATION =====
    task_routes={
        # ===== EMAIL CAMPAIGN TASKS =====
        'tasks.send_single_campaign_email': {'queue': 'campaigns', 'priority': 7},
        'tasks.send_campaign_batch': {'queue': 'campaigns', 'priority': 6},
        'tasks.start_campaign': {'queue': 'campaigns', 'priority': 8},
        'tasks.complete_campaign': {'queue': 'campaigns', 'priority': 5},
        'tasks.cancel_campaign': {'queue': 'campaigns', 'priority': 9},
        'tasks.check_scheduled_campaigns': {'queue': 'campaigns', 'priority': 8},
        
        # ===== CAMPAIGN MANAGEMENT =====
        'tasks.pause_campaign': {'queue': 'campaigns', 'priority': 9},
        'tasks.resume_campaign': {'queue': 'campaigns', 'priority': 8},
        'tasks.stop_campaign': {'queue': 'campaigns', 'priority': 9},
        
        # ===== RECOVERY TASKS =====
        'tasks.startup_recovery': {'queue': 'recovery', 'priority': 10},
        'tasks.startup_recovery_only': {'queue': 'recovery', 'priority': 10},
        'tasks.recover_failed_campaign': {'queue': 'recovery', 'priority': 8},
        
        # ===== AUTOMATION TASKS =====
        'tasks.execute_automation_step': {'queue': 'automation', 'priority': 6},
        'tasks.process_automation_trigger': {'queue': 'automation', 'priority': 7},
        'tasks.cleanup_automation_executions': {'queue': 'automation', 'priority': 2},
        'tasks.process_scheduled_automations': {'queue': 'automation', 'priority': 5},
        
        # ✅ NEW: Automation trigger checkers
        'tasks.check_welcome_automations': {'queue': 'automation', 'priority': 7},
        'tasks.check_birthday_automations': {'queue': 'automation', 'priority': 6},
        'tasks.check_abandoned_cart_automations': {'queue': 'automation', 'priority': 6},
        'tasks.check_inactive_subscriber_automations': {'queue': 'automation', 'priority': 5},
        'tasks.check_daily_birthdays': {'queue': 'automation', 'priority': 8},
        'tasks.check_inactive_subscribers': {'queue': 'automation', 'priority': 7},
        'tasks.detect_at_risk_subscribers': {'queue': 'automation', 'priority': 6},
        'tasks.cleanup_old_events': {'queue': 'automation', 'priority': 3},
        
        # ===== SES/WEBHOOK TASKS =====
        'tasks.process_ses_events_batch': {'queue': 'ses_events', 'priority': 6},
        'tasks.process_critical_ses_events': {'queue': 'ses_critical', 'priority': 9},
        'tasks.process_webhook_event': {'queue': 'webhooks', 'priority': 7},
        'tasks.process_bounce_notification': {'queue': 'webhooks', 'priority': 8},
        'tasks.process_complaint_notification': {'queue': 'webhooks', 'priority': 8},
        
        # ===== SUBSCRIBER TASKS =====
        'tasks.bulk_subscriber_import': {'queue': 'subscribers', 'priority': 5},
        'tasks.process_subscriber_batch': {'queue': 'subscribers', 'priority': 5},
        'tasks.validate_subscribers': {'queue': 'subscribers', 'priority': 4},
        'tasks.import_subscribers_from_file': {'queue': 'subscribers', 'priority': 5},
        
        # ===== SUPPRESSION TASKS =====
        'tasks.process_bounce': {'queue': 'suppressions', 'priority': 8},
        'tasks.process_complaint': {'queue': 'suppressions', 'priority': 8},
        'tasks.sync_suppressions': {'queue': 'suppressions', 'priority': 3},
        'tasks.cleanup_old_suppressions': {'queue': 'suppressions', 'priority': 2},
        
        # ===== DEAD LETTER QUEUE =====
        'tasks.handle_failed_email': {'queue': 'dlq', 'priority': 7},
        'tasks.process_dlq_retries': {'queue': 'dlq', 'priority': 6},
        'tasks.cleanup_old_dlq_entries': {'queue': 'dlq', 'priority': 1},
        
        # ===== MONITORING & HEALTH =====
        'tasks.collect_all_metrics': {'queue': 'monitoring', 'priority': 3},
        'tasks.run_health_checks': {'queue': 'monitoring', 'priority': 4},
        'tasks.check_provider_health': {'queue': 'monitoring', 'priority': 4},
        'tasks.monitor_system_resources': {'queue': 'monitoring', 'priority': 3},
        
        # ===== ANALYTICS & REPORTING =====
        'tasks.calculate_campaign_analytics': {'queue': 'analytics', 'priority': 4},
        'tasks.update_real_time_stats': {'queue': 'analytics', 'priority': 5},
        'tasks.aggregate_analytics': {'queue': 'analytics', 'priority': 3},
        'tasks.generate_dlq_analytics': {'queue': 'analytics', 'priority': 2},
        'tasks.generate_daily_compliance_report': {'queue': 'analytics', 'priority': 3},
        'tasks.aggregate_real_time_analytics': {'queue': 'analytics', 'priority': 4},
        
        # ===== TEMPLATE MANAGEMENT =====
        'tasks.preload_template_cache': {'queue': 'templates', 'priority': 5},
        'tasks.cleanup_template_cache': {'queue': 'templates', 'priority': 1},
        'tasks.validate_template': {'queue': 'templates', 'priority': 4},
        
        # ===== CLEANUP TASKS =====
        'tasks.cleanup_old_metrics': {'queue': 'cleanup', 'priority': 1},
        'tasks.cleanup_audit_logs': {'queue': 'cleanup', 'priority': 1},
        'tasks.cleanup_health_reports': {'queue': 'cleanup', 'priority': 1},
        'tasks.cleanup_campaign_flags': {'queue': 'cleanup', 'priority': 2},
        'tasks.cleanup_inactive_subscribers': {'queue': 'cleanup', 'priority': 1},
        'tasks.cleanup_old_jobs': {'queue': 'cleanup', 'priority': 1},
    },
    
    # ===== TASK ANNOTATIONS =====
    task_annotations={
        # Global rate limit
        '*': {
            'rate_limit': '1000/s',
        },
        
        # Email sending tasks
        'tasks.send_single_campaign_email': {
            'rate_limit': '500/s',
            'max_retries': task_settings.MAX_EMAIL_RETRIES,
            'default_retry_delay': 60,
            'retry_backoff': True,
            'retry_backoff_max': 600,
            'retry_jitter': True,
        },
        'tasks.send_campaign_batch': {
            'rate_limit': '10/s',
            'max_retries': 3,
            'default_retry_delay': 120,
        },
        
        # Automation tasks
        'tasks.execute_automation_step': {
            'rate_limit': '100/s',
            'max_retries': 3,
            'default_retry_delay': 300,
        },
        
        # ✅ NEW: Automation trigger checkers rate limits
        'tasks.check_welcome_automations': {
            'rate_limit': '10/m',
            'max_retries': 2,
        },
        'tasks.check_birthday_automations': {
            'rate_limit': '5/h',
            'max_retries': 2,
        },
        
        # Webhook processing
        'tasks.process_ses_events_batch': {
            'rate_limit': '50/s',
            'max_retries': 5,
            'default_retry_delay': 10,
        },
        'tasks.process_critical_ses_events': {
            'rate_limit': '100/s',
            'max_retries': 5,
            'default_retry_delay': 5,
        },
        
        # Subscriber import
        'tasks.bulk_subscriber_import': {
            'rate_limit': '10/m',
            'time_limit': 3600,
            'soft_time_limit': 3000,
            'max_retries': 2,
        },
        
        # DLQ processing
        'tasks.process_dlq_retries': {
            'rate_limit': '20/s',
            'max_retries': 3,
        },
    },
)

logger.info("✅ Celery configuration applied")


# ============================================
# BEAT SCHEDULE (PERIODIC TASKS)
# ============================================

beat_schedule = {}

if task_settings.ENABLE_METRICS_COLLECTION:
    beat_schedule.update({
        # ===== MONITORING TASKS =====
        'collect-system-metrics': {
            'task': 'tasks.collect_all_metrics',
            'schedule': timedelta(seconds=task_settings.METRICS_COLLECTION_INTERVAL_SECONDS),
            'options': {'queue': 'monitoring', 'priority': 3}
        },
        'health-check': {
            'task': 'tasks.run_health_checks',
            'schedule': timedelta(seconds=task_settings.HEALTH_CHECK_INTERVAL_SECONDS),
            'options': {'queue': 'monitoring', 'priority': 4}
        },
        'provider-health-check': {
            'task': 'tasks.check_provider_health',
            'schedule': timedelta(seconds=task_settings.PROVIDER_HEALTH_CHECK_INTERVAL_SECONDS),
            'options': {'queue': 'monitoring', 'priority': 4}
        },
        'monitor-system-resources': {
            'task': 'tasks.monitor_system_resources',
            'schedule': timedelta(minutes=1),
            'options': {'queue': 'monitoring', 'priority': 3}
        },
    })

if task_settings.ENABLE_DLQ:
    beat_schedule.update({
        # ===== DLQ PROCESSING =====
        'process-dlq-retries': {
            'task': 'tasks.process_dlq_retries',
            'schedule': timedelta(minutes=task_settings.DLQ_RETRY_DELAY_MINUTES),
            'options': {'queue': 'dlq', 'priority': 6}
        },
        'cleanup-old-dlq-entries': {
            'task': 'tasks.cleanup_old_dlq_entries',
            'schedule': timedelta(days=1),
            'options': {'queue': 'cleanup', 'priority': 1}
        },
    })

# Always include cleanup tasks
beat_schedule.update({
    # ===== CLEANUP TASKS =====
    'cleanup-old-metrics': {
        'task': 'tasks.cleanup_old_metrics',
        'schedule': timedelta(hours=6),
        'options': {'queue': 'cleanup', 'priority': 1}
    },
    'cleanup-template-cache': {
        'task': 'tasks.cleanup_template_cache',
        'schedule': timedelta(hours=4),
        'options': {'queue': 'cleanup', 'priority': 1}
    },
    'cleanup-health-reports': {
        'task': 'tasks.cleanup_health_reports',
        'schedule': timedelta(hours=12),
        'options': {'queue': 'cleanup', 'priority': 1}
    },
    'cleanup-campaign-flags': {
        'task': 'tasks.cleanup_campaign_flags',
        'schedule': timedelta(hours=1),
        'options': {'queue': 'cleanup', 'priority': 2}
    },
    'cleanup-old-jobs': {
        'task': 'tasks.cleanup_old_jobs',
        'schedule': timedelta(days=1),
        'options': {'queue': 'cleanup', 'priority': 1}
    },
})

# Analytics tasks
beat_schedule.update({
    # ===== ANALYTICS & REPORTING =====
    'aggregate-real-time-analytics': {
        'task': 'tasks.aggregate_real_time_analytics',
        'schedule': timedelta(minutes=5),
        'options': {'queue': 'analytics', 'priority': 4}
    },
    'generate-dlq-analytics': {
        'task': 'tasks.generate_dlq_analytics',
        'schedule': timedelta(hours=4),
        'options': {'queue': 'analytics', 'priority': 2}
    },
})

# ✅ UPDATED: Automation processing with trigger checkers
beat_schedule.update({
    # ===== AUTOMATION PROCESSING =====
    'process-scheduled-automations': {
        'task': 'tasks.process_scheduled_automations',
        'schedule': timedelta(minutes=5),
        'options': {'queue': 'automation', 'priority': 5}
    },
    'cleanup-automation-executions': {
        'task': 'tasks.cleanup_automation_executions',
        'schedule': timedelta(days=7),
        'options': {'queue': 'automation', 'priority': 1}
    },
    
    # ✅ NEW: Welcome automation trigger checker
    'check-welcome-automations': {
        'task': 'tasks.check_welcome_automations',
        'schedule': crontab(minute='*/5'),  # Every 5 minutes
        'options': {'queue': 'automation', 'priority': 7}
    },
    
    # ✅ NEW: Birthday automation checker (multiple times for timezone coverage)
    'check-birthdays-midnight-utc': {
        'task': 'tasks.check_daily_birthdays',
        'schedule': crontab(hour=0, minute=0),  # Midnight UTC
        'options': {'queue': 'automation', 'priority': 8}
    },
    'check-birthdays-morning-utc': {
        'task': 'tasks.check_daily_birthdays',
        'schedule': crontab(hour=6, minute=0),  # 6 AM UTC
        'options': {'queue': 'automation', 'priority': 8}
    },
    'check-birthdays-noon-utc': {
        'task': 'tasks.check_daily_birthdays',
        'schedule': crontab(hour=12, minute=0),  # Noon UTC
        'options': {'queue': 'automation', 'priority': 8}
    },
    
    # ✅ NEW: Abandoned cart checker
    'check-abandoned-cart-automations': {
        'task': 'tasks.check_abandoned_cart_automations',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
        'options': {'queue': 'automation', 'priority': 6}
    },
    
    # ✅ NEW: Inactive subscriber checker
    'check-inactive-subscribers': {
        'task': 'tasks.check_inactive_subscriber_automations',
        'schedule': crontab(hour=3, minute=0),  # Daily at 3 AM
        'options': {'queue': 'automation', 'priority': 7}
    },
    
    # ✅ NEW: At-risk subscriber detector
    'detect-at-risk-subscribers': {
        'task': 'tasks.detect_at_risk_subscribers',
        'schedule': crontab(hour=4, minute=0),  # Daily at 4 AM
        'options': {'queue': 'automation', 'priority': 6}
    },
    
    # ✅ NEW: Event cleanup
    'cleanup-old-events': {
        'task': 'tasks.cleanup_old_events',
        'schedule': crontab(day_of_month=1, hour=2, minute=0),  # 1st of month at 2 AM
        'options': {'queue': 'automation', 'priority': 3}
    },
})

beat_schedule.update({
    'check-scheduled-campaigns': {
        'task': 'tasks.check_scheduled_campaigns',
        'schedule': timedelta(minutes=1),
        'options': {'queue': 'campaigns', 'priority': 8}
    },
})

# Subscriber cleanup
beat_schedule.update({
    # ===== SUBSCRIBER MANAGEMENT =====
    'cleanup-inactive-subscribers': {
        'task': 'tasks.cleanup_inactive_subscribers',
        'schedule': timedelta(days=30),
        'options': {'queue': 'cleanup', 'priority': 1}
    },
})

if task_settings.ENABLE_COMPLIANCE_TRACKING:
    beat_schedule['daily-compliance-report'] = {
        'task': 'tasks.generate_daily_compliance_report',
        'schedule': timedelta(days=1),
        'options': {'queue': 'analytics', 'priority': 3}
    }

if task_settings.ENABLE_AUDIT_LOGGING:
    beat_schedule['cleanup-audit-logs'] = {
        'task': 'tasks.cleanup_audit_logs',
        'schedule': timedelta(days=7),
        'options': {'queue': 'cleanup', 'priority': 1}
    }

# Apply beat schedule
celery_app.conf.beat_schedule = beat_schedule
logger.info(f"✅ Beat schedule configured with {len(beat_schedule)} periodic tasks")


# ============================================
# SIGNAL HANDLERS
# ============================================

@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **extra):
    """Handle task startup - setup resources"""
    try:
        logger.debug(f"Task starting: {task.name if task else 'unknown'} [{task_id}]")
    except Exception as e:
        logger.error(f"Task prerun handler error: {e}")


@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, 
                         retval=None, state=None, **extra):
    """Handle task completion - cleanup resources"""
    try:
        logger.debug(f"Task completed: {task.name if task else 'unknown'} [{task_id}] - State: {state}")
    except Exception as e:
        logger.error(f"Task postrun handler error: {e}")


@task_success.connect
def task_success_handler(sender=None, result=None, **kwargs):
    """Handle successful task completion"""
    try:
        if task_settings.ENABLE_METRICS_COLLECTION:
            # Track successful task completion
            pass
    except Exception as e:
        logger.error(f"Task success handler error: {e}")


@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, traceback=None, 
                        einfo=None, args=None, kwargs=None, **extra):
    """Handle task failures"""
    try:
        task_name = sender.__name__ if sender else 'unknown'
        error_msg = str(exception) if exception else 'unknown'
        
        logger.error(f"❌ Task failure: {task_name} [{task_id}] - {error_msg}")
        
        if task_settings.ENABLE_AUDIT_LOGGING:
            try:
                from tasks.audit_logger import log_system_event, AuditEventType, AuditSeverity
                log_system_event(
                    AuditEventType.SYSTEM_ERROR,
                    {
                        "task_failure": True,
                        "task_name": task_name,
                        "task_id": task_id,
                        "error": error_msg,
                        "args": str(args) if args else None,
                        "kwargs": str(kwargs) if kwargs else None
                    },
                    AuditSeverity.ERROR
                )
            except Exception as e:
                logger.debug(f"Audit logging failed: {e}")
        
    except Exception as e:
        logger.error(f"Task failure handler error: {e}")


@task_retry.connect
def task_retry_handler(sender=None, task_id=None, reason=None, einfo=None, **kwargs):
    """Handle task retries"""
    try:
        task_name = sender.__name__ if sender else 'unknown'
        logger.warning(f"⚠️  Task retry: {task_name} [{task_id}] - Reason: {reason}")
    except Exception as e:
        logger.error(f"Task retry handler error: {e}")


@worker_init.connect
def worker_init_handler(sender=None, **kwargs):
    """Handle worker initialization"""
    try:
        logger.info(f"🔧 Worker initializing: {sender.hostname if sender else 'unknown'}")
    except Exception as e:
        logger.error(f"Worker init handler error: {e}")


@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    """Worker ready event handler"""
    try:
        hostname = sender.hostname if sender else 'unknown'
        logger.info(f"✅ Celery worker ready: {hostname}")
        
        # Preload template cache if available
        try:
            from tasks.template_cache import preload_template_cache
            preload_template_cache.delay()
            logger.info("🚀 Template cache preloading initiated")
        except ImportError:
            logger.debug("Template caching not available")
        
        if task_settings.ENABLE_AUDIT_LOGGING:
            try:
                from tasks.audit_logger import log_system_event, AuditEventType
                log_system_event(
                    AuditEventType.SYSTEM_STARTUP,
                    {"worker_ready": True, "hostname": hostname}
                )
            except Exception as e:
                logger.debug(f"Audit logging failed: {e}")
        
    except Exception as e:
        logger.error(f"Worker ready handler error: {e}")


if task_settings.ENABLE_GRACEFUL_SHUTDOWN:
    @worker_shutdown.connect
    def worker_shutdown_handler(sender=None, **kwargs):
        """Handle worker shutdown gracefully"""
        try:
            hostname = sender.hostname if sender else 'unknown'
            logger.info(f"🛑 Celery worker shutting down gracefully: {hostname}")
            
            if task_settings.ENABLE_AUDIT_LOGGING:
                try:
                    from tasks.audit_logger import log_system_event, AuditEventType
                    log_system_event(
                        AuditEventType.SYSTEM_SHUTDOWN,
                        {"worker_shutdown": True, "hostname": hostname}
                    )
                except Exception as e:
                    logger.debug(f"Audit logging failed: {e}")
            
        except Exception as e:
            logger.error(f"Worker shutdown handler error: {e}")


@after_setup_logger.connect
def setup_celery_logger(logger_instance, *args, **kwargs):
    try:
        from logging.handlers import RotatingFileHandler
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "var", "log")
        os.makedirs(log_dir, exist_ok=True)

        log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        celery_file_handler = RotatingFileHandler(
            os.path.join(log_dir, "celery.log"),
            maxBytes=10 * 1024 * 1024,
            backupCount=5
        )
        celery_file_handler.setFormatter(log_format)
        logger_instance.addHandler(celery_file_handler)

        celery_error_handler = RotatingFileHandler(
            os.path.join(log_dir, "celery_error.log"),
            maxBytes=10 * 1024 * 1024,
            backupCount=5
        )
        celery_error_handler.setLevel(logging.ERROR)
        celery_error_handler.setFormatter(log_format)
        logger_instance.addHandler(celery_error_handler)

        logger_instance.info(f"Celery logger configured - files in {log_dir}")
    except Exception as e:
        logger.error(f"Celery logger setup error: {e}")


# ============================================
# CONFIGURATION VERIFICATION
# ============================================

def verify_celery_config() -> Dict[str, Any]:
    """Verify Celery configuration and return status"""
    try:
        config_info = {
            "broker": celery_app.conf.broker_url,
            "backend": celery_app.conf.result_backend,
            "timezone": celery_app.conf.timezone,
            "task_routes_count": len(celery_app.conf.task_routes),
            "beat_schedule_count": len(celery_app.conf.beat_schedule) if hasattr(celery_app.conf, 'beat_schedule') else 0,
            "included_tasks": len(celery_app.conf.include),
            "production_features": 'tasks.resource_manager' in celery_app.conf.include,
            "queues": [
                "campaigns", "recovery", "automation", "webhooks", "subscribers",
                "suppressions", "dlq", "monitoring", "analytics", "templates",
                "cleanup", "ses_events", "ses_critical"
            ]
        }
        
        logger.info("🔧 Celery Configuration Verification:")
        logger.info(f"   • Broker: {config_info['broker']}")
        logger.info(f"   • Backend: {config_info['backend']}")
        logger.info(f"   • Timezone: {config_info['timezone']}")
        logger.info(f"   • Task routes: {config_info['task_routes_count']} configured")
        logger.info(f"   • Beat schedule: {config_info['beat_schedule_count']} periodic tasks")
        logger.info(f"   • Included tasks: {config_info['included_tasks']} modules")
        logger.info(f"   • Production features: {'Enabled' if config_info['production_features'] else 'Basic'}")
        logger.info(f"   • Queues: {', '.join(config_info['queues'])}")
        
        return config_info
        
    except Exception as e:
        logger.error(f"❌ Celery config verification failed: {e}")
        return {"error": str(e)}


def get_celery_status() -> Dict[str, Any]:
    """Get current Celery worker status"""
    try:
        inspect = celery_app.control.inspect()
        
        status = {
            "active_tasks": inspect.active() or {},
            "scheduled_tasks": inspect.scheduled() or {},
            "registered_tasks": inspect.registered() or {},
            "stats": inspect.stats() or {},
        }
        
        # Count total tasks
        total_active = sum(len(tasks) for tasks in status['active_tasks'].values())
        total_scheduled = sum(len(tasks) for tasks in status['scheduled_tasks'].values())
        
        status['summary'] = {
            "total_active": total_active,
            "total_scheduled": total_scheduled,
            "workers_online": len(status['stats'])
        }
        
        return status
        
    except Exception as e:
        logger.error(f"Failed to get Celery status: {e}")
        return {"error": str(e)}


# ============================================
# EXPORTS
# ============================================

__all__ = [
    'celery_app',
    'verify_celery_config',
    'get_celery_status',
]


# ============================================
# AUTO-VERIFICATION
# ============================================

# Run verification on import
verify_celery_config()

logger.info("✅ Celery app configuration complete")