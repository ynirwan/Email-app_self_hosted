# backend/tasks/automation/automation_email_tasks.py
"""
Automation-specific email sending task.

Key design decisions vs original:
  - Send path: email_provider_manager.send_email_with_failover() — same backend
    used by campaign tasks. Gives failover, circuit breaker, rate limiting, and
    SES configuration set header automatically.
  - Rendering: template_renderer.personalize_template() — full Jinja2 stack with
    fault-isolated block rendering, pipe-header normalization, and dot-notation
    expansion. Replaces the old {{ }} string.replace() approach.
  - Tracking: same open pixel injection and link rewriting as send_single_campaign_email.
  - Unsubscribe: per-send token generated and injected as {{unsubscribe_url}} and
    List-Unsubscribe header.
  - Duplicate-send guard: checks email_logs for (automation_rule_id, step_id,
    subscriber_id) before sending. Idempotent on Celery retry.
"""

import asyncio
import logging
from datetime import datetime
from bson import ObjectId

from celery import shared_task

from database import (
    get_sync_subscribers_collection,
    get_sync_templates_collection,
    get_sync_email_logs_collection,
    get_sync_suppressions_collection,
)

logger = logging.getLogger(__name__)


@shared_task(
    name="tasks.send_automation_email",
    bind=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=3600,
)
def send_automation_email(
    self,
    subscriber_id: str,
    template_id: str,
    automation_rule_id: str,
    step_id: str,
    workflow_instance_id: str,
    email_config: dict,
    field_map: dict = None,
    fallback_values: dict = None,
):
    """
    Send one automation email to one subscriber.

    Idempotent: a (automation_rule_id, step_id, subscriber_id) pair that has
    already been sent will be skipped on retry without double-sending.

    Args:
        subscriber_id:        MongoDB ObjectId string for the subscriber.
        template_id:          MongoDB ObjectId string for the email template.
        automation_rule_id:   The parent automation rule ID (for log correlation).
        step_id:              The automation step ID (used for dedup key).
        workflow_instance_id: The active workflow instance ID.
        email_config:         Dict with keys: from_email, from_name, reply_to, subject.
        field_map:            {template_field: subscriber_field} mapping (optional).
        fallback_values:      {template_field: default_value} fallbacks (optional).

    Returns:
        Dict with status, email_log_id, message_id, subscriber_email.
    """
    field_map = field_map or {}
    fallback_values = fallback_values or {}

    try:
        subscribers_collection = get_sync_subscribers_collection()
        templates_collection = get_sync_templates_collection()
        email_logs_collection = get_sync_email_logs_collection()
        suppressions_collection = get_sync_suppressions_collection()

        logger.info(
            "send_automation_email started",
            extra={
                "automation_rule_id": automation_rule_id,
                "step_id": step_id,
                "subscriber_id": subscriber_id,
                "workflow_instance_id": workflow_instance_id,
                "task_id": self.request.id,
            },
        )

        # ── STEP 1: DUPLICATE-SEND GUARD ─────────────────────────────────────
        # One sent log per (rule, step, subscriber) is the idempotency contract.
        # Check before fetching subscriber/template to keep retries cheap.
        already_sent = email_logs_collection.find_one(
            {
                "automation_rule_id": automation_rule_id,
                "automation_step_id": step_id,
                "subscriber_id": subscriber_id,
                "status": {"$in": ["sent", "delivered"]},
            },
            {"_id": 1},
        )
        if already_sent:
            logger.info(
                "Skipping — already sent for this step",
                extra={
                    "automation_rule_id": automation_rule_id,
                    "step_id": step_id,
                    "subscriber_id": subscriber_id,
                },
            )
            return {"status": "skipped", "reason": "already_sent"}

        # ── STEP 2: SUBSCRIBER ───────────────────────────────────────────────
        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not subscriber:
            logger.error("Subscriber not found: %s", subscriber_id)
            return {"status": "error", "error": "subscriber_not_found"}

        subscriber_email = subscriber.get("email")
        if not subscriber_email:
            return {"status": "error", "error": "subscriber_email_missing"}

        # ── STEP 3: SUBSCRIBER STATUS ────────────────────────────────────────
        if subscriber.get("status") != "active":
            logger.info(
                "Subscriber not active, skipping",
                extra={
                    "subscriber_id": subscriber_id,
                    "status": subscriber.get("status"),
                },
            )
            return {"status": "skipped", "reason": "subscriber_not_active"}

        # ── STEP 4: SUPPRESSION CHECK ────────────────────────────────────────
        if suppressions_collection.find_one(
            {"email": subscriber_email, "is_active": True}
        ):
            logger.info("Subscriber suppressed: %s", subscriber_email)
            return {"status": "skipped", "reason": "subscriber_suppressed"}

        # ── STEP 5: TEMPLATE ─────────────────────────────────────────────────
        template = templates_collection.find_one({"_id": ObjectId(template_id)})
        if not template:
            logger.error("Template not found: %s", template_id)
            return {"status": "error", "error": "template_not_found"}

        # ── STEP 6: PERSONALIZATION CONTEXT ─────────────────────────────────
        # Build context the same way send_single_campaign_email does so
        # automation subscribers get identical rendering quality.
        standard_fields = subscriber.get("standard_fields", {})
        custom_fields = subscriber.get("custom_fields", {})

        # Base context: email + all subscriber fields
        personalization_context = {
            "email": subscriber_email,
            "subscriber_id": str(subscriber.get("_id", "")),
            "current_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "current_year": str(datetime.utcnow().year),
            "sent_at": datetime.utcnow().strftime("%B %d, %Y"),
            **standard_fields,
            **custom_fields,
        }

        # Apply field_map (template_field → subscriber_field path)
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
                value = subscriber_email
            elif mapped_field.startswith("standard."):
                value = standard_fields.get(mapped_field.replace("standard.", ""), "")
            elif mapped_field.startswith("custom."):
                value = custom_fields.get(mapped_field.replace("custom.", ""))
            else:
                value = fallback_values.get(template_field, "")

            personalization_context[template_field] = value if value is not None else ""

        # Apply fallbacks for any template field not yet set
        for key, value in fallback_values.items():
            if key not in personalization_context:
                personalization_context[key] = value

        # ── STEP 7: UNSUBSCRIBE TOKEN ────────────────────────────────────────
        unsub_url = "#"
        try:
            from routes.unsubscribe import (
                generate_unsubscribe_token,
                build_unsubscribe_url,
            )

            unsub_token = generate_unsubscribe_token(
                automation_rule_id, subscriber_id, subscriber_email
            )
            unsub_url = build_unsubscribe_url(unsub_token)
        except Exception as _unsub_err:
            logger.warning("Failed to generate unsubscribe token: %s", _unsub_err)

        personalization_context["unsubscribe_url"] = unsub_url

        # ── STEP 8: OPEN TRACKING TOKEN ──────────────────────────────────────
        open_token = None
        open_enabled = True
        click_enabled = True
        try:
            from routes.tracking import (
                generate_tracking_token,
                build_open_pixel_url,
                get_tracking_flags_sync,
            )

            flags = get_tracking_flags_sync()
            open_enabled = flags.get("open_tracking_enabled", True)
            click_enabled = flags.get("click_tracking_enabled", True)

            if open_enabled or click_enabled:
                open_token = generate_tracking_token(
                    automation_rule_id, subscriber_id, subscriber_email
                )

            personalization_context["open_tracking_url"] = (
                build_open_pixel_url(open_token) if open_enabled and open_token else ""
            )
        except Exception as _ot_err:
            logger.warning("Failed to generate tracking token: %s", _ot_err)
            personalization_context["open_tracking_url"] = ""

        # ── STEP 9: TEMPLATE RENDERING (full Jinja2 stack) ───────────────────
        from tasks.campaign.template_renderer import template_renderer

        # Build the template dict in the shape TemplateRenderer expects
        template_for_render = {
            "html_content": template.get("html_content", ""),
            "text_content": template.get("text_content", ""),
            "subject": email_config.get("subject") or template.get("subject", ""),
        }

        # If template stores content in content_json (drag-drop / visual), extract HTML
        if not template_for_render["html_content"] and template.get("content_json"):
            try:
                from tasks.campaign.snapshot_utils import (
                    _extract_html_from_content_json,
                )

                template_for_render["html_content"] = _extract_html_from_content_json(
                    template["content_json"]
                )
            except Exception as _ex_err:
                logger.warning("content_json extraction failed: %s", _ex_err)

        if not template_for_render["html_content"]:
            logger.error("Template %s has no renderable HTML", template_id)
            return {"status": "error", "error": "template_no_html"}

        personalized = template_renderer.personalize_template(
            template_for_render,
            subscriber,
            personalization_context,
        )

        if "error" in personalized and not personalized.get("html_content"):
            logger.error("Template rendering failed: %s", personalized["error"])
            return {"status": "error", "error": "template_render_failed"}

        html_to_send = personalized["html_content"]

        # ── STEP 10: INJECT PIXEL + REWRITE LINKS ────────────────────────────
        if open_token and html_to_send:
            try:
                from routes.tracking import (
                    rewrite_links_for_tracking,
                    build_open_pixel_url,
                    create_tracking_record,
                )

                if click_enabled:
                    html_to_send = rewrite_links_for_tracking(html_to_send, open_token)

                if open_enabled:
                    pixel = (
                        f'<img src="{build_open_pixel_url(open_token)}" '
                        f'width="1" height="1" alt="" style="display:none;border:0;" />'
                    )
                    if "</body>" in html_to_send:
                        html_to_send = html_to_send.replace(
                            "</body>", pixel + "</body>", 1
                        )
                    else:
                        html_to_send += pixel

                # Register the tracking record so opens/clicks can be attributed
                try:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(
                        create_tracking_record(
                            automation_rule_id,
                            subscriber_id,
                            subscriber_email,
                            open_token,
                        )
                    )
                    loop.close()
                except Exception as _te:
                    logger.warning("create_tracking_record failed: %s", _te)

            except Exception as _lre:
                logger.warning("Tracking inject/rewrite failed: %s", _lre)

        # ── STEP 11: SEND ─────────────────────────────────────────────────────
        from tasks.campaign.provider_manager import email_provider_manager

        sender_email = email_config.get("from_email", "")
        sender_name = email_config.get("from_name", "")
        reply_to = email_config.get("reply_to") or sender_email
        final_subject = email_config.get("subject") or template.get(
            "subject", "No Subject"
        )

        # SES configuration set — needed for bounce/open/click webhooks from SES
        from database import get_sync_settings_collection

        ses_configuration_set = None
        try:
            settings_doc = get_sync_settings_collection().find_one(
                {"type": "email_smtp"}
            )
            if settings_doc:
                ses_configuration_set = settings_doc.get("config", {}).get(
                    "ses_configuration_set"
                )
        except Exception:
            pass  # best-effort; missing config set doesn't block delivery

        send_result = email_provider_manager.send_email_with_failover(
            sender_email=f"{sender_name} <{sender_email}>"
            if sender_name
            else sender_email,
            recipient_email=subscriber_email,
            subject=final_subject,
            html_content=html_to_send,
            text_content=personalized.get("text_content"),
            campaign_id=automation_rule_id,  # used for circuit-breaker key only
            reply_to=reply_to,
            unsubscribe_url=unsub_url,
            configuration_set=ses_configuration_set,
        )

        # ── STEP 12: LOG RESULT ───────────────────────────────────────────────
        sent_ok = send_result.get("success", False)
        status_str = "sent" if sent_ok else "failed"

        email_log = {
            "_id": ObjectId(),
            "subscriber_id": subscriber_id,
            "subscriber_email": subscriber_email,
            "campaign_id": None,  # automation emails have no campaign_id
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "workflow_instance_id": workflow_instance_id,
            "template_id": template_id,
            "subject": final_subject,
            "from_email": sender_email,
            "status": status_str,
            "latest_status": status_str,
            "message_id": send_result.get("message_id"),
            "provider": send_result.get("selected_provider"),
            "sent_at": datetime.utcnow() if sent_ok else None,
            "error_message": send_result.get("error") if not sent_ok else None,
            "metadata": {
                "type": "automation",
                "automation_rule_id": automation_rule_id,
                "automation_step_id": step_id,
                "workflow_instance_id": workflow_instance_id,
                "template_id": template_id,
                "subscriber_id": subscriber_id,
            },
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        email_logs_collection.insert_one(email_log)

        if sent_ok:
            logger.info(
                "Automation email sent",
                extra={
                    "subscriber_email": subscriber_email,
                    "automation_rule_id": automation_rule_id,
                    "step_id": step_id,
                    "message_id": send_result.get("message_id"),
                    "provider": send_result.get("selected_provider"),
                },
            )
            return {
                "status": "success",
                "email_log_id": str(email_log["_id"]),
                "message_id": send_result.get("message_id"),
                "subscriber_email": subscriber_email,
                "provider": send_result.get("selected_provider"),
            }
        else:
            logger.warning(
                "Automation email send failed",
                extra={
                    "subscriber_email": subscriber_email,
                    "automation_rule_id": automation_rule_id,
                    "step_id": step_id,
                    "error": send_result.get("error"),
                },
            )
            raise self.retry(
                exc=Exception(send_result.get("error", "provider send failed")),
            )

    except Exception as exc:
        logger.error(
            "send_automation_email exception",
            extra={
                "subscriber_id": subscriber_id,
                "automation_rule_id": automation_rule_id,
                "step_id": step_id,
                "error": str(exc),
                "retry": self.request.retries,
            },
            exc_info=True,
        )
        raise self.retry(exc=exc)
