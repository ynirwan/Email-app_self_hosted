# backend/migrations/setup_automation_indexes.py
"""
MongoDB indexes and schema setup for automation system
Run this script to create all necessary indexes for optimal performance
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging

logger = logging.getLogger(__name__)

MONGODB_URI = os.getenv(
    "MONGODB_URI",
    "mongodb://admin:password@mongodb:27017/email_marketing?authSource=admin"
)


async def create_automation_indexes():
    """Create all indexes for automation collections"""
    
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client.email_marketing
    
    logger.info("🔧 Creating automation indexes...")
    
    # ===========================
    # AUTOMATION_RULES INDEXES
    # ===========================
    rules_collection = db.automation_rules
    
    await rules_collection.create_index([("trigger", 1), ("status", 1)])
    logger.info("✅ Created index: automation_rules.trigger + status")
    
    await rules_collection.create_index([("status", 1), ("deleted_at", 1)])
    logger.info("✅ Created index: automation_rules.status + deleted_at")
    
    await rules_collection.create_index([("target_segments", 1)])
    logger.info("✅ Created index: automation_rules.target_segments")
    
    await rules_collection.create_index([("created_at", -1)])
    logger.info("✅ Created index: automation_rules.created_at")
    
    # ===========================
    # AUTOMATION_STEPS INDEXES
    # ===========================
    steps_collection = db.automation_steps
    
    await steps_collection.create_index([("automation_rule_id", 1), ("step_order", 1)])
    logger.info("✅ Created index: automation_steps.automation_rule_id + step_order")
    
    await steps_collection.create_index([("email_template_id", 1)])
    logger.info("✅ Created index: automation_steps.email_template_id")
    
    await steps_collection.create_index([("step_type", 1)])
    logger.info("✅ Created index: automation_steps.step_type")
    
    # ===========================
    # AUTOMATION_EXECUTIONS INDEXES
    # ===========================
    executions_collection = db.automation_executions
    
    # Critical compound index for performance
    await executions_collection.create_index([
        ("automation_rule_id", 1),
        ("subscriber_id", 1),
        ("status", 1)
    ])
    logger.info("✅ Created index: automation_executions.rule + subscriber + status")
    
    await executions_collection.create_index([
        ("automation_rule_id", 1),
        ("executed_at", -1)
    ])
    logger.info("✅ Created index: automation_executions.rule + executed_at")
    
    await executions_collection.create_index([
        ("subscriber_id", 1),
        ("executed_at", -1)
    ])
    logger.info("✅ Created index: automation_executions.subscriber + executed_at")
    
    await executions_collection.create_index([
        ("automation_step_id", 1),
        ("status", 1)
    ])
    logger.info("✅ Created index: automation_executions.step + status")
    
    await executions_collection.create_index([("scheduled_for", 1), ("status", 1)])
    logger.info("✅ Created index: automation_executions.scheduled_for + status")
    
    await executions_collection.create_index([("task_id", 1)])
    logger.info("✅ Created index: automation_executions.task_id")
    
    # For analytics queries
    await executions_collection.create_index([
        ("automation_rule_id", 1),
        ("ab_variant", 1),
        ("opened_at", 1)
    ])
    logger.info("✅ Created index: automation_executions analytics (A/B testing)")
    
    await executions_collection.create_index([("goal_achieved", 1), ("goal_achieved_at", -1)])
    logger.info("✅ Created index: automation_executions.goal_achieved")
    
    # ===========================
    # SUBSCRIBERS INDEXES (if not exist)
    # ===========================
    subscribers_collection = db.subscribers
    
    await subscribers_collection.create_index([("email", 1)], unique=True)
    logger.info("✅ Created index: subscribers.email (unique)")
    
    await subscribers_collection.create_index([("status", 1)])
    logger.info("✅ Created index: subscribers.status")
    
    await subscribers_collection.create_index([("segments", 1)])
    logger.info("✅ Created index: subscribers.segments")
    
    await subscribers_collection.create_index([("list", 1), ("status", 1)])
    logger.info("✅ Created index: subscribers.list + status")
    
    # ===========================
    # EMAIL_EVENTS INDEXES (if not exist)
    # ===========================
    events_collection = db.email_events
    
    await events_collection.create_index([
        ("subscriber_id", 1),
        ("event_type", 1),
        ("timestamp", -1)
    ])
    logger.info("✅ Created index: email_events.subscriber + type + timestamp")
    
    await events_collection.create_index([
        ("automation_rule_id", 1),
        ("event_type", 1)
    ])
    logger.info("✅ Created index: email_events.automation + type")
    
    await events_collection.create_index([("timestamp", -1)])
    logger.info("✅ Created index: email_events.timestamp")
    
    # ===========================
    # TEMPLATES INDEXES
    # ===========================
    templates_collection = db.templates
    
    await templates_collection.create_index([("deleted_at", 1)])
    logger.info("✅ Created index: templates.deleted_at")
    
    await templates_collection.create_index([("created_at", -1)])
    logger.info("✅ Created index: templates.created_at")
    
    await templates_collection.create_index([("name", "text"), ("subject", "text")])
    logger.info("✅ Created index: templates text search")
    
    # ===========================
    # SEGMENTS INDEXES
    # ===========================
    segments_collection = db.segments
    
    await segments_collection.create_index([("is_active", 1), ("deleted_at", 1)])
    logger.info("✅ Created index: segments.is_active + deleted_at")
    
    await segments_collection.create_index([("last_calculated", -1)])
    logger.info("✅ Created index: segments.last_calculated")
    
    logger.info("✨ All automation indexes created successfully!")
    
    client.close()


async def setup_automation_collections():
    """Create collections with validation schemas"""
    
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client.email_marketing
    
    logger.info("🔧 Setting up automation collections...")
    
    # ===========================
    # AUTOMATION_RULES SCHEMA
    # ===========================
    try:
        await db.create_collection("automation_rules", validator={
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["name", "trigger", "status", "created_at"],
                "properties": {
                    "name": {"bsonType": "string"},
                    "description": {"bsonType": ["string", "null"]},
                    "trigger": {"bsonType": "string"},
                    "trigger_conditions": {"bsonType": "object"},
                    "target_segments": {"bsonType": "array"},
                    "status": {
                        "enum": ["draft", "active", "paused", "completed", "deleted"]
                    },
                    "type": {"enum": ["basic", "advanced"]},
                    "primary_goal": {"bsonType": ["object", "null"]},
                    "exit_on_goal_achieved": {"bsonType": "bool"},
                    "exit_on_unsubscribe": {"bsonType": "bool"},
                    "created_at": {"bsonType": "date"},
                    "updated_at": {"bsonType": "date"},
                    "deleted_at": {"bsonType": ["date", "null"]}
                }
            }
        })
        logger.info("✅ Created collection: automation_rules with schema")
    except Exception as e:
        logger.info(f"Collection automation_rules already exists: {e}")
    
    # ===========================
    # AUTOMATION_STEPS SCHEMA
    # ===========================
    try:
        await db.create_collection("automation_steps", validator={
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["automation_rule_id", "step_order", "step_type"],
                "properties": {
                    "automation_rule_id": {"bsonType": "string"},
                    "step_order": {"bsonType": "int"},
                    "step_type": {
                        "enum": ["email", "delay", "condition", "ab_split", 
                                "wait_for_event", "goal_check", "send_webhook", "update_field"]
                    },
                    "email_template_id": {"bsonType": ["string", "null"]},
                    "delay_hours": {"bsonType": "int"},
                    "segment_conditions": {"bsonType": "array"},
                    "conditional_branch": {"bsonType": ["object", "null"]},
                    "ab_test_config": {"bsonType": ["object", "null"]},
                    "wait_for_event": {"bsonType": ["object", "null"]},
                    "goal_tracking": {"bsonType": ["object", "null"]},
                    "smart_send_time": {"bsonType": ["object", "null"]},
                    "webhook_url": {"bsonType": ["string", "null"]},
                    "webhook_payload": {"bsonType": ["object", "null"]},
                    "field_updates": {"bsonType": ["object", "null"]},
                    "created_at": {"bsonType": "date"}
                }
            }
        })
        logger.info("✅ Created collection: automation_steps with schema")
    except Exception as e:
        logger.info(f"Collection automation_steps already exists: {e}")
    
    # ===========================
    # AUTOMATION_EXECUTIONS SCHEMA
    # ===========================
    try:
        await db.create_collection("automation_executions", validator={
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["automation_rule_id", "subscriber_id", "status"],
                "properties": {
                    "automation_rule_id": {"bsonType": "string"},
                    "automation_step_id": {"bsonType": "string"},
                    "subscriber_id": {"bsonType": "string"},
                    "step_order": {"bsonType": "int"},
                    "step_type": {"bsonType": "string"},
                    "status": {
                        "enum": ["scheduled", "sent", "skipped", "failed", 
                                "waiting", "completed", "cancelled", "timeout"]
                    },
                    "scheduled_at": {"bsonType": ["date", "null"]},
                    "scheduled_for": {"bsonType": ["date", "null"]},
                    "executed_at": {"bsonType": ["date", "null"]},
                    "task_id": {"bsonType": ["string", "null"]