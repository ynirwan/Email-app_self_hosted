import os
from dotenv import load_dotenv

load_dotenv()


class TaskSettings:

    # ===== CAMPAIGN PROCESSING =====
    MAX_BATCH_SIZE: int = int(os.getenv("MAX_BATCH_SIZE", "1000"))
    MIN_BATCH_SIZE: int = int(os.getenv("MIN_BATCH_SIZE", "1"))
    MAX_CONCURRENT_TASKS: int = int(os.getenv("MAX_CONCURRENT_TASKS", "50"))
    WORKER_MAX_TASKS_PER_CHILD: int = int(os.getenv("WORKER_MAX_TASKS_PER_CHILD", "500"))
    TASK_TIMEOUT_SECONDS: int = int(os.getenv("TASK_TIMEOUT_SECONDS", "30"))
    CAMPAIGN_PAUSE_TIMEOUT_SECONDS: int = 3600
    DEFAULT_CAMPAIGN_TIMEOUT_HOURS: int = 24
    CAMPAIGN_BATCH_DELAY_SECONDS: int = 30

    # ===== EMAIL SENDING =====
    EMAIL_SEND_TIMEOUT_SECONDS: int = int(os.getenv("EMAIL_SEND_TIMEOUT_SECONDS", "30"))
    MAX_EMAIL_RETRIES: int = int(os.getenv("MAX_EMAIL_RETRIES", "3"))
    RETRY_BACKOFF_BASE_SECONDS: int = 60000
    RETRY_BACKOFF_MAX_SECONDS: int = 3600
    SMTP_ERROR_THRESHOLD: int = 10
    SMTP_ERROR_WINDOW_SECONDS: int = 300
    SMTP_CIRCUIT_BREAKER_TIMEOUT_SECONDS: int = 600
    SMTP_CONNECTION_POOL_SIZE: int = 10

    # ===== RATE LIMITING =====
    ENABLE_RATE_LIMITING: bool = os.getenv("ENABLE_RATE_LIMITING", "true").lower() == "true"
    BASE_RATE_LIMIT_PER_MINUTE: int = 10000
    MAX_RATE_LIMIT_PER_MINUTE: int = 50000
    MIN_RATE_LIMIT_PER_MINUTE: int = 10
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    ADAPTIVE_RATE_LIMITING: bool = True
    RATE_LIMIT_SUCCESS_THRESHOLD: float = 0.95
    RATE_LIMIT_FAILURE_THRESHOLD: float = 0.50
    RATE_LIMIT_MIN_SAMPLES: int = 10

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

    # ===== METRICS & MONITORING =====
    ENABLE_METRICS_COLLECTION: bool = os.getenv("ENABLE_METRICS_COLLECTION", "true").lower() == "true"
    METRICS_COLLECTION_INTERVAL_SECONDS: int = int(os.getenv("METRICS_COLLECTION_INTERVAL_SECONDS", "60"))
    METRICS_RETENTION_HOURS: int = 24
    METRICS_AGGREGATION_INTERVAL_SECONDS: int = 300
    ENABLE_RESOURCE_MONITORING: bool = os.getenv("ENABLE_RESOURCE_MONITORING", "true").lower() == "true"
    MEMORY_THRESHOLD_PERCENT: float = 85.0
    CPU_THRESHOLD_PERCENT: float = 90.0
    DISK_THRESHOLD_PERCENT: float = 90.0
    RESOURCE_CHECK_INTERVAL_SECONDS: int = 60
    MAX_MEMORY_USAGE_PERCENT: float = float(os.getenv("MAX_MEMORY_USAGE_PERCENT", "85.0"))
    MAX_DISK_USAGE_PERCENT: float = float(os.getenv("MAX_DISK_USAGE_PERCENT", "90.0"))
    MAX_CPU_USAGE_PERCENT: float = float(os.getenv("MAX_CPU_USAGE_PERCENT", "80.0"))

    # ===== HEALTH CHECK =====
    HEALTH_CHECK_ENABLED: bool = True
    HEALTH_CHECK_INTERVAL_SECONDS: int = int(os.getenv("HEALTH_CHECK_INTERVAL_SECONDS", "30"))
    HEALTH_REPORT_RETENTION_HOURS: int = 24
    DATABASE_RESPONSE_TIME_THRESHOLD: float = float(os.getenv("DATABASE_RESPONSE_TIME_THRESHOLD", "2.0"))
    HEALTH_CHECK_STRICT_MODE: bool = os.getenv("HEALTH_CHECK_STRICT_MODE", "false").lower() == "true"
    ENABLE_HEALTH_CHECK_BLOCKING: bool = os.getenv("ENABLE_HEALTH_CHECK_BLOCKING", "false").lower() == "true"
    SKIP_HEALTH_CHECKS_FOR_TESTING: bool = os.getenv("SKIP_HEALTH_CHECKS_FOR_TESTING", "false").lower() == "true"

    # ===== SUBSCRIBER PROCESSING =====
    SUBSCRIBER_PROCESSING_TIMEOUT: int = int(os.getenv("SUBSCRIBER_PROCESSING_TIMEOUT", "300"))
    MAX_RECORDS_PER_OPERATION: int = int(os.getenv("MAX_RECORDS_PER_OPERATION", "50000"))
    ENABLE_BULK_OPTIMIZATIONS: bool = os.getenv("ENABLE_BULK_OPTIMIZATIONS", "true").lower() == "true"
    SUBSCRIBER_IMPORT_CHUNK_SIZE: int = 1000
    DUPLICATE_CHECK_ENABLED: bool = True

    # ===== AUDIT & COMPLIANCE =====
    ENABLE_AUDIT_LOGGING: bool = os.getenv("ENABLE_AUDIT_LOGGING", "true").lower() == "true"
    ENABLE_COMPLIANCE_TRACKING: bool = os.getenv("ENABLE_COMPLIANCE_TRACKING", "false").lower() == "true"
    AUDIT_LOG_RETENTION_DAYS: int = int(os.getenv("AUDIT_LOG_RETENTION_DAYS", "90"))
    LOG_SENSITIVE_DATA: bool = False
    LOG_EMAIL_CONTENT: bool = False
    GDPR_COMPLIANCE_MODE: bool = True
    DATA_RETENTION_DAYS: int = 365

    # ===== TEMPLATE & CONTENT =====
    ENABLE_TEMPLATE_CACHING: bool = True
    TEMPLATE_CACHE_TTL_SECONDS: int = 3600
    MAX_TEMPLATE_SIZE_KB: int = 500
    ENABLE_CONTENT_COMPRESSION: bool = True
    TEMPLATE_VALIDATION_ENABLED: bool = True
    PERSONALIZATION_ENABLED: bool = True

    # ===== ANALYTICS =====
    ENABLE_REAL_TIME_ANALYTICS: bool = True
    ANALYTICS_AGGREGATION_INTERVAL_MINUTES: int = 5
    ANALYTICS_RETENTION_DAYS: int = 90
    TRACK_LINK_CLICKS: bool = True
    TRACK_EMAIL_OPENS: bool = True

    # ===== WEBHOOK =====
    WEBHOOK_RETRY_ATTEMPTS: int = 3
    WEBHOOK_TIMEOUT_SECONDS: int = 10
    WEBHOOK_MAX_PAYLOAD_SIZE_KB: int = 1024

    # ===== SES TASKS =====
    SES_BATCH_SIZE: int = int(os.getenv("SES_BATCH_SIZE", "200"))
    SES_CRITICAL_BATCH_SIZE: int = int(os.getenv("SES_CRITICAL_BATCH_SIZE", "50"))

    # ===== CELERY WORKER =====
    CELERY_WORKER_PREFETCH_MULTIPLIER: int = 4
    CELERY_TASK_ACKS_LATE: bool = False
    CELERY_TASK_TIME_LIMIT: int = 3600
    CELERY_TASK_SOFT_TIME_LIMIT: int = 3000

    # ===== FEATURE FLAGS =====
    ENABLE_CAMPAIGN_PAUSE_RESUME: bool = True
    ENABLE_AB_TESTING: bool = True
    ENABLE_AUTOMATION: bool = True
    ENABLE_SEGMENTATION: bool = True
    ENABLE_SUPPRESSIONS: bool = True
    PRODUCTION_SAFETY_MODE: bool = os.getenv("PRODUCTION_SAFETY_MODE", "true").lower() == "true"
    ENABLE_STRUCTURED_LOGGING: bool = True
    ENABLE_GRACEFUL_SHUTDOWN: bool = True
    ENABLE_PERFORMANCE_LOGGING: bool = os.getenv("ENABLE_PERFORMANCE_LOGGING", "true").lower() == "true"

    # ===== PROVIDER =====
    PROVIDER_HEALTH_CHECK_INTERVAL_SECONDS: int = 300


task_settings = TaskSettings()
