import logging
import time
import uuid
import os
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import FastAPI, Request, HTTPException, status, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from core.rate_limit import limiter

# ============================================
# GLOBAL UTC DATETIME FIX
# ============================================
# FastAPI's default jsonable_encoder calls datetime.isoformat() which produces
# strings WITHOUT a timezone marker, e.g. "2026-05-08T09:00:00".
# JavaScript's new Date() treats such strings as LOCAL time, so IST users
# (UTC+5:30) see all timestamps shifted by -5:30h.
# Patching ENCODERS_BY_TYPE here fixes this app-wide: every route that returns
# a dict containing a naive UTC datetime will now emit "...Z" instead.
from fastapi import encoders as _fe
_fe.ENCODERS_BY_TYPE[datetime] = lambda dt: (
    dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    if dt.tzinfo is None
    else dt.isoformat()
)

# ============================================
# PRODUCTION IMPORTS WITH FALLBACKS
# ============================================

PRODUCTION_FEATURES = {
    "config": True,
    "health_monitor": True,
    "metrics_collector": True,
    "resource_manager": True,
    "campaign_controller": True,
    "dlq_manager": True,
    "database": True,
}

from core.config import settings, is_production_ready
from core.license import get_license, reload_license

PRODUCTION_FEATURES["config"] = True
logger = logging.getLogger(__name__)

try:
    from tasks.task_config import task_settings

    _metrics_enabled = task_settings.ENABLE_METRICS_COLLECTION
except ImportError:
    _metrics_enabled = False

# Import database
try:
    from database import (
        initialize_async_client,
        close_async_client,
        ensure_indexes,
        ping_database,
        get_database_info,
    )

    PRODUCTION_FEATURES["database"] = True
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

    PRODUCTION_FEATURES["health_monitor"] = True
except ImportError:
    health_monitor = None

try:
    from tasks.metrics_collector import metrics_collector

    PRODUCTION_FEATURES["metrics_collector"] = True
except ImportError:
    metrics_collector = None

try:
    from tasks.resource_manager import resource_manager

    PRODUCTION_FEATURES["resource_manager"] = True
except ImportError:
    resource_manager = None

try:
    from tasks.campaign_control import campaign_controller

    PRODUCTION_FEATURES["campaign_controller"] = True
except ImportError:
    campaign_controller = None

try:
    from tasks.dlq_manager import dlq_manager

    PRODUCTION_FEATURES["dlq_manager"] = True
except ImportError:
    dlq_manager = None

# Import your existing routes
from core.auth import get_current_user
from core.license import license_feature
from fastapi import Depends
from routes import (
    auth,
    subscribers,
    campaigns,
    stats,
    templates,
    setting,
    domains,
    analytics,
    email_settings,
    webhooks,
    suppressions,
    segments,
    ab_testing,
    ab_winner_analytics,
    automation,
    automation_advanced,
    events,
    automation_analytics,
    audit,
    unsubscribe,
    tracking,
    test_email,
    public_optin,
    deliverability,
)

# ============================================
# LOGGING CONFIGURATION
# ============================================

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "var", "log")
os.makedirs(LOG_DIR, exist_ok=True)

from logging.handlers import RotatingFileHandler

log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
access_log_format = "%(asctime)s - %(message)s"
log_level = getattr(logging, settings.LOG_LEVEL, logging.INFO)


def _setup_file_logging():
    root_logger = logging.getLogger()
    if any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers):
        return
    root_logger.setLevel(log_level)

    formatter = logging.Formatter(log_format)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    app_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "app.log"), maxBytes=10 * 1024 * 1024, backupCount=5
    )
    app_handler.setLevel(log_level)
    app_handler.setFormatter(formatter)
    root_logger.addHandler(app_handler)

    error_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "error.log"), maxBytes=10 * 1024 * 1024, backupCount=5
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)

    access_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "access.log"), maxBytes=10 * 1024 * 1024, backupCount=5
    )
    access_handler.setLevel(logging.INFO)
    access_handler.setFormatter(logging.Formatter(access_log_format))

    for uvi_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvi_logger = logging.getLogger(uvi_name)
        uvi_logger.handlers = []
        uvi_logger.propagate = True
    logging.getLogger("uvicorn.access").addHandler(access_handler)

    for mod_name in (
        "routes",
        "tasks",
        "database",
        "core",
        "celery",
        "motor",
        "pymongo",
        "fastapi",
        "httpx",
        "aiohttp",
    ):
        logging.getLogger(mod_name).setLevel(log_level)


_setup_file_logging()
logger.info(f"Logging configured at {settings.LOG_LEVEL} level")
logger.info(f"Log files: {LOG_DIR}/app.log, error.log, access.log")

# ============================================
# APPLICATION LIFESPAN MANAGEMENT
# ============================================


async def _register_install_startup(lic) -> None:
    """
    Register this instance with the ZeniPost Dashboard on startup.

    Posts to the dashboard's /api/licenses/register-install endpoint so the
    dashboard can track unique running instances per license and enforce
    per-plan seat limits.  Failures are logged at WARNING level and never
    propagate — the app must start regardless of dashboard reachability.
    """
    import json
    import httpx
    import socket as _socket

    from core.installation import get_installation_id
    from core.license import _find_license_file

    ping_url: str = getattr(lic, "ping_url", "") or ""
    if not ping_url:
        logger.debug("Skipping startup install registration — no ping_url in license.")
        return

    # Derive register-install URL from ping URL
    # e.g. https://dashboard.zenipost.com/api/licenses/ping
    #   →  https://dashboard.zenipost.com/api/licenses/register-install
    register_url = ping_url.rstrip("/").rsplit("/ping", 1)[0] + "/register-install"

    # Read the raw signature from license.json
    license_path = _find_license_file()
    if license_path is None:
        logger.warning("Startup install registration: license.json not found.")
        return

    try:
        raw = json.loads(license_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Startup install registration: could not read license.json: %s", exc)
        return

    signature = raw.get("signature", "")
    if not signature:
        logger.warning("Startup install registration: no signature in license.json.")
        return

    installation_id = get_installation_id()

    # Best-effort server IP detection
    server_ip = ""
    try:
        with _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM) as _s:
            _s.connect(("8.8.8.8", 80))
            server_ip = _s.getsockname()[0]
    except Exception:
        pass

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            register_url,
            json={
                "domain":          lic.domain,
                "signature":       signature,
                "server_ip":       server_ip,
                "installation_id": installation_id,
            },
        )

    if resp.status_code == 200:
        data = resp.json()
        logger.info(
            "✅ Installation registered with dashboard — %s (seats %s/%s)",
            data.get("message", "ok"),
            data.get("seats_used", "?"),
            data.get("seats_limit", "?"),
        )
    elif resp.status_code == 403:
        data = resp.json()
        code = data.get("code", "")
        if code == "INSTALL_LIMIT_REACHED":
            logger.critical(
                "🚫 Installation seat limit reached for this license. "
                "This instance is not authorised. "
                "Upgrade your license or remove another installation via the ZeniPost Dashboard. "
                "Details: %s", data.get("message", "")
            )
        elif code == "LICENSE_REVOKED":
            logger.critical(
                "🚫 License has been revoked — this installation is not authorised. "
                "Contact support@zenipost.com."
            )
        else:
            logger.warning("Startup install registration returned 403: %s", data)
    else:
        logger.warning(
            "Startup install registration returned HTTP %s: %s",
            resp.status_code, resp.text[:200],
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - handles startup and shutdown"""
    # ===== STARTUP =====
    logger.info(f"🚀 Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")

    # ── License check ─────────────────────────────────────────────────────
    lic = get_license()
    if lic.valid:
        days = lic.days_until_expiry()
        expiry_note = f" ({days}d until expiry)" if days is not None else ""
        logger.info(
            "✅ License valid — plan=%s domain=%s expires=%s%s",
            lic.plan, lic.domain, lic.expires_at, expiry_note,
        )
        if lic.has_managed_delivery:
            plan_name = (lic.delivery or {}).get("plan_name", "managed")
            logger.info("   Managed delivery: %s", plan_name)

        # ── Register this installation with the dashboard ──────────────────
        # Best-effort: never block startup on network failures.
        try:
            await _register_install_startup(lic)
        except Exception as _exc:
            logger.warning("Startup install registration failed (non-fatal): %s", _exc)
    else:
        logger.error("❌ License invalid: %s", lic.error)
        if settings.ENVIRONMENT == "production":
            raise RuntimeError(
                f"Cannot start in production with an invalid license: {lic.error}"
            )

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

    # Log production features
    enabled_features = [k for k, v in PRODUCTION_FEATURES.items() if v]
    logger.info(
        f"🎯 Production features enabled: {len(enabled_features)}/{len(PRODUCTION_FEATURES)}"
    )
    for feature, enabled in PRODUCTION_FEATURES.items():
        status_icon = "✅" if enabled else "❌"
        logger.info(f"   • {feature}: {status_icon}")

    # Check production readiness
    if PRODUCTION_FEATURES.get("config"):
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
    description="Production-ready email marketing platform with campaigns, automation, analytics, and more",
    version=settings.APP_VERSION,
    docs_url="/docs" if settings.DEBUG_MODE else None,
    redoc_url="/redoc" if settings.DEBUG_MODE else None,
    lifespan=lifespan,
    redirect_slashes=False,
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

# Attach the shared slowapi limiter so @limiter.limit() decorators in route
# files can find it at request time.
app.state.limiter = limiter

# ============================================
# MIDDLEWARE CONFIGURATION
# ============================================

# 1. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
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
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Content-Security-Policy — restricts what the browser executes/loads.
        # 'unsafe-inline' in style-src is required by Tailwind's inline class approach.
        # 'unsafe-inline' is intentionally absent from script-src; Vite production
        # builds emit no inline scripts. If you add third-party analytics that requires
        # a nonce/hash, extend script-src rather than adding 'unsafe-inline'.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "font-src 'self' data:; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "base-uri 'self'; "
            "object-src 'none'"
        )

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
    if _metrics_enabled and metrics_collector:
        try:
            asyncio.create_task(
                metrics_collector.record_request_metric(
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration=process_time,
                )
            )
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

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "Internal server error",
                "message": str(e)
                if settings.DEBUG_MODE
                else "An unexpected error occurred",
                "request_id": getattr(request.state, "request_id", None),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


logger.info("✅ Error handling middleware configured")

# ============================================
# EXCEPTION HANDLERS
# ============================================

# Rate-limit exceeded → 429 Too Many Requests
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "request_id": getattr(request.state, "request_id", None),
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors"""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation error",
            "details": exc.errors(),
            "request_id": getattr(request.state, "request_id", None),
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request: Request, exc: RuntimeError):
    """
    Convert license-related RuntimeErrors from require_feature() / service-layer
    guards into proper HTTP 403 responses so the frontend receives actionable JSON
    instead of a generic 500.

    Any RuntimeError whose message starts with "Feature '" or "License invalid"
    is treated as a plan-enforcement failure.  All others fall through to the
    general exception handler as a 500.
    """
    msg = str(exc)
    if msg.startswith(("Feature '", "License invalid")):
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": "Plan restriction",
                "message": msg,
                "request_id": getattr(request.state, "request_id", None),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    # Not a license error — log and return 500 as before.
    logger.error(f"Unhandled RuntimeError: {msg}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "message": msg if settings.DEBUG_MODE else "An unexpected error occurred",
            "request_id": getattr(request.state, "request_id", None),
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle all other exceptions"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "message": str(exc)
            if settings.DEBUG_MODE
            else "An unexpected error occurred",
            "request_id": getattr(request.state, "request_id", None),
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Custom 404 handler"""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not found",
            "message": f"The endpoint {request.url.path} does not exist",
            "request_id": getattr(request.state, "request_id", None),
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


logger.info("✅ Exception handlers configured")

# ============================================
# LICENSE STATUS ENDPOINT
# ============================================


@app.get("/api/license/status", tags=["License"])
async def license_status(current_user: dict = Depends(get_current_user)):
    """Return the current license summary (authenticated users only)."""
    lic = get_license()
    return {
        "valid":    lic.valid,
        "error":    lic.error or None,
        **lic.to_public_dict(),
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/api/license/reload", tags=["License"])
async def license_reload(current_user: dict = Depends(get_current_user)):
    """Force a license reload from disk (use after placing a new license file)."""
    lic = reload_license()
    return {
        "message": "License reloaded",
        "valid":   lic.valid,
        "error":   lic.error or None,
        **lic.to_public_dict(),
    }


@app.post("/api/license/upload", tags=["License"])
async def license_upload(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload a new license file (.lic or .json) while the app is running.

    The file is validated before being written to disk — if decryption or
    signature verification fails the existing license is left untouched.
    After a successful write, the in-memory license cache is refreshed
    automatically.
    """
    from core.license import (
        _find_license_file,
        _decrypt_lic_blob,
        _license_secret,
        _verify_jwt_signature,
        _verify_legacy_signature,
        _LICENSE_PATH_CANDIDATES,
    )
    import json as _json
    from pathlib import Path

    allowed_suffixes = {".lic", ".json"}
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_suffixes:
        raise HTTPException(
            status_code=400,
            detail="Only .lic or .json license files are accepted.",
        )

    content_bytes = await file.read()
    if len(content_bytes) > 512 * 1024:  # 512 KB sanity guard
        raise HTTPException(status_code=400, detail="License file is unexpectedly large.")

    content_str = content_bytes.decode("utf-8", errors="replace")

    # ── Validate before touching disk ─────────────────────────────────────
    env = os.getenv("ENVIRONMENT", "development").lower()
    is_dev = env == "development"

    try:
        if suffix == ".lic":
            raw = _decrypt_lic_blob(content_str.strip(), _license_secret())
        else:
            raw = _json.loads(content_str)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"License file could not be parsed/decrypted: {exc}",
        )

    if not is_dev:
        sig = raw.get("signature", "")
        is_v2 = raw.get("format") == "zenipost-license-v2"
        if not sig or sig == "REPLACE_WITH_ACTUAL_SIGNATURE_FROM_VENDOR":
            raise HTTPException(status_code=422, detail="License has a placeholder signature.")
        ok = _verify_jwt_signature(raw, sig) if is_v2 else _verify_legacy_signature(raw, sig)
        if not ok:
            raise HTTPException(
                status_code=422,
                detail="License signature is invalid — file may be tampered or for a different secret.",
            )

    # ── Write to the repo-root canonical path ──────────────────────────────
    # Prefer the same location as the currently loaded file if one exists;
    # otherwise write to the first candidate (repo root).
    existing = _find_license_file()
    if existing:
        target = existing.with_suffix(suffix)  # keep path, update extension if needed
    else:
        target = _LICENSE_PATH_CANDIDATES[0].parent / f"license{suffix}"

    try:
        target.write_text(content_str, encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not write license to disk: {exc}")

    # ── Reload in-memory cache ─────────────────────────────────────────────
    lic = reload_license()

    logger.info(
        "License uploaded and reloaded: plan=%s valid=%s expires=%s uploaded_by=%s",
        lic.plan,
        lic.valid,
        lic.expires_at,
        current_user.get("email", current_user.get("sub", "unknown")),
    )

    return {
        "message": "License uploaded and reloaded successfully.",
        "valid":   lic.valid,
        "error":   lic.error or None,
        **lic.to_public_dict(),
    }


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
        "environment": settings.ENVIRONMENT,
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

    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content={
            "status": "ready" if all_healthy else "not_ready",
            "checks": checks,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


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
        "features": PRODUCTION_FEATURES,
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
        "checks": {},
    }

    # Database check
    if ping_database:
        try:
            db_healthy = await ping_database()
            health_info["checks"]["database"] = {
                "status": "healthy" if db_healthy else "unhealthy",
                "connected": db_healthy,
            }

            if get_database_info:
                try:
                    db_info = get_database_info()
                    health_info["checks"]["database"]["info"] = db_info
                except Exception as e:
                    health_info["checks"]["database"]["info_error"] = str(e)
        except Exception as e:
            health_info["checks"]["database"] = {"status": "unhealthy", "error": str(e)}

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
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.utcnow().isoformat(),
        "production_features": PRODUCTION_FEATURES,
        "enabled_features": [k for k, v in PRODUCTION_FEATURES.items() if v],
        "capabilities": {
            "health_monitoring": PRODUCTION_FEATURES.get("health_monitor", False),
            "metrics_collection": PRODUCTION_FEATURES.get("metrics_collector", False),
            "resource_management": PRODUCTION_FEATURES.get("resource_manager", False),
            "campaign_control": PRODUCTION_FEATURES.get("campaign_controller", False),
            "dlq_processing": PRODUCTION_FEATURES.get("dlq_manager", False),
        },
        "routes_registered": len(app.routes),
        "status": "production_ready"
        if settings.ENVIRONMENT == "production"
        else "development",
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
            "timestamp": datetime.utcnow().isoformat(),
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
        "documentation": "/docs"
        if getattr(settings, "DEBUG_MODE", True)
        else "Contact support for API documentation",
        "health_check": "/health",
        "endpoints": {
            "authentication": "/api/auth",
            "campaigns": "/api/campaigns",
            "subscribers": "/api/subscribers",
            "templates": "/api/templates",
            "analytics": "/api/analytics",
            "automation": "/api/automation",
            "settings": "/api/settings",
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


# ============================================
# REGISTER APPLICATION ROUTES
# ============================================
# Public routes: /api/auth (login/register), /api/webhooks, /api/unsubscribe, /api/public/*
# All other routes require a valid JWT via Depends(get_current_user)

_auth_dep = [Depends(get_current_user)]

# Authentication — public (login, register, me)
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])

# Webhooks — public (called by SES/external services, no user session)
app.include_router(webhooks.router, prefix="/api", tags=["Webhooks"])

# Unsubscribe — public (clicked from email, no user session)
app.include_router(unsubscribe.router, prefix="/api", tags=["Unsubscribe"])

# Public opt-in — public (submitted from embedded form, no user session)
app.include_router(public_optin.router, prefix="/api", tags=["Public Opt-In"])

# Tracking — public (pixel/click/unsubscribe-confirm, hit directly from emails)
# Routes: GET /t/o/{token}.gif  GET /t/c/{token}  GET /t/verify/{token}  POST /t/u/{token}
app.include_router(tracking.router, prefix="", tags=["Tracking"])

# ── Protected routes ──────────────────────────────────────────────────────
app.include_router(
    templates.router,
    prefix="/api/templates",
    tags=["Templates"],
    dependencies=_auth_dep,
)

app.include_router(
    subscribers.router,
    prefix="/api/subscribers",
    tags=["Subscribers"],
    dependencies=_auth_dep,
)

app.include_router(
    stats.router, prefix="/api/stats", tags=["Statistics"], dependencies=_auth_dep
)

app.include_router(
    setting.router, prefix="/api/settings", tags=["Settings"], dependencies=_auth_dep
)

#app.include_router(
#    tracking.settings_router,
#    prefix="/api/settings",
#    tags=["Settings"],
#    dependencies=_auth_dep,
#)

app.include_router(
    domains.router, prefix="/api/domains", tags=["Domains"], dependencies=_auth_dep
)

app.include_router(
    analytics.router,
    prefix="/api/analytics",
    tags=["Analytics"],
    dependencies=_auth_dep,
)

app.include_router(
    email_settings.router,
    prefix="/api/email",
    tags=["Email Settings"],
    dependencies=_auth_dep,
)



app.include_router(
    suppressions.router,
    prefix="/api/suppressions",
    tags=["Suppressions"],
    dependencies=_auth_dep,
)

app.include_router(
    segments.router,
    prefix="/api/segments",
    tags=["Segments"],
    dependencies=_auth_dep + [Depends(license_feature("segmentation"))],
)

app.include_router(
    campaigns.router, prefix="/api", tags=["Campaigns"], dependencies=_auth_dep
)

# ── Plan-gated routes ────────────────────────────────────────────────────────
# These routers are only reachable when the license includes the matching feature.
# HTTP 403 is returned for any plan that does not include the feature.

app.include_router(
    ab_testing.router,
    prefix="/api",
    tags=["A/B Testing"],
    dependencies=_auth_dep + [Depends(license_feature("ab_testing"))],
)

app.include_router(
    ab_winner_analytics.router,
    prefix="/api",
    tags=["A/B Testing"],
    dependencies=_auth_dep + [Depends(license_feature("ab_testing"))],
)

app.include_router(
    automation.router,
    prefix="/api",
    tags=["Automation"],
    dependencies=_auth_dep + [Depends(license_feature("automation"))],
)

app.include_router(
    automation_advanced.router,
    prefix="/api",
    tags=["Automation Advanced"],
    dependencies=_auth_dep + [Depends(license_feature("automation"))],
)

app.include_router(
    events.router, prefix="/api", tags=["Events"], dependencies=_auth_dep
)

app.include_router(
    automation_analytics.router,
    prefix="/api",
    tags=["Automation Analytics"],
    dependencies=_auth_dep + [Depends(license_feature("automation"))],
)

app.include_router(
    audit.router,
    prefix="/api/audit",
    tags=["audit"],
    dependencies=_auth_dep + [Depends(license_feature("audit_trail"))],
)

app.include_router(
    deliverability.router,
    prefix="/api",
    tags=["Deliverability"],
    dependencies=_auth_dep + [Depends(license_feature("deliverability_dashboard"))],
)

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
            if hasattr(route, "path") and hasattr(route, "methods"):
                routes.append(
                    {
                        "path": route.path,
                        "methods": list(route.methods),
                        "name": route.name,
                    }
                )

        return {
            "total_routes": len(routes),
            "routes": sorted(routes, key=lambda x: x["path"]),
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

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG_MODE,
        log_level=settings.LOG_LEVEL.lower(),
    )
