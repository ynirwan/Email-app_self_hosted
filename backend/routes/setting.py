# routes/setting.py
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from pydantic import BaseModel, EmailStr, validator


from database import get_settings_collection, get_audit_collection

router = APIRouter()

class SendingLimits(BaseModel):
    per_minute: int = 100
    per_hour: int = 3600
    per_day: int = 50000

class BounceHandling(BaseModel):
    enabled: bool = True
    webhook_url: Optional[str] = None
    forward_bounces: bool = False
    forward_email: Optional[EmailStr] = None

    @validator("webhook_url", "forward_email", pre=True)
    def empty_str_to_none(cls, v):
        if v == "":
            return None
        return v

class EmailSettings(BaseModel):
    provider: str
    smtp_server: str
    smtp_port: int = 587
    username: str
    password: str
    sending_limits: SendingLimits
    bounce_handling: BounceHandling

class EmailTestSettings(BaseModel):
    smtp_server: str
    smtp_port: int
    username: str
    password: str

async def get_smtp_mode():
    """Get SMTP mode from database settings"""
    settings_collection = get_settings_collection()
    settings = await settings_collection.find_one({"type": "email"})
    if settings and settings.get("smtp_mode"):
        return settings["smtp_mode"].lower()
    if settings and settings.get("config", {}).get("smtp_choice"):
        return settings["config"]["smtp_choice"].lower()
    return "unmanaged"

async def get_managed_smtp_limits():
    """Get managed SMTP limits from database settings"""
    settings_collection = get_settings_collection()
    settings = await settings_collection.find_one({"type": "email"})
    if settings:
        config = settings.get("config", {})
        sending_limits = config.get("sending_limits", {})
        if sending_limits:
            return {
                "max_per_minute": sending_limits.get("per_minute", 500),
                "max_per_hour": sending_limits.get("per_hour", 25000),
                "max_per_day": sending_limits.get("per_day", 100000)
            }
    return {
        "max_per_minute": 500,
        "max_per_hour": 25000,
        "max_per_day": 100000
    }

async def validate_managed_smtp_limits(limits: SendingLimits):
    """Validate limits against managed SMTP constraints"""
    managed_limits = await get_managed_smtp_limits()
    
    if limits.per_minute > managed_limits["max_per_minute"]:
        raise ValueError(f"Per minute limit cannot exceed {managed_limits['max_per_minute']}")
    
    if limits.per_hour > managed_limits["max_per_hour"]:
        raise ValueError(f"Per hour limit cannot exceed {managed_limits['max_per_hour']}")
    
    if limits.per_day > managed_limits["max_per_day"]:
        raise ValueError(f"Per day limit cannot exceed {managed_limits['max_per_day']}")

@router.get("/email/system-config")
async def get_system_config():
    """Get system SMTP configuration"""
    try:
        settings_collection = get_settings_collection()
        settings = await settings_collection.find_one({"type": "email"})
        
        smtp_mode = await get_smtp_mode()
        managed_limits = await get_managed_smtp_limits()
        
        return {
            "smtp_mode": smtp_mode,
            "is_configured": settings is not None,
            "managed_limits": managed_limits
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get system config: {str(e)}")

@router.get("/email")
async def get_email_settings():
    """Get current email settings"""
    try:
        settings_collection = get_settings_collection()
        settings = await settings_collection.find_one({"type": "email"})
        smtp_mode = await get_smtp_mode()

        if not settings:
            # Return default settings based on SMTP mode
            default_provider = "internal" if smtp_mode == "managed" else ""
            
            return {
                "provider": default_provider,
                "smtp_server": "Internal" if smtp_mode == "managed" else "",
                "smtp_port": 587,
                "username": "",
                "password": "",
                "sending_limits": {
                    "per_minute": 100,
                    "per_hour": 3600,
                    "per_day": 50000
                },
                "bounce_handling": {
                    "enabled": True,
                    "webhook_url": "",
                    "forward_bounces": False,
                    "forward_email": ""
                }
            }
        
        config = settings.get("config", {})
        
        # For managed SMTP, force internal provider
        if smtp_mode == "managed" and config.get("provider") != "internal":
            config["provider"] = "internal"
            config["smtp_server"] = "Internal"
        
        return config
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch email settings: {str(e)}")

@router.put("/email")
async def update_email_settings(settings: EmailSettings):
    """Update email settings"""
    try:
        settings_collection = get_settings_collection()
        audit_collection = get_audit_collection()
        smtp_mode = await get_smtp_mode()

        # Validate settings based on SMTP mode
        if smtp_mode == "managed":
            # Force internal provider for managed SMTP
            if settings.provider != "internal":
                settings.provider = "internal"
                settings.smtp_server = "Internal"
            
            # Validate limits against managed constraints
            try:
                await validate_managed_smtp_limits(settings.sending_limits)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

        # Check if this is a new configuration or update
        existing_settings = await settings_collection.find_one({"type": "email"})
        is_new_config = existing_settings is None

        # Update settings
        result = await settings_collection.update_one(
            {"type": "email"},
            {
                "$set": {
                    "type": "email",
                    "config": settings.dict(),
                    "updated_at": datetime.utcnow(),
                    "smtp_mode": smtp_mode
                }
            },
            upsert=True
        )

        # ✅ Log the configuration change for audit trail
        audit_action = "email_settings_created" if is_new_config else "email_settings_updated"
        await audit_collection.insert_one({
            "action": audit_action,
            "provider": settings.provider,
            "smtp_server": settings.smtp_server,
            "smtp_mode": smtp_mode,
            "updated_at": datetime.utcnow(),
            "settings_id": str(result.upserted_id) if result.upserted_id else "existing"
        })

        return {
            "message": f"Email settings {'saved' if is_new_config else 'updated'} successfully",
            "is_new_config": is_new_config,
            "smtp_mode": smtp_mode,
            "modified_count": result.modified_count,
            "upserted_id": str(result.upserted_id) if result.upserted_id else None
        }

    except HTTPException:
        raise
    except Exception as e:
        # Log error to audit
        try:
            audit_collection = get_audit_collection()
            await audit_collection.insert_one({
                "action": "email_settings_update_failed",
                "error": str(e),
                "smtp_mode": "unknown",
                "attempted_at": datetime.utcnow()
            })
        except:
            pass
        
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {str(e)}")

@router.post("/email/test")
async def test_email_connection(settings: EmailTestSettings):
    """Test SMTP connection - only available for unmanaged SMTP"""
    try:
        smtp_mode = await get_smtp_mode()
        audit_collection = get_audit_collection()
        
        # Don't allow connection testing for managed SMTP
        if smtp_mode == "managed":
            raise HTTPException(
                status_code=400, 
                detail="Connection testing is not available for managed SMTP service"
            )
        
        username = settings.username.strip()
        password = settings.password.strip()
        
        # Test the connection
        server = smtplib.SMTP(settings.smtp_server, settings.smtp_port, timeout=10)
        server.starttls()
        server.login(username, password)
        server.quit()
        
        # Log successful test
        await audit_collection.insert_one({
            "action": "smtp_connection_test",
            "status": "success",
            "smtp_server": settings.smtp_server,
            "smtp_port": settings.smtp_port,
            "username": username,
            "tested_at": datetime.utcnow()
        })
        
        return {"detail": "✅ SMTP connection successful!"}
        
    except smtplib.SMTPAuthenticationError as e:
        # Log failed test
        await audit_collection.insert_one({
            "action": "smtp_connection_test",
            "status": "auth_failed",
            "smtp_server": settings.smtp_server,
            "error": str(e),
            "tested_at": datetime.utcnow()
        })
        raise HTTPException(status_code=401, detail="❌ Authentication failed — check username/password or region")
        
    except smtplib.SMTPConnectError as e:
        # Log failed test
        await audit_collection.insert_one({
            "action": "smtp_connection_test",
            "status": "connection_failed",
            "smtp_server": settings.smtp_server,
            "error": str(e),
            "tested_at": datetime.utcnow()
        })
        raise HTTPException(status_code=502, detail="❌ Could not connect to SMTP server — check host/port")
        
    except Exception as e:
        # Log failed test
        await audit_collection.insert_one({
            "action": "smtp_connection_test",
            "status": "error",
            "smtp_server": settings.smtp_server,
            "error": str(e),
            "tested_at": datetime.utcnow()
        })
        raise HTTPException(status_code=500, detail=f"❌ Unexpected error: {e}")

@router.get("/email/status")
async def get_email_system_status():
    """Get email system status"""
    try:
        settings_collection = get_settings_collection()
        audit_collection = get_audit_collection()
        smtp_mode = await get_smtp_mode()

        settings = await settings_collection.find_one({"type": "email"})

        # Get recent audit logs
        recent_tests = await audit_collection.find(
            {"action": "smtp_connection_test"},
            sort=[("tested_at", -1)],
            limit=5
        ).to_list(5)

        # Get recent configuration changes
        recent_config_changes = await audit_collection.find(
            {"action": {"$regex": "^email_settings_"}},
            sort=[("updated_at", -1)],
            limit=5
        ).to_list(5)

        return {
            "configured": settings is not None,
            "smtp_mode": smtp_mode,
            "provider": settings.get("config", {}).get("provider") if settings else None,
            "last_updated": settings.get("updated_at") if settings else None,
            "recent_connection_tests": recent_tests,
            "recent_config_changes": recent_config_changes,
            "managed_limits": (await get_managed_smtp_limits()) if smtp_mode == "managed" else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")

@router.get("/email/audit")
async def get_email_audit_logs(limit: int = 50):
    """Get email configuration audit logs"""
    try:
        audit_collection = get_audit_collection()
        smtp_mode = await get_smtp_mode()

        logs = await audit_collection.find(
            {"action": {"$regex": "^email_|^smtp_"}},
            sort=[("updated_at", -1), ("tested_at", -1)],
            limit=limit
        ).to_list(limit)

        return {
            "audit_logs": logs,
            "smtp_mode": smtp_mode,
            "total_logs": len(logs)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get audit logs: {str(e)}")

@router.delete("/email")
async def delete_email_settings():
    """Delete email settings (admin only)"""
    try:
        settings_collection = get_settings_collection()
        audit_collection = get_audit_collection()
        smtp_mode = await get_smtp_mode()

        # Check if settings exist
        existing_settings = await settings_collection.find_one({"type": "email"})
        if not existing_settings:
            raise HTTPException(status_code=404, detail="Email settings not found")

        # Delete settings
        result = await settings_collection.delete_one({"type": "email"})

        # Log the deletion
        await audit_collection.insert_one({
            "action": "email_settings_deleted",
            "smtp_mode": smtp_mode,
            "deleted_at": datetime.utcnow(),
            "deleted_count": result.deleted_count
        })

        return {
            "message": "Email settings deleted successfully",
            "deleted_count": result.deleted_count
        }

    except HTTPException:
        raise
    except Exception as e:
        # Log error to audit
        try:
            audit_collection = get_audit_collection()
            await audit_collection.insert_one({
                "action": "email_settings_delete_failed",
                "error": str(e),
                "smtp_mode": "unknown",
                "attempted_at": datetime.utcnow()
            })
        except:
            pass

        raise HTTPException(status_code=500, detail=f"Failed to delete settings: {str(e)}")

@router.get("/email/limits")
async def get_email_limits():
    """Get email sending limits information"""
    try:
        settings_collection = get_settings_collection()
        smtp_mode = await get_smtp_mode()
        
        settings = await settings_collection.find_one({"type": "email"})
        current_limits = settings.get("config", {}).get("sending_limits", {}) if settings else {}
        
        response = {
            "smtp_mode": smtp_mode,
            "current_limits": current_limits
        }
        
        if smtp_mode == "managed":
            response["managed_limits"] = await get_managed_smtp_limits()
            response["limits_enforced_by"] = "system"
        else:
            response["limits_enforced_by"] = "application"
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get limits: {str(e)}")

@router.post("/email/validate-limits")
async def validate_email_limits(limits: SendingLimits):
    """Validate email sending limits against system constraints"""
    try:
        smtp_mode = await get_smtp_mode()
        
        if smtp_mode == "managed":
            try:
                await validate_managed_smtp_limits(limits)
                return {
                    "valid": True,
                    "message": "Limits are within system constraints",
                    "smtp_mode": smtp_mode
                }
            except ValueError as e:
                return {
                    "valid": False,
                    "message": str(e),
                    "smtp_mode": smtp_mode,
                    "managed_limits": await get_managed_smtp_limits()
                }
        else:
            return {
                "valid": True,
                "message": "No system constraints for unmanaged SMTP",
                "smtp_mode": smtp_mode
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to validate limits: {str(e)}")
