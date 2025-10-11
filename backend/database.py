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
    return database.settings  # ✅ Fixed: was 'setting'

def get_usage_collection():
    return db.usage
  
def get_smtp_configs_collection():
    return db.smtp_configs

def get_email_logs_collection():
    return database.email_logs

def get_templates_collection():
    return database.templates

# ✅ Missing collections that your analytics route needs
def get_analytics_collection():
    return database.analytics

def get_email_events_collection():
    return database.email_events

# ✅ Additional collections for domain management
def get_domains_collection():
    return database.domains

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


