# backend/routes/email_settings.py
from fastapi import APIRouter, HTTPException, Request
from models.email_models import HostedEmailSettings, SMTPTestSettings
from core.deployment_manager import DeploymentMode
from core.security import encrypt_password, decrypt_password 
from database import get_settings_collection, get_usage_collection, get_audit_collection
from datetime import datetime
from cryptography.fernet import Fernet
import smtplib
import os

router = APIRouter()


ENCRYPTION_KEY = os.getenv("MASTER_ENCRYPTION_KEY")
print(f"🔍 DEBUG: ENCRYPTION_KEY value: '{ENCRYPTION_KEY}'")
print(f"🔍 DEBUG: ENCRYPTION_KEY type: {type(ENCRYPTION_KEY)}")
print(f"🔍 DEBUG: ENCRYPTION_KEY length: {len(ENCRYPTION_KEY) if ENCRYPTION_KEY else 'None'}")


# Make sure you have a consistent key in env
#ENCRYPTION_KEY = os.getenv("MASTER_ENCRYPTION_KEY")
fernet = Fernet(ENCRYPTION_KEY)

def encrypt_password(password: str) -> str:
    return fernet.encrypt(password.encode()).decode()

def decrypt_password(token: str) -> str:
    return fernet.decrypt(token.encode()).decode()


class QuotaManager:
    def __init__(self):
        self.deployment_mode = DeploymentMode.HOSTED_SERVICE
        # Daily limit set from environment variable (subscription-dependent)
        self.daily_limit = int(os.getenv("EMAIL_DAILY_LIMIT", "1000"))
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
    try:
        audit_collection = get_audit_collection()
        settings_collection = get_settings_collection()
        body = await request.json()

        smtp_server = body.get("smtp_server")
        smtp_port = body.get("smtp_port", 587)
        username = body.get("username")
        password = body.get("password")

        if not all([smtp_server, username, password]):
            raise HTTPException(status_code=400, detail="Missing required SMTP settings")

        # Handle case where frontend sends "********" for unchanged password
        if password == "********":
            settings = await settings_collection.find_one({"type": "email_smtp"})
            if not settings or not settings.get("config", {}).get("password"):
                raise HTTPException(status_code=400, detail="No stored password available for testing")
            from core.security import decrypt_password
            password = decrypt_password(settings["config"]["password"])

        # Attempt SMTP connection
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
        server.starttls()
        server.login(username.strip(), password.strip())
        server.quit()

        print(f"✅ SMTP connection successful to {smtp_server}:{smtp_port} as {username}")  # CLI log

        # Audit log
        await audit_collection.insert_one({
            "action": "smtp_connection_test",
            "status": "success",
            "smtp_server": smtp_server,
            "smtp_port": smtp_port,
            "timestamp": datetime.utcnow()
        })

        return {"status": "success", "message": "✅ SMTP connection successful!"}

    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ Authentication failed for {smtp_server}:{smtp_port} - {e}")  # CLI log
        await audit_collection.insert_one({
            "action": "smtp_connection_test",
            "status": "auth_failed",
            "error": str(e),
            "timestamp": datetime.utcnow()
        })
        raise HTTPException(status_code=401, detail="❌ Authentication failed - check username/password")

    except smtplib.SMTPConnectError as e:
        print(f"❌ Connection failed to {smtp_server}:{smtp_port} - {e}")  # CLI log
        await audit_collection.insert_one({
            "action": "smtp_connection_test",
            "status": "connection_failed",
            "error": str(e),
            "timestamp": datetime.utcnow()
        })
        raise HTTPException(status_code=502, detail="❌ Could not connect to SMTP server - check host/port")

    except Exception as e:
        print(f"❌ SMTP test error for {smtp_server}:{smtp_port} - {e}")  # CLI log
        await audit_collection.insert_one({
            "action": "smtp_connection_test",
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow()
        })
        raise HTTPException(status_code=500, detail=f"❌ Connection test failed: {str(e)}")




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

