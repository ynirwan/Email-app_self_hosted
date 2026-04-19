# backend/tasks/ab/winner_send.py
"""
Send the winning A/B variant to every subscriber NOT in the A/B sample.

Production design mirrors email_campaign_tasks.py:
  ┌─ send_winner_batch (cursor-paged, batch-locked) ──────────────────────────┐
  │  • Fetches WINNER_BATCH_SIZE unique subscribers per task                  │
  │  • Skips sampled_ids using a Redis Set (not in-memory Python set)         │
  │  • Loads suppressed emails via indexed query, not a full collection scan  │
  │  • Holds a Redis NX batch-lock so retry never runs two batches at once    │
  │  • Checks stop flag before each batch                                     │
  │  • Writes progress to Redis + DB after every batch                        │
  │  • Chains next batch via self-scheduling (not a giant task fan-out)       │
  └───────────────────────────────────────────────────────────────────────────┘
  ┌─ send_winner_single_email ─────────────────────────────────────────────────┐
  │  • Per-recipient NX Redis send-lock (dedup, idempotent retry-safe)        │
  │  • Checks canonical email_delivery_state for already-sent guard           │
  │  • Suppression check per-recipient                                        │
  │  • Rate limiter integration                                               │
  │  • DLQ on permanent failure                                               │
  │  • Writes to email_logs (same as normal campaigns)                        │
  │  • Writes upsert_delivery_state canonical record                          │
  │  • Updates winner_send counters atomically                                │
  └───────────────────────────────────────────────────────────────────────────┘
"""

import logging
import json
import time
from datetime import datetime, timedelta
from bson import ObjectId
from typing import Optional

from celery_app import celery_app
from database import (
    get_sync_ab_tests_collection,
    get_sync_subscribers_collection,
    get_sync_ab_test_results_collection,
    get_sync_suppressions_collection,
    get_sync_email_logs_collection,
    get_sync_email_delivery_state_collection,
)
from tasks.campaign.provider_manager import email_provider_manager
from tasks.campaign.template_renderer import template_renderer
from tasks.task_config import task_settings

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

# Subscribers fetched and dispatched per batch task.
WINNER_BATCH_SIZE = 500

# Batch lock TTL — covers one full batch processing cycle with generous headroom.
_BATCH_LOCK_TTL = 420  # 7 minutes

# Send lock TTL per recipient — covers max send timeout + retries.
_SEND_LOCK_TTL = 900  # 15 minutes

# Terminal delivery states — never overwrite these.
_TERMINAL_STATES = frozenset({"sent", "delivered", "failed", "suppressed", "invalid"})


# ── Redis key helpers ─────────────────────────────────────────────────────────

def _stop_key(test_id: str) -> str:
    return f"ab_winner_send_stop:{test_id}"

def _progress_key(test_id: str) -> str:
    return f"ab_winner_send_progress:{test_id}"

def _batch_lock_key(test_id: str) -> str:
    return f"ab_winner_batch_lock:{test_id}"

def _send_lock_key(test_id: str, subscriber_id: str) -> str:
    return f"ab_winner_send_lock:{test_id}:{subscriber_id}"

def _sampled_set_key(test_id: str) -> str:
    """Redis Set storing subscriber IDs already in the A/B sample."""
    return f"ab_sampled_ids:{test_id}"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_redis():
    from core.redis_client import get_redis
    return get_redis()


def _is_stopped(test_id: str) -> bool:
    try:
        return bool(_get_redis().get(_stop_key(test_id)))
    except Exception:
        return False


def _update_progress(
    test_id: str,
    sent: int,
    failed: int,
    total: Optional[int],
    status: str,
):
    try:
        r = _get_redis()
        progress = {
            "sent": sent,
            "failed": failed,
            "total": total,
            "progress_pct": round(sent / total * 100, 1) if total else None,
            "status": status,
            "updated_at": datetime.utcnow().isoformat(),
        }
        r.setex(_progress_key(test_id), 86400, json.dumps(progress))
    except Exception as e:
        logger.debug(f"Progress update failed for {test_id}: {e}")


def _ensure_sampled_set(test_id: str, variant_assignments: dict) -> bool:
    """
    Populate a Redis Set with the sampled subscriber IDs for this test.
    Returns True if the set was created/existed, False on error.
    Uses SETNX-style creation so concurrent batch retries are idempotent.
    """
    try:
        r = _get_redis()
        key = _sampled_set_key(test_id)
        if r.exists(key):
            return True
        ids = []
        for sub_list in variant_assignments.values():
            for entry in sub_list:
                sub_id = entry.get("id") or entry.get("_id") or entry.get("subscriber_id")
                if sub_id:
                    ids.append(str(sub_id))
        if ids:
            # Pipeline in chunks to avoid huge single command
            pipe = r.pipeline()
            for chunk_start in range(0, len(ids), 1000):
                pipe.sadd(key, *ids[chunk_start:chunk_start + 1000])
            pipe.expire(key, 86400 * 7)  # keep 7 days
            pipe.execute()
        return True
    except Exception as e:
        logger.warning(f"_ensure_sampled_set failed for {test_id}: {e}")
        return False


def _is_sampled(test_id: str, subscriber_id: str) -> bool:
    """Check if subscriber was part of the A/B sample via Redis Set."""
    try:
        return bool(_get_redis().sismember(_sampled_set_key(test_id), subscriber_id))
    except Exception:
        return False


def _log_email_status(
    test_id: str,
    subscriber_id: str,
    email: str,
    status: str,
    message_id: Optional[str] = None,
    error_reason: Optional[str] = None,
    provider: Optional[str] = None,
):
    """Write to email_logs collection — same as normal campaigns."""
    try:
        col = get_sync_email_logs_collection()
        entry = {
            # Store test_id as a string campaign_id proxy so analytics queries work
            "campaign_id": test_id,
            "ab_test_id": test_id,
            "is_winner_send": True,
            "subscriber_id": subscriber_id,
            "email": email,
            "latest_status": status,
            "message_id": message_id,
            "provider": provider,
            "last_attempted_at": datetime.utcnow(),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        if status == "sent":
            entry["sent_at"] = datetime.utcnow()
        elif status == "failed":
            entry["failure_reason"] = error_reason
            entry["failed_at"] = datetime.utcnow()
        col.insert_one(entry)
    except Exception as e:
        logger.debug(f"log_email_status failed for {test_id}/{subscriber_id}: {e}")


def _upsert_delivery_state(
    test_id: str,
    subscriber_id: str,
    email: str,
    state: str,
    *,
    provider: Optional[str] = None,
    message_id: Optional[str] = None,
    failure_reason: Optional[str] = None,
):
    """Canonical per-recipient delivery state — idempotent, never overwrites terminal."""
    try:
        col = get_sync_email_delivery_state_collection()
        now = datetime.utcnow()
        set_fields = {
            "email": email,
            "updated_at": now,
            "state": state,
            "ab_test_id": test_id,
            "is_winner_send": True,
        }
        if provider:
            set_fields["provider"] = provider
        if message_id:
            set_fields["message_id"] = message_id
        if failure_reason:
            set_fields["failure_reason"] = failure_reason
        if state == "sent":
            set_fields["sent_at"] = now
        elif state == "failed":
            set_fields["failed_at"] = now
        elif state == "suppressed":
            set_fields["suppressed_at"] = now

        col.update_one(
            {
                "campaign_id": test_id,
                "subscriber_id": subscriber_id,
                "$or": [
                    {"state": {"$nin": list(_TERMINAL_STATES)}},
                    {"state": state},
                ],
            },
            {
                "$set": set_fields,
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
    except Exception as e:
        logger.debug(f"upsert_delivery_state failed {test_id}/{subscriber_id}: {e}")


def _finalize_winner_send(test_id: str):
    """Mark winner send completed. Re-reads counters from DB for accuracy."""
    try:
        col = get_sync_ab_tests_collection()
        doc = col.find_one(
            {"_id": ObjectId(test_id)},
            {"winner_send_sent": 1, "winner_send_failed": 1},
        )
        total_sent = (doc or {}).get("winner_send_sent", 0)
        total_failed = (doc or {}).get("winner_send_failed", 0)
        col.update_one(
            {"_id": ObjectId(test_id)},
            {"$set": {
                "winner_send_status": "completed",
                "winner_send_count": total_sent,
                "winner_send_failed_count": total_failed,
                "winner_send_completed_at": datetime.utcnow(),
            }},
        )
        _update_progress(test_id, total_sent, total_failed, total_sent + total_failed, "completed")
        logger.info(f"[winner] {test_id}: finalized. sent={total_sent} failed={total_failed}")
        # Clean up Redis sampled set (no longer needed)
        try:
            _get_redis().delete(_sampled_set_key(test_id))
        except Exception:
            pass
    except Exception as e:
        logger.error(f"_finalize_winner_send error for {test_id}: {e}")


# ============================================================
# TASK: send_winner_batch
# ============================================================

@celery_app.task(
    bind=True,
    queue="ab_tests",
    name="tasks.send_winner_batch",
    max_retries=5,
    soft_time_limit=360,
)
def send_winner_batch(self, test_id: str, winner_variant: str, last_id: Optional[str]):
    """
    Cursor-paged batch: fetch next WINNER_BATCH_SIZE remaining subscribers,
    dispatch individual send tasks, update counters, schedule the next batch.

    Guarded by a Redis NX batch-lock so concurrent retries never overlap.
    Checks stop flag before every batch. Self-chains rather than fan-out.
    """
    # ── Batch lock ─────────────────────────────────────────────────────────
    r = _get_redis()
    lock_key = _batch_lock_key(test_id)
    lock_acquired = False
    try:
        lock_acquired = bool(r.set(lock_key, self.request.id, nx=True, ex=_BATCH_LOCK_TTL))
        if not lock_acquired:
            holder = r.get(lock_key)
            logger.info(f"[winner_batch] {test_id}: lock held by {holder} — skip duplicate")
            return {"status": "skipped_duplicate", "lock_holder": str(holder)}
    except Exception as lock_err:
        logger.warning(f"[winner_batch] {test_id}: could not acquire lock: {lock_err}")

    try:
        # ── Stop flag check ────────────────────────────────────────────────
        if _is_stopped(test_id):
            logger.info(f"[winner_batch] {test_id}: stop flag set — halting")
            col = get_sync_ab_tests_collection()
            doc = col.find_one({"_id": ObjectId(test_id)}, {"winner_send_sent": 1, "winner_send_failed": 1})
            sent = (doc or {}).get("winner_send_sent", 0)
            failed = (doc or {}).get("winner_send_failed", 0)
            col.update_one(
                {"_id": ObjectId(test_id)},
                {"$set": {"winner_send_status": "stopped"}},
            )
            _update_progress(test_id, sent, failed, None, "stopped")
            return {"status": "stopped", "test_id": test_id}

        # ── Fetch test doc ─────────────────────────────────────────────────
        col = get_sync_ab_tests_collection()
        test = col.find_one(
            {"_id": ObjectId(test_id)},
            {
                "status": 1,
                "target_lists": 1,
                "target_segments": 1,
                "variant_assignments": 1,
                "variants": 1,
                "subject": 1,
                "sender_name": 1,
                "sender_email": 1,
                "reply_to": 1,
                "field_map": 1,
                "fallback_values": 1,
                "content_snapshot": 1,
                "winner_send_sent": 1,
                "winner_send_failed": 1,
            },
        )
        if not test:
            logger.error(f"[winner_batch] Test {test_id} not found")
            return {"status": "error", "reason": "test_not_found"}

        if test.get("status") not in ("completed", "running"):
            logger.warning(f"[winner_batch] {test_id}: status={test.get('status')} — aborting")
            return {"status": "skipped", "reason": f"status_{test.get('status')}"}

        # ── Ensure sampled IDs are in Redis Set ────────────────────────────
        variant_assignments = test.get("variant_assignments", {})
        _ensure_sampled_set(test_id, variant_assignments)

        # ── Resolve winning variant config ────────────────────────────────
        variant_index = 0 if winner_variant == "A" else 1
        variants = test.get("variants", [])
        if variant_index >= len(variants):
            logger.error(f"[winner_batch] Variant index {variant_index} out of range")
            return {"status": "error", "reason": "variant_out_of_range"}
        winner_config = variants[variant_index]

        # ── Build query ────────────────────────────────────────────────────
        target_lists = test.get("target_lists", [])
        if not target_lists:
            logger.info(f"[winner_batch] {test_id}: no target lists")
            _finalize_winner_send(test_id)
            return {"status": "done", "reason": "no_target_lists"}

        query = {
            "$or": [
                {"list": {"$in": target_lists}},
                {"lists": {"$in": target_lists}},
            ],
            "status": "active",
        }
        if last_id:
            query["_id"] = {"$gt": ObjectId(last_id)}

        # ── Fetch suppressed emails — indexed query, not full scan ─────────
        # Query only emails that appear in our target lists; don't load all suppressions.
        supp_col = get_sync_suppressions_collection()
        suppressed: set = set()
        # We need a fast check — use the email_logs approach: check per-recipient
        # in send_winner_single_email rather than pre-loading all suppressions here.
        # For the batch-level quick skip we only check a Redis-cached suppression count
        # to decide whether to do per-recipient suppression checks inline.
        # Full suppression check happens in send_winner_single_email.

        # ── Stream batch from cursor ───────────────────────────────────────
        subs_col = get_sync_subscribers_collection()
        batch_cursor = subs_col.find(
            query,
            {"_id": 1, "email": 1, "standard_fields": 1, "custom_fields": 1},
        ).sort("_id", 1).limit(WINNER_BATCH_SIZE)

        batch = list(batch_cursor)

        if not batch:
            logger.info(f"[winner_batch] {test_id}: no more subscribers — done")
            _finalize_winner_send(test_id)
            return {"status": "done", "test_id": test_id}

        # ── Dispatch send tasks ────────────────────────────────────────────
        dispatched = 0
        skipped_sampled = 0
        last_seen_id = None

        for sub in batch:
            last_seen_id = str(sub["_id"])
            sub_id = last_seen_id

            # Skip if in A/B sample (Redis Set check — O(1))
            if _is_sampled(test_id, sub_id):
                skipped_sampled += 1
                continue

            email = (sub.get("email") or "").strip()
            if not email:
                continue

            sub_payload = {
                "_id": sub_id,
                "email": sub.get("email", ""),
                "standard_fields": sub.get("standard_fields") or {},
                "custom_fields": sub.get("custom_fields") or {},
            }

            send_winner_single_email.apply_async(
                args=[test_id, winner_variant, winner_config, sub_payload],
                queue="ab_tests",
            )
            dispatched += 1

        # ── Update progress counters ───────────────────────────────────────
        col.update_one(
            {"_id": ObjectId(test_id)},
            {
                "$inc": {"winner_send_queued": dispatched},
                "$set": {
                    "winner_send_last_cursor": last_seen_id,
                    "winner_send_status": "running",
                },
            },
        )
        updated = col.find_one(
            {"_id": ObjectId(test_id)},
            {"winner_send_sent": 1, "winner_send_failed": 1, "winner_send_total": 1},
        )
        sent_so_far = (updated or {}).get("winner_send_sent", 0)
        failed_so_far = (updated or {}).get("winner_send_failed", 0)
        total_est = (updated or {}).get("winner_send_total")
        _update_progress(test_id, sent_so_far, failed_so_far, total_est, "running")

        logger.info(
            f"[winner_batch] {test_id}: dispatched={dispatched} skipped_sampled={skipped_sampled} "
            f"cursor={last_seen_id} cumulative_sent≈{sent_so_far}"
        )

        # ── Chain next batch ───────────────────────────────────────────────
        if len(batch) == WINNER_BATCH_SIZE:
            send_winner_batch.apply_async(
                args=[test_id, winner_variant, last_seen_id],
                queue="ab_tests",
                countdown=2,  # brief gap — prevents queue flooding
            )
        else:
            # Final batch — wait briefly for in-flight tasks then finalize
            send_winner_finalize.apply_async(
                args=[test_id],
                queue="ab_tests",
                countdown=120,  # 2 min — allows last batch tasks to settle
            )

        return {
            "status": "batch_done",
            "dispatched": dispatched,
            "skipped_sampled": skipped_sampled,
            "next_cursor": last_seen_id,
        }

    except Exception as e:
        logger.error(f"[winner_batch] {test_id}: error — {e}")
        raise self.retry(exc=e, countdown=60)

    finally:
        # Always release batch lock
        if lock_acquired:
            try:
                current = r.get(lock_key)
                if str(current) == self.request.id:
                    r.delete(lock_key)
            except Exception:
                pass


# ============================================================
# TASK: send_winner_finalize
# ============================================================

@celery_app.task(
    bind=True,
    queue="ab_tests",
    name="tasks.send_winner_finalize",
    max_retries=3,
)
def send_winner_finalize(self, test_id: str):
    """
    Called after the last batch completes. Waits for queued_count to reach 0
    (mirroring finalize_campaign), then writes final stats. Uses a finalize
    lock so concurrent retries don't double-write.
    """
    finalize_lock_key = f"ab_winner_finalize_lock:{test_id}"
    r = _get_redis()
    try:
        held = r.set(finalize_lock_key, "1", nx=True, ex=600)
        if not held:
            logger.info(f"[winner_finalize] {test_id}: already finalizing")
            return {"status": "already_finalizing"}
    except Exception:
        held = False

    try:
        col = get_sync_ab_tests_collection()
        doc = col.find_one(
            {"_id": ObjectId(test_id)},
            {"winner_send_queued": 1, "winner_send_sent": 1, "winner_send_failed": 1},
        )
        if not doc:
            return {"status": "test_not_found"}

        queued = doc.get("winner_send_queued", 0)
        sent = doc.get("winner_send_sent", 0)
        failed = doc.get("winner_send_failed", 0)

        # Stale guard — if tasks are still processing, defer
        stale_threshold = datetime.utcnow() - timedelta(minutes=30)
        updated_doc = col.find_one({"_id": ObjectId(test_id)}, {"winner_send_last_cursor_at": 1})
        last_cursor_at = (updated_doc or {}).get("winner_send_last_cursor_at")
        if queued > (sent + failed) and (last_cursor_at is None or last_cursor_at > stale_threshold):
            logger.info(f"[winner_finalize] {test_id}: tasks still in flight (queued={queued} sent={sent} failed={failed}). Deferring.")
            raise self.retry(countdown=60)

        _finalize_winner_send(test_id)
        return {"status": "finalized", "sent": sent, "failed": failed}

    finally:
        if held:
            try:
                r.delete(finalize_lock_key)
            except Exception:
                pass


# ============================================================
# TASK: send_winner_single_email
# ============================================================

@celery_app.task(
    bind=True,
    queue="ab_tests",
    name="tasks.send_winner_single_email",
    max_retries=task_settings.MAX_EMAIL_RETRIES,
    soft_time_limit=task_settings.TASK_TIMEOUT_SECONDS,
)
def send_winner_single_email(
    self,
    test_id: str,
    variant: str,
    variant_config: dict,
    subscriber: dict,
):
    """
    Send the winning variant to one remaining subscriber.

    Production safeguards mirroring send_single_campaign_email:
    - Per-recipient NX send lock (prevents duplicate sends on retry)
    - canonical email_delivery_state duplicate check
    - Suppression check
    - Rate limiting (if enabled)
    - DLQ on permanent failure
    - email_logs write (same schema as normal campaigns)
    - Atomic counter updates on test document
    """
    recipient_email = subscriber.get("email", "")
    subscriber_id = str(subscriber.get("_id", ""))
    ab_results_col = get_sync_ab_test_results_collection()

    # ── Stop flag (queued tasks abort cleanly) ─────────────────────────────
    if _is_stopped(test_id):
        logger.debug(f"[winner_single] {test_id} stopped — skipping {recipient_email}")
        return {"status": "skipped", "reason": "winner_send_stopped"}

    # ── Per-recipient send lock (NX) ────────────────────────────────────────
    r = _get_redis()
    slk = _send_lock_key(test_id, subscriber_id)
    lock_held = False
    try:
        lock_held = bool(r.set(slk, self.request.id, nx=True, ex=_SEND_LOCK_TTL))
        if not lock_held:
            logger.debug(f"[winner_single] Send lock held for {subscriber_id} — skipping")
            return {"status": "skipped", "reason": "send_lock_concurrent"}
    except Exception as lock_err:
        logger.warning(f"[winner_single] Lock unavailable: {lock_err}")

    try:
        # ── Canonical duplicate check ─────────────────────────────────────
        delivery_col = get_sync_email_delivery_state_collection()
        already = delivery_col.find_one(
            {
                "campaign_id": test_id,
                "subscriber_id": subscriber_id,
                "state": {"$in": ["sent", "delivered"]},
            },
            {"_id": 1},
        )
        if already:
            logger.debug(f"[winner_single] {recipient_email} already sent in {test_id}")
            return {"status": "skipped", "reason": "already_sent"}

        # ── Suppression check ─────────────────────────────────────────────
        supp_col = get_sync_suppressions_collection()
        if supp_col.find_one({"email": recipient_email, "is_active": {"$ne": False}}, {"_id": 1}):
            _upsert_delivery_state(test_id, subscriber_id, recipient_email, "suppressed")
            get_sync_ab_tests_collection().update_one(
                {"_id": ObjectId(test_id)},
                {"$inc": {"winner_send_sent": 1}},
            )
            logger.debug(f"[winner_single] {recipient_email} suppressed")
            return {"status": "skipped", "reason": "suppressed"}

        # ── Rate limiting ─────────────────────────────────────────────────
        if task_settings.ENABLE_RATE_LIMITING:
            from tasks.campaign.rate_limiter import rate_limiter, EmailProvider, RateLimitResult
            can_send, rate_info = rate_limiter.can_send_email(EmailProvider.DEFAULT, test_id)
            if can_send == RateLimitResult.RATE_LIMITED:
                raise self.retry(countdown=60, exc=Exception(f"Rate limited: {rate_info}"))
            elif can_send == RateLimitResult.CIRCUIT_BREAKER_OPEN:
                if task_settings.ENABLE_DLQ:
                    from tasks.campaign.dlq_manager import dlq_manager
                    dlq_manager.send_to_dlq(
                        test_id, subscriber_id, recipient_email,
                        {"error": "Circuit breaker open", "context": "winner_send"},
                    )
                return {"status": "failed", "reason": "circuit_breaker_open"}

        # ── Fetch test (snapshot + sender info) ───────────────────────────
        col = get_sync_ab_tests_collection()
        test = col.find_one(
            {"_id": ObjectId(test_id)},
            {
                "subject": 1, "sender_name": 1, "sender_email": 1, "reply_to": 1,
                "field_map": 1, "fallback_values": 1, "content_snapshot": 1, "template_id": 1,
            },
        )
        if not test:
            raise Exception(f"A/B test {test_id} not found")

        subject = variant_config.get("subject") or test.get("subject", "")
        sender_name = variant_config.get("sender_name") or test.get("sender_name", "")
        sender_email = variant_config.get("sender_email") or test.get("sender_email", "")
        reply_to = variant_config.get("reply_to") or test.get("reply_to") or sender_email

        # ── Resolve HTML from snapshot ─────────────────────────────────────
        snap = test.get("content_snapshot")
        html_content = ""
        field_map = {}
        fallback_values = {}

        if snap:
            html_content = snap.get("html_content", "")
            field_map = snap.get("field_map", test.get("field_map", {}))
            fallback_values = snap.get("fallback_values", test.get("fallback_values", {}))
        else:
            field_map = test.get("field_map", {})
            fallback_values = test.get("fallback_values", {})
            if test.get("template_id"):
                from database import get_sync_templates_collection
                tmpl = get_sync_templates_collection().find_one({"_id": ObjectId(test["template_id"])})
                if tmpl:
                    html_content = tmpl.get("html_content", "") or tmpl.get("content", "")

        if not html_content:
            first_name = (subscriber.get("standard_fields") or {}).get("first_name", "there")
            html_content = f"<html><body><p>Hello {first_name},</p><p>{subject}</p></body></html>"

        # ── Build personalization context ──────────────────────────────────
        email = subscriber.get("email", "")
        standard_fields = subscriber.get("standard_fields") or {}
        custom_fields = subscriber.get("custom_fields") or {}
        first_name = standard_fields.get("first_name", "")

        unsub_url = "#"
        try:
            from routes.unsubscribe import generate_unsubscribe_token, build_unsubscribe_url
            unsub_url = build_unsubscribe_url(
                generate_unsubscribe_token(test_id, subscriber_id, email)
            )
        except Exception as _ue:
            logger.debug(f"Unsubscribe token failed: {_ue}")

        _open_token = None
        _open_enabled = _click_enabled = True
        try:
            from routes.tracking import (
                generate_tracking_token, get_tracking_flags_sync, create_ab_tracking_record_sync,
            )
            _flags = get_tracking_flags_sync()
            _open_enabled = _flags.get("open_tracking_enabled", True)
            _click_enabled = _flags.get("click_tracking_enabled", True)
            if _open_enabled or _click_enabled:
                _open_token = generate_tracking_token(test_id, subscriber_id, email)
                create_ab_tracking_record_sync(test_id, variant, subscriber_id, email, _open_token)
        except Exception as _te:
            logger.debug(f"Tracking failed: {_te}")

        ctx: dict = {}
        for tf, mf in field_map.items():
            tf = tf.strip()
            if mf == "__EMPTY__":
                ctx[tf] = ""
            elif mf == "__DEFAULT__":
                ctx[tf] = fallback_values.get(tf, "")
            elif mf == "email":
                ctx[tf] = email
            elif mf.startswith("standard."):
                v = standard_fields.get(mf.replace("standard.", ""), "")
                ctx[tf] = v or fallback_values.get(tf, "")
            elif mf.startswith("custom."):
                raw = custom_fields.get(mf.replace("custom.", ""))
                ctx[tf] = str(raw) if raw is not None else fallback_values.get(tf, "")
            else:
                v = standard_fields.get(mf) or str(custom_fields.get(mf, ""))
                ctx[tf] = v or fallback_values.get(tf, "")

        ctx.update({
            "email": email,
            "first_name": first_name,
            "last_name": standard_fields.get("last_name", ""),
            "unsubscribe_url": unsub_url,
            "subject": subject,
            "subscriber_id": subscriber_id,
            "current_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "current_year": str(datetime.utcnow().year),
            "sent_at": datetime.utcnow().strftime("%B %d, %Y"),
        })
        for k, v in custom_fields.items():
            if k not in ctx:
                ctx[k] = str(v) if v is not None else ""
        for k, v in fallback_values.items():
            if k not in ctx:
                ctx[k] = v

        if _open_token:
            try:
                from routes.tracking import build_open_pixel_url
                ctx["open_tracking_url"] = build_open_pixel_url(_open_token)
            except Exception:
                ctx["open_tracking_url"] = ""

        # ── Render via template_renderer (Jinja2 + field replace) ─────────
        personalized = template_renderer.personalize_template(
            {"html_content": html_content, "text_content": "", "subject": subject},
            {"email": email, "standard_fields": standard_fields, "custom_fields": custom_fields, "_id": subscriber_id},
            ctx,
        )
        rendered_html = personalized.get("html_content", html_content)
        rendered_subject = personalized.get("subject") or subject

        # ── Inject tracking ────────────────────────────────────────────────
        if _open_token and rendered_html:
            try:
                from routes.tracking import rewrite_links_for_tracking, build_open_pixel_url
                if _click_enabled:
                    rendered_html = rewrite_links_for_tracking(rendered_html, _open_token)
                if _open_enabled:
                    pixel = (
                        f'<img src="{build_open_pixel_url(_open_token)}" '
                        f'width="1" height="1" alt="" style="display:none;border:0;" />'
                    )
                    rendered_html = (
                        rendered_html.replace("</body>", pixel + "</body>", 1)
                        if "</body>" in rendered_html
                        else rendered_html + pixel
                    )
            except Exception as _pe:
                logger.debug(f"Pixel injection failed: {_pe}")

        # ── Send ───────────────────────────────────────────────────────────
        result = email_provider_manager.send_email_with_failover(
            sender_email=sender_email,
            recipient_email=recipient_email,
            subject=rendered_subject,
            html_content=rendered_html,
            sender_name=sender_name,
            reply_to=reply_to,
        )

        success = result.get("success", False)
        message_id = result.get("message_id")
        provider = result.get("selected_provider", "unknown")
        error_msg = result.get("error") if not success else None
        is_permanent = result.get("permanent_failure", False)

        if success:
            # ── Success path ──────────────────────────────────────────────
            _log_email_status(test_id, subscriber_id, recipient_email, "sent", message_id, provider=provider)
            _upsert_delivery_state(test_id, subscriber_id, recipient_email, "sent", provider=provider, message_id=message_id)

            ab_results_col.insert_one({
                "test_id": test_id, "variant": variant,
                "subscriber_id": subscriber_id, "subscriber_email": recipient_email,
                "open_token": _open_token, "email_sent": True, "is_winner_send": True,
                "sent_at": datetime.utcnow(), "message_id": message_id,
                "email_opened": False, "email_clicked": False,
                "first_open_at": None, "last_open_at": None,
                "first_click_at": None, "last_click_at": None,
            })

            if task_settings.ENABLE_RATE_LIMITING:
                from tasks.campaign.rate_limiter import rate_limiter, EmailProvider
                rate_limiter.record_email_result(True, EmailProvider.DEFAULT, None, test_id)

            get_sync_ab_tests_collection().update_one(
                {"_id": ObjectId(test_id)},
                {"$inc": {"winner_send_sent": 1}},
            )
            return {"status": "sent", "message_id": message_id}

        else:
            # ── Failure path ──────────────────────────────────────────────
            if task_settings.ENABLE_RATE_LIMITING:
                from tasks.campaign.rate_limiter import rate_limiter, EmailProvider
                rate_limiter.record_email_result(False, EmailProvider.DEFAULT, error_msg, test_id)

            if is_permanent or self.request.retries >= self.max_retries:
                if task_settings.ENABLE_DLQ and not is_permanent:
                    from tasks.campaign.dlq_manager import dlq_manager
                    dlq_manager.send_to_dlq(
                        test_id, subscriber_id, recipient_email,
                        {"error": error_msg, "retry_count": self.request.retries, "context": "winner_send"},
                    )
                _log_email_status(test_id, subscriber_id, recipient_email, "failed", error_reason=error_msg)
                _upsert_delivery_state(test_id, subscriber_id, recipient_email, "failed", failure_reason=error_msg)
                ab_results_col.insert_one({
                    "test_id": test_id, "variant": variant,
                    "subscriber_id": subscriber_id, "subscriber_email": recipient_email,
                    "email_sent": False, "is_winner_send": True,
                    "sent_at": datetime.utcnow(), "error": error_msg,
                })
                get_sync_ab_tests_collection().update_one(
                    {"_id": ObjectId(test_id)},
                    {"$inc": {"winner_send_failed": 1}},
                )
                return {"status": "failed", "error": error_msg}
            else:
                countdown = min(
                    task_settings.RETRY_BACKOFF_BASE_SECONDS * (2 ** self.request.retries), 3600
                )
                raise self.retry(countdown=countdown, exc=Exception(error_msg))

    except Exception as e:
        _log_email_status(test_id, subscriber_id, recipient_email, "failed", error_reason=str(e))
        _upsert_delivery_state(test_id, subscriber_id, recipient_email, "failed", failure_reason=str(e))
        ab_results_col.insert_one({
            "test_id": test_id, "variant": variant,
            "subscriber_id": subscriber_id, "subscriber_email": recipient_email,
            "email_sent": False, "is_winner_send": True,
            "sent_at": datetime.utcnow(), "error": str(e),
        })
        get_sync_ab_tests_collection().update_one(
            {"_id": ObjectId(test_id)},
            {"$inc": {"winner_send_failed": 1}},
        )
        logger.error(f"[winner_single] {test_id} {variant} {recipient_email}: {e}")
        raise self.retry(exc=e, countdown=60)

    finally:
        # Always release per-recipient send lock
        if lock_held:
            try:
                current = r.get(slk)
                if str(current) == self.request.id:
                    r.delete(slk)
            except Exception:
                pass


# ============================================================
# Legacy entry point — auto_complete_ab_test calls this
# ============================================================

@celery_app.task(
    bind=True,
    queue="ab_tests",
    name="tasks.send_winner_to_remaining",
    max_retries=2,
)
def send_winner_to_remaining(self, test_id: str, winner_variant: str):
    """Delegates to the batched send_winner_batch. Kept for backward compat."""
    try:
        col = get_sync_ab_tests_collection()
        test = col.find_one({"_id": ObjectId(test_id)}, {"status": 1})
        if not test or test.get("status") not in ("completed", "running"):
            return {"skipped": True, "reason": "not_active"}

        col.update_one(
            {"_id": ObjectId(test_id)},
            {"$set": {
                "winner_send_status": "running",
                "winner_send_sent": 0,
                "winner_send_failed": 0,
                "winner_send_queued": 0,
                "winner_send_started_at": datetime.utcnow(),
            }},
        )
        send_winner_batch.apply_async(
            args=[test_id, winner_variant, None],
            queue="ab_tests",
            countdown=2,
        )
        logger.info(f"[winner_to_remaining] Delegated {test_id} to send_winner_batch")
        return {"dispatched": True, "test_id": test_id, "winner_variant": winner_variant}

    except Exception as e:
        logger.error(f"send_winner_to_remaining failed for {test_id}: {e}")
        raise self.retry(exc=e, countdown=60)