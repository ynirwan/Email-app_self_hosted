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


# ============================================================
# CAMPAIGN WATCHDOG / RECONCILIATION
# ============================================================

@celery_app.task(bind=True, queue="cleanup", name="tasks.reconcile_sending_campaigns")
def reconcile_sending_campaigns(self):
    """
    Watchdog: scans campaigns stuck in 'sending' and repairs them.
    Runs every 10 minutes via Celery Beat.

    Repairs:
    - Chord callback failed -> campaign never finalized -> re-seeds or finalizes
    - Worker crashed -> queued_count drifted -> resets and re-seeds from saved cursor
    - All work done but finalize lock blocked -> re-triggers finalize

    Decision per stale campaign (no batch activity > STALE_MINUTES):
      batch lock held       -> skip (actively running)
      paused / stopped      -> skip (user-controlled state)
      queued_count=0 & done -> finalize (chord miss scenario)
      otherwise             -> reset queued_count + re-seed from cursor
    """
    import redis as _redis_lib
    from tasks.task_config import task_settings, get_redis_key

    STALE_MINUTES = 15
    MAX_PER_RUN = 20

    try:
        campaigns_col = get_sync_campaigns_collection()
        now = datetime.utcnow()
        stale_threshold = now - timedelta(minutes=STALE_MINUTES)

        stale = list(campaigns_col.find(
            {
                "status": "sending",
                "$or": [
                    {"last_batch_at": {"$lt": stale_threshold}},
                    {"last_batch_at": {"$exists": False}},
                ],
            },
            {
                "_id": 1, "title": 1, "queued_count": 1,
                "processed_count": 1, "target_list_count": 1,
                "last_batch_at": 1, "resume_cursor": 1,
            },
            limit=MAX_PER_RUN,
        ))

        if not stale:
            logger.debug("reconcile_sending_campaigns: no stale campaigns")
            return {"status": "ok", "stale_found": 0}

        try:
            _r = _redis_lib.Redis.from_url(
                task_settings.REDIS_URL, decode_responses=True
            )
        except Exception:
            _r = None

        results = []
        for campaign in stale:
            cid = str(campaign["_id"])

            if _r:
                if _r.exists(f"campaign_batch_lock:{cid}"):
                    results.append({"campaign_id": cid, "action": "skipped_lock_held"})
                    continue
                if _r.exists(get_redis_key("campaign_paused", cid)):
                    results.append({"campaign_id": cid, "action": "skipped_paused"})
                    continue
                if _r.exists(get_redis_key("campaign_stopped", cid)):
                    results.append({"campaign_id": cid, "action": "skipped_stopped"})
                    continue

            queued = campaign.get("queued_count", 0)
            processed = campaign.get("processed_count", 0)
            target = campaign.get("target_list_count", 0)

            logger.warning(
                f"reconcile: stale campaign {cid} '{campaign.get('title')}' "
                f"queued={queued} processed={processed} target={target}"
            )

            from tasks.campaign.email_campaign_tasks import (
                finalize_campaign, send_campaign_batch,
            )

            if queued == 0 and (processed >= target or not target):
                result = finalize_campaign(cid)
                results.append({"campaign_id": cid, "action": "finalized", "result": result})
            else:
                if queued > 0:
                    campaigns_col.update_one(
                        {"_id": campaign["_id"]}, {"$set": {"queued_count": 0}}
                    )
                resume_from = campaign.get("resume_cursor")
                if not resume_from and _r:
                    rc = _r.get(f"campaign:cursor:{cid}")
                    resume_from = rc if rc else None

                task = send_campaign_batch.delay(
                    cid, task_settings.MAX_BATCH_SIZE, resume_from
                )
                results.append({
                    "campaign_id": cid, "action": "reseeded",
                    "resume_from": resume_from, "task_id": task.id,
                })

        logger.info(
            f"reconcile_sending_campaigns: checked {len(stale)}, "
            f"actions={[r['action'] for r in results]}"
        )
        return {"status": "ok", "stale_found": len(stale), "results": results}

    except Exception as e:
        logger.error(f"reconcile_sending_campaigns failed: {e}")
        return {"error": str(e)}


@celery_app.task(bind=True, queue="cleanup", name="tasks.cleanup_campaign_flags")
def cleanup_campaign_flags(self):
    """
    Clean stale Redis campaign control flags.

    Removes:
    - Keys with no TTL (ttl == -1): should always have explicit TTL
    - Pause flags for campaigns no longer in 'paused' DB status
    - Stop flags for campaigns no longer in 'stopped' DB status
    - Cursor keys for completed/failed/cancelled campaigns
    """
    import redis as _redis_lib
    from tasks.task_config import task_settings, get_redis_key

    try:
        _r = _redis_lib.Redis.from_url(
            task_settings.REDIS_URL, decode_responses=True
        )
        campaigns_col = get_sync_campaigns_collection()

        active_paused = {
            str(c["_id"])
            for c in campaigns_col.find({"status": "paused"}, {"_id": 1})
        }
        active_stopped = {
            str(c["_id"])
            for c in campaigns_col.find({"status": "stopped"}, {"_id": 1})
        }
        valid_cursor_ids = {
            str(c["_id"])
            for c in campaigns_col.find(
                {"status": {"$in": ["sending", "paused"]}}, {"_id": 1}
            )
        }

        cleaned_no_ttl = 0
        cleaned_stale = 0

        for pattern in [
            get_redis_key("campaign_paused", "*"),
            get_redis_key("campaign_stopped", "*"),
            "campaign:cursor:*",
        ]:
            for key in _r.scan_iter(match=pattern):
                if _r.ttl(key) == -1:
                    _r.delete(key)
                    cleaned_no_ttl += 1

        for key in _r.scan_iter(match=get_redis_key("campaign_paused", "*")):
            cid = key.rsplit(":", 1)[-1]
            if cid not in active_paused:
                _r.delete(key)
                cleaned_stale += 1

        for key in _r.scan_iter(match=get_redis_key("campaign_stopped", "*")):
            cid = key.rsplit(":", 1)[-1]
            if cid not in active_stopped:
                _r.delete(key)
                cleaned_stale += 1

        for key in _r.scan_iter(match="campaign:cursor:*"):
            cid = key.split("campaign:cursor:")[-1]
            if cid not in valid_cursor_ids:
                _r.delete(key)
                cleaned_stale += 1

        logger.info(
            f"cleanup_campaign_flags: removed {cleaned_no_ttl} no-TTL, "
            f"{cleaned_stale} stale flags"
        )
        return {"cleaned_no_ttl": cleaned_no_ttl, "cleaned_stale": cleaned_stale}

    except Exception as e:
        logger.error(f"cleanup_campaign_flags failed: {e}")
        return {"error": str(e)}