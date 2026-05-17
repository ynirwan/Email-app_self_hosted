# backend/routes/email_settings.py
import logging
from fastapi import APIRouter, HTTPException, Request
from models.email_models import HostedEmailSettings, SMTPTestSettings
from core.config import settings
from core.deployment_manager import DeploymentMode
from core.security import encrypt_password, decrypt_password 
from database import get_settings_collection, get_usage_collection, get_audit_collection
from datetime import datetime
from cryptography.fernet import Fernet
import smtplib

logger = logging.getLogger(__name__)
router = APIRouter()


ENCRYPTION_KEY = settings.MASTER_ENCRYPTION_KEY
try:
    fernet = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)
except Exception as e:
    logger.error(f"Failed to initialize Fernet in email_settings: {e}")
    fernet = None

def encrypt_password(password: str) -> str:
    if not fernet:
        return password
    return fernet.encrypt(password.encode()).decode()

def decrypt_password(token: str) -> str:
    if not fernet:
        return token
    return fernet.decrypt(token.encode()).decode()


class QuotaManager:
    def __init__(self):
        self.deployment_mode = DeploymentMode.HOSTED_SERVICE
        self.daily_limit = 1000
        self.current_usage = 0

    async def get_system_quota(self):
        usage_collection = get_usage_collection()
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        usage_record = await usage_collection.find_one({"date": today_str})
        self.current_usage = usage_record["emails_sent"] if usage_record else 0

        quota_info = {
            "current_usage": self.current_usage,
            "daily_limit": self.daily_limit
        }
        return quota_info

    async def can_send_email(self):
        # Reporting only; no sending enforcement
        return {"can_send": True, "reason": "Quota usage reporting only"}

@router.get("/system-info")
async def get_email_system_info():
    try:
        quota_manager = QuotaManager()
        return {
            "deployment_mode": "hosted_service",
            "quota_enabled": True,
            "smtp_control": "managed_limits",
            "daily_limit": quota_manager.daily_limit,
            "features": {
                "managed_quotas": True,
                "billing_integration": True,
                "multiple_smtp_options": True
            },
            "smtp_options": {
                "managed": {
                    "name": "Premium Managed SMTP",
                    "features": [
                        "99.9% uptime guarantee",
                        "High deliverability",
                        "No configuration required",
                        "24/7 monitoring",
                        "Built-in analytics"
                    ],
                    "configuration_access": False
                },
                "client": {
                    "name": "Your SMTP Provider",
                    "features": [
                        "Full control",
                        "Use existing setup",
                        "Connection testing",
                        "All major providers supported"
                    ],
                    "configuration_access": True,
                    "supported_providers": ["SendGrid", "Mailgun", "Amazon SES", "Postmark", "Custom SMTP"]
                }
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get system info: {str(e)}")

@router.get("/settings")
async def get_email_settings():
    try:
        settings_collection = get_settings_collection()
        quota_manager = QuotaManager()

        settings = await settings_collection.find_one({"type": "email_smtp"})
        if not settings:
            return {
                "deployment_mode": "hosted_service",
                "smtp_choice": "managed",
                "configured": False,
                "daily_limit": quota_manager.daily_limit,
                "bounce_forward_email": "",
                "quota_info": await quota_manager.get_system_quota()
            }
        config = settings.get("config", {})
        if config.get("password"):
            config["password"] = "********"
        config["quota_info"] = await quota_manager.get_system_quota()
        config["deployment_mode"] = "hosted_service"
        config["configured"] = True
        return config
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get settings: {str(e)}")

@router.put("/settings")
async def update_email_settings(request: Request):
    try:
        settings_collection = get_settings_collection()
        audit_collection = get_audit_collection()
        quota_manager = QuotaManager()

        body = await request.json()

        config_to_store = {
            "smtp_choice": body.get("smtp_choice", "managed"),
            "daily_limit": quota_manager.daily_limit,  # enforce plan daily limit from env
            "bounce_forward_email": body.get("bounce_forward_email", ""),
            "deployment_mode": "hosted_service",
            "updated_at": datetime.utcnow()
        }
        if body.get("smtp_choice") == "client":
            config_to_store.update({
                "provider": body.get("provider", ""),
                "smtp_server": body.get("smtp_server", ""),
                "smtp_port": body.get("smtp_port", 587),
                "username": body.get("username", ""),
                "password": encrypt_password(body.get("password", "")),
                "managed_by_system": False
            })
        else:
            config_to_store.update({
                "provider": "managed_service",
                "managed_by_system": True
            })

        result = await settings_collection.update_one(
            {"type": "email_smtp"},
            {"$set": {
                "type": "email_smtp",
                "config": config_to_store
             }},
            upsert=True
        )

        await audit_collection.insert_one({
            "action": "email_settings_updated",
            "deployment_mode": "hosted_service",
            "provider": config_to_store.get("provider"),
            "timestamp": datetime.utcnow()
        })

        response = {
            "message": "Email settings updated successfully",
            "deployment_mode": "hosted_service",
            "modified_count": result.modified_count,
            "upserted_id": str(result.upserted_id) if result.upserted_id else None,
            "quota_info": await quota_manager.get_system_quota()
        }
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {str(e)}")


@router.post("/test-connection")
async def test_smtp_connection(request: Request):
    """
    Test SMTP credentials before or after saving.

    Password handling:
      - If frontend sends the real plaintext (new/changed password, pre-save):
        use it directly.
      - If frontend sends "********" (masked, post-load, unchanged):
        fetch the stored encrypted value and decrypt with the module-level
        fernet — the SAME instance used when saving — so encrypt/decrypt
        always use the same key and algorithm.
      - If decryption yields an empty string: fail loudly with a clear error
        rather than sending a blank password that causes "504 Invalid AUTH
        string" from the SMTP server.
    """
    # Initialise variables used in except blocks so they are always in scope
    smtp_server = None
    smtp_port = None
    audit_collection = None

    try:
        audit_collection = get_audit_collection()
        settings_collection = get_settings_collection()
        body = await request.json()

        smtp_server = body.get("smtp_server", "").strip()
        smtp_port   = int(body.get("smtp_port") or 587)
        username    = (body.get("username") or "").strip()
        password    = body.get("password") or ""

        # ── 1. Basic field validation ─────────────────────────────────────────
        missing = [f for f, v in [
            ("smtp_server", smtp_server),
            ("username",    username),
            ("password",    password),
        ] if not v]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required fields: {', '.join(missing)}",
            )

        # ── 2. Resolve password ───────────────────────────────────────────────
        password_source = "plaintext"   # for audit log

        if password == "********":
            # Frontend sent the masked sentinel — fetch from DB and decrypt
            stored_doc = await settings_collection.find_one({"type": "email_smtp"})
            encrypted  = (stored_doc or {}).get("config", {}).get("password", "")

            if not encrypted:
                logger.warning(
                    "SMTP test requested with masked password but no stored "
                    "record found — user must save settings first."
                )
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "No stored password found. "
                        "Please save your settings first, or re-enter the password."
                    ),
                )

            # Plaintext guard: if somehow stored un-encrypted, use as-is
            if not encrypted.startswith("gAAAAA"):
                logger.warning(
                    "Stored SMTP password does not appear to be Fernet-encrypted "
                    "(missing gAAAAA prefix). Using as-is — re-save settings to encrypt."
                )
                password        = encrypted
                password_source = "stored_plaintext"
            else:
                if not fernet:
                    logger.error(
                        "Module-level fernet is None — MASTER_ENCRYPTION_KEY "
                        "may be missing or invalid."
                    )
                    raise HTTPException(
                        status_code=500,
                        detail=(
                            "Encryption is not initialised on the server. "
                            "Check MASTER_ENCRYPTION_KEY configuration."
                        ),
                    )
                try:
                    password        = fernet.decrypt(encrypted.encode()).decode()
                    password_source = "stored_encrypted"
                except Exception as dec_err:
                    logger.error(
                        "Fernet decryption failed for stored SMTP password. "
                        "MASTER_ENCRYPTION_KEY may have rotated since last save. "
                        f"Error: {dec_err}"
                    )
                    await audit_collection.insert_one({
                        "action":      "smtp_connection_test",
                        "status":      "decryption_failed",
                        "smtp_server": smtp_server,
                        "smtp_port":   smtp_port,
                        "username":    username,
                        "error":       f"Fernet decryption error: {dec_err}",
                        "timestamp":   datetime.utcnow(),
                    })
                    raise HTTPException(
                        status_code=500,
                        detail=(
                            "Could not decrypt the stored SMTP password. "
                            "The encryption key may have changed — please re-enter "
                            "and re-save your password."
                        ),
                    )

        # ── 3. Empty-password guard ───────────────────────────────────────────
        #  Sending an empty password to smtplib produces "504 Invalid AUTH
        #  string" from the server — a confusing error.  Fail loudly here.
        if not password.strip():
            logger.error(
                f"SMTP test aborted — resolved password is empty "
                f"(source={password_source}, server={smtp_server}:{smtp_port}, "
                f"user={username!r})"
            )
            await audit_collection.insert_one({
                "action":          "smtp_connection_test",
                "status":          "empty_password",
                "smtp_server":     smtp_server,
                "smtp_port":       smtp_port,
                "username":        username,
                "password_source": password_source,
                "error":           "Password resolved to empty string",
                "timestamp":       datetime.utcnow(),
            })
            raise HTTPException(
                status_code=400,
                detail=(
                    "Password is empty after processing. "
                    "Please re-enter your SMTP password."
                ),
            )

        # ── 4. SMTP connection attempt ────────────────────────────────────────
        logger.info(
            f"Testing SMTP connection: server={smtp_server}:{smtp_port} "
            f"user={username!r} password_source={password_source} "
            f"pass_len={len(password)}"
        )

        server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
        server.starttls()
        server.login(username, password.strip())
        server.quit()

        # ── 5. Success ────────────────────────────────────────────────────────
        logger.info(
            f"✅ SMTP test succeeded: {smtp_server}:{smtp_port} user={username!r}"
        )
        await audit_collection.insert_one({
            "action":          "smtp_connection_test",
            "status":          "success",
            "smtp_server":     smtp_server,
            "smtp_port":       smtp_port,
            "username":        username,
            "password_source": password_source,
            "timestamp":       datetime.utcnow(),
        })

        return {"status": "success", "message": "✅ SMTP connection successful!"}

    # ── 6. Auth failure ───────────────────────────────────────────────────────
    except smtplib.SMTPAuthenticationError as e:
        logger.warning(
            f"❌ SMTP auth failed: server={smtp_server}:{smtp_port} "
            f"user={username!r} smtp_code={e.smtp_code} smtp_error={e.smtp_error!r}"
        )
        if audit_collection is not None:
            await audit_collection.insert_one({
                "action":      "smtp_connection_test",
                "status":      "auth_failed",
                "smtp_server": smtp_server,
                "smtp_port":   smtp_port,
                "username":    username,
                "smtp_code":   e.smtp_code,
                "error":       str(e),
                "timestamp":   datetime.utcnow(),
            })
        raise HTTPException(
            status_code=401,
            detail=(
                f"❌ Authentication failed (SMTP {e.smtp_code}): "
                "check your username and password."
            ),
        )

    # ── 7. Connection / network failure ──────────────────────────────────────
    except smtplib.SMTPConnectError as e:
        logger.warning(
            f"❌ SMTP connect failed: server={smtp_server}:{smtp_port} error={e}"
        )
        if audit_collection is not None:
            await audit_collection.insert_one({
                "action":      "smtp_connection_test",
                "status":      "connection_failed",
                "smtp_server": smtp_server,
                "smtp_port":   smtp_port,
                "username":    username,
                "error":       str(e),
                "timestamp":   datetime.utcnow(),
            })
        raise HTTPException(
            status_code=502,
            detail="❌ Could not connect to the SMTP server — check host and port.",
        )

    # ── 8. STARTTLS failure ───────────────────────────────────────────────────
    except smtplib.SMTPNotSupportedError as e:
        logger.warning(
            f"❌ STARTTLS not supported: server={smtp_server}:{smtp_port} error={e}"
        )
        if audit_collection is not None:
            await audit_collection.insert_one({
                "action":      "smtp_connection_test",
                "status":      "starttls_not_supported",
                "smtp_server": smtp_server,
                "smtp_port":   smtp_port,
                "username":    username,
                "error":       str(e),
                "timestamp":   datetime.utcnow(),
            })
        raise HTTPException(
            status_code=502,
            detail=(
                "❌ STARTTLS is not supported on this server/port combination. "
                "Try port 465 (SSL) or 587 (STARTTLS)."
            ),
        )

    # ── 9. Timeout ────────────────────────────────────────────────────────────
    except TimeoutError as e:
        logger.warning(
            f"❌ SMTP timeout: server={smtp_server}:{smtp_port} error={e}"
        )
        if audit_collection is not None:
            await audit_collection.insert_one({
                "action":      "smtp_connection_test",
                "status":      "timeout",
                "smtp_server": smtp_server,
                "smtp_port":   smtp_port,
                "username":    username,
                "error":       str(e),
                "timestamp":   datetime.utcnow(),
            })
        raise HTTPException(
            status_code=504,
            detail="❌ Connection timed out — the server did not respond in 10 seconds.",
        )

    # ── 10. HTTPException passthrough (our own raises above) ─────────────────
    except HTTPException:
        raise

    # ── 11. Catch-all ─────────────────────────────────────────────────────────
    except Exception as e:
        logger.exception(
            f"❌ Unexpected SMTP test error: server={smtp_server}:{smtp_port} "
            f"user={username!r} error={e}"
        )
        if audit_collection is not None:
            await audit_collection.insert_one({
                "action":      "smtp_connection_test",
                "status":      "error",
                "smtp_server": smtp_server,
                "smtp_port":   smtp_port,
                "username":    username,
                "error":       str(e),
                "timestamp":   datetime.utcnow(),
            })
        raise HTTPException(
            status_code=500,
            detail=f"❌ Unexpected error during connection test: {e}",
        )


@router.get("/usage")
async def get_email_usage():
    try:
        quota_manager = QuotaManager()
        quota_info = await quota_manager.get_system_quota()
        now = datetime.utcnow()
        return {
            "deployment_mode": "hosted_service",
            "current_date": now.strftime("%Y-%m-%d"),
            "quota": quota_info
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get usage: {str(e)}")

