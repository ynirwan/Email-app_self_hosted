# backend/core/config.py - UNIFIED CONFIGURATION
"""
Single source of truth for all application configuration
Replaces: config.py, campaign_config.py, subscriber_config.py
"""
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class Settings:
    """Unified application settings"""
    
    # ===== BASIC APP SETTINGS =====
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG_MODE: bool = os.getenv("DEBUG_MODE", "true").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # ===== JWT AUTHENTICATION =====
    JWT_SECRET: str = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXP: int = int(os.getenv("JWT_EXP", "3600"))  # 1 hour
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # ===== DATABASE CONFIGURATION =====
    MONGODB_URI: str = os.getenv(
        "MONGODB_URI",
        "mongodb://admin:password@mongodb:27017/email_marketing?authSource=admin"
    )
    DB_MAX_POOL_SIZE: int = int(os.getenv("DB_MAX_POOL_SIZE", "50"))
    DB_MIN_POOL_SIZE: int = int(os.getenv("DB_MIN_POOL_SIZE", "5"))
    DB_MAX_IDLE_TIME_SECONDS: int = int(os.getenv("DB_MAX_IDLE_TIME_SECONDS", "300"))
    DB_CONNECTION_TIMEOUT_SECONDS: int = int(os.getenv("DB_CONNECTION_TIMEOUT_SECONDS", "10"))
    DB_SOCKET_TIMEOUT_SECONDS: int = int(os.getenv("DB_SOCKET_TIMEOUT_SECONDS", "30"))
    DB_SERVER_SELECTION_TIMEOUT_SECONDS: int = int(os.getenv("DB_SERVER_SELECTION_TIMEOUT_SECONDS", "10"))
    
    # ===== REDIS CONFIGURATION =====
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_KEY_PREFIX: str = os.getenv("REDIS_KEY_PREFIX", "email_marketing")
    REDIS_DEFAULT_TTL_SECONDS: int = 3600
    
    # ===== EMAIL SENDING CONFIGURATION =====
    MOCK_EMAIL_SENDING: bool = os.getenv("MOCK_EMAIL_SENDING", "false").lower() == "true"
    EMAIL_SEND_TIMEOUT_SECONDS: int = int(os.getenv("EMAIL_SEND_TIMEOUT_SECONDS", "30"))
    MAX_EMAIL_RETRIES: int = int(os.getenv("MAX_EMAIL_RETRIES", "3"))
    RETRY_BACKOFF_BASE_SECONDS: int = 60
    
    # ===== SMTP CONFIGURATION =====
    SMTP_ERROR_THRESHOLD: int = 10
    SMTP_ERROR_WINDOW_SECONDS: int = 300
    SMTP_CIRCUIT_BREAKER_TIMEOUT_SECONDS: int = 600
    
    # ===== AWS SES CONFIGURATION (if using SES) =====
    AWS_REGION: Optional[str] = os.getenv("AWS_REGION")
    AWS_ACCESS_KEY_ID: Optional[str] = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = os.getenv("AWS_SECRET_ACCESS_KEY")
    SES_CONFIGURATION_SET: Optional[str] = os.getenv("SES_CONFIGURATION_SET")
    
    # ===== CAMPAIGN PROCESSING =====
    MAX_BATCH_SIZE: int = int(os.getenv("MAX_BATCH_SIZE", "100"))
    MAX_CONCURRENT_TASKS: int = int(os.getenv("MAX_CONCURRENT_TASKS", "50"))
    WORKER_MAX_TASKS_PER_CHILD: int = int(os.getenv("WORKER_MAX_TASKS_PER_CHILD", "500"))
    TASK_TIMEOUT_SECONDS: int = int(os.getenv("TASK_TIMEOUT_SECONDS", "30"))
    CAMPAIGN_PAUSE_TIMEOUT_SECONDS: int = 3600
    DEFAULT_CAMPAIGN_TIMEOUT_HOURS: int = 24
    
    # ===== SUBSCRIBER PROCESSING =====
    SUBSCRIBER_PROCESSING_TIMEOUT: int = int(os.getenv("SUBSCRIBER_PROCESSING_TIMEOUT", "300"))
    MAX_RECORDS_PER_OPERATION: int = int(os.getenv("MAX_RECORDS_PER_OPERATION", "50000"))
    ENABLE_BULK_OPTIMIZATIONS: bool = os.getenv("ENABLE_BULK_OPTIMIZATIONS", "false").lower() == "true"
    
    # ===== RATE LIMITING =====
    ENABLE_RATE_LIMITING: bool = os.getenv("ENABLE_RATE_LIMITING", "true").lower() == "true"
    BASE_RATE_LIMIT_PER_MINUTE: int = 100
    MAX_RATE_LIMIT_PER_MINUTE: int = 500
    MIN_RATE_LIMIT_PER_MINUTE: int = 10
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_SUCCESS_THRESHOLD: float = 0.95
    RATE_LIMIT_FAILURE_THRESHOLD: float = 0.8
    
    # ===== RESOURCE MANAGEMENT =====
    ENABLE_RESOURCE_MONITORING: bool = os.getenv("ENABLE_RESOURCE_MONITORING", "true").lower() == "true"
    MAX_MEMORY_USAGE_PERCENT: int = int(os.getenv("MAX_MEMORY_USAGE_PERCENT", "85"))
    MAX_CPU_USAGE_PERCENT: int = int(os.getenv("MAX_CPU_USAGE_PERCENT", "80"))
    TASK_MEMORY_LIMIT_MB: int = 512
    QUEUE_SIZE_LIMIT: int = 10000
    
    # ===== DEAD LETTER QUEUE (DLQ) =====
    ENABLE_DLQ: bool = os.getenv("ENABLE_DLQ", "true").lower() == "true"
    ENABLE_DLQ_PROCESSING: bool = True
    DLQ_RETENTION_DAYS: int = 7
    
    # ===== RECOVERY & FAILOVER =====
    ENABLE_HYBRID_RECOVERY: bool = os.getenv("ENABLE_HYBRID_RECOVERY", "true").lower() == "true"
    STARTUP_RECOVERY_ENABLED: bool = os.getenv("STARTUP_RECOVERY_ENABLED", "true").lower() == "true"
    STARTUP_RECOVERY_DELAY_SECONDS: int = 60
    STARTUP_RECOVERY_STUCK_THRESHOLD_HOURS: int = 2
    MIN_HOURS_BETWEEN_RECOVERIES: int = 1
    MAX_RECOVERY_ATTEMPTS: int = 5
    RECOVERY_FILE_PATH: str = os.getenv("RECOVERY_FILE_PATH", "recovery")
    MAX_RECOVERY_FILE_AGE_DAYS: int = int(os.getenv("MAX_RECOVERY_FILE_AGE_DAYS", "30"))
    ENABLE_PROVIDER_FAILOVER: bool = True
    ENABLE_GRACEFUL_SHUTDOWN: bool = True
    SHUTDOWN_TIMEOUT_SECONDS: int = 30
    
    # ===== MONITORING & METRICS =====
    ENABLE_METRICS_COLLECTION: bool = os.getenv("ENABLE_METRICS_COLLECTION", "true").lower() == "true"
    ENABLE_PERFORMANCE_LOGGING: bool = os.getenv("ENABLE_PERFORMANCE_LOGGING", "true").lower() == "true"
    METRICS_COLLECTION_INTERVAL_SECONDS: int = int(os.getenv("METRICS_COLLECTION_INTERVAL_SECONDS", "60"))
    HEALTH_CHECK_INTERVAL_SECONDS: int = int(os.getenv("HEALTH_CHECK_INTERVAL_SECONDS", "30"))
    PROVIDER_HEALTH_CHECK_INTERVAL_SECONDS: int = 300
    METRICS_RETENTION_HOURS: int = 24
    
    # ===== AUDIT & COMPLIANCE =====
    ENABLE_AUDIT_LOGGING: bool = os.getenv("ENABLE_AUDIT_LOGGING", "true").lower() == "true"
    ENABLE_COMPLIANCE_TRACKING: bool = os.getenv("ENABLE_COMPLIANCE_TRACKING", "false").lower() == "true"
    AUDIT_LOG_RETENTION_DAYS: int = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "90"))
    LOG_SENSITIVE_DATA: bool = False  # GDPR compliance
    LOG_EMAIL_CONTENT: bool = False   # Security
    
    # ===== TEMPLATE & CONTENT =====
    ENABLE_TEMPLATE_CACHING: bool = True
    TEMPLATE_CACHE_TTL_SECONDS: int = 3600
    MAX_TEMPLATE_SIZE_KB: int = 500
    ENABLE_CONTENT_COMPRESSION: bool = True
    
    # ===== FEATURE FLAGS =====
    ENABLE_DATABASE_POOLING: bool = os.getenv("ENABLE_DATABASE_POOLING", "true").lower() == "true"
    ENABLE_CAMPAIGN_PAUSE_RESUME: bool = True
    PRODUCTION_SAFETY_MODE: bool = os.getenv("PRODUCTION_SAFETY_MODE", "true").lower() == "true"
    ENABLE_STRUCTURED_LOGGING: bool = True
    
    def __init__(self):
        """Initialize and validate settings"""
        if self.PRODUCTION_SAFETY_MODE:
            # Enforce conservative limits in safety mode
            self.MAX_BATCH_SIZE = min(self.MAX_BATCH_SIZE, 200)
            self.MAX_CONCURRENT_TASKS = min(self.MAX_CONCURRENT_TASKS, 50)
            self.DB_MAX_POOL_SIZE = min(self.DB_MAX_POOL_SIZE, 50)
        
        self._validate_critical_settings()
    
    def _validate_critical_settings(self):
        """Validate critical configuration"""
        if self.ENVIRONMENT == "production":
            if self.JWT_SECRET == "your-secret-key-change-in-production":
                raise ValueError("❌ JWT_SECRET must be changed in production!")
            
            if "localhost" in self.MONGODB_URI and "mongodb:27017" not in self.MONGODB_URI:
                raise ValueError("❌ MONGODB_URI should not use localhost in production!")
    
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.ENVIRONMENT.lower() == "production"
    
    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled"""
        feature_map = {
            'database_pooling': self.ENABLE_DATABASE_POOLING,
            'performance_logging': self.ENABLE_PERFORMANCE_LOGGING,
            'metrics_collection': self.ENABLE_METRICS_COLLECTION,
            'resource_monitoring': self.ENABLE_RESOURCE_MONITORING,
            'dlq': self.ENABLE_DLQ,
            'hybrid_recovery': self.ENABLE_HYBRID_RECOVERY,
            'audit_logging': self.ENABLE_AUDIT_LOGGING,
            'rate_limiting': self.ENABLE_RATE_LIMITING,
            'bulk_optimizations': self.ENABLE_BULK_OPTIMIZATIONS,
            'template_caching': self.ENABLE_TEMPLATE_CACHING,
            'compliance_tracking': self.ENABLE_COMPLIANCE_TRACKING
        }
        return feature_map.get(feature, False)
    
    def get_batch_size_for_operation(self, total_records: int, operation: str = "general") -> int:
        """Calculate optimal batch size for different operations"""
        if operation == "subscriber_upload":
            if not self.ENABLE_BULK_OPTIMIZATIONS:
                return min(1000, total_records)
            
            if total_records < 1000:
                return total_records
            elif total_records < 10000:
                return 1000
            elif total_records < 50000:
                return 2000
            else:
                return min(self.MAX_BATCH_SIZE, 5000)
        
        elif operation == "campaign_batch":
            return min(self.MAX_BATCH_SIZE, total_records)
        
        else:
            return min(1000, total_records)

# Global settings instance
settings = Settings()

# Helper functions
def get_redis_key(key_type: str, identifier: str = "") -> str:
    """Generate consistent Redis keys"""
    base_key = f"{settings.REDIS_KEY_PREFIX}:{key_type}"
    if identifier:
        return f"{base_key}:{identifier}"
    return base_key

def is_production_ready() -> bool:
    """Check if production dependencies are available"""
    try:
        import redis
        r = redis.Redis.from_url(settings.REDIS_URL)
        r.ping()
        return True
    except:
        return False

# Export for backward compatibility
SECRET_KEY = settings.JWT_SECRET
ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
MONGO_URI = settings.MONGODB_URI
JWT_SECRET = settings.JWT_SECRET
JWT_EXP = settings.JWT_EXP

__all__ = ['settings', 'get_redis_key', 'is_production_ready', 'Settings']