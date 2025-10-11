# routes/email_settings.py
from fastapi import APIRouter, HTTPException, Request
from models.email_models import SMTPSettings, HostedEmailSettings, SMTPTestSettings
from core.deployment_manager import QuotaManager, DeploymentMode
from core.security import encrypt_password, decrypt_password
from database import get_settings_collection, get_usage_collection, get_audit_collection
from datetime import datetime
import smtplib
import calendar

router = APIRouter()

@router.get("/system-info")
async def get_email_system_info():
    """Get system information based on deployment mode"""
    try:
        quota_manager = QuotaManager()
        deployment_mode = quota_manager.deployment_mode

        if deployment_mode == DeploymentMode.SELF_HOSTED:
            return {
                "deployment_mode": "self_hosted",
                "quota_enabled": False,
                "smtp_control": "full_access",
                "features": {
                    "unlimited_emails": True,
                    "full_smtp_config": True,
                    "no_billing": True,
                    "complete_control": True,
                    "no_tracking": True
                },
                "supported_providers": [
                    "SendGrid", "Mailgun", "Amazon SES", "Postmark",
                    "Custom SMTP", "Local SMTP Server", "Office365", "Gmail"
                ],
                "message": "Complete SMTP control - configure any email provider"
            }

        else:  # HOSTED_SERVICE
            return {
                "deployment_mode": "hosted_service",
                "quota_enabled": True,
                "smtp_control": "managed_limits",
                "free_quota": quota_manager.free_monthly_limit,
                "overage_price": quota_manager.overage_price,
                "features": {
                    "managed_quotas": True,
                    "billing_integration": True,
                    "overage_tracking": True,
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
    """Get email settings - single user system"""
    try:
        settings_collection = get_settings_collection()
        quota_manager = QuotaManager()

        # Get existing settings (single document, no user_id)
        settings = await settings_collection.find_one({"type": "email"})

        if not settings:
            # Return defaults based on deployment mode
            if quota_manager.deployment_mode == DeploymentMode.SELF_HOSTED:
                return {
                    "deployment_mode": "self_hosted",
                    "provider": "",
                    "smtp_server": "",
                    "smtp_port": 587,
                    "username": "",
                    "password": "",
                    "daily_limit": None,
                    "configured": False,
                    "bounce_handling": {
                        "enabled": True,
                        "webhook_url": "",
                        "forward_bounces": False,
                        "forward_email": ""
                    },
                    "quota_info": {
                        "enabled": False,
                        "unlimited": True,
                        "message": "Unlimited email sending"
                    }
                }
            else:
                return {
                    "deployment_mode": "hosted_service",
                    "smtp_choice": "managed",
                    "configured": False,
                    "daily_limit": 1000,
                    "bounce_forward_email": "",
                    "quota_info": await quota_manager.get_user_quota()  # No user_id needed
                }

        # Return existing settings with quota info
        config = settings.get("config", {})

        # Don't show actual password
        if config.get("password"):
            config["password"] = "********"

        config["quota_info"] = await quota_manager.get_user_quota()  # No user_id needed
        config["deployment_mode"] = quota_manager.deployment_mode.value
        config["configured"] = True

        return config

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get settings: {str(e)}")

@router.put("/settings")
async def update_email_settings(request: Request):
    """Update email settings - single user system"""
    try:
        settings_collection = get_settings_collection()
        audit_collection = get_audit_collection()
        quota_manager = QuotaManager()
        deployment_mode = quota_manager.deployment_mode

        # Get request body
        body = await request.json()

        if deployment_mode == DeploymentMode.SELF_HOSTED:
            # Self-hosted: Full SMTP configuration
            config_to_store = {
                "provider": body.get("provider", ""),
                "smtp_server": body.get("smtp_server", ""),
                "smtp_port": body.get("smtp_port", 587),
                "username": body.get("username", ""),
                "password": encrypt_password(body.get("password", "")),
                "daily_limit": body.get("daily_limit"),
                "bounce_handling": body.get("bounce_handling", {}),
                "deployment_mode": deployment_mode.value,
                "updated_at": datetime.utcnow()
            }
        else:
            # Hosted service: Limited configuration
            config_to_store = {
                "smtp_choice": body.get("smtp_choice", "managed"),
                "daily_limit": body.get("daily_limit", 1000),
                "bounce_forward_email": body.get("bounce_forward_email", ""),
                "deployment_mode": deployment_mode.value,
                "updated_at": datetime.utcnow()
            }

            # Add client SMTP config if chosen
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

        # Store settings (single document, no user_id)
        result = await settings_collection.update_one(
            {"type": "email"},
            {
                "$set": {
                    "type": "email",
                    "config": config_to_store
                }
            },
            upsert=True
        )

        # Audit log (no user_id)
        await audit_collection.insert_one({
            "action": "email_settings_updated",
            "deployment_mode": deployment_mode.value,
            "provider": config_to_store.get("provider"),
            "timestamp": datetime.utcnow()
        })

        response = {
            "message": "Email settings updated successfully",
            "deployment_mode": deployment_mode.value,
            "modified_count": result.modified_count,
            "upserted_id": str(result.upserted_id) if result.upserted_id else None
        }

        if deployment_mode == DeploymentMode.SELF_HOSTED:
            response["note"] = "No sending limits applied - full control enabled"
        else:
            response["quota_info"] = await quota_manager.get_user_quota()  # No user_id needed

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {str(e)}")

@router.post("/test-connection")
async def test_smtp_connection(request: Request):
    """Test SMTP connection - single user system"""
    try:
        audit_collection = get_audit_collection()
        
        # Get request body
        body = await request.json()
        
        smtp_server = body.get("smtp_server")
        smtp_port = body.get("smtp_port", 587)
        username = body.get("username")
        password = body.get("password")
        
        if not all([smtp_server, username, password]):
            raise HTTPException(status_code=400, detail="Missing required SMTP settings")

        # Test the connection
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
        server.starttls()
        server.login(username.strip(), password.strip())
        server.quit()

        # Log successful test (no user_id)
        await audit_collection.insert_one({
            "action": "smtp_connection_test",
            "status": "success",
            "smtp_server": smtp_server,
            "smtp_port": smtp_port,
            "timestamp": datetime.utcnow()
        })

        return {"status": "success", "message": "✅ SMTP connection successful!"}

    except smtplib.SMTPAuthenticationError as e:
        await audit_collection.insert_one({
            "action": "smtp_connection_test",
            "status": "auth_failed",
            "error": str(e),
            "timestamp": datetime.utcnow()
        })
        raise HTTPException(status_code=401, detail="❌ Authentication failed - check username/password")

    except smtplib.SMTPConnectError as e:
        await audit_collection.insert_one({
            "action": "smtp_connection_test",
            "status": "connection_failed",
            "error": str(e),
            "timestamp": datetime.utcnow()
        })
        raise HTTPException(status_code=502, detail="❌ Could not connect to SMTP server - check host/port")

    except Exception as e:
        await audit_collection.insert_one({
            "action": "smtp_connection_test",
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow()
        })
        raise HTTPException(status_code=500, detail=f"❌ Connection test failed: {str(e)}")

@router.get("/usage")
async def get_email_usage():
    """Get email usage - single user system"""
    try:
        quota_manager = QuotaManager()

        if quota_manager.deployment_mode == DeploymentMode.SELF_HOSTED:
            return {
                "deployment_mode": "self_hosted",
                "unlimited": True,
                "message": "No usage limits or tracking for self-hosted deployment"
            }

        # For hosted service, return quota info (no user_id needed)
        quota_info = await quota_manager.get_user_quota()

        # Calculate additional info
        now = datetime.now()
        last_day = calendar.monthrange(now.year, now.month)[1]
        days_remaining = last_day - now.day + 1

        usage_percentage = 0
        if quota_info.get("monthly_limit", 0) > 0:
            usage_percentage = (quota_info.get("current_usage", 0) / quota_info["monthly_limit"]) * 100

        return {
            "deployment_mode": "hosted_service",
            "current_month": now.strftime("%Y-%m"),
            "quota": quota_info,
            "usage_percentage": round(usage_percentage, 1),
            "days_remaining_in_month": days_remaining,
            "billing_enabled": quota_info.get("billing_enabled", False)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get usage: {str(e)}")

@router.get("/health")
async def get_email_health():
    """Get email system health status - single user system"""
    try:
        settings_collection = get_settings_collection()
        quota_manager = QuotaManager()

        # Get settings (single document, no user_id)
        settings = await settings_collection.find_one({"type": "email"})

        if not settings:
            return {
                "configured": False,
                "status": "not_configured",
                "message": "Email settings not configured"
            }

        config = settings.get("config", {})
        health_info = {
            "configured": True,
            "deployment_mode": quota_manager.deployment_mode.value,
            "provider": config.get("provider"),
            "last_updated": settings.get("updated_at")
        }

        if quota_manager.deployment_mode == DeploymentMode.SELF_HOSTED:
            health_info.update({
                "status": "operational",
                "limits": "unlimited",
                "message": "Self-hosted deployment - full control"
            })
        else:
            quota = await quota_manager.get_user_quota()  # No user_id needed
            can_send = await quota_manager.can_send_email()  # No user_id needed

            health_info.update({
                "status": "operational" if can_send["can_send"] else "quota_exceeded",
                "quota_remaining": quota.get("remaining", 0),
                "can_send": can_send["can_send"],
                "message": can_send.get("reason", "ok")
            })

        return health_info

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get health status: {str(e)}")

@router.delete("/settings")
async def delete_email_settings():
    """Delete email settings - single user system"""
    try:
        settings_collection = get_settings_collection()
        audit_collection = get_audit_collection()

        # Check if settings exist (single document, no user_id)
        existing_settings = await settings_collection.find_one({"type": "email"})
        if not existing_settings:
            raise HTTPException(status_code=404, detail="Email settings not found")

        # Delete settings (single document, no user_id)
        result = await settings_collection.delete_one({"type": "email"})

        # Audit log (no user_id)
        await audit_collection.insert_one({
            "action": "email_settings_deleted",
            "timestamp": datetime.utcnow(),
            "deleted_count": result.deleted_count
        })

        return {
            "message": "Email settings deleted successfully",
            "deleted_count": result.deleted_count
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete settings: {str(e)}")

