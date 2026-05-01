"""
Patch: replace build_unsubscribe_url so it reads the configured unsubscribe_domain
from the tracking settings document (same source as open/click domains) rather than
the hardcoded UNSUBSCRIBE_DOMAIN env var.

Priority order:
  1. tracking settings doc → unsubscribe_domain
  2. tracking settings doc → open_tracking_domain  (fallback — same server)
  3. env APP_BASE_URL
  4. "localhost:8000"

This is a drop-in replacement for the existing function — all call sites remain
identical (generate_unsubscribe_token / build_unsubscribe_url).
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from database import get_sync_unsubscribe_tokens_collection

logger = logging.getLogger(__name__)
router = APIRouter(tags=["unsubscribe"])


# ── Token generation ──────────────────────────────────────────────────────────

def generate_unsubscribe_token(campaign_id: str, subscriber_id: str, email: str) -> str:
    token = uuid.uuid4().hex
    col = get_sync_unsubscribe_tokens_collection()
    col.insert_one(
        {
            "token": token,
            "campaign_id": campaign_id,
            "subscriber_id": subscriber_id,
            "email": email,
            "created_at": datetime.utcnow(),
            "used": False,
        }
    )
    return token


def _get_unsubscribe_base() -> str:
    """
    Resolve the base URL for unsubscribe links.

    Reads the 'tracking' settings document from MongoDB (same store used by
    open/click tracking domains) so all domain config is in one place and can
    be changed at runtime without a redeploy.
    """
    import os
    try:
        from database import get_sync_database
        doc = get_sync_database().settings.find_one({"type": "tracking"}) or {}

        # Prefer the explicit unsubscribe domain, fall back to open tracking domain.
        for key in ("unsubscribe_domain", "open_tracking_domain"):
            val = (doc.get(key) or "").strip()
            if val:
                return val if val.startswith("http") else f"https://{val}"
    except Exception as e:
        logger.debug(f"Could not read tracking settings for unsubscribe domain: {e}")

    # Last resort: APP_BASE_URL env var.
    return os.environ.get("APP_BASE_URL", "http://localhost:8000")


def build_unsubscribe_url(token: str) -> str:
    base = _get_unsubscribe_base()
    return f"{base}/unsubscribe/{token}"


# ── HTML pages ────────────────────────────────────────────────────────────────

_SUCCESS_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Unsubscribed</title>
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
</style></head>
<body><div class="card">
  <div class="ico"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></div>
  <h1>Successfully Unsubscribed</h1>
  <p>You've been removed from this mailing list and will no longer receive these emails.</p>
</div></body></html>"""

_ALREADY_USED_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Already Unsubscribed</title>
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
</style></head>
<body><div class="card">
  <div class="ico"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></div>
  <h1>Already Unsubscribed</h1>
  <p>This link has already been used. You are already unsubscribed from this list.</p>
</div></body></html>"""

_ERROR_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Invalid Link</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       background:#fef2f2;min-height:100vh;display:flex;align-items:center;justify-content:center}
  .card{background:#fff;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.08);
        padding:48px 40px;text-align:center;max-width:440px;width:90%}
  h1{font-size:22px;font-weight:700;color:#dc2626;margin-bottom:10px}
  p{color:#6b7280;line-height:1.6;font-size:15px}
</style></head>
<body><div class="card">
  <h1>Invalid Link</h1>
  <p>This unsubscribe link is invalid or has expired.</p>
</div></body></html>"""


# ── Core unsubscribe logic (delegates to tracking._atomic_unsubscribe) ────────

async def _process_unsubscribe(token: str) -> dict:
    from database import (
        get_unsubscribe_tokens_collection,
        get_subscribers_collection,
        get_suppressions_collection,
    )

    tokens_col = get_unsubscribe_tokens_collection()
    token_doc = await tokens_col.find_one({"token": token})

    if not token_doc:
        return {"success": False, "reason": "invalid_token"}

    if token_doc.get("used"):
        return {"success": False, "reason": "already_used"}

    email = token_doc["email"]
    subscriber_id = token_doc["subscriber_id"]
    campaign_id = token_doc["campaign_id"]

    # Delegate to canonical dual-write implementation in tracking
    try:
        from routes.tracking import _atomic_unsubscribe
        await _atomic_unsubscribe(
            email=email,
            subscriber_id=str(subscriber_id),
            campaign_id=str(campaign_id),
            ip="token-link",
        )
    except ImportError:
        # Fallback if tracking module not available
        subscribers_col = get_subscribers_collection()
        suppressions_col = get_suppressions_collection()
        await subscribers_col.update_many(
            {"email": email},
            {"$set": {"status": "unsubscribed", "unsubscribed_at": datetime.utcnow(), "is_suppressed": True}},
        )
        existing = await suppressions_col.find_one({"email": email, "type": "unsubscribe"})
        if not existing:
            await suppressions_col.insert_one({
                "email": email, "type": "unsubscribe", "reason": "user_unsubscribed",
                "source": "unsubscribe_link", "campaign_id": campaign_id,
                "subscriber_id": subscriber_id, "scope": "global",
                "created_at": datetime.utcnow(),
            })

    await tokens_col.update_one(
        {"token": token},
        {"$set": {"used": True, "used_at": datetime.utcnow()}},
    )

    logger.info(f"[unsubscribe] {email} unsubscribed via token (campaign: {campaign_id})")
    return {"success": True, "email": email}


# ── Public endpoints ──────────────────────────────────────────────────────────

@router.get("/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe_via_link(token: str):
    result = await _process_unsubscribe(token)
    if result["success"]:
        return HTMLResponse(content=_SUCCESS_HTML, status_code=200)
    if result.get("reason") == "already_used":
        return HTMLResponse(content=_ALREADY_USED_HTML, status_code=200)
    return HTMLResponse(content=_ERROR_HTML, status_code=400)


class UnsubscribeWebhookPayload(BaseModel):
    token: str

@router.post("/webhooks/unsubscribe")
async def unsubscribe_webhook(payload: UnsubscribeWebhookPayload):
    from fastapi import HTTPException
    result = await _process_unsubscribe(payload.token)
    if result["success"]:
        return {"status": "success", "email": result["email"]}
    raise HTTPException(status_code=400, detail="Invalid or already-used unsubscribe token")