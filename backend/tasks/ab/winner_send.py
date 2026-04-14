# backend/tasks/ab/winner_send.py
"""
Send the winning A/B variant to every subscriber who was NOT in the test sample.

Flow
----
1. Read the completed A/B test document (target_lists, target_segments,
   variant_assignments, winner variant config, content_snapshot).
2. Build the set of subscriber IDs that were already sent to (the sample).
3. Fetch all active subscribers from the target audience, excluding the
   already-sampled IDs.
4. Dispatch send_winner_single_email for each remaining subscriber.

Design notes
------------
- Uses email_provider_manager directly (same as send_ab_test_single_email).
  No campaign document is created or touched.
- Suppression is checked per-recipient in send_winner_single_email.
- Results are written to ab_test_results so the test's final stats include
  the winner-send recipients.
- Batches recipient dispatch to avoid building a huge Celery group in memory.
"""

import logging
from datetime import datetime
from bson import ObjectId
from typing import List, Optional

from celery_app import celery_app
from database import (
    get_sync_ab_tests_collection,
    get_sync_subscribers_collection,
    get_sync_ab_test_results_collection,
    get_sync_suppressions_collection,
)
from tasks.campaign.provider_manager import email_provider_manager
from tasks.campaign.template_renderer import template_renderer

logger = logging.getLogger(__name__)

# How many recipient tasks to dispatch per batch loop iteration.
# Keeps memory flat for large audiences.
_DISPATCH_CHUNK = 500


# ============================================================
# TASK: send_winner_to_remaining
# Reads test, resolves audience, dispatches per-recipient tasks.
# ============================================================


@celery_app.task(
    bind=True,
    queue="ab_tests",
    name="tasks.send_winner_to_remaining",
    max_retries=2,
)
def send_winner_to_remaining(self, test_id: str, winner_variant: str):
    """
    Entry point — called after a test completes (manually or by auto_complete).

    Args:
        test_id:        ObjectId string of the ab_test document.
        winner_variant: "A" or "B"
    """
    try:
        col = get_sync_ab_tests_collection()
        test = col.find_one({"_id": ObjectId(test_id)})
        if not test:
            logger.error(f"send_winner_to_remaining: test {test_id} not found")
            return {"error": "test_not_found"}

        if test.get("status") not in ("completed", "running"):
            logger.warning(
                f"send_winner_to_remaining: test {test_id} has status "
                f"'{test.get('status')}' — aborting"
            )
            return {"skipped": True, "reason": "test_not_completed"}

        # ── Winning variant config ────────────────────────────────────────────
        variant_index = 0 if winner_variant == "A" else 1
        variants = test.get("variants", [])
        if variant_index >= len(variants):
            logger.error(
                f"send_winner_to_remaining: variant index {variant_index} "
                f"out of range for test {test_id}"
            )
            return {"error": "variant_index_out_of_range"}
        winner_config = variants[variant_index]

        # ── Already-sampled subscriber IDs ────────────────────────────────────
        # variant_assignments stores {"A": [{id, email, ...}], "B": [...]}
        variant_assignments = test.get("variant_assignments", {})
        sampled_ids = set()
        for sub_list in variant_assignments.values():
            for entry in sub_list:
                sub_id = (
                    entry.get("id") or entry.get("_id") or entry.get("subscriber_id")
                )
                if sub_id:
                    sampled_ids.add(str(sub_id))

        logger.info(
            f"send_winner_to_remaining: test={test_id} winner={winner_variant} "
            f"already_sampled={len(sampled_ids)}"
        )

        # ── Fetch remaining subscribers ───────────────────────────────────────
        remaining = _fetch_remaining_subscribers(test, sampled_ids)
        logger.info(f"send_winner_to_remaining: {len(remaining)} remaining recipients")

        if not remaining:
            logger.info(
                f"send_winner_to_remaining: no remaining recipients for {test_id}"
            )
            col.update_one(
                {"_id": ObjectId(test_id)},
                {
                    "$set": {
                        "winner_send_status": "no_remaining_subscribers",
                        "winner_send_at": datetime.utcnow(),
                    }
                },
            )
            return {"skipped": True, "reason": "no_remaining_subscribers"}

        # ── Dispatch per-recipient tasks in chunks ────────────────────────────
        dispatched = 0
        for i in range(0, len(remaining), _DISPATCH_CHUNK):
            chunk = remaining[i : i + _DISPATCH_CHUNK]
            for sub in chunk:
                send_winner_single_email.apply_async(
                    args=[test_id, winner_variant, winner_config, sub],
                    queue="ab_tests",
                )
                dispatched += 1

        # Record that winner-send was kicked off
        col.update_one(
            {"_id": ObjectId(test_id)},
            {
                "$set": {
                    "winner_send_status": "dispatched",
                    "winner_send_at": datetime.utcnow(),
                    "winner_send_count": dispatched,
                    "winner_variant_sent": winner_variant,
                }
            },
        )

        logger.info(
            f"send_winner_to_remaining: dispatched {dispatched} tasks "
            f"for test {test_id}"
        )
        return {
            "dispatched": dispatched,
            "test_id": test_id,
            "winner_variant": winner_variant,
        }

    except Exception as e:
        logger.error(f"send_winner_to_remaining failed for {test_id}: {e}")
        raise self.retry(exc=e, countdown=60)


# ============================================================
# TASK: send_winner_single_email
# Sends one email to one remaining subscriber.
# ============================================================


@celery_app.task(
    bind=True,
    queue="ab_tests",
    name="tasks.send_winner_single_email",
    max_retries=3,
    default_retry_delay=60,
)
def send_winner_single_email(
    self,
    test_id: str,
    variant: str,
    variant_config: dict,
    subscriber: dict,
):
    """
    Send the winning variant to one subscriber who was not in the sample.

    subscriber dict shape (same as produced by _fetch_remaining_subscribers):
        {_id, email, standard_fields, custom_fields}
    """
    ab_results_col = get_sync_ab_test_results_collection()
    recipient_email = subscriber.get("email", "")
    subscriber_id = str(subscriber.get("_id", ""))

    try:
        # ── Suppression check ────────────────────────────────────────────────
        supp_col = get_sync_suppressions_collection()
        if supp_col.find_one({"email": recipient_email, "is_active": {"$ne": False}}):
            logger.debug(
                f"send_winner_single_email: {recipient_email} suppressed — skipping"
            )
            ab_results_col.insert_one(
                {
                    "test_id": test_id,
                    "variant": variant,
                    "subscriber_id": subscriber_id,
                    "subscriber_email": recipient_email,
                    "email_sent": False,
                    "is_winner_send": True,
                    "skipped_reason": "suppressed",
                    "sent_at": datetime.utcnow(),
                }
            )
            return {"status": "skipped", "reason": "suppressed"}

        # ── Fetch test (projection: only what we need) ───────────────────────
        col = get_sync_ab_tests_collection()
        test = col.find_one(
            {"_id": ObjectId(test_id)},
            {
                "subject": 1,
                "sender_name": 1,
                "sender_email": 1,
                "reply_to": 1,
                "field_map": 1,
                "fallback_values": 1,
                "content_snapshot": 1,
                "template_id": 1,
            },
        )
        if not test:
            raise Exception(f"A/B test {test_id} not found")

        # ── Resolve per-variant overrides (same logic as ab_testing.py) ──────
        subject = variant_config.get("subject") or test.get("subject", "")
        sender_name = variant_config.get("sender_name") or test.get("sender_name", "")
        sender_email = variant_config.get("sender_email") or test.get(
            "sender_email", ""
        )
        reply_to = (
            variant_config.get("reply_to") or test.get("reply_to") or sender_email
        )

        # ── Resolve HTML from snapshot (preferred) or live template ──────────
        snap = test.get("content_snapshot")
        html_content = ""
        field_map = {}
        fallback_values = {}

        if snap:
            html_content = snap.get("html_content", "")
            field_map = snap.get("field_map", test.get("field_map", {}))
            fallback_values = snap.get(
                "fallback_values", test.get("fallback_values", {})
            )
        else:
            # Fallback for tests started before snapshot support
            field_map = test.get("field_map", {})
            fallback_values = test.get("fallback_values", {})
            if test.get("template_id"):
                from database import get_sync_templates_collection

                tmpl = get_sync_templates_collection().find_one(
                    {"_id": ObjectId(test["template_id"])}
                )
                if tmpl:
                    html_content = tmpl.get("html_content", "") or tmpl.get(
                        "content", ""
                    )

        # ── Personalise ───────────────────────────────────────────────────────
        if html_content:
            email = subscriber.get("email", "")
            first_name = subscriber.get("first_name", "") or subscriber.get(
                "standard_fields", {}
            ).get("first_name", "")
            custom_fields = subscriber.get("custom_fields", {})

            # ── Unsubscribe token ──────────────────────────────────────────────
            unsub_url = "#"
            try:
                from routes.unsubscribe import (
                    generate_unsubscribe_token,
                    build_unsubscribe_url,
                )

                _unsub_token = generate_unsubscribe_token(test_id, subscriber_id, email)
                unsub_url = build_unsubscribe_url(_unsub_token)
            except Exception as _ue:
                logger.warning(f"winner_send unsubscribe token failed: {_ue}")

            html_content = html_content.replace("{{unsubscribe_url}}", unsub_url)

            # ── Open & click tracking ──────────────────────────────────────────
            _open_token = None
            _open_enabled = True
            _click_enabled = True
            try:
                from routes.tracking import (
                    generate_tracking_token,
                    build_open_pixel_url,
                    get_tracking_flags_sync,
                    create_ab_tracking_record_sync,
                )

                _flags = get_tracking_flags_sync()
                _open_enabled = _flags.get("open_tracking_enabled", True)
                _click_enabled = _flags.get("click_tracking_enabled", True)

                if _open_enabled or _click_enabled:
                    _open_token = generate_tracking_token(test_id, subscriber_id, email)
                    create_ab_tracking_record_sync(
                        test_id, variant, subscriber_id, email, _open_token
                    )
            except Exception as _te:
                logger.warning(f"winner_send tracking setup failed: {_te}")

            for template_field, mapped_field in field_map.items():
                value = ""
                if mapped_field == "__EMPTY__":
                    value = ""
                elif mapped_field == "__DEFAULT__":
                    value = fallback_values.get(template_field, "")
                elif mapped_field == "email":
                    value = email
                elif mapped_field.startswith("standard."):
                    fn = mapped_field.replace("standard.", "")
                    value = subscriber.get("standard_fields", {}).get(fn, "")
                elif mapped_field.startswith("custom."):
                    fn = mapped_field.replace("custom.", "")
                    value = str(custom_fields.get(fn, ""))
                else:
                    value = fallback_values.get(template_field, "")
                html_content = html_content.replace(
                    f"{{{{{template_field}}}}}", str(value)
                )

            html_content = html_content.replace("{{first_name}}", first_name)
            html_content = html_content.replace("{{email}}", email)
            html_content = html_content.replace("{{subject}}", subject)
            for k, v in custom_fields.items():
                html_content = html_content.replace(f"{{{{{k}}}}}", str(v))
        else:
            _open_token = None
            _open_enabled = _click_enabled = False

        if not html_content:
            first_name = subscriber.get("standard_fields", {}).get(
                "first_name", "there"
            )
            html_content = (
                f"<html><body><p>Hello {first_name},</p><p>{subject}</p></body></html>"
            )

        # ── Inject open pixel + rewrite links ────────────────────────────────
        if _open_token and html_content:
            try:
                from routes.tracking import (
                    rewrite_links_for_tracking,
                    build_open_pixel_url,
                )

                if _click_enabled:
                    html_content = rewrite_links_for_tracking(html_content, _open_token)
                if _open_enabled:
                    _pixel = (
                        f'<img src="{build_open_pixel_url(_open_token)}" '
                        f'width="1" height="1" alt="" style="display:none;border:0;" />'
                    )
                    if "</body>" in html_content:
                        html_content = html_content.replace(
                            "</body>", _pixel + "</body>", 1
                        )
                    else:
                        html_content += _pixel
            except Exception as _pe:
                logger.warning(f"winner_send pixel injection failed: {_pe}")

        # ── Send ─────────────────────────────────────────────────────────────
        result = email_provider_manager.send_email_with_failover(
            sender_email=sender_email,
            recipient_email=recipient_email,
            subject=subject,
            html_content=html_content,
            sender_name=sender_name,
            reply_to=reply_to,
        )

        message_id = result.get("message_id")
        success = result.get("success", False)

        ab_results_col.insert_one(
            {
                "test_id": test_id,
                "variant": variant,
                "subscriber_id": subscriber_id,
                "subscriber_email": recipient_email,
                "open_token": _open_token,
                "email_sent": success,
                "is_winner_send": True,
                "sent_at": datetime.utcnow(),
                "message_id": message_id,
                "email_opened": False,
                "email_clicked": False,
                "first_open_at": None,
                "last_open_at": None,
                "first_click_at": None,
                "last_click_at": None,
                "error": None if success else result.get("error"),
            }
        )

        if success:
            logger.debug(
                f"send_winner_single_email: sent to {recipient_email} "
                f"via {result.get('selected_provider')}"
            )
            return {"status": "sent", "message_id": message_id}
        else:
            raise Exception(result.get("error", "Provider returned failure"))

    except Exception as e:
        ab_results_col.insert_one(
            {
                "test_id": test_id,
                "variant": variant,
                "subscriber_id": subscriber_id,
                "subscriber_email": recipient_email,
                "email_sent": False,
                "is_winner_send": True,
                "sent_at": datetime.utcnow(),
                "error": str(e),
            }
        )
        logger.error(f"send_winner_single_email failed for {recipient_email}: {e}")
        raise self.retry(exc=e)


# ============================================================
# HELPER: resolve remaining subscribers
# ============================================================


def _fetch_remaining_subscribers(
    test: dict,
    sampled_ids: set,
) -> List[dict]:
    """
    Return all active subscribers in the test's audience that were NOT
    part of the A/B sample, with suppressed emails excluded.
    """
    subscribers_col = get_sync_subscribers_collection()
    supp_col = get_sync_suppressions_collection()

    target_lists = test.get("target_lists", [])
    target_segments = test.get("target_segments", [])

    # Build suppression set (only emails, not full docs — faster for large lists)
    suppressed_emails: set = set()
    for doc in supp_col.find({"is_active": {"$ne": False}}, {"email": 1, "_id": 0}):
        if doc.get("email"):
            suppressed_emails.add(doc["email"].lower())

    seen_ids: set = set()
    results: List[dict] = []

    # ── From lists ────────────────────────────────────────────────────────────
    if target_lists:
        query = {
            "$or": [
                {"lists": {"$in": target_lists}},
                {"list": {"$in": target_lists}},
            ],
            "status": "active",
        }
        for doc in subscribers_col.find(
            query,
            {"_id": 1, "email": 1, "standard_fields": 1, "custom_fields": 1},
        ):
            sub_id = str(doc["_id"])
            email = doc.get("email", "").lower()
            if (
                sub_id not in sampled_ids
                and sub_id not in seen_ids
                and email
                and email not in suppressed_emails
            ):
                seen_ids.add(sub_id)
                doc["_id"] = sub_id
                results.append(doc)

    # ── From segments (if any) ────────────────────────────────────────────────
    if target_segments:
        seg_ids = _resolve_segment_ids(target_segments)
        if seg_ids:
            remaining_seg = [
                i for i in seg_ids if i not in seen_ids and i not in sampled_ids
            ]
            if remaining_seg:
                for doc in subscribers_col.find(
                    {
                        "_id": {"$in": [ObjectId(i) for i in remaining_seg]},
                        "status": "active",
                    },
                    {"_id": 1, "email": 1, "standard_fields": 1, "custom_fields": 1},
                ):
                    sub_id = str(doc["_id"])
                    email = doc.get("email", "").lower()
                    if (
                        sub_id not in seen_ids
                        and email
                        and email not in suppressed_emails
                    ):
                        seen_ids.add(sub_id)
                        doc["_id"] = sub_id
                        results.append(doc)

    return results


def _resolve_segment_ids(segment_ids: List[str]) -> List[str]:
    """Resolve segment criteria → subscriber _id strings (sync version)."""
    if not segment_ids:
        return []
    try:
        from routes.segments import build_segment_query, SegmentCriteria
        from database import get_sync_segments_collection

        segs_col = get_sync_segments_collection()
        subs_col = get_sync_subscribers_collection()
        all_ids: set = set()
        for seg_id in segment_ids:
            if not ObjectId.is_valid(seg_id):
                continue
            seg = segs_col.find_one({"_id": ObjectId(seg_id)})
            if not seg or not seg.get("criteria"):
                continue
            try:
                query = build_segment_query(SegmentCriteria(**seg["criteria"]))
            except Exception as _qe:
                logger.warning(f"Could not build query for segment {seg_id}: {_qe}")
                continue
            query["status"] = "active"
            for doc in subs_col.find(query, {"_id": 1}):
                all_ids.add(str(doc["_id"]))
        return list(all_ids)
    except Exception as e:
        logger.error(f"_resolve_segment_ids failed: {e}")
        return []
