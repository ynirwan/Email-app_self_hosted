# backend/config.py - COMPLETE PRODUCTION CONFIG
"""
Production-ready email marketing configuration
Centralized settings for easy management
"""
import os
from datetime import timedelta

class ProductionSettings:
    # ===== EMAIL SENDING CONFIGURATION =====
    MOCK_EMAIL_SENDING = False  # ← Change to False for real emails
    ENABLE_DLQ = True
    ENABLE_RATE_LIMITING = True
    ENABLE_METRICS_COLLECTION = True
    
    # ===== PERFORMANCE SETTINGS =====
    MAX_BATCH_SIZE = 100  # Reduced from 1000 to prevent memory issues
    MAX_CONCURRENT_TASKS = 50  # Limit concurrent tasks per worker
    WORKER_MAX_TASKS_PER_CHILD = 500  # Restart workers to prevent memory leaks
    TASK_TIMEOUT_SECONDS = 30
    EMAIL_SEND_TIMEOUT_SECONDS = 10
    
    # ===== MEMORY & RESOURCE MANAGEMENT =====
    MAX_MEMORY_USAGE_PERCENT = 85
    TASK_MEMORY_LIMIT_MB = 512
    QUEUE_SIZE_LIMIT = 10000
    ENABLE_RESOURCE_MONITORING = True
    
    # ===== DATABASE CONNECTION POOLING =====
    DB_MAX_POOL_SIZE = 20
    DB_MIN_POOL_SIZE = 5
    DB_MAX_IDLE_TIME_SECONDS = 300  # 5 minutes
    DB_CONNECTION_TIMEOUT_SECONDS = 10
    DB_SOCKET_TIMEOUT_SECONDS = 10
    DB_SERVER_SELECTION_TIMEOUT_SECONDS = 5
    
    # ===== RATE LIMITING CONFIGURATION =====
    BASE_RATE_LIMIT_PER_MINUTE = 100
    MAX_RATE_LIMIT_PER_MINUTE = 500
    MIN_RATE_LIMIT_PER_MINUTE = 10
    RATE_LIMIT_WINDOW_SECONDS = 60
    RATE_LIMIT_SUCCESS_THRESHOLD = 0.95  # 95% success rate to increase
    RATE_LIMIT_FAILURE_THRESHOLD = 0.8   # 80% success rate to decrease
    
    # ===== RETRY & DLQ CONFIGURATION =====
    MAX_EMAIL_RETRIES = 3
    RETRY_BACKOFF_BASE_SECONDS = 60  # 1, 2, 4 minutes exponential backoff
    DLQ_RETENTION_DAYS = 7
    ENABLE_DLQ_PROCESSING = True
    
    # ===== STARTUP RECOVERY SETTINGS =====
    STARTUP_RECOVERY_ENABLED = True
    STARTUP_RECOVERY_DELAY_SECONDS = 60
    STARTUP_RECOVERY_STUCK_THRESHOLD_HOURS = 2
    MIN_HOURS_BETWEEN_RECOVERIES = 1
    MAX_RECOVERY_ATTEMPTS = 5
    
    # ===== MONITORING & METRICS =====
    METRICS_COLLECTION_INTERVAL_SECONDS = 60
    HEALTH_CHECK_INTERVAL_SECONDS = 30
    METRICS_RETENTION_HOURS = 24
    ENABLE_PERFORMANCE_LOGGING = True
    
    # ===== CAMPAIGN MANAGEMENT =====
    ENABLE_CAMPAIGN_PAUSE_RESUME = True
    CAMPAIGN_PAUSE_TIMEOUT_SECONDS = 3600  # 1 hour
    DEFAULT_CAMPAIGN_TIMEOUT_HOURS = 24
    
    # ===== SMTP CIRCUIT BREAKER =====
    SMTP_ERROR_THRESHOLD = 10
    SMTP_ERROR_WINDOW_SECONDS = 300  # 5 minutes
    SMTP_CIRCUIT_BREAKER_TIMEOUT_SECONDS = 600  # 10 minutes
    
    # ===== TEMPLATE & CONTENT =====
    ENABLE_TEMPLATE_CACHING = True
    TEMPLATE_CACHE_TTL_SECONDS = 3600  # 1 hour
    MAX_TEMPLATE_SIZE_KB = 500
    ENABLE_CONTENT_COMPRESSION = True
    
    # ===== AUDIT & COMPLIANCE =====
    ENABLE_AUDIT_LOGGING = True
    AUDIT_LOG_RETENTION_DAYS = 90
    ENABLE_COMPLIANCE_TRACKING = True
    LOG_SENSITIVE_DATA = False  # For GDPR compliance
    
    # ===== FAILOVER & RELIABILITY =====
    ENABLE_PROVIDER_FAILOVER = True
    PROVIDER_HEALTH_CHECK_INTERVAL_SECONDS = 300  # 5 minutes
    ENABLE_GRACEFUL_SHUTDOWN = True
    SHUTDOWN_TIMEOUT_SECONDS = 30
    
    # ===== REDIS CONFIGURATION =====
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_KEY_PREFIX = "email_marketing"
    REDIS_DEFAULT_TTL_SECONDS = 3600
    
    # ===== LOGGING CONFIGURATION =====
    LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
    ENABLE_STRUCTURED_LOGGING = True
    LOG_EMAIL_CONTENT = False  # Security: Don't log email content

# Global settings instance
settings = ProductionSettings()

# Helper functions
def get_redis_key(key_type: str, identifier: str = None) -> str:
    """Generate consistent Redis keys"""
    if identifier:
        return f"{settings.REDIS_KEY_PREFIX}:{key_type}:{identifier}"
    return f"{settings.REDIS_KEY_PREFIX}:{key_type}"

def is_production() -> bool:
    """Check if running in production"""
    return os.getenv("ENVIRONMENT", "development").lower() == "production"

