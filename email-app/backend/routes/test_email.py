# backend/routes/test_email.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any, List
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import logging
from jinja2 import Template
from bson import ObjectId
import re

# Import your existing database functions
from database import (
    get_campaigns_collection, 
    get_settings_collection, 
    get_subscribers_collection,
    get_lists_collection,
    get_audit_collection,
    get_email_logs_collection,
    get_templates_collection
)

router = APIRouter()
logger = logging.getLogger(__name__)

class TestEmailRequest(BaseModel):
    campaign_id: str
    test_email: EmailStr
    selected_list_id: Optional[str] = None
    use_custom_data: bool = False
    subscriber_id: Optional[str] = None  # For testing with specific subscriber data

class TestEmailResponse(BaseModel):
    success: bool
    message: str
    email_sent_to: str
    campaign_name: str
    timestamp: datetime

# Helper function to convert ObjectId to string
def str_object_id(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: str_object_id(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [str_object_id(item) for item in obj]
    return obj

async def get_smtp_settings():
    """Get SMTP settings from database"""
    settings_collection = get_settings_collection()
    settings = await settings_collection.find_one({"type": "email"})
    
    if not settings or not settings.get("config"):
        raise HTTPException(
            status_code=404, 
            detail="SMTP settings not configured. Please configure email settings first."
        )
    
    config = settings["config"]
    return {
        "smtp_server": config.get("smtp_server"),
        "smtp_port": config.get("smtp_port", 587),
        "username": config.get("username"),
        "password": config.get("password"),
        "provider": config.get("provider")
    }

async def get_campaign_details(campaign_id: str):
    """Get campaign details from database - matches your existing campaign structure"""
    campaigns_collection = get_campaigns_collection()
    
    try:
        if not ObjectId.is_valid(campaign_id):
            raise HTTPException(status_code=400, detail="Invalid campaign ID format")
            
        campaign = await campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
            
        return str_object_id(campaign)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching campaign {campaign_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching campaign details")

async def get_rendered_campaign_content(campaign_id: str):
    """Get rendered HTML content for campaign using template and field mapping"""
    try:
        campaigns_collection = get_campaigns_collection()
        templates_collection = get_templates_collection()
        
        if not ObjectId.is_valid(campaign_id):
            raise HTTPException(status_code=400, detail="Invalid campaign ID format")

        campaign = await campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        template_id = campaign.get("template_id")
        if not template_id or not ObjectId.is_valid(template_id):
            # Fallback: return basic content if no template
            return campaign.get("content", campaign.get("subject", "Test Email Content"))

        template = await templates_collection.find_one({"_id": ObjectId(template_id)})
        if not template:
            # Fallback: return basic content if template not found
            return campaign.get("content", campaign.get("subject", "Test Email Content"))

        # Use your existing email merge function
        try:
            from utils.email_merge import merge_template
            html_content = merge_template(template["content_json"], campaign.get("field_map", {}))
            return html_content
        except ImportError:
            # Fallback if merge function not available
            logger.warning("email_merge utility not found, using basic content")
            return template.get("content_json", {}).get("html", "Template content")
        except Exception as e:
            logger.warning(f"Template merge failed: {str(e)}, using fallback")
            return campaign.get("subject", "Test Email Content")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rendering campaign content: {str(e)}")
        # Return fallback content
        return "Test Email Content"

async def get_subscriber_data(list_id: str = None, subscriber_id: str = None):
    """Get subscriber data for personalization - matches your subscriber structure"""
    subscribers_collection = get_subscribers_collection()
    
    try:
        if subscriber_id:
            # Get specific subscriber
            if ObjectId.is_valid(subscriber_id):
                subscriber = await subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
            else:
                subscriber = await subscribers_collection.find_one({"_id": subscriber_id})
        elif list_id:
            # Get a random subscriber from the specific list
            subscriber = await subscribers_collection.find_one({"list": list_id})
        else:
            # Get any active subscriber for testing
            subscriber = await subscribers_collection.find_one({"status": "active"})
        
        if subscriber:
            return str_object_id(subscriber)
        return None
        
    except Exception as e:
        logger.error(f"Error fetching subscriber data: {str(e)}")
        return None

def personalize_content(content: str, subscriber_data: Dict[str, Any] = None):
    """Replace placeholders in email content with subscriber data"""
    if not subscriber_data:
        subscriber_data = {
            "name": "Test User",
            "email": "test@example.com"
        }
    
    try:
        # Handle Jinja2 template syntax
        template = Template(content)
        
        # Create template context
        context = {
            "subscriber": subscriber_data,
            "name": subscriber_data.get("name", "Test User"),
            "email": subscriber_data.get("email", "test@example.com"),
            "first_name": subscriber_data.get("name", "Test User").split()[0] if subscriber_data.get("name") else "Test"
        }
        
        # Add custom fields to context
        if subscriber_data.get("custom_fields"):
            context.update(subscriber_data["custom_fields"])
        
        personalized_content = template.render(**context)
        return personalized_content
        
    except Exception as e:
        logger.warning(f"Template rendering failed: {str(e)}, using original content")
        # Fallback: simple string replacement
        personalized_content = content
        
        # Simple placeholder replacement
        if subscriber_data:
            personalized_content = personalized_content.replace("{{name}}", subscriber_data.get("name", "Test User"))
            personalized_content = personalized_content.replace("{{email}}", subscriber_data.get("email", "test@example.com"))
            personalized_content = personalized_content.replace("{{first_name}}", 
                subscriber_data.get("name", "Test User").split()[0] if subscriber_data.get("name") else "Test")
        
        return personalized_content

async def send_test_email(smtp_config: Dict, campaign: Dict, test_email: str, subscriber_data: Dict = None):
    """Send test email using SMTP - matches your campaign structure"""
    try:
        # Create email message
        msg = MIMEMultipart('alternative')
        msg['From'] = campaign.get('sender_email', smtp_config['username'])
        msg['To'] = test_email
        
        # Get sender info from campaign
        sender_name = campaign.get('sender_name', 'Test Sender')
        if sender_name:
            msg['From'] = f"{sender_name} <{campaign.get('sender_email', smtp_config['username'])}>"
        
        # Set reply-to if specified
        reply_to = campaign.get('reply_to')
        if reply_to:
            msg['Reply-To'] = reply_to
        
        # Get and personalize subject
        subject = campaign.get('subject', 'Test Email')
        if subscriber_data:
            subject = personalize_content(subject, subscriber_data)
        
        msg['Subject'] = f"[TEST] {subject}"
        
        # Get rendered HTML content
        try:
            content = await get_rendered_campaign_content(campaign.get('_id', ''))
        except Exception as e:
            logger.warning(f"Failed to get rendered content: {str(e)}, using fallback")
            content = campaign.get('subject', 'Test email content')
        
        # Personalize content if subscriber data available
        if subscriber_data:
            content = personalize_content(content, subscriber_data)
        
        # Create HTML and text parts
        html_part = MIMEText(content, 'html')
        msg.attach(html_part)
        
        # Connect to SMTP server
        server = smtplib.SMTP(smtp_config['smtp_server'], smtp_config['smtp_port'], timeout=10)
        server.starttls()
        server.login(smtp_config['username'], smtp_config['password'])
        
        # Send email
        text = msg.as_string()
        server.sendmail(smtp_config['username'], test_email, text)
        server.quit()
        
        return True, "Email sent successfully"
        
    except smtplib.SMTPAuthenticationError:
        return False, "SMTP authentication failed. Please check your email credentials."
    except smtplib.SMTPRecipientsRefused:
        return False, "Invalid recipient email address."
    except smtplib.SMTPConnectError:
        return False, "Could not connect to SMTP server. Please check server settings."
    except Exception as e:
        logger.error(f"Email sending failed: {str(e)}")
        return False, f"Failed to send email: {str(e)}"

async def log_test_email(campaign_id: str, test_email: str, success: bool, message: str):
    """Log test email activity"""
    try:
        email_logs_collection = get_email_logs_collection()
        audit_collection = get_audit_collection()
        
        # Log to email logs
        await email_logs_collection.insert_one({
            "type": "test_email",
            "campaign_id": campaign_id,
            "recipient": test_email,
            "success": success,
            "message": message,
            "timestamp": datetime.utcnow()
        })
        
        # Log to audit
        await audit_collection.insert_one({
            "action": "test_email_sent" if success else "test_email_failed",
            "campaign_id": campaign_id,
            "recipient": test_email,
            "message": message,
            "timestamp": datetime.utcnow()
        })
        
    except Exception as e:
        logger.error(f"Failed to log test email: {str(e)}")

@router.post("/campaigns/{campaign_id}/test-email")
async def send_campaign_test_email(campaign_id: str, request: TestEmailRequest):
    """Send test email for a campaign"""
    try:
        # Validate campaign_id matches request
        if campaign_id != request.campaign_id:
            raise HTTPException(status_code=400, detail="Campaign ID mismatch")
        
        # Get SMTP settings
        smtp_config = await get_smtp_settings()
        
        # Get campaign details
        campaign = await get_campaign_details(campaign_id)
        
        # Get subscriber data if requested
        subscriber_data = None
        if request.use_custom_data:
            subscriber_data = await get_subscriber_data(
                list_id=request.selected_list_id,
                subscriber_id=request.subscriber_id
            )
        
        # Send test email
        success, message = await send_test_email(
            smtp_config, 
            campaign, 
            request.test_email, 
            subscriber_data
        )
        
        # Log the activity
        await log_test_email(campaign_id, request.test_email, success, message)
        
        if not success:
            raise HTTPException(status_code=500, detail=message)
        
        return TestEmailResponse(
            success=True,
            message=message,
            email_sent_to=request.test_email,
            campaign_name=campaign.get('name', 'Unnamed Campaign'),
            timestamp=datetime.utcnow()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Test email failed: {str(e)}")
        await log_test_email(campaign_id, request.test_email, False, str(e))
        raise HTTPException(status_code=500, detail=f"Failed to send test email: {str(e)}")

@router.post("/test-email")
async def send_standalone_test_email(request: TestEmailRequest):
    """Send test email (alternative endpoint for flexibility)"""
    return await send_campaign_test_email(request.campaign_id, request)

@router.get("/campaigns/{campaign_id}/test-email/logs")
async def get_test_email_logs(campaign_id: str, limit: int = 10):
    """Get test email logs for a campaign"""
    try:
        email_logs_collection = get_email_logs_collection()
        
        logs = await email_logs_collection.find(
            {
                "type": "test_email",
                "campaign_id": campaign_id
            },
            sort=[("timestamp", -1)],
            limit=limit
        ).to_list(limit)
        
        return {"logs": str_object_id(logs)}
        
    except Exception as e:
        logger.error(f"Failed to fetch test email logs: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch logs")

@router.get("/campaigns/{campaign_id}/preview")
async def preview_campaign_email(campaign_id: str, subscriber_id: Optional[str] = None, list_id: Optional[str] = None):
    """Preview campaign email with sample data - matches your existing campaign structure"""
    try:
        # Get campaign details
        campaign = await get_campaign_details(campaign_id)
        
        # Get subscriber data for preview
        subscriber_data = await get_subscriber_data(list_id=list_id, subscriber_id=subscriber_id)
        
        # Get rendered content
        content = await get_rendered_campaign_content(campaign_id)
        
        # Personalize content
        subject = campaign.get('subject', 'No Subject')
        
        if subscriber_data:
            subject = personalize_content(subject, subscriber_data)
            content = personalize_content(content, subscriber_data)
        
        return {
            "campaign_name": campaign.get('title', 'Unnamed Campaign'),  # Using 'title' as per your schema
            "subject": subject,
            "content": content,
            "sender_name": campaign.get('sender_name', ''),
            "sender_email": campaign.get('sender_email', ''),
            "reply_to": campaign.get('reply_to', ''),
            "preview_data": subscriber_data if subscriber_data else "No subscriber data available",
            "template_id": campaign.get('template_id', ''),
            "field_map": campaign.get('field_map', {})
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to preview campaign: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate preview")
