# core/deployment_manager.py
import os
import httpx
from enum import Enum
from typing import Dict, Optional
from datetime import datetime
import calendar

class DeploymentMode(str, Enum):
    SELF_HOSTED = "self_hosted"
    HOSTED_SERVICE = "hosted_service"

class QuotaManager:
    def __init__(self):
        self.deployment_mode = DeploymentMode(os.getenv("DEPLOYMENT_MODE", "self_hosted"))
        self.quota_enabled = os.getenv("EMAIL_QUOTA_ENABLED", "false").lower() == "true"
        self.quota_source = os.getenv("EMAIL_QUOTA_SOURCE", "database")
        self.free_monthly_limit = int(os.getenv("FREE_EMAIL_LIMIT_MONTHLY", "50000"))
        self.overage_price = float(os.getenv("OVERAGE_PRICE_PER_EMAIL", "0.001"))

    async def get_user_quota(self) -> Dict:
        """Get email quota - single user system"""
        
        if self.deployment_mode == DeploymentMode.SELF_HOSTED:
            # Self-hosted = unlimited
            return {
                "monthly_limit": -1,  # -1 = unlimited
                "current_usage": 0,
                "remaining": -1,  # unlimited
                "overage": 0,
                "overage_allowed": True,
                "billing_enabled": False,
                "controlled_by": "self_hosted",
                "unlimited": True
            }

        # For hosted service, check quota
        return await self._fetch_hosted_quota()

    async def _fetch_hosted_quota(self) -> Dict:
        """Fetch quota - single user system"""
        
        if self.quota_source == "remote_vault":
            return await self._fetch_from_control_api()
        elif self.quota_source == "database":
            return await self._fetch_from_database()
        else:
            # Default hosted limits
            return await self._get_default_hosted_quota()

    async def _fetch_from_control_api(self) -> Dict:
        """Fetch from your centralized control API - single user system"""
        try:
            # For single user, use a fixed identifier or system-level quota
            control_url = os.getenv("QUOTA_CHECK_URL", "").replace("{user_id}", "single_user")
            api_key = os.getenv("QUOTA_API_KEY", "")

            if not control_url or not api_key:
                return await self._get_default_hosted_quota()

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    control_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=5.0
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    return await self._get_default_hosted_quota()

        except Exception:
            # Network issues - use safe defaults
            return await self._get_default_hosted_quota()

    async def _fetch_from_database(self) -> Dict:
        """Fetch quota from local database - single user system"""
        from database import get_usage_collection

        try:
            usage_collection = get_usage_collection()
            current_month = datetime.now().strftime("%Y-%m")

            # Single document query (no user_id)
            usage = await usage_collection.find_one({
                "type": "usage",
                "month": current_month
            })

            if not usage:
                # Create new usage record for single user
                usage = {
                    "type": "usage",
                    "month": current_month,
                    "emails_sent": 0,
                    "emails_remaining": self.free_monthly_limit,
                    "overage_emails": 0,
                    "last_updated": datetime.utcnow()
                }
                await usage_collection.insert_one(usage)

            return {
                "monthly_limit": self.free_monthly_limit,
                "current_usage": usage["emails_sent"],
                "remaining": max(0, usage["emails_remaining"]),
                "overage": usage["overage_emails"],
                "billing_enabled": True,
                "controlled_by": "platform",
                "overage_price": self.overage_price
            }

        except Exception as e:
            print(f"Error fetching quota from database: {e}")
            return await self._get_default_hosted_quota()

    async def _get_default_hosted_quota(self) -> Dict:
        """Safe default for hosted service - single user system"""
        return {
            "monthly_limit": self.free_monthly_limit,
            "current_usage": 0,
            "remaining": self.free_monthly_limit,
            "overage": 0,
            "billing_enabled": True,
            "controlled_by": "platform_default",
            "overage_price": self.overage_price
        }

    async def can_send_email(self) -> Dict:
        """Check if can send email - single user system"""
        if self.deployment_mode == DeploymentMode.SELF_HOSTED:
            return {
                "can_send": True,
                "reason": "unlimited",
                "unlimited": True
            }

        quota = await self.get_user_quota()  # No user_id needed
        can_send = quota["remaining"] > 0 or quota.get("overage_allowed", True)

        return {
            "can_send": can_send,
            "reason": "quota_exceeded" if not can_send else "ok",
            "quota": quota
        }

    async def increment_usage(self, email_count: int = 1) -> Dict:
        """Increment email usage counter - single user system"""
        if self.deployment_mode == DeploymentMode.SELF_HOSTED:
            # No tracking for self-hosted
            return {"success": True, "message": "No tracking for self-hosted"}

        try:
            from database import get_usage_collection
            usage_collection = get_usage_collection()
            current_month = datetime.now().strftime("%Y-%m")

            # Update single document (no user_id)
            result = await usage_collection.update_one(
                {"type": "usage", "month": current_month},
                {
                    "$inc": {
                        "emails_sent": email_count,
                        "emails_remaining": -email_count
                    },
                    "$set": {"last_updated": datetime.utcnow()}
                },
                upsert=True
            )

            # Handle overage
            current_usage = await usage_collection.find_one({"type": "usage", "month": current_month})
            if current_usage and current_usage["emails_remaining"] < 0:
                overage = abs(current_usage["emails_remaining"])
                await usage_collection.update_one(
                    {"type": "usage", "month": current_month},
                    {
                        "$set": {
                            "emails_remaining": 0,
                            "overage_emails": overage
                        }
                    }
                )

            return {"success": True, "usage_updated": result.modified_count}

        except Exception as e:
            print(f"Error incrementing usage: {e}")
            return {"success": False, "error": str(e)}

    async def reset_monthly_quota(self) -> Dict:
        """Reset monthly quota - single user system"""
        if self.deployment_mode == DeploymentMode.SELF_HOSTED:
            return {"success": True, "message": "No quota to reset for self-hosted"}

        try:
            from database import get_usage_collection
            usage_collection = get_usage_collection()
            current_month = datetime.now().strftime("%Y-%m")

            # Reset single document (no user_id)
            result = await usage_collection.update_one(
                {"type": "usage", "month": current_month},
                {
                    "$set": {
                        "emails_sent": 0,
                        "emails_remaining": self.free_monthly_limit,
                        "overage_emails": 0,
                        "last_updated": datetime.utcnow()
                    }
                },
                upsert=True
            )

            return {"success": True, "quota_reset": True}

        except Exception as e:
            print(f"Error resetting quota: {e}")
            return {"success": False, "error": str(e)}

    async def get_usage_stats(self) -> Dict:
        """Get usage statistics - single user system"""
        if self.deployment_mode == DeploymentMode.SELF_HOSTED:
            return {
                "deployment_mode": "self_hosted",
                "unlimited": True,
                "total_sent": "unlimited",
                "monthly_stats": []
            }

        try:
            from database import get_usage_collection
            usage_collection = get_usage_collection()

            # Get last 12 months of usage (no user_id)
            monthly_stats = await usage_collection.find(
                {"type": "usage"},
                sort=[("month", -1)],
                limit=12
            ).to_list(12)

            total_sent = sum(stat.get("emails_sent", 0) for stat in monthly_stats)

            return {
                "deployment_mode": "hosted_service",
                "total_sent": total_sent,
                "monthly_stats": monthly_stats,
                "current_quota": await self.get_user_quota()
            }

        except Exception as e:
            print(f"Error getting usage stats: {e}")
            return {
                "deployment_mode": "hosted_service",
                "total_sent": 0,
                "monthly_stats": [],
                "error": str(e)
            }

