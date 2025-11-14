import os
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

class Settings:
    """Unified application settings - Production ready"""
    
    # ===== BASIC APP SETTINGS =====
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG_MODE: bool = os.getenv("DEBUG_MODE", "true").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    APP_NAME: str = "Email Marketing Platform"
    APP_VERSION: str = "1.0.0"
    
    # ===== JWT AUTHENTICATION =====
    JWT_SECRET: str = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXP: int = int(os.getenv("JWT_EXP", "3600"))  # 1 hour
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    RATE_LIMIT_SUCCESS_THRESHOLD: float = 0.95  # 95% success rate threshold
    RATE_LIMIT_FAILURE_THRESHOLD: float = 0.50  # 50% failure rate threshold
    RATE_LIMIT_WINDOW_SECONDS: int = 300       # 5 minute window
    RATE_LIMIT_MIN_SAMPLES: int = 10            # Minimum samples before rate limiting
    
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
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    REDIS_HOST: str = os.getenv("REDIS_HOST", "redis")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_KEY_PREFIX: str = os.getenv("REDIS_KEY_PREFIX", "email_marketing")
    REDIS_DEFAULT_TTL_SECONDS: int = 3600
    REDIS_MAX_CONNECTIONS: int = 50
    
    # ===== EMAIL SENDING CONFIGURATION =====
    EMAIL_SEND_TIMEOUT_SECONDS: int = int(os.getenv("EMAIL_SEND_TIMEOUT_SECONDS", "30"))
    MAX_EMAIL_RETRIES: int = int(os.getenv("MAX_EMAIL_RETRIES", "3"))
    RETRY_BACKOFF_BASE_SECONDS: int = 60000
    RETRY_BACKOFF_MAX_SECONDS: int = 3600
    DEFAULT_SENDER_EMAIL: str = os.getenv("DEFAULT_SENDER_EMAIL", "noreply@example.com")
    DEFAULT_SENDER_NAME: str = os.getenv("DEFAULT_SENDER_NAME", "Email Marketing")
    
    # ===== SMTP CONFIGURATION =====
    SMTP_ERROR_THRESHOLD: int = 10
    SMTP_ERROR_WINDOW_SECONDS: int = 300
    SMTP_CIRCUIT_BREAKER_TIMEOUT_SECONDS: int = 600
    SMTP_CONNECTION_POOL_SIZE: int = 10
    SMTP_USE_TLS: bool = True
    
    # ===== AWS SES CONFIGURATION =====
    AWS_REGION: Optional[str] = os.getenv("AWS_REGION", "us-east-1")
    AWS_ACCESS_KEY_ID: Optional[str] = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = os.getenv("AWS_SECRET_ACCESS_KEY")
    SES_CONFIGURATION_SET: Optional[str] = os.getenv("SES_CONFIGURATION_SET")
    SES_FROM_ARN: Optional[str] = os.getenv("SES_FROM_ARN")
    SES_RETURN_PATH_ARN: Optional[str] = os.getenv("SES_RETURN_PATH_ARN")
    
    # ===== EMAIL PROVIDER CONFIGURATION =====
    EMAIL_PROVIDER: str = os.getenv("EMAIL_PROVIDER", "smtp")  # smtp, ses, sendgrid
    PROVIDER_FAILOVER_ENABLED: bool = os.getenv("PROVIDER_FAILOVER_ENABLED", "true").lower() == "true"
    PROVIDER_HEALTH_CHECK_INTERVAL_SECONDS: int = 300
    
    # ===== CAMPAIGN PROCESSING =====
    MAX_BATCH_SIZE: int = int(os.getenv("MAX_BATCH_SIZE", "1000"))
    MIN_BATCH_SIZE: int = int(os.getenv("MIN_BATCH_SIZE", "1"))
    MAX_CONCURRENT_TASKS: int = int(os.getenv("MAX_CONCURRENT_TASKS", "50"))
    WORKER_MAX_TASKS_PER_CHILD: int = int(os.getenv("WORKER_MAX_TASKS_PER_CHILD", "500"))
    TASK_TIMEOUT_SECONDS: int = int(os.getenv("TASK_TIMEOUT_SECONDS", "30"))
    CAMPAIGN_PAUSE_TIMEOUT_SECONDS: int = 3600
    DEFAULT_CAMPAIGN_TIMEOUT_HOURS: int = 24
    CAMPAIGN_BATCH_DELAY_SECONDS: int = 30
    
    # ===== SUBSCRIBER PROCESSING =====
    SUBSCRIBER_PROCESSING_TIMEOUT: int = int(os.getenv("SUBSCRIBER_PROCESSING_TIMEOUT", "300"))
    MAX_RECORDS_PER_OPERATION: int = int(os.getenv("MAX_RECORDS_PER_OPERATION", "50000"))
    ENABLE_BULK_OPTIMIZATIONS: bool = os.getenv("ENABLE_BULK_OPTIMIZATIONS", "true").lower() == "true"
    SUBSCRIBER_IMPORT_CHUNK_SIZE: int = 1000
    DUPLICATE_CHECK_ENABLED: bool = True
    
    # ===== RATE LIMITING =====
    ENABLE_RATE_LIMITING: bool = os.getenv("ENABLE_RATE_LIMITING", "true").lower() == "true"
    BASE_RATE_LIMIT_PER_MINUTE: int = 10000
    MAX_RATE_LIMIT_PER_MINUTE: int = 50000
    MIN_RATE_LIMIT_PER_MINUTE: int = 10
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    ADAPTIVE_RATE_LIMITING: bool = True
    
    # ===== DEAD LETTER QUEUE (DLQ) =====
    ENABLE_DLQ: bool = os.getenv("ENABLE_DLQ", "true").lower() == "true"
    DLQ_MAX_RETRY_COUNT: int = int(os.getenv("DLQ_MAX_RETRY_COUNT", "1"))
    DLQ_RETRY_DELAY_MINUTES: int = int(os.getenv("DLQ_RETRY_DELAY_MINUTES", "15"))
    DLQ_MAX_AGE_HOURS: int = int(os.getenv("DLQ_MAX_AGE_HOURS", "48"))
    DLQ_PROCESSING_BATCH_SIZE: int = 100
    DLQ_AUTO_RETRY_ENABLED: bool = True
    
    # ===== HYBRID RECOVERY =====
    ENABLE_HYBRID_RECOVERY: bool = os.getenv("ENABLE_HYBRID_RECOVERY", "true").lower() == "true"
    RECOVERY_FILE_PATH: str = os.getenv("RECOVERY_FILE_PATH", "/tmp/recovery")
    RECOVERY_CHUNK_SIZE: int = 10000
    RECOVERY_MAX_FILE_SIZE_MB: int = 500
    FILE_FIRST_RECOVERY_ENABLED: bool = True
    
    # ===== PERFORMANCE & MONITORING =====
    ENABLE_PERFORMANCE_LOGGING: bool = os.getenv("ENABLE_PERFORMANCE_LOGGING", "true").lower() == "true"
    SLOW_QUERY_THRESHOLD_MS: int = 1000
    LOG_QUERY_PERFORMANCE: bool = True
    ENABLE_METRICS_COLLECTION: bool = os.getenv("ENABLE_METRICS_COLLECTION", "true").lower() == "true"
    METRICS_COLLECTION_INTERVAL_SECONDS: int = int(os.getenv("METRICS_COLLECTION_INTERVAL_SECONDS", "60"))
    METRICS_RETENTION_HOURS: int = 24
    METRICS_AGGREGATION_INTERVAL_SECONDS: int = 300
    
    # ===== RESOURCE MONITORING =====
    ENABLE_RESOURCE_MONITORING: bool = os.getenv("ENABLE_RESOURCE_MONITORING", "true").lower() == "true"
    MEMORY_THRESHOLD_PERCENT: float = 85.0
    CPU_THRESHOLD_PERCENT: float = 90.0
    DISK_THRESHOLD_PERCENT: float = 90.0
    RESOURCE_CHECK_INTERVAL_SECONDS: int = 60
    AUTO_SCALE_ON_RESOURCE_PRESSURE: bool = True

    # ===== HEALTH CHECK THRESHOLDS (ADD THESE) =====
    MAX_MEMORY_USAGE_PERCENT: float = float(os.getenv("MAX_MEMORY_USAGE_PERCENT", "85.0"))
    MAX_DISK_USAGE_PERCENT: float = float(os.getenv("MAX_DISK_USAGE_PERCENT", "90.0"))
    MAX_CPU_USAGE_PERCENT: float = float(os.getenv("MAX_CPU_USAGE_PERCENT", "80.0"))
    DATABASE_RESPONSE_TIME_THRESHOLD: float = float(os.getenv("DATABASE_RESPONSE_TIME_THRESHOLD", "2.0"))
    HEALTH_CHECK_STRICT_MODE: bool = os.getenv("HEALTH_CHECK_STRICT_MODE", "false").lower() == "true"
    ENABLE_HEALTH_CHECK_BLOCKING: bool = os.getenv("ENABLE_HEALTH_CHECK_BLOCKING", "false").lower() == "true"
    SKIP_HEALTH_CHECKS_FOR_TESTING: bool = os.getenv("SKIP_HEALTH_CHECKS_FOR_TESTING", "false").lower() == "true"
    
    # ===== HEALTH MONITORING =====
    HEALTH_CHECK_ENABLED: bool = True
    HEALTH_CHECK_INTERVAL_SECONDS: int = int(os.getenv("HEALTH_CHECK_INTERVAL_SECONDS", "30"))
    HEALTH_REPORT_RETENTION_HOURS: int = 24
    ALERT_ON_HEALTH_DEGRADATION: bool = True
    
    # ===== AUDIT & COMPLIANCE =====
    ENABLE_AUDIT_LOGGING: bool = os.getenv("ENABLE_AUDIT_LOGGING", "true").lower() == "true"
    ENABLE_COMPLIANCE_TRACKING: bool = os.getenv("ENABLE_COMPLIANCE_TRACKING", "false").lower() == "true"
    AUDIT_LOG_RETENTION_DAYS: int = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "90"))
    LOG_SENSITIVE_DATA: bool = False  # GDPR compliance
    LOG_EMAIL_CONTENT: bool = False   # Security - never log email content
    GDPR_COMPLIANCE_MODE: bool = True
    DATA_RETENTION_DAYS: int = 365
    
    # ===== TEMPLATE & CONTENT =====
    ENABLE_TEMPLATE_CACHING: bool = True
    TEMPLATE_CACHE_TTL_SECONDS: int = 3600
    MAX_TEMPLATE_SIZE_KB: int = 500
    ENABLE_CONTENT_COMPRESSION: bool = True
    TEMPLATE_VALIDATION_ENABLED: bool = True
    PERSONALIZATION_ENABLED: bool = True

    # ===== CORS CONFIGURATION =====
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:4173"
    ]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]
    
    # ===== SECURITY =====
    MASTER_ENCRYPTION_KEY: Optional[str] = os.getenv("MASTER_ENCRYPTION_KEY")
    ENABLE_FIELD_ENCRYPTION: bool = os.getenv("ENABLE_FIELD_ENCRYPTION", "true").lower() == "true"
    PASSWORD_ENCRYPTION_ENABLED: bool = True
    API_KEY_ROTATION_DAYS: int = 90
    SESSION_TIMEOUT_MINUTES: int = 30
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 15
    
    # ===== WEBHOOK CONFIGURATION =====
    WEBHOOK_ENABLED: bool = True
    WEBHOOK_RETRY_ATTEMPTS: int = 3
    WEBHOOK_TIMEOUT_SECONDS: int = 10
    WEBHOOK_SIGNATURE_ENABLED: bool = True
    WEBHOOK_MAX_PAYLOAD_SIZE_KB: int = 1024
    
    # ===== FILE UPLOAD =====
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
    ALLOWED_FILE_TYPES: List[str] = ['.csv', '.xlsx', '.txt', '.xls']
    UPLOAD_DIRECTORY: str = os.getenv("UPLOAD_DIRECTORY", "/tmp/uploads")
    FILE_CLEANUP_AFTER_HOURS: int = 24
    VALIDATE_FILE_CONTENT: bool = True
    
    # ===== API CONFIGURATION =====
    API_RATE_LIMIT_PER_MINUTE: int = 60
    API_RATE_LIMIT_PER_HOUR: int = 1000
    MAX_PAGE_SIZE: int = 1000
    DEFAULT_PAGE_SIZE: int = 50
    API_TIMEOUT_SECONDS: int = 30
    
    # ===== FEATURE FLAGS =====
    ENABLE_DATABASE_POOLING: bool = os.getenv("ENABLE_DATABASE_POOLING", "true").lower() == "true"
    ENABLE_CAMPAIGN_PAUSE_RESUME: bool = True
    ENABLE_AB_TESTING: bool = True
    ENABLE_AUTOMATION: bool = True
    ENABLE_SEGMENTATION: bool = True
    ENABLE_SUPPRESSIONS: bool = True
    PRODUCTION_SAFETY_MODE: bool = os.getenv("PRODUCTION_SAFETY_MODE", "true").lower() == "true"
    ENABLE_STRUCTURED_LOGGING: bool = True
    ENABLE_GRACEFUL_SHUTDOWN: bool = True
    
    # ===== CELERY CONFIGURATION =====
    CELERY_BROKER_URL: str = REDIS_URL
    CELERY_RESULT_BACKEND: str = REDIS_URL
    CELERY_TASK_SERIALIZER: str = 'json'
    CELERY_RESULT_SERIALIZER: str = 'json'
    CELERY_ACCEPT_CONTENT: List[str] = ['json']
    CELERY_TIMEZONE: str = 'UTC'
    CELERY_ENABLE_UTC: bool = True
    CELERY_WORKER_PREFETCH_MULTIPLIER: int = 4
    CELERY_TASK_ACKS_LATE: bool = False
    
    
    # ===== ANALYTICS =====
    ENABLE_REAL_TIME_ANALYTICS: bool = True
    ANALYTICS_AGGREGATION_INTERVAL_MINUTES: int = 5
    ANALYTICS_RETENTION_DAYS: int = 90
    TRACK_LINK_CLICKS: bool = True
    TRACK_EMAIL_OPENS: bool = True
    
    # ===== NOTIFICATIONS =====
    ENABLE_SYSTEM_NOTIFICATIONS: bool = True
    NOTIFICATION_EMAIL: Optional[str] = os.getenv("NOTIFICATION_EMAIL")
    NOTIFY_ON_CAMPAIGN_COMPLETE: bool = True
    NOTIFY_ON_ERRORS: bool = True
    NOTIFY_ON_THRESHOLD_BREACH: bool = True
    
    def __init__(self):
        """Initialize and validate settings"""
        # Apply production safety mode restrictions
        if self.PRODUCTION_SAFETY_MODE:
            self._apply_safety_limits()
        
        # Validate critical settings
        self._validate_critical_settings()
        
        # Initialize computed settings
        self._initialize_computed_settings()
    
    def _apply_safety_limits(self):
        """Apply conservative limits in production safety mode"""
        self.MAX_BATCH_SIZE = min(self.MAX_BATCH_SIZE, 1000)
        self.MAX_CONCURRENT_TASKS = min(self.MAX_CONCURRENT_TASKS, 50)
        self.DB_MAX_POOL_SIZE = min(self.DB_MAX_POOL_SIZE, 50)
        self.MAX_RECORDS_PER_OPERATION = min(self.MAX_RECORDS_PER_OPERATION, 50000)
        self.MAX_FILE_SIZE_MB = min(self.MAX_FILE_SIZE_MB, 50)
    
    def _validate_critical_settings(self):
        """Validate critical configuration values"""
        errors = []
        
        # Production environment checks
        if self.ENVIRONMENT == "production":
            if self.JWT_SECRET == "your-secret-key-change-in-production":
                errors.append("JWT_SECRET must be changed in production!")
            
            if "localhost" in self.MONGODB_URI and "mongodb:27017" not in self.MONGODB_URI:
                errors.append("MONGODB_URI should not use localhost in production!")
            
            if self.DEBUG_MODE:
                errors.append("DEBUG_MODE should be False in production!")
            
            if not self.MASTER_ENCRYPTION_KEY:
                errors.append("MASTER_ENCRYPTION_KEY is required in production!")
        
        # Email provider validation
        if self.EMAIL_PROVIDER not in ['smtp', 'ses', 'sendgrid']:
            errors.append(f"Invalid EMAIL_PROVIDER: {self.EMAIL_PROVIDER}")
        
        # Rate limiting validation
        if self.MIN_RATE_LIMIT_PER_MINUTE >= self.MAX_RATE_LIMIT_PER_MINUTE:
            errors.append("MIN_RATE_LIMIT_PER_MINUTE must be less than MAX_RATE_LIMIT_PER_MINUTE")
        
        # Batch size validation
        if self.MIN_BATCH_SIZE >= self.MAX_BATCH_SIZE:
            errors.append("MIN_BATCH_SIZE must be less than MAX_BATCH_SIZE")
        
        # Raise if there are critical errors
        if errors:
            error_message = "Configuration validation failed:\n" + "\n".join(f"  ❌ {err}" for err in errors)
            raise ValueError(error_message)
    
    def _initialize_computed_settings(self):
        """Initialize settings that depend on other settings"""
        # Compute optimal worker settings based on concurrent tasks
        if not hasattr(self, '_computed_initialized'):
            self.CELERY_WORKER_PREFETCH_MULTIPLIER = max(1, self.MAX_CONCURRENT_TASKS // 10)
            self._computed_initialized = True
    
    # ============================================
    # HELPER METHODS
    # ============================================
    
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.ENVIRONMENT.lower() == "production"
    
    def is_development(self) -> bool:
        """Check if running in development environment"""
        return self.ENVIRONMENT.lower() == "development"
    
    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a specific feature is enabled"""
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
            'compliance_tracking': self.ENABLE_COMPLIANCE_TRACKING,
            'ab_testing': self.ENABLE_AB_TESTING,
            'automation': self.ENABLE_AUTOMATION,
            'segmentation': self.ENABLE_SEGMENTATION,
            'suppressions': self.ENABLE_SUPPRESSIONS
        }
        return feature_map.get(feature.lower(), False)
    
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
            return min(self.MAX_BATCH_SIZE, max(self.MIN_BATCH_SIZE, total_records))
        
        elif operation == "email_sending":
            # Conservative batch size for actual email sending
            return min(self.MAX_BATCH_SIZE, 1000)
        
        else:
            # Default batch size
            return min(1000, total_records)
    
    def get_provider_config(self, provider_type: str) -> Dict[str, Any]:
        """Get provider-specific configuration"""
        configs = {
            "smtp": {
                "timeout": self.SMTP_CONNECTION_POOL_SIZE,
                "max_batch": 100,
                "rate_limit": self.BASE_RATE_LIMIT_PER_MINUTE,
                "use_tls": self.SMTP_USE_TLS
            },
            "ses": {
                "region": self.AWS_REGION,
                "max_batch": 50,
                "rate_limit": 200,
                "configuration_set": self.SES_CONFIGURATION_SET
            },
            "sendgrid": {
                "api_version": "v3",
                "max_batch": 1000,
                "rate_limit": 1000
            }
        }
        return configs.get(provider_type, configs["smtp"])
    
    def get_rate_limit(self, provider: str = "default") -> int:
        """Get rate limit for specific provider"""
        provider_limits = {
            "sendgrid": 1000,
            "ses": 200,
            "smtp": 1000,
            "default": self.BASE_RATE_LIMIT_PER_MINUTE
        }
        return provider_limits.get(provider, self.BASE_RATE_LIMIT_PER_MINUTE)
    
    def validate_email_settings(self, settings_dict: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate email provider settings"""
        errors = []
        
        provider = settings_dict.get('provider', '').lower()
        
        if provider == 'smtp':
            required = ['smtp_server', 'smtp_port', 'username', 'password']
            for field in required:
                if not settings_dict.get(field):
                    errors.append(f"SMTP {field} is required")
        
        elif provider == 'ses':
            required = ['aws_access_key', 'aws_secret_key', 'region']
            for field in required:
                if not settings_dict.get(field):
                    errors.append(f"SES {field} is required")
        
        elif provider == 'sendgrid':
            if not settings_dict.get('api_key'):
                errors.append("SendGrid API key is required")
        
        else:
            errors.append(f"Unknown provider: {provider}")
        
        return len(errors) == 0, errors
    
    def get_monitoring_config(self) -> Dict[str, Any]:
        """Get monitoring configuration"""
        return {
            "enabled": self.ENABLE_RESOURCE_MONITORING,
            "interval_seconds": self.RESOURCE_CHECK_INTERVAL_SECONDS,
            "thresholds": {
                "memory_percent": self.MEMORY_THRESHOLD_PERCENT,
                "cpu_percent": self.CPU_THRESHOLD_PERCENT,
                "disk_percent": self.DISK_THRESHOLD_PERCENT
            },
            "health_check": {
                "enabled": self.HEALTH_CHECK_ENABLED,
                "interval_seconds": self.HEALTH_CHECK_INTERVAL_SECONDS
            },
            "metrics": {
                "enabled": self.ENABLE_METRICS_COLLECTION,
                "interval_seconds": self.METRICS_COLLECTION_INTERVAL_SECONDS,
                "retention_hours": self.METRICS_RETENTION_HOURS
            }
        }
    
    def get_security_config(self) -> Dict[str, Any]:
        """Get security configuration"""
        return {
            "encryption_enabled": self.ENABLE_FIELD_ENCRYPTION,
            "password_encryption": self.PASSWORD_ENCRYPTION_ENABLED,
            "session_timeout_minutes": self.SESSION_TIMEOUT_MINUTES,
            "max_login_attempts": self.MAX_LOGIN_ATTEMPTS,
            "lockout_duration_minutes": self.LOCKOUT_DURATION_MINUTES,
            "jwt": {
                "algorithm": self.JWT_ALGORITHM,
                "expiry_seconds": self.JWT_EXP
            }
        }
    
    def get_feature_flags(self) -> Dict[str, bool]:
        """Get all feature flags as a dictionary"""
        return {
            "database_pooling": self.ENABLE_DATABASE_POOLING,
            "campaign_pause_resume": self.ENABLE_CAMPAIGN_PAUSE_RESUME,
            "ab_testing": self.ENABLE_AB_TESTING,
            "automation": self.ENABLE_AUTOMATION,
            "segmentation": self.ENABLE_SEGMENTATION,
            "suppressions": self.ENABLE_SUPPRESSIONS,
            "performance_logging": self.ENABLE_PERFORMANCE_LOGGING,
            "metrics_collection": self.ENABLE_METRICS_COLLECTION,
            "resource_monitoring": self.ENABLE_RESOURCE_MONITORING,
            "dlq": self.ENABLE_DLQ,
            "hybrid_recovery": self.ENABLE_HYBRID_RECOVERY,
            "audit_logging": self.ENABLE_AUDIT_LOGGING,
            "rate_limiting": self.ENABLE_RATE_LIMITING,
            "bulk_optimizations": self.ENABLE_BULK_OPTIMIZATIONS,
            "template_caching": self.ENABLE_TEMPLATE_CACHING,
            "compliance_tracking": self.ENABLE_COMPLIANCE_TRACKING
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Export configuration as dictionary (excluding sensitive data)"""
        sensitive_keys = {
            'JWT_SECRET', 'MASTER_ENCRYPTION_KEY', 
            'AWS_SECRET_ACCESS_KEY', 'MONGODB_URI',
            'REDIS_URL'
        }
        
        config_dict = {}
        for key, value in self.__dict__.items():
            if not key.startswith('_') and key not in sensitive_keys:
                config_dict[key] = value
        
        return config_dict


# ============================================
# GLOBAL SETTINGS INSTANCE
# ============================================

settings = Settings()


# ============================================
# HELPER FUNCTIONS
# ============================================

def get_redis_key(key_type: str, identifier: str = "") -> str:
    """Generate consistent Redis keys with prefix"""
    base_key = f"{settings.REDIS_KEY_PREFIX}:{key_type}"
    if identifier:
        return f"{base_key}:{identifier}"
    return base_key


def is_production_ready() -> tuple[bool, List[str]]:
    """Check if all production dependencies are available"""
    checks = []
    all_ready = True
    
    # Check Redis connection
    try:
        import redis
        r = redis.Redis.from_url(settings.REDIS_URL)
        r.ping()
        checks.append("✅ Redis connection")
    except Exception as e:
        checks.append(f"❌ Redis connection: {e}")
        all_ready = False
    
    # Check MongoDB connection
    try:
        from pymongo import MongoClient
        client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        checks.append("✅ MongoDB connection")
        client.close()
    except Exception as e:
        checks.append(f"❌ MongoDB connection: {e}")
        all_ready = False
    
    # Check encryption key in production
    if settings.is_production() and not settings.MASTER_ENCRYPTION_KEY:
        checks.append("❌ MASTER_ENCRYPTION_KEY not set in production")
        all_ready = False
    else:
        checks.append("✅ Encryption key configured")
    
    # Check JWT secret
    if settings.JWT_SECRET == "your-secret-key-change-in-production":
        checks.append("⚠️  Using default JWT_SECRET (change in production)")
        if settings.is_production():
            all_ready = False
    else:
        checks.append("✅ JWT secret configured")
    
    return all_ready, checks


def validate_config() -> None:
    """Validate configuration and raise exception if invalid"""
    try:
        # This will run validation during settings initialization
        _ = settings.__dict__
        print("✅ Configuration validated successfully")
    except ValueError as e:
        print(f"❌ Configuration validation failed: {e}")
        raise


# ============================================
# LEGACY COMPATIBILITY EXPORTS
# ============================================

# For backward compatibility with existing code
SECRET_KEY = settings.JWT_SECRET
ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
MONGO_URI = settings.MONGODB_URI
JWT_SECRET = settings.JWT_SECRET
JWT_EXP = settings.JWT_EXP
REDIS_URL = settings.REDIS_URL


# ============================================
# MODULE EXPORTS
# ============================================

__all__ = [
    # Main settings
    'settings',
    'Settings',
    
    # Helper functions
    'get_redis_key',
    'is_production_ready',
    'validate_config',
    
    # Legacy exports
    'SECRET_KEY',
    'ALGORITHM',
    'ACCESS_TOKEN_EXPIRE_MINUTES',
    'MONGO_URI',
    'JWT_SECRET',
    'JWT_EXP',
    'REDIS_URL',
]


# ============================================
# AUTO-VALIDATION ON IMPORT
# ============================================

# Validate configuration on module import
try:
    validate_config()
except Exception as e:
    print(f"⚠️  Configuration validation error: {e}")
    # Don't raise in development to allow debugging
    if settings.is_production():
        raise

