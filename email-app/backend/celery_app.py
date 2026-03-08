"""
Celery application for email marketing platform.
Uses external Redis for broker/backend (configured via .env).
"""
from celery import Celery
import logging
import os

logger = logging.getLogger(__name__)

# Load configuration
from core.config import settings

# Create Celery app
celery_app = Celery(
    "email_campaign_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Configure Celery
celery_app.conf.update(
    timezone='UTC',
    enable_utc=True,
    task_acks_late=False,
    task_reject_on_worker_lost=True,
    task_ignore_result=True,
    task_store_errors_even_if_ignored=True,
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3000,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    task_default_queue='campaigns',
)

# Auto-discover tasks from tasks package
celery_app.autodiscover_tasks(['tasks'], force=True)

logger.info("✅ Celery app configured with external Redis broker")
