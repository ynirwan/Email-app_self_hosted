# backend/tasks/campaign/provider_manager.py
# ─────────────────────────────────────────────────────────────────────────────
# TWO TARGETED FIXES:
#
# FIX 1 — SMTPEmailService.get_provider_status()
#   The old implementation did a full SMTP login on every health check.
#   Called once per email, this hammers your SMTP server with login attempts,
#   causing rate-limit failures/timeouts → provider marked FAILED → "No healthy
#   email providers available".
#   New approach: TCP-only ping to confirm reachability. No login attempt.
#   Actual credential validity is already proven when the test connection
#   succeeds in the settings UI.
#
# FIX 2 — EmailProviderManager.load_provider_configurations()
#   When reading the nested email_smtp format, the provider field was ignored
#   and email_service was always hardcoded to "smtp". This caused issues if
#   the provider field contained values like "amazonses" etc. Now correctly
#   maps provider → email_service.  For plain SMTP this makes no difference
#   but is correct for future-proofing.
# ─────────────────────────────────────────────────────────────────────────────
import logging
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum
from abc import ABC, abstractmethod
from celery_app import celery_app
from database import get_sync_settings_collection
from tasks.task_config import task_settings, get_redis_key
from .rate_limiter import EmailProvider
from .audit_logger import log_system_event, AuditEventType, AuditSeverity
import redis
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

ENCRYPTION_KEY = task_settings.MASTER_ENCRYPTION_KEY


def decrypt_smtp_password(encrypted_password: str) -> str:
    """Decrypt password using same Fernet key as email_settings.py"""
    try:
        if not encrypted_password:
            return ""
        if not encrypted_password.startswith("gAAAAA"):
            return encrypted_password  # plaintext, use as-is
        fernet = Fernet(ENCRYPTION_KEY.encode())
        decrypted = fernet.decrypt(encrypted_password.encode())
        logger.info("✅ Password decrypted successfully")
        return decrypted.decode()
    except Exception as e:
        logger.error(f"❌ Password decryption failed: {e}")
        return encrypted_password


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


class EmailServiceInterface(ABC):
    @abstractmethod
    def send_email(
        self,
        sender_email: str,
        recipient_email: str,
        subject: str,
        html_content: str,
        text_content: str = None,
        **kwargs,
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_provider_status(self) -> Tuple[ProviderStatus, Dict[str, Any]]:
        pass

    @abstractmethod
    def get_provider_limits(self) -> Dict[str, Any]:
        pass


class SMTPEmailService(EmailServiceInterface):
    """Generic SMTP email service"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.smtp_server = config.get("smtp_server")
        self.smtp_port = config.get("smtp_port", 587)
        self.username = config.get("username")
        self.password = config.get("password")
        self.use_tls = config.get("use_tls", True)

    def send_email(
        self,
        sender_email: str,
        recipient_email: str,
        subject: str,
        html_content: str,
        text_content: str = None,
        **kwargs,
    ) -> Dict[str, Any]:
        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = sender_email
            message["To"] = recipient_email

            reply_to = kwargs.get("reply_to")
            if reply_to:
                message["Reply-To"] = reply_to

            unsubscribe_url = kwargs.get("unsubscribe_url")
            if unsubscribe_url and unsubscribe_url != "#":
                message["List-Unsubscribe"] = f"<{unsubscribe_url}>"
                message["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

            configuration_set = kwargs.get("configuration_set")
            if configuration_set:
                message["X-SES-CONFIGURATION-SET"] = configuration_set

            if text_content:
                message.attach(MIMEText(text_content, "plain"))
            if html_content:
                message.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10) as server:
                if self.use_tls:
                    server.starttls()
                if self.username and self.password:
                    server.login(self.username, self.password)
                server.send_message(message)

            return {
                "success": True,
                "message_id": f"smtp_{int(time.time() * 1000)}",
                "provider": "smtp",
                "cost": 0.0,
            }
        except Exception as e:
            return {
                "success": False,
                "message_id": None,
                "error": f"SMTP send failed: {str(e)}",
                "provider": "smtp",
            }

    def get_provider_status(self) -> Tuple[ProviderStatus, Dict[str, Any]]:
        """
        FIX 1: TCP-only connectivity check — no login attempt.

        The old version did a full SMTP login on every health check.
        With get_best_provider() called once per email this hammered the SMTP
        server with login attempts, triggering rate-limits/timeouts and causing
        the provider to be marked FAILED even though credentials are fine.

        A TCP connect + EHLO is enough to confirm the server is reachable.
        Credential validity is verified once at settings-save time via the
        test-connection endpoint.
        """
        if not self.smtp_server:
            return ProviderStatus.FAILED, {"error": "smtp_server not configured"}

        try:
            import smtplib

            start_time = time.time()

            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=5) as server:
                # Just EHLO — confirms TCP reachability and server response.
                # No STARTTLS, no AUTH — avoids triggering rate limits.
                server.ehlo()

            response_time = (time.time() - start_time) * 1000
            status = (
                ProviderStatus.HEALTHY
                if response_time <= 5000
                else ProviderStatus.DEGRADED
            )

            return status, {
                "response_time_ms": round(response_time, 2),
                "connection_successful": True,
                "server": self.smtp_server,
                "port": self.smtp_port,
                "check_type": "tcp_ehlo",  # not a full login
            }
        except Exception as e:
            return ProviderStatus.FAILED, {
                "error": str(e),
                "connection_successful": False,
                "server": self.smtp_server,
                "port": self.smtp_port,
            }

    def get_provider_limits(self) -> Dict[str, Any]:
        return {
            "emails_per_second": 14,
            "emails_per_hour": 50400,
            "daily_quota": 10000,
            "monthly_quota": 300000,
        }


class SESEmailService(EmailServiceInterface):
    """AWS SES via SMTP (smtp_server present) or API (boto3)"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.smtp_server = config.get("smtp_server")
        self.smtp_port = config.get("smtp_port", 587)
        self.username = config.get("username") or config.get("access_key")
        self.password = config.get("password") or config.get("secret_key")
        self.use_tls = config.get("use_tls", True)
        self.region = config.get("region", "us-east-1")
        self.access_key = config.get("access_key") or config.get("username")
        self.secret_key = config.get("secret_key") or config.get("password")
        self.use_smtp_mode = bool(self.smtp_server)

    def send_email(
        self,
        sender_email: str,
        recipient_email: str,
        subject: str,
        html_content: str,
        text_content: str = None,
        **kwargs,
    ) -> Dict[str, Any]:
        if self.use_smtp_mode:
            # Delegate to SMTPEmailService logic
            smtp_svc = SMTPEmailService(self.config)
            return smtp_svc.send_email(
                sender_email,
                recipient_email,
                subject,
                html_content,
                text_content,
                **kwargs,
            )
        # API mode
        try:
            import boto3

            ses = boto3.client(
                "ses",
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
            )
            body = {"Html": {"Data": html_content, "Charset": "UTF-8"}}
            if text_content:
                body["Text"] = {"Data": text_content, "Charset": "UTF-8"}
            kw = dict(
                Source=sender_email,
                Destination={"ToAddresses": [recipient_email]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": body,
                },
            )
            cfg_set = kwargs.get("configuration_set")
            if cfg_set:
                kw["ConfigurationSetName"] = cfg_set
            resp = ses.send_email(**kw)
            return {
                "success": True,
                "message_id": resp["MessageId"],
                "provider": "ses_api",
                "cost": 0.0001,
            }
        except Exception as e:
            return {
                "success": False,
                "message_id": None,
                "error": f"SES API send failed: {str(e)}",
                "provider": "ses_api",
            }

    def get_provider_status(self) -> Tuple[ProviderStatus, Dict[str, Any]]:
        if self.use_smtp_mode:
            # Use the same lightweight TCP check
            smtp_svc = SMTPEmailService(self.config)
            return smtp_svc.get_provider_status()
        try:
            import boto3

            start = time.time()
            ses = boto3.client(
                "ses",
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
            )
            resp = ses.get_send_quota()
            rt = (time.time() - start) * 1000
            used_pct = (resp["SentLast24Hours"] / resp["Max24HourSend"]) * 100
            status = (
                ProviderStatus.DEGRADED
                if used_pct > 90 or rt > 3000
                else ProviderStatus.HEALTHY
            )
            return status, {
                "response_time_ms": round(rt, 2),
                "quota_used_percent": round(used_pct, 2),
                "max_24h_send": resp["Max24HourSend"],
                "sent_last_24h": resp["SentLast24Hours"],
            }
        except Exception as e:
            return ProviderStatus.FAILED, {"error": str(e)}

    def get_provider_limits(self) -> Dict[str, Any]:
        return {
            "emails_per_second": 14,
            "emails_per_hour": 50400,
            "daily_quota": 200,
            "monthly_quota": 6000,
        }


class SendGridEmailService(EmailServiceInterface):
    def __init__(self, config: Dict[str, Any]):
        self.api_key = config.get("api_key") or config.get("password")
        self.base_url = "https://api.sendgrid.com/v3"

    def send_email(
        self,
        sender_email: str,
        recipient_email: str,
        subject: str,
        html_content: str,
        text_content: str = None,
        **kwargs,
    ) -> Dict[str, Any]:
        try:
            import requests

            payload = {
                "personalizations": [
                    {"to": [{"email": recipient_email}], "subject": subject}
                ],
                "from": {"email": sender_email},
                "content": [],
            }
            if text_content:
                payload["content"].append({"type": "text/plain", "value": text_content})
            if html_content:
                payload["content"].append({"type": "text/html", "value": html_content})
            resp = requests.post(
                f"{self.base_url}/mail/send",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=task_settings.EMAIL_SEND_TIMEOUT_SECONDS,
            )
            if resp.status_code == 202:
                return {
                    "success": True,
                    "message_id": resp.headers.get("X-Message-Id"),
                    "provider": "sendgrid",
                    "cost": 0.0001,
                }
            return {
                "success": False,
                "message_id": None,
                "error": f"SendGrid {resp.status_code}: {resp.text}",
                "provider": "sendgrid",
            }
        except Exception as e:
            return {
                "success": False,
                "message_id": None,
                "error": f"SendGrid send failed: {str(e)}",
                "provider": "sendgrid",
            }

    def get_provider_status(self) -> Tuple[ProviderStatus, Dict[str, Any]]:
        try:
            import requests

            start = time.time()
            resp = requests.get(
                f"{self.base_url}/user/account",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=5,
            )
            rt = (time.time() - start) * 1000
            if resp.status_code == 200:
                return ProviderStatus.HEALTHY, {"response_time_ms": round(rt, 2)}
            return ProviderStatus.DEGRADED, {
                "response_time_ms": round(rt, 2),
                "status_code": resp.status_code,
            }
        except Exception as e:
            return ProviderStatus.FAILED, {"error": str(e)}

    def get_provider_limits(self) -> Dict[str, Any]:
        return {
            "emails_per_second": 100,
            "emails_per_hour": 360000,
            "daily_quota": 100000,
            "monthly_quota": 3000000,
        }


class EmailProviderManager:
    """Email provider manager with failover and load balancing"""

    # ── Per-worker provider cache ─────────────────────────────────────────────
    # Health check is expensive (TCP round-trip). We cache the result in worker
    # memory and only re-check after HEALTH_CHECK_INTERVAL seconds, or when a
    # send actually fails (error-driven re-evaluation).
    HEALTH_CHECK_INTERVAL = 120  # seconds between proactive health checks

    def __init__(self):
        self.redis_client = redis.Redis.from_url(task_settings.REDIS_URL)
        self.providers: Dict[str, EmailServiceInterface] = {}
        self.provider_configs: Dict[str, Any] = {}
        # Worker-local cache: { provider_name: (ProviderStatus, details, checked_at) }
        self._health_cache: Dict[str, Tuple[ProviderStatus, Dict, float]] = {}
        # Name of the provider currently in use — sticky until it errors
        self._current_provider: Optional[str] = None
        self.load_provider_configurations()

    def load_provider_configurations(self):
        """
        FIX 2: correctly map provider field → email_service when reading
        the nested email_smtp format.  Plain SMTP users are unaffected
        (provider is empty/custom → falls through to smtp branch).
        """
        try:
            settings_collection = get_sync_settings_collection()

            # ── Legacy flat format ───────────────────────────────────────────
            email_config = settings_collection.find_one({"type": "smtp"})

            # ── Current nested format ────────────────────────────────────────
            if not email_config:
                doc = settings_collection.find_one({"type": "email_smtp"})
                if doc and "config" in doc:
                    cfg = doc["config"]

                    decrypted_pw = decrypt_smtp_password(cfg.get("password", ""))

                    provider_field = (cfg.get("provider") or "smtp").lower()

                    # Map provider name → internal email_service key
                    if provider_field == "amazonses":
                        email_service = "ses"
                    elif provider_field == "sendgrid":
                        email_service = "sendgrid"
                    elif provider_field == "mailgun":
                        email_service = "mailgun"
                    else:
                        # gmail, yahoo, outlook, custom, managed_service, smtp, ""
                        email_service = "smtp"

                    email_config = {
                        "email_service": email_service,
                        "smtp_server": cfg.get("smtp_server"),
                        "smtp_port": cfg.get("smtp_port", 587),
                        "username": cfg.get("username"),
                        "password": decrypted_pw,
                        "use_tls": cfg.get("use_tls", True),
                        # SES API fields (only used when provider == amazonses + ses_type == api)
                        "region": cfg.get("aws_region", "us-east-1"),
                        "access_key": cfg.get("username"),
                        "secret_key": decrypted_pw,
                    }
                    logger.info(
                        f"Loaded email config from 'email_smtp' format — "
                        f"provider='{provider_field}' → email_service='{email_service}', "
                        f"smtp_server='{email_config['smtp_server']}'"
                    )

            if task_settings.MOCK_EMAIL_SENDING:
                self._setup_mock_provider()
                logger.info("MOCK_EMAIL_SENDING=True — using mock provider")
                return

            if email_config:
                svc = email_config.get("email_service", "smtp").lower()
                if svc == "sendgrid":
                    self._setup_sendgrid_provider(email_config)
                elif svc in ("ses", "amazonses"):
                    self._setup_ses_provider(email_config)
                elif svc == "mailgun":
                    self._setup_mailgun_provider(email_config)
                else:
                    self._setup_smtp_provider(email_config)

                logger.info(
                    f"✅ {len(self.providers)} provider(s) loaded: "
                    f"{list(self.providers.keys())}"
                )
            else:
                logger.warning(
                    "⚠️ No email provider config found in DB — "
                    "worker starting in degraded mode."
                )

        except Exception as e:
            logger.error(f"Failed to load provider configurations: {e}", exc_info=True)
            # Don't raise — let worker start; tasks will fail with a clear message.

    def _setup_smtp_provider(self, config: Dict[str, Any]):
        pc = {
            "smtp_server": config.get("smtp_server"),
            "smtp_port": config.get("smtp_port", 587),
            "username": config.get("username"),
            "password": config.get("password"),
            "use_tls": config.get("use_tls", True),
            "type": ProviderType.SMTP,
        }
        self.provider_configs["smtp"] = pc
        self.providers["smtp"] = SMTPEmailService(pc)

    def _setup_ses_provider(self, config: Dict[str, Any]):
        pc = {
            "smtp_server": config.get("smtp_server"),
            "smtp_port": config.get("smtp_port", 587),
            "username": config.get("username") or config.get("access_key"),
            "password": config.get("password") or config.get("secret_key"),
            "use_tls": config.get("use_tls", True),
            "region": config.get("region", "us-east-1"),
            "access_key": config.get("access_key") or config.get("username"),
            "secret_key": config.get("secret_key") or config.get("password"),
            "type": ProviderType.SES,
        }
        self.provider_configs["ses"] = pc
        self.providers["ses"] = SESEmailService(pc)

    def _setup_sendgrid_provider(self, config: Dict[str, Any]):
        pc = {
            "api_key": config.get("api_key") or config.get("password"),
            "type": ProviderType.SENDGRID,
        }
        self.provider_configs["sendgrid"] = pc
        self.providers["sendgrid"] = SendGridEmailService(pc)

    def _setup_mailgun_provider(self, config: Dict[str, Any]):
        # Mailgun over SMTP
        pc = {
            "smtp_server": config.get("smtp_server", "smtp.mailgun.org"),
            "smtp_port": config.get("smtp_port", 587),
            "username": config.get("username"),
            "password": config.get("password"),
            "use_tls": True,
            "type": ProviderType.SMTP,
        }
        self.provider_configs["mailgun"] = pc
        self.providers["mailgun"] = SMTPEmailService(pc)

    def _setup_mock_provider(self):
        class _Mock(EmailServiceInterface):
            def send_email(self, *a, **kw):
                import random as _r

                time.sleep(_r.uniform(0.01, 0.05))
                return {
                    "success": True,
                    "message_id": f"mock_{int(time.time() * 1000)}",
                    "provider": "mock",
                    "cost": 0.0,
                }

            def get_provider_status(self):
                return ProviderStatus.HEALTHY, {"mock": True}

            def get_provider_limits(self):
                return {"emails_per_second": 1000}

        self.provider_configs["mock"] = {"type": "mock"}
        self.providers["mock"] = _Mock()

    def get_best_provider(
        self, campaign_id: str = None
    ) -> Optional[Tuple[str, EmailServiceInterface]]:
        """
        Return the current sticky provider without doing a health check.

        Strategy:
          1. If we already have a working provider (_current_provider), return it
             immediately — no health check, no DB hit, no TCP round-trip.
          2. If we have no current provider (first call, or previous one errored),
             run a one-time health check across all providers, pick the best,
             and cache it as sticky.
          3. Health check results are cached per-worker for HEALTH_CHECK_INTERVAL
             seconds so even the initial selection is cheap on retries.

        A provider is only evicted from _current_provider when send_email_with_failover
        receives an actual send failure — not based on periodic polling.
        """
        try:
            if not self.providers:
                logger.error("No email providers configured")
                return None

            # ── Fast path: reuse sticky provider ─────────────────────────────
            if self._current_provider and self._current_provider in self.providers:
                return self._current_provider, self.providers[self._current_provider]

            # ── Slow path: pick best provider via cached health check ─────────
            now = time.time()
            provider_health = {}

            for name, provider in self.providers.items():
                cached = self._health_cache.get(name)
                if cached and (now - cached[2]) < self.HEALTH_CHECK_INTERVAL:
                    # Use cached result — no TCP call
                    status, details, _ = cached
                else:
                    # Cache miss or expired — do one real check and cache it
                    try:
                        status, details = provider.get_provider_status()
                    except Exception as e:
                        status, details = ProviderStatus.FAILED, {"error": str(e)}
                    self._health_cache[name] = (status, details, now)

                provider_health[name] = {
                    "status": status,
                    "details": details,
                    "provider": provider,
                }

            healthy = [
                (n, i)
                for n, i in provider_health.items()
                if i["status"] in (ProviderStatus.HEALTHY, ProviderStatus.DEGRADED)
            ]

            if not healthy:
                logger.error("No healthy email providers available")
                self._current_provider = None
                return None

            healthy.sort(
                key=lambda x: (
                    0 if x[1]["status"] == ProviderStatus.HEALTHY else 1,
                    x[1]["details"].get("response_time_ms", 1000),
                )
            )
            best_name, best_info = healthy[0]

            # Pin this provider as the sticky choice for this worker
            self._current_provider = best_name
            logger.info(f"Provider selected: {best_name}")
            return best_name, best_info["provider"]

        except Exception as e:
            logger.error(f"Provider selection failed: {e}")
            return None

    def _mark_provider_failed(self, provider_name: str):
        """
        Called when a real send error occurs.
        Evicts the provider from cache and clears the sticky selection so the
        next call to get_best_provider() re-evaluates all providers.
        """
        self._health_cache.pop(provider_name, None)
        if self._current_provider == provider_name:
            self._current_provider = None
            logger.warning(
                f"Provider {provider_name} failed — will re-select on next send"
            )

    def send_email_with_failover(
        self,
        sender_email: str,
        recipient_email: str,
        subject: str,
        html_content: str,
        text_content: str = None,
        campaign_id: str = None,
        **kwargs,
    ) -> Dict[str, Any]:
        attempted: list = []
        last_error = None
        max_attempts = min(len(self.providers), 3)

        for _ in range(max_attempts):
            info = self.get_best_provider(campaign_id)
            if not info:
                break
            pname, provider = info
            if pname in attempted:
                continue
            attempted.append(pname)

            try:
                result = provider.send_email(
                    sender_email=sender_email,
                    recipient_email=recipient_email,
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content,
                    **kwargs,
                )
                result["attempted_providers"] = attempted
                result["selected_provider"] = pname

                if result.get("success"):
                    self._record_provider_result(pname, True, campaign_id)
                    return result

                self._record_provider_result(pname, False, campaign_id)
                last_error = result.get("error", "Unknown error")
                if self._is_permanent_failure(last_error):
                    result["permanent_failure"] = True
                    return result
                continue

            except Exception as e:
                last_error = str(e)
                self._record_provider_result(pname, False, campaign_id)
                logger.error(f"Provider {pname} raised: {e}")
                continue

        return {
            "success": False,
            "message_id": None,
            "error": f"All email providers failed. Last error: {last_error}",
            "attempted_providers": attempted,
            "total_attempts": len(attempted),
        }

    def _record_provider_result(
        self, provider_name: str, success: bool, campaign_id: str = None
    ):
        try:
            key = get_redis_key(f"provider_stats_{provider_name}", "hourly")
            self.redis_client.hincrby(
                key, "success_count" if success else "failure_count", 1
            )
            self.redis_client.expire(key, 3600)
        except Exception as e:
            logger.error(f"Failed to record provider result: {e}")

    def _is_permanent_failure(self, error_message: str) -> bool:
        permanent = [
            "invalid_email",
            "blacklisted",
            "suppressed",
            "unsubscribed",
            "domain_not_found",
            "recipient_not_found",
            "mailbox_full",
        ]
        msg = (error_message or "").lower()
        return any(p in msg for p in permanent)

    def get_provider_health_report(self) -> Dict[str, Any]:
        try:
            report: Dict[str, Any] = {
                "generated_at": datetime.utcnow().isoformat(),
                "providers": {},
                "summary": {
                    "total_providers": len(self.providers),
                    "healthy_providers": 0,
                    "degraded_providers": 0,
                    "failed_providers": 0,
                    "recommended_provider": None,
                },
            }
            for name, provider in self.providers.items():
                try:
                    status, details = provider.get_provider_status()
                    report["providers"][name] = {
                        "status": status.value,
                        "details": details,
                        "limits": provider.get_provider_limits(),
                    }
                    if status == ProviderStatus.HEALTHY:
                        report["summary"]["healthy_providers"] += 1
                    elif status == ProviderStatus.DEGRADED:
                        report["summary"]["degraded_providers"] += 1
                    else:
                        report["summary"]["failed_providers"] += 1
                except Exception as e:
                    report["providers"][name] = {"status": "error", "error": str(e)}
                    report["summary"]["failed_providers"] += 1
            best = self.get_best_provider()
            if best:
                report["summary"]["recommended_provider"] = best[0]
            return report
        except Exception as e:
            return {"error": str(e)}


# Global singleton
email_provider_manager = EmailProviderManager()


def get_email_service_with_failover():
    """Backward-compat accessor."""
    return email_provider_manager


@celery_app.task(bind=True, queue="monitoring", name="tasks.check_provider_health")
def check_provider_health(self):
    """Periodic health check task — caches result in Redis for 5 minutes."""
    try:
        manager = EmailProviderManager()
        report = manager.get_provider_health_report()
        rc = redis.Redis.from_url(task_settings.REDIS_URL)
        rc.setex(
            get_redis_key("provider_health", "latest"),
            300,
            json.dumps(report, default=str),
        )
        failed = report["summary"]["failed_providers"]
        if failed > 0:
            log_system_event(
                AuditEventType.SYSTEM_STARTUP,
                {
                    "failed_providers": failed,
                    "total_providers": report["summary"]["total_providers"],
                },
                AuditSeverity.WARNING
                if failed < len(manager.providers)
                else AuditSeverity.CRITICAL,
            )
        return report
    except Exception as e:
        logger.error(f"Provider health check task failed: {e}")
        return {"error": str(e)}
