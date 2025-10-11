import logging
from datetime import datetime
from bson import ObjectId
from database_sync import (
    get_sync_campaigns_collection,
    get_sync_subscribers_collection, 
    get_sync_templates_collection,
    get_sync_ab_tests_collection,
    get_sync_ab_test_results_collection,
    get_sync_settings_collection
)
from routes.smtp_services.email_campaign_processor import SyncEmailCampaignProcessor
from routes.smtp_services.email_service_factory import get_email_service_sync
from celery_app import celery_app

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, queue="ab_tests", name="tasks.send_ab_test_batch")
def send_ab_test_batch(self, test_id: str, variant_assignments: dict):
    """Send A/B test emails using existing campaign infrastructure"""
    try:
        ab_tests_collection = get_sync_ab_tests_collection()
        campaigns_collection = get_sync_campaigns_collection()
        
        test = ab_tests_collection.find_one({"_id": ObjectId(test_id)})
        if not test:
            logger.error(f"A/B test not found: {test_id}")
            return {"success": False, "error": "Test not found"}
        
        campaign = campaigns_collection.find_one({"_id": test["campaign_id"]})
        if not campaign:
            logger.error(f"Campaign not found: {test['campaign_id']}")
            return {"success": False, "error": "Campaign not found"}
        
        # Process Variant A
        variant_a_results = process_variant_emails(
            test_id, "A", test["variants"][0], 
            variant_assignments["A"], campaign, test
        )
        
        # Process Variant B  
        variant_b_results = process_variant_emails(
            test_id, "B", test["variants"][1],
            variant_assignments["B"], campaign, test
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
                          subscribers: list, base_campaign: dict, test_config: dict):
    """Process emails for a single variant"""
    try:
        task_ids = []
        for subscriber in subscribers:
            task = send_ab_test_single_email.apply_async(
                args=[test_id, variant_name, variant_config, subscriber, base_campaign],
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
                             subscriber: dict, base_campaign: dict):
    """Send individual A/B test email"""
    try:
        ab_test_results_collection = get_sync_ab_test_results_collection()
        templates_collection = get_sync_templates_collection()
        
        campaign_variant = create_campaign_variant(base_campaign, variant_config)
        
        processor = SyncEmailCampaignProcessor(
            campaigns_collection=get_sync_campaigns_collection(),
            templates_collection=templates_collection,
            subscribers_collection=get_sync_subscribers_collection()
        )
        
        email_content = processor.prepare_email_content(campaign_variant, subscriber)
        
        if not email_content.get("html_content") or not email_content.get("recipient_email"):
            raise Exception("Invalid email content generated")
        
        settings_collection = get_sync_settings_collection()
        email_service = get_email_service_sync(settings_collection)
        
        result = email_service.send_email(
            sender_email=campaign_variant.get("sender_email"),
            recipient_email=email_content["recipient_email"],
            subject=email_content["subject"],
            html_content=email_content["html_content"],
            sender_name=campaign_variant.get("sender_name"),
            reply_to=campaign_variant.get("reply_to")
        )
        
        message_id = getattr(result, "message_id", None) or getattr(result, "MessageId", None)
        
        if getattr(result, "success", False):
            ab_test_results_collection.insert_one({
                "test_id": test_id,
                "variant": variant,
                "subscriber_id": str(subscriber.get("_id")),
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
            "subscriber_id": str(subscriber.get("_id")),
            "subscriber_email": subscriber["email"],
            "email_sent": False,
            "error": str(e),
            "sent_at": datetime.utcnow()
        })
        logger.error(f"A/B test email failed: {test_id} {variant} {subscriber['email']}: {e}")
        raise

def create_campaign_variant(base_campaign: dict, variant_config: dict) -> dict:
    """Create campaign variant by merging base campaign with variant config"""
    campaign_variant = base_campaign.copy()
    
    if variant_config.get("subject"):
        campaign_variant["subject"] = variant_config["subject"]
    if variant_config.get("sender_name"):
        campaign_variant["sender_name"] = variant_config["sender_name"]
    if variant_config.get("sender_email"):
        campaign_variant["sender_email"] = variant_config["sender_email"]
    if variant_config.get("reply_to"):
        campaign_variant["reply_to"] = variant_config["reply_to"]
    
    return campaign_variant

