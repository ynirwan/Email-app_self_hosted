from celery import Celery
import logging
from datetime import timedelta
import os

logger = logging.getLogger(__name__)

from core.config import settings
from tasks.task_config import task_settings

celery_app = Celery(
    "email_campaign_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_ignore_result=True,
    task_store_errors_even_if_ignored=True,
    broker_connection_retry_on_startup=True,
    timezone='UTC',
    enable_utc=True,
    imports=(
        'tasks.campaign.email_campaign_tasks',
        'tasks.automation_tasks',
        'tasks.ses_webhook_tasks',
        'tasks.analytics_tasks',
        'tasks.cleanup_tasks',
        'tasks.suppression_tasks',
    )
)

celery_app.conf.beat_schedule = {
    'check-scheduled-campaigns': {
        'task': 'tasks.campaign.email_campaign_tasks.check_scheduled_campaigns',
        'schedule': timedelta(minutes=1),
        'options': {'queue': 'campaigns', 'priority': 8}
    },
}

from celery.signals import worker_ready
@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    logger.info(f"✅ Celery worker ready: {sender.hostname if sender else 'unknown'}")
