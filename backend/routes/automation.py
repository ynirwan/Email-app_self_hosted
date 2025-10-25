# backend/routes/automation.py - FIXED VERSION
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, validator, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from enum import Enum
import uuid
from bson import ObjectId
import pytz  # ⭐ CRITICAL FIX: Missing import

from database import (
    get_automation_rules_collection,
    get_automation_steps_collection,
    get_automation_executions_collection,
    get_subscribers_collection,
    get_templates_collection,
    get_segments_collection,
    get_audit_collection
)

router = APIRouter(prefix="/automation")

# ===========================
# PYDANTIC SCHEMAS
# ===========================

class EmailConfig(BaseModel):
    """Email sending configuration"""
    sender_email: EmailStr
    sender_name: str
    reply_to: Optional[EmailStr] = None
    
    @validator('sender_name')
    def validate_sender_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Sender name is required')
        return v.strip()


class AutomationStepCreate(BaseModel):
    """Step configuration for automation"""
    template_id: str
    delay_value: int = 1
    delay_type: str = "hours"  # hours, days, weeks
    segment_conditions: Optional[List[str]] = []  # Segment IDs for conditional sending
    conditions: Optional[Dict[str, Any]] = {}


class AutomationRuleCreate(BaseModel):
    """Create automation rule with full timezone and scheduling support"""
    name: str
    trigger: str  # welcome, birthday, abandoned_cart, etc.
    trigger_conditions: Dict[str, Any] = {}
    target_segments: Optional[List[str]] = []
    target_lists: Optional[List[str]] = []
    active: bool = False
    steps: List[AutomationStepCreate] = []
    email_config: EmailConfig
    
    # ⭐ TIMEZONE CONFIGURATION
    timezone: str = "UTC"  # User-specified timezone for this automation
    use_subscriber_timezone: bool = False  # Use subscriber's timezone if available
    
    # ⭐ RE-TRIGGER SETTINGS
    allow_retrigger: bool = False  # Allow automation to trigger multiple times
    retrigger_delay_hours: int = 24  # Minimum hours between triggers
    cancel_previous_on_retrigger: bool = True  # Cancel active workflow when retriggering
    
    # ⭐ EXIT CONDITIONS
    exit_on_goal_achieved: bool = True  # Stop workflow if goal achieved
    exit_on_unsubscribe: bool = True  # Stop workflow if user unsubscribes
    
    # ⭐ FREQUENCY CAPPING
    max_emails_per_day: int = 3  # Max emails per subscriber per day (0 = unlimited)
    respect_quiet_hours: bool = True  # Don't send during quiet hours
    quiet_hours_start: int = 22  # 10 PM
    quiet_hours_end: int = 8  # 8 AM
    
    # ⭐ FAILURE HANDLING
    skip_step_on_failure: bool = False  # Skip failed step and continue
    notify_on_failure: bool = True  # Notify admin on failures
    
    @validator('timezone')
    def validate_timezone(cls, v):
        """Validate timezone using pytz"""
        try:
            pytz.timezone(v)
        except pytz.exceptions.UnknownTimeZoneError:
            raise ValueError(f'Invalid timezone: {v}. Use format like "America/New_York", "Asia/Kolkata", "UTC"')
        return v
    
    @validator('quiet_hours_start', 'quiet_hours_end')
    def validate_hours(cls, v):
        """Validate hours are in 0-23 range"""
        if not 0 <= v <= 23:
            raise ValueError('Hours must be between 0 and 23')
        return v
    
    @validator('name')
    def validate_name(cls, v):
        """Validate automation name"""
        if not v or not v.strip():
            raise ValueError('Automation name is required')
        if len(v) > 200:
            raise ValueError('Name must be less than 200 characters')
        return v.strip()
    
    @validator('steps')
    def validate_steps(cls, v):
        """Validate at least one step exists"""
        if len(v) == 0:
            raise ValueError('At least one email step is required')
        return v


class AutomationRuleUpdate(BaseModel):
    """Update automation rule"""
    name: Optional[str] = None
    trigger: Optional[str] = None
    trigger_conditions: Optional[Dict[str, Any]] = None
    target_segments: Optional[List[str]] = None
    target_lists: Optional[List[str]] = None
    active: Optional[bool] = None
    steps: Optional[List[AutomationStepCreate]] = None
    email_config: Optional[EmailConfig] = None
    
    # Timezone settings
    timezone: Optional[str] = None
    use_subscriber_timezone: Optional[bool] = None
    
    # Other settings
    allow_retrigger: Optional[bool] = None
    retrigger_delay_hours: Optional[int] = None
    cancel_previous_on_retrigger: Optional[bool] = None
    exit_on_goal_achieved: Optional[bool] = None
    exit_on_unsubscribe: Optional[bool] = None
    max_emails_per_day: Optional[int] = None
    respect_quiet_hours: Optional[bool] = None
    quiet_hours_start: Optional[int] = None
    quiet_hours_end: Optional[int] = None
    skip_step_on_failure: Optional[bool] = None
    notify_on_failure: Optional[bool] = None


class AutomationRuleResponse(BaseModel):
    """Response format for automation rules"""
    id: str
    name: str
    trigger: str
    trigger_conditions: Dict[str, Any] = {}
    target_segments: List[str] = []
    target_lists: List[str] = []
    status: str
    active: bool = False
    emails_sent: int = 0
    open_rate: float = 0.0
    click_rate: float = 0.0
    created_at: datetime
    updated_at: datetime
    steps: List[Dict] = []
    
    # Timezone and scheduling
    timezone: str = "UTC"
    use_subscriber_timezone: bool = False
    respect_quiet_hours: bool = True
    quiet_hours_start: int = 22
    quiet_hours_end: int = 8
    
    # Email config
    email_config: Optional[EmailConfig] = None


# ===========================
# VALIDATION FUNCTIONS
# ===========================

async def validate_templates_exist(template_ids: List[str]) -> Dict[str, bool]:
    """Batch validate templates - returns validation results"""
    from database import get_templates_collection
    
    if not template_ids:
        return {}
    
    # Validate ObjectIds first
    valid_ids = []
    invalid_ids = []
    
    for template_id in template_ids:
        if ObjectId.is_valid(template_id):
            valid_ids.append(ObjectId(template_id))
        else:
            invalid_ids.append(template_id)
    
    if invalid_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid template IDs: {', '.join(invalid_ids)}"
        )
    
    # Batch query - much faster than individual queries
    templates_collection = get_templates_collection()
    existing_templates = await templates_collection.find(
        {"_id": {"$in": valid_ids}},
        {"_id": 1}
    ).to_list(length=len(valid_ids))
    
    existing_ids = {str(t["_id"]) for t in existing_templates}
    
    # Check for missing templates
    missing_ids = set(template_ids) - existing_ids
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Templates not found: {', '.join(missing_ids)}"
        )
    
    return {tid: tid in existing_ids for tid in template_ids}


async def validate_segments_exist(segment_ids: List[str]) -> Dict[str, bool]:
    """Batch validate segments"""
    from database import get_segments_collection
    
    if not segment_ids:
        return {}
    
    valid_ids = []
    invalid_ids = []
    
    for segment_id in segment_ids:
        if ObjectId.is_valid(segment_id):
            valid_ids.append(ObjectId(segment_id))
        else:
            invalid_ids.append(segment_id)
    
    if invalid_ids:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid segment IDs: {', '.join(invalid_ids)}"
        )
    
    segments_collection = get_segments_collection()
    existing_segments = await segments_collection.find(
        {"_id": {"$in": valid_ids}},
        {"_id": 1}
    ).to_list(length=len(valid_ids))
    
    existing_ids = {str(s["_id"]) for s in existing_segments}
    
    missing_ids = set(segment_ids) - existing_ids
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Segments not found: {', '.join(missing_ids)}"
        )
    
    return {sid: sid in existing_ids for sid in segment_ids}


# ===========================
# AUTOMATION ROUTES
# ===========================
@router.get("/templates")
async def get_automation_templates():
    """Get all available templates for automation"""
    try:
        templates_collection = get_templates_collection()
        
        templates = []
        async for template in templates_collection.find({"deleted_at": {"$exists": False}}):
            templates.append({
                "id": str(template["_id"]),
                "name": template.get("name", "Untitled"),
                "subject": template.get("subject", ""),
                "content_preview": template.get("content_text", "")[:100] if template.get("content_text") else ""
            })
        
        return {"templates": templates, "total": len(templates)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch templates: {str(e)}")


@router.get("/segments")
async def get_automation_segments():
    """Get all available segments for targeting"""
    try:
        segments_collection = get_segments_collection()
        
        segments = []
        async for segment in segments_collection.find({"deleted_at": {"$exists": False}}):
            segments.append({
                "id": str(segment["_id"]),
                "name": segment.get("name", "Untitled"),
                "description": segment.get("description", ""),
                "subscriber_count": segment.get("subscriber_count", 0)
            })
        
        return {"segments": segments, "total": len(segments)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch segments: {str(e)}")


@router.post("/rules", status_code=201)
async def create_automation_rule(rule_data: AutomationRuleCreate, background_tasks: BackgroundTasks):
    """
    Create a new automation rule with comprehensive validation """
       # ⭐ ADD THIS DEBUG LOGGING AT THE TOP
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("📥 RECEIVED AUTOMATION RULE DATA:")
    logger.info(f"Name: {rule_data.name}")
    logger.info(f"Trigger: {rule_data.trigger}")
    logger.info(f"Timezone: {rule_data.timezone}")
    logger.info(f"Email Config: {rule_data.email_config}")
    logger.info(f"Steps count: {len(rule_data.steps)}")
    logger.info("=" * 60)
    
    rules_collection = get_automation_rules_collection()
    steps_collection = get_automation_steps_collection()
    audit_collection = get_audit_collection()
    
    # Validate templates exist
    template_ids = [step.template_id for step in rule_data.steps]
    await validate_templates_exist(template_ids)
    
    # Validate segments if specified
    if rule_data.target_segments:
        await validate_segments_exist(rule_data.target_segments)
    
    # Convert delay to hours for storage
    steps_data = []
    for idx, step in enumerate(rule_data.steps):
        delay_hours = step.delay_value
        if step.delay_type == "days":
            delay_hours = step.delay_value * 24
        elif step.delay_type == "weeks":
            delay_hours = step.delay_value * 168
        
        steps_data.append({
            "email_template_id": step.template_id,
            "delay_hours": delay_hours,
            "delay_value": step.delay_value,
            "delay_type": step.delay_type,
            "segment_conditions": step.segment_conditions or [],
            "conditions": step.conditions or {},
            "step_order": idx + 1
        })
    
    # Create automation rule document
    rule_doc = {
        "name": rule_data.name,
        "trigger": rule_data.trigger,
        "trigger_conditions": rule_data.trigger_conditions,
        "target_segments": rule_data.target_segments or [],
        "target_lists": rule_data.target_lists or [],
        "status": "active" if rule_data.active else "draft",
        "email_config": rule_data.email_config.dict(),
        
        # Timezone settings
        "timezone": rule_data.timezone,
        "use_subscriber_timezone": rule_data.use_subscriber_timezone,
        
        # Re-trigger settings
        "allow_retrigger": rule_data.allow_retrigger,
        "retrigger_delay_hours": rule_data.retrigger_delay_hours,
        "cancel_previous_on_retrigger": rule_data.cancel_previous_on_retrigger,
        
        # Exit conditions
        "exit_on_goal_achieved": rule_data.exit_on_goal_achieved,
        "exit_on_unsubscribe": rule_data.exit_on_unsubscribe,
        
        # Frequency capping
        "max_emails_per_day": rule_data.max_emails_per_day,
        "respect_quiet_hours": rule_data.respect_quiet_hours,
        "quiet_hours_start": rule_data.quiet_hours_start,
        "quiet_hours_end": rule_data.quiet_hours_end,
        
        # Failure handling
        "skip_step_on_failure": rule_data.skip_step_on_failure,
        "notify_on_failure": rule_data.notify_on_failure,
        
        # Analytics
        "emails_sent": 0,
        "emails_opened": 0,
        "emails_clicked": 0,
        "subscribers_entered": 0,
        "subscribers_completed": 0,
        
        # Metadata
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = await rules_collection.insert_one(rule_doc)
    rule_id = str(result.inserted_id)
    
    # Insert steps
    for step_data in steps_data:
        step_data["automation_rule_id"] = rule_id
        step_data["created_at"] = datetime.utcnow()
        await steps_collection.insert_one(step_data)
    
    # Audit log
    await audit_collection.insert_one({
        "action": "automation_created",
        "entity_type": "automation_rule",
        "entity_id": rule_id,
        "details": {"name": rule_data.name, "trigger": rule_data.trigger},
        "timestamp": datetime.utcnow()
    })
    
    return {
        "id": rule_id,
        "message": "Automation rule created successfully",
        "status": rule_doc["status"]
    }


@router.get("/rules")
async def list_automation_rules(
    status: Optional[str] = Query(None),
    trigger: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    skip: int = Query(0)
):
    """
    List all automation rules with filtering
    """
    rules_collection = get_automation_rules_collection()
    
    query = {"deleted_at": {"$exists": False}}
    
    if status:
        query["status"] = status
    if trigger:
        query["trigger"] = trigger
    
    total = await rules_collection.count_documents(query)
    
    rules = await rules_collection.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(length=limit)
    
    # Format response
    formatted_rules = []
    for rule in rules:
        formatted_rules.append({
            "id": str(rule["_id"]),
            "name": rule["name"],
            "trigger": rule["trigger"],
            "status": rule.get("status", "draft"),
            "active": rule.get("status") == "active",
            "emails_sent": rule.get("emails_sent", 0),
            "subscribers_entered": rule.get("subscribers_entered", 0),
            "subscribers_completed": rule.get("subscribers_completed", 0),
            "timezone": rule.get("timezone", "UTC"),
            "created_at": rule["created_at"],
            "updated_at": rule["updated_at"]
        })
    
    return {
        "rules": formatted_rules,
        "total": total,
        "limit": limit,
        "skip": skip
    }


@router.get("/rules/{rule_id}")
async def get_automation_rule(rule_id: str):
    """Get a specific automation rule by ID with all details"""
    try:
        object_id = ObjectId(rule_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid rule ID format")
    
    rules_collection = get_automation_rules_collection()
    rule = await rules_collection.find_one({
        "_id": object_id,
        "deleted_at": {"$exists": False}
    })
    
    if not rule:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    
    # Get steps for this rule
    steps_collection = get_automation_steps_collection()
    steps = await steps_collection.find({
        "automation_rule_id": rule_id
    }).sort("step_order", 1).to_list(None)
    
    # Format response to match frontend expectations
    rule_response = {
        "id": str(rule["_id"]),
        "name": rule["name"],
        "trigger": rule["trigger"],
        "trigger_conditions": rule.get("trigger_conditions", {}),
        "target_segments": rule.get("target_segments", []),
        "target_lists": rule.get("target_lists", []),
        "status": rule.get("status", "draft"),
        "active": rule.get("status") == "active",
        
        # Timezone settings
        "timezone": rule.get("timezone", "UTC"),
        "use_subscriber_timezone": rule.get("use_subscriber_timezone", False),
        
        # Scheduling settings
        "respect_quiet_hours": rule.get("respect_quiet_hours", True),
        "quiet_hours_start": rule.get("quiet_hours_start", 22),
        "quiet_hours_end": rule.get("quiet_hours_end", 8),
        
        # Other settings
        "allow_retrigger": rule.get("allow_retrigger", False),
        "retrigger_delay_hours": rule.get("retrigger_delay_hours", 24),
        "max_emails_per_day": rule.get("max_emails_per_day", 3),
        "exit_on_unsubscribe": rule.get("exit_on_unsubscribe", True),
        
        # Email config
        "email_config": rule.get("email_config", {}),
        
        # Analytics
        "emails_sent": rule.get("emails_sent", 0),
        "emails_opened": rule.get("emails_opened", 0),
        "emails_clicked": rule.get("emails_clicked", 0),
        "subscribers_entered": rule.get("subscribers_entered", 0),
        "subscribers_completed": rule.get("subscribers_completed", 0),
        
        # Metadata
        "created_at": rule["created_at"],
        "updated_at": rule["updated_at"],
        "steps": []
    }
    
    # Convert steps to frontend format
    for step in steps:
        # Convert delay_hours back to frontend format
        delay_hours = step.get("delay_hours", 1)
        if delay_hours >= 168:  # 1 week = 168 hours
            delay_value = delay_hours // 168
            delay_type = "weeks"
        elif delay_hours >= 24:  # 1 day = 24 hours
            delay_value = delay_hours // 24
            delay_type = "days"
        else:
            delay_value = delay_hours
            delay_type = "hours"
        
        step_data = {
            "id": str(step["_id"]),
            "template_id": step["email_template_id"],
            "delay_value": delay_value,
            "delay_type": delay_type,
            "segment_conditions": step.get("segment_conditions", []),
            "step_order": step["step_order"]
        }
        rule_response["steps"].append(step_data)
    
    return rule_response


@router.put("/rules/{rule_id}")
async def update_automation_rule(rule_id: str, rule_data: AutomationRuleUpdate):
    """Update an automation rule"""
    try:
        object_id = ObjectId(rule_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid rule ID format")
    
    rules_collection = get_automation_rules_collection()
    steps_collection = get_automation_steps_collection()
    
    # Build update document
    update_doc = {}
    
    if rule_data.name is not None:
        update_doc["name"] = rule_data.name
    if rule_data.trigger is not None:
        update_doc["trigger"] = rule_data.trigger
    if rule_data.trigger_conditions is not None:
        update_doc["trigger_conditions"] = rule_data.trigger_conditions
    if rule_data.target_segments is not None:
        update_doc["target_segments"] = rule_data.target_segments
        await validate_segments_exist(rule_data.target_segments)
    if rule_data.target_lists is not None:
        update_doc["target_lists"] = rule_data.target_lists
    if rule_data.active is not None:
        update_doc["status"] = "active" if rule_data.active else "draft"
    if rule_data.email_config is not None:
        update_doc["email_config"] = rule_data.email_config.dict()
    
    # Update timezone settings
    if rule_data.timezone is not None:
        update_doc["timezone"] = rule_data.timezone
    if rule_data.use_subscriber_timezone is not None:
        update_doc["use_subscriber_timezone"] = rule_data.use_subscriber_timezone
    if rule_data.respect_quiet_hours is not None:
        update_doc["respect_quiet_hours"] = rule_data.respect_quiet_hours
    if rule_data.quiet_hours_start is not None:
        update_doc["quiet_hours_start"] = rule_data.quiet_hours_start
    if rule_data.quiet_hours_end is not None:
        update_doc["quiet_hours_end"] = rule_data.quiet_hours_end
    
    # Update steps if provided
    if rule_data.steps is not None:
        # Validate templates
        template_ids = [step.template_id for step in rule_data.steps]
        await validate_templates_exist(template_ids)
        
        # Delete existing steps
        await steps_collection.delete_many({"automation_rule_id": rule_id})
        
        # Insert new steps
        for idx, step in enumerate(rule_data.steps):
            delay_hours = step.delay_value
            if step.delay_type == "days":
                delay_hours = step.delay_value * 24
            elif step.delay_type == "weeks":
                delay_hours = step.delay_value * 168
            
            step_doc = {
                "automation_rule_id": rule_id,
                "email_template_id": step.template_id,
                "delay_hours": delay_hours,
                "delay_value": step.delay_value,
                "delay_type": step.delay_type,
                "segment_conditions": step.segment_conditions or [],
                "conditions": step.conditions or {},
                "step_order": idx + 1,
                "created_at": datetime.utcnow()
            }
            await steps_collection.insert_one(step_doc)
    
    if update_doc:
        update_doc["updated_at"] = datetime.utcnow()
        result = await rules_collection.update_one(
            {"_id": object_id},
            {"$set": update_doc}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Automation not found")
    
    return {"message": "Automation rule updated successfully"}


@router.delete("/rules/{rule_id}")
async def delete_automation_rule(rule_id: str):
    """Soft delete an automation rule"""
    try:
        object_id = ObjectId(rule_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid rule ID format")
    
    rules_collection = get_automation_rules_collection()
    
    result = await rules_collection.update_one(
        {"_id": object_id},
        {"$set": {
            "deleted_at": datetime.utcnow(),
            "status": "deleted",
            "updated_at": datetime.utcnow()
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Automation not found")
    
    return {"message": "Automation rule deleted successfully"}


@router.post("/rules/{rule_id}/status")
async def update_automation_status(rule_id: str, status_data: Dict[str, str]):
    """Toggle automation active status"""
    try:
        object_id = ObjectId(rule_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid rule ID format")
    
    rules_collection = get_automation_rules_collection()
    
    new_status = status_data.get("status")
    if new_status not in ["active", "draft", "paused"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    result = await rules_collection.update_one(
        {"_id": object_id},
        {"$set": {
            "status": new_status,
            "updated_at": datetime.utcnow()
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Automation not found")
    
    return {"message": "Status updated successfully", "status": new_status}


@router.get("/rules/{rule_id}/analytics")
async def get_automation_analytics(rule_id: str):
    """Get analytics for a specific automation"""
    try:
        object_id = ObjectId(rule_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid rule ID format")
    
    rules_collection = get_automation_rules_collection()
    executions_collection = get_automation_executions_collection()
    
    rule = await rules_collection.find_one({"_id": object_id})
    if not rule:
        raise HTTPException(status_code=404, detail="Automation not found")
    
    # Get execution stats
    total_executions = await executions_collection.count_documents({
        "automation_rule_id": rule_id
    })
    
    completed_executions = await executions_collection.count_documents({
        "automation_rule_id": rule_id,
        "status": "completed"
    })
    
    failed_executions = await executions_collection.count_documents({
        "automation_rule_id": rule_id,
        "status": "failed"
    })
    
    # Calculate rates
    emails_sent = rule.get("emails_sent", 0)
    emails_opened = rule.get("emails_opened", 0)
    emails_clicked = rule.get("emails_clicked", 0)
    
    open_rate = (emails_opened / emails_sent * 100) if emails_sent > 0 else 0
    click_rate = (emails_clicked / emails_sent * 100) if emails_sent > 0 else 0
    
    return {
        "rule_id": rule_id,
        "rule_name": rule["name"],
        "emails_sent": emails_sent,
        "emails_opened": emails_opened,
        "emails_clicked": emails_clicked,
        "open_rate": round(open_rate, 2),
        "click_rate": round(click_rate, 2),
        "total_executions": total_executions,
        "completed_executions": completed_executions,
        "failed_executions": failed_executions,
        "subscribers_entered": rule.get("subscribers_entered", 0),
        "subscribers_completed": rule.get("subscribers_completed", 0)
    }


@router.post("/trigger")
async def trigger_automation(background_tasks: BackgroundTasks, trigger_data: Dict[str, Any]):
    """
    Manually trigger automation for testing
    """
    from tasks.automation_tasks import process_automation_trigger
    
    trigger_type = trigger_data.get("trigger")
    subscriber_id = trigger_data.get("subscriber_id")
    
    if not trigger_type or not subscriber_id:
        raise HTTPException(
            status_code=400,
            detail="Both trigger and subscriber_id are required"
        )
    
    # Queue the automation trigger task
    task = process_automation_trigger.delay(
        trigger_type=trigger_type,
        subscriber_id=subscriber_id,
        trigger_data=trigger_data
    )
    
    return {
        "message": "Automation trigger queued",
        "task_id": task.id,
        "trigger": trigger_type,
        "subscriber_id": subscriber_id
    }