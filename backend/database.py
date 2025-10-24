
import os
import logging
from typing import Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import time

logger = logging.getLogger(__name__)

# ===== MONGODB CONFIGURATION =====
MONGODB_URI = os.getenv(
    "MONGODB_URI", 
    "mongodb://admin:password@mongodb:27017/email_marketing?authSource=admin"
)

# ===== CONNECTION POOL SETTINGS =====
MAX_POOL_SIZE = int(os.getenv("DB_MAX_POOL_SIZE", "50"))
MIN_POOL_SIZE = int(os.getenv("DB_MIN_POOL_SIZE", "5"))
MAX_IDLE_TIME_MS = int(os.getenv("DB_MAX_IDLE_TIME_MS", "45000"))
CONNECT_TIMEOUT_MS = int(os.getenv("DB_CONNECT_TIMEOUT_MS", "10000"))
SERVER_SELECTION_TIMEOUT_MS = int(os.getenv("DB_SERVER_SELECTION_TIMEOUT_MS", "10000"))

# ===== CLIENT INSTANCES =====
async_client: Optional[AsyncIOMotorClient] = None
async_database: Optional[AsyncIOMotorDatabase] = None
sync_client: Optional[MongoClient] = None
sync_database: Optional[Database] = None

# ===== INITIALIZATION FLAGS =====
_async_initialized = False
_sync_initialized = False
_indexes_created = False


# ============================================
# ASYNC CLIENT INITIALIZATION
# ============================================

def initialize_async_client() -> AsyncIOMotorClient:
    """Initialize async MongoDB client with error handling (call once at startup)"""
    global async_client, async_database, _async_initialized
    
    if async_client is not None and _async_initialized:
        return async_client
    
    try:
        async_client = AsyncIOMotorClient(
            MONGODB_URI,
            maxPoolSize=MAX_POOL_SIZE,
            minPoolSize=MIN_POOL_SIZE,
            maxIdleTimeMS=MAX_IDLE_TIME_MS,
            connectTimeoutMS=CONNECT_TIMEOUT_MS,
            serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS,
            retryWrites=True,
            retryReads=True,
            appName="email_marketing_async"
        )
        async_database = async_client.email_marketing
        _async_initialized = True
        logger.info("✅ Async MongoDB client initialized")
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize async MongoDB client: {e}")
        raise
    
    return async_client


def initialize_sync_client() -> MongoClient:
    """Initialize sync MongoDB client with error handling (call once at Celery startup)"""
    global sync_client, sync_database, _sync_initialized
    
    if sync_client is not None and _sync_initialized:
        return sync_client
    
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            sync_client = MongoClient(
                MONGODB_URI,
                maxPoolSize=MAX_POOL_SIZE,
                minPoolSize=MIN_POOL_SIZE,
                maxIdleTimeMS=MAX_IDLE_TIME_MS,
                connectTimeoutMS=CONNECT_TIMEOUT_MS,
                serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS,
                retryWrites=True,
                appname="email_marketing_sync"
            )
            
            # Test connection
            sync_client.admin.command('ping')
            sync_database = sync_client.email_marketing
            _sync_initialized = True
            logger.info("✅ Sync MongoDB client initialized")
            return sync_client
            
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.warning(f"⚠️ Sync MongoDB connection attempt {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error("❌ Failed to initialize sync MongoDB client after all retries")
                raise
        except Exception as e:
            logger.error(f"❌ Unexpected error initializing sync MongoDB client: {e}")
            raise
    
    return sync_client


# ============================================
# ASYNC DATABASE & COLLECTION GETTERS
# ============================================

def get_async_database() -> AsyncIOMotorDatabase:
    """Get async database instance"""
    if async_database is None:
        initialize_async_client()
    return async_database


# Core Collections
def get_users_collection():
    """Users/authentication collection"""
    return get_async_database().users

def get_subscribers_collection():
    """Subscribers/contacts collection"""
    return get_async_database().subscribers

def get_campaigns_collection():
    """Email campaigns collection"""
    return get_async_database().campaigns

def get_lists_collection():
    """Subscriber lists collection"""
    return get_async_database().lists

def get_templates_collection():
    """Email templates collection"""
    return get_async_database().templates


# Logs & Analytics Collections
def get_email_logs_collection():
    """Email sending logs collection"""
    return get_async_database().email_logs

def get_email_events_collection():
    """Email events (opens, clicks, bounces) collection"""
    return get_async_database().email_events

def get_analytics_collection():
    """Campaign analytics collection"""
    return get_async_database().analytics

def get_audit_collection():
    """Audit trail collection"""
    return get_async_database().audit


# Settings & Configuration Collections
def get_settings_collection():
    """Application settings collection"""
    return get_async_database().settings

def get_smtp_configs_collection():
    """SMTP configurations collection"""
    return get_async_database().smtp_configs

def get_domains_collection():
    """Domain verification collection"""
    return get_async_database().domains


# Suppression & Compliance Collections
def get_suppressions_collection():
    """Email suppressions collection"""
    return get_async_database().suppressions

def get_suppression_logs_collection():
    """Suppression activity logs collection"""
    return get_async_database().suppression_logs


# Segmentation & Testing Collections
def get_segments_collection():
    """Subscriber segments collection"""
    return get_async_database().segments

def get_ab_tests_collection():
    """A/B test configurations collection"""
    return get_async_database().ab_tests

def get_ab_test_results_collection():
    """A/B test results collection"""
    return get_async_database().ab_test_results


# Automation Collections
def get_automation_rules_collection():
    """Automation rules collection"""
    return get_async_database().automation_rules

def get_automation_steps_collection():
    """Automation workflow steps collection"""
    return get_async_database().automation_steps

def get_automation_executions_collection():
    """Automation execution logs collection"""
    return get_async_database().automation_executions


# System Collections
def get_jobs_collection():
    """Background jobs collection"""
    return get_async_database().upload_jobs

def get_stats_collection():
    """System statistics collection"""
    return get_async_database().stats

def get_usage_collection():
    """Usage tracking collection"""
    return get_async_database().usage


# Production Feature Collections
def get_dlq_collection():
    """Dead Letter Queue collection"""
    return get_async_database().dead_letter_queue

def get_metrics_collection():
    """System metrics collection"""
    return get_async_database().system_metrics

def get_health_reports_collection():
    """Health monitoring reports collection"""
    return get_async_database().health_reports

def get_campaign_flags_collection():
    """Campaign control flags collection"""
    return get_async_database().campaign_flags

def get_rate_limits_collection():
    """Rate limiting data collection"""
    return get_async_database().rate_limits


# ============================================
# SYNC DATABASE & COLLECTION GETTERS
# ============================================

def get_sync_database() -> Database:
    """Get sync database instance"""
    if sync_database is None:
        initialize_sync_client()
    return sync_database


# Core Collections (Sync)
def get_sync_users_collection():
    """Sync users collection"""
    return get_sync_database().users

def get_sync_subscribers_collection():
    """Sync subscribers collection"""
    return get_sync_database().subscribers

def get_sync_campaigns_collection():
    """Sync campaigns collection"""
    return get_sync_database().campaigns

def get_sync_lists_collection():
    """Sync lists collection"""
    return get_sync_database().lists

def get_sync_templates_collection():
    """Sync templates collection"""
    return get_sync_database().templates


# Logs & Analytics Collections (Sync)
def get_sync_email_logs_collection():
    """Sync email logs collection"""
    return get_sync_database().email_logs

def get_sync_email_events_collection():
    """Sync email events collection"""
    return get_sync_database().email_events

def get_sync_analytics_collection():
    """Sync analytics collection"""
    return get_sync_database().analytics

def get_sync_audit_collection():
    """Sync audit collection"""
    return get_sync_database().audit


# Settings & Configuration Collections (Sync)
def get_sync_settings_collection():
    """Sync settings collection"""
    return get_sync_database().settings

def get_sync_smtp_configs_collection():
    """Sync SMTP configs collection"""
    return get_sync_database().smtp_configs

def get_sync_domains_collection():
    """Sync domains collection"""
    return get_sync_database().domains


# Suppression & Compliance Collections (Sync)
def get_sync_suppressions_collection():
    """Sync suppressions collection"""
    return get_sync_database().suppressions

def get_sync_suppression_logs_collection():
    """Sync suppression logs collection"""
    return get_sync_database().suppression_logs


# Segmentation & Testing Collections (Sync)
def get_sync_segments_collection():
    """Sync segments collection"""
    return get_sync_database().segments

def get_sync_ab_tests_collection():
    """Sync A/B tests collection"""
    return get_sync_database().ab_tests

def get_sync_ab_test_results_collection():
    """Sync A/B test results collection"""
    return get_sync_database().ab_test_results


# Automation Collections (Sync)
def get_sync_automation_rules_collection():
    """Sync automation rules collection"""
    return get_sync_database().automation_rules

def get_sync_automation_steps_collection():
    """Sync automation steps collection"""
    return get_sync_database().automation_steps

def get_sync_automation_executions_collection():
    """Sync automation executions collection"""
    return get_sync_database().automation_executions


# System Collections (Sync)
def get_sync_jobs_collection():
    """Sync jobs collection"""
    return get_sync_database().upload_jobs

def get_sync_stats_collection():
    """Sync stats collection"""
    return get_sync_database().stats

def get_sync_usage_collection():
    """Sync usage collection"""
    return get_sync_database().usage


# Production Feature Collections (Sync)
def get_sync_dlq_collection():
    """Sync Dead Letter Queue collection"""
    return get_sync_database().dead_letter_queue

def get_sync_metrics_collection():
    """Sync system metrics collection"""
    return get_sync_database().system_metrics

def get_sync_health_reports_collection():
    """Sync health reports collection"""
    return get_sync_database().health_reports

def get_sync_campaign_flags_collection():
    """Sync campaign flags collection"""
    return get_sync_database().campaign_flags

def get_sync_rate_limits_collection():
    """Sync rate limits collection"""
    return get_sync_database().rate_limits


# ============================================
# DATABASE UTILITIES
# ============================================

def get_collection_stats(collection_name: str) -> Dict[str, Any]:
    """Get statistics for a collection"""
    try:
        db = get_sync_database()
        stats = db.command("collStats", collection_name)
        return {
            "count": stats.get("count", 0),
            "size": stats.get("size", 0),
            "avgObjSize": stats.get("avgObjSize", 0),
            "storageSize": stats.get("storageSize", 0),
            "indexes": stats.get("nindexes", 0)
        }
    except Exception as e:
        logger.error(f"Failed to get collection stats for {collection_name}: {e}")
        return {
            "count": 0,
            "size": 0,
            "avgObjSize": 0,
            "storageSize": 0,
            "indexes": 0,
            "error": str(e)
        }


def get_database_info() -> Dict[str, Any]:
    """Get database metadata and statistics"""
    try:
        db = get_sync_database()
        
        # Server info
        server_info = sync_client.server_info()
        
        # Database stats
        db_stats = db.command("dbStats")
        
        return {
            "database_name": db.name,
            "server_version": server_info.get("version", "unknown"),
            "collections": db_stats.get("collections", 0),
            "objects": db_stats.get("objects", 0),
            "data_size": db_stats.get("dataSize", 0),
            "storage_size": db_stats.get("storageSize", 0),
            "indexes": db_stats.get("indexes", 0),
            "index_size": db_stats.get("indexSize", 0)
        }
    except Exception as e:
        logger.error(f"Failed to get database info: {e}")
        return {"error": str(e)}


async def ensure_indexes():
    """Create database indexes for optimal performance"""
    global _indexes_created
    
    if _indexes_created:
        return
    
    try:
        logger.info("🔧 Creating database indexes...")
        
        # Subscribers indexes
        subscribers = get_subscribers_collection()
        await subscribers.create_index([("email", ASCENDING), ("list", ASCENDING)], unique=True)
        await subscribers.create_index([("list", ASCENDING)])
        await subscribers.create_index([("status", ASCENDING)])
        await subscribers.create_index([("created_at", DESCENDING)])
        
        # Campaigns indexes
        campaigns = get_campaigns_collection()
        await campaigns.create_index([("status", ASCENDING)])
        await campaigns.create_index([("created_at", DESCENDING)])
        await campaigns.create_index([("scheduled_at", ASCENDING)])
        
        # Email logs indexes
        email_logs = get_email_logs_collection()
        await email_logs.create_index([("campaign_id", ASCENDING)])
        await email_logs.create_index([("email", ASCENDING)])
        await email_logs.create_index([("latest_status", ASCENDING)])
        await email_logs.create_index([("created_at", DESCENDING)])
        
        # Email events indexes
        email_events = get_email_events_collection()
        await email_events.create_index([("campaign_id", ASCENDING)])
        await email_events.create_index([("subscriber_id", ASCENDING)])
        await email_events.create_index([("event_type", ASCENDING)])
        await email_events.create_index([("timestamp", DESCENDING)])
        
        # Analytics indexes
        analytics = get_analytics_collection()
        await analytics.create_index([("campaign_id", ASCENDING)], unique=True)
        
        # Suppressions indexes
        suppressions = get_suppressions_collection()
        await suppressions.create_index([("email", ASCENDING)], unique=True)
        await suppressions.create_index([("is_active", ASCENDING)])
        await suppressions.create_index([("scope", ASCENDING)])
        
        # Audit indexes
        audit = get_audit_collection()
        await audit.create_index([("timestamp", DESCENDING)])
        await audit.create_index([("entity_type", ASCENDING)])
        
        # Automation indexes
        automation_rules = get_automation_rules_collection()
        await automation_rules.create_index([("is_active", ASCENDING)])
        await automation_rules.create_index([("trigger_type", ASCENDING)])
        
        automation_executions = get_automation_executions_collection()
        await automation_executions.create_index([("automation_rule_id", ASCENDING)])
        await automation_executions.create_index([("subscriber_id", ASCENDING)])
        await automation_executions.create_index([("executed_at", DESCENDING)])
        
        # Jobs indexes
        jobs = get_jobs_collection()
        await jobs.create_index([("job_id", ASCENDING)], unique=True)
        await jobs.create_index([("status", ASCENDING)])
        
        # DLQ indexes
        dlq = get_dlq_collection()
        await dlq.create_index([("campaign_id", ASCENDING)])
        await dlq.create_index([("retry_count", ASCENDING)])
        await dlq.create_index([("last_attempt_at", DESCENDING)])
        
        _indexes_created = True
        logger.info("✅ Database indexes created successfully")
        
    except Exception as e:
        logger.error(f"❌ Failed to create indexes: {e}")
        # Don't raise - indexes are optimization, not critical


def ensure_indexes_sync():
    """Create database indexes synchronously (for Celery)"""
    global _indexes_created
    
    if _indexes_created:
        return
    
    try:
        logger.info("🔧 Creating database indexes (sync)...")
        
        db = get_sync_database()
        
        # Subscribers indexes
        db.subscribers.create_index([("email", ASCENDING), ("list", ASCENDING)], unique=True)
        db.subscribers.create_index([("list", ASCENDING)])
        db.subscribers.create_index([("status", ASCENDING)])
        
        # Campaigns indexes
        db.campaigns.create_index([("status", ASCENDING)])
        db.campaigns.create_index([("created_at", DESCENDING)])
        
        # Email logs indexes
        db.email_logs.create_index([("campaign_id", ASCENDING)])
        db.email_logs.create_index([("latest_status", ASCENDING)])
        
        # Suppressions indexes
        db.suppressions.create_index([("email", ASCENDING)], unique=True)
        db.suppressions.create_index([("is_active", ASCENDING)])
        
        _indexes_created = True
        logger.info("✅ Database indexes created successfully (sync)")
        
    except Exception as e:
        logger.error(f"❌ Failed to create indexes (sync): {e}")


# ============================================
# HEALTH CHECK FUNCTIONS
# ============================================

async def ping_database() -> bool:
    """Test async database connectivity"""
    try:
        if async_client is None:
            initialize_async_client()
        await async_client.admin.command('ping')
        logger.info("✅ Async database connection successful")
        return True
    except Exception as e:
        logger.error(f"❌ Async database connection failed: {e}")
        return False


def ping_sync_database() -> tuple[bool, Dict[str, Any]]:
    """Test sync database connectivity with detailed info"""
    try:
        if sync_client is None:
            initialize_sync_client()
            
        result = sync_client.admin.command('ping')
        server_info = sync_client.server_info()
        
        health_info = {
            "connection_status": "healthy",
            "server_version": server_info.get("version", "unknown"),
            "database_name": sync_database.name,
            "ping_response": result,
            "ping_time_ms": result.get("ok", 0)
        }
        
        logger.info("✅ Sync database connection successful")
        return True, health_info
        
    except Exception as e:
        error_info = {
            "connection_status": "failed",
            "error": str(e),
            "error_type": type(e).__name__
        }
        logger.error(f"❌ Sync database connection failed: {e}")
        return False, error_info


# ============================================
# GRACEFUL SHUTDOWN
# ============================================

def close_async_client():
    """Close async client connections"""
    global async_client, async_database, _async_initialized
    if async_client:
        async_client.close()
        async_client = None
        async_database = None
        _async_initialized = False
        logger.info("✅ Async MongoDB client closed")


def close_sync_client():
    """Close sync client connections"""
    global sync_client, sync_database, _sync_initialized
    if sync_client:
        sync_client.close()
        sync_client = None
        sync_database = None
        _sync_initialized = False
        logger.info("✅ Sync MongoDB client closed")


def close_all_connections():
    """Close all database connections"""
    close_async_client()
    close_sync_client()
    logger.info("✅ All database connections closed")


# ============================================
# LEGACY COMPATIBILITY
# ============================================

# Backward compatibility with existing code
database = get_async_database
db = get_async_database
client = lambda: async_client
sync_db = get_sync_database
get_collection = lambda name: get_async_database()[name]
get_sync_collection = lambda name: get_sync_database()[name]


# ============================================
# AUTO-INITIALIZATION
# ============================================

# Initialize async client on import (for FastAPI)
try:
    initialize_async_client()
except Exception as e:
    logger.warning(f"⚠️ Could not initialize async client on import: {e}")


# ============================================
# EXPORTS
# ============================================

__all__ = [
    # Initialization
    'initialize_async_client',
    'initialize_sync_client',
    
    # Database access
    'get_async_database',
    'get_sync_database',
    
    # Async collections
    'get_users_collection',
    'get_subscribers_collection',
    'get_campaigns_collection',
    'get_lists_collection',
    'get_templates_collection',
    'get_email_logs_collection',
    'get_email_events_collection',
    'get_analytics_collection',
    'get_audit_collection',
    'get_settings_collection',
    'get_smtp_configs_collection',
    'get_domains_collection',
    'get_suppressions_collection',
    'get_suppression_logs_collection',
    'get_segments_collection',
    'get_ab_tests_collection',
    'get_ab_test_results_collection',
    'get_automation_rules_collection',
    'get_automation_steps_collection',
    'get_automation_executions_collection',
    'get_jobs_collection',
    'get_stats_collection',
    'get_usage_collection',
    'get_dlq_collection',
    'get_metrics_collection',
    'get_health_reports_collection',
    'get_campaign_flags_collection',
    'get_rate_limits_collection',
    
    # Sync collections
    'get_sync_users_collection',
    'get_sync_subscribers_collection',
    'get_sync_campaigns_collection',
    'get_sync_lists_collection',
    'get_sync_templates_collection',
    'get_sync_email_logs_collection',
    'get_sync_email_events_collection',
    'get_sync_analytics_collection',
    'get_sync_audit_collection',
    'get_sync_settings_collection',
    'get_sync_smtp_configs_collection',
    'get_sync_domains_collection',
    'get_sync_suppressions_collection',
    'get_sync_suppression_logs_collection',
    'get_sync_segments_collection',
    'get_sync_ab_tests_collection',
    'get_sync_ab_test_results_collection',
    'get_sync_automation_rules_collection',
    'get_sync_automation_steps_collection',
    'get_sync_automation_executions_collection',
    'get_sync_jobs_collection',
    'get_sync_stats_collection',
    'get_sync_usage_collection',
    'get_sync_dlq_collection',
    'get_sync_metrics_collection',
    'get_sync_health_reports_collection',
    'get_sync_campaign_flags_collection',
    'get_sync_rate_limits_collection',
    
    # Utilities
    'get_collection_stats',
    'get_database_info',
    'ensure_indexes',
    'ensure_indexes_sync',
    'ping_database',
    'ping_sync_database',
    
    # Cleanup
    'close_async_client',
    'close_sync_client',
    'close_all_connections',
    
    # Legacy
    'database',
    'db',
    'client',
    'sync_db',
    'get_collection',
    'get_sync_collection',
]
