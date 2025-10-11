# backend/database.py
import os
from motor.motor_asyncio import AsyncIOMotorClient
import logging

logger = logging.getLogger(__name__)

# MongoDB URI using Docker service name
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://admin:password@mongodb:27017/email_marketing?authSource=admin")

# Create AsyncIOMotorClient
client = AsyncIOMotorClient(MONGODB_URI)
database = client.email_marketing

# Collection getter functions
def get_users_collection():
    return database.users

def get_subscribers_collection():
    return database.subscribers

def get_campaigns_collection():
    return database.campaigns

def get_lists_collection():
    return database.lists

def get_stats_collection():
    return database.stats

def get_audit_collection():
    return database.audit

def get_settings_collection():
    return database.settings

def get_usage_collection():
    return database.usage  # Fixed: was db.usage

def get_smtp_configs_collection():
    return database.smtp_configs  # Fixed: was db.smtp_configs

def get_email_logs_collection():
    return database.email_logs

def get_templates_collection():
    return database.templates

# Analytics collections
def get_analytics_collection():
    return database.analytics

def get_email_events_collection():
    return database.email_events

# Domain management collections
def get_domains_collection():
    return database.domains

def get_suppressions_collection():
    return database.suppressions

def get_suppression_logs_collection():
    return database.suppression_logs

# Add to your database.py file
def get_segments_collection():
    return database.segment

def get_ab_tests_collection():
    return database.ab_tests

def get_ab_test_results_collection():
    return database.ab_test_results

# Automation collections
def get_automation_rules_collection():
    return database.automation_rules

def get_automation_steps_collection():
    return database.automation_steps

def get_automation_executions_collection():
    return database.automation_executions

# Jobs collection for tracking background upload jobs
def get_jobs_collection():
    try:
        return database.upload_jobs
    except Exception as e:
        logger.error(f"Failed to get jobs collection: {e}")
        raise

# Database connection test function
async def ping_database():
    try:
        await client.admin.command('ping')
        logger.info("✅ Database connection successful")
        return True
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False

# Legacy compatibility
db = database
