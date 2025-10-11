# backend/tasks/cleanup_tasks.py - FIXED VERSION
import logging
from datetime import datetime, timedelta
from celery_app import celery_app
from database_sync import get_sync_email_logs_collection, get_sync_campaigns_collection

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, queue="cleanup", name="tasks.cleanup_old_logs")
def cleanup_old_logs(self, days_old: int = 30):
    """Clean up old email logs"""
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        email_logs_collection = get_sync_email_logs_collection()
        
        result = email_logs_collection.delete_many({
            "last_attempted_at": {"$lt": cutoff_date}
        })
        
        logger.info(f"Cleaned up {result.deleted_count} old email logs")
        return {"deleted_count": result.deleted_count}
        
    except Exception as e:
        logger.exception("Cleanup error")
        raise

@celery_app.task(bind=True, queue="cleanup", name="tasks.cleanup_completed_campaigns")
def cleanup_completed_campaigns(self):
    """Clean up old completed campaigns"""
    try:
        campaigns_collection = get_sync_campaigns_collection()
        
        # Clean up completed campaigns older than 90 days
        cutoff_date = datetime.utcnow() - timedelta(days=90)
        
        result = campaigns_collection.delete_many({
            "status": "completed",
            "completed_at": {"$lt": cutoff_date}
        })
        
        logger.info(f"Cleaned up {result.deleted_count} old completed campaigns")
        return {"deleted_count": result.deleted_count}
        
    except Exception as e:
        logger.exception("Campaign cleanup error")
        raise

@celery_app.task(bind=True, queue="cleanup", name="tasks.cleanup_failed_campaigns")
def cleanup_failed_campaigns(self):
    """Clean up old failed campaigns"""
    try:
        campaigns_collection = get_sync_campaigns_collection()
        
        # Clean up failed campaigns older than 30 days
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        
        result = campaigns_collection.delete_many({
            "status": "failed",
            "$or": [
                {"failed_at": {"$lt": cutoff_date}},
                {"completed_at": {"$lt": cutoff_date}}
            ]
        })
        
        logger.info(f"Cleaned up {result.deleted_count} old failed campaigns")
        return {"deleted_count": result.deleted_count}
        
    except Exception as e:
        logger.exception("Failed campaign cleanup error")
        raise

