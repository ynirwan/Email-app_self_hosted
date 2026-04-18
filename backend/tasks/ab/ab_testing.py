# backend/tasks/ab/ab_testing.py
# ============================================================
# KEY FIXES:
#   1. send_ab_test_single_email uses _pm.send_email_with_failover()
#      instead of the removed get_email_service_sync / .send_email()
#   2. Field mapping reads standard_fields / custom_fields from the
#      full subscriber dict (now stored in variant_assignments)
#   3. assign_variants uses hashlib.md5 for stable cross-process hashing
# ============================================================

import logging
from datetime import datetime
from bson import ObjectId

from database import (
    get_sync_subscribers_collection,
    get_sync_templates_collection,
    get_sync_ab_tests_collection,
    get_sync_ab_test_results_collection,
)
from tasks.campaign.provider_manager import email_provider_manager as _pm
from celery_app import celery_app
from tasks.campaign.template_renderer import template_renderer

logger = logging.getLogger(__name__)


# ============================================================
# TASK: send_ab_test_batch
# ============================================================


@celery_app.task(bind=True, queue="ab_tests", name="tasks.send_ab_test_batch")
def send_ab_test_batch(self, test_id: str, variant_assignments: dict):
    try:
        col = get_sync_ab_tests_collection()

        test = col.find_one({"_id": ObjectId(test_id)})
        if not test:
            logger.error(f"A/B test not found: {test_id}")
            return {"success": False, "error": "Test not found"}

        variant_a_results = process_variant_emails(
            test_id,
            "A",
            test["variants"][0],
            variant_assignments["A"],
            test,
        )
        variant_b_results = process_variant_emails(
            test_id,
            "B",
            test["variants"][1],
            variant_assignments["B"],
            test,
        )

        col.update_one(
            {"_id": ObjectId(test_id)},
            {
                "$set": {
                    "emails_queued_at": datetime.utcnow(),
                    "variant_a_queued": len(variant_assignments["A"]),
                    "variant_b_queued": len(variant_assignments["B"]),
                }
            },
        )

        logger.info(f"A/B test batch queued: {test_id}")
        return {
            "success": True,
            "variant_a_processed": variant_a_results["processed"],
            "variant_b_processed": variant_b_results["processed"],
            "total_queued": (
                variant_a_results["processed"] + variant_b_results["processed"]
            ),
        }

    except Exception as e:
        logger.error(f"A/B test batch failed: {test_id}, error: {e}")
        return {"success": False, "error": str(e)}


# ============================================================
# HELPER: dispatch per-variant emails
# ============================================================


def process_variant_emails(
    test_id: str,
    variant_name: str,
    variant_config: dict,
    subscribers: list,
    test_config: dict,
):
    try:
        task_ids = []
        for subscriber in subscribers:
            task = send_ab_test_single_email.apply_async(
                args=[test_id, variant_name, variant_config, subscriber],
                queue="ab_tests",
            )
            task_ids.append(task.id)
        return {"processed": len(subscribers), "suppressed": 0, "task_ids": task_ids}
    except Exception as e:
        logger.error(f"Variant processing failed: {test_id} {variant_name}, error: {e}")
        return {"processed": 0, "suppressed": 0, "task_ids": []}


# ============================================================
# TASK: send_ab_test_single_email
# ============================================================


@celery_app.task(
    bind=True,
    max_retries=3,
    queue="ab_tests",
    name="tasks.send_ab_test_single_email",
)
def send_ab_test_single_email(
    self,
    test_id: str,
    variant: str,
    variant_config: dict,
    subscriber: dict,
):
    ab_test_results_collection = get_sync_ab_test_results_collection()

    try:
        col_tests = get_sync_ab_tests_collection()

        # Fetch test — projection: only what we need
        test = col_tests.find_one(
            {"_id": ObjectId(test_id)},
            {
                "template_id": 1,
                "subject": 1,
                "sender_name": 1,
                "sender_email": 1,
                "reply_to": 1,
                "field_map": 1,
                "fallback_values": 1,
                "content_snapshot": 1,
            },
        )
        if not test:
            raise Exception(f"A/B test not found: {test_id}")

        # Per-variant overrides
        subject = variant_config.get("subject") or test.get("subject", "")
        sender_name = variant_config.get("sender_name") or test.get("sender_name", "")
        sender_email = variant_config.get("sender_email") or test.get("sender_email", "")
        reply_to = variant_config.get("reply_to") or test.get("reply_to", sender_email)

        # ── Resolve html_content from snapshot ────────────────────────────────
        snap = test.get("content_snapshot")
        html_content = ""
        field_map = {}
        fallback_values = {}

        if snap:
            html_content = snap.get("html_content", "")
            field_map = snap.get("field_map", test.get("field_map", {}))
            fallback_values = snap.get("fallback_values", test.get("fallback_values", {}))
            logger.debug(
                f"AB test {test_id}/{variant}: using snapshot html ({len(html_content)} bytes)"
            )
        else:
            # Fallback: no snapshot (old test)
            field_map = test.get("field_map", {})
            fallback_values = test.get("fallback_values", {})
            logger.warning(
                f"AB test {test_id}: no content_snapshot, falling back to live template"
            )
            col_templates = get_sync_templates_collection()
            if test.get("template_id"):
                tmpl = col_templates.find_one({"_id": ObjectId(test["template_id"])})
                if tmpl:
                    html_content = tmpl.get("html_content", "") or tmpl.get("content", "")

        # ── Personalise ───────────────────────────────────────────────────────
        if html_content:
            email = subscriber.get("email", "")
            subscriber_id = str(subscriber.get("_id") or subscriber.get("id", ""))

            # FIX: read standard_fields and custom_fields from full subscriber dict
            # (these are now stored in variant_assignments by the fixed assign_variants)
            standard_fields = subscriber.get("standard_fields", {})
            custom_fields = subscriber.get("custom_fields", {})
            first_name = standard_fields.get("first_name", "") or subscriber.get("first_name", "")

            # ── Unsubscribe token ────────────────────────────────────────────
            unsub_url = "#"
            try:
                from routes.unsubscribe import generate_unsubscribe_token, build_unsubscribe_url
                unsub_token = generate_unsubscribe_token(test_id, subscriber_id, email)
                unsub_url = build_unsubscribe_url(unsub_token)
            except Exception as _ue:
                logger.warning(f"AB test unsubscribe token failed: {_ue}")

            html_content = html_content.replace("{{unsubscribe_url}}", unsub_url)

            # ── Tracking ─────────────────────────────────────────────────────
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
                logger.warning(f"AB test tracking setup failed: {_te}")

            # ── Apply field_map ───────────────────────────────────────────────
            for template_field, mapped_field in field_map.items():
                template_field = template_field.strip()
                value = ""

                if mapped_field == "__EMPTY__":
                    value = ""
                elif mapped_field == "__DEFAULT__":
                    value = fallback_values.get(template_field, "")
                elif mapped_field == "email":
                    value = email
                elif mapped_field.startswith("standard."):
                    field_name = mapped_field.replace("standard.", "")
                    value = standard_fields.get(field_name, "")
                    if not value:
                        value = fallback_values.get(template_field, "")
                elif mapped_field.startswith("custom."):
                    field_name = mapped_field.replace("custom.", "")
                    value = str(custom_fields.get(field_name, ""))
                    if not value:
                        value = fallback_values.get(template_field, "")
                else:
                    # Plain field name — check universal, standard, custom in order
                    if mapped_field == "email":
                        value = email
                    elif mapped_field in standard_fields:
                        value = standard_fields.get(mapped_field, "")
                    elif mapped_field in custom_fields:
                        value = str(custom_fields.get(mapped_field, ""))
                    else:
                        value = fallback_values.get(template_field, "")

                if value is None:
                    value = fallback_values.get(template_field, "")

                html_content = html_content.replace(f"{{{{{template_field}}}}}", str(value))

            # Convenience replacements
            html_content = html_content.replace("{{first_name}}", first_name)
            html_content = html_content.replace("{{email}}", email)
            html_content = html_content.replace("{{subject}}", subject)

            # Remaining custom fields not covered by field_map
            for k, v in custom_fields.items():
                html_content = html_content.replace(f"{{{{{k}}}}}", str(v))

        # Fallback body if still empty
        if not html_content:
            first_name = subscriber.get("standard_fields", {}).get("first_name", "there")
            html_content = (
                f"<html><body>"
                f"<p>Hello {first_name},</p>"
                f"<p>{subject}</p>"
                f"</body></html>"
            )

        # ── Inject open pixel + rewrite links ─────────────────────────────────
        if _open_token and html_content:
            try:
                from routes.tracking import rewrite_links_for_tracking, build_open_pixel_url
                if _click_enabled:
                    html_content = rewrite_links_for_tracking(html_content, _open_token)
                if _open_enabled:
                    _pixel = (
                        f'<img src="{build_open_pixel_url(_open_token)}" '
                        f'width="1" height="1" alt="" style="display:none;border:0;" />'
                    )
                    if "</body>" in html_content:
                        html_content = html_content.replace("</body>", _pixel + "</body>", 1)
                    else:
                        html_content += _pixel
            except Exception as _pe:
                logger.warning(f"AB test pixel injection failed: {_pe}")

        # ── Send via provider manager ─────────────────────────────────────────
        # FIX: use _pm.send_email_with_failover() — EmailProviderManager does NOT
        # have a .send_email() method. Result is a plain dict, not an object.
        result = _pm.send_email_with_failover(
            sender_email=sender_email,
            recipient_email=subscriber["email"],
            subject=subject,
            html_content=html_content,
            sender_name=sender_name,
            reply_to=reply_to,
        )

        message_id = result.get("message_id")

        if result.get("success", False):
            ab_test_results_collection.insert_one(
                {
                    "test_id": test_id,
                    "variant": variant,
                    "subscriber_id": str(subscriber.get("_id") or subscriber.get("id", "")),
                    "subscriber_email": subscriber["email"],
                    "open_token": _open_token,
                    "email_sent": True,
                    "sent_at": datetime.utcnow(),
                    "message_id": message_id,
                    "email_opened": False,
                    "email_clicked": False,
                    "first_open_at": None,
                    "last_open_at": None,
                    "first_click_at": None,
                    "last_click_at": None,
                    "conversion": False,
                }
            )
            logger.info(f"A/B email sent: {test_id} {variant} {subscriber['email']}")
        else:
            error_msg = result.get("error", "Provider returned failure")
            raise Exception(error_msg)

    except Exception as e:
        ab_test_results_collection.insert_one(
            {
                "test_id": test_id,
                "variant": variant,
                "subscriber_id": str(subscriber.get("_id") or subscriber.get("id", "")),
                "subscriber_email": subscriber["email"],
                "email_sent": False,
                "error": str(e),
                "sent_at": datetime.utcnow(),
            }
        )
        logger.error(
            f"A/B email failed: {test_id} {variant} {subscriber.get('email', '?')}: {e}"
        )
        raise


# ============================================================
# TASK: check_ab_test_expiry  (Celery Beat — every 15 min)
# ============================================================


@celery_app.task(
    bind=True,
    queue="ab_tests",
    name="tasks.check_ab_test_expiry",
)
def check_ab_test_expiry(self):
    try:
        col = get_sync_ab_tests_collection()
        running = list(col.find({"status": "running"}))
        logger.info(f"[AB Expiry] Checking {len(running)} running tests")

        now = datetime.utcnow()
        triggered = 0

        for test in running:
            test_id = str(test["_id"])
            start_date = test.get("start_date")
            duration_hours = test.get("test_duration_hours")

            if not start_date or not duration_hours:
                continue

            elapsed_hours = (now - start_date).total_seconds() / 3600
            if elapsed_hours >= duration_hours:
                logger.info(
                    f"[AB Expiry] Test {test_id} expired "
                    f"({elapsed_hours:.1f}h >= {duration_hours}h), triggering auto-complete"
                )
                try:
                    auto_complete_ab_test.delay(test_id)
                    triggered += 1
                except Exception as e:
                    logger.error(
                        f"[AB Expiry] Failed to trigger auto-complete for {test_id}: {e}"
                    )

        return {"checked": len(running), "triggered": triggered}

    except Exception as e:
        logger.error(f"check_ab_test_expiry failed: {e}")
        return {"error": str(e)}


# ============================================================
# TASK: auto_complete_ab_test
# ============================================================


@celery_app.task(
    bind=True,
    queue="ab_tests",
    name="tasks.auto_complete_ab_test",
)
def auto_complete_ab_test(self, test_id: str):
    """Auto-complete a test after its configured duration expires."""
    try:
        from routes.ab_testing import calculate_test_results, determine_winner
        import asyncio

        col = get_sync_ab_tests_collection()
        test = col.find_one({"_id": ObjectId(test_id)})
        if not test or test.get("status") not in ("running",):
            return {"skipped": True, "reason": "not_running"}

        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(calculate_test_results(test_id))
            winner = determine_winner(results, test.get("winner_criteria", "open_rate"))
        finally:
            loop.close()

        col.update_one(
            {"_id": ObjectId(test_id)},
            {
                "$set": {
                    "status": "completed",
                    "end_date": datetime.utcnow(),
                    "winner": winner,
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        logger.info(f"[AB AutoComplete] Test {test_id} completed. Winner: {winner}")

        winner_variant = winner.get("winner") if isinstance(winner, dict) else winner
        if (
            test.get("auto_send_winner", True)
            and winner_variant
            and winner_variant != "TIE"
        ):
            try:
                from tasks.ab.winner_send import send_winner_to_remaining
                send_winner_to_remaining.apply_async(
                    args=[test_id, winner_variant],
                    countdown=5,
                )
                logger.info(
                    f"[AB AutoComplete] send_winner_to_remaining queued for "
                    f"test {test_id}, variant {winner_variant}"
                )
            except Exception as _we:
                logger.error(
                    f"[AB AutoComplete] Failed to queue winner send for {test_id}: {_we}"
                )

        return {"completed": True, "test_id": test_id, "winner": winner}

    except Exception as e:
        logger.error(f"auto_complete_ab_test failed for {test_id}: {e}")
        return {"error": str(e)}