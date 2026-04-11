# backend/tasks/campaign/email_campaign_tasks.py
# PRODUCTION-READY EMAIL CAMPAIGN TASKS WITH SNAPSHOT SUPPORT
#
# KEY CHANGES vs original:
#   - Module-level _campaign_meta_cache and _snapshot_cache replace
#     per-email template fetches.
#   - _get_campaign_meta(campaign_id): DB read once per worker per campaign,
#     then memory only. Projection: only fields needed for sending.
#   - _get_snapshot(campaign_id): reads content_snapshot once per worker
#     per campaign. Falls back to live template_processor for old campaigns
#     that have no snapshot (backward compatibility).
#   - send_single_campaign_email: Step 5 now uses snapshot instead of
#     template_cache removed — snapshot used instead, direct Mongo fetch as fallback.
#   - finalize_campaign: evicts both caches on completion.
#   - Everything else unchanged.
#
# BUG FIXES (requeue / counter accuracy):
#   - Step 4  (already_sent):  removed stray `$inc processed_count +1` that
#     caused double-counting when a successfully-sent email was re-queued.
#   - Step 4c (new):           detect requeue — subscriber has an existing
#     "failed" log entry from a prior attempt.
#   - Success / failure paths: requeue-aware counter updates so processed_count
#     and failed_count are never incremented a second time for the same email.
#     On a successful requeue the previous failed_count is reversed (-1).
#   - All queued_count decrements now route through _decrement_queued() which
#     guards against going below zero (MongoDB $gt: 0 condition).

import logging
import time
import redis as _redis_module
import os
import json

from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from bson import ObjectId
from celery_app import celery_app
from celery import chord, group

from tasks.task_config import task_settings
from database import (
    get_sync_campaigns_collection,
    get_sync_email_logs_collection,
    get_sync_subscribers_collection,
    get_sync_templates_collection,
    get_sync_email_delivery_state_collection,   # BLOCKER-4: canonical delivery state
)
from tasks.campaign.resource_manager import resource_manager
from tasks.campaign.rate_limiter import rate_limiter, EmailProvider, RateLimitResult
from tasks.campaign.dlq_manager import dlq_manager
from tasks.campaign.campaign_control import campaign_controller
from tasks.campaign.metrics_collector import metrics_collector
from .template_renderer import template_renderer
from tasks.campaign.provider_manager import email_provider_manager
from tasks.campaign.audit_logger import (
    log_campaign_event,
    AuditEventType,
)

logger = logging.getLogger(__name__)

# ============================================================
# FILE-BASED OPERATIONAL LOGGING (/var/log)
# ============================================================


BACKEND_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
LOG_DIR = os.path.join(BACKEND_ROOT, "var", "log")
os.makedirs(LOG_DIR, exist_ok=True)


def _build_rotating_logger(name: str, filename: str) -> logging.Logger:
    _logger = logging.getLogger(name)
    if _logger.handlers:
        return _logger

    _logger.setLevel(logging.INFO)
    _logger.propagate = False

    handler = RotatingFileHandler(
        os.path.join(LOG_DIR, filename),
        maxBytes=20 * 1024 * 1024,  # 20MB
        backupCount=10,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(handler)
    return _logger


submission_logger = _build_rotating_logger(
    "campaign_submission_logger", "submission.log"
)
delivery_logger = _build_rotating_logger(
    "campaign_delivery_logger", "delivery.log"
)
campaign_ops_logger = _build_rotating_logger(
    "campaign_ops_logger", "campaign.log"
)


def _write_json_log(file_logger: logging.Logger, payload: Dict[str, Any]):
    try:
        payload.setdefault("timestamp", datetime.utcnow().isoformat())
        file_logger.info(json.dumps(payload, default=str, ensure_ascii=False))
    except Exception as e:
        logger.warning(f"Failed to write var log: {e}")


# ============================================================
# MODULE-LEVEL WORKER CACHES
# ============================================================

_campaign_meta_cache: Dict[str, Dict[str, Any]] = {}
_snapshot_cache: Dict[str, Dict[str, Any]] = {}


def _get_campaign_meta(campaign_id: str) -> Optional[Dict[str, Any]]:
    """Fetch campaign metadata with worker-level caching (projection ~200 bytes)."""
    if campaign_id in _campaign_meta_cache:
        return _campaign_meta_cache[campaign_id]

    campaigns_collection = get_sync_campaigns_collection()
    meta = campaigns_collection.find_one(
        {"_id": ObjectId(campaign_id)},
        {
            "sender_email": 1,
            "sender_name": 1,
            "reply_to": 1,
            "email_settings": 1,
            "status": 1,
            "subject": 1,
        },
    )
    if meta:
        meta["_id"] = str(meta["_id"])
        _campaign_meta_cache[campaign_id] = meta
        logger.debug(f"Campaign meta cached for {campaign_id}")
    return meta


def _get_snapshot(campaign_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch frozen content_snapshot with worker-level caching.
    Falls back to live template fetch for old campaigns without snapshot.
    """
    if campaign_id in _snapshot_cache:
        return _snapshot_cache[campaign_id]

    campaigns_collection = get_sync_campaigns_collection()
    doc = campaigns_collection.find_one(
        {"_id": ObjectId(campaign_id)},
        {"content_snapshot": 1, "template_id": 1, "field_map": 1, "fallback_values": 1},
    )
    if not doc:
        return None

    snap = doc.get("content_snapshot")

    if snap and snap.get("html_content"):
        result = {
            "html_content": snap["html_content"],
            "text_content": snap.get("text_content", ""),
            "subject": snap.get("subject", ""),
            "field_map": snap.get("field_map", doc.get("field_map", {})),
            "fallback_values": snap.get(
                "fallback_values", doc.get("fallback_values", {})
            ),
            "from_snapshot": True,
        }
        _snapshot_cache[campaign_id] = result
        logger.debug(
            f"Snapshot cached for {campaign_id} ({len(result['html_content'])} bytes)"
        )
        return result

    # Backward-compatibility: no snapshot — old campaign
    template_id = doc.get("template_id")
    if not template_id:
        logger.error(f"Campaign {campaign_id}: no snapshot and no template_id")
        return None

    logger.warning(
        f"Campaign {campaign_id}: content_snapshot absent — fetching template directly (old campaign)"
    )
    templates_collection = get_sync_templates_collection()
    template = templates_collection.find_one({"_id": ObjectId(template_id)})
    if not template:
        logger.error(
            f"Campaign {campaign_id}: fallback template {template_id} not found"
        )
        return None

    html_content = template.get("html_content", "")
    if not html_content:
        content_json = template.get("content_json", {})
        if content_json:
            from tasks.campaign.snapshot_utils import _extract_html_from_content_json

            html_content = _extract_html_from_content_json(content_json)

    if not html_content:
        logger.error(f"Campaign {campaign_id}: fallback template has no HTML")
        return None

    result = {
        "html_content": html_content,
        "text_content": template.get("text_content", ""),
        "subject": template.get("subject", ""),
        "field_map": doc.get("field_map", {}),
        "fallback_values": doc.get("fallback_values", {}),
        "from_snapshot": False,
    }
    _snapshot_cache[campaign_id] = result
    return result


def _evict_campaign_caches(campaign_id: str):
    """Remove completed/stopped campaign from both worker caches."""
    _campaign_meta_cache.pop(campaign_id, None)
    _snapshot_cache.pop(campaign_id, None)
    logger.debug(f"Evicted worker caches for campaign {campaign_id}")


# ============================================================
# EMAIL STATUS LOGGING
# ============================================================


def log_email_status(
    campaign_id: str,
    subscriber_id: str,
    email: str,
    status: str,
    message_id: str = None,
    error_reason: str = None,
    provider: str = None,
    cost: float = 0.0,
):
    try:
        email_logs_collection = get_sync_email_logs_collection()
        log_entry = {
            "campaign_id": ObjectId(campaign_id),
            "subscriber_id": subscriber_id,
            "email": email,
            "latest_status": status,
            "message_id": message_id,
            "provider": provider,
            "cost": cost,
            "last_attempted_at": datetime.utcnow(),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        if status == "sent":
            log_entry["sent_at"] = datetime.utcnow()
        elif status == "delivered":
            log_entry["delivered_at"] = datetime.utcnow()
        elif status == "failed":
            log_entry["failure_reason"] = error_reason
            log_entry["failed_at"] = datetime.utcnow()

        email_logs_collection.insert_one(log_entry)

        # File-based delivery log (replaces duplicate audit email logging)
        _write_json_log(
            delivery_logger,
            {
                "event": "email_status",
                "campaign_id": campaign_id,
                "subscriber_id": subscriber_id,
                "email": email,
                "status": status,
                "message_id": message_id,
                "provider": provider,
                "cost": cost,
                "error": error_reason,
            },
        )

    except Exception as e:
        logger.error(f"Failed to log email status: {e}")


# ============================================================
# TASK: send_single_campaign_email
# ============================================================


def _decrement_queued(campaign_id: str):
    """
    Decrement queued_count by 1, floored at 0.
    Uses findAndModify-style update to avoid negative values.
    All code paths that finish processing a queued task MUST use this
    function instead of raw '$inc queued_count: -1' to prevent the
    counter from going negative when tasks are requeued from DLQ.
    """
    try:
        col = get_sync_campaigns_collection()
        oid = ObjectId(campaign_id)
        # Decrement only if current value > 0
        col.update_one(
            {"_id": oid, "queued_count": {"$gt": 0}}, {"$inc": {"queued_count": -1}}
        )
    except Exception:
        pass  # best-effort


# ─────────────────────────────────────────────────────────────────────────────
# BLOCKER-4: CANONICAL DELIVERY STATE
# One doc per (campaign_id, subscriber_id) — the single source of truth for
# each recipient's journey. email_logs remains append-only audit trail.
#
# BLOCKER-4 FIX: _TERMINAL_STATES must only contain irreversible recipient
# outcomes. "duplicate" and "skipped" are execution outcomes — they must NOT
# be terminal because a later legitimate retry should be able to promote the
# state to "sent". Treating them as terminal would permanently block a
# recipient who was temporarily skipped due to a race.
# ─────────────────────────────────────────────────────────────────────────────
_TERMINAL_STATES = frozenset({"sent", "delivered", "failed", "suppressed", "invalid"})


def upsert_delivery_state(
    campaign_id: str,
    subscriber_id: str,
    email: str,
    state: str,
    *,
    provider: str = None,
    message_id: str = None,
    failure_reason: str = None,
    attempts_inc: int = 0,
) -> None:
    """
    Upsert the canonical delivery-state doc for one recipient.

    Rules:
    - Creates doc on first call.
    - Never overwrites a terminal state with a non-terminal one (idempotent).
    - "duplicate"/"skipped" are non-terminal: a future retry can still reach "sent".
    - Records per-state timestamps for observability.
    - Best-effort: never raises — a write failure here must not block email sending.
    """
    try:
        col = get_sync_email_delivery_state_collection()
        now = datetime.utcnow()

        set_fields: Dict[str, Any] = {
            "email": email,
            "updated_at": now,
            "state": state,
        }
        if provider:
            set_fields["provider"] = provider
        if message_id:
            set_fields["message_id"] = message_id
        if failure_reason:
            set_fields["failure_reason"] = failure_reason

        if state == "sent":
            set_fields["sent_at"] = now
        elif state == "delivered":
            set_fields["delivered_at"] = now
        elif state == "failed":
            set_fields["failed_at"] = now
        elif state == "suppressed":
            set_fields["suppressed_at"] = now

        update: Dict[str, Any] = {
            "$set": set_fields,
            "$setOnInsert": {"created_at": now},
        }
        if attempts_inc:
            update["$inc"] = {"attempts": attempts_inc}

        col.update_one(
            {
                "campaign_id": ObjectId(campaign_id),
                "subscriber_id": subscriber_id,
                # Only allow overwrite if current state is NOT terminal.
                # This keeps "sent" permanent even if a duplicate task fires later.
                "$or": [
                    {"state": {"$nin": list(_TERMINAL_STATES)}},
                    {"state": state},  # re-upsert same terminal state is idempotent
                ],
            },
            update,
            upsert=True,
        )
    except Exception as e:
        logger.warning(
            f"upsert_delivery_state non-fatal failure for "
            f"{campaign_id}/{subscriber_id} -> {state}: {e}"
        )


@celery_app.task(
    bind=True,
    max_retries=task_settings.MAX_EMAIL_RETRIES,
    queue="campaigns",
    name="tasks.send_single_campaign_email",
    soft_time_limit=task_settings.TASK_TIMEOUT_SECONDS,
)
def send_single_campaign_email(self, campaign_id: str, subscriber_id: str):
    start_time = time.time()

    try:
        # ── STEP 1: RESOURCE CHECK ────────────────────────────────────────────
        can_process, reason, health_info = resource_manager.can_process_batch(
            1, campaign_id
        )
        if not can_process:
            if reason == "campaign_paused":
                _decrement_queued(campaign_id)
                return {
                    "status": "paused",
                    "reason": reason,
                    "campaign_id": campaign_id,
                }
            elif reason == "memory_limit_exceeded":
                raise self.retry(
                    countdown=60, exc=Exception(f"System overloaded: {reason}")
                )
            else:
                _decrement_queued(campaign_id)
                return {
                    "status": "resource_unavailable",
                    "reason": reason,
                    "health": health_info,
                }

        campaigns_collection = get_sync_campaigns_collection()
        subscribers_collection = get_sync_subscribers_collection()
        email_logs_collection = get_sync_email_logs_collection()

        # ── STEP 2: CAMPAIGN STATUS (from cache) ─────────────────────────────
        campaign_meta = _get_campaign_meta(campaign_id)
        if not campaign_meta:
            _decrement_queued(campaign_id)
            return {"status": "failed", "reason": "campaign_not_found"}

        if (
            campaign_controller.is_campaign_paused(campaign_id)
            or campaign_meta.get("status") == "paused"
        ):
            _decrement_queued(campaign_id)
            return {"status": "paused", "reason": "campaign_paused"}

        if (
            campaign_controller.is_campaign_stopped(campaign_id)
            or campaign_meta.get("status") == "stopped"
        ):
            _decrement_queued(campaign_id)
            return {"status": "stopped", "reason": "campaign_stopped"}

        # ── STEP 3: SUBSCRIBER ───────────────────────────────────────────────
        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not subscriber:
            _decrement_queued(campaign_id)
            return {"status": "failed", "reason": "subscriber_not_found"}

        recipient_email = subscriber.get("email")
        if not recipient_email:
            _decrement_queued(campaign_id)
            return {"status": "failed", "reason": "email_missing"}

        # ── STEP 3b: PER-RECIPIENT SEND LOCK ─────────────────────────────────
        # Acquired before duplicate check to close the TOCTOU window.
        # Two concurrent tasks for same (campaign, subscriber) race here;
        # only one wins nx=True. The loser returns "skipped" cleanly without
        # touching counters or delivery state — the winner will do all that.
        # TTL=900s covers max send timeout + all retries.
        _send_lock_key = f"campaign_send_lock:{campaign_id}:{subscriber_id}"
        _send_redis = None
        try:
            from core.redis_client import get_redis as _get_redis
            _send_redis = _get_redis()
            lock_acquired = _send_redis.set(_send_lock_key, self.request.id, nx=True, ex=900)
            if not lock_acquired:
                _decrement_queued(campaign_id)
                return {"status": "skipped", "reason": "send_lock_held_by_concurrent_task"}
        except Exception as _lock_err:
            logger.warning(
                f"Send lock unavailable for {campaign_id}/{subscriber_id}: {_lock_err}. "
                f"Continuing — duplicate check below still guards."
            )
            _send_redis = None

        # ── STEP 4: DUPLICATE CHECK ──────────────────────────────────────────
        # Check canonical delivery state first (fast, indexed, authoritative).
        # Fall back to email_logs for campaigns that predate delivery state.
        delivery_state_col = get_sync_email_delivery_state_collection()
        existing_state = delivery_state_col.find_one(
            {
                "campaign_id": ObjectId(campaign_id),
                "subscriber_id": subscriber_id,
                "state": {"$in": ["sent", "delivered"]},
            },
            {"_id": 1},
        )
        if not existing_state:
            existing_state = email_logs_collection.find_one(
                {
                    "campaign_id": ObjectId(campaign_id),
                    "subscriber_id": subscriber_id,
                    "latest_status": {"$in": ["sent", "delivered"]},
                },
                {"_id": 1},
            )
        if existing_state:
            _decrement_queued(campaign_id)
            return {"status": "skipped", "reason": "already_sent"}

        # ── STEP 4b: SUPPRESSION CHECK ───────────────────────────────────────
        from database import get_sync_suppressions_collection

        if get_sync_suppressions_collection().find_one(
            {"email": recipient_email}, {"_id": 1}
        ):
            _decrement_queued(campaign_id)
            campaigns_collection.update_one(
                {"_id": ObjectId(campaign_id)}, {"$inc": {"processed_count": 1}}
            )
            upsert_delivery_state(campaign_id, subscriber_id, recipient_email, "suppressed")
            return {
                "status": "skipped",
                "reason": "suppressed",
                "email": recipient_email,
            }

        # ── STEP 4c: REQUEUE DETECTION ───────────────────────────────────────
        existing_failed = email_logs_collection.find_one(
            {
                "campaign_id": ObjectId(campaign_id),
                "subscriber_id": subscriber_id,
                "latest_status": "failed",
            },
            {"_id": 1},
        )
        is_requeue = existing_failed is not None
        if is_requeue:
            logger.info(
                f"Requeue detected for subscriber {subscriber_id} "
                f"in campaign {campaign_id} — counters will not be re-incremented"
            )

        # ── STEP 5: RATE LIMITING ────────────────────────────────────────────
        provider_type = EmailProvider.DEFAULT
        if task_settings.ENABLE_RATE_LIMITING:
            email_settings = campaign_meta.get("email_settings", {})
            if email_settings:
                es = str(email_settings).lower()
                if "sendgrid" in es:
                    provider_type = EmailProvider.SENDGRID
                elif "ses" in es:
                    provider_type = EmailProvider.SES
                elif "mailgun" in es:
                    provider_type = EmailProvider.MAILGUN
                elif "smtp" in es:
                    provider_type = EmailProvider.SMTP

            can_send, rate_info = rate_limiter.can_send_email(
                provider_type, campaign_id
            )
            if can_send == RateLimitResult.RATE_LIMITED:
                raise self.retry(
                    countdown=60, exc=Exception(f"Rate limited: {rate_info}")
                )
            elif can_send == RateLimitResult.CIRCUIT_BREAKER_OPEN:
                if task_settings.ENABLE_DLQ:
                    dlq_result = dlq_manager.send_to_dlq(
                        campaign_id,
                        subscriber_id,
                        recipient_email,
                        {
                            "error": "Circuit breaker open",
                            "provider": provider_type.value,
                        },
                    )
                    return {
                        "status": "dlq",
                        "reason": "circuit_breaker_open",
                        "dlq_result": dlq_result,
                    }
                _decrement_queued(campaign_id)
                return {"status": "failed", "reason": "circuit_breaker_open"}

        # ── STEP 6: GET SNAPSHOT (cached per worker) ─────────────────────────
        snap = _get_snapshot(campaign_id)
        if not snap or not snap.get("html_content"):
            logger.error(f"No usable snapshot or template for campaign {campaign_id}")
            _decrement_queued(campaign_id)
            return {"status": "failed", "reason": "template_missing"}

        field_map = snap["field_map"]
        fallback_values = snap["fallback_values"]

        # ── STEP 7: PERSONALIZATION ──────────────────────────────────────────
        personalization_context = {}

        for template_field, mapped_field in field_map.items():
            template_field = template_field.strip()
            if mapped_field == "__EMPTY__":
                personalization_context[template_field] = ""
                continue
            if mapped_field == "__DEFAULT__":
                personalization_context[template_field] = fallback_values.get(
                    template_field, ""
                )
                continue

            value = None
            if mapped_field == "email":
                value = subscriber.get("email", "")
            elif mapped_field.startswith("standard."):
                value = subscriber.get("standard_fields", {}).get(
                    mapped_field.replace("standard.", ""), ""
                )
            elif mapped_field.startswith("custom."):
                value = subscriber.get("custom_fields", {}).get(
                    mapped_field.replace("custom.", "")
                )
                if value is None:
                    value = ""
            else:
                value = fallback_values.get(template_field, "")

            personalization_context[template_field] = value

        personalization_context["email"] = subscriber.get("email", "")
        personalization_context["first_name"] = subscriber.get(
            "standard_fields", {}
        ).get("first_name", "")
        personalization_context["last_name"] = subscriber.get(
            "standard_fields", {}
        ).get("last_name", "")

        for key, value in subscriber.get("custom_fields", {}).items():
            if key not in personalization_context:
                personalization_context[key] = value

        try:
            from routes.unsubscribe import (
                generate_unsubscribe_token,
                build_unsubscribe_url,
            )

            unsub_token = generate_unsubscribe_token(
                campaign_id, subscriber_id, recipient_email
            )
            personalization_context["unsubscribe_url"] = build_unsubscribe_url(
                unsub_token
            )
        except Exception as unsub_err:
            logger.warning(f"Failed to generate unsubscribe token: {unsub_err}")
            personalization_context["unsubscribe_url"] = "#"

        # ── Open & click tracking ─────────────────────────────────────────────
        _open_token = None
        _open_enabled = True
        _click_enabled = True
        try:
            from routes.tracking import (
                generate_tracking_token,
                build_open_pixel_url,
                get_tracking_flags_sync,
            )

            _flags = get_tracking_flags_sync()
            _open_enabled = _flags.get("open_tracking_enabled", True)
            _click_enabled = _flags.get("click_tracking_enabled", True)

            if _open_enabled or _click_enabled:
                _open_token = generate_tracking_token(
                    campaign_id, subscriber_id, recipient_email
                )

            personalization_context["open_tracking_url"] = (
                build_open_pixel_url(_open_token)
                if _open_enabled and _open_token
                else ""
            )
        except Exception as ot_err:
            logger.warning(f"Failed to generate tracking token: {ot_err}")
            personalization_context["open_tracking_url"] = ""

        personalization_context.update(
            {
                "subscriber_id": str(subscriber.get("_id", "")),
                "current_date": datetime.utcnow().strftime("%Y-%m-%d"),
                "current_year": str(datetime.utcnow().year),
                "sent_at": datetime.utcnow().strftime("%B %d, %Y"),
            }
        )
        for key, value in fallback_values.items():
            if key not in personalization_context:
                personalization_context[key] = value

        snapshot_as_template = {
            "html_content": snap["html_content"],
            "text_content": snap.get("text_content", ""),
            "subject": snap.get("subject", ""),
        }

        personalized = template_renderer.personalize_template(
            snapshot_as_template, subscriber, personalization_context
        )
        personalized["subject"] = campaign_meta.get("subject") or snap.get(
            "subject", "No Subject"
        )

        logger.info(
            f"Personalized {len(personalization_context)} fields for {recipient_email}"
        )

        if "error" in personalized:
            logger.error(f"Template personalization failed: {personalized['error']}")
            _decrement_queued(campaign_id)
            return {"status": "failed", "reason": "template_personalization_failed"}

        # ── STEP 8: SEND ─────────────────────────────────────────────────────
        sender_email = campaign_meta.get("sender_email", "noreply@example.com")
        sender_name = campaign_meta.get("sender_name", "")
        reply_to = campaign_meta.get("reply_to", sender_email)
        from_email = f"{sender_name} <{sender_email}>" if sender_name else sender_email
        configuration_set = campaign_meta.get("email_settings", {}).get(
            "ses_configuration_set"
        )

        # ── Inject pixel + rewrite links in final HTML ───────────────────────
        _html_to_send = personalized["html_content"]
        if _open_token and _html_to_send:
            try:
                from routes.tracking import (
                    rewrite_links_for_tracking,
                    create_tracking_record,
                )
                import asyncio as _asyncio

                if _click_enabled:
                    _html_to_send = rewrite_links_for_tracking(
                        _html_to_send, _open_token
                    )

                if _open_enabled:
                    from routes.tracking import build_open_pixel_url as _bop

                    _pixel = (
                        f'<img src="{_bop(_open_token)}" width="1" height="1" '
                        f'alt="" style="display:none;border:0;" />'
                    )
                    if "</body>" in _html_to_send:
                        _html_to_send = _html_to_send.replace(
                            "</body>", _pixel + "</body>", 1
                        )
                    else:
                        _html_to_send += _pixel

                try:
                    _loop = _asyncio.new_event_loop()
                    _loop.run_until_complete(
                        create_tracking_record(
                            campaign_id, subscriber_id, recipient_email, _open_token
                        )
                    )
                    _loop.close()
                except Exception as _te:
                    logger.warning(f"create_tracking_record failed: {_te}")

            except Exception as _lre:
                logger.warning(f"Tracking inject/rewrite failed: {_lre}")

        _write_json_log(
            submission_logger,
            {
                "event": "submission_attempt",
                "campaign_id": campaign_id,
                "subscriber_id": subscriber_id,
                "email": recipient_email,
                "task_id": self.request.id,
                "provider_hint": provider_type.value if provider_type else "default",
                "subject": personalized.get("subject"),
                "is_requeue": is_requeue,
            },
        )

        try:
            send_result = email_provider_manager.send_email_with_failover(
                sender_email=from_email,
                recipient_email=recipient_email,
                subject=personalized["subject"],
                html_content=_html_to_send,
                text_content=personalized.get("text_content"),
                campaign_id=campaign_id,
                reply_to=reply_to,
                timeout=task_settings.EMAIL_SEND_TIMEOUT_SECONDS,
                unsubscribe_url=personalization_context.get("unsubscribe_url", ""),
                configuration_set=configuration_set,
            )

            execution_time = time.time() - start_time

            if send_result.get("success"):
                message_id = send_result.get("message_id")
                provider = send_result.get("selected_provider", "unknown")
                cost = send_result.get("cost", 0.0)

                _write_json_log(
                    submission_logger,
                    {
                        "event": "submission_result",
                        "campaign_id": campaign_id,
                        "subscriber_id": subscriber_id,
                        "email": recipient_email,
                        "task_id": self.request.id,
                        "status": "sent",
                        "provider": provider,
                        "message_id": message_id,
                        "cost": cost,
                        "attempted_providers": send_result.get(
                            "attempted_providers", []
                        ),
                        "execution_time": execution_time,
                    },
                )

                log_email_status(
                    campaign_id,
                    subscriber_id,
                    recipient_email,
                    "sent",
                    message_id,
                    None,
                    provider,
                    cost,
                )
                upsert_delivery_state(
                    campaign_id, subscriber_id, recipient_email, "sent",
                    provider=provider, message_id=message_id, attempts_inc=1,
                )

                if is_requeue:
                    campaigns_collection.update_one(
                        {"_id": ObjectId(campaign_id)},
                        {
                            "$inc": {
                                "sent_count": 1,
                                "failed_count": -1,
                            },
                            "$set": {"last_batch_at": datetime.utcnow()},
                        },
                    )
                else:
                    campaigns_collection.update_one(
                        {"_id": ObjectId(campaign_id)},
                        {
                            "$inc": {
                                "sent_count": 1,
                                "processed_count": 1,
                            },
                            "$set": {"last_batch_at": datetime.utcnow()},
                        },
                    )
                _decrement_queued(campaign_id)

                if task_settings.ENABLE_RATE_LIMITING:
                    rate_limiter.record_email_result(
                        True, provider_type, None, campaign_id
                    )

                return {
                    "status": "sent",
                    "message_id": message_id,
                    "provider": provider,
                    "execution_time": execution_time,
                    "cost": cost,
                    "attempted_providers": send_result.get("attempted_providers", []),
                    "email": recipient_email,
                    "used_snapshot": snap.get("from_snapshot", False),
                }

            else:
                error_reason = send_result.get("error", "Unknown error")
                attempted_providers = send_result.get("attempted_providers", [])
                is_permanent = send_result.get("permanent_failure", False)

                _write_json_log(
                    submission_logger,
                    {
                        "event": "submission_result",
                        "campaign_id": campaign_id,
                        "subscriber_id": subscriber_id,
                        "email": recipient_email,
                        "task_id": self.request.id,
                        "status": "failed",
                        "error": error_reason,
                        "attempted_providers": attempted_providers,
                        "permanent_failure": is_permanent,
                    },
                )

                if is_permanent or self.request.retries >= self.max_retries:
                    if task_settings.ENABLE_DLQ and not is_permanent:
                        dlq_manager.send_to_dlq(
                            campaign_id,
                            subscriber_id,
                            recipient_email,
                            {
                                "error": error_reason,
                                "retry_count": self.request.retries,
                                "attempted_providers": attempted_providers,
                                "task_id": self.request.id,
                            },
                        )
                    log_email_status(
                        campaign_id,
                        subscriber_id,
                        recipient_email,
                        "failed",
                        None,
                        error_reason,
                        attempted_providers[0] if attempted_providers else "unknown",
                    )
                    upsert_delivery_state(
                        campaign_id, subscriber_id, recipient_email, "failed",
                        failure_reason=error_reason, attempts_inc=1,
                    )

                    if not is_requeue:
                        campaigns_collection.update_one(
                            {"_id": ObjectId(campaign_id)},
                            {
                                "$inc": {
                                    "failed_count": 1,
                                    "processed_count": 1,
                                },
                                "$set": {"last_batch_at": datetime.utcnow()},
                            },
                        )
                    else:
                        campaigns_collection.update_one(
                            {"_id": ObjectId(campaign_id)},
                            {"$set": {"last_batch_at": datetime.utcnow()}},
                        )
                    _decrement_queued(campaign_id)

                    if task_settings.ENABLE_RATE_LIMITING:
                        rate_limiter.record_email_result(
                            False, provider_type, error_reason, campaign_id
                        )

                    return {
                        "status": "failed" if is_permanent else "dlq",
                        "reason": "permanent_failure"
                        if is_permanent
                        else "max_retries_exceeded",
                        "error": error_reason,
                        "execution_time": execution_time,
                        "attempted_providers": attempted_providers,
                        "retry_count": self.request.retries,
                    }
                else:
                    countdown = min(
                        task_settings.RETRY_BACKOFF_BASE_SECONDS
                        * (2**self.request.retries),
                        3600,
                    )
                    raise self.retry(countdown=countdown, exc=Exception(error_reason))

        except Exception as e:
            _write_json_log(
                submission_logger,
                {
                    "event": "submission_exception",
                    "campaign_id": campaign_id,
                    "subscriber_id": subscriber_id,
                    "email": recipient_email if "recipient_email" in locals() else None,
                    "task_id": self.request.id,
                    "retry_count": self.request.retries,
                    "error": str(e),
                },
            )

            if self.request.retries >= self.max_retries:
                error_msg = str(e)
                if task_settings.ENABLE_DLQ:
                    dlq_manager.send_to_dlq(
                        campaign_id,
                        subscriber_id,
                        recipient_email,
                        {
                            "error": error_msg,
                            "retry_count": self.request.retries,
                            "task_id": self.request.id,
                            "exception": "send_exception",
                        },
                    )
                log_email_status(
                    campaign_id,
                    subscriber_id,
                    recipient_email,
                    "failed",
                    None,
                    error_msg,
                    "unknown",
                )
                upsert_delivery_state(
                    campaign_id, subscriber_id, recipient_email, "failed",
                    failure_reason=error_msg, attempts_inc=1,
                )

                if not is_requeue:
                    campaigns_collection.update_one(
                        {"_id": ObjectId(campaign_id)},
                        {
                            "$inc": {
                                "failed_count": 1,
                                "processed_count": 1,
                            },
                            "$set": {"last_batch_at": datetime.utcnow()},
                        },
                    )
                else:
                    campaigns_collection.update_one(
                        {"_id": ObjectId(campaign_id)},
                        {"$set": {"last_batch_at": datetime.utcnow()}},
                    )
                _decrement_queued(campaign_id)

                return {
                    "status": "failed",
                    "reason": "send_exception",
                    "error": error_msg,
                    "execution_time": time.time() - start_time,
                    "retry_count": self.request.retries,
                }
            else:
                raise self.retry(countdown=60, exc=e)

    except Exception as e:
        return {
            "status": "failed",
            "reason": "task_exception",
            "error": str(e),
            "execution_time": time.time() - start_time,
            "campaign_id": campaign_id,
            "subscriber_id": subscriber_id,
        }
    finally:
        # Always release the per-recipient send lock so future legitimate
        # retries (e.g. from DLQ) can acquire it. Only delete if we still
        # own it — another task may have taken it on a race.
        try:
            if _send_redis and _send_lock_key:
                current_holder = _send_redis.get(_send_lock_key)
                if current_holder == self.request.id:
                    _send_redis.delete(_send_lock_key)
        except Exception:
            pass


# ============================================================
# TASK: send_campaign_batch
# ============================================================


@celery_app.task(
    bind=True, queue="campaigns", name="tasks.send_campaign_batch", soft_time_limit=300
)
def send_campaign_batch(
    self, campaign_id: str, batch_size: int = None, last_id: str = None
):
    """
    Process one batch of subscribers.

    Redis lock: only ONE batch per campaign runs at a time.
    If a batch is already running, this task exits immediately.
    This prevents duplicate queueing and negative queued_count.
    """
    try:
        _redis = _redis_module.Redis.from_url(
            task_settings.REDIS_URL, decode_responses=True
        )
        lock_key = f"campaign_batch_lock:{campaign_id}"
        acquired = _redis.set(lock_key, self.request.id, nx=True, ex=360)
        if not acquired:
            running_task = _redis.get(lock_key)
            logger.info(
                f"Batch lock held by task {running_task} for campaign {campaign_id} — skipping duplicate"
            )
            return {
                "status": "skipped_duplicate_batch",
                "campaign_id": campaign_id,
                "lock_held_by": running_task,
            }
    except Exception as lock_err:
        logger.warning(f"Could not acquire batch lock for {campaign_id}: {lock_err}")
        _redis = None
        lock_key = None

    try:
        start_time = time.time()
        if not batch_size:
            batch_size = task_settings.MAX_BATCH_SIZE

        optimal_batch_size = resource_manager.get_optimal_batch_size(
            batch_size, campaign_id
        )
        if optimal_batch_size < batch_size:
            batch_size = optimal_batch_size

        campaigns_collection = get_sync_campaigns_collection()
        campaign = campaigns_collection.find_one(
            {"_id": ObjectId(campaign_id)},
            {
                "status": 1,
                "target_lists": 1,
                "target_list_count": 1,
                "processed_count": 1,
            },
        )
        if not campaign:
            return {"error": "campaign_not_found", "campaign_id": campaign_id}

        if campaign.get("status") not in ["sending", "paused"]:
            return {
                "status": "campaign_not_active",
                "current_status": campaign.get("status"),
                "campaign_id": campaign_id,
            }

        if campaign.get("status") == "paused" or campaign_controller.is_campaign_paused(
            campaign_id
        ):
            cursor_key = f"campaign:cursor:{campaign_id}"
            # BLOCKER-1 FIX: was campaign_controller.redis_client.set() — redis_client
            # no longer lives on the controller. Use the shared pool directly.
            # Also write cursor to Mongo for durability (Redis can expire).
            try:
                from core.redis_client import get_redis as _get_redis
                _get_redis().set(cursor_key, last_id or "", ex=86400)
            except Exception as _re:
                logger.warning(f"Redis cursor write failed for {campaign_id}: {_re}")
            campaigns_collection.update_one(
                {"_id": ObjectId(campaign_id)},
                {"$set": {
                    "resume_cursor": last_id,
                    "resume_cursor_saved_at": datetime.utcnow(),
                }},
            )
            return {
                "status": "paused",
                "reason": "campaign_paused",
                "campaign_id": campaign_id,
                "saved_cursor": last_id,
            }

        if campaign_controller.is_campaign_stopped(campaign_id):
            return {"status": "stopped", "campaign_id": campaign_id}

        subscribers = get_subscribers_for_campaign(campaign_id, batch_size, last_id)

        if not subscribers:
            processed_count = campaign.get("processed_count", 0)
            target_count = campaign.get("target_list_count", 0)
            if last_id or processed_count >= target_count or not target_count:
                finalize_result = finalize_campaign(campaign_id)
                return {
                    "status": "campaign_completed",
                    "processed_count": processed_count,
                    "target_count": target_count,
                    "finalize_result": finalize_result,
                }
            return {
                "status": "no_subscribers_found",
                "processed_count": processed_count,
                "target_count": target_count,
            }

        subscriber_ids = [str(sub["_id"]) for sub in subscribers]
        email_logs_collection = get_sync_email_logs_collection()
        already_sent = email_logs_collection.find(
            {
                "campaign_id": ObjectId(campaign_id),
                "subscriber_id": {"$in": subscriber_ids},
                "latest_status": {"$in": ["sent", "delivered"]},
            },
            {"subscriber_id": 1},
        )

        already_sent_ids = {log["subscriber_id"] for log in already_sent}
        new_subscribers = [
            s for s in subscribers if str(s["_id"]) not in already_sent_ids
        ]

        if not new_subscribers:
            if len(subscribers) < batch_size:
                finalize_result = finalize_campaign(campaign_id)
                return {
                    "status": "campaign_completed",
                    "processed_count": campaign.get("processed_count", 0),
                    "target_count": campaign.get("target_list_count", 0),
                    "finalize_result": finalize_result,
                }
            last_subscriber = subscribers[-1]
            next_task = send_campaign_batch.delay(
                campaign_id, batch_size, str(last_subscriber["_id"])
            )
            return {
                "status": "batch_already_processed",
                "total_subscribers": len(subscribers),
                "next_task_id": next_task.id,
            }

        email_sigs = [
            send_single_campaign_email.si(campaign_id, str(sub["_id"]))
            for sub in new_subscribers
        ]

        # BLOCKER-3 FIX: Recheck pause/stop immediately before queuing.
        # A user can hit Pause after subscribers are fetched but before sigs
        # are dispatched. Without this check, a full batch leaks through even
        # though the UI shows "paused". This is the tightest safe point.
        if campaign_controller.is_campaign_paused(campaign_id):
            try:
                from core.redis_client import get_redis as _get_redis
                _get_redis().set(f"campaign:cursor:{campaign_id}", last_id or "", ex=86400)
            except Exception:
                pass
            campaigns_collection.update_one(
                {"_id": ObjectId(campaign_id)},
                {"$set": {
                    "resume_cursor": last_id,
                    "resume_cursor_saved_at": datetime.utcnow(),
                }},
            )
            return {
                "status": "paused",
                "reason": "pause_detected_pre_queue",
                "campaign_id": campaign_id,
                "saved_cursor": last_id,
            }

        if campaign_controller.is_campaign_stopped(campaign_id):
            return {"status": "stopped", "reason": "stop_detected_pre_queue",
                    "campaign_id": campaign_id}

        campaigns_collection.update_one(
            {"_id": ObjectId(campaign_id)},
            {
                "$inc": {"queued_count": len(new_subscribers)},
                "$set": {"last_batch_at": datetime.utcnow()},
            },
        )

        next_task_id = None
        if len(subscribers) == batch_size:
            last_subscriber = subscribers[-1]
            next_batch_sig = send_campaign_batch.si(
                campaign_id, batch_size, str(last_subscriber["_id"])
            )
            result = chord(email_sigs)(next_batch_sig)
            next_task_id = result.id
        else:
            # Final batch — chord ensures finalize only fires after ALL
            # individual send tasks complete. BLOCKER-5 FIX: use .s() not .si()
            # so Celery's chord callback machinery works correctly across
            # different result backend configurations. The callback accepts
            # *args to tolerate variadic chord results.
            finalize_sig = finalize_campaign_task.s(campaign_id)
            chord(email_sigs)(finalize_sig)

        execution_time = time.time() - start_time
        result = {
            "status": "batch_processed",
            "campaign_id": campaign_id,
            "batch_size": len(new_subscribers),
            "queued_tasks": len(new_subscribers),
            "already_sent": len(already_sent_ids),
            "next_task_id": next_task_id,
            "execution_time": execution_time,
            "last_subscriber_id": str(subscribers[-1]["_id"]) if subscribers else None,
        }
        return result

    except Exception as e:
        logger.error(f"Batch processing failed for {campaign_id}: {e}")
        return {
            "error": str(e),
            "campaign_id": campaign_id,
            "batch_size": batch_size,
            "last_id": last_id,
        }

    finally:
        try:
            if _redis and lock_key:
                current = _redis.get(lock_key)
                if current == self.request.id:
                    _redis.delete(lock_key)
        except Exception:
            pass


def get_subscribers_for_campaign(
    campaign_id: str, batch_size: int, last_id: str = None
) -> List[Dict]:
    """
    Fetch next batch of subscribers for a campaign.
    Excludes emails that are in the suppressions collection (unsubscribed,
    bounced, spam complaints) so they are never fetched or queued.
    """
    try:
        from database import get_sync_suppressions_collection

        campaigns_collection = get_sync_campaigns_collection()
        subscribers_collection = get_sync_subscribers_collection()
        suppressions_collection = get_sync_suppressions_collection()

        campaign = campaigns_collection.find_one(
            {"_id": ObjectId(campaign_id)}, {"target_lists": 1, "target_segments": 1}
        )
        if not campaign:
            return []

        suppressed_emails = set(
            doc["email"]
            for doc in suppressions_collection.find({}, {"email": 1, "_id": 0})
            if doc.get("email")
        )

        target_lists = campaign.get("target_lists", [])
        query = {
            "email": {"$exists": True, "$ne": ""},
            "status": "active",
        }

        if suppressed_emails and len(suppressed_emails) <= 5000:
            query["email"] = {
                "$nin": list(suppressed_emails),
                "$exists": True,
                "$ne": "",
            }

        if target_lists:
            query["$or"] = [
                {"lists": {"$in": target_lists}},
                {"list": {"$in": target_lists}},
            ]

        if last_id:
            query["_id"] = {"$gt": ObjectId(last_id)}

        projection = {
            "_id": 1,
            "email": 1,
            "status": 1,
            "standard_fields": 1,
            "custom_fields": 1,
        }
        subscribers = list(
            subscribers_collection.find(query, projection)
            .sort("_id", 1)
            .limit(batch_size)
        )

        if suppressed_emails and len(suppressed_emails) > 5000:
            subscribers = [
                s for s in subscribers if s.get("email") not in suppressed_emails
            ]

        return subscribers

    except Exception as e:
        logger.error(f"Failed to get subscribers for campaign {campaign_id}: {e}")
        return []


def finalize_campaign(campaign_id: str) -> Dict[str, Any]:
    """
    Finalize a completed campaign.

    BLOCKER-2 FIX: Guarded by a Redis NX finalize lock so concurrent callers
    (chord callback, watchdog, manual invoke, end-of-list batch path) cannot
    race against each other. Only the first caller executes; subsequent ones
    return "already_finalizing" immediately.

    Lock TTL = 10 minutes. If the winner crashes mid-finalize, the watchdog
    will re-trigger after the lock expires + stale_threshold passes.
    """
    # ── Finalize lock — only one finalizer runs at a time ────────────────────
    _finalize_lock_key = f"campaign_finalize_lock:{campaign_id}"
    _finalize_redis = None
    _held_lock = False
    try:
        from core.redis_client import get_redis as _get_redis
        _finalize_redis = _get_redis()
        _held_lock = bool(
            _finalize_redis.set(_finalize_lock_key, "1", nx=True, ex=600)
        )
        if not _held_lock:
            logger.info(
                f"finalize_campaign: lock already held for {campaign_id} — skipping duplicate"
            )
            return {"status": "already_finalizing", "campaign_id": campaign_id}
    except Exception as _lock_err:
        logger.warning(
            f"finalize_campaign: could not acquire lock for {campaign_id}: {_lock_err}. "
            f"Proceeding without lock (degraded mode)."
        )

    try:
        campaigns_collection = get_sync_campaigns_collection()
        email_logs_collection = get_sync_email_logs_collection()

        campaign = campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
        if not campaign:
            return {"error": "campaign_not_found"}

        # Guard: don't finalize while tasks are genuinely still in flight.
        # BLOCKER-3 FIX: stale timeout so a crashed worker's drifted
        # queued_count can never deadlock finalization forever.
        queued_count = campaign.get("queued_count", 0)
        last_batch_at = campaign.get("last_batch_at")

        if queued_count > 0:
            stale_threshold = datetime.utcnow() - timedelta(minutes=30)
            is_stale = last_batch_at is None or last_batch_at < stale_threshold
            if not is_stale:
                logger.warning(
                    f"finalize_campaign: {campaign_id} queued_count={queued_count}, "
                    f"last_batch_at={last_batch_at} — deferring (tasks still in flight)"
                )
                return {
                    "status": "deferred",
                    "reason": "tasks_still_queued",
                    "queued_count": queued_count,
                }
            logger.warning(
                f"finalize_campaign: {campaign_id} queued_count={queued_count} is STALE "
                f"(last_batch_at={last_batch_at}) — forcing queued_count=0 and finalizing"
            )
            campaigns_collection.update_one(
                {"_id": ObjectId(campaign_id)},
                {"$set": {"queued_count": 0}},
            )

        if campaign.get("stop_type") == "graceful":
            campaigns_collection.update_one(
                {"_id": ObjectId(campaign_id)},
                {
                    "$set": {"status": "stopped", "completed_at": datetime.utcnow()},
                    "$unset": {"resume_cursor": "", "resume_cursor_saved_at": ""},
                },
            )
            _evict_campaign_caches(campaign_id)
            _cleanup_campaign_redis_keys(campaign_id)
            return {"status": "stopped", "message": "Campaign was manually stopped"}

        stats_pipeline = [
            {"$match": {"campaign_id": ObjectId(campaign_id)}},
            {"$group": {"_id": "$latest_status", "count": {"$sum": 1}}},
        ]
        final_stats = list(email_logs_collection.aggregate(stats_pipeline))
        status_counts = {stat["_id"]: stat["count"] for stat in final_stats}

        total_processed = sum(status_counts.values())
        sent_count = status_counts.get("sent", 0)
        delivered_count = status_counts.get("delivered", 0)
        failed_count = status_counts.get("failed", 0)

        canonical_sent = sent_count + delivered_count
        if canonical_sent > 0:
            final_status = "completed"
        elif total_processed == 0:
            final_status = "failed"
        else:
            final_status = "failed"

        campaigns_collection.update_one(
            {"_id": ObjectId(campaign_id)},
            {
                "$set": {
                    "status": final_status,
                    "completed_at": datetime.utcnow(),
                    "sent_count": sent_count,
                    "delivered_count": delivered_count,
                    "failed_count": failed_count,
                    "processed_count": total_processed,
                    "queued_count": 0,
                    "final_stats": status_counts,
                },
                "$unset": {"resume_cursor": "", "resume_cursor_saved_at": ""},
            },
        )

        _evict_campaign_caches(campaign_id)
        _cleanup_campaign_redis_keys(campaign_id)

        if task_settings.ENABLE_AUDIT_LOGGING:
            log_campaign_event(
                AuditEventType.CAMPAIGN_COMPLETED,
                campaign_id,
                {
                    "final_status": final_status,
                    "total_processed": total_processed,
                    "sent_count": sent_count,
                    "failed_count": failed_count,
                    "final_stats": status_counts,
                },
            )

        logger.info(
            f"Campaign {campaign_id} finalized: {final_status} "
            f"({total_processed} processed)"
        )
        return {
            "status": final_status,
            "total_processed": total_processed,
            "final_stats": status_counts,
            "completed_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Campaign finalization failed for {campaign_id}: {e}")
        return {"error": str(e)}
    finally:
        # Release finalize lock only if we acquired it
        if _held_lock and _finalize_redis:
            try:
                _finalize_redis.delete(_finalize_lock_key)
            except Exception:
                pass


def _cleanup_campaign_redis_keys(campaign_id: str) -> None:
    """
    Delete all transient Redis keys for a finished campaign.
    Called from finalize_campaign after DB is updated.
    Best-effort — never raises.
    """
    try:
        from core.redis_client import get_redis as _get_redis
        from tasks.task_config import get_redis_key
        r = _get_redis()
        r.delete(f"campaign:cursor:{campaign_id}")
        r.delete(f"campaign_batch_lock:{campaign_id}")
        r.delete(f"campaign_finalize_lock:{campaign_id}")
        r.delete(get_redis_key("campaign_paused", campaign_id))
        r.delete(get_redis_key("campaign_stopped", campaign_id))
    except Exception as e:
        logger.debug(f"_cleanup_campaign_redis_keys non-fatal for {campaign_id}: {e}")


@celery_app.task(
    bind=True,
    queue="campaigns",
    name="tasks.finalize_campaign_task",
    ignore_result=False,
)
def finalize_campaign_task(self, *results, campaign_id: str):
    """
    Chord callback — fires after every send_single_campaign_email in the
    final batch has returned.

    BLOCKER-5 FIX: Signature uses (*results, campaign_id) so it is tolerant
    of variadic chord result delivery. Some Celery versions pass a list of
    results as a single positional arg; others pass them individually.
    Using *results absorbs all of that without breaking.

    'results' is intentionally ignored — we re-derive final state from DB
    to guarantee correctness regardless of chord result completeness.
    """
    logger.info(
        f"finalize_campaign_task chord callback for campaign {campaign_id} "
        f"(received {len(results)} result(s))"
    )
    return finalize_campaign(campaign_id)


# ============================================================
# TASK: start_campaign
# ============================================================


@celery_app.task(bind=True, queue="campaigns", name="tasks.start_campaign")
def start_campaign(self, campaign_id: str):
    try:
        campaigns_collection = get_sync_campaigns_collection()
        result = campaigns_collection.update_one(
            {
                "_id": ObjectId(campaign_id),
                "status": {"$in": ["draft", "scheduled", "queued"]},
            },
            {
                "$set": {
                    "status": "sending",
                    "started_at": datetime.utcnow(),
                    "last_batch_at": datetime.utcnow(),
                    "sent_count": 0,
                    "failed_count": 0,
                    "delivered_count": 0,
                    "processed_count": 0,
                    "queued_count": 0,
                }
            },
        )
        if result.modified_count == 0:
            return {"error": "campaign_not_startable", "campaign_id": campaign_id}

        if task_settings.ENABLE_AUDIT_LOGGING:
            log_campaign_event(
                AuditEventType.CAMPAIGN_STARTED,
                campaign_id,
                {"started_by": "system", "started_at": datetime.utcnow().isoformat()},
            )

        initial_batch_task = send_campaign_batch.delay(
            campaign_id, task_settings.MAX_BATCH_SIZE, None
        )
        return {
            "status": "campaign_started",
            "campaign_id": campaign_id,
            "initial_batch_task_id": initial_batch_task.id,
            "started_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"Campaign start failed for {campaign_id}: {e}")
        return {"error": str(e)}


# ============================================================
# TASK: check_scheduled_campaigns
# ============================================================


@celery_app.task(bind=True, queue="campaigns", name="tasks.check_scheduled_campaigns")
def check_scheduled_campaigns(self):
    try:
        campaigns_collection = get_sync_campaigns_collection()
        now = datetime.utcnow()
        triggered = []

        while True:
            campaign = campaigns_collection.find_one_and_update(
                {"status": "scheduled", "scheduled_time": {"$lte": now}},
                {"$set": {"status": "queued", "queued_at": now}},
            )
            if not campaign:
                break
            campaign_id = str(campaign["_id"])
            try:
                task = start_campaign.delay(campaign_id)
                triggered.append({"campaign_id": campaign_id, "task_id": task.id})
            except Exception as e:
                campaigns_collection.update_one(
                    {"_id": campaign["_id"]}, {"$set": {"status": "scheduled"}}
                )
                logger.error(f"Failed to trigger scheduled campaign {campaign_id}: {e}")

        return {
            "status": "completed",
            "checked_at": now.isoformat(),
            "triggered_count": len(triggered),
            "triggered_campaigns": triggered,
        }

    except Exception as e:
        logger.error(f"check_scheduled_campaigns failed: {e}")
        return {"error": str(e)}