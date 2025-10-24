# backend/routes/automation.py
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, validator, EmailStr
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

# Email configuration
    email_config: EmailConfig
    
    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Automation name is required')
        if len(v) > 200:
            raise ValueError('Name must be less than 200 characters')
        return v.strip()
    
    @validator('steps')
    def validate_steps(cls, v):
        if len(v) == 0:
            raise ValueError('At least one email step is required')
        return v
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
        {"_id": {"$in": valid_ids}, "is_active": True},
        {"_id": 1}
    ).to_list(length=len(valid_ids))
    
    existing_ids = {str(s["_id"]) for s in existing_segments}
    
    missing_ids = set(segment_ids) - existing_ids
    if missing_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Segments not found or inactive: {', '.join(missing_ids)}"
        )
    
    return {sid: sid in existing_ids for sid in segment_ids}

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
async def get_templates_for_automation(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    search: Optional[str] = None
):
    """Get templates with pagination and search"""
    from database import get_templates_collection
    
    templates_collection = get_templates_collection()
    
    # Build query with optional search
    query = {"deleted_at": {"$exists": False}}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"subject": {"$regex": search, "$options": "i"}}
        ]
    
    # Get total count for pagination
    total = await templates_collection.count_documents(query)
    
    # Fetch with projection (only needed fields)
    cursor = templates_collection.find(
        query,
        {
            "_id": 1,
            "name": 1,
            "subject": 1,
            "type": 1,
            "created_at": 1,
            "thumbnail": 1  # If you have preview images
        }
    ).skip(skip).limit(limit).sort("created_at", -1)
    
    templates = []
    async for template in cursor:
        templates.append({
            "id": str(template["_id"]),
            "name": template.get("name", "Untitled"),
            "subject": template.get("subject", ""),
            "type": template.get("type", "html"),
            "created_at": template.get("created_at"),
            "thumbnail": template.get("thumbnail")
        })
    
    return {
        "templates": templates,
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + limit) < total
    }

@router.get("/segments")
async def get_segments_for_automation(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    include_stats: bool = Query(False)
):
    """Get segments with pagination and optional statistics"""
    from database import get_segments_collection, get_subscribers_collection
    
    segments_collection = get_segments_collection()
    
    query = {
        "is_active": True,
        "deleted_at": {"$exists": False}
    }
    
    total = await segments_collection.count_documents(query)
    
    # Use projection for performance
    projection = {
        "_id": 1,
        "name": 1,
        "description": 1,
        "subscriber_count": 1,
        "criteria_types": 1,
        "last_calculated": 1
    }
    
    cursor = segments_collection.find(
        query, 
        projection
    ).skip(skip).limit(limit).sort("name", 1)
    
    segments = []
    async for segment in cursor:
        segment_data = {
            "id": str(segment["_id"]),
            "name": segment["name"],
            "description": segment.get("description", ""),
            "subscriber_count": segment.get("subscriber_count", 0),
            "criteria_types": segment.get("criteria_types", []),
            "last_calculated": segment.get("last_calculated")
        }
        
        # Optional: Get real-time subscriber count if requested
        if include_stats:
            subscribers_collection = get_subscribers_collection()
            actual_count = await subscribers_collection.count_documents({
                "segments": str(segment["_id"]),
                "status": "active"
            })
            segment_data["actual_subscriber_count"] = actual_count
        
        segments.append(segment_data)
    
    return {
        "segments": segments,
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + limit) < total
    }

# ✅ SPECIFIC ROUTES BEFORE GENERAL ONES
@router.get("/rules/{rule_id}/analytics")
async def get_automation_analytics(
    rule_id: str,
    range: str = Query(default="30d", regex="^[0-9]+d$")
):
    """Optimized analytics with aggregation pipeline"""
    from database import (
        get_automation_rules_collection,
        get_automation_executions_collection,
        get_automation_steps_collection,
        get_templates_collection,
        get_subscribers_collection
    )
    
    # Verify rule exists
    if not ObjectId.is_valid(rule_id):
        raise HTTPException(status_code=400, detail="Invalid rule ID format")
    
    rules_collection = get_automation_rules_collection()
    rule = await rules_collection.find_one({
        "_id": ObjectId(rule_id),
        "deleted_at": {"$exists": False}
    })
    
    if not rule:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    
    # Calculate date range
    days = int(range.replace('d', ''))
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Use aggregation pipeline for better performance
    executions_collection = get_automation_executions_collection()
    
    # Aggregate execution statistics
    pipeline = [
        {
            "$match": {
                "automation_rule_id": rule_id,
                "executed_at": {"$gte": start_date}
            }
        },
        {
            "$group": {
                "_id": "$automation_step_id",
                "total_sent": {"$sum": 1},
                "total_opened": {
                    "$sum": {"$cond": [{"$ifNull": ["$opened_at", False]}, 1, 0]}
                },
                "total_clicked": {
                    "$sum": {"$cond": [{"$ifNull": ["$clicked_at", False]}, 1, 0]}
                },
                "total_bounced": {
                    "$sum": {"$cond": [{"$ifNull": ["$bounced_at", False]}, 1, 0]}
                },
                "total_unsubscribed": {
                    "$sum": {"$cond": [{"$ifNull": ["$unsubscribed_at", False]}, 1, 0]}
                }
            }
        }
    ]
    
    execution_stats = await executions_collection.aggregate(pipeline).to_list(None)
    
    # Create lookup map for step stats
    stats_by_step = {
        stat["_id"]: stat for stat in execution_stats
    }
    
    # Get steps with template info
    steps_collection = get_automation_steps_collection()
    templates_collection = get_templates_collection()
    
    steps = await steps_collection.find({
        "automation_rule_id": rule_id
    }).sort("step_order", 1).to_list(None)
    
    # Batch fetch templates
    template_ids = [ObjectId(step["email_template_id"]) for step in steps]
    templates = await templates_collection.find(
        {"_id": {"$in": template_ids}},
        {"_id": 1, "subject": 1, "name": 1}
    ).to_list(None)
    
    template_map = {str(t["_id"]): t for t in templates}
    
    # Calculate email performance
    email_performance = []
    total_sent = 0
    total_opened = 0
    total_clicked = 0
    total_bounced = 0
    total_unsubscribed = 0
    
    for step in steps:
        step_id = str(step["_id"])
        stats = stats_by_step.get(step_id, {})
        
        sent = stats.get("total_sent", 0)
        opened = stats.get("total_opened", 0)
        clicked = stats.get("total_clicked", 0)
        bounced = stats.get("total_bounced", 0)
        unsubscribed = stats.get("total_unsubscribed", 0)
        
        total_sent += sent
        total_opened += opened
        total_clicked += clicked
        total_bounced += bounced
        total_unsubscribed += unsubscribed
        
        template = template_map.get(step["email_template_id"], {})
        subject = template.get("subject") or template.get("name", f"Email {step['step_order']}")
        
        email_performance.append({
            "step_id": step_id,
            "step_order": step["step_order"],
            "subject": subject,
            "sent": sent,
            "opened": opened,
            "clicked": clicked,
            "bounced": bounced,
            "unsubscribed": unsubscribed,
            "open_rate": round((opened / sent * 100), 2) if sent > 0 else 0,
            "click_rate": round((clicked / sent * 100), 2) if sent > 0 else 0,
            "bounce_rate": round((bounced / sent * 100), 2) if sent > 0 else 0,
            "unsubscribe_rate": round((unsubscribed / sent * 100), 2) if sent > 0 else 0
        })
    
    # Get active subscriber count
    subscribers_collection = get_subscribers_collection()
    active_subscribers = await subscribers_collection.count_documents({
        "status": "active"
    })
    
    return {
        "rule_id": rule_id,
        "rule_name": rule.get("name"),
        "date_range": f"{days} days",
        "total_sent": total_sent,
        "total_delivered": total_sent - total_bounced,
        "total_opened": total_opened,
        "total_clicked": total_clicked,
        "total_bounced": total_bounced,
        "total_unsubscribed": total_unsubscribed,
        "open_rate": round((total_opened / total_sent * 100), 2) if total_sent > 0 else 0,
        "click_rate": round((total_clicked / total_sent * 100), 2) if total_sent > 0 else 0,
        "bounce_rate": round((total_bounced / total_sent * 100), 2) if total_sent > 0 else 0,
        "unsubscribe_rate": round((total_unsubscribed / total_sent * 100), 2) if total_sent > 0 else 0,
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

@router.put("/rules/{rule_id}")
async def update_automation_rule(rule_id: str, automation: AutomationRuleCreate):
    """Update existing automation rule"""
    try:
        if not ObjectId.is_valid(rule_id):
            raise HTTPException(status_code=400, detail="Invalid rule ID")

        automation_rules_collection = get_automation_rules_collection()
        automation_steps_collection = get_automation_steps_collection()

        # Update automation rule
        update_data = {
            "name": automation.name,
            "description": automation.description,
            "trigger": automation.trigger,
            "trigger_conditions": automation.trigger_conditions,
            "target_segments": automation.target_segments,
            "status": "active" if automation.active else "draft",
            "email_config": {
                "sender_email": automation.email_config.sender_email,
                "sender_name": automation.email_config.sender_name,
                "reply_to": automation.email_config.reply_to or automation.email_config.sender_email
            },
            "updated_at": datetime.utcnow()
        }

        result = await automation_rules_collection.update_one(
            {"_id": ObjectId(rule_id)},
            {"$set": update_data}
        )

        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Automation rule not found")

        # Delete old steps
        await automation_steps_collection.delete_many({"automation_rule_id": rule_id})

        # Create new steps
        for index, step in enumerate(automation.steps):
            delay_hours = step.delay_value
            if step.delay_type == "days":
                delay_hours = step.delay_value * 24
            elif step.delay_type == "weeks":
                delay_hours = step.delay_value * 24 * 7

            step_doc = {
                "_id": ObjectId(),
                "automation_rule_id": rule_id,
                "step_order": index + 1,
                "email_template_id": step.template_id,
                "delay_hours": delay_hours,
                "delay_type": step.delay_type,
                "delay_value": step.delay_value,
                "created_at": datetime.utcnow()
            }

            await automation_steps_collection.insert_one(step_doc)

        # Log activity (use `automation`, not undefined `rule_data`)
        await log_automation_activity(
            action="update",
            automation_id=rule_id,
            details=f"Updated automation '{automation.name}' with {len([s for s in automation.steps if s.template_id])} steps"
        )

        return {"message": "Automation updated successfully", "automation_id": rule_id}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
async def create_automation_rule(automation: AutomationRuleCreate):
    """Create new automation rule with email configuration"""
    try:
        automation_rules_collection = get_automation_rules_collection()
        automation_steps_collection = get_automation_steps_collection()
        
        # Create automation rule document
        rule_doc = {
            "_id": ObjectId(),
            "name": automation.name,
            "description": automation.description,
            "trigger": automation.trigger,
            "trigger_conditions": automation.trigger_conditions,
            "target_segments": automation.target_segments,
            "status": "active" if automation.active else "draft",
            
            # Email configuration
            "email_config": {
                "sender_email": automation.email_config.sender_email,
                "sender_name": automation.email_config.sender_name,
                "reply_to": automation.email_config.reply_to or automation.email_config.sender_email
            },
            
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "emails_sent": 0,
            "open_rate": 0,
            "click_rate": 0
        }
        
        result = await automation_rules_collection.insert_one(rule_doc)
        rule_id = str(result.inserted_id)
        
        # Create automation steps
        for index, step in enumerate(automation.steps):
            # Convert delay to hours
            delay_hours = step.delay_value
            if step.delay_type == "days":
                delay_hours = step.delay_value * 24
            elif step.delay_type == "weeks":
                delay_hours = step.delay_value * 24 * 7
            
            step_doc = {
                "_id": ObjectId(),
                "automation_rule_id": rule_id,
                "step_order": index + 1,
                "email_template_id": step.template_id,
                "delay_hours": delay_hours,
                "delay_type": step.delay_type,
                "delay_value": step.delay_value,
                "created_at": datetime.utcnow()
            }
            
            await automation_steps_collection.insert_one(step_doc)
        
        return {
            "message": "Automation rule created successfully",
            "id": rule_id,
            "name": automation.name,
            "status": rule_doc["status"]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))