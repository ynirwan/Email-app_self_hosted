# backend/routes/automation_advanced.py
"""
Advanced automation features:
- Conditional branching (A/B paths)
- Wait for conditions
- Goal tracking
- Smart send time optimization
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime, timedelta
from bson import ObjectId
from enum import Enum

from database import (
    get_automation_rules_collection,
    get_automation_steps_collection,
    get_automation_executions_collection,
    get_subscribers_collection,
    get_email_events_collection
)

router = APIRouter(prefix="/automation/advanced", tags=["automation-advanced"])


# ===========================
# ENHANCED SCHEMAS
# ===========================

class StepType(str, Enum):
    EMAIL = "email"
    DELAY = "delay"
    CONDITION = "condition"
    AB_SPLIT = "ab_split"
    WAIT_FOR_EVENT = "wait_for_event"
    GOAL_CHECK = "goal_check"
    SEND_WEBHOOK = "send_webhook"
    UPDATE_FIELD = "update_field"


class ConditionOperator(str, Enum):
    OPENED_EMAIL = "opened_email"
    CLICKED_LINK = "clicked_link"
    NOT_OPENED = "not_opened"
    FIELD_EQUALS = "field_equals"
    FIELD_CONTAINS = "field_contains"
    SEGMENT_MATCH = "segment_match"
    TAG_HAS = "tag_has"
    CUSTOM_EVENT = "custom_event"


class GoalType(str, Enum):
    PURCHASE = "purchase"
    SIGNUP = "signup"
    DOWNLOAD = "download"
    CLICK = "click"
    OPEN = "open"
    CUSTOM = "custom"


class ABTestConfig(BaseModel):
    """A/B test configuration for automation steps"""
    variant_a_percentage: int = Field(50, ge=0, le=100)
    variant_b_percentage: int = Field(50, ge=0, le=100)
    variant_a_template_id: str
    variant_b_template_id: str

    variant_a_subject: Optional[str] = None
    variant_b_subject: Optional[str] = None

    winning_metric: Literal["open_rate", "click_rate", "conversion_rate"] = "open_rate"
    test_duration_hours: int = Field(24, ge=1)
    
    @validator('variant_a_percentage', 'variant_b_percentage')
    def validate_percentages(cls, v, values):
        if 'variant_a_percentage' in values and 'variant_b_percentage' in values:
            if values['variant_a_percentage'] + v != 100:
                raise ValueError("Variant percentages must sum to 100")
        return v


class ConditionalBranch(BaseModel):
    """Conditional branch configuration"""
    condition_type: ConditionOperator
    condition_value: Optional[Any] = None
    true_path_step_ids: List[str] = []
    false_path_step_ids: List[str] = []
    wait_time_hours: int = Field(24, description="Time to wait before checking condition")
    timeout_path: Literal["true", "false", "exit"] = "false"


class WaitForEventConfig(BaseModel):
    """Wait for specific event configuration"""
    event_type: str  # opened_email, clicked_link, made_purchase, etc.
    event_source: Optional[str] = None  # specific email, link, etc.
    max_wait_hours: int = Field(168, description="Max hours to wait (default 7 days)")
    timeout_action: Literal["continue", "exit", "alternate_path"] = "continue"
    alternate_step_ids: List[str] = []


class GoalTracking(BaseModel):
    """Goal tracking configuration"""
    goal_type: GoalType
    goal_value: Optional[float] = None  # For revenue goals
    tracking_window_days: int = Field(30, ge=1)
    conversion_url: Optional[str] = None


class SmartSendTimeConfig(BaseModel):
    """Smart send time optimization"""
    enabled: bool = False
    optimize_for: Literal["opens", "clicks", "engagement"] = "opens"
    time_window_start: int = Field(8, ge=0, le=23, description="Hour (0-23)")
    time_window_end: int = Field(20, ge=0, le=23, description="Hour (0-23)")
    respect_timezone: bool = True
    fallback_time: int = Field(10, ge=0, le=23)


class AdvancedAutomationStep(BaseModel):
    """Enhanced automation step with advanced features"""
    step_type: StepType
    step_order: int
    
    # Email step fields
    template_id: Optional[str] = None
    subject_line: Optional[str] = None
    
    # Delay configuration
    delay_value: int = 1
    delay_type: Literal["hours", "days", "weeks"] = "hours"
    
    # Conditional branching
    conditional_branch: Optional[ConditionalBranch] = None
    
    # A/B testing
    ab_test_config: Optional[ABTestConfig] = None
    
    # Wait for event
    wait_for_event: Optional[WaitForEventConfig] = None
    
    # Goal tracking
    goal_tracking: Optional[GoalTracking] = None
    
    # Smart send time
    smart_send_time: Optional[SmartSendTimeConfig] = None
    
    # Segment filtering
    segment_conditions: List[str] = []
    
    # Webhook configuration
    webhook_url: Optional[str] = None
    webhook_payload: Optional[Dict[str, Any]] = None
    
    # Field update
    field_updates: Optional[Dict[str, Any]] = None


class AdvancedAutomationCreate(BaseModel):
    """Create advanced automation rule"""
    name: str
    description: Optional[str] = None
    trigger: str
    trigger_conditions: Dict[str, Any] = {}
    target_segments: List[str] = []
    steps: List[AdvancedAutomationStep]
    
    # Goal configuration
    primary_goal: Optional[GoalTracking] = None
    
    # Exit conditions
    exit_on_goal_achieved: bool = True
    exit_on_unsubscribe: bool = True
    
    # Active status
    active: bool = False


# ===========================
# ADVANCED ENDPOINTS
# ===========================

@router.post("/rules/advanced")
async def create_advanced_automation(
    automation: AdvancedAutomationCreate,
    background_tasks: BackgroundTasks
):
    """Create automation with advanced features"""
    from database import get_automation_rules_collection, get_automation_steps_collection
    
    rules_collection = get_automation_rules_collection()
    steps_collection = get_automation_steps_collection()
    
    # Create automation rule
    rule_doc = {
        "_id": ObjectId(),
        "name": automation.name,
        "description": automation.description,
        "trigger": automation.trigger,
        "trigger_conditions": automation.trigger_conditions,
        "target_segments": automation.target_segments,
        "status": "active" if automation.active else "draft",
        "type": "advanced",
        "primary_goal": automation.primary_goal.dict() if automation.primary_goal else None,
        "exit_on_goal_achieved": automation.exit_on_goal_achieved,
        "exit_on_unsubscribe": automation.exit_on_unsubscribe,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = await rules_collection.insert_one(rule_doc)
    rule_id = str(result.inserted_id)
    
    # Create steps with advanced configurations
    for step_data in automation.steps:
        step_doc = {
            "_id": ObjectId(),
            "automation_rule_id": rule_id,
            "step_order": step_data.step_order,
            "step_type": step_data.step_type,
            "email_template_id": step_data.template_id,
            "subject_line": step_data.subject_line,
            "delay_hours": convert_delay(step_data.delay_value, step_data.delay_type),
            "segment_conditions": step_data.segment_conditions,
            "conditional_branch": step_data.conditional_branch.dict() if step_data.conditional_branch else None,
            "ab_test_config": step_data.ab_test_config.dict() if step_data.ab_test_config else None,
            "wait_for_event": step_data.wait_for_event.dict() if step_data.wait_for_event else None,
            "goal_tracking": step_data.goal_tracking.dict() if step_data.goal_tracking else None,
            "smart_send_time": step_data.smart_send_time.dict() if step_data.smart_send_time else None,
            "webhook_url": step_data.webhook_url,
            "webhook_payload": step_data.webhook_payload,
            "field_updates": step_data.field_updates,
            "created_at": datetime.utcnow()
        }
        
        await steps_collection.insert_one(step_doc)
    
    return {
        "message": "Advanced automation created successfully",
        "automation_id": rule_id,
        "features_enabled": {
            "conditional_branching": any(s.conditional_branch for s in automation.steps),
            "ab_testing": any(s.ab_test_config for s in automation.steps),
            "wait_for_events": any(s.wait_for_event for s in automation.steps),
            "goal_tracking": automation.primary_goal is not None,
            "smart_send_time": any(s.smart_send_time and s.smart_send_time.enabled for s in automation.steps)
        }
    }


@router.get("/rules/{rule_id}/goal-performance")
async def get_goal_performance(
    rule_id: str,
    date_range: int = 30
):
    """Get goal achievement metrics for automation"""
    from database import get_automation_executions_collection
    
    if not ObjectId.is_valid(rule_id):
        raise HTTPException(status_code=400, detail="Invalid rule ID")
    
    executions_collection = get_automation_executions_collection()
    
    start_date = datetime.utcnow() - timedelta(days=date_range)
    
    # Aggregate goal achievements
    pipeline = [
        {
            "$match": {
                "automation_rule_id": rule_id,
                "executed_at": {"$gte": start_date}
            }
        },
        {
            "$group": {
                "_id": "$goal_achieved",
                "count": {"$sum": 1},
                "total_value": {"$sum": {"$ifNull": ["$goal_value", 0]}},
                "avg_time_to_goal": {"$avg": "$time_to_goal_hours"}
            }
        }
    ]
    
    results = await executions_collection.aggregate(pipeline).to_list(None)
    
    total_executions = sum(r["count"] for r in results)
    goal_achieved = next((r for r in results if r["_id"] == True), {})
    
    return {
        "rule_id": rule_id,
        "date_range_days": date_range,
        "total_executions": total_executions,
        "goals_achieved": goal_achieved.get("count", 0),
        "goal_achievement_rate": (goal_achieved.get("count", 0) / total_executions * 100) if total_executions > 0 else 0,
        "total_goal_value": goal_achieved.get("total_value", 0),
        "avg_time_to_goal_hours": goal_achieved.get("avg_time_to_goal", 0)
    }


@router.get("/rules/{rule_id}/path-analysis")
async def get_path_analysis(rule_id: str):
    """Analyze which conditional paths subscribers take"""
    from database import get_automation_executions_collection
    
    if not ObjectId.is_valid(rule_id):
        raise HTTPException(status_code=400, detail="Invalid rule ID")
    
    executions_collection = get_automation_executions_collection()
    
    # Get path data
    pipeline = [
        {
            "$match": {
                "automation_rule_id": rule_id,
                "step_type": "condition"
            }
        },
        {
            "$group": {
                "_id": {
                    "step_id": "$automation_step_id",
                    "path_taken": "$path_taken"
                },
                "count": {"$sum": 1}
            }
        }
    ]
    
    results = await executions_collection.aggregate(pipeline).to_list(None)
    
    # Format results
    path_analysis = {}
    for result in results:
        step_id = result["_id"]["step_id"]
        if step_id not in path_analysis:
            path_analysis[step_id] = {"true_path": 0, "false_path": 0, "timeout": 0}
        
        path_taken = result["_id"]["path_taken"]
        if path_taken:
            path_analysis[step_id][f"{path_taken}_path"] = result["count"]
    
    return {
        "rule_id": rule_id,
        "path_analysis": path_analysis
    }


@router.post("/rules/{rule_id}/optimize-send-times")
async def optimize_send_times(
    rule_id: str,
    background_tasks: BackgroundTasks
):
    """Analyze past performance and optimize send times"""
    from tasks.automation_tasks import analyze_optimal_send_times
    
    if not ObjectId.is_valid(rule_id):
        raise HTTPException(status_code=400, detail="Invalid rule ID")
    
    # Schedule analysis task
    result = analyze_optimal_send_times.delay(rule_id)
    
    return {
        "message": "Send time optimization analysis scheduled",
        "task_id": result.id,
        "rule_id": rule_id
    }


@router.get("/rules/{rule_id}/ab-test-results")
async def get_ab_test_results(rule_id: str, step_id: str):
    """Get A/B test results for a specific step"""
    from database import get_automation_executions_collection
    
    if not ObjectId.is_valid(rule_id):
        raise HTTPException(status_code=400, detail="Invalid rule ID")
    
    executions_collection = get_automation_executions_collection()
    
    # Aggregate by variant
    pipeline = [
        {
            "$match": {
                "automation_rule_id": rule_id,
                "automation_step_id": step_id,
                "ab_variant": {"$exists": True}
            }
        },
        {
            "$group": {
                "_id": "$ab_variant",
                "sent": {"$sum": 1},
                "opened": {"$sum": {"$cond": [{"$ifNull": ["$opened_at", False]}, 1, 0]}},
                "clicked": {"$sum": {"$cond": [{"$ifNull": ["$clicked_at", False]}, 1, 0]}},
                "conversions": {"$sum": {"$cond": [{"$ifNull": ["$goal_achieved", False]}, 1, 0]}}
            }
        }
    ]
    
    results = await executions_collection.aggregate(pipeline).to_list(None)
    
    # Calculate metrics for each variant
    variants = {}
    for result in results:
        variant = result["_id"]
        sent = result["sent"]
        
        variants[variant] = {
            "sent": sent,
            "opened": result["opened"],
            "clicked": result["clicked"],
            "conversions": result["conversions"],
            "open_rate": round((result["opened"] / sent * 100), 2) if sent > 0 else 0,
            "click_rate": round((result["clicked"] / sent * 100), 2) if sent > 0 else 0,
            "conversion_rate": round((result["conversions"] / sent * 100), 2) if sent > 0 else 0
        }
    
    # Determine winner
    winner = None
    if len(variants) == 2:
        variant_a = variants.get("A", {})
        variant_b = variants.get("B", {})
        
        if variant_a.get("open_rate", 0) > variant_b.get("open_rate", 0):
            winner = "A"
        elif variant_b.get("open_rate", 0) > variant_a.get("open_rate", 0):
            winner = "B"
    
    return {
        "rule_id": rule_id,
        "step_id": step_id,
        "variants": variants,
        "winner": winner,
        "statistical_significance": calculate_significance(variants) if len(variants) == 2 else None
    }


# ===========================
# HELPER FUNCTIONS
# ===========================

def convert_delay(value: int, delay_type: str) -> int:
    """Convert delay to hours"""
    if delay_type == "hours":
        return value
    elif delay_type == "days":
        return value * 24
    elif delay_type == "weeks":
        return value * 24 * 7
    return value


def calculate_significance(variants: Dict) -> Dict:
    """Calculate statistical significance between variants"""
    # Simplified calculation - in production use proper statistical tests
    variant_a = variants.get("A", {})
    variant_b = variants.get("B", {})
    
    if not variant_a or not variant_b:
        return {"significant": False, "confidence": 0}
    
    # Calculate z-score for open rates
    p1 = variant_a.get("open_rate", 0) / 100
    p2 = variant_b.get("open_rate", 0) / 100
    n1 = variant_a.get("sent", 0)
    n2 = variant_b.get("sent", 0)
    
    if n1 < 30 or n2 < 30:
        return {"significant": False, "confidence": 0, "note": "Insufficient sample size"}
    
    # Pooled proportion
    p_pool = (p1 * n1 + p2 * n2) / (n1 + n2)
    
    # Standard error
    se = (p_pool * (1 - p_pool) * (1/n1 + 1/n2)) ** 0.5
    
    if se == 0:
        return {"significant": False, "confidence": 0}
    
    # Z-score
    z = abs(p1 - p2) / se
    
    # Confidence level (simplified)
    if z > 2.58:
        confidence = 99
        significant = True
    elif z > 1.96:
        confidence = 95
        significant = True
    elif z > 1.65:
        confidence = 90
        significant = True
    else:
        confidence = 0
        significant = False
    
    return {
        "significant": significant,
        "confidence": confidence,
        "z_score": round(z, 2),
        "difference": round(abs(p1 - p2) * 100, 2)
    }