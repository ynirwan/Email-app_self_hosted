# backend/database_unified.py
"""
UNIFIED database configuration - replaces database.py, database_sync.py, and database_pool.py
Use this single file for all database operations
"""
import os
import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import MongoClient
from pymongo.database import Database

logger = logging.getLogger(__name__)

# MongoDB URI
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

# ===== ASYNC CLIENT (for FastAPI routes) =====
async_client: Optional[AsyncIOMotorClient] = None
async_database: Optional[AsyncIOMotorDatabase] = None

# ===== SYNC CLIENT (for Celery tasks) =====
sync_client: Optional[MongoClient] = None
sync_database: Optional[Database] = None

def initialize_async_client():
    """Initialize async MongoDB client (call once at startup)"""
    global async_client, async_database
    
    if async_client is None:
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
        logger.info("✅ Async MongoDB client initialized")
    
    return async_client

def initialize_sync_client():
    """Initialize sync MongoDB client (call once at Celery startup)"""
    global sync_client, sync_database
    
    if sync_client is None:
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
        sync_database = sync_client.email_marketing
        logger.info("✅ Sync MongoDB client initialized")
    
    return sync_client

# ===== ASYNC COLLECTION GETTERS (for FastAPI) =====
def get_async_database() -> AsyncIOMotorDatabase:
    """Get async database instance"""
    if async_database is None:
        initialize_async_client()
    return async_database

def get_users_collection():
    return get_async_database().users

def get_subscribers_collection():
    return get_async_database().subscribers

def get_campaigns_collection():
    return get_async_database().campaigns

def get_lists_collection():
    return get_async_database().lists

def get_stats_collection():
    return get_async_database().stats

def get_audit_collection():
    return get_async_database().audit

def get_settings_collection():
    return get_async_database().settings

def get_usage_collection():
    return get_async_database().usage

def get_smtp_configs_collection():
    return get_async_database().smtp_configs

def get_email_logs_collection():
    return get_async_database().email_logs

def get_templates_collection():
    return get_async_database().templates

def get_analytics_collection():
    return get_async_database().analytics

def get_email_events_collection():
    return get_async_database().email_events

def get_domains_collection():
    return get_async_database().domains

def get_suppressions_collection():
    return get_async_database().suppressions

def get_suppression_logs_collection():
    return get_async_database().suppression_logs

def get_segments_collection():
    return get_async_database().segments

def get_ab_tests_collection():
    return get_async_database().ab_tests

def get_ab_test_results_collection():
    return get_async_database().ab_test_results

def get_automation_rules_collection():
    return get_async_database().automation_rules

def get_automation_steps_collection():
    return get_async_database().automation_steps

def get_automation_executions_collection():
    return get_async_database().automation_executions

def get_jobs_collection():
    return get_async_database().upload_jobs

# ===== SYNC COLLECTION GETTERS (for Celery) =====
def get_sync_database() -> Database:
    """Get sync database instance"""
    if sync_database is None:
        initialize_sync_client()
    return sync_database

def get_sync_users_collection():
    return get_sync_database().users

def get_sync_subscribers_collection():
    return get_sync_database().subscribers

def get_sync_campaigns_collection():
    return get_sync_database().campaigns

def get_sync_lists_collection():
    return get_sync_database().lists

def get_sync_stats_collection():
    return get_sync_database().stats

def get_sync_audit_collection():
    return get_sync_database().audit

def get_sync_settings_collection():
    return get_sync_database().settings

def get_sync_usage_collection():
    return get_sync_database().usage

def get_sync_smtp_configs_collection():
    return get_sync_database().smtp_configs

def get_sync_email_logs_collection():
    return get_sync_database().email_logs

def get_sync_templates_collection():
    return get_sync_database().templates

def get_sync_analytics_collection():
    return get_sync_database().analytics

def get_sync_email_events_collection():
    return get_sync_database().email_events

def get_sync_domains_collection():
    return get_sync_database().domains

def get_sync_suppressions_collection():
    return get_sync_database().suppressions

def get_sync_suppression_logs_collection():
    return get_sync_database().suppression_logs

def get_sync_segments_collection():
    return get_sync_database().segments

def get_sync_ab_tests_collection():
    return get_sync_database().ab_tests

def get_sync_ab_test_results_collection():
    return get_sync_database().ab_test_results

def get_sync_automation_rules_collection():
    return get_sync_database().automation_rules

def get_sync_automation_steps_collection():
    return get_sync_database().automation_steps

def get_sync_automation_executions_collection():
    return get_sync_database().automation_executions

def get_sync_jobs_collection():
    return get_sync_database().upload_jobs

def get_sync_dlq_collection():
    return get_sync_database().dead_letter_queue

# ===== HEALTH CHECK =====
async def ping_database() -> bool:
    """Test async database connectivity"""
    try:
        await async_client.admin.command('ping')
        logger.info("✅ Async database connection successful")
        return True
    except Exception as e:
        logger.error(f"❌ Async database connection failed: {e}")
        return False

def ping_sync_database() -> tuple[bool, dict]:
    """Test sync database connectivity"""
    try:
        result = sync_client.admin.command('ping')
        server_info = sync_client.server_info()
        
        health_info = {
            "connection_status": "healthy",
            "server_version": server_info.get("version", "unknown"),
            "database_name": sync_database.name,
            "ping_response": result
        }
        
        logger.info("✅ Sync database connection successful")
        return True, health_info
    except Exception as e:
        error_info = {
            "connection_status": "failed",
            "error": str(e)
        }
        logger.error("❌ Sync database connection failed")
        return False, error_info

# ===== GRACEFUL SHUTDOWN =====
def close_async_client():
    """Close async client connections"""
    global async_client, async_database
    if async_client:
        async_client.close()
        async_client = None
        async_database = None
        logger.info("✅ Async MongoDB client closed")

def close_sync_client():
    """Close sync client connections"""
    global sync_client, sync_database
    if sync_client:
        sync_client.close()
        sync_client = None
        sync_database = None
        logger.info("✅ Sync MongoDB client closed")

def close_all_connections():
    """Close all database connections"""
    close_async_client()
    close_sync_client()

# ===== LEGACY COMPATIBILITY =====
# For backward compatibility with existing code
database = get_async_database
db = get_async_database
client = lambda: async_client
sync_db = get_sync_database

# Initialize async client on import (for FastAPI)
initialize_async_client()