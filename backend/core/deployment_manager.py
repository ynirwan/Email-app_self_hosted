# config/deployment_manager.py
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
        
    async def get_user_quota(self, user_id: str) -> Dict:
        """Get user email quota based on deployment mode"""
        
        if self.deployment_mode == DeploymentMode.SELF_HOSTED:
            # Self-hosted = unlimited
            return {
                "monthly_limit": -1,  # -1 = unlimited
                "current_usage": 0,
                "overage_allowed": True,
                "billing_enabled": False,
                "controlled_by": "self_hosted",
                "unlimited": True
            }
        
        # For hosted service, check quota from your control system
        return await self._fetch_hosted_quota(user_id)
    
    async def _fetch_hosted_quota(self, user_id: str) -> Dict:
        """Fetch quota from your centralized control system"""
        
        if self.quota_source == "remote_vault":
            return await self._fetch_from_control_api(user_id)
        elif self.quota_source == "database":
            return await self._fetch_from_database(user_id)
        else:
            # Default hosted limits
            return await self._get_default_hosted_quota()
    
    async def _fetch_from_control_api(self, user_id: str) -> Dict:
        """Fetch from your centralized control API"""
        try:
            control_url = os.getenv("QUOTA_CHECK_URL", "").format(user_id=user_id)
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
    
    async def _fetch_from_database(self, user_id: str) -> Dict:
        """Fetch quota from local database"""
        from database import get_usage_collection
        
        try:
            usage_collection = get_usage_collection()
            current_month = datetime.now().strftime("%Y-%m")
            
            usage = await usage_collection.find_one({
                "user_id": user_id,
                "month": current_month
            })
            
            if not usage:
                # Create new usage record
                usage = {
                    "user_id": user_id,
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
            
        except Exception:
            return await self._get_default_hosted_quota()
    
    async def _get_default_hosted_quota(self) -> Dict:
        """Safe default for hosted service"""
        return {
            "monthly_limit": self.free_monthly_limit,
            "current_usage": 0, 
            "remaining": self.free_monthly_limit,
            "overage": 0,
            "billing_enabled": True,
            "controlled_by": "platform_default",
            "overage_price": self.overage_price
        }
    
    async def can_send_email(self, user_id: str) -> Dict:
        """Check if user can send email"""
        if self.deployment_mode == DeploymentMode.SELF_HOSTED:
            return {
                "can_send": True,
                "reason": "unlimited",
                "unlimited": True
            }
        
        quota = await self.get_user_quota(user_id)
        can_send = quota["remaining"] > 0 or quota.get("overage_allowed", True)
        
        return {
            "can_send": can_send,
            "reason": "quota_exceeded" if not can_send else "ok",
            "quota": quota
        }

