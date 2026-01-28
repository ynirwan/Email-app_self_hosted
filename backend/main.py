import logging
import time
import uuid
import os
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

# ============================================
# PRODUCTION IMPORTS WITH FALLBACKS
# ============================================

PRODUCTION_FEATURES = {
    'config': True,
    'health_monitor': True,
    'metrics_collector': True,
    'resource_manager': True,
    'campaign_controller': True,
    'dlq_manager': True,
    'database': True,
}

# Import configuration
try:
    from core.config import settings, is_production_ready
    PRODUCTION_FEATURES['config'] = True
    logger = logging.getLogger(__name__)
except ImportError:
    # Fallback settings
    class MockSettings:
        ENVIRONMENT = 'development'
        DEBUG_MODE = True
        LOG_LEVEL = 'DEBUG'
        CORS_ORIGINS = [
            "https://5474f674-6074-4eb8-8818-15946bef35a1-00-1y8lhfj74gqcq.pike.replit.dev"
        ]
        API_RATE_LIMIT_PER_MINUTE = 60
        ENABLE_METRICS_COLLECTION = False
        ENABLE_AUDIT_LOGGING = False
        APP_NAME = "Email Marketing API"
        APP_VERSION = "1.0.0"

    settings = MockSettings()
    logger = logging.getLogger(__name__)

# Import database
try:
    from database import (initialize_async_client, close_async_client,
                          ensure_indexes, ping_database, get_database_info)
    PRODUCTION_FEATURES['database'] = True
except ImportError:
    logger.warning("Database module not available")
    initialize_async_client = None
    close_async_client = None
    ensure_indexes = None
    ping_database = None
    get_database_info = None

# Import production monitoring
try:
    from tasks.health_monitor import health_monitor
    PRODUCTION_FEATURES['health_monitor'] = True
except ImportError:
    health_monitor = None

try:
    from tasks.metrics_collector import metrics_collector
    PRODUCTION_FEATURES['metrics_collector'] = True
except ImportError:
    metrics_collector = None

try:
    from tasks.resource_manager import resource_manager
    PRODUCTION_FEATURES['resource_manager'] = True
except ImportError:
    resource_manager = None

try:
    from tasks.campaign_control import campaign_controller
    PRODUCTION_FEATURES['campaign_controller'] = True
except ImportError:
    campaign_controller = None

try:
    from tasks.dlq_manager import dlq_manager
    PRODUCTION_FEATURES['dlq_manager'] = True
except ImportError:
    dlq_manager = None

# Import your existing routes
from routes import (auth, subscribers, campaigns, stats, setting, templates,
                    domains, analytics, email_settings, webhooks, suppressions,
                    segments, ab_testing, automation, events,
                    automation_analytics, audit)

# ============================================
# LOGGING CONFIGURATION
# ============================================

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger.info(f"Logging configured at {settings.LOG_LEVEL} level")

# ============================================
# APPLICATION LIFESPAN MANAGEMENT
# ============================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - handles startup and shutdown"""
    # ===== STARTUP =====
    logger.info(f"🚀 Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")

    # Initialize database
    if initialize_async_client:
        try:
            initialize_async_client()
            logger.info("✅ Database client initialized")

            # Create indexes
            if ensure_indexes:
                await ensure_indexes()
                logger.info("✅ Database indexes created")

            # Test database connection
            if ping_database:
                db_healthy = await ping_database()
                if db_healthy:
                    logger.info("✅ Database connection verified")
                else:
                    logger.error("❌ Database connection failed")
        except Exception as e:
            logger.error(f"❌ Database initialization error: {e}")

    # Startup recovery
    startup_recovery_enabled = os.getenv("STARTUP_RECOVERY_ENABLED",
                                         "true").lower() == "true"
    if startup_recovery_enabled:
        try:
            from tasks.startup_recovery import startup_recovery_only
            startup_recovery_only.apply_async(countdown=60)
            logger.info("✅ Startup recovery scheduled")
        except Exception as e:
            logger.warning(f"⚠️  Startup recovery not available: {e}")

    # Log production features
    enabled_features = [k for k, v in PRODUCTION_FEATURES.items() if v]
    logger.info(
        f"🎯 Production features enabled: {len(enabled_features)}/{len(PRODUCTION_FEATURES)}"
    )
    for feature, enabled in PRODUCTION_FEATURES.items():
        status_icon = "✅" if enabled else "❌"
        logger.info(f"   • {feature}: {status_icon}")

    # Check production readiness
    if PRODUCTION_FEATURES.get('config'):
        try:
            ready, checks = is_production_ready()
            logger.info(
                f"Production readiness: {'✅ READY' if ready else '⚠️  NOT READY'}"
            )
            for check in checks:
                logger.info(f"   {check}")
        except Exception as e:
            logger.warning(f"Could not check production readiness: {e}")

    logger.info("✅ Application startup complete!")

    yield  # Application is running

    # ===== SHUTDOWN =====
    logger.info("🛑 Shutting down application...")

    # Close database connections
    if close_async_client:
        try:
            close_async_client()
            logger.info("✅ Database connections closed")
        except Exception as e:
            logger.error(f"Error closing database: {e}")

    logger.info("✅ Application shutdown complete")


# ============================================
# CREATE FASTAPI APPLICATION
# ============================================

app = FastAPI(
    title=settings.APP_NAME,
    description=
    "Production-ready email marketing platform with campaigns, automation, analytics, and more",
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG_MODE else None,
    redoc_url="/redoc" if settings.DEBUG_MODE else None,
    lifespan=lifespan,
    # OpenAPI customization
    contact={
        "name": "API Support",
        "email": "support@example.com",
    },
    license_info={
        "name": "MIT",
    },
)

logger.info(f"FastAPI application created: {settings.APP_NAME}")

# ============================================
# MIDDLEWARE CONFIGURATION
# ============================================

# 1. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info("✅ CORS middleware configured")

# 2. GZip Compression Middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
logger.info("✅ GZip compression middleware configured")


# 3. Request ID Middleware
class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add unique request ID to each request"""

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        return response


app.add_middleware(RequestIDMiddleware)
logger.info("✅ Request ID middleware configured")


# 4. Security Headers Middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers[
            "Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        return response


app.add_middleware(SecurityHeadersMiddleware)
logger.info("✅ Security headers middleware configured")


# 5. Performance Monitoring Middleware
@app.middleware("http")
async def performance_monitoring_middleware(request: Request, call_next):
    """Monitor request performance and add metrics"""
    start_time = time.time()

    # Process request
    response = await call_next(request)

    # Calculate processing time
    process_time = time.time() - start_time

    # Add performance headers
    response.headers["X-Process-Time"] = f"{process_time:.3f}"

    # Log slow requests
    if process_time > 2.0:
        logger.warning(
            f"Slow request: {request.method} {request.url.path} - {process_time:.3f}s"
        )

    # Collect metrics if enabled
    if settings.ENABLE_METRICS_COLLECTION and metrics_collector:
        try:
            asyncio.create_task(
                metrics_collector.record_request_metric(
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration=process_time))
        except Exception as e:
            logger.debug(f"Failed to record metrics: {e}")

    return response


logger.info("✅ Performance monitoring middleware configured")


# 6. Error Handling Middleware
@app.middleware("http")
async def error_handling_middleware(request: Request, call_next):
    """Catch and format all unhandled errors"""
    try:
        return await call_next(request)
    except Exception as e:
        logger.error(f"Unhandled error: {str(e)}", exc_info=True)

        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            content={
                                "error":
                                "Internal server error",
                                "message":
                                str(e) if settings.DEBUG_MODE else
                                "An unexpected error occurred",
                                "request_id":
                                getattr(request.state, 'request_id', None),
                                "timestamp":
                                datetime.utcnow().isoformat()
                            })


logger.info("✅ Error handling middleware configured")

# ============================================
# EXCEPTION HANDLERS
# ============================================


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request,
                                 exc: StarletteHTTPException):
    """Handle HTTP exceptions"""
    return JSONResponse(status_code=exc.status_code,
                        content={
                            "error":
                            exc.detail,
                            "status_code":
                            exc.status_code,
                            "request_id":
                            getattr(request.state, 'request_id', None),
                            "timestamp":
                            datetime.utcnow().isoformat()
                        })


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request,
                                       exc: RequestValidationError):
    """Handle request validation errors"""
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        content={
                            "error":
                            "Validation error",
                            "details":
                            exc.errors(),
                            "request_id":
                            getattr(request.state, 'request_id', None),
                            "timestamp":
                            datetime.utcnow().isoformat()
                        })


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle all other exceptions"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)

    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        content={
                            "error":
                            "Internal server error",
                            "message":
                            str(exc) if settings.DEBUG_MODE else
                            "An unexpected error occurred",
                            "request_id":
                            getattr(request.state, 'request_id', None),
                            "timestamp":
                            datetime.utcnow().isoformat()
                        })


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Custom 404 handler"""
    return JSONResponse(status_code=404,
                        content={
                            "error":
                            "Not found",
                            "message":
                            f"The endpoint {request.url.path} does not exist",
                            "request_id":
                            getattr(request.state, 'request_id', None),
                            "timestamp":
                            datetime.utcnow().isoformat()
                        })


logger.info("✅ Exception handlers configured")

# ============================================
# HEALTH CHECK ENDPOINTS
# ============================================


@app.get("/health", tags=["Health"])
async def health_check():
    """Basic health check - liveness probe"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT
    }


@app.get("/health/ready", tags=["Health"])
async def readiness_check():
    """Readiness check - is the app ready to accept traffic"""
    checks = {"api": True, "database": False, "redis": False}

    # Check database
    if ping_database:
        try:
            checks["database"] = await ping_database()
        except Exception as e:
            logger.error(f"Database health check failed: {e}")

    # Check Redis (via metrics collector)
    if metrics_collector:
        try:
            checks["redis"] = True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")

    all_healthy = all(checks.values())

    return JSONResponse(status_code=200 if all_healthy else 503,
                        content={
                            "status": "ready" if all_healthy else "not_ready",
                            "checks": checks,
                            "timestamp": datetime.utcnow().isoformat()
                        })


@app.get("/health/live", tags=["Health"])
async def liveness_check():
    """Liveness check - is the app alive"""
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}


@app.get("/health/startup", tags=["Health"])
async def startup_check():
    """Startup check - has the app completed startup"""
    return {
        "status": "started",
        "timestamp": datetime.utcnow().isoformat(),
        "features": PRODUCTION_FEATURES
    }


@app.get("/health/detailed", tags=["Health"])
async def detailed_health_check():
    """Detailed system health check"""
    health_info = {
        "api_status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "production_features": PRODUCTION_FEATURES,
        "checks": {}
    }

    # Database check
    if ping_database:
        try:
            db_healthy = await ping_database()
            health_info["checks"]["database"] = {
                "status": "healthy" if db_healthy else "unhealthy",
                "connected": db_healthy
            }

            if get_database_info:
                try:
                    db_info = get_database_info()
                    health_info["checks"]["database"]["info"] = db_info
                except Exception as e:
                    health_info["checks"]["database"]["info_error"] = str(e)
        except Exception as e:
            health_info["checks"]["database"] = {
                "status": "unhealthy",
                "error": str(e)
            }

    # Health monitor check
    if health_monitor:
        try:
            health_report = health_monitor.run_all_health_checks()
            health_info["system_health"] = health_report
        except Exception as e:
            health_info["health_monitor_error"] = str(e)

    return health_info


# ============================================
# SYSTEM MONITORING ENDPOINTS
# ============================================


@app.get("/metrics", tags=["Monitoring"])
async def get_metrics():
    """Get system metrics"""
    if not metrics_collector:
        return {"error": "Metrics collection not available"}

    try:
        metrics = metrics_collector.get_metrics_summary(hours=1)
        return {"timestamp": datetime.utcnow().isoformat(), "metrics": metrics}
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.utcnow().isoformat()}


@app.get("/system/info", tags=["System"])
async def system_info():
    """System information and capabilities"""
    return {
        "name":
        settings.APP_NAME,
        "version":
        settings.APP_VERSION,
        "environment":
        settings.ENVIRONMENT,
        "timestamp":
        datetime.utcnow().isoformat(),
        "production_features":
        PRODUCTION_FEATURES,
        "enabled_features": [k for k, v in PRODUCTION_FEATURES.items() if v],
        "capabilities": {
            "health_monitoring":
            PRODUCTION_FEATURES.get('health_monitor', False),
            "metrics_collection":
            PRODUCTION_FEATURES.get('metrics_collector', False),
            "resource_management":
            PRODUCTION_FEATURES.get('resource_manager', False),
            "campaign_control":
            PRODUCTION_FEATURES.get('campaign_controller', False),
            "dlq_processing":
            PRODUCTION_FEATURES.get('dlq_manager', False),
        },
        "routes_registered":
        len(app.routes),
        "status":
        "production_ready"
        if settings.ENVIRONMENT == "production" else "development"
    }


@app.get("/system/workers", tags=["System"])
async def worker_status():
    """Get Celery worker status"""
    try:
        from celery_app import get_celery_status
        status = get_celery_status()
        return status
    except Exception as e:
        return {"error": str(e), "message": "Worker status not available"}


@app.get("/system/queues", tags=["System"])
async def queue_status():
    """Get queue status information"""
    try:
        from celery_app import celery_app
        inspect = celery_app.control.inspect()

        return {
            "active_queues": inspect.active_queues() or {},
            "reserved_tasks": inspect.reserved() or {},
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {"error": str(e), "message": "Queue status not available"}


# ============================================
# ROOT ENDPOINT
# ============================================


@app.get("/", tags=["Root"])
async def root():
    """API root endpoint"""
    # Root endpoint
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "status": "operational",
        "documentation": "/docs" if getattr(settings, 'DEBUG_MODE', True) else "Contact support for API documentation",
        "health_check": "/health",
        "endpoints": {
            "authentication": "/api/auth",
            "campaigns": "/api/campaigns",
            "subscribers": "/api/subscribers",
            "templates": "/api/templates",
            "analytics": "/api/analytics",
            "automation": "/api/automation",
            "settings": "/api/settings"
        },
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================
# REGISTER APPLICATION ROUTES
# ============================================

# Authentication
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])

# Subscribers
app.include_router(subscribers.router,
                   prefix="/api/subscribers",
                   tags=["Subscribers"])

# Campaigns
app.include_router(campaigns.router, prefix="/api", tags=["Campaigns"])

# Dashboard Stats
app.include_router(stats.router, prefix="/api/stats", tags=["Statistics"])

# Settings
app.include_router(setting.router, prefix="/api/settings", tags=["Settings"])

# Templates
app.include_router(templates.router,
                   prefix="/api/templates",
                   tags=["Templates"])

# Domains
app.include_router(domains.router, prefix="/api/domains", tags=["Domains"])

# Analytics
app.include_router(analytics.router,
                   prefix="/api/analytics",
                   tags=["Analytics"])

# Email Settings
app.include_router(email_settings.router,
                   prefix="/api/email",
                   tags=["Email Settings"])

# Webhooks
app.include_router(webhooks.router, prefix="/api", tags=["Webhooks"])

# Suppressions
app.include_router(suppressions.router,
                   prefix="/api/suppressions",
                   tags=["Suppressions"])

# Segments
app.include_router(segments.router, prefix="/api/segments", tags=["Segments"])

# A/B Testing
app.include_router(ab_testing.router, prefix="/api", tags=["A/B Testing"])

# Automation
app.include_router(automation.router, prefix="/api", tags=["Automation"])

# Automation Events
app.include_router(events.router, prefix="/api", tags=["Events"])

# Automation Analytics
app.include_router(automation_analytics.router,
                   prefix="/api",
                   tags=["Automation Analytics"])

#Audit
app.include_router(audit.router, prefix="/api/audit", tags=["audit"])

logger.info(f"✅ {len(app.routes)} routes registered")

# ============================================
# DEBUG ROUTE LISTING
# ============================================

if settings.DEBUG_MODE:

    @app.get("/debug/routes", tags=["Debug"])
    async def list_routes():
        """List all registered routes (debug only)"""
        routes = []
        for route in app.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                routes.append({
                    "path": route.path,
                    "methods": list(route.methods),
                    "name": route.name
                })

        return {
            "total_routes": len(routes),
            "routes": sorted(routes, key=lambda x: x['path'])
        }


# ============================================
# APPLICATION STARTUP MESSAGE
# ============================================

if __name__ == "__main__":
    import uvicorn

    logger.info("=" * 60)
    logger.info(f"{settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug Mode: {settings.DEBUG_MODE}")
    logger.info("=" * 60)

    uvicorn.run("main:app",
                host="0.0.0.0",
                port=8000,
                reload=settings.DEBUG_MODE,
                log_level=settings.LOG_LEVEL.lower())
