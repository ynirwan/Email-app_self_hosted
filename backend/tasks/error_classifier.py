# backend/tasks/error_classifier.py
"""
Standalone provider error classification module.
Imported by both email_campaign_tasks.py and ab_testing.py.

Returns structured classification dicts used to drive auto-pause / auto-fail
logic and surface actionable human messages to users.
"""

import re
import logging
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


# ── Enums ─────────────────────────────────────────────────────────────────────

class ProviderErrorClass(str, Enum):
    CONFIG_ERROR = "config_error"   # permanent — user must fix settings
    LIMIT_ERROR  = "limit_error"    # soft — quota/rate, resumable
    TRANSIENT    = "transient"      # retry with backoff
    UNKNOWN      = "unknown"        # treat as transient, pause after N fails


class ProviderErrorType(str, Enum):
    AUTH_FAILED           = "auth_failed"
    SENDER_NOT_AUTHORIZED = "sender_not_authorized"
    DOMAIN_NOT_VERIFIED   = "domain_not_verified"
    BAD_SENDER_FORMAT     = "bad_sender_format"
    ACCOUNT_SUSPENDED     = "account_suspended"
    TLS_REQUIRED          = "tls_required"
    CONNECTION_REFUSED    = "connection_refused"
    NO_PROVIDER           = "no_provider"

    DAILY_QUOTA_EXCEEDED  = "daily_quota_exceeded"
    RATE_LIMITED          = "rate_limited"
    HOURLY_LIMIT          = "hourly_limit"

    SERVICE_UNAVAILABLE   = "service_unavailable"
    LOCAL_ERROR           = "local_error"
    CONNECTION_TIMEOUT    = "connection_timeout"

    UNKNOWN_ERROR         = "unknown_error"


# ── Human-readable messages ───────────────────────────────────────────────────

_HUMAN_MESSAGES: dict[ProviderErrorType, str] = {
    ProviderErrorType.AUTH_FAILED: (
        "SMTP authentication failed. Your username or password is incorrect. "
        "Update your SMTP credentials in Settings → Email."
    ),
    ProviderErrorType.SENDER_NOT_AUTHORIZED: (
        "Your sender email or name is not authorized on your email provider. "
        "Verify your sender identity in your provider dashboard."
    ),
    ProviderErrorType.DOMAIN_NOT_VERIFIED: (
        "Your sending domain is not verified. "
        "Check domain verification status with your email provider."
    ),
    ProviderErrorType.BAD_SENDER_FORMAT: (
        "The From address format is invalid. "
        "Check sender email in campaign settings."
    ),
    ProviderErrorType.ACCOUNT_SUSPENDED: (
        "Your email provider account appears suspended or blocked. "
        "Contact your email provider."
    ),
    ProviderErrorType.TLS_REQUIRED: (
        "Your SMTP connection requires TLS/STARTTLS. "
        "Check port and TLS settings in Settings → Email."
    ),
    ProviderErrorType.CONNECTION_REFUSED: (
        "Could not connect to your SMTP server. "
        "Check hostname and port in Settings → Email."
    ),
    ProviderErrorType.NO_PROVIDER: (
        "No email provider is configured or reachable. "
        "Configure your SMTP/SES settings in Settings → Email."
    ),
    ProviderErrorType.DAILY_QUOTA_EXCEEDED: (
        "Your email provider's daily sending limit has been reached. "
        "The campaign has been paused and can be resumed after your quota resets."
    ),
    ProviderErrorType.RATE_LIMITED: (
        "Your email provider is throttling sends. "
        "The campaign has been paused. You can resume shortly."
    ),
    ProviderErrorType.HOURLY_LIMIT: (
        "Your email provider's hourly limit was reached. "
        "The campaign has been paused and can be resumed when the limit resets."
    ),
    ProviderErrorType.SERVICE_UNAVAILABLE: (
        "Email provider temporarily unavailable. Will retry automatically."
    ),
    ProviderErrorType.LOCAL_ERROR: (
        "Temporary provider processing error. Will retry automatically."
    ),
    ProviderErrorType.CONNECTION_TIMEOUT: (
        "Connection to email provider timed out. Will retry automatically."
    ),
    ProviderErrorType.UNKNOWN_ERROR: (
        "An unknown provider error occurred. Will retry automatically."
    ),
}


# ── Core classifier ───────────────────────────────────────────────────────────

def classify_submission_error(error_message: str | None) -> dict:
    """
    Classify a provider error string into a structured dict.

    Returns:
        {
            "error_class":   ProviderErrorClass,
            "error_type":    ProviderErrorType,
            "is_resumable":  bool,   # True only for LIMIT_ERROR
            "human_message": str,    # user-facing, actionable
            "raw_message":   str,    # original error string
        }
    """
    raw = (error_message or "").strip()
    msg = raw.lower()

    # ── No provider at all ────────────────────────────────────────────────────
    if not msg or "no healthy email providers" in msg:
        return _result(
            ProviderErrorClass.CONFIG_ERROR,
            ProviderErrorType.NO_PROVIDER,
            is_resumable=False,
            raw=raw,
        )

    # ── CONFIG errors (permanent) ─────────────────────────────────────────────

    # Auth / credentials
    if any(k in msg for k in ("535", "authentication", "auth", "credentials", "username", "password")):
        return _result(ProviderErrorClass.CONFIG_ERROR, ProviderErrorType.AUTH_FAILED, raw=raw)

    # Sender not authorized  (530, or 553+sender/from)
    if "530" in msg or "sender name is not valid" in msg or "sender not authorized" in msg:
        return _result(ProviderErrorClass.CONFIG_ERROR, ProviderErrorType.SENDER_NOT_AUTHORIZED, raw=raw)

    if "553" in msg and any(k in msg for k in ("sender", "from")):
        return _result(ProviderErrorClass.CONFIG_ERROR, ProviderErrorType.SENDER_NOT_AUTHORIZED, raw=raw)

    # Domain not verified
    if "550" in msg and any(k in msg for k in ("domain", "verify", "verified")):
        return _result(ProviderErrorClass.CONFIG_ERROR, ProviderErrorType.DOMAIN_NOT_VERIFIED, raw=raw)

    # Bad sender format
    if "501" in msg and any(k in msg for k in ("from", "sender", "malformed")):
        return _result(ProviderErrorClass.CONFIG_ERROR, ProviderErrorType.BAD_SENDER_FORMAT, raw=raw)

    # Account suspended / blocked
    if "521" in msg or ("554" in msg and any(k in msg for k in ("suspend", "blocked", "account"))):
        return _result(ProviderErrorClass.CONFIG_ERROR, ProviderErrorType.ACCOUNT_SUSPENDED, raw=raw)

    # TLS required
    if "538" in msg or "starttls" in msg or "must use tls" in msg:
        return _result(ProviderErrorClass.CONFIG_ERROR, ProviderErrorType.TLS_REQUIRED, raw=raw)

    # Connection refused / DNS failure
    if any(k in msg for k in ("connection refused", "no route to host", "name or service not known")):
        return _result(ProviderErrorClass.CONFIG_ERROR, ProviderErrorType.CONNECTION_REFUSED, raw=raw)

    # ── LIMIT errors (resumable) ──────────────────────────────────────────────

    if any(k in msg for k in ("quota exceeded", "daily sending quota", "daily limit")):
        return _result(ProviderErrorClass.LIMIT_ERROR, ProviderErrorType.DAILY_QUOTA_EXCEEDED, is_resumable=True, raw=raw)

    if any(k in msg for k in ("429", "too many requests", "rate limit")):
        return _result(ProviderErrorClass.LIMIT_ERROR, ProviderErrorType.RATE_LIMITED, is_resumable=True, raw=raw)

    if any(k in msg for k in ("452", "too many recipients", "hourly")):
        return _result(ProviderErrorClass.LIMIT_ERROR, ProviderErrorType.HOURLY_LIMIT, is_resumable=True, raw=raw)

    # ── TRANSIENT errors ──────────────────────────────────────────────────────

    if any(k in msg for k in ("421", "service temporarily", "try again later")):
        return _result(ProviderErrorClass.TRANSIENT, ProviderErrorType.SERVICE_UNAVAILABLE, raw=raw)

    if any(k in msg for k in ("451", "local error")):
        return _result(ProviderErrorClass.TRANSIENT, ProviderErrorType.LOCAL_ERROR, raw=raw)

    if any(k in msg for k in ("timeout", "timed out")):
        return _result(ProviderErrorClass.TRANSIENT, ProviderErrorType.CONNECTION_TIMEOUT, raw=raw)

    # ── UNKNOWN fallback ──────────────────────────────────────────────────────
    return _result(ProviderErrorClass.UNKNOWN, ProviderErrorType.UNKNOWN_ERROR, raw=raw)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _result(
    error_class: ProviderErrorClass,
    error_type: ProviderErrorType,
    *,
    is_resumable: bool = False,
    raw: str = "",
) -> dict:
    return {
        "error_class":   error_class,
        "error_type":    error_type,
        "is_resumable":  is_resumable,
        "human_message": _HUMAN_MESSAGES.get(error_type, "An unexpected provider error occurred."),
        "raw_message":   raw,
    }


def extract_smtp_code(error_message: str | None) -> int | None:
    """Extract the first 4xx/5xx SMTP code from an error string."""
    match = re.search(r'\b([45]\d{2})\b', error_message or "")
    return int(match.group(1)) if match else None