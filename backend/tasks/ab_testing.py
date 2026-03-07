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
            "success":
            True,
            "variant_a_processed":
            variant_a_results["processed"],
            "variant_b_processed":
            variant_b_results["processed"],
            "total_queued":
            (variant_a_results["processed"] + variant_b_results["processed"]),
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
        return {
            "processed": len(subscribers),
            "suppressed": 0,
            "task_ids": task_ids
        }
    except Exception as e:
        logger.error(
            f"Variant processing failed: {test_id} {variant_name}, error: {e}")
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
        col_templates = get_sync_templates_collection()
        col_settings = get_sync_settings_collection()

        test = col_tests.find_one({"_id": ObjectId(test_id)})
        if not test:
            raise Exception(f"A/B test not found: {test_id}")

        template = None
        if test.get("template_id"):
            template = col_templates.find_one(
                {"_id": ObjectId(test["template_id"])})

        subject = variant_config.get("subject") or test.get("subject", "")
        sender_name = variant_config.get("sender_name") or test.get(
            "sender_name", "")
        sender_email = variant_config.get("sender_email") or test.get(
            "sender_email", "")
        reply_to = (variant_config.get("reply_to")
                    or test.get("reply_to", sender_email))

        html_content = ""
        if template:
            html_content = (template.get("html_content", "")
                            or template.get("content", ""))
            first_name = subscriber.get("first_name", "")
            email = subscriber.get("email", "")
            custom_fields = subscriber.get("custom_fields", {})

            html_content = html_content.replace("{{first_name}}", first_name)
            html_content = html_content.replace("{{email}}", email)
            html_content = html_content.replace("{{subject}}", subject)
            for k, v in custom_fields.items():
                html_content = html_content.replace(f"{{{{{k}}}}}", str(v))

        if not html_content:
            html_content = (f"<html><body><p>Hello "
                            f"{subscriber.get('first_name', 'there')},</p>"
                            f"<p>{subject}</p></body></html>")

        email_service = get_email_service_sync(col_settings)
        result = email_service.send_email(
            sender_email=sender_email,
            recipient_email=subscriber["email"],
            subject=subject,
            html_content=html_content,
            sender_name=sender_name,
            reply_to=reply_to,
        )

        message_id = (getattr(result, "message_id", None)
                      or getattr(result, "MessageId", None))

        if getattr(result, "success", False):
            ab_test_results_collection.insert_one({
                "test_id":
                test_id,
                "variant":
                variant,
                "subscriber_id":
                str(subscriber.get("_id") or subscriber.get("id", "")),
                "subscriber_email":
                subscriber["email"],
                "email_sent":
                True,
                "sent_at":
                datetime.utcnow(),
                "message_id":
                message_id,
                "email_opened":
                False,
                "email_clicked":
                False,
                "conversion":
                False,
            })
            logger.info(
                f"A/B email sent: {test_id} {variant} {subscriber['email']}")
        else:
            raise Exception(getattr(result, "error", "Send failed"))

    except Exception as e:
        ab_test_results_collection.insert_one({
            "test_id":
            test_id,
            "variant":
            variant,
            "subscriber_id":
            str(subscriber.get("_id") or subscriber.get("id", "")),
            "subscriber_email":
            subscriber["email"],
            "email_sent":
            False,
            "error":
            str(e),
            "sent_at":
            datetime.utcnow(),
        })
        logger.error(f"A/B email failed: {test_id} {variant} "
                     f"{subscriber.get('email', '?')}: {e}")
        raise


# ============================================================
# TASK: check_ab_test_expiry  (Celery Beat — every 15 min)
# Finds running tests whose duration has elapsed and fires
# auto_complete_ab_test for each one.
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

            elapsed = (now - start_date).total_seconds() / 3600
            if elapsed < duration_hours:
                logger.debug(f"[AB Expiry] {test_id} not expired "
                             f"({elapsed:.1f}h / {duration_hours}h)")
                continue

            logger.info(f"[AB Expiry] {test_id} expired — auto-completing")
            auto_complete_ab_test.delay(
                test_id=test_id,
                apply_to_campaign=test.get("auto_send_winner", True),
            )
            triggered += 1

        return {"checked": len(running), "triggered": triggered}

    except Exception as e:
        logger.error(f"[AB Expiry] check_ab_test_expiry failed: {e}")
        return {"error": str(e)}


# ============================================================
# TASK: auto_complete_ab_test
# Declare winner, mark completed, apply to campaign if needed.
# ============================================================


@celery_app.task(
    bind=True,
    queue="ab_tests",
    name="tasks.auto_complete_ab_test",
)
def auto_complete_ab_test(self, test_id: str, apply_to_campaign: bool = True):
    try:
        # Import here to avoid circular imports at module load
        from routes.ab_testing import (
            calculate_test_results_sync,
            determine_winner,
            apply_winner_to_campaign_sync,
        )

        col = get_sync_ab_tests_collection()
        test = col.find_one({"_id": ObjectId(test_id)})
        if not test:
            logger.error(f"[AB Complete] Test {test_id} not found")
            return {"success": False, "error": "not_found"}

        if test["status"] == "completed":
            logger.info(f"[AB Complete] {test_id} already completed, skipping")
            return {"success": True, "skipped": True}

        results = calculate_test_results_sync(test_id)
        winner = determine_winner(results,
                                  test.get("winner_criteria", "open_rate"))

        col.update_one(
            {"_id": ObjectId(test_id)},
            {
                "$set": {
                    "status": "completed",
                    "end_date": datetime.utcnow(),
                    "winner_variant": winner.get("winner"),
                    "winner_improvement": winner.get("improvement", 0),
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        logger.info(f"[AB Complete] {test_id} completed — "
                    f"winner={winner.get('winner')}, "
                    f"improvement={winner.get('improvement')}%")

        campaign_applied = False
        if (apply_to_campaign and test.get("campaign_id")
                and winner.get("winner") != "TIE"):
            apply_winner_to_campaign_sync(test_id, str(test["campaign_id"]),
                                          winner["winner"])
            campaign_applied = True

        return {
            "success": True,
            "test_id": test_id,
            "winner": winner.get("winner"),
            "improvement": winner.get("improvement"),
            "campaign_applied": campaign_applied,
        }

    except Exception as e:
        logger.error(
            f"[AB Complete] auto_complete_ab_test failed for {test_id}: {e}")
        return {"success": False, "error": str(e)}
