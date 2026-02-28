import logging
from datetime import datetime
from bson import ObjectId
from database import (
    get_sync_subscribers_collection, 
    get_sync_templates_collection,
    get_sync_ab_tests_collection,
    get_sync_ab_test_results_collection,
    get_sync_settings_collection
)
from routes.smtp_services.email_service_factory import get_email_service_sync
from celery_app import celery_app

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, queue="ab_tests", name="tasks.send_ab_test_batch")
def send_ab_test_batch(self, test_id: str, variant_assignments: dict):
    try:
        ab_tests_collection = get_sync_ab_tests_collection()
        
        test = ab_tests_collection.find_one({"_id": ObjectId(test_id)})
        if not test:
            logger.error(f"A/B test not found: {test_id}")
            return {"success": False, "error": "Test not found"}
        
        variant_a_results = process_variant_emails(
            test_id, "A", test["variants"][0], 
            variant_assignments["A"], test
        )
        
        variant_b_results = process_variant_emails(
            test_id, "B", test["variants"][1],
            variant_assignments["B"], test
        )
        
        ab_tests_collection.update_one(
            {"_id": ObjectId(test_id)},
            {
                "$set": {
                    "emails_queued_at": datetime.utcnow(),
                    "variant_a_queued": len(variant_assignments["A"]),
                    "variant_b_queued": len(variant_assignments["B"])
                }
            }
        )
        
        logger.info(f"A/B test batch queued: {test_id}")
        
        return {
            "success": True,
            "variant_a_processed": variant_a_results["processed"],
            "variant_b_processed": variant_b_results["processed"],
            "total_queued": variant_a_results["processed"] + variant_b_results["processed"]
        }
        
    except Exception as e:
        logger.error(f"A/B test batch failed: {test_id}, Error: {e}")
        return {"success": False, "error": str(e)}

def process_variant_emails(test_id: str, variant_name: str, variant_config: dict, 
                          subscribers: list, test_config: dict):
    try:
        task_ids = []
        for subscriber in subscribers:
            task = send_ab_test_single_email.apply_async(
                args=[test_id, variant_name, variant_config, subscriber],
                queue="ab_tests"
            )
            task_ids.append(task.id)
        
        return {
            "processed": len(subscribers),
            "suppressed": 0,
            "task_ids": task_ids
        }
        
    except Exception as e:
        logger.error(f"Variant processing failed: {test_id} {variant_name}, Error: {e}")
        return {"processed": 0, "suppressed": 0, "task_ids": []}

@celery_app.task(
    bind=True,
    max_retries=3,
    queue="ab_tests", 
    name="tasks.send_ab_test_single_email"
)
def send_ab_test_single_email(self, test_id: str, variant: str, variant_config: dict,
                             subscriber: dict):
    try:
        ab_tests_collection = get_sync_ab_tests_collection()
        ab_test_results_collection = get_sync_ab_test_results_collection()
        templates_collection = get_sync_templates_collection()
        
        test = ab_tests_collection.find_one({"_id": ObjectId(test_id)})
        if not test:
            raise Exception(f"A/B test not found: {test_id}")
        
        template = None
        if test.get("template_id"):
            template = templates_collection.find_one({"_id": ObjectId(test["template_id"])})
        
        subject = variant_config.get("subject") or test.get("subject", "")
        sender_name = variant_config.get("sender_name") or test.get("sender_name", "")
        sender_email = variant_config.get("sender_email") or test.get("sender_email", "")
        reply_to = variant_config.get("reply_to") or test.get("reply_to", sender_email)
        
        html_content = ""
        if template:
            html_content = template.get("html_content", "") or template.get("content", "")
            
            first_name = subscriber.get("first_name", "")
            email = subscriber.get("email", "")
            custom_fields = subscriber.get("custom_fields", {})
            
            html_content = html_content.replace("{{first_name}}", first_name)
            html_content = html_content.replace("{{email}}", email)
            html_content = html_content.replace("{{subject}}", subject)
            for key, value in custom_fields.items():
                html_content = html_content.replace(f"{{{{{key}}}}}", str(value))
        
        if not html_content:
            html_content = f"<html><body><p>Hello {subscriber.get('first_name', 'there')},</p><p>{subject}</p></body></html>"
        
        settings_collection = get_sync_settings_collection()
        email_service = get_email_service_sync(settings_collection)
        
        result = email_service.send_email(
            sender_email=sender_email,
            recipient_email=subscriber["email"],
            subject=subject,
            html_content=html_content,
            sender_name=sender_name,
            reply_to=reply_to
        )
        
        message_id = getattr(result, "message_id", None) or getattr(result, "MessageId", None)
        
        if getattr(result, "success", False):
            ab_test_results_collection.insert_one({
                "test_id": test_id,
                "variant": variant,
                "subscriber_id": str(subscriber.get("_id") or subscriber.get("id", "")),
                "subscriber_email": subscriber["email"],
                "email_sent": True,
                "sent_at": datetime.utcnow(),
                "message_id": message_id,
                "email_opened": False,
                "email_clicked": False,
                "conversion": False
            })
            logger.info(f"A/B test email sent: {test_id} {variant} {subscriber['email']}")
        else:
            raise Exception(getattr(result, "error", "Send failed"))
            
    except Exception as e:
        ab_test_results_collection = get_sync_ab_test_results_collection()
        ab_test_results_collection.insert_one({
            "test_id": test_id,
            "variant": variant, 
            "subscriber_id": str(subscriber.get("_id") or subscriber.get("id", "")),
            "subscriber_email": subscriber["email"],
            "email_sent": False,
            "error": str(e),
            "sent_at": datetime.utcnow()
        })
        logger.error(f"A/B test email failed: {test_id} {variant} {subscriber['email']}: {e}")
        raise
