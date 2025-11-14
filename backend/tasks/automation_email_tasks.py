# backend/tasks/automation_email_tasks.py
"""
Automation-specific email sending tasks based on campaign email infrastructure
"""
from celery import shared_task
from datetime import datetime
from bson import ObjectId
import logging

from database import (
    get_sync_subscribers_collection,
    get_sync_templates_collection,
    get_sync_email_logs_collection,
    get_sync_suppressions_collection
)

logger = logging.getLogger(__name__)


@shared_task(
    name="tasks.send_automation_email",
    bind=True,
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=3600
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
    fallback_values: dict = None
):
    """
    Send automation email to a single subscriber
    Based on send_single_campaign_email but optimized for automation workflows
    
    Args:
        subscriber_id: Subscriber ID
        template_id: Email template ID
        automation_rule_id: Automation rule ID
        step_id: Automation step ID
        workflow_instance_id: Workflow instance ID
        email_config: Email configuration (from_email, from_name, reply_to, subject)
        field_map: Field mapping for personalization
        fallback_values: Fallback values for missing fields
    """
    try:
        subscribers_collection = get_sync_subscribers_collection()
        templates_collection = get_sync_templates_collection()
        email_logs_collection = get_sync_email_logs_collection()
        suppressions_collection = get_sync_suppressions_collection()
        
        logger.info(f"📧 Starting automation email send for subscriber {subscriber_id}")
        
        # Get subscriber
        subscriber = subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not subscriber:
            logger.error(f"Subscriber not found: {subscriber_id}")
            return {"status": "error", "error": "Subscriber not found"}
        
        subscriber_email = subscriber.get("email")
        
        # Check if subscriber is active
        if subscriber.get("status") != "active":
            logger.warning(f"Subscriber {subscriber_email} is not active")
            return {"status": "skipped", "reason": "subscriber_not_active"}
        
        # Check suppression
        is_suppressed = suppressions_collection.find_one({
            "email": subscriber_email,
            "is_active": True
        })
        
        if is_suppressed:
            logger.warning(f"Subscriber {subscriber_email} is suppressed")
            return {"status": "skipped", "reason": "subscriber_suppressed"}
        
        # Get template
        template = templates_collection.find_one({"_id": ObjectId(template_id)})
        if not template:
            logger.error(f"Template not found: {template_id}")
            return {"status": "error", "error": "Template not found"}
        
        # Prepare personalization data
        personalization_data = {
            "email": subscriber_email,
            **subscriber.get("standard_fields", {}),
            **subscriber.get("custom_fields", {})
        }
        
        # Apply field mapping
        mapped_data = {}
        if field_map:
            for target_field, source_field in field_map.items():
                # Parse source field (e.g., "standard.first_name" or "custom.tier")
                if "." in source_field:
                    field_type, field_name = source_field.split(".", 1)
                    if field_type == "standard":
                        value = subscriber.get("standard_fields", {}).get(field_name)
                    elif field_type == "custom":
                        value = subscriber.get("custom_fields", {}).get(field_name)
                    else:
                        value = personalization_data.get(field_name)
                else:
                    value = personalization_data.get(source_field)
                
                # Apply fallback if value is None
                if value is None and fallback_values:
                    value = fallback_values.get(target_field)
                
                if value is not None:
                    mapped_data[target_field] = value
        
        # Merge all personalization data
        final_personalization = {
            **personalization_data,
            **mapped_data
        }
        
        # Get email content
        html_content = template.get("content_html", "")
        text_content = template.get("content_text", "")
        
        # Simple template variable replacement ({{variable}})
        for key, value in final_personalization.items():
            placeholder = "{{" + key + "}}"
            if placeholder in html_content:
                html_content = html_content.replace(placeholder, str(value))
            if placeholder in text_content:
                text_content = text_content.replace(placeholder, str(value))
        
        # Prepare email data
        email_data = {
            "to_email": subscriber_email,
            "to_name": subscriber.get("standard_fields", {}).get("first_name", ""),
            "from_email": email_config.get("from_email"),
            "from_name": email_config.get("from_name"),
            "reply_to": email_config.get("reply_to"),
            "subject": email_config.get("subject"),
            "html_content": html_content,
            "text_content": text_content,
            "metadata": {
                "type": "automation",
                "automation_rule_id": automation_rule_id,
                "automation_step_id": step_id,
                "workflow_instance_id": workflow_instance_id,
                "template_id": template_id,
                "subscriber_id": subscriber_id
            }
        }
        
        # Import email sender (use your actual email sending implementation)
        from tasks.campaign.email_campaign_tasks import send_email_via_smtp
        
        # Send email
        send_result = send_email_via_smtp(email_data)
        
        # Create email log
        email_log = {
            "_id": ObjectId(),
            "subscriber_id": subscriber_id,
            "subscriber_email": subscriber_email,
            "campaign_id": None,  # Automation emails don't have campaign_id
            "automation_rule_id": automation_rule_id,
            "automation_step_id": step_id,
            "workflow_instance_id": workflow_instance_id,
            "template_id": template_id,
            "subject": email_config.get("subject"),
            "from_email": email_config.get("from_email"),
            "status": send_result.get("status", "sent"),
            "latest_status": send_result.get("status", "sent"),
            "message_id": send_result.get("message_id"),
            "sent_at": datetime.utcnow() if send_result.get("status") == "sent" else None,
            "delivery_status": send_result.get("delivery_status"),
            "error_message": send_result.get("error"),
            "metadata": email_data["metadata"],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        email_logs_collection.insert_one(email_log)
        
        logger.info(f"✅ Automation email sent successfully to {subscriber_email}")
        
        return {
            "status": "success",
            "email_log_id": str(email_log["_id"]),
            "message_id": send_result.get("message_id"),
            "subscriber_email": subscriber_email
        }
        
    except Exception as exc:
        logger.error(f"Failed to send automation email: {exc}", exc_info=True)
        raise self.retry(exc=exc)
