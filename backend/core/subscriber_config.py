# backend/config.py - SAFE PRODUCTION CONFIGURATION
"""
Production configuration that enhances existing system without breaking anything.
All features are DISABLED by default - enable gradually via environment variables.
"""
import os
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class ProductionSettings:
    """Safe production settings - all features disabled by default"""
    
    # ===== BASIC SYSTEM SETTINGS =====
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    DEBUG_MODE: bool = os.getenv("DEBUG_MODE", "true").lower() == "true"
    
    # ===== SUBSCRIBER PROCESSING (CURRENT DEFAULTS) =====
    MAX_BATCH_SIZE: int = int(os.getenv("MAX_BATCH_SIZE", "1000"))  # Your current default
    SUBSCRIBER_PROCESSING_TIMEOUT: int = int(os.getenv("SUBSCRIBER_PROCESSING_TIMEOUT", "300"))
    ENABLE_BULK_OPTIMIZATIONS: bool = os.getenv("ENABLE_BULK_OPTIMIZATIONS", "false").lower() == "true"
    
    # ===== PRODUCTION FEATURES (ALL DISABLED BY DEFAULT) =====
    ENABLE_DATABASE_POOLING: bool = os.getenv("ENABLE_DATABASE_POOLING", "false").lower() == "true"
    ENABLE_PERFORMANCE_LOGGING: bool = os.getenv("ENABLE_PERFORMANCE_LOGGING", "false").lower() == "true"
    ENABLE_METRICS_COLLECTION: bool = os.getenv("ENABLE_METRICS_COLLECTION", "false").lower() == "true"
    ENABLE_RESOURCE_MONITORING: bool = os.getenv("ENABLE_RESOURCE_MONITORING", "false").lower() == "true"
    ENABLE_DLQ: bool = os.getenv("ENABLE_DLQ", "false").lower() == "true"
    ENABLE_HYBRID_RECOVERY: bool = os.getenv("ENABLE_HYBRID_RECOVERY", "true").lower() == "true"  # File recovery always on
    ENABLE_AUDIT_LOGGING: bool = os.getenv("ENABLE_AUDIT_LOGGING", "false").lower() == "true"
    ENABLE_RATE_LIMITING: bool = os.getenv("ENABLE_RATE_LIMITING", "false").lower() == "true"
    
    # ===== DATABASE SETTINGS =====
    DB_MAX_POOL_SIZE: int = int(os.getenv("DB_MAX_POOL_SIZE", "10"))
    DB_MIN_POOL_SIZE: int = int(os.getenv("DB_MIN_POOL_SIZE", "2"))
    DB_CONNECTION_TIMEOUT_SECONDS: int = int(os.getenv("DB_CONNECTION_TIMEOUT_SECONDS", "30"))
    
    # ===== REDIS SETTINGS =====
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_KEY_PREFIX: str = os.getenv("REDIS_KEY_PREFIX", "email_app")
    
    # ===== RECOVERY SETTINGS =====
    RECOVERY_FILE_PATH: str = os.getenv("RECOVERY_FILE_PATH", "recovery")
    MAX_RECOVERY_FILE_AGE_DAYS: int = int(os.getenv("MAX_RECOVERY_FILE_AGE_DAYS", "30"))
    
    # ===== RESOURCE LIMITS =====
    MAX_MEMORY_USAGE_PERCENT: int = int(os.getenv("MAX_MEMORY_USAGE_PERCENT", "80"))
    MAX_CPU_USAGE_PERCENT: int = int(os.getenv("MAX_CPU_USAGE_PERCENT", "80"))
    MAX_RECORDS_PER_OPERATION: int = int(os.getenv("MAX_RECORDS_PER_OPERATION", "50000"))
    
    # ===== EMAIL SETTINGS =====
    MOCK_EMAIL_SENDING: bool = os.getenv("MOCK_EMAIL_SENDING", "false").lower() == "true"
    EMAIL_SEND_TIMEOUT_SECONDS: int = int(os.getenv("EMAIL_SEND_TIMEOUT_SECONDS", "30"))
    MAX_CONCURRENT_TASKS: int = int(os.getenv("MAX_CONCURRENT_TASKS", "10"))
    
    # ===== SAFETY SETTINGS =====
    PRODUCTION_SAFETY_MODE: bool = os.getenv("PRODUCTION_SAFETY_MODE", "true").lower() == "true"
    
    def __init__(self):
        """Initialize with safety checks"""
        if self.PRODUCTION_SAFETY_MODE:
            # Force conservative settings
            self.MAX_BATCH_SIZE = min(self.MAX_BATCH_SIZE, 2000)
            self.MAX_CONCURRENT_TASKS = min(self.MAX_CONCURRENT_TASKS, 20)
            self.DB_MAX_POOL_SIZE = min(self.DB_MAX_POOL_SIZE, 20)
        
        logger.info("✅ Production configuration loaded (safety mode: %s)", self.PRODUCTION_SAFETY_MODE)
    
    def get_batch_size_for_operation(self, total_records: int, operation: str = "general") -> int:
        """Get optimal batch size for different operations"""
        if operation == "subscriber_upload":
            if not self.ENABLE_BULK_OPTIMIZATIONS:
                return min(1000, total_records)
            
            # Smart batch sizing when optimizations enabled
            if total_records < 1000:
                return total_records
            elif total_records < 10000:
                return 1000
            elif total_records < 50000:
                return 2000
            else:
                return min(self.MAX_BATCH_SIZE, 5000)
        else:
            return min(1000, total_records)
    
    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a production feature is enabled"""
        feature_map = {
            'database_pooling': self.ENABLE_DATABASE_POOLING,
            'performance_logging': self.ENABLE_PERFORMANCE_LOGGING,
            'metrics_collection': self.ENABLE_METRICS_COLLECTION,
            'resource_monitoring': self.ENABLE_RESOURCE_MONITORING,
            'dlq': self.ENABLE_DLQ,
            'hybrid_recovery': self.ENABLE_HYBRID_RECOVERY,
            'audit_logging': self.ENABLE_AUDIT_LOGGING,
            'rate_limiting': self.ENABLE_RATE_LIMITING,
            'bulk_optimizations': self.ENABLE_BULK_OPTIMIZATIONS
        }
        return feature_map.get(feature, False)

# Global settings instance
settings = ProductionSettings()

# Helper functions
def get_redis_key(key_type: str, identifier: str = "") -> str:
    """Generate consistent Redis keys"""
    base_key = f"{settings.REDIS_KEY_PREFIX}:{key_type}"
    if identifier:
        return f"{base_key}:{identifier}"
    return base_key

def is_production_ready() -> bool:
    """Check if production features are available"""
    try:
        import redis
        r = redis.Redis.from_url(settings.REDIS_URL)
        r.ping()
        return True
    except:
        return False

# Export settings
__all__ = ['settings', 'get_redis_key', 'is_production_ready']

