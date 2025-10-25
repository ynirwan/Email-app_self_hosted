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

# Import config safely with fallbacks
try:
    from core.config import settings, get_redis_key
    REDIS_URL = settings.REDIS_URL
    MAX_CONCURRENT_TASKS = settings.MAX_CONCURRENT_TASKS
    WORKER_MAX_TASKS_PER_CHILD = settings.WORKER_MAX_TASKS_PER_CHILD
    MAX_EMAIL_RETRIES = settings.MAX_EMAIL_RETRIES
    ENABLE_METRICS_COLLECTION = settings.ENABLE_METRICS_COLLECTION
    ENABLE_AUDIT_LOGGING = settings.ENABLE_AUDIT_LOGGING
    ENABLE_GRACEFUL_SHUTDOWN = settings.ENABLE_GRACEFUL_SHUTDOWN
    METRICS_COLLECTION_INTERVAL_SECONDS = settings.METRICS_COLLECTION_INTERVAL_SECONDS
    HEALTH_CHECK_INTERVAL_SECONDS = settings.HEALTH_CHECK_INTERVAL_SECONDS
    PROVIDER_HEALTH_CHECK_INTERVAL_SECONDS = settings.PROVIDER_HEALTH_CHECK_INTERVAL_SECONDS
    ENABLE_COMPLIANCE_TRACKING = settings.ENABLE_COMPLIANCE_TRACKING
    AUDIT_LOG_RETENTION_DAYS = settings.AUDIT_LOG_RETENTION_DAYS
    ENABLE_DLQ = settings.ENABLE_DLQ
    DLQ_RETRY_DELAY_MINUTES = settings.DLQ_RETRY_DELAY_MINUTES
    logger.info("✅ Loaded settings from core.config")
except ImportError as e:
    logger.warning(f"⚠️  Could not import core.config: {e}, using fallback values")
    # Fallback values if config not available
    REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
    MAX_CONCURRENT_TASKS = 50
    WORKER_MAX_TASKS_PER_CHILD = 500
    MAX_EMAIL_RETRIES = 3
    ENABLE_METRICS_COLLECTION = True
    ENABLE_AUDIT_LOGGING = True
    ENABLE_GRACEFUL_SHUTDOWN = True
    METRICS_COLLECTION_INTERVAL_SECONDS = 60
    HEALTH_CHECK_INTERVAL_SECONDS = 30
    PROVIDER_HEALTH_CHECK_INTERVAL_SECONDS = 300
    ENABLE_COMPLIANCE_TRACKING = False
    AUDIT_LOG_RETENTION_DAYS = 90
    ENABLE_DLQ = True
    DLQ_RETRY_DELAY_MINUTES = 15


# ============================================
# CREATE CELERY APP
# ============================================

celery_app = Celery(
    "email_campaign_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        # Core email campaign tasks (always included)
        "tasks.email_campaign_tasks",
        "tasks.startup_recovery",
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
    "tasks.resource_manager",
    "tasks.rate_limiter",
    "tasks.dlq_manager",
    "tasks.campaign_control",
    "tasks.metrics_collector",
    "tasks.health_monitor",
    "tasks.template_cache",
    "tasks.audit_logger",
    "tasks.provider_manager",
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
    worker_prefetch_multiplier=max(1, MAX_CONCURRENT_TASKS // 10),  # Optimize prefetch
    worker_max_tasks_per_child=WORKER_MAX_TASKS_PER_CHILD,  # Prevent memory leaks
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
    result_backend=REDIS_URL,
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
            'max_retries': MAX_EMAIL_RETRIES,
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

if ENABLE_METRICS_COLLECTION:
    beat_schedule.update({
        # ===== MONITORING TASKS =====
        'collect-system-metrics': {
            'task': 'tasks.collect_all_metrics',
            'schedule': timedelta(seconds=METRICS_COLLECTION_INTERVAL_SECONDS),
            'options': {'queue': 'monitoring', 'priority': 3}
        },
        'health-check': {
            'task': 'tasks.run_health_checks',
            'schedule': timedelta(seconds=HEALTH_CHECK_INTERVAL_SECONDS),
            'options': {'queue': 'monitoring', 'priority': 4}
        },
        'provider-health-check': {
            'task': 'tasks.check_provider_health',
            'schedule': timedelta(seconds=PROVIDER_HEALTH_CHECK_INTERVAL_SECONDS),
            'options': {'queue': 'monitoring', 'priority': 4}
        },
        'monitor-system-resources': {
            'task': 'tasks.monitor_system_resources',
            'schedule': timedelta(minutes=1),
            'options': {'queue': 'monitoring', 'priority': 3}
        },
    })

if ENABLE_DLQ:
    beat_schedule.update({
        # ===== DLQ PROCESSING =====
        'process-dlq-retries': {
            'task': 'tasks.process_dlq_retries',
            'schedule': timedelta(minutes=DLQ_RETRY_DELAY_MINUTES),
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

# Automation processing
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
})



# Add to beat_schedule
celery_app.conf.beat_schedule = {
    
    # ⭐ Check birthdays daily at multiple times for different timezones
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

        # Clean old events monthly
    'cleanup-old-events': {
        'task': 'tasks.cleanup_old_events',
        'schedule': crontab(day_of_month=1, hour=2, minute=0),  # 1st of month at 2 AM
        'options': {'queue': 'automation', 'priority': 3}
    },
    
    'check-inactive-subscribers': {
        'task': 'tasks.check_inactive_subscribers',
        'schedule': crontab(hour=3, minute=0),
        'options': {'queue': 'automation', 'priority': 7}
    },
    
    # Detect at-risk subscribers daily at 4 AM
    'detect-at-risk-subscribers': {
        'task': 'tasks.detect_at_risk_subscribers',
        'schedule': crontab(hour=4, minute=0),
        'options': {'queue': 'automation', 'priority': 6}
    },

}




# Subscriber cleanup
beat_schedule.update({
    # ===== SUBSCRIBER MANAGEMENT =====
    'cleanup-inactive-subscribers': {
        'task': 'tasks.cleanup_inactive_subscribers',
        'schedule': timedelta(days=30),
        'options': {'queue': 'cleanup', 'priority': 1}
    },
})

if ENABLE_COMPLIANCE_TRACKING:
    beat_schedule['daily-compliance-report'] = {
        'task': 'tasks.generate_daily_compliance_report',
        'schedule': timedelta(days=1),
        'options': {'queue': 'analytics', 'priority': 3}
    }

if ENABLE_AUDIT_LOGGING:
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
        if ENABLE_METRICS_COLLECTION:
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
        
        if ENABLE_AUDIT_LOGGING:
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
        
        if ENABLE_AUDIT_LOGGING:
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


if ENABLE_GRACEFUL_SHUTDOWN:
    @worker_shutdown.connect
    def worker_shutdown_handler(sender=None, **kwargs):
        """Handle worker shutdown gracefully"""
        try:
            hostname = sender.hostname if sender else 'unknown'
            logger.info(f"🛑 Celery worker shutting down gracefully: {hostname}")
            
            if ENABLE_AUDIT_LOGGING:
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
    """Setup Celery logger configuration"""
    try:
        logger_instance.info("✅ Celery logger configured")
        logger_instance.info(f"📊 Configured queues: campaigns, recovery, automation, webhooks, subscribers, "
                           f"suppressions, dlq, monitoring, analytics, templates, cleanup, ses_events, ses_critical")
        logger_instance.info(f"⚡ Worker settings: {WORKER_MAX_TASKS_PER_CHILD} max tasks per child, "
                           f"{MAX_CONCURRENT_TASKS} concurrent tasks")
        logger_instance.info(f"📈 Monitoring enabled: {ENABLE_METRICS_COLLECTION}")
        logger_instance.info(f"📝 Audit logging enabled: {ENABLE_AUDIT_LOGGING}")
        
    except Exception as e:
        logger.error(f"❌ Celery logger setup error: {e}")


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
