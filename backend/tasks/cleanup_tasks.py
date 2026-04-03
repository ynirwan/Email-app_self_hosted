# backend/tasks/cleanup_tasks.py - FIXED VERSION
import logging
from datetime import datetime, timedelta
from celery_app import celery_app
from database import get_sync_email_logs_collection, get_sync_campaigns_collection

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


@celery_app.task(bind=True, queue="cleanup", name="tasks.cleanup_old_jobs")
def cleanup_old_jobs(self, days_old: int = 7):
    """Remove completed/expired background job records older than days_old days."""
    try:
        from database import get_sync_db
        db = get_sync_db()
        cutoff = datetime.utcnow() - timedelta(days=days_old)
        result = db["background_jobs"].delete_many({
            "status": {"$in": ["completed", "failed", "expired"]},
            "updated_at": {"$lt": cutoff}
        })
        logger.info(f"cleanup_old_jobs: removed {result.deleted_count} old job records")
        return {"deleted_count": result.deleted_count}
    except Exception as e:
        logger.error(f"cleanup_old_jobs failed: {e}")
        return {"error": str(e)}


@celery_app.task(bind=True, queue="cleanup", name="tasks.cleanup_inactive_subscribers")
def cleanup_inactive_subscribers(self, days_old: int = 365):
    """Archive subscriber records that have been unsubscribed/bounced for over a year."""
    try:
        from database import get_sync_subscribers_collection
        subscribers_collection = get_sync_subscribers_collection()
        cutoff = datetime.utcnow() - timedelta(days=days_old)
        result = subscribers_collection.update_many(
            {
                "status": {"$in": ["unsubscribed", "bounced", "complained"]},
                "updated_at": {"$lt": cutoff},
                "archived": {"$ne": True},
            },
            {"$set": {"archived": True, "archived_at": datetime.utcnow()}}
        )
        logger.info(f"cleanup_inactive_subscribers: archived {result.modified_count} subscribers")
        return {"archived_count": result.modified_count}
    except Exception as e:
        logger.error(f"cleanup_inactive_subscribers failed: {e}")
        return {"error": str(e)}


@celery_app.task(bind=True, queue="automation", name="tasks.cleanup_automation_executions")
def cleanup_automation_executions(self, days_old: int = 30):
    """Remove old automation execution logs to keep the collection lean."""
    try:
        from database import get_sync_db
        db = get_sync_db()
        cutoff = datetime.utcnow() - timedelta(days=days_old)
        result = db["automation_executions"].delete_many({
            "status": {"$in": ["completed", "failed", "skipped"]},
            "executed_at": {"$lt": cutoff}
        })
        logger.info(f"cleanup_automation_executions: removed {result.deleted_count} records")
        return {"deleted_count": result.deleted_count}
    except Exception as e:
        logger.error(f"cleanup_automation_executions failed: {e}")
        return {"error": str(e)}

