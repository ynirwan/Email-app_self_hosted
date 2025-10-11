import os
from pymongo import MongoClient
import logging

logger = logging.getLogger(__name__)

# MongoDB URI - using the same as your async version
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://admin:password@mongodb:27017/email_marketing?authSource=admin")

# ✅ FIXED: Basic MongoClient configuration (compatible with all PyMongo versions)
sync_client = MongoClient(
    MONGODB_URI,
    # Basic configuration that works across PyMongo versions
    maxPoolSize=50,           # Maximum connections per process
    minPoolSize=5,            # Minimum connections to maintain
    maxIdleTimeMS=45000,      # Close connections after 45s idle
    waitQueueTimeoutMS=5000,  # Wait max 5s for connection
    serverSelectionTimeoutMS=10000,  # Server selection timeout
    connectTimeoutMS=10000,   # Connection timeout
    socketTimeoutMS=30000,    # Socket timeout for operations
    retryWrites=True,         # Enable retryable writes
    # ✅ REMOVED: These options cause compatibility issues
    # readConcern=ReadConcern("majority"),  # Not supported in older versions
    # writeConcern=WriteConcern(w="majority", wtimeout=10000)  # Not supported in constructor
)

sync_database = sync_client.email_marketing

# ✅ ENHANCED: Collection getter functions with retry and error handling
def get_collection_with_retry(collection_name: str, max_retries: int = 3):
    """Get collection with automatic retry on connection failures"""
    for attempt in range(max_retries):
        try:
            collection = getattr(sync_database, collection_name)
            # Test connection with a simple operation
            sync_client.admin.command('ping')
            return collection
        except Exception as e:
            logger.warning(f"Database connection attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                logger.error(f"Failed to connect to database after {max_retries} attempts")
                raise
    return None

# ✅ FIXED: All collection functions using the compatible approach
def get_sync_users_collection():
    return get_collection_with_retry("users")

def get_sync_subscribers_collection():
    return get_collection_with_retry("subscribers")

def get_sync_campaigns_collection():
    return get_collection_with_retry("campaigns")

def get_sync_lists_collection():
    return get_collection_with_retry("lists")

def get_sync_stats_collection():
    return get_collection_with_retry("stats")

def get_sync_audit_collection():
    return get_collection_with_retry("audit")

def get_sync_settings_collection():
    return get_collection_with_retry("settings")

def get_sync_usage_collection():
    return get_collection_with_retry("usage")

def get_sync_smtp_configs_collection():
    return get_collection_with_retry("smtp_configs")

def get_sync_email_logs_collection():
    return get_collection_with_retry("email_logs")

def get_sync_templates_collection():
    return get_collection_with_retry("templates")

def get_sync_analytics_collection():
    return get_collection_with_retry("analytics")

def get_sync_email_events_collection():
    return get_collection_with_retry("email_events")

def get_sync_domains_collection():
    return get_collection_with_retry("domains")

def get_sync_jobs_collection():
    return get_collection_with_retry("upload_jobs")

def get_sync_suppressions_collection():
    return get_collection_with_retry("suppressions")

def get_sync_suppression_logs_collection():
    return get_collection_with_retry("suppression_logs")

def get_sync_segments_collection():  # ✅ FIXED: Correct function name
    return get_collection_with_retry("segments")

def get_sync_ab_tests_collection():
    return get_collection_with_retry("ab_tests")

def get_sync_ab_test_results_collection():
    return get_collection_with_retry("ab_test_results")

def get_sync_automation_rules_collection():
    return get_collection_with_retry("automation_rules")

def get_sync_automation_steps_collection():
    return get_collection_with_retry("automation_steps")

def get_sync_automation_executions_collection():
    return get_collection_with_retry("automation_executions")

# ✅ ENHANCED: Database health monitoring with version detection
def ping_sync_database():
    """Test database connectivity with detailed health info"""
    try:
        # Test basic connectivity
        result = sync_client.admin.command('ping')
        
        # Get server info
        server_info = sync_client.server_info()
        
        # Get server status for health monitoring
        try:
            server_status = sync_client.admin.command('serverStatus')
            connections_info = server_status.get("connections", {})
        except Exception:
            # Fallback if serverStatus command fails
            connections_info = {"current": "unknown", "available": "unknown"}
        
        health_info = {
            "connection_status": "healthy",
            "server_version": server_info.get("version", "unknown"),
            "pymongo_version": sync_client.__class__.__module__,
            "database_name": sync_database.name,
            "active_connections": connections_info.get("current", "unknown"),
            "available_connections": connections_info.get("available", "unknown"),
            "ping_response": result
        }
        
        logger.info("✅ Sync database connection successful", extra=health_info)
        return True, health_info
        
    except Exception as e:
        error_info = {
            "connection_status": "failed", 
            "error": str(e),
            "error_type": type(e).__name__
        }
        logger.error("❌ Sync database connection failed", extra=error_info)
        return False, error_info

# ✅ ENHANCED: Connection cleanup for graceful shutdown
def close_sync_database():
    """Close database connections gracefully"""
    try:
        sync_client.close()
        logger.info("✅ Sync database connections closed successfully")
    except Exception as e:
        logger.error(f"❌ Error closing sync database connections: {e}")

# ✅ NEW: Apply read/write concerns at collection level (compatible approach)
def get_collection_with_concerns(collection_name: str, read_concern_level: str = "local", write_concern: dict = None):
    """
    Get collection with specific read/write concerns applied at collection level
    This is the compatible way to apply concerns across PyMongo versions
    """
    try:
        from pymongo.read_concern import ReadConcern
        from pymongo.write_concern import WriteConcern
        
        collection = get_collection_with_retry(collection_name)
        
        # Apply read concern at collection level (supported in PyMongo 3.2+)
        if read_concern_level and hasattr(ReadConcern, '__init__'):
            read_concern = ReadConcern(level=read_concern_level)
            collection = collection.with_options(read_concern=read_concern)
        
        # Apply write concern if specified
        if write_concern and hasattr(WriteConcern, '__init__'):
            wc = WriteConcern(**write_concern)
            collection = collection.with_options(write_concern=wc)
        
        return collection
        
    except ImportError:
        # Fallback for very old PyMongo versions
        logger.warning(f"ReadConcern/WriteConcern not available, using basic collection for {collection_name}")
        return get_collection_with_retry(collection_name)
    except Exception as e:
        logger.warning(f"Failed to apply concerns to {collection_name}: {e}, using basic collection")
        return get_collection_with_retry(collection_name)

# ✅ NEW: High-reliability collection getters for critical operations
def get_sync_campaigns_collection_with_concerns():
    """Get campaigns collection with majority read concern for consistency"""
    return get_collection_with_concerns(
        "campaigns", 
        read_concern_level="majority",
        write_concern={"w": "majority", "wtimeout": 10000}
    )

def get_sync_email_logs_collection_with_concerns():
    """Get email logs collection with local read concern for performance"""
    return get_collection_with_concerns(
        "email_logs", 
        read_concern_level="local",
        write_concern={"w": 1, "wtimeout": 5000}
    )

# Legacy compatibility
sync_db = sync_database

# ✅ NEW: Startup validation
def validate_database_connection():
    """Validate database connection and log important info"""
    try:
        success, info = ping_sync_database()
        if success:
            logger.info("Database sync module initialized successfully", extra={
                "mongodb_uri": MONGODB_URI.replace(MONGODB_URI.split('@')[0].split('//')[1], "***:***"),  # Hide credentials
                "database_name": sync_database.name,
                "server_version": info.get("server_version"),
                "collections_available": True
            })
        return success
    except Exception as e:
        logger.error(f"Database validation failed: {e}")
        return False

# Run validation on import
if __name__ != "__main__":  # Don't run during direct execution
    validate_database_connection()
