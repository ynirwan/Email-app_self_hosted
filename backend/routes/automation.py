# backend/routes/automation.py
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, validator
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from enum import Enum
import uuid
from bson import ObjectId

from database import (
    get_automation_rules_collection,
    get_automation_steps_collection,
    get_automation_executions_collection,
    get_subscribers_collection,
    get_templates_collection,
    get_segments_collection,
    get_audit_collection
)

# ===========================
# PYDANTIC SCHEMAS
# ===========================

class AutomationStepCreate(BaseModel):
    template_id: str
    delay_value: int = 1
    delay_type: str = "hours"  # hours, days, weeks
    segment_conditions: Optional[List[str]] = []  # Segment IDs for conditional sending
    conditions: Optional[Dict[str, Any]] = {}

class AutomationRuleCreate(BaseModel):
    name: str
    trigger: str  # welcome, birthday, abandoned_cart, etc.
    trigger_conditions: Dict[str, Any] = {}
    target_segments: Optional[List[str]] = []  # Initial segments to target
    active: bool = False
    steps: List[AutomationStepCreate] = []

class AutomationRuleResponse(BaseModel):
    id: str
    name: str
    trigger: str
    trigger_conditions: Dict[str, Any] = {}
    target_segments: List[str] = []
    status: str
    active: bool = False
    emails_sent: int = 0
    open_rate: float = 0.0
    click_rate: float = 0.0
    created_at: datetime
    updated_at: datetime
    steps: List[Dict] = []

# ===========================
# VALIDATION FUNCTIONS
# ===========================

async def validate_templates_exist(template_ids: List[str]) -> bool:
    """Validate that all template IDs exist using your existing templates system"""
    templates_collection = get_templates_collection()

    for template_id in template_ids:
        if not ObjectId.is_valid(template_id):
            raise HTTPException(status_code=400, detail=f"Invalid template ID: {template_id}")

        template = await templates_collection.find_one({"_id": ObjectId(template_id)})
        if not template:
            raise HTTPException(status_code=400, detail=f"Template {template_id} not found")

    return True

async def validate_segments_exist(segment_ids: List[str]) -> bool:
    """Validate that all segment IDs exist using your existing segments system"""
    segments_collection = get_segments_collection()

    for segment_id in segment_ids:
        if not ObjectId.is_valid(segment_id):
            raise HTTPException(status_code=400, detail=f"Invalid segment ID: {segment_id}")

        segment = await segments_collection.find_one({"_id": ObjectId(segment_id)})
        if not segment:
            raise HTTPException(status_code=400, detail=f"Segment {segment_id} not found")

    return True

def convert_delay_to_hours(value: int, delay_type: str) -> int:
    """Convert delay to hours"""
    if delay_type == "hours":
        return value
    elif delay_type == "days":
        return value * 24
    elif delay_type == "weeks":
        return value * 24 * 7
    return value

async def log_automation_activity(action: str, automation_id: str, details: str):
    """Log automation activity using your existing audit system"""
    try:
        audit_collection = get_audit_collection()
        log_entry = {
            "timestamp": datetime.utcnow(),
            "action": action,
            "entity_type": "automation",
            "entity_id": automation_id,
            "details": details,
            "system": "email_automation"
        }
        await audit_collection.insert_one(log_entry)
    except Exception as e:
        print(f"Failed to log automation activity: {e}")

# ===========================
# ROUTER WITH CORRECT ORDER
# ===========================

router = APIRouter(prefix="/automation", tags=["automation"])

# ✅ TEMPLATES & SEGMENTS ENDPOINTS FIRST
@router.get("/templates")
async def get_templates_for_automation():
    """Get templates for automation builder - Uses your existing templates system"""
    templates_collection = get_templates_collection()
    templates = []

    cursor = templates_collection.find()
    async for template in cursor:
        templates.append({
            "id": str(template["_id"]),
            "name": template.get("name", "Untitled"),
            "subject": template.get("subject", ""),
            "type": template.get("type", "html"),
            "created_at": template.get("created_at")
        })

    return templates

@router.get("/segments")
async def get_segments_for_automation():
    """Get segments for automation targeting - Uses your existing segments system"""
    segments_collection = get_segments_collection()
    segments = []

    # Get only active segments
    cursor = segments_collection.find({"is_active": True})
    async for segment in cursor:
        segments.append({
            "id": str(segment["_id"]),
            "name": segment["name"],
            "description": segment.get("description", ""),
            "subscriber_count": segment.get("subscriber_count", 0),
            "criteria_types": segment.get("criteria_types", []),
            "last_calculated": segment.get("last_calculated")
        })

    return segments

# ✅ SPECIFIC ROUTES BEFORE GENERAL ONES
@router.get("/rules/{rule_id}/analytics")
async def get_automation_analytics(
    rule_id: str,
    range: str = Query(default="30d")
):
    """Get analytics for a specific automation rule"""
    # Verify rule exists
    rules_collection = get_automation_rules_collection()
    try:
        object_id = ObjectId(rule_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid rule ID format")
    
    rule = await rules_collection.find_one({
        "_id": object_id,
        "deleted_at": {"$exists": False}
    })
    
    if not rule:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    
    # Calculate date range
    try:
        days = int(range.replace('d', ''))
    except:
        days = 30
        
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Get executions in date range
    executions_collection = get_automation_executions_collection()
    executions = await executions_collection.find({
        "automation_rule_id": rule_id,
        "executed_at": {"$gte": start_date}
    }).to_list(None)
    
    # Get subscriber count
    subscribers_collection = get_subscribers_collection()
    active_subscribers = await subscribers_collection.count_documents({"status": "active"})
    
    # Calculate analytics
    total_sent = len(executions)
    total_opens = len([e for e in executions if e.get('opened_at')])
    total_clicks = len([e for e in executions if e.get('clicked_at')])
    
    # Get step performance
    steps_collection = get_automation_steps_collection()
    steps = await steps_collection.find({
        "automation_rule_id": rule_id
    }).sort("step_order", 1).to_list(None)
    
    email_performance = []
    for step in steps:
        step_executions = [e for e in executions if e.get('automation_step_id') == str(step['_id'])]
        
        # Get template subject
        templates_collection = get_templates_collection()
        template = await templates_collection.find_one({"_id": ObjectId(step['email_template_id'])})
        subject = template.get('subject', f"Email {step['step_order']}") if template else f"Email {step['step_order']}"
        
        step_opens = len([e for e in step_executions if e.get('opened_at')])
        step_clicks = len([e for e in step_executions if e.get('clicked_at')])
        
        email_performance.append({
            "step_order": step['step_order'],
            "subject": subject,
            "sent": len(step_executions),
            "opens": step_opens,
            "clicks": step_clicks,
            "open_rate": (step_opens / len(step_executions) * 100) if step_executions else 0,
            "click_rate": (step_clicks / len(step_executions) * 100) if step_executions else 0
        })
    
    return {
        "total_sent": total_sent,
        "total_delivered": total_sent,
        "total_opens": total_opens,
        "total_clicks": total_clicks,
        "open_rate": (total_opens / total_sent * 100) if total_sent > 0 else 0,
        "click_rate": (total_clicks / total_sent * 100) if total_sent > 0 else 0,
        "bounce_rate": 0.0,
        "active_subscribers": active_subscribers,
        "email_performance": email_performance
    }

@router.post("/rules/{rule_id}/trigger")
async def trigger_automation_manually(
    rule_id: str,
    background_tasks: BackgroundTasks,
    target_segments: Optional[List[str]] = None
):
    """Manually trigger automation for specific segments"""
    # Get automation rule
    rules_collection = get_automation_rules_collection()
    rule = await rules_collection.find_one({
        "_id": ObjectId(rule_id),
        "deleted_at": {"$exists": False}
    })

    if not rule:
        raise HTTPException(status_code=404, detail="Automation rule not found")

    # Determine which segments to target
    segments_to_target = target_segments or rule.get("target_segments", [])

    if not segments_to_target:
        raise HTTPException(status_code=400, detail="No target segments specified")

    # Validate segments exist
    await validate_segments_exist(segments_to_target)

    return {
        "message": "Automation triggered successfully",
        "subscribers_count": 0,  # Implement actual logic
        "segments_count": len(segments_to_target)
    }

@router.put("/rules/{rule_id}/status")
async def update_automation_status(rule_id: str, status_data: Dict[str, str]):
    """Update automation status"""
    rules_collection = get_automation_rules_collection()

    result = await rules_collection.update_one(
        {"_id": ObjectId(rule_id)},
        {"$set": {
            "status": status_data["status"],
            "updated_at": datetime.utcnow()
        }}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Automation not found")

    return {"message": "Status updated successfully"}

# ✅ GENERAL ROUTES AFTER SPECIFIC ONES
@router.get("/rules/{rule_id}")
async def get_automation_rule(rule_id: str):
    """Get a specific automation rule by ID"""
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
        "status": rule.get("status", "draft"),
        "active": rule.get("status") == "active",
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

# ✅ PUT ROUTE MOVED TO CORRECT POSITION
@router.put("/rules/{rule_id}")
async def update_automation_rule(
    rule_id: str,
    rule_data: AutomationRuleCreate
):
    """Update an existing automation rule"""
    try:
        object_id = ObjectId(rule_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid rule ID format")
    
    rules_collection = get_automation_rules_collection()
    steps_collection = get_automation_steps_collection()
    
    # Check if rule exists
    existing_rule = await rules_collection.find_one({
        "_id": object_id,
        "deleted_at": {"$exists": False}
    })
    
    if not existing_rule:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    
    # Validate templates exist (only non-empty template_ids)
    template_ids = [step.template_id for step in rule_data.steps if step.template_id]
    if template_ids:
        await validate_templates_exist(template_ids)
    
    # Validate segments exist
    if rule_data.target_segments:
        await validate_segments_exist(rule_data.target_segments)
    
    # Update the automation rule
    update_data = {
        "name": rule_data.name,
        "trigger": rule_data.trigger,
        "trigger_conditions": rule_data.trigger_conditions,
        "target_segments": rule_data.target_segments,
        "status": "active" if rule_data.active else "draft",
        "updated_at": datetime.utcnow()
    }
    
    await rules_collection.update_one(
        {"_id": object_id},
        {"$set": update_data}
    )
    
    # Remove existing steps
    await steps_collection.delete_many({"automation_rule_id": rule_id})
    
    # Add new steps (only if template_id is provided)
    for i, step_data in enumerate(rule_data.steps):
        if not step_data.template_id:  # Skip steps without template
            continue
            
        delay_hours = convert_delay_to_hours(step_data.delay_value, step_data.delay_type)
        
        automation_step = {
            "_id": ObjectId(),
            "automation_rule_id": rule_id,
            "step_order": i + 1,
            "email_template_id": step_data.template_id,
            "delay_hours": delay_hours,
            "segment_conditions": step_data.segment_conditions or [],
            "conditions": step_data.conditions or {},
            "created_at": datetime.utcnow()
        }
        await steps_collection.insert_one(automation_step)
    
    # Log activity
    await log_automation_activity(
        action="update",
        automation_id=rule_id,
        details=f"Updated automation '{rule_data.name}' with {len([s for s in rule_data.steps if s.template_id])} steps"
    )
    
    return {"message": "Automation updated successfully", "automation_id": rule_id}

@router.delete("/rules/{rule_id}")
async def delete_automation_rule(rule_id: str):
    """Soft delete automation rule"""
    rules_collection = get_automation_rules_collection()

    result = await rules_collection.update_one(
        {"_id": ObjectId(rule_id)},
        {"$set": {
            "deleted_at": datetime.utcnow(),
            "status": "deleted"
        }}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Automation not found")

    return {"message": "Automation deleted successfully"}

@router.get("/rules")
async def get_automation_rules():
    """Get all automation rules"""
    collection = get_automation_rules_collection()
    rules = await collection.find({"deleted_at": {"$exists": False}}).to_list(None)

    response_rules = []
    for rule in rules:
        rule_dict = {
            "id": str(rule["_id"]),
            "name": rule["name"],
            "trigger": rule["trigger"],
            "trigger_conditions": rule.get("trigger_conditions", {}),
            "target_segments": rule.get("target_segments", []),
            "status": rule.get("status", "draft"),
            "active": rule.get("status") == "active",
            "created_at": rule["created_at"],
            "updated_at": rule["updated_at"],
            "emails_sent": 0,  # Calculate from executions
            "open_rate": 0.0,  # Calculate from executions
            "click_rate": 0.0  # Calculate from executions
        }

        # Get steps
        steps_collection = get_automation_steps_collection()
        steps = await steps_collection.find({
            "automation_rule_id": str(rule["_id"])
        }).sort("step_order", 1).to_list(None)

        rule_dict["steps"] = [
            {
                "id": str(step["_id"]),
                "template_id": step["email_template_id"],
                "delay_hours": step["delay_hours"],
                "segment_conditions": step.get("segment_conditions", []),
                "step_order": step["step_order"]
            }
            for step in steps
        ]

        response_rules.append(rule_dict)

    return response_rules

@router.post("/rules")
async def create_automation_rule(
    rule_data: AutomationRuleCreate,
    background_tasks: BackgroundTasks
):
    """Create automation rule - Compatible with your templates and segments"""

    # Validate templates using your existing system (only non-empty template_ids)
    template_ids = [step.template_id for step in rule_data.steps if step.template_id]
    if template_ids:
        await validate_templates_exist(template_ids)

    # Validate segments using your existing system
    if rule_data.target_segments:
        await validate_segments_exist(rule_data.target_segments)

    # Create automation rule
    automation_rule = {
        "_id": ObjectId(),
        "name": rule_data.name,
        "trigger": rule_data.trigger,
        "trigger_conditions": rule_data.trigger_conditions,
        "target_segments": rule_data.target_segments,
        "status": "active" if rule_data.active else "draft",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }

    rules_collection = get_automation_rules_collection()
    result = await rules_collection.insert_one(automation_rule)
    rule_id = str(result.inserted_id)

    # Create steps (only if template_id is provided)
    steps_collection = get_automation_steps_collection()
    for i, step_data in enumerate(rule_data.steps):
        if not step_data.template_id:  # Skip steps without template
            continue
            
        delay_hours = convert_delay_to_hours(step_data.delay_value, step_data.delay_type)

        automation_step = {
            "_id": ObjectId(),
            "automation_rule_id": rule_id,
            "step_order": i + 1,
            "email_template_id": step_data.template_id,
            "delay_hours": delay_hours,
            "segment_conditions": step_data.segment_conditions,
            "conditions": step_data.conditions,
            "created_at": datetime.utcnow()
        }
        await steps_collection.insert_one(automation_step)

    # Log in your audit system
    await log_automation_activity(
        action="create",
        automation_id=rule_id,
        details=f"Created automation '{rule_data.name}' with {len([s for s in rule_data.steps if s.template_id])} steps"
    )

    return {"message": "Automation created successfully", "automation_id": rule_id}

