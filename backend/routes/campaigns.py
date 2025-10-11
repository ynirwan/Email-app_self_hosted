from fastapi import APIRouter, HTTPException, Path, status
from pydantic import BaseModel, EmailStr, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Template
from database import get_campaigns_collection,  get_audit_collection
from .email_sender import send_test_email
from .list_validator import validate_target_lists_exist, compute_target_list_count 
from .field_handler import   get_subscriber_field_value, render_email_for_subscriber, count_populated_fields, create_mock_subscriber_tiered,get_sample_subscriber_tiered, FIELD_TIERS

from .field_validator import  validate_tiered_field_mapping, calculate_tiered_audience_count




logger = logging.getLogger(__name__)
router = APIRouter()

FIELD_TIERS = {
    "universal": ["email"],
    "standard": [
        "first_name", "last_name", "phone", "company", 
        "country", "city", "job_title"
    ]
}


# Update your existing CampaignCreate class
class CampaignCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    subject: str = Field(..., min_length=1, max_length=300)
    sender_name: Optional[str] = Field(default="", max_length=100)
    sender_email: Optional[str] = Field(default="", max_length=100)
    reply_to: Optional[str] = Field(default="", max_length=100)
    target_lists: List[str] = Field(..., min_items=1)
    template_id: str
    field_map: Dict[str, str] = Field(default_factory=dict)  # Now supports tier prefixes like "standard.first_name"
    status: Optional[str] = Field(default="draft")
    
    # NEW: Three-tier system fields
    field_mapping_strategy: Optional[Dict[str, Any]] = Field(default_factory=dict)
    fallback_values: Optional[Dict[str, str]] = Field(default_factory=dict)
    
    @validator('target_lists')
    def validate_target_lists(cls, v):
        """Ensure target_lists is not empty and contains valid list IDs"""
        if not v or len(v) == 0:
            raise ValueError('At least one target list must be selected')
        unique_lists = list(dict.fromkeys(v))
        if len(unique_lists) != len(v):
            raise ValueError('Duplicate lists found in target_lists')
        return unique_lists

# Update your existing CampaignUpdate class
class CampaignUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    subject: str = Field(..., min_length=1, max_length=300)
    sender_name: Optional[str] = Field(default="", max_length=100)
    sender_email: Optional[str] = Field(default="", max_length=100)
    reply_to: Optional[str] = Field(default="", max_length=100)
    target_lists: List[str] = Field(..., min_items=1)
    template_id: str
    field_map: Dict[str, str] = Field(default_factory=dict)
    status: Optional[str] = Field(default="draft")
    
    # NEW: Three-tier system fields
    field_mapping_strategy: Optional[Dict[str, Any]] = Field(default_factory=dict)
    fallback_values: Optional[Dict[str, str]] = Field(default_factory=dict)
    
    @validator('target_lists')
    def validate_target_lists(cls, v):
        """Ensure target_lists is not empty and contains valid list IDs"""
        if not v or len(v) == 0:
            raise ValueError('At least one target list must be selected')
        unique_lists = list(dict.fromkeys(v))
        if len(unique_lists) != len(v):
            raise ValueError('Duplicate lists found in target_lists')
        return unique_lists

# Also update your TestEmail class to match the document
class TestEmail(BaseModel):
    campaign_id: str
    test_email: EmailStr
    use_custom_data: bool = False
    selected_list_id: Optional[str] = None
    subscriber_id: Optional[str] = None



@router.post("/campaigns")
async def create_campaign(campaign: CampaignCreate):
    """Create a new campaign with three-tier field validation"""
    try:
        campaigns_collection = get_campaigns_collection()
        
        # ✅ STEP 1: Validate that target lists exist (keep existing logic)
        if not await validate_target_lists_exist(campaign.target_lists):
            raise HTTPException(
                status_code=400,
                detail="One or more target lists do not exist or have no subscribers"
            )
        
        # ✅ NEW: Validate field mappings with tier system
        validated_mapping = await validate_tiered_field_mapping(
            campaign.field_map, 
            campaign.target_lists
        )
        
        # ✅ STEP 2: Calculate target audience with tier-aware counting
        target_count = await calculate_tiered_audience_count(
            campaign.target_lists,
            validated_mapping
        )
        
        if target_count == 0:
            raise HTTPException(
                status_code=400,
                detail="Selected lists have no subscribers. Cannot create campaign with empty audience."
            )
        
        # ✅ STEP 3: Build campaign document with new fields
        campaign_doc = {
            "title": campaign.title,
            "subject": campaign.subject,
            "sender_name": campaign.sender_name,
            "sender_email": campaign.sender_email,
            "reply_to": campaign.reply_to,
            "target_lists": campaign.target_lists,
            "template_id": campaign.template_id,
            "field_map": validated_mapping["field_map"],
            "field_mapping_strategy": validated_mapping["strategy"],
            "fallback_values": campaign.fallback_values or {},
            "status": campaign.status or "draft",
            "target_list_count": target_count,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        # ✅ STEP 4: Insert campaign
        result = await campaigns_collection.insert_one(campaign_doc)
        
        if not result.inserted_id:
            raise HTTPException(status_code=500, detail="Failed to create campaign")
        
        logger.info(f"Campaign created: {result.inserted_id} with {target_count} target subscribers")
        logger.info(f"Field mapping summary: {validated_mapping['summary']}")
        
        return {
            "message": "Campaign created successfully",
            "campaign_id": str(result.inserted_id),
            "target_count": target_count,
            "field_mapping_summary": validated_mapping["summary"],
            "campaign": {
                **campaign_doc,
                "_id": str(result.inserted_id)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Campaign creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create campaign: {str(e)}")



@router.get("/campaigns")
async def list_campaigns():
    try:
        campaigns_collection = get_campaigns_collection()
        campaigns = []
        cursor = campaigns_collection.find().sort("created_at", -1)
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])  # Convert ObjectId to string
            campaigns.append(doc)
        logger.info(f"Retrieved {len(campaigns)} campaigns")
        return {
            "campaigns": campaigns,
            "total": len(campaigns)
        }
    except Exception as e:
        logger.error(f"Failed to list campaigns: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve campaigns: {str(e)}")


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str):
    try:
        campaigns_collection = get_campaigns_collection()
        if not ObjectId.is_valid(campaign_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid campaign ID format")
        campaign = await campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
        if not campaign:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
        campaign["_id"] = str(campaign["_id"])
        logger.info(f"Retrieved campaign: {campaign_id}")
        return campaign
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get campaign {campaign_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve campaign: {str(e)}")


@router.put("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: str, campaign_data: CampaignUpdate):
    """Update campaign with three-tier field validation"""
    try:
        campaigns_collection = get_campaigns_collection()
        
        # ✅ STEP 1: Validate campaign exists
        if not ObjectId.is_valid(campaign_id):
            raise HTTPException(status_code=400, detail="Invalid campaign ID format")
            
        existing_campaign = await campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
        if not existing_campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        # ✅ STEP 2: Validate that NEW target lists exist
        if not await validate_target_lists_exist(campaign_data.target_lists):
            raise HTTPException(
                status_code=400,
                detail="One or more target lists do not exist or have no subscribers"
            )
        
        # ✅ NEW: Validate field mappings with tier system
        validated_mapping = await validate_tiered_field_mapping(
            campaign_data.field_map, 
            campaign_data.target_lists
        )
        
        # ✅ STEP 3: Calculate target audience with tier-aware counting
        target_count = await calculate_tiered_audience_count(
            campaign_data.target_lists,
            validated_mapping
        )
        
        if target_count == 0:
            raise HTTPException(
                status_code=400,
                detail="Selected lists have no subscribers. Cannot update campaign with empty audience."
            )
        
        # ✅ STEP 4: Build update data with validated mapping
        update_data = {
            "title": campaign_data.title,
            "subject": campaign_data.subject,
            "sender_name": campaign_data.sender_name,
            "sender_email": campaign_data.sender_email,
            "reply_to": campaign_data.reply_to,
            "target_lists": campaign_data.target_lists,
            "template_id": campaign_data.template_id,
            "field_map": validated_mapping["field_map"],
            "field_mapping_strategy": validated_mapping["strategy"],
            "fallback_values": campaign_data.fallback_values or {},
            "status": campaign_data.status,
            "target_list_count": target_count,
            "updated_at": datetime.utcnow()
        }
        
        # ✅ STEP 5: Preserve original timestamps
        if "created_at" in existing_campaign:
            update_data["created_at"] = existing_campaign["created_at"]
        if "sent_at" in existing_campaign:
            update_data["sent_at"] = existing_campaign["sent_at"]
        
        # ✅ STEP 6: Update campaign
        result = await campaigns_collection.update_one(
            {"_id": ObjectId(campaign_id)},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        # ✅ STEP 7: Return updated campaign
        updated_campaign = await campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
        updated_campaign["_id"] = str(updated_campaign["_id"])
        
        logger.info(f"Campaign updated: {campaign_id} - New target count: {target_count}")
        logger.info(f"Field mapping summary: {validated_mapping['summary']}")
        
        return {
            "message": "Campaign updated successfully",
            "campaign": updated_campaign,
            "computed_target_count": target_count,
            "target_lists_updated": campaign_data.target_lists,
            "field_mapping_summary": validated_mapping["summary"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update campaign: {str(e)}")


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str):
    try:
        campaigns_collection = get_campaigns_collection()
        if not ObjectId.is_valid(campaign_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid campaign ID format")
        campaign = await campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
        if not campaign:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
        result = await campaigns_collection.delete_one({"_id": ObjectId(campaign_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete campaign")
        logger.info(f"Campaign deleted: {campaign_id}")
        return {
            "message": "Campaign deleted successfully",
            "deleted_campaign_id": campaign_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete campaign {campaign_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete campaign: {str(e)}")


# ✅ UPDATED TEST EMAIL ENDPOINT - Now fully functional
@router.post("/campaigns/send-test")
async def send_test_email(test_data: TestEmail):
    """Send test email for a campaign with full functionality"""
    try:
        # Get SMTP settings
        smtp_config = await get_smtp_settings()
        
        # Get campaign details
        campaigns_collection = get_campaigns_collection()
        if not ObjectId.is_valid(test_data.campaign_id):
            raise HTTPException(status_code=400, detail="Invalid campaign ID format")
            
        campaign = await campaigns_collection.find_one({"_id": ObjectId(test_data.campaign_id)})
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        # Get subscriber data if requested
        subscriber_data = None
        if test_data.use_custom_data:
            subscriber_data = await get_subscriber_data(
                list_id=test_data.selected_list_id,
                subscriber_id=test_data.subscriber_id
            )
        
        # Create email message
        msg = MIMEMultipart('alternative')
        
        # Set sender info from campaign
        sender_email = campaign.get('sender_email')
        sender_name = campaign.get('sender_name', 'Test Sender')
        if sender_name:
            msg['From'] = f"{sender_name} <{sender_email}>"
        else:
            msg['From'] = sender_email
            
        msg['To'] = test_data.test_email
        
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
            content = await get_rendered_campaign_content(test_data.campaign_id)
        except Exception as e:
            logger.warning(f"Failed to get rendered content: {str(e)}, using fallback")
            content = campaign.get('subject', 'Test email content')
        
        # Personalize content if subscriber data available
        if subscriber_data:
            content = personalize_content(content, subscriber_data)
        
        # Create HTML part
        html_part = MIMEText(content, 'html')
        msg.attach(html_part)
        
        # Connect to SMTP server and send
        server = smtplib.SMTP(smtp_config['smtp_server'], smtp_config['smtp_port'], timeout=10)
        server.starttls()
        server.login(smtp_config['username'], smtp_config['password'])
        
        text = msg.as_string()
        print(text)
        server.sendmail(sender_email, test_data.test_email, text)
        server.quit()
        
        # Log success
        await log_test_email(test_data.campaign_id, test_data.test_email, True, "Test email sent successfully")
        
        logger.info(f"Test email sent successfully to: {test_data.test_email}")
        return {
            "message": f"✅ Test email sent successfully to {test_data.test_email}",
            "recipient": test_data.test_email,
            "campaign_title": campaign.get('title', 'Unnamed Campaign'),
            "subject": subject,
            "sender": msg['From'],
            "timestamp": datetime.utcnow().isoformat(),
            "status": "sent"
        }
        
    except HTTPException:
        raise
    except smtplib.SMTPAuthenticationError as e:
        error_msg = "SMTP authentication failed. Please check your email credentials."
        await log_test_email(test_data.campaign_id, test_data.test_email, False, error_msg)
        raise HTTPException(status_code=401, detail=error_msg)
    except smtplib.SMTPRecipientsRefused as e:
        error_msg = "Invalid recipient email address."
        await log_test_email(test_data.campaign_id, test_data.test_email, False, error_msg)
        raise HTTPException(status_code=400, detail=error_msg)
    except smtplib.SMTPConnectError as e:
        error_msg = "Could not connect to SMTP server. Please check server settings."
        await log_test_email(test_data.campaign_id, test_data.test_email, False, error_msg)
        raise HTTPException(status_code=502, detail=error_msg)
    except Exception as e:
        error_msg = f"Failed to send test email: {str(e)}"
        logger.error(f"Test email failed: {error_msg}")
        await log_test_email(test_data.campaign_id, test_data.test_email, False, error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


# ✅ ALTERNATIVE ENDPOINT - Campaign-specific test email
@router.post("/campaigns/{campaign_id}/test-email")
async def send_campaign_test_email(campaign_id: str, test_email: EmailStr, use_custom_data: bool = False, selected_list_id: Optional[str] = None):
    """Send test email for a specific campaign"""
    test_data = TestEmail(
        campaign_id=campaign_id,
        test_email=test_email,
        use_custom_data=use_custom_data,
        selected_list_id=selected_list_id
    )
    return await send_test_email(test_data)


@router.post("/campaigns/{campaign_id}/send")
async def send_campaign(campaign_id: str):
    try:
        campaigns_collection = get_campaigns_collection()
        if not ObjectId.is_valid(campaign_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid campaign ID format")
        campaign = await campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
        if not campaign:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
        logger.info(f"Send campaign request for: {campaign_id}")
        return {
            "message": "Campaign sending functionality not implemented yet",
            "campaign_id": campaign_id,
            "status": "placeholder"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in send campaign endpoint: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Send campaign error: {str(e)}")


# New render endpoint to merge template content + dynamic fields for the campaign
@router.post("/campaigns/{campaign_id}/render")
async def render_campaign_email(campaign_id: str):
    from database import get_templates_collection  # Import here to avoid circular imports

    campaigns_collection = get_campaigns_collection()
    templates_collection = get_templates_collection()

    if not ObjectId.is_valid(campaign_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid campaign ID format")

    campaign = await campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    template_id = campaign.get("template_id")
    if not template_id or not ObjectId.is_valid(template_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or missing template ID in campaign")

    template = await templates_collection.find_one({"_id": ObjectId(template_id)})
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    # Use your merge function (implement as needed)
    try:
        from utils.email_merge import merge_template
        html = merge_template(template["content_json"], campaign.get("field_map", {}))
        return {"html": html}
    except ImportError:
        return {"html": template.get("content_json", {}).get("html", "Template content")}



# ✅ NEW ENDPOINT - Get test email logs
@router.get("/campaigns/{campaign_id}/test-logs")
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



# Get campaign statistics
@router.get("/campaigns/{campaign_id}/stats")
async def get_campaign_stats(campaign_id: str):
    """
    Get detailed statistics for a campaign including real-time subscriber counts.
    
    Explanation:
        - Shows stored vs current subscriber counts
        - Helps identify if lists have changed since campaign creation
        - Useful for debugging and monitoring
    """
    try:
        campaigns_collection = get_campaigns_collection()
        
        if not ObjectId.is_valid(campaign_id):
            raise HTTPException(status_code=400, detail="Invalid campaign ID format")
            
        campaign = await campaigns_collection.find_one({"_id": ObjectId(campaign_id)})
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        # Get current subscriber count
        current_count = await compute_target_list_count(campaign.get("target_lists", []))
        stored_count = campaign.get("target_list_count", 0)
        
        # Detailed list breakdown
        list_breakdown = []
        for list_id in campaign.get("target_lists", []):
            subscribers_collection = get_subscribers_collection()
            count = await subscribers_collection.count_documents({"list_id": list_id})
            list_breakdown.append({
                "list_id": list_id,
                "current_count": count
            })
        
        return {
            "campaign_id": campaign_id,
            "target_lists": campaign.get("target_lists", []),
            "stored_target_count": stored_count,
            "current_target_count": current_count,
            "count_differs": current_count != stored_count,
            "list_breakdown": list_breakdown,
            "last_updated": campaign.get("updated_at"),
            "status": campaign.get("status")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get campaign stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get campaign stats: {str(e)}")    
