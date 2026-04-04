"""
backend/routes/unsubscribe.py

Public unsubscribe endpoints — no auth required.

The dual-write logic (subscribers + suppressions) lives in
routes/tracking.py::_atomic_unsubscribe() — one canonical implementation,
no risk of the two collections drifting out of sync.

Bug that was fixed
------------------
Old code in _process_unsubscribe():
  1. Always called subscribers.update_many()
  2. Called suppressions.insert_one() ONLY IF existing suppression not found
     → if suppression existed but was inactive (admin re-enabled it), the
       subscriber would be marked unsubscribed but NOT suppressed, so future
       sends would still go through.

Fix:
  - Delegates to _atomic_unsubscribe() which does an upsert on suppressions
    (reactivate if exists, insert if not) and always writes both collections.
  - Logs a granular event row in email_events on every unsubscribe.
  - Updates analytics counters (total_unsubscribed, unsubscribe_rate).
"""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from database import get_sync_unsubscribe_tokens_collection
from core.config import settings

router = APIRouter(tags=["unsubscribe"])
logger = logging.getLogger(__name__)


# ── Token generation (called by email_campaign_tasks at send time via sync DB) ─


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


def build_unsubscribe_url(token: str) -> str:
    domain = settings.UNSUBSCRIBE_DOMAIN
    return f"https://{domain}/unsubscribe/{token}"


# ── HTML pages (fallback — frontend React page is preferred) ──────────────────

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
  <p>This link has already been used. You are already removed from our mailing list.</p>
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
  .ico{width:64px;height:64px;background:#fee2e2;border-radius:50%;
       display:flex;align-items:center;justify-content:center;margin:0 auto 20px}
  .ico svg{width:32px;height:32px;stroke:#dc2626;fill:none;stroke-width:2.5;
           stroke-linecap:round;stroke-linejoin:round}
  h1{font-size:22px;font-weight:700;color:#111;margin-bottom:10px}
  p{color:#6b7280;line-height:1.6;font-size:15px}
</style></head>
<body><div class="card">
  <div class="ico">
    <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
  </div>
  <h1>Invalid Link</h1>
  <p>This unsubscribe link is invalid or has expired. If you continue to receive unwanted emails, please reply and ask to be removed.</p>
</div></body></html>"""


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe_via_link(token: str, request: Request):
    """
    One-click unsubscribe — called directly from email link.
    Delegates to the shared atomic handler which writes BOTH collections.
    """
    from routes.tracking import _atomic_unsubscribe

    result = await _atomic_unsubscribe(token, request)

    if result["success"]:
        return HTMLResponse(content=_SUCCESS_HTML, status_code=200)
    if result["reason"] == "token_already_used":
        return HTMLResponse(content=_ALREADY_USED_HTML, status_code=200)
    return HTMLResponse(content=_ERROR_HTML, status_code=400)


class UnsubscribeWebhookPayload(BaseModel):
    token: str


@router.post("/webhooks/unsubscribe")
async def unsubscribe_webhook(payload: UnsubscribeWebhookPayload, request: Request):
    """Programmatic unsubscribe (e.g. List-Unsubscribe POST header)."""
    from routes.tracking import _atomic_unsubscribe

    result = await _atomic_unsubscribe(payload.token, request)
    if result["success"]:
        return {"status": "success", "message": f"Unsubscribed {result['email']}"}
    if result["reason"] == "token_already_used":
        return {"status": "already_done", "message": "Already unsubscribed"}
    from fastapi import HTTPException

    raise HTTPException(status_code=400, detail="Invalid or expired unsubscribe token")
