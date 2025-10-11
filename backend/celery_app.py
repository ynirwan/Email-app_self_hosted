# backend/celery_app.py - FIXED CELERY CONFIGURATION
"""
Production-ready Celery configuration with all optimizations
Compatible with all Celery versions - Fixed event handlers
"""
from celery import Celery
from celery.signals import task_failure, worker_ready, worker_shutdown, after_setup_logger
import os
import logging
from datetime import timedelta

# Import config safely
try:
    from config import settings, get_redis_key
    REDIS_URL = settings.REDIS_URL
    MAX_CONCURRENT_TASKS = getattr(settings, 'MAX_CONCURRENT_TASKS', 50)
    WORKER_MAX_TASKS_PER_CHILD = getattr(settings, 'WORKER_MAX_TASKS_PER_CHILD', 500)
    MAX_EMAIL_RETRIES = getattr(settings, 'MAX_EMAIL_RETRIES', 3)
    ENABLE_METRICS_COLLECTION = getattr(settings, 'ENABLE_METRICS_COLLECTION', True)
    ENABLE_AUDIT_LOGGING = getattr(settings, 'ENABLE_AUDIT_LOGGING', False)
    ENABLE_GRACEFUL_SHUTDOWN = getattr(settings, 'ENABLE_GRACEFUL_SHUTDOWN', True)
    METRICS_COLLECTION_INTERVAL_SECONDS = getattr(settings, 'METRICS_COLLECTION_INTERVAL_SECONDS', 60)
    HEALTH_CHECK_INTERVAL_SECONDS = getattr(settings, 'HEALTH_CHECK_INTERVAL_SECONDS', 30)
    PROVIDER_HEALTH_CHECK_INTERVAL_SECONDS = getattr(settings, 'PROVIDER_HEALTH_CHECK_INTERVAL_SECONDS', 300)
    ENABLE_COMPLIANCE_TRACKING = getattr(settings, 'ENABLE_COMPLIANCE_TRACKING', False)
    AUDIT_LOG_RETENTION_DAYS = getattr(settings, 'AUDIT_LOG_RETENTION_DAYS', 90)
except ImportError:
    # Fallback values if config not available
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    MAX_CONCURRENT_TASKS = 50
    WORKER_MAX_TASKS_PER_CHILD = 500
    MAX_EMAIL_RETRIES = 3
    ENABLE_METRICS_COLLECTION = True
    ENABLE_AUDIT_LOGGING = False
    ENABLE_GRACEFUL_SHUTDOWN = True
    METRICS_COLLECTION_INTERVAL_SECONDS = 60
    HEALTH_CHECK_INTERVAL_SECONDS = 30
    PROVIDER_HEALTH_CHECK_INTERVAL_SECONDS = 300
    ENABLE_COMPLIANCE_TRACKING = False
    AUDIT_LOG_RETENTION_DAYS = 90

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Celery app
celery_app = Celery(
    "email_campaign_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "tasks.email_campaign_tasks",
        "tasks.startup_recovery",  # Include your existing recovery task
    ]
)

# Try to include production tasks if available
try:
    celery_app.conf.include.extend([
        "tasks.resource_manager",
        "tasks.rate_limiter", 
        "tasks.dlq_manager",
        "tasks.campaign_control",
        "tasks.metrics_collector",
        "tasks.health_monitor",
        "tasks.template_cache",
        "tasks.audit_logger",
        "tasks.provider_manager",
    ])
    logger.info("✅ Production tasks included")
except Exception as e:
    logger.info(f"ℹ️  Production tasks not available: {e}")

# Production-optimized Celery configuration
celery_app.conf.update(
    # ===== BASIC CONFIGURATION =====
    timezone='UTC',
    enable_utc=True,
    
    # ===== TASK CONFIGURATION =====
    task_acks_late=False,  # Acknowledge tasks early for better throughput
    task_reject_on_worker_lost=True,  # Reject tasks if worker is lost
    task_ignore_result=True,  # Don't store task results by default
    task_store_errors_even_if_ignored=True,  # But store errors for debugging
    
    # ===== WORKER CONFIGURATION =====
    worker_prefetch_multiplier=max(1, MAX_CONCURRENT_TASKS // 10),  # Optimize prefetch
    worker_max_tasks_per_child=WORKER_MAX_TASKS_PER_CHILD,  # Prevent memory leaks
    worker_disable_rate_limits=False,  # Keep rate limits enabled
    worker_log_format='[%(asctime)s: %(levelname)s/%(processName)s] %(message)s',
    worker_task_log_format='[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s',
    
    # ===== BROKER CONFIGURATION =====
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
    broker_pool_limit=50,
    broker_heartbeat=30,
    broker_transport_options={
        'visibility_timeout': 3600,  # 1 hour
        'fanout_prefix': True,
        'fanout_patterns': True
    },
    
    # ===== RESULT BACKEND CONFIGURATION =====
    result_backend=None,  # Disable result backend for performance
    result_expires=3600,  # 1 hour
    
    # ===== SERIALIZATION =====
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    
    # ===== ROUTING CONFIGURATION =====
    task_routes={
        # High priority email tasks
        'tasks.send_single_campaign_email': {'queue': 'campaigns'},
        'tasks.send_campaign_batch': {'queue': 'campaigns'},
        'tasks.start_campaign': {'queue': 'campaigns'},
        
        # Your existing tasks
        'tasks.startup_recovery_only': {'queue': 'recovery'},
        
        # Campaign management (if available)
        'tasks.pause_campaign': {'queue': 'campaigns'},
        'tasks.resume_campaign': {'queue': 'campaigns'},
        'tasks.stop_campaign': {'queue': 'campaigns'},
        
        # Dead Letter Queue processing (if available)
        'tasks.handle_failed_email': {'queue': 'dlq'},
        'tasks.process_dlq_retries': {'queue': 'dlq'},
        
        # Monitoring and metrics (if available)
        'tasks.collect_all_metrics': {'queue': 'monitoring'},
        'tasks.run_health_checks': {'queue': 'monitoring'},
        'tasks.check_provider_health': {'queue': 'monitoring'},
        
        # Analytics and reporting (if available)
        'tasks.generate_dlq_analytics': {'queue': 'analytics'},
        'tasks.generate_daily_compliance_report': {'queue': 'analytics'},
        
        # Template management (if available)
        'tasks.preload_template_cache': {'queue': 'templates'},
        
        # Cleanup tasks (if available)
        'tasks.cleanup_old_metrics': {'queue': 'cleanup'},
        'tasks.cleanup_template_cache': {'queue': 'cleanup'},
        'tasks.cleanup_audit_logs': {'queue': 'cleanup'},
        'tasks.cleanup_old_dlq_entries': {'queue': 'cleanup'},
        'tasks.cleanup_health_reports': {'queue': 'cleanup'},
        'tasks.cleanup_campaign_flags': {'queue': 'cleanup'},
    },
    
    # ===== QUEUE CONFIGURATION =====
    task_default_queue='campaigns',
    task_default_exchange='campaigns',
    task_default_routing_key='campaigns',
    
    # Define queue priorities
    task_queue_max_priority=10,
    task_default_priority=5,
    
    # ===== MONITORING CONFIGURATION =====
    worker_send_task_events=True,
    task_send_sent_event=True,
    
    # ===== ERROR HANDLING =====
    task_annotation={
        '*': {
            'rate_limit': '1000/s',  # Global rate limit
        },
        'tasks.send_single_campaign_email': {
            'rate_limit': '500/s',  # Email sending rate limit
            'max_retries': MAX_EMAIL_RETRIES,
            'default_retry_delay': 60,
        },
        'tasks.send_campaign_batch': {
            'rate_limit': '10/s',  # Batch processing rate limit
            'max_retries': 3,
        }
    },
)

# ===== BEAT SCHEDULE (CONDITIONAL) =====
if ENABLE_METRICS_COLLECTION:
    beat_schedule = {
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
        
        # ===== DLQ PROCESSING =====
        'process-dlq-retries': {
            'task': 'tasks.process_dlq_retries',
            'schedule': timedelta(minutes=10),  # Every 10 minutes
            'options': {'queue': 'dlq', 'priority': 6}
        },
        
        # ===== CLEANUP TASKS =====
        'cleanup-old-metrics': {
            'task': 'tasks.cleanup_old_metrics',
            'schedule': timedelta(hours=6),  # Every 6 hours
            'options': {'queue': 'cleanup', 'priority': 1}
        },
        'cleanup-template-cache': {
            'task': 'tasks.cleanup_template_cache',
            'schedule': timedelta(hours=4),  # Every 4 hours
            'options': {'queue': 'cleanup', 'priority': 1}
        },
        'cleanup-health-reports': {
            'task': 'tasks.cleanup_health_reports',
            'schedule': timedelta(hours=12),  # Twice daily
            'options': {'queue': 'cleanup', 'priority': 1}
        },
        'cleanup-campaign-flags': {
            'task': 'tasks.cleanup_campaign_flags',
            'schedule': timedelta(hours=1),  # Every hour
            'options': {'queue': 'cleanup', 'priority': 2}
        },
        'cleanup-old-dlq-entries': {
            'task': 'tasks.cleanup_old_dlq_entries',
            'schedule': timedelta(days=1),  # Daily
            'options': {'queue': 'cleanup', 'priority': 1}
        },
        
        # ===== ANALYTICS & REPORTING =====
        'generate-dlq-analytics': {
            'task': 'tasks.generate_dlq_analytics',
            'schedule': timedelta(hours=4),  # Every 4 hours
            'options': {'queue': 'analytics', 'priority': 2}
        },
    }
    
    # Add compliance reporting if enabled
    if ENABLE_COMPLIANCE_TRACKING:
        beat_schedule['daily-compliance-report'] = {
            'task': 'tasks.generate_daily_compliance_report',
            'schedule': timedelta(days=1),  # Daily at midnight
            'options': {'queue': 'analytics', 'priority': 3}
        }
    
    # Add audit log cleanup if enabled
    if ENABLE_AUDIT_LOGGING:
        beat_schedule['cleanup-audit-logs'] = {
            'task': 'tasks.cleanup_audit_logs',
            'schedule': timedelta(days=7),  # Weekly
            'options': {'queue': 'cleanup', 'priority': 1}
        }
    
    celery_app.conf.beat_schedule = beat_schedule
    logger.info(f"✅ Beat schedule configured with {len(beat_schedule)} tasks")

# ===== EVENT HANDLERS (FIXED SYNTAX) =====

@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, traceback=None, einfo=None, **kwargs):
    """Handle task failures"""
    try:
        if ENABLE_AUDIT_LOGGING:
            try:
                from tasks.audit_logger import log_system_event, AuditEventType, AuditSeverity
                log_system_event(
                    AuditEventType.SYSTEM_STARTUP,  # Using available event type
                    {
                        "task_failure": True,
                        "task_name": sender.__name__ if sender else "unknown",
                        "task_id": task_id,
                        "error": str(exception) if exception else "unknown"
                    },
                    AuditSeverity.ERROR
                )
            except Exception as e:
                logger.debug(f"Audit logging failed: {e}")
        
        logger.error(f"Task failure: {sender.__name__ if sender else 'unknown'} [{task_id}] - {exception}")
        
    except Exception as e:
        logger.error(f"Task failure handler error: {e}")

@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    """Worker ready event handler"""
    try:
        # Preload template cache if available
        try:
            from tasks.template_cache import preload_template_cache
            preload_template_cache.delay()
            logger.info("🚀 Template cache preloading initiated")
        except ImportError:
            logger.info("🚀 Celery worker ready (template caching not available)")
        
    except Exception as e:
        logger.error(f"Worker ready handler error: {e}")

if ENABLE_GRACEFUL_SHUTDOWN:
    @worker_shutdown.connect
    def worker_shutdown_handler(sender=None, **kwargs):
        """Handle worker shutdown gracefully"""
        try:
            if ENABLE_AUDIT_LOGGING:
                try:
                    from tasks.audit_logger import log_system_event, AuditEventType
                    log_system_event(
                        AuditEventType.SYSTEM_SHUTDOWN,
                        {"worker_shutdown": True, "hostname": sender.hostname if sender else "unknown"}
                    )
                except:
                    pass
            
            logger.info("🛑 Celery worker shutting down gracefully")
            
        except Exception as e:
            logger.error(f"Worker shutdown handler error: {e}")

@after_setup_logger.connect
def setup_celery_logger(logger, *args, **kwargs):
    """Setup Celery logger configuration"""
    try:
        logger.info("✅ Celery logger configured")
        logger.info(f"📊 Configured queues: campaigns, recovery, dlq, monitoring, analytics, templates, cleanup")
        logger.info(f"⚡ Worker settings: {WORKER_MAX_TASKS_PER_CHILD} max tasks per child")
        logger.info(f"📈 Monitoring enabled: {ENABLE_METRICS_COLLECTION}")
        
    except Exception as e:
        logger.error(f"❌ Celery logger setup error: {e}")

# ===== CONFIGURATION VERIFICATION =====
def verify_celery_config():
    """Verify Celery configuration"""
    try:
        logger.info("🔧 Celery Configuration:")
        logger.info(f"   • Broker: {celery_app.conf.broker_url}")
        logger.info(f"   • Backend: {celery_app.conf.result_backend}")
        logger.info(f"   • Timezone: {celery_app.conf.timezone}")
        logger.info(f"   • Task routes: {len(celery_app.conf.task_routes)} configured")
        logger.info(f"   • Beat schedule: {'Enabled' if hasattr(celery_app.conf, 'beat_schedule') else 'Disabled'}")
        logger.info(f"   • Production features: {'Available' if 'tasks.resource_manager' in celery_app.conf.include else 'Basic'}")
        
        return True
    except Exception as e:
        logger.error(f"Celery config verification failed: {e}")
        return False

# Run verification
verify_celery_config()

# Export the celery app
__all__ = ['celery_app']
