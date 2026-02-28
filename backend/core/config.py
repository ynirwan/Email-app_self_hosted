import os
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

class Settings:
    """App-level settings only. Task/Celery settings are in tasks/task_config.py"""
    
    # ===== BASIC APP SETTINGS =====
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG_MODE: bool = os.getenv("DEBUG_MODE", "true").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    APP_NAME: str = "Email Marketing Platform"
    APP_VERSION: str = "1.0.0"
    
    # ===== JWT AUTHENTICATION =====
    JWT_SECRET: str = os.getenv("JWT_SECRET", "your-secret-key-change-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXP: int = int(os.getenv("JWT_EXP", "3600"))
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # ===== DATABASE CONFIGURATION =====
    MONGODB_URI: str = os.getenv("MONGODB_URI", "")
    DB_MAX_POOL_SIZE: int = int(os.getenv("DB_MAX_POOL_SIZE", "50"))
    DB_MIN_POOL_SIZE: int = int(os.getenv("DB_MIN_POOL_SIZE", "5"))
    DB_MAX_IDLE_TIME_SECONDS: int = int(os.getenv("DB_MAX_IDLE_TIME_SECONDS", "300"))
    DB_CONNECTION_TIMEOUT_SECONDS: int = int(os.getenv("DB_CONNECTION_TIMEOUT_SECONDS", "10"))
    DB_SOCKET_TIMEOUT_SECONDS: int = int(os.getenv("DB_SOCKET_TIMEOUT_SECONDS", "30"))
    DB_SERVER_SELECTION_TIMEOUT_SECONDS: int = int(os.getenv("DB_SERVER_SELECTION_TIMEOUT_SECONDS", "10"))
    
    # ===== REDIS CONFIGURATION =====
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_KEY_PREFIX: str = os.getenv("REDIS_KEY_PREFIX", "email_marketing")
    REDIS_DEFAULT_TTL_SECONDS: int = 3600
    REDIS_MAX_CONNECTIONS: int = 50
    
    # ===== SECURITY =====
    MASTER_ENCRYPTION_KEY: str = os.getenv("MASTER_ENCRYPTION_KEY", "")
    ENABLE_FIELD_ENCRYPTION: bool = os.getenv("ENABLE_FIELD_ENCRYPTION", "true").lower() == "true"
    PASSWORD_ENCRYPTION_ENABLED: bool = True
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 15
    SESSION_TIMEOUT_MINUTES: int = 30
    
    # ===== CORS CONFIGURATION =====
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5000",
        "http://localhost:5173",
        "http://localhost:4173",
        "*"
    ]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]
    
    # ===== UNSUBSCRIBE CONFIGURATION =====
    UNSUBSCRIBE_DOMAIN: str = os.getenv("UNSUBSCRIBE_DOMAIN", "gnagainbox.com")
    
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
    
    # ===== DEPLOYMENT =====
    DEPLOYMENT_MODE: str = os.getenv("DEPLOYMENT_MODE", "self_hosted")
    EMAIL_QUOTA_ENABLED: bool = os.getenv("EMAIL_QUOTA_ENABLED", "false").lower() == "true"
    EMAIL_QUOTA_SOURCE: str = os.getenv("EMAIL_QUOTA_SOURCE", "database")
    FREE_EMAIL_LIMIT_MONTHLY: int = int(os.getenv("FREE_EMAIL_LIMIT_MONTHLY", "50000"))
    QUOTA_CHECK_URL: str = os.getenv("QUOTA_CHECK_URL", "")
    QUOTA_API_KEY: str = os.getenv("QUOTA_API_KEY", "")
    
    # ===== STARTUP =====
    STARTUP_RECOVERY_ENABLED: bool = os.getenv("STARTUP_RECOVERY_ENABLED", "true").lower() == "true"
    
    # ===== CELERY CONNECTION (shared) =====
    CELERY_BROKER_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    CELERY_TASK_SERIALIZER: str = 'json'
    CELERY_RESULT_SERIALIZER: str = 'json'
    CELERY_ACCEPT_CONTENT: List[str] = ['json']
    CELERY_TIMEZONE: str = 'UTC'
    CELERY_ENABLE_UTC: bool = True
    
    # ===== DATABASE POOLING =====
    ENABLE_DATABASE_POOLING: bool = os.getenv("ENABLE_DATABASE_POOLING", "true").lower() == "true"
    
    def __init__(self):
        self._validate_critical_settings()
    
    def _validate_critical_settings(self):
        errors = []
        
        if self.ENVIRONMENT == "production":
            if self.JWT_SECRET == "your-secret-key-change-in-production":
                errors.append("JWT_SECRET must be changed in production!")
            
            if not self.MONGODB_URI:
                errors.append("MONGODB_URI is required!")
            
            if self.DEBUG_MODE:
                errors.append("DEBUG_MODE should be False in production!")
            
            if not self.MASTER_ENCRYPTION_KEY:
                errors.append("MASTER_ENCRYPTION_KEY is required in production!")
        
        if errors:
            error_message = "Configuration validation failed:\n" + "\n".join(f"  - {err}" for err in errors)
            raise ValueError(error_message)
    
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"
    
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == "development"
    
    def is_feature_enabled(self, feature: str) -> bool:
        feature_map = {
            'database_pooling': self.ENABLE_DATABASE_POOLING,
        }
        return feature_map.get(feature.lower(), False)
    
    def get_security_config(self) -> Dict[str, Any]:
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
        return {
            "database_pooling": self.ENABLE_DATABASE_POOLING,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        sensitive_keys = {
            'JWT_SECRET', 'MASTER_ENCRYPTION_KEY',
            'MONGODB_URI', 'REDIS_URL', 'QUOTA_API_KEY'
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
    base_key = f"{settings.REDIS_KEY_PREFIX}:{key_type}"
    if identifier:
        return f"{base_key}:{identifier}"
    return base_key


def is_production_ready() -> tuple[bool, List[str]]:
    checks = []
    all_ready = True
    
    try:
        import redis
        r = redis.Redis.from_url(settings.REDIS_URL)
        r.ping()
        checks.append("Redis connection OK")
    except Exception as e:
        checks.append(f"Redis connection failed: {e}")
        all_ready = False
    
    try:
        from pymongo import MongoClient
        client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        checks.append("MongoDB connection OK")
        client.close()
    except Exception as e:
        checks.append(f"MongoDB connection failed: {e}")
        all_ready = False
    
    if settings.is_production() and not settings.MASTER_ENCRYPTION_KEY:
        checks.append("MASTER_ENCRYPTION_KEY not set in production")
        all_ready = False
    else:
        checks.append("Encryption key configured")
    
    if settings.JWT_SECRET == "your-secret-key-change-in-production":
        checks.append("Using default JWT_SECRET (change in production)")
        if settings.is_production():
            all_ready = False
    else:
        checks.append("JWT secret configured")
    
    return all_ready, checks


def validate_config() -> None:
    try:
        _ = settings.__dict__
        print("Configuration validated successfully")
    except ValueError as e:
        print(f"Configuration validation failed: {e}")
        raise


# ============================================
# LEGACY COMPATIBILITY EXPORTS
# ============================================

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
    'settings',
    'Settings',
    'get_redis_key',
    'is_production_ready',
    'validate_config',
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

try:
    validate_config()
except Exception as e:
    print(f"Configuration validation error: {e}")
    if settings.is_production():
        raise
