# backend/tasks/ab/ab_testing.py
"""
A/B test email sending tasks.

Changes vs previous version:
  - Added error_classifier integration
  - _handle_ab_test_level_failure(): atomic Redis NX + Mongo auto-fail
  - _check_ab_test_abort(): cheap Redis abort flag read per task
  - Pre-flight provider check in send_ab_test_batch
  - CONFIG/LIMIT errors → status=failed (A/B tests are terminal, no pause/resume)
  - TRANSIENT/UNKNOWN → existing retry path unchanged
"""

import logging
import json
import redis as _redis_module
from datetime import datetime
from bson import ObjectId

from database import (
    get_sync_subscribers_collection,
    get_sync_templates_collection,
    get_sync_ab_tests_collection,
    get_sync_ab_test_results_collection,
)
from tasks.campaign.provider_manager import email_provider_manager as _pm
from tasks.campaign.template_renderer import template_renderer
from celery_app import celery_app
from tasks.task_config import task_settings

# ── NEW: error classifier ────────────────────────────────────────────────────
from tasks.error_classifier import (
    classify_submission_error,
    extract_smtp_code,
    ProviderErrorClass,
)

logger = logging.getLogger(__name__)


# ============================================================
# ERROR HANDLING HELPERS (NEW)
# ============================================================


def _get_redis():
    return _redis_module.Redis.from_url(task_settings.REDIS_URL, decode_responses=True)


def _check_ab_test_abort(test_id: str) -> bool:
    """Return True if the A/B test abort flag is set in Redis."""
    try:
        return bool(_get_redis().exists(f"ab_test:abort:{test_id}"))
    except Exception:
        return False


def _handle_ab_test_level_failure(test_id: str, classification: dict) -> None:
    """
    Called when a CONFIG or LIMIT provider error is detected.
    A/B tests have no pause/resume — marks test as 'failed'.
    Uses Redis NX so only the first failing task writes the failure.
    """
    abort_key = f"ab_test:abort:{test_id}"
    try:
        r = _get_redis()
        was_set = r.set(
            abort_key,
            json.dumps(
                {
                    "error_class": classification["error_class"],
                    "detected_at": datetime.utcnow().isoformat(),
                }
            ),
            ex=86400,
            nx=True,
        )
    except Exception as redis_err:
        logger.warning(
            f"Redis abort flag write failed for ab_test {test_id}: {redis_err}"
        )
        was_set = True

    if not was_set:
        return  # Another task already handled this

    provider_error = {
        "error_class": classification["error_class"],
        "error_type": classification["error_type"],
        "smtp_code": extract_smtp_code(classification["raw_message"]),
        "raw_message": classification["raw_message"],
        "human_message": classification["human_message"],
        "is_resumable": classification["is_resumable"],
        "detected_at": datetime.utcnow(),
        "auto_failed": True,
    }

    col = get_sync_ab_tests_collection()
    col.update_one(
        {"_id": ObjectId(test_id), "status": "running"},
        {
            "$set": {
                "status": "failed",
                "failed_at": datetime.utcnow(),
                "fail_reason": "provider_error_auto_fail",
                "provider_error": provider_error,
                "updated_at": datetime.utcnow(),
            }
        },
    )

    logger.error(
        f"A/B test {test_id} auto-failed — "
        f"{classification['error_type']}: {classification['raw_message']}"
    )


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

        # ── PRE-FLIGHT: verify provider is available (NEW) ─────────────────────
        if not _pm.get_best_provider(test_id):
            _cls = classify_submission_error("no healthy email providers available")
            _handle_ab_test_level_failure(test_id, _cls)
            logger.error(
                f"A/B test {test_id} aborted at pre-flight: no healthy providers"
            )
            return {"success": False, "error": "no_healthy_providers"}

        variant_a_results = process_variant_emails(
            test_id, "A", test["variants"][0], variant_assignments["A"], test
        )
        variant_b_results = process_variant_emails(
            test_id, "B", test["variants"][1], variant_assignments["B"], test
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
            "total_queued": variant_a_results["processed"]
            + variant_b_results["processed"],
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
        # ── ABORT FLAG CHECK (NEW) ─────────────────────────────────────────────
        if _check_ab_test_abort(test_id):
            return {"skipped": True, "reason": "test_aborted"}

        col_tests = get_sync_ab_tests_collection()
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

        # ── Resolve sender + subject from variant_config or test defaults ──────
        subject = variant_config.get("subject") or test.get("subject", "")
        sender_name = variant_config.get("sender_name") or test.get("sender_name", "")
        sender_email = variant_config.get("sender_email") or test.get(
            "sender_email", ""
        )
        reply_to = variant_config.get("reply_to") or test.get("reply_to", sender_email)

        # ── Template / snapshot ───────────────────────────────────────────────
        snap = test.get("content_snapshot")
        if snap and snap.get("html_content"):
            html_content = snap["html_content"]
        else:
            tpl_id = test.get("template_id")
            if tpl_id:
                tpl_col = get_sync_templates_collection()
                template = tpl_col.find_one({"_id": ObjectId(tpl_id)})
                if not template:
                    raise Exception(f"Template not found: {tpl_id}")
                cj = template.get("content_json", {})
                html_content = template.get("html_content", "")
                if not html_content:
                    if cj.get("mode") == "html" and cj.get("content"):
                        html_content = cj["content"]
                    elif cj.get("mode") == "drag-drop" and cj.get("blocks"):
                        html_content = "\n".join(
                            b.get("content", "") for b in cj["blocks"]
                        )
                    elif cj.get("mode") == "visual" and cj.get("content"):
                        html_content = cj["content"]
            else:
                html_content = ""

        if not html_content:
            fn = subscriber.get("standard_fields", {}).get("first_name", "there")
            html_content = (
                f"<html><body><p>Hello {fn},</p><p>{subject}</p></body></html>"
            )

        # ── Subscriber fields ─────────────────────────────────────────────────
        email = subscriber.get("email", "")
        standard_fields = subscriber.get("standard_fields", {})
        custom_fields = subscriber.get("custom_fields", {})
        first_name = standard_fields.get("first_name", "")
        subscriber_id = str(subscriber.get("_id") or subscriber.get("id", ""))
        field_map = test.get("field_map", {})
        fallback_values = test.get("fallback_values", {})

        # ── Unsubscribe token ─────────────────────────────────────────────────
        unsub_url = "#"
        try:
            from routes.unsubscribe import (
                generate_unsubscribe_token,
                build_unsubscribe_url,
            )

            unsub_url = build_unsubscribe_url(
                generate_unsubscribe_token(test_id, subscriber_id, email)
            )
        except Exception as _ue:
            logger.warning(f"AB test unsubscribe token failed: {_ue}")

        html_content = html_content.replace("{{unsubscribe_url}}", unsub_url)

        # ── Tracking ──────────────────────────────────────────────────────────
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

        # ── Field map application ─────────────────────────────────────────────
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
                fn2 = mapped_field.replace("standard.", "")
                value = standard_fields.get(fn2, "") or fallback_values.get(
                    template_field, ""
                )
            elif mapped_field.startswith("custom."):
                fn2 = mapped_field.replace("custom.", "")
                value = str(custom_fields.get(fn2, "")) or fallback_values.get(
                    template_field, ""
                )
            else:
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

        html_content = html_content.replace("{{first_name}}", first_name)
        html_content = html_content.replace("{{email}}", email)
        html_content = html_content.replace("{{subject}}", subject)
        for k, v in custom_fields.items():
            html_content = html_content.replace(f"{{{{{k}}}}}", str(v))

        # ── Inject open pixel + rewrite links ─────────────────────────────────
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
                    html_content = (
                        html_content.replace("</body>", _pixel + "</body>", 1)
                        if "</body>" in html_content
                        else html_content + _pixel
                    )
            except Exception as _pe:
                logger.warning(f"AB test pixel injection failed: {_pe}")

        # ── Send ──────────────────────────────────────────────────────────────
        result = _pm.send_email_with_failover(
            sender_email=sender_email,
            recipient_email=email,
            subject=subject,
            html_content=html_content,
            sender_name=sender_name,
            reply_to=reply_to,
        )

        message_id = result.get("message_id")
        success = result.get("success", False)
        error_msg = result.get("error", "") if not success else None
        is_permanent = result.get("permanent_failure", False)

        if success:
            ab_test_results_collection.insert_one(
                {
                    "test_id": test_id,
                    "variant": variant,
                    "subscriber_id": subscriber_id,
                    "subscriber_email": email,
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
            logger.info(f"A/B email sent: {test_id} {variant} {email}")
            return {"status": "sent", "message_id": message_id}

        else:
            # ── FAILURE: classify and auto-fail on CONFIG/LIMIT (NEW) ─────────
            _cls = classify_submission_error(error_msg)
            if _cls["error_class"] in (
                ProviderErrorClass.CONFIG_ERROR,
                ProviderErrorClass.LIMIT_ERROR,
            ):
                _handle_ab_test_level_failure(test_id, _cls)
                ab_test_results_collection.insert_one(
                    {
                        "test_id": test_id,
                        "variant": variant,
                        "subscriber_id": subscriber_id,
                        "subscriber_email": email,
                        "email_sent": False,
                        "error": _cls["human_message"],
                        "sent_at": datetime.utcnow(),
                    }
                )
                return {
                    "status": "aborted",
                    "reason": f"test_auto_failed:{_cls['error_type']}",
                }

            # TRANSIENT/UNKNOWN — raise for existing retry path
            raise Exception(error_msg or "Provider returned failure")

    except Exception as e:
        # Already aborted?
        if _check_ab_test_abort(test_id):
            return {"skipped": True, "reason": "test_aborted_on_exception"}

        err_str = str(e)
        # Classify exception-form errors before retrying
        _cls = classify_submission_error(err_str)
        if _cls["error_class"] in (
            ProviderErrorClass.CONFIG_ERROR,
            ProviderErrorClass.LIMIT_ERROR,
        ):
            _handle_ab_test_level_failure(test_id, _cls)
            ab_test_results_collection.insert_one(
                {
                    "test_id": test_id,
                    "variant": variant,
                    "subscriber_id": str(
                        subscriber.get("_id") or subscriber.get("id", "")
                    ),
                    "subscriber_email": subscriber.get("email", ""),
                    "email_sent": False,
                    "error": _cls["human_message"],
                    "sent_at": datetime.utcnow(),
                }
            )
            return {
                "status": "aborted",
                "reason": f"test_auto_failed:{_cls['error_type']}",
            }

        ab_test_results_collection.insert_one(
            {
                "test_id": test_id,
                "variant": variant,
                "subscriber_id": str(subscriber.get("_id") or subscriber.get("id", "")),
                "subscriber_email": subscriber.get("email", ""),
                "email_sent": False,
                "error": err_str,
                "sent_at": datetime.utcnow(),
            }
        )
        logger.error(
            f"A/B email failed: {test_id} {variant} {subscriber.get('email', '?')}: {e}"
        )
        raise
