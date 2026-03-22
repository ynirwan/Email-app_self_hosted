# backend/tasks/ab_testing.py
# ============================================================
# FULL REPLACEMENT FILE
#
# KEY CHANGES vs original:
#   1. send_ab_test_single_email reads html_content from
#      test["content_snapshot"] (written at start_ab_test time).
#      Falls back to live template fetch if snapshot absent
#      (backward compatibility for existing running tests).
#   3. All other tasks (batch, expiry, auto_complete) unchanged.
# ============================================================

import logging
from datetime import datetime
from bson import ObjectId

from database import (
    get_sync_subscribers_collection,
    get_sync_templates_collection,
    get_sync_ab_tests_collection,
    get_sync_ab_test_results_collection,
    get_sync_settings_collection,
)
from routes.smtp_services.email_service_factory import get_email_service_sync
from celery_app import celery_app
from tasks.campaign.template_renderer import template_renderer

logger = logging.getLogger(__name__)


# ============================================================
# TASK: send_ab_test_batch
# Dispatches individual-email tasks for both variants.
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
        col_settings = get_sync_settings_collection()

        # ── Fetch test (projection: only what we need) ───────────────────────
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
                "content_snapshot": 1,  # ← snapshot written at start_ab_test
            },
        )
        if not test:
            raise Exception(f"A/B test not found: {test_id}")

        # ── Resolve per-variant overrides ────────────────────────────────────
        subject = variant_config.get("subject") or test.get("subject", "")
        sender_name = variant_config.get("sender_name") or test.get("sender_name", "")
        sender_email = variant_config.get("sender_email") or test.get(
            "sender_email", ""
        )
        reply_to = variant_config.get("reply_to") or test.get("reply_to", sender_email)

        # ── Resolve html_content from snapshot (preferred) ──────────────────
        snap = test.get("content_snapshot")
        html_content = ""

        if snap:
            # Happy path: snapshot was written at start_ab_test
            html_content = snap.get("html_content", "")
            # If the variant overrides the subject, that's already handled above.
            # field_map / fallback from snapshot
            field_map = snap.get("field_map", test.get("field_map", {}))
            fallback_values = snap.get(
                "fallback_values", test.get("fallback_values", {})
            )
            logger.debug(
                f"AB test {test_id}/{variant}: using snapshot html ({len(html_content)} bytes)"
            )

        else:
            # Fallback: snapshot absent (old test started before this deploy)
            # Fetch live template — same as original behaviour
            field_map = test.get("field_map", {})
            fallback_values = test.get("fallback_values", {})
            logger.warning(
                f"AB test {test_id}: no content_snapshot found, "
                "falling back to live template fetch"
            )
            col_templates = get_sync_templates_collection()
            if test.get("template_id"):
                tmpl = col_templates.find_one({"_id": ObjectId(test["template_id"])})
                if tmpl:
                    html_content = tmpl.get("html_content", "") or tmpl.get(
                        "content", ""
                    )

        # ── Personalise html_content ─────────────────────────────────────────
        if html_content:
            first_name = subscriber.get("first_name", "") or subscriber.get(
                "standard_fields", {}
            ).get("first_name", "")
            email = subscriber.get("email", "")
            custom_fields = subscriber.get("custom_fields", {})

            # Apply explicit field_map first
            import re

            for template_field, mapped_field in field_map.items():
                value = ""
                if mapped_field == "__EMPTY__":
                    value = ""
                elif mapped_field == "__DEFAULT__":
                    value = fallback_values.get(template_field, "")
                elif mapped_field == "email":
                    value = email
                elif mapped_field.startswith("standard."):
                    field_name = mapped_field.replace("standard.", "")
                    value = subscriber.get("standard_fields", {}).get(field_name, "")
                elif mapped_field.startswith("custom."):
                    field_name = mapped_field.replace("custom.", "")
                    value = str(custom_fields.get(field_name, ""))
                else:
                    value = fallback_values.get(template_field, "")
                html_content = html_content.replace(
                    f"{{{{{template_field}}}}}", str(value)
                )

            # Convenience replacements for unmapped common fields
            html_content = html_content.replace("{{first_name}}", first_name)
            html_content = html_content.replace("{{email}}", email)
            html_content = html_content.replace("{{subject}}", subject)

            # Any remaining custom fields
            for k, v in custom_fields.items():
                html_content = html_content.replace(f"{{{{{k}}}}}", str(v))

        # Fallback body if still empty
        if not html_content:
            html_content = (
                f"<html><body>"
                f"<p>Hello {subscriber.get('first_name', 'there')},</p>"
                f"<p>{subject}</p>"
                f"</body></html>"
            )

        # ── Send ─────────────────────────────────────────────────────────────
        email_service = get_email_service_sync(col_settings)
        result = email_service.send_email(
            sender_email=sender_email,
            recipient_email=subscriber["email"],
            subject=subject,
            html_content=html_content,
            sender_name=sender_name,
            reply_to=reply_to,
        )

        message_id = getattr(result, "message_id", None) or getattr(
            result, "MessageId", None
        )

        if getattr(result, "success", False):
            ab_test_results_collection.insert_one(
                {
                    "test_id": test_id,
                    "variant": variant,
                    "subscriber_id": str(
                        subscriber.get("_id") or subscriber.get("id", "")
                    ),
                    "subscriber_email": subscriber["email"],
                    "email_sent": True,
                    "sent_at": datetime.utcnow(),
                    "message_id": message_id,
                    "email_opened": False,
                    "email_clicked": False,
                    "conversion": False,
                }
            )
            logger.info(f"A/B email sent: {test_id} {variant} {subscriber['email']}")
        else:
            raise Exception(getattr(result, "error", "Send failed"))

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
        if not test or test.get("status") != "running":
            return {"skipped": True, "reason": "not_running"}

        # Calculate results synchronously
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
        return {"completed": True, "test_id": test_id, "winner": winner}

    except Exception as e:
        logger.error(f"auto_complete_ab_test failed for {test_id}: {e}")
        return {"error": str(e)}
