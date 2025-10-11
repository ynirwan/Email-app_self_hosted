# backend/database_pool.py - COMPLETE DATABASE CONNECTION POOLING
"""
Production-ready database connection pooling
Handles both async and sync connections with health monitoring
"""
import os
import logging
import time
import threading
from typing import Optional, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure
from core.campaign_config import settings

logger = logging.getLogger(__name__)

class DatabasePool:
    """Singleton database connection pool manager"""
    
    _instance = None
    _lock = threading.Lock()
    _async_client: Optional[AsyncIOMotorClient] = None
    _sync_client: Optional[MongoClient] = None
    _connection_health = {"async": True, "sync": True}
    _last_health_check = 0
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def get_mongodb_uri(cls) -> str:
        """Get MongoDB URI from environment"""
        return os.getenv(
            "MONGODB_URI", 
            "mongodb://admin:password@mongodb:27017/email_marketing?authSource=admin"
        )
    
    @classmethod
    def get_async_client(cls) -> AsyncIOMotorClient:
        """Get async MongoDB client with connection pooling"""
        if cls._async_client is None:
            with cls._lock:
                if cls._async_client is None:
                    try:
                        cls._async_client = AsyncIOMotorClient(
                            cls.get_mongodb_uri(),
                            # Connection pool settings
                            maxPoolSize=settings.DB_MAX_POOL_SIZE,
                            minPoolSize=settings.DB_MIN_POOL_SIZE,
                            maxIdleTimeMS=settings.DB_MAX_IDLE_TIME_SECONDS * 1000,
                            
                            # Timeout settings
                            serverSelectionTimeoutMS=settings.DB_SERVER_SELECTION_TIMEOUT_SECONDS * 1000,
                            connectTimeoutMS=settings.DB_CONNECTION_TIMEOUT_SECONDS * 1000,
                            socketTimeoutMS=settings.DB_SOCKET_TIMEOUT_SECONDS * 1000,
                            
                            # Health monitoring
                            heartbeatFrequencyMS=10000,  # 10 seconds
                            
                            # Connection behavior
                            retryWrites=True,
                            retryReads=True,
                            
                            # Application name for monitoring
                            appName="email_marketing_async",
                        )
                        
                        logger.info("Async MongoDB client initialized with connection pooling")
                        
                    except Exception as e:
                        logger.error(f"Failed to initialize async MongoDB client: {e}")
                        raise
        
        return cls._async_client
    
    @classmethod
    def get_sync_client(cls) -> MongoClient:
        """Get sync MongoDB client with connection pooling"""
        if cls._sync_client is None:
            with cls._lock:
                if cls._sync_client is None:
                    try:
                        cls._sync_client = MongoClient(
                            cls.get_mongodb_uri(),
                            # Connection pool settings
                            maxPoolSize=settings.DB_MAX_POOL_SIZE,
                            minPoolSize=settings.DB_MIN_POOL_SIZE,
                            maxIdleTimeMS=settings.DB_MAX_IDLE_TIME_SECONDS * 1000,
                            
                            # Timeout settings
                            serverSelectionTimeoutMS=settings.DB_SERVER_SELECTION_TIMEOUT_SECONDS * 1000,
                            connectTimeoutMS=settings.DB_CONNECTION_TIMEOUT_SECONDS * 1000,
                            socketTimeoutMS=settings.DB_SOCKET_TIMEOUT_SECONDS * 1000,
                            
                            # Connection behavior
                            retryWrites=True,
                            retryReads=True,
                            
                            # Application name for monitoring
                            appname="email_marketing_sync",
                        )
                        
                        logger.info("Sync MongoDB client initialized with connection pooling")
                        
                    except Exception as e:
                        logger.error(f"Failed to initialize sync MongoDB client: {e}")
                        raise
        
        return cls._sync_client
    
    @classmethod
    def check_connection_health(cls) -> Dict[str, Any]:
        """Check health of database connections"""
        current_time = time.time()
        
        # Only check health every 30 seconds to avoid overhead
        if current_time - cls._last_health_check < settings.HEALTH_CHECK_INTERVAL_SECONDS:
            return {
                "async_healthy": cls._connection_health["async"],
                "sync_healthy": cls._connection_health["sync"],
                "cached": True
            }
        
        health_status = {"cached": False}
        
        # Check async client
        try:
            if cls._async_client:
                import asyncio
                
                async def ping_async():
                    return await cls._async_client.admin.command("ping")
                
                # Run async ping
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(ping_async())
                loop.close()
                
                cls._connection_health["async"] = bool(result.get("ok"))
            else:
                cls._connection_health["async"] = True  # Not initialized yet
                
        except Exception as e:
            logger.error(f"Async DB health check failed: {e}")
            cls._connection_health["async"] = False
        
        # Check sync client
        try:
            if cls._sync_client:
                result = cls._sync_client.admin.command("ping")
                cls._connection_health["sync"] = bool(result.get("ok"))
            else:
                cls._connection_health["sync"] = True  # Not initialized yet
                
        except Exception as e:
            logger.error(f"Sync DB health check failed: {e}")
            cls._connection_health["sync"] = False
        
        health_status.update({
            "async_healthy": cls._connection_health["async"],
            "sync_healthy": cls._connection_health["sync"]
        })
        
        cls._last_health_check = current_time
        
        return health_status
    
    @classmethod
    def get_connection_stats(cls) -> Dict[str, Any]:
        """Get connection pool statistics"""
        stats = {
            "timestamp": time.time(),
            "async_client": None,
            "sync_client": None
        }
        
        # Get async client stats
        if cls._async_client:
            try:
                # Motor doesn't expose connection pool stats directly
                # but we can get some basic info
                stats["async_client"] = {
                    "initialized": True,
                    "max_pool_size": settings.DB_MAX_POOL_SIZE,
                    "min_pool_size": settings.DB_MIN_POOL_SIZE
                }
            except Exception as e:
                stats["async_client"] = {"error": str(e)}
        
        # Get sync client stats
        if cls._sync_client:
            try:
                # PyMongo provides connection pool info
                pool_stats = {}
                for server in cls._sync_client.topology_description.server_descriptions():
                    pool_stats[str(server)] = {
                        "pool_generation": getattr(server, 'pool_generation', 'unknown'),
                        "server_type": str(server.server_type)
                    }
                
                stats["sync_client"] = {
                    "initialized": True,
                    "max_pool_size": settings.DB_MAX_POOL_SIZE,
                    "min_pool_size": settings.DB_MIN_POOL_SIZE,
                    "servers": pool_stats
                }
            except Exception as e:
                stats["sync_client"] = {"error": str(e)}
        
        return stats
    
    @classmethod
    def close_connections(cls):
        """Close all database connections gracefully"""
        try:
            if cls._async_client:
                cls._async_client.close()
                cls._async_client = None
                logger.info("Async MongoDB client closed")
            
            if cls._sync_client:
                cls._sync_client.close()
                cls._sync_client = None
                logger.info("Sync MongoDB client closed")
                
        except Exception as e:
            logger.error(f"Error closing database connections: {e}")
    
    @classmethod
    def reset_connections(cls):
        """Reset connections (useful for recovery scenarios)"""
        logger.info("Resetting database connections")
        cls.close_connections()
        cls._connection_health = {"async": True, "sync": True}
        cls._last_health_check = 0

# Collection getters using the pool
def get_async_database():
    """Get async database instance"""
    client = DatabasePool.get_async_client()
    return client.email_marketing

def get_sync_database():
    """Get sync database instance"""
    client = DatabasePool.get_sync_client()
    return client.email_marketing

# Collection shortcuts for async operations
def get_campaigns_collection():
    """Get async campaigns collection"""
    return get_async_database().campaigns

def get_subscribers_collection():
    """Get async subscribers collection"""
    return get_async_database().subscribers

def get_templates_collection():
    """Get async templates collection"""
    return get_async_database().templates

def get_email_logs_collection():
    """Get async email_logs collection"""
    return get_async_database().email_logs

def get_settings_collection():
    """Get async settings collection"""
    return get_async_database().settings

def get_analytics_collection():
    """Get async analytics collection"""
    return get_async_database().analytics

# Collection shortcuts for sync operations (Celery tasks)
def get_sync_campaigns_collection():
    """Get sync campaigns collection"""
    return get_sync_database().campaigns

def get_sync_subscribers_collection():
    """Get sync subscribers collection"""
    return get_sync_database().subscribers

def get_sync_templates_collection():
    """Get sync templates collection"""
    return get_sync_database().templates

def get_sync_email_logs_collection():
    """Get sync email_logs collection"""
    return get_sync_database().email_logs

def get_sync_settings_collection():
    """Get sync settings collection"""
    return get_sync_database().settings

def get_sync_analytics_collection():
    """Get sync analytics collection"""
    return get_sync_database().analytics

def get_sync_dlq_collection():
    """Get sync dead letter queue collection"""
    return get_sync_database().dead_letter_queue

def get_sync_audit_collection():
    """Get sync audit collection"""
    return get_sync_database().audit_logs

# Initialize database pool on module import
database_pool = DatabasePool()

