# backend/tasks/provider_manager.py - COMPLETE EMAIL PROVIDER FAILOVER
"""
Production-ready email provider management with automatic failover
Supports multiple providers with health monitoring and intelligent routing
"""
import logging
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
from abc import ABC, abstractmethod
from celery_app import celery_app
from database import get_sync_settings_collection
from core.config import settings, get_redis_key
from .rate_limiter import EmailProvider
from .audit_logger import log_system_event, AuditEventType, AuditSeverity
import redis

logger = logging.getLogger(__name__)

class ProviderStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    MAINTENANCE = "maintenance"
    DISABLED = "disabled"

class ProviderType(Enum):
    SENDGRID = "sendgrid"
    SES = "ses"
    MAILGUN = "mailgun"
    SMTP = "smtp"
    MOCK = "mock"

class EmailServiceInterface(ABC):
    """Abstract interface for email service providers"""
    
    @abstractmethod
    def send_email(self, sender_email: str, recipient_email: str, subject: str, 
                   html_content: str, text_content: str = None, **kwargs) -> Dict[str, Any]:
        """Send email through the provider"""
        pass
    
    @abstractmethod
    def get_provider_status(self) -> Tuple[ProviderStatus, Dict[str, Any]]:
        """Check provider health status"""
        pass
    
    @abstractmethod
    def get_provider_limits(self) -> Dict[str, Any]:
        """Get provider rate limits and quotas"""
        pass

class MockEmailService(EmailServiceInterface):
    """Mock email service for testing"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.failure_rate = config.get("mock_failure_rate", 0.0)  # 0.0 = no failures, 1.0 = all fail
    
    def send_email(self, sender_email: str, recipient_email: str, subject: str, 
                   html_content: str, text_content: str = None, **kwargs) -> Dict[str, Any]:
        """Mock email sending"""
        import random
        import time
        
        # Simulate processing time
        time.sleep(random.uniform(0.01, 0.05))
        
        # Simulate failures based on failure rate
        if random.random() < self.failure_rate:
            return {
                "success": False,
                "message_id": None,
                "error": "Mock email failure for testing",
                "provider": "mock",
                "cost": 0.0
            }
        
        # Simulate success
        mock_message_id = f"mock_{int(time.time() * 1000)}_{hash(recipient_email) % 10000}"
        
        return {
            "success": True,
            "message_id": mock_message_id,
            "provider": "mock",
            "cost": 0.0,
            "delivered_at": datetime.utcnow().isoformat()
        }
    
    def get_provider_status(self) -> Tuple[ProviderStatus, Dict[str, Any]]:
        """Mock provider status - always healthy unless configured otherwise"""
        status = ProviderStatus.HEALTHY
        if self.failure_rate > 0.5:
            status = ProviderStatus.DEGRADED
        if self.failure_rate >= 1.0:
            status = ProviderStatus.FAILED
        
        return status, {
            "response_time_ms": 20,
            "failure_rate": self.failure_rate,
            "mock_provider": True
        }
    
    def get_provider_limits(self) -> Dict[str, Any]:
        """Mock provider limits"""
        return {
            "emails_per_second": 1000,
            "emails_per_hour": 1000000,
            "daily_quota": 50000000,
            "monthly_quota": 1000000000
        }

class SendGridEmailService(EmailServiceInterface):
    """SendGrid email service implementation"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.api_key = config.get("api_key")
        self.base_url = "https://api.sendgrid.com/v3"
    
    def send_email(self, sender_email: str, recipient_email: str, subject: str, 
                   html_content: str, text_content: str = None, **kwargs) -> Dict[str, Any]:
        """Send email via SendGrid API"""
        try:
            import requests
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "personalizations": [{
                    "to": [{"email": recipient_email}],
                    "subject": subject
                }],
                "from": {"email": sender_email},
                "content": []
            }
            
            if text_content:
                payload["content"].append({"type": "text/plain", "value": text_content})
            if html_content:
                payload["content"].append({"type": "text/html", "value": html_content})
            
            response = requests.post(
                f"{self.base_url}/mail/send",
                headers=headers,
                json=payload,
                timeout=settings.EMAIL_SEND_TIMEOUT_SECONDS
            )
            
            if response.status_code == 202:  # SendGrid success code
                return {
                    "success": True,
                    "message_id": response.headers.get("X-Message-Id"),
                    "provider": "sendgrid",
                    "cost": 0.0001  # Approximate cost per email
                }
            else:
                return {
                    "success": False,
                    "message_id": None,
                    "error": f"SendGrid API error: {response.status_code} - {response.text}",
                    "provider": "sendgrid"
                }
                
        except Exception as e:
            return {
                "success": False,
                "message_id": None,
                "error": f"SendGrid send failed: {str(e)}",
                "provider": "sendgrid"
            }
    
    def get_provider_status(self) -> Tuple[ProviderStatus, Dict[str, Any]]:
        """Check SendGrid API status"""
        try:
            import requests
            
            start_time = time.time()
            response = requests.get(
                f"{self.base_url}/user/profile",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=5
            )
            response_time = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                status = ProviderStatus.HEALTHY
                if response_time > 2000:  # > 2 seconds is slow
                    status = ProviderStatus.DEGRADED
            else:
                status = ProviderStatus.FAILED
            
            return status, {
                "response_time_ms": round(response_time, 2),
                "api_status_code": response.status_code,
                "api_accessible": response.status_code < 500
            }
            
        except Exception as e:
            return ProviderStatus.FAILED, {"error": str(e)}
    
    def get_provider_limits(self) -> Dict[str, Any]:
        """SendGrid rate limits (varies by plan)"""
        return {
            "emails_per_second": 100,
            "emails_per_hour": 100000,
            "daily_quota": 1000000,
            "monthly_quota": 50000000
        }

class SESEmailService(EmailServiceInterface):
    """Amazon SES email service implementation"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.region = config.get("region", "us-east-1")
        self.access_key = config.get("access_key")
        self.secret_key = config.get("secret_key")
    
    def send_email(self, sender_email: str, recipient_email: str, subject: str, 
                   html_content: str, text_content: str = None, **kwargs) -> Dict[str, Any]:
        """Send email via AWS SES"""
        try:
            import boto3
            from botocore.exceptions import ClientError
            
            # Create SES client
            ses_client = boto3.client(
                'ses',
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            )
            
            # Prepare message
            message = {
                'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                'Body': {}
            }
            
            if text_content:
                message['Body']['Text'] = {'Data': text_content, 'Charset': 'UTF-8'}
            if html_content:
                message['Body']['Html'] = {'Data': html_content, 'Charset': 'UTF-8'}
            
            # Send email
            response = ses_client.send_email(
                Source=sender_email,
                Destination={'ToAddresses': [recipient_email]},
                Message=message
            )
            
            return {
                "success": True,
                "message_id": response.get('MessageId'),
                "provider": "ses",
                "cost": 0.0001  # $0.10 per 1000 emails
            }
            
        except ClientError as e:
            return {
                "success": False,
                "message_id": None,
                "error": f"SES API error: {e.response['Error']['Code']} - {e.response['Error']['Message']}",
                "provider": "ses"
            }
        except Exception as e:
            return {
                "success": False,
                "message_id": None,
                "error": f"SES send failed: {str(e)}",
                "provider": "ses"
            }
    
    def get_provider_status(self) -> Tuple[ProviderStatus, Dict[str, Any]]:
        """Check AWS SES status"""
        try:
            import boto3
            from botocore.exceptions import ClientError
            
            start_time = time.time()
            ses_client = boto3.client(
                'ses',
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            )
            
            # Check sending quota
            response = ses_client.get_send_quota()
            response_time = (time.time() - start_time) * 1000
            
            quota_used_percent = (response['SentLast24Hours'] / response['Max24HourSend']) * 100
            
            status = ProviderStatus.HEALTHY
            if quota_used_percent > 90:
                status = ProviderStatus.DEGRADED
            if response_time > 3000:  # > 3 seconds
                status = ProviderStatus.DEGRADED
            
            return status, {
                "response_time_ms": round(response_time, 2),
                "quota_used_percent": round(quota_used_percent, 2),
                "max_24h_send": response['Max24HourSend'],
                "sent_last_24h": response['SentLast24Hours']
            }
            
        except Exception as e:
            return ProviderStatus.FAILED, {"error": str(e)}
    
    def get_provider_limits(self) -> Dict[str, Any]:
        """SES rate limits (varies by account)"""
        return {
            "emails_per_second": 14,  # Default sending rate
            "emails_per_hour": 50400,  # 14 * 3600
            "daily_quota": 200,  # Default new account limit
            "monthly_quota": 6000
        }

class SMTPEmailService(EmailServiceInterface):
    """SMTP email service implementation"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.smtp_server = config.get("smtp_server")
        self.smtp_port = config.get("smtp_port", 587)
        self.username = config.get("username")
        self.password = config.get("password")
        self.use_tls = config.get("use_tls", True)
    
    def send_email(self, sender_email: str, recipient_email: str, subject: str, 
                   html_content: str, text_content: str = None, **kwargs) -> Dict[str, Any]:
        """Send email via SMTP"""
        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            
            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = sender_email
            message["To"] = recipient_email
            
            if text_content:
                text_part = MIMEText(text_content, "plain")
                message.attach(text_part)
            
            if html_content:
                html_part = MIMEText(html_content, "html")
                message.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                
                if self.username and self.password:
                    server.login(self.username, self.password)
                
                server.send_message(message)
            
            return {
                "success": True,
                "message_id": f"smtp_{int(time.time() * 1000)}",
                "provider": "smtp",
                "cost": 0.0
            }
            
        except Exception as e:
            return {
                "success": False,
                "message_id": None,
                "error": f"SMTP send failed: {str(e)}",
                "provider": "smtp"
            }
    
    def get_provider_status(self) -> Tuple[ProviderStatus, Dict[str, Any]]:
        """Check SMTP server status"""
        try:
            import smtplib
            import socket
            
            start_time = time.time()
            
            # Test connection
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=5) as server:
                if self.use_tls:
                    server.starttls()
                
                if self.username and self.password:
                    server.login(self.username, self.password)
                
                response_time = (time.time() - start_time) * 1000
            
            status = ProviderStatus.HEALTHY
            if response_time > 5000:  # > 5 seconds
                status = ProviderStatus.DEGRADED
            
            return status, {
                "response_time_ms": round(response_time, 2),
                "connection_successful": True,
                "server": self.smtp_server,
                "port": self.smtp_port
            }
            
        except Exception as e:
            return ProviderStatus.FAILED, {
                "error": str(e),
                "connection_successful": False
            }
    
    def get_provider_limits(self) -> Dict[str, Any]:
        """SMTP limits (generic estimates)"""
        return {
            "emails_per_second": 5,
            "emails_per_hour": 1000,
            "daily_quota": 10000,
            "monthly_quota": 300000
        }

class EmailProviderManager:
    """Email provider manager with failover and load balancing"""
    
    def __init__(self):
        self.redis_client = redis.Redis.from_url(settings.REDIS_URL)
        self.providers = {}
        self.provider_configs = {}
        self.load_provider_configurations()
    
    def load_provider_configurations(self):
        """Load email provider configurations from database"""
        try:
            settings_collection = get_sync_settings_collection()
            
            # Load email service configuration
            email_config = settings_collection.find_one({"type": "smtp"})
            
            if email_config:
                # Determine provider type
                service_type = email_config.get("email_service", "smtp").lower()
                
                if service_type == "sendgrid":
                    self._setup_sendgrid_provider(email_config)
                elif service_type == "ses":
                    self._setup_ses_provider(email_config)
                elif service_type == "mailgun":
                    self._setup_mailgun_provider(email_config)
                elif service_type == "smtp":
                    self._setup_smtp_provider(email_config)
            
            # Always setup mock provider for testing
            if settings.MOCK_EMAIL_SENDING:
                self._setup_mock_provider()
            
            logger.info(f"Loaded {len(self.providers)} email providers")
            
        except Exception as e:
            logger.error(f"Failed to load provider configurations: {e}")
            # Fallback to mock provider
            self._setup_mock_provider()
    
    def _setup_sendgrid_provider(self, config: Dict[str, Any]):
        """Setup SendGrid provider"""
        provider_config = {
            "api_key": config.get("api_key") or config.get("password"),
            "type": ProviderType.SENDGRID
        }
        
        self.provider_configs["sendgrid"] = provider_config
        self.providers["sendgrid"] = SendGridEmailService(provider_config)
    
    def _setup_ses_provider(self, config: Dict[str, Any]):
        """Setup AWS SES provider"""
        provider_config = {
            "region": config.get("region", "us-east-1"),
            "access_key": config.get("access_key") or config.get("username"),
            "secret_key": config.get("secret_key") or config.get("password"),
            "type": ProviderType.SES
        }
        
        self.provider_configs["ses"] = provider_config
        self.providers["ses"] = SESEmailService(provider_config)
    
    def _setup_smtp_provider(self, config: Dict[str, Any]):
        """Setup SMTP provider"""
        provider_config = {
            "smtp_server": config.get("smtp_server"),
            "smtp_port": config.get("smtp_port", 587),
            "username": config.get("username"),
            "password": config.get("password"),
            "use_tls": config.get("use_tls", True),
            "type": ProviderType.SMTP
        }
        
        self.provider_configs["smtp"] = provider_config
        self.providers["smtp"] = SMTPEmailService(provider_config)
    
    def _setup_mock_provider(self):
        """Setup mock provider for testing"""
        provider_config = {
            "mock_failure_rate": 0.0,  # No failures by default
            "type": ProviderType.MOCK
        }
        
        self.provider_configs["mock"] = provider_config
        self.providers["mock"] = MockEmailService(provider_config)
    
    def get_best_provider(self, campaign_id: str = None) -> Optional[Tuple[str, EmailServiceInterface]]:
        """Get the best available provider based on health and load"""
        try:
            if not self.providers:
                logger.error("No email providers configured")
                return None
            
            # If mock mode is enabled, always use mock provider
            if settings.MOCK_EMAIL_SENDING and "mock" in self.providers:
                return "mock", self.providers["mock"]
            
            # Get provider health status
            provider_health = {}
            for name, provider in self.providers.items():
                if name == "mock" and not settings.MOCK_EMAIL_SENDING:
                    continue  # Skip mock provider unless in mock mode
                
                try:
                    status, details = provider.get_provider_status()
                    provider_health[name] = {
                        "status": status,
                        "details": details,
                        "provider": provider
                    }
                except Exception as e:
                    provider_health[name] = {
                        "status": ProviderStatus.FAILED,
                        "details": {"error": str(e)},
                        "provider": provider
                    }
            
            # Sort providers by health and performance
            healthy_providers = [
                (name, info) for name, info in provider_health.items()
                if info["status"] in [ProviderStatus.HEALTHY, ProviderStatus.DEGRADED]
            ]
            
            if not healthy_providers:
                logger.error("No healthy email providers available")
                return None
            
            # Choose best provider (prefer healthy over degraded)
            healthy_providers.sort(key=lambda x: (
                0 if x[1]["status"] == ProviderStatus.HEALTHY else 1,
                x[1]["details"].get("response_time_ms", 1000)
            ))
            
            best_provider_name, best_provider_info = healthy_providers[0]
            
            # Log provider selection
            log_system_event(
                AuditEventType.SYSTEM_STARTUP,  # Using closest available event
                {
                    "selected_provider": best_provider_name,
                    "provider_status": best_provider_info["status"].value,
                    "campaign_id": campaign_id,
                    "available_providers": len(healthy_providers)
                }
            )
            
            return best_provider_name, best_provider_info["provider"]
            
        except Exception as e:
            logger.error(f"Provider selection failed: {e}")
            return None
    
    def send_email_with_failover(self, sender_email: str, recipient_email: str, subject: str,
                                html_content: str, text_content: str = None, 
                                campaign_id: str = None, **kwargs) -> Dict[str, Any]:
        """Send email with automatic failover between providers"""
        
        attempted_providers = []
        last_error = None
        
        # Try providers in order of preference
        max_attempts = min(len(self.providers), 3)  # Try up to 3 providers
        
        for attempt in range(max_attempts):
            provider_info = self.get_best_provider(campaign_id)
            
            if not provider_info:
                break
            
            provider_name, provider = provider_info
            
            # Skip already attempted providers
            if provider_name in attempted_providers:
                continue
            
            attempted_providers.append(provider_name)
            
            try:
                logger.debug(f"Attempting email send via {provider_name}")
                
                result = provider.send_email(
                    sender_email=sender_email,
                    recipient_email=recipient_email,
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content,
                    **kwargs
                )
                
                # Add provider info to result
                result["attempted_providers"] = attempted_providers
                result["selected_provider"] = provider_name
                
                if result.get("success"):
                    # Record successful send
                    self._record_provider_result(provider_name, True, campaign_id)
                    
                    logger.debug(f"Email sent successfully via {provider_name}")
                    return result
                else:
                    # Record failed send and try next provider
                    self._record_provider_result(provider_name, False, campaign_id)
                    last_error = result.get("error", "Unknown provider error")
                    
                    # Check if this is a permanent failure (don't retry)
                    if self._is_permanent_failure(result.get("error", "")):
                        result["attempted_providers"] = attempted_providers
                        result["permanent_failure"] = True
                        return result
                    
                    logger.warning(f"Email send failed via {provider_name}: {last_error}")
                    continue
                    
            except Exception as e:
                last_error = str(e)
                self._record_provider_result(provider_name, False, campaign_id)
                logger.error(f"Provider {provider_name} failed with exception: {e}")
                continue
        
        # All providers failed
        return {
            "success": False,
            "message_id": None,
            "error": f"All email providers failed. Last error: {last_error}",
            "attempted_providers": attempted_providers,
            "total_attempts": len(attempted_providers)
        }
    
    def _record_provider_result(self, provider_name: str, success: bool, campaign_id: str = None):
        """Record provider send result for health monitoring"""
        try:
            # Update provider statistics
            stats_key = get_redis_key(f"provider_stats_{provider_name}", "hourly")
            
            if success:
                self.redis_client.hincrby(stats_key, "success_count", 1)
            else:
                self.redis_client.hincrby(stats_key, "failure_count", 1)
            
            self.redis_client.expire(stats_key, 3600)  # 1 hour TTL
            
        except Exception as e:
            logger.error(f"Failed to record provider result: {e}")
    
    def _is_permanent_failure(self, error_message: str) -> bool:
        """Check if error indicates a permanent failure that shouldn't be retried"""
        permanent_failure_indicators = [
            "invalid_email", "blacklisted", "suppressed", "unsubscribed",
            "domain_not_found", "recipient_not_found", "mailbox_full"
        ]
        
        error_lower = error_message.lower()
        return any(indicator in error_lower for indicator in permanent_failure_indicators)
    
    def get_provider_health_report(self) -> Dict[str, Any]:
        """Get comprehensive provider health report"""
        try:
            report = {
                "timestamp": datetime.utcnow().isoformat(),
                "providers": {},
                "summary": {
                    "total_providers": len(self.providers),
                    "healthy_providers": 0,
                    "degraded_providers": 0,
                    "failed_providers": 0,
                    "recommended_provider": None
                }
            }
            
            for name, provider in self.providers.items():
                try:
                    status, details = provider.get_provider_status()
                    limits = provider.get_provider_limits()
                    
                    # Get statistics from Redis
                    stats_key = get_redis_key(f"provider_stats_{name}", "hourly")
                    stats = self.redis_client.hgetall(stats_key)
                    
                    success_count = int(stats.get(b"success_count", 0))
                    failure_count = int(stats.get(b"failure_count", 0))
                    total_count = success_count + failure_count
                    
                    success_rate = (success_count / total_count * 100) if total_count > 0 else 100
                    
                    report["providers"][name] = {
                        "status": status.value,
                        "details": details,
                        "limits": limits,
                        "statistics": {
                            "success_count": success_count,
                            "failure_count": failure_count,
                            "success_rate_percent": round(success_rate, 2)
                        }
                    }
                    
                    # Update summary counts
                    if status == ProviderStatus.HEALTHY:
                        report["summary"]["healthy_providers"] += 1
                    elif status == ProviderStatus.DEGRADED:
                        report["summary"]["degraded_providers"] += 1
                    else:
                        report["summary"]["failed_providers"] += 1
                        
                except Exception as e:
                    report["providers"][name] = {
                        "status": "error",
                        "error": str(e)
                    }
                    report["summary"]["failed_providers"] += 1
            
            # Determine recommended provider
            best_provider = self.get_best_provider()
            if best_provider:
                report["summary"]["recommended_provider"] = best_provider[0]
            
            return report
            
        except Exception as e:
            logger.error(f"Provider health report generation failed: {e}")
            return {"error": str(e)}

# Celery tasks for provider management
@celery_app.task(bind=True, queue="monitoring", name="tasks.check_provider_health")
def check_provider_health(self):
    """Check health of all email providers"""
    try:
        manager = EmailProviderManager()
        health_report = manager.get_provider_health_report()
        
        # Store health report
        health_key = get_redis_key("provider_health", "latest")
        redis_client = redis.Redis.from_url(settings.REDIS_URL)
        redis_client.setex(health_key, 300, json.dumps(health_report, default=str))  # 5 minutes
        
        # Log critical provider failures
        failed_providers = health_report["summary"]["failed_providers"]
        if failed_providers > 0:
            log_system_event(
                AuditEventType.SYSTEM_STARTUP,  # Using available event type
                {
                    "failed_providers": failed_providers,
                    "total_providers": health_report["summary"]["total_providers"],
                    "health_check": "provider_monitoring"
                },
                AuditSeverity.WARNING if failed_providers < len(manager.providers) else AuditSeverity.CRITICAL
            )
        
        return health_report
        
    except Exception as e:
        logger.error(f"Provider health check task failed: {e}")
        return {"error": str(e)}

# Global provider manager instance
email_provider_manager = EmailProviderManager()

# Convenience function for getting email service with failover
def get_email_service_with_failover():
    """Get email service with automatic failover support"""
    return email_provider_manager

