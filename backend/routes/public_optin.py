"""
Public opt-in endpoints — no authentication required.

Endpoints:
  GET  /public/list-meta/{list_id}       — returns list schema for dynamic form rendering
  POST /public/opt-in                    — subscribe with double opt-in confirmation email
  GET  /public/confirm/{token}           — activate a pending_confirmation subscriber

Security:
  - Redis-backed rate limiting (10 submissions / 15 min per IP) — fails open if Redis unavailable
  - CORS is open for these routes (configured in main.py)
  - Confirmation tokens are uuid4 hex (128-bit) with 48 h expiry

Suppression safety:
  - pending_confirmation status is intentionally excluded from campaign send queries (status='active')
  - Campaign send guards in email_campaign_processor.py query `status: active`, so pending subscribers
    are never emailed campaign content.
"""

import logging
import uuid
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import HTMLResponse

from database import get_subscribers_collection, get_lists_collection
from schemas.subscriber_schema import (
    STANDARD_FIELD_NAMES,
    PublicOptInRequest,
    SubscriberStatus,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["public"])

# ── Constants ─────────────────────────────────────────────────────────────────

TOKEN_TTL_HOURS = 48
RATE_LIMIT_WINDOW = 900   # 15 minutes in seconds
RATE_LIMIT_MAX    = 10    # submissions per window per IP

# ── HTML templates ────────────────────────────────────────────────────────────

_CONFIRMED_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Subscription Confirmed</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:#f0fdf4;min-height:100vh;display:flex;align-items:center;justify-content:center}
    .card{background:#fff;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.08);
          padding:48px 40px;text-align:center;max-width:440px;width:90%}
    .ico{width:64px;height:64px;background:#dcfce7;border-radius:50%;
         display:flex;align-items:center;justify-content:center;margin:0 auto 20px}
    .ico svg{width:32px;height:32px;stroke:#16a34a;fill:none;stroke-width:2.5;
             stroke-linecap:round;stroke-linejoin:round}
    h1{font-size:22px;font-weight:700;color:#111;margin-bottom:10px}
    p{color:#6b7280;line-height:1.6;font-size:15px}
  </style>
</head>
<body>
  <div class="card">
    <div class="ico"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></div>
    <h1>You're confirmed!</h1>
    <p>Your subscription has been confirmed. You'll start receiving emails shortly.</p>
  </div>
</body>
</html>"""

_ALREADY_CONFIRMED_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Already Confirmed</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:#eff6ff;min-height:100vh;display:flex;align-items:center;justify-content:center}
    .card{background:#fff;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.08);
          padding:48px 40px;text-align:center;max-width:440px;width:90%}
    h1{font-size:22px;font-weight:700;color:#1d4ed8;margin-bottom:10px}
    p{color:#6b7280;line-height:1.6;font-size:15px}
  </style>
</head>
<body>
  <div class="card">
    <h1>Already confirmed</h1>
    <p>This email address is already subscribed and confirmed. No further action is needed.</p>
  </div>
</body>
</html>"""

_EXPIRED_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Link Expired</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:#fef2f2;min-height:100vh;display:flex;align-items:center;justify-content:center}
    .card{background:#fff;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.08);
          padding:48px 40px;text-align:center;max-width:440px;width:90%}
    h1{font-size:22px;font-weight:700;color:#dc2626;margin-bottom:10px}
    p{color:#6b7280;line-height:1.6;font-size:15px}
  </style>
</head>
<body>
  <div class="card">
    <h1>Link expired</h1>
    <p>This confirmation link has expired (links are valid for 48 hours). Please sign up again to get a new link.</p>
  </div>
</body>
</html>"""

_INVALID_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Invalid Link</title>
  <style>
    *{box-sizing:border-box;margin:0;padding:0}
    body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
         background:#fef2f2;min-height:100vh;display:flex;align-items:center;justify-content:center}
    .card{background:#fff;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.08);
          padding:48px 40px;text-align:center;max-width:440px;width:90%}
    h1{font-size:22px;font-weight:700;color:#dc2626;margin-bottom:10px}
    p{color:#6b7280;line-height:1.6;font-size:15px}
  </style>
</head>
<body>
  <div class="card">
    <h1>Invalid link</h1>
    <p>This confirmation link is invalid or has already been used.</p>
  </div>
</body>
</html>"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _rate_limit_optin(request: Request) -> None:
    """
    Enforce 10 opt-in submissions per IP per 15-minute window using Redis.
    Fails open (allows the request) if Redis is unavailable — avoids blocking
    legitimate subscribers due to infrastructure issues.
    """
    try:
        from core.redis_client import get_async_redis
        ip = _get_client_ip(request)
        key = f"optin:rl:{ip}"
        async with get_async_redis() as r:
            count = await r.incr(key)
            if count == 1:
                await r.expire(key, RATE_LIMIT_WINDOW)
            if count > RATE_LIMIT_MAX:
                raise HTTPException(
                    status_code=429,
                    detail="Too many subscription attempts. Please try again later.",
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[public_optin] rate-limit check failed (fails open): {e}")


def _get_allowed_fields(registry: Optional[dict]) -> tuple[set, set]:
    """
    Return (allowed_standard_fields, allowed_custom_field_names) from the list
    field registry document. If no registry exists, allow all standard fields
    and no custom fields.
    """
    if not registry:
        return set(STANDARD_FIELD_NAMES), set()

    allowed_standard = set(registry.get("standard", [])) & STANDARD_FIELD_NAMES
    allowed_custom = set(registry.get("custom", {}).keys())
    return allowed_standard, allowed_custom


def _sanitize_fields(
    raw_standard: Dict[str, Any],
    raw_custom: Dict[str, Any],
    allowed_standard: set,
    allowed_custom: set,
) -> tuple[dict, dict]:
    """
    Strip any fields not declared in the list registry.
    Silently drops unknown keys rather than rejecting the request — better UX
    for public forms that may pass extra fields.
    """
    clean_standard = {
        k: v for k, v in raw_standard.items()
        if k in allowed_standard and v not in (None, "", [], {})
    }
    clean_custom = {
        k: v for k, v in raw_custom.items()
        if k in allowed_custom and v not in (None, "", [], {})
    }
    return clean_standard, clean_custom


async def _get_smtp_config() -> Optional[dict]:
    """
    Returns SMTP config dict if email sending is configured, else None.
    Does not raise — callers should handle None gracefully.
    """
    try:
        from database import get_settings_collection
        settings_col = get_settings_collection()
        doc = await settings_col.find_one({"type": "email"})
        if not doc:
            return None
        config = doc.get("config", {})
        if config.get("smtp_choice") == "client":
            return {
                "smtp_server": config.get("smtp_server"),
                "smtp_port": int(config.get("smtp_port", 587)),
                "username": config.get("username"),
                "password": config.get("password"),
                "sender_email": config.get("username"),  # SMTP sender = login
                "sender_name": config.get("sender_name", ""),
            }
        # SES or other providers: could add support here later
        return None
    except Exception as e:
        logger.warning(f"[public_optin] could not load SMTP config: {e}")
        return None


def _build_confirmation_url(token: str, request: Request) -> str:
    """Build absolute confirmation URL from the incoming request's base URL."""
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/public/confirm/{token}"


async def _send_confirmation_email(
    email: str,
    list_name: str,
    confirm_url: str,
    smtp: dict,
) -> None:
    """
    Fire-and-forget background task: sends a double opt-in confirmation email.
    Logs errors but does not raise — failure here should not break the opt-in flow.
    """
    try:
        msg = MIMEMultipart("alternative")
        sender = smtp["sender_email"]
        sender_name = smtp.get("sender_name", "")
        msg["From"] = f"{sender_name} <{sender}>" if sender_name else sender
        msg["To"] = email
        msg["Subject"] = f"Please confirm your subscription to {list_name}"

        html_body = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Confirm your subscription</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f9fafb;
       padding:40px 20px}}
  .card{{background:#fff;border-radius:12px;box-shadow:0 2px 16px rgba(0,0,0,.07);
         max-width:480px;margin:0 auto;padding:40px 36px;text-align:center}}
  h2{{font-size:20px;font-weight:700;color:#111;margin-bottom:12px}}
  p{{color:#6b7280;line-height:1.6;font-size:15px;margin-bottom:24px}}
  .btn{{display:inline-block;background:#2563eb;color:#fff;text-decoration:none;
        padding:14px 32px;border-radius:8px;font-size:15px;font-weight:600}}
  .btn:hover{{background:#1d4ed8}}
  .note{{font-size:12px;color:#9ca3af;margin-top:20px}}
  .url{{word-break:break-all;font-size:12px;color:#9ca3af;margin-top:8px}}
</style>
</head>
<body>
  <div class="card">
    <h2>Confirm your subscription</h2>
    <p>You recently signed up for <strong>{list_name}</strong>. Click the button below
       to confirm your email address and complete your subscription.</p>
    <a href="{confirm_url}" class="btn">Confirm subscription</a>
    <p class="note">This link expires in 48 hours. If you didn't sign up, you can safely ignore this email.</p>
    <p class="url">{confirm_url}</p>
  </div>
</body>
</html>"""

        msg.attach(MIMEText(html_body, "html"))

        server = smtplib.SMTP(smtp["smtp_server"], smtp["smtp_port"], timeout=15)
        server.starttls()
        server.login(smtp["username"], smtp["password"])
        server.sendmail(sender, email, msg.as_string())
        server.quit()

        logger.info(f"[public_optin] confirmation email sent to {email} for list '{list_name}'")

    except Exception as e:
        logger.error(f"[public_optin] failed to send confirmation email to {email}: {e}")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/public/list-meta/{list_id}")
async def get_list_meta(list_id: str):
    """
    Returns list field schema for dynamic public form rendering.
    list_id is the list name (URL-encoded).

    Response:
      { list_name, standard_fields: [str, ...], custom_fields: [{ name, type }, ...] }
    """
    lists_col = get_lists_collection()
    registry = await lists_col.find_one({"list_name": list_id})

    if not registry:
        # List exists (might have subscribers) but no registry — return empty schema
        subscribers_col = get_subscribers_collection()
        any_sub = await subscribers_col.find_one({"list": list_id}, {"_id": 1})
        if not any_sub:
            raise HTTPException(status_code=404, detail="List not found")
        return {
            "list_name": list_id,
            "standard_fields": [],
            "custom_fields": [],
        }

    return {
        "list_name": registry.get("list_name", list_id),
        "standard_fields": registry.get("standard", []),
        "custom_fields": [
            {"name": k, "type": v.get("type", "string") if isinstance(v, dict) else "string"}
            for k, v in registry.get("custom", {}).items()
        ],
    }


@router.post("/public/opt-in", status_code=202)
async def public_opt_in(
    payload: PublicOptInRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Public double opt-in subscription endpoint.

    Behaviour per subscriber state:
      new              → insert as pending_confirmation, send confirmation email
      pending_conf.    → resend confirmation email (idempotent)
      active           → 202 (already subscribed, no noise)
      unsubscribed     → 422 (cannot re-subscribe via opt-in form; must be done by owner)
      bounced/inactive → 422

    Returns 202 regardless of outcome to avoid leaking subscriber existence.
    """
    await _rate_limit_optin(request)

    subscribers_col = get_subscribers_collection()
    lists_col = get_lists_collection()

    # Load registry to validate / sanitize field names
    registry = await lists_col.find_one({"list_name": payload.list_id})
    allowed_std, allowed_cust = _get_allowed_fields(registry)
    clean_std, clean_cust = _sanitize_fields(
        payload.standard_fields, payload.custom_fields, allowed_std, allowed_cust
    )

    email = payload.email
    list_name = payload.list_id

    existing = await subscribers_col.find_one(
        {"email": email, "list": list_name},
        {"status": 1, "confirmation_token": 1, "confirmation_token_created_at": 1},
    )

    smtp = await _get_smtp_config()

    if existing:
        status = existing.get("status")

        if status == SubscriberStatus.ACTIVE:
            # Already confirmed — silently accept (avoid leaking info)
            logger.info(f"[public_optin] already active: {email} on {list_name}")
            return {"message": "Thank you. Please check your email to confirm."}

        if status in (
            SubscriberStatus.UNSUBSCRIBED,
            SubscriberStatus.BOUNCED,
            SubscriberStatus.INACTIVE,
        ):
            # Cannot re-subscribe via public form — this protects against
            # malicious bulk re-subscription of opted-out addresses.
            logger.info(f"[public_optin] rejected re-subscribe attempt: {email} ({status})")
            # Return generic 202 — do NOT reveal this address is suppressed
            return {"message": "Thank you. Please check your email to confirm."}

        if status == SubscriberStatus.PENDING_CONFIRMATION:
            # Resend confirmation (idempotent — reuse existing token if still fresh)
            token = existing.get("confirmation_token")
            token_created = existing.get("confirmation_token_created_at")
            if not token or (
                token_created
                and datetime.utcnow() - token_created > timedelta(hours=TOKEN_TTL_HOURS)
            ):
                # Issue a fresh token
                token = uuid.uuid4().hex
                await subscribers_col.update_one(
                    {"_id": existing["_id"]},
                    {
                        "$set": {
                            "confirmation_token": token,
                            "confirmation_token_created_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow(),
                        }
                    },
                )

            if smtp:
                confirm_url = _build_confirmation_url(token, request)
                background_tasks.add_task(
                    _send_confirmation_email, email, list_name, confirm_url, smtp
                )
            else:
                logger.warning(
                    f"[public_optin] no SMTP config — confirmation email NOT sent to {email}"
                )

            return {"message": "Thank you. Please check your email to confirm."}

    # ── New subscriber ─────────────────────────────────────────────────────────
    token = uuid.uuid4().hex
    now = datetime.utcnow()

    doc = {
        "email": email,
        "list": list_name,
        "status": SubscriberStatus.PENDING_CONFIRMATION,
        "standard_fields": clean_std,
        "custom_fields": clean_cust,
        "confirmation_token": token,
        "confirmation_token_created_at": now,
        "source": payload.source,
        "consent": True,
        "consent_at": now,
        "created_at": now,
        "updated_at": now,
    }

    try:
        await subscribers_col.insert_one(doc)
        logger.info(f"[public_optin] new pending subscriber: {email} on {list_name}")
    except Exception as e:
        # Duplicate key — another request raced us; treat as pending resend
        logger.warning(f"[public_optin] insert race for {email}: {e}")

    if smtp:
        confirm_url = _build_confirmation_url(token, request)
        background_tasks.add_task(
            _send_confirmation_email, email, list_name, confirm_url, smtp
        )
    else:
        logger.warning(
            f"[public_optin] no SMTP config — confirmation email NOT sent to {email}"
        )

    return {"message": "Thank you. Please check your email to confirm."}


@router.get("/public/confirm/{token}", response_class=HTMLResponse)
async def confirm_subscription(token: str):
    """
    Activates a pending_confirmation subscriber.

    Token lookup is done by the `confirmation_token` field (sparse index).
    - Token expired (>48h)    → expired HTML page
    - Already active          → already-confirmed HTML page
    - Invalid token           → invalid HTML page
    - Success                 → confirmed HTML page + clears token fields
    """
    subscribers_col = get_subscribers_collection()

    sub = await subscribers_col.find_one(
        {"confirmation_token": token},
        {
            "status": 1,
            "email": 1,
            "list": 1,
            "confirmation_token_created_at": 1,
        },
    )

    if not sub:
        return HTMLResponse(content=_INVALID_HTML, status_code=400)

    status = sub.get("status")

    if status == SubscriberStatus.ACTIVE:
        return HTMLResponse(content=_ALREADY_CONFIRMED_HTML, status_code=200)

    # Check expiry
    token_created: Optional[datetime] = sub.get("confirmation_token_created_at")
    if token_created and datetime.utcnow() - token_created > timedelta(hours=TOKEN_TTL_HOURS):
        logger.info(
            f"[public_optin] expired token for {sub.get('email')} on {sub.get('list')}"
        )
        return HTMLResponse(content=_EXPIRED_HTML, status_code=410)

    # Activate subscriber and clear token fields
    await subscribers_col.update_one(
        {"_id": sub["_id"]},
        {
            "$set": {
                "status": SubscriberStatus.ACTIVE,
                "confirmed_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            },
            "$unset": {
                "confirmation_token": "",
                "confirmation_token_created_at": "",
            },
        },
    )

    logger.info(
        f"[public_optin] confirmed: {sub.get('email')} on list '{sub.get('list')}'"
    )
    return HTMLResponse(content=_CONFIRMED_HTML, status_code=200)
