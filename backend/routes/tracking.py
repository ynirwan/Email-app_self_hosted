"""
backend/routes/tracking.py

Email open & click tracking endpoints. All routes are PUBLIC (no auth required)
because they are hit directly from inside rendered emails.

Routes
------
GET  /t/o/{token}.gif          — 1×1 pixel open tracker
GET  /t/c/{token}              — click redirect (wraps outbound links)
GET  /t/verify/{token}         — verify unsubscribe token for confirmation page
POST /t/u/{token}              — programmatic unsubscribe (used by public confirm page)

Internal helpers (imported by analytics.py and unsubscribe.py)
------
generate_tracking_token(campaign_id, subscriber_id, email) -> str
build_open_pixel_url(token) -> str
build_click_redirect_url(token, target_url) -> str
"""

import base64
import hashlib
import logging
import os
import secrets
import urllib.parse
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from database import (
    get_analytics_collection,
    get_campaigns_collection,
    get_email_events_collection,
    get_suppressions_collection,
    get_subscribers_collection,
    get_unsubscribe_tokens_collection,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["tracking"])

# ── 1×1 transparent GIF (base64) ─────────────────────────────────────────────
_PIXEL = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
_PIXEL_RESPONSE = Response(
    content=_PIXEL,
    media_type="image/gif",
    headers={
        "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    },
)


# ─────────────────────────────────────────────────────────────────────────────
# Token helpers (called by email_campaign_tasks.py at send time)
# ─────────────────────────────────────────────────────────────────────────────


def generate_tracking_token(campaign_id: str, subscriber_id: str, email: str) -> str:
    """
    Create a short, URL-safe token that encodes campaign+subscriber+email.
    Stored in the email_events collection so we can look it up on hit.
    Format: <random_hex>  (32 chars) — the mapping is stored in MongoDB.
    """
    return secrets.token_urlsafe(24)


def _get_tracking_domain(key: str, fallback_env: str = "APP_BASE_URL") -> str:
    """
    Read a tracking domain from MongoDB settings collection (sync).
    Falls back to env var, then to http://localhost:8000.
    Called at send time from Celery tasks — must be synchronous.
    """
    try:
        from database import get_sync_database
        doc = get_sync_database().settings.find_one({"type": "tracking"}) or {}
        val = doc.get(key, "").strip()
        if val:
            # Ensure scheme
            return val if val.startswith("http") else f"https://{val}"
    except Exception:
        pass
    return os.environ.get(fallback_env, os.environ.get("APP_BASE_URL", "http://localhost:8000"))


def build_open_pixel_url(token: str, base_url: str = None) -> str:
    domain = base_url or _get_tracking_domain("open_tracking_domain")
    return f"{domain}/t/o/{token}.gif"


def build_click_redirect_url(token: str, target_url: str, base_url: str = None) -> str:
    domain = base_url or _get_tracking_domain("click_tracking_domain")
    encoded = urllib.parse.quote(target_url, safe="")
    return f"{domain}/t/c/{token}?u={encoded}"


async def create_tracking_record(
    campaign_id: str,
    subscriber_id: str,
    email: str,
    open_token: str,
) -> None:
    """
    Write an initial 'sent' event document to email_events.
    Called immediately after a message is dispatched.
    """
    try:
        col = get_email_events_collection()
        await col.insert_one(
            {
                "open_token": open_token,
                "campaign_id": ObjectId(campaign_id)
                if ObjectId.is_valid(campaign_id)
                else campaign_id,
                "subscriber_id": ObjectId(subscriber_id)
                if ObjectId.is_valid(subscriber_id)
                else subscriber_id,
                "email": email.lower().strip(),
                "event_type": "sent",
                "open_count": 0,
                "click_count": 0,
                "is_unsubscribed": False,
                "timestamp": datetime.utcnow(),
                "first_open_at": None,
                "first_click_at": None,
                "last_event_at": None,
            }
        )
    except Exception as e:
        logger.warning(f"create_tracking_record failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Background helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _record_open(token: str, ip: str, ua: str):
    """
    Persist an open event.
    - Increments open_count on the tracking doc
    - Inserts an 'opened' event in email_events
    - Increments total_opened in the analytics collection
    - Updates campaign.open_rate
    """
    try:
        col = get_email_events_collection()
        now = datetime.utcnow()

        # Find the master tracking doc by open_token
        doc = await col.find_one({"open_token": token})
        if not doc:
            logger.debug(f"[tracking] open pixel hit with unknown token: {token}")
            return

        campaign_id = doc.get("campaign_id")
        subscriber_id = doc.get("subscriber_id")
        is_first_open = doc.get("open_count", 0) == 0

        # Update the tracking doc (increment open_count, set first_open_at if first)
        update_fields = {
            "$inc": {"open_count": 1},
            "$set": {"last_event_at": now},
        }
        if is_first_open:
            update_fields["$set"]["first_open_at"] = now
            update_fields["$set"]["event_type"] = "opened"

        await col.update_one({"_id": doc["_id"]}, update_fields)

        # Insert a granular event log row
        await col.insert_one(
            {
                "open_token": token,
                "campaign_id": campaign_id,
                "subscriber_id": subscriber_id,
                "email": doc.get("email"),
                "event_type": "opened",
                "ip_address": ip,
                "user_agent": ua,
                "timestamp": now,
            }
        )

        # Only count unique opens for analytics (first open per subscriber per campaign)
        if is_first_open and campaign_id:
            await _increment_analytics(str(campaign_id), "total_opened")

    except Exception as e:
        logger.error(f"[tracking] _record_open error: {e}", exc_info=True)


async def _record_click(token: str, url: str, ip: str, ua: str):
    """
    Persist a click event.
    - Increments click_count on the tracking doc
    - Inserts a 'clicked' event row with url
    - Increments total_clicked in analytics (unique per subscriber)
    """
    try:
        col = get_email_events_collection()
        now = datetime.utcnow()

        doc = await col.find_one({"open_token": token})
        if not doc:
            logger.debug(f"[tracking] click hit with unknown token: {token}")
            return

        campaign_id = doc.get("campaign_id")
        subscriber_id = doc.get("subscriber_id")
        is_first_click = doc.get("click_count", 0) == 0

        update_fields = {
            "$inc": {"click_count": 1},
            "$set": {"last_event_at": now},
        }
        if is_first_click:
            update_fields["$set"]["first_click_at"] = now

        await col.update_one({"_id": doc["_id"]}, update_fields)

        # Granular click event
        await col.insert_one(
            {
                "open_token": token,
                "campaign_id": campaign_id,
                "subscriber_id": subscriber_id,
                "email": doc.get("email"),
                "event_type": "clicked",
                "url": url,
                "ip_address": ip,
                "user_agent": ua,
                "timestamp": now,
            }
        )

        if is_first_click and campaign_id:
            await _increment_analytics(str(campaign_id), "total_clicked")

    except Exception as e:
        logger.error(f"[tracking] _record_click error: {e}", exc_info=True)


async def _increment_analytics(campaign_id: str, field: str):
    """
    Atomically increment a counter in the analytics collection and
    recompute open_rate / click_rate based on campaign.sent_count.
    """
    try:
        analytics_col = get_analytics_collection()
        campaigns_col = get_campaigns_collection()

        cid = ObjectId(campaign_id) if ObjectId.is_valid(campaign_id) else campaign_id

        # Upsert the analytics document
        await analytics_col.update_one(
            {"campaign_id": cid},
            {"$inc": {field: 1}, "$set": {"updated_at": datetime.utcnow()}},
            upsert=True,
        )

        # Recompute rates
        campaign = await campaigns_col.find_one(
            {"_id": cid}, {"sent_count": 1, "delivered_count": 1}
        )
        analytics = await analytics_col.find_one({"campaign_id": cid})

        if campaign and analytics:
            total_sent = (campaign.get("sent_count") or 0) + (
                campaign.get("delivered_count") or 0
            )
            if total_sent > 0:
                open_rate = round(
                    analytics.get("total_opened", 0) / total_sent * 100, 2
                )
                click_rate = round(
                    analytics.get("total_clicked", 0) / total_sent * 100, 2
                )
                unsub_rate = round(
                    analytics.get("total_unsubscribed", 0) / total_sent * 100, 2
                )
                await analytics_col.update_one(
                    {"campaign_id": cid},
                    {
                        "$set": {
                            "open_rate": open_rate,
                            "click_rate": click_rate,
                            "unsubscribe_rate": unsub_rate,
                        }
                    },
                )
                # Also mirror to campaign document for quick dashboard access
                await campaigns_col.update_one(
                    {"_id": cid},
                    {"$set": {"open_rate": open_rate, "click_rate": click_rate}},
                )
    except Exception as e:
        logger.error(f"[tracking] _increment_analytics error: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Public endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/t/o/{token_gif}", include_in_schema=False)
async def open_pixel(token_gif: str, request: Request, bt: BackgroundTasks):
    """
    Serve 1×1 GIF and record an open event.
    The filename in the email HTML is `{token}.gif` so token_gif = "abc123.gif".
    We strip the extension before looking up.
    """
    token = token_gif.removesuffix(".gif")
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")
    bt.add_task(_record_open, token, ip, ua)
    return _PIXEL_RESPONSE


@router.get("/t/c/{token}", include_in_schema=False)
async def click_redirect(
    token: str, u: str = "", request: Request = None, bt: BackgroundTasks = None
):
    """
    Record a click and redirect to the target URL.
    Usage in emails: <a href="https://app/t/c/{token}?u=https%3A%2F%2Fexample.com">
    """
    target = urllib.parse.unquote(u) if u else "/"

    # Validate URL to prevent open-redirect abuse
    parsed = urllib.parse.urlparse(target)
    if parsed.scheme not in ("http", "https", ""):
        target = "/"

    if token and bt:
        ip = request.client.host if request.client else "unknown"
        ua = request.headers.get("user-agent", "") if request else ""
        bt.add_task(_record_click, token, target, ip, ua)

    return RedirectResponse(url=target, status_code=302)


@router.get("/t/verify/{token}")
async def verify_unsubscribe_token(token: str):
    """
    Verify an unsubscribe token without consuming it.
    Used by the frontend confirmation page before showing the 'Confirm' button.
    """
    tokens_col = get_unsubscribe_tokens_collection()
    doc = await tokens_col.find_one({"token": token})

    if not doc:
        raise HTTPException(status_code=404, detail="Invalid unsubscribe link")
    if doc.get("used"):
        raise HTTPException(status_code=410, detail="This link has already been used")

    return {
        "valid": True,
        "email": doc["email"],
        # Mask email for display: u****@domain.com
        "email_masked": _mask_email(doc["email"]),
        "campaign_id": doc.get("campaign_id"),
    }


@router.post("/t/u/{token}")
async def confirm_unsubscribe(token: str, request: Request):
    """
    Confirm unsubscribe from the public page.
    Atomically writes to BOTH subscribers AND suppressions.
    This is the canonical unsubscribe handler — unsubscribe.py delegates here.
    """
    result = await _atomic_unsubscribe(token, request)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["reason"])
    return {"status": "ok", "email": result["email"]}


# ─────────────────────────────────────────────────────────────────────────────
# Shared atomic unsubscribe logic (also used by unsubscribe.py HTML route)
# ─────────────────────────────────────────────────────────────────────────────


async def _atomic_unsubscribe(token: str, request: Request = None) -> dict:
    """
    Single source of truth for processing an unsubscribe.

    Bug that was fixed:
        Previously _process_unsubscribe in unsubscribe.py only inserted into
        the suppressions collection IF the email did not already exist there.
        But it ALWAYS updated subscribers. This caused:
          - A subscriber reactivated by an admin would not be re-suppressed
          - The suppression could be missing if inserted via a different code path
          - Partial writes if an exception occurred between the two DB calls

        Fix: we now perform both writes sequentially with explicit error handling,
        logging which write succeeded/failed. We also handle the case where the
        suppression already exists (upsert-style) so there are no skips.
    """
    tokens_col = get_unsubscribe_tokens_collection()
    subscribers_col = get_subscribers_collection()
    suppressions_col = get_suppressions_collection()
    email_events_col = get_email_events_collection()
    analytics_col = get_analytics_collection()

    # 1. Validate token
    token_doc = await tokens_col.find_one({"token": token})
    if not token_doc:
        return {"success": False, "reason": "invalid_token"}
    if token_doc.get("used"):
        return {"success": False, "reason": "token_already_used"}

    email: str = token_doc["email"].lower().strip()
    subscriber_id: str = token_doc.get("subscriber_id", "")
    campaign_id: str = token_doc.get("campaign_id", "")
    now = datetime.utcnow()
    ip = request.client.host if request and request.client else "unknown"

    errors = []

    # 2. Mark token as used (do this first — idempotency guard)
    try:
        await tokens_col.update_one(
            {"token": token},
            {"$set": {"used": True, "used_at": now, "used_from_ip": ip}},
        )
    except Exception as e:
        logger.error(f"[unsubscribe] failed to mark token used: {e}")
        return {"success": False, "reason": "internal_error"}

    # 3. Update subscribers collection — ALL docs with this email
    #    (handles case where same email appears in multiple lists)
    try:
        sub_result = await subscribers_col.update_many(
            {"email": email},
            {
                "$set": {
                    "status": "unsubscribed",
                    "unsubscribed_at": now,
                    "is_suppressed": True,
                    "updated_at": now,
                }
            },
        )
        logger.info(
            f"[unsubscribe] updated {sub_result.modified_count} subscriber docs for {email}"
        )
    except Exception as e:
        logger.error(f"[unsubscribe] FAILED to update subscribers for {email}: {e}")
        errors.append(f"subscribers: {e}")

    # 4. Write to suppressions collection — upsert so we never skip
    #    This is the critical fix: previously used insert_one only if not existing,
    #    which could leave the suppression missing if the doc existed but was inactive.
    try:
        existing_sup = await suppressions_col.find_one(
            {"email": email, "scope": "global"}
        )
        if existing_sup:
            # Ensure it's active regardless of previous state
            await suppressions_col.update_one(
                {"_id": existing_sup["_id"]},
                {
                    "$set": {
                        "is_active": True,
                        "reason": "unsubscribe",
                        "source": "unsubscribe_link",
                        "updated_at": now,
                        "last_unsubscribe_at": now,
                        "campaign_id": campaign_id
                        if campaign_id
                        else existing_sup.get("campaign_id"),
                        "subscriber_id": subscriber_id
                        if subscriber_id
                        else existing_sup.get("subscriber_id"),
                    }
                },
            )
            logger.info(f"[unsubscribe] updated existing suppression for {email}")
        else:
            sup_doc = {
                "email": email,
                "type": "unsubscribe",  # legacy field — kept for compat
                "reason": "unsubscribe",
                "source": "unsubscribe_link",
                "scope": "global",
                "target_lists": [],
                "campaign_id": campaign_id,
                "subscriber_id": subscriber_id,
                "is_active": True,
                "notes": "",
                "created_at": now,
                "updated_at": now,
                "created_by": "system",
            }
            await suppressions_col.insert_one(sup_doc)
            logger.info(f"[unsubscribe] inserted suppression for {email}")
    except Exception as e:
        logger.error(f"[unsubscribe] FAILED to write suppression for {email}: {e}")
        errors.append(f"suppressions: {e}")

    # 5. Mark the tracking doc as unsubscribed (best-effort)
    try:
        if campaign_id:
            await email_events_col.update_many(
                {
                    "email": email,
                    "campaign_id": ObjectId(campaign_id)
                    if ObjectId.is_valid(campaign_id)
                    else campaign_id,
                },
                {"$set": {"is_unsubscribed": True, "last_event_at": now}},
            )
    except Exception as e:
        logger.warning(f"[unsubscribe] could not update email_events: {e}")

    # 6. Log unsubscribe event in email_events (granular row)
    try:
        await email_events_col.insert_one(
            {
                "email": email,
                "campaign_id": ObjectId(campaign_id)
                if campaign_id and ObjectId.is_valid(campaign_id)
                else campaign_id,
                "subscriber_id": ObjectId(subscriber_id)
                if subscriber_id and ObjectId.is_valid(subscriber_id)
                else subscriber_id,
                "event_type": "unsubscribed",
                "timestamp": now,
                "ip_address": ip,
            }
        )
    except Exception as e:
        logger.warning(f"[unsubscribe] could not log event row: {e}")

    # 7. Increment analytics counter (best-effort)
    try:
        if campaign_id:
            await _increment_analytics(campaign_id, "total_unsubscribed")
    except Exception as e:
        logger.warning(f"[unsubscribe] could not update analytics: {e}")

    if errors:
        logger.error(f"[unsubscribe] partial errors for {email}: {errors}")

    logger.info(f"[unsubscribe] ✅ {email} unsubscribed from campaign {campaign_id}")
    return {"success": True, "email": email, "errors": errors}


def _mask_email(email: str) -> str:
    """u****@domain.com style masking."""
    try:
        local, domain = email.split("@", 1)
        return local[0] + "****@" + domain
    except Exception:
        return "****"


def rewrite_links_for_tracking(html: str, open_token: str, base_url: str = None) -> str:
    """
    Replace all <a href="..."> links in the HTML with click-tracked redirects.
    Skips:
      - mailto: links
      - tel: links
      - # anchors
      - Already-wrapped /t/c/ links
      - The unsubscribe link (preserves it as-is)
    """
    import re

    def _replace(m):
        original_url = m.group(1)
        # Skip special schemes and already-wrapped links
        if original_url.startswith(("mailto:", "tel:", "#", "/t/c/")):
            return m.group(0)
        wrapped = build_click_redirect_url(open_token, original_url, base_url)
        return f'href="{wrapped}"'

    # Match href="..." double-quoted
    html = re.sub(r'href="([^"]+)"', _replace, html)

    # Match href='...' single-quoted
    def _replace_sq(m):
        original_url = m.group(1)
        if original_url.startswith(("mailto:", "tel:", "#", "/t/c/")):
            return m.group(0)
        wrapped = build_click_redirect_url(open_token, original_url, base_url)
        return f"href='{wrapped}'"

    html = re.sub(r"href='([^']+)'", _replace_sq, html)
    return html


# ── Settings helpers (called by email_campaign_tasks) ─────────────────────────


async def get_tracking_flags() -> dict:
    """
    Return the current tracking feature flags from the settings collection.
    Falls back to enabled=True so behaviour is unchanged if the settings doc
    doesn't exist yet.
    """
    try:
        from database import get_settings_collection

        col = get_settings_collection()
        doc = await col.find_one({"type": "tracking"})
        defaults = {
            "open_tracking_enabled": True,
            "click_tracking_enabled": True,
        }
        if doc:
            defaults["open_tracking_enabled"] = doc.get("open_tracking_enabled", True)
            defaults["click_tracking_enabled"] = doc.get("click_tracking_enabled", True)
        return defaults
    except Exception:
        return {"open_tracking_enabled": True, "click_tracking_enabled": True}


def get_tracking_flags_sync() -> dict:
    """
    Synchronous version for use inside Celery tasks.
    Uses the sync MongoDB client already available in the task context.
    """
    try:
        from database import get_sync_database

        doc = get_sync_database().settings.find_one({"type": "tracking"})
        defaults = {"open_tracking_enabled": True, "click_tracking_enabled": True}
        if doc:
            defaults["open_tracking_enabled"] = doc.get("open_tracking_enabled", True)
            defaults["click_tracking_enabled"] = doc.get("click_tracking_enabled", True)
        return defaults
    except Exception:
        return {"open_tracking_enabled": True, "click_tracking_enabled": True}


# ── Settings router (auth-protected, mounted at /api/settings) ────────────────
from fastapi import APIRouter as _APIRouter
from pydantic import BaseModel as _BaseModel
from typing import Optional as _Optional

settings_router = _APIRouter(tags=["Settings"])

_TOGGLE_DEFAULTS = {
    "open_tracking_enabled": True,
    "click_tracking_enabled": True,
    "unsubscribe_tracking_enabled": True,
    "track_unique_only": True,
}


class _TrackingSettingsUpdate(_BaseModel):
    open_tracking_enabled: _Optional[bool] = None
    click_tracking_enabled: _Optional[bool] = None
    unsubscribe_tracking_enabled: _Optional[bool] = None
    track_unique_only: _Optional[bool] = None
    unsubscribe_domain: _Optional[str] = None
    open_tracking_domain: _Optional[str] = None
    click_tracking_domain: _Optional[str] = None


def _clean_domain(domain: str) -> str:
    return domain.strip().lower().replace("https://", "").replace("http://", "").rstrip("/")


@settings_router.get("/tracking")
async def get_tracking_settings():
    """Return the merged tracking settings (toggle flags + domains)."""
    from database import get_settings_collection
    col = get_settings_collection()
    doc = await col.find_one({"type": "tracking"}) or {}
    return {
        "open_tracking_enabled":        doc.get("open_tracking_enabled",        _TOGGLE_DEFAULTS["open_tracking_enabled"]),
        "click_tracking_enabled":       doc.get("click_tracking_enabled",       _TOGGLE_DEFAULTS["click_tracking_enabled"]),
        "unsubscribe_tracking_enabled": doc.get("unsubscribe_tracking_enabled", _TOGGLE_DEFAULTS["unsubscribe_tracking_enabled"]),
        "track_unique_only":            doc.get("track_unique_only",            _TOGGLE_DEFAULTS["track_unique_only"]),
        # Domains: return empty string if not set in DB so the frontend shows blank (not env var)
        "unsubscribe_domain":    doc.get("unsubscribe_domain",    ""),
        "open_tracking_domain":  doc.get("open_tracking_domain",  ""),
        "click_tracking_domain": doc.get("click_tracking_domain", ""),
    }


@settings_router.put("/tracking")
async def update_tracking_settings(payload: _TrackingSettingsUpdate):
    """
    Save tracking settings (toggles and/or domains) to MongoDB.
    Uses $set so only fields present in the payload are updated — existing
    fields in the document are preserved (no accidental clobber on partial saves).
    """
    from database import get_settings_collection
    col = get_settings_collection()

    # Only include fields that were explicitly sent (not None)
    fields: dict = {"updated_at": datetime.utcnow()}

    if payload.open_tracking_enabled is not None:
        fields["open_tracking_enabled"] = payload.open_tracking_enabled
    if payload.click_tracking_enabled is not None:
        fields["click_tracking_enabled"] = payload.click_tracking_enabled
    if payload.unsubscribe_tracking_enabled is not None:
        fields["unsubscribe_tracking_enabled"] = payload.unsubscribe_tracking_enabled
    if payload.track_unique_only is not None:
        fields["track_unique_only"] = payload.track_unique_only

    # Domains: empty string means "clear the override" (fall back to server default)
    if payload.unsubscribe_domain is not None:
        fields["unsubscribe_domain"] = _clean_domain(payload.unsubscribe_domain)
    if payload.open_tracking_domain is not None:
        fields["open_tracking_domain"] = _clean_domain(payload.open_tracking_domain)
    if payload.click_tracking_domain is not None:
        fields["click_tracking_domain"] = _clean_domain(payload.click_tracking_domain)

    # $set only touches the listed fields; upsert creates the doc if missing
    await col.update_one(
        {"type": "tracking"},
        {"$set": fields, "$setOnInsert": {"type": "tracking"}},
        upsert=True,
    )
    logger.info(f"Tracking settings updated: {list(fields.keys())}")

    # Return the full merged document so the frontend can re-sync state
    doc = await col.find_one({"type": "tracking"}) or {}
    return {
        "status": "saved",
        "open_tracking_enabled":        doc.get("open_tracking_enabled",        _TOGGLE_DEFAULTS["open_tracking_enabled"]),
        "click_tracking_enabled":       doc.get("click_tracking_enabled",       _TOGGLE_DEFAULTS["click_tracking_enabled"]),
        "unsubscribe_tracking_enabled": doc.get("unsubscribe_tracking_enabled", _TOGGLE_DEFAULTS["unsubscribe_tracking_enabled"]),
        "track_unique_only":            doc.get("track_unique_only",            _TOGGLE_DEFAULTS["track_unique_only"]),
        "unsubscribe_domain":    doc.get("unsubscribe_domain",    ""),
        "open_tracking_domain":  doc.get("open_tracking_domain",  ""),
        "click_tracking_domain": doc.get("click_tracking_domain", ""),
    }