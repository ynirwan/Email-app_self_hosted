# backend/routes/tracking.py
"""
Open and click tracking endpoints.

Public  (no auth):
  GET /api/track/open/{campaign_id}/{subscriber_id}   → 1×1 transparent GIF, logs open
  GET /api/track/click/{campaign_id}/{subscriber_id}  → redirects to ?url=..., logs click

Auth-required (settings management):
  GET /api/settings/tracking   → current domain config
  PUT /api/settings/tracking   → update domain config (stored in MongoDB)
"""

import base64
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import unquote

from bson import ObjectId
from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel

from core.config import settings
from database import get_email_logs_collection, get_settings_collection

logger = logging.getLogger(__name__)

# ── 1×1 transparent GIF pixel (binary) ──────────────────────────────────────
_PIXEL_B64 = (
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)
_PIXEL_BYTES = base64.b64decode(_PIXEL_B64)

# ── Public router (no auth) ──────────────────────────────────────────────────
public_router = APIRouter(tags=["Tracking"])


def _get_tracking_domains_from_db_sync():
    """Read tracking domains from MongoDB (synchronous, for tasks)."""
    from database import get_sync_db
    db = get_sync_db()
    doc = db["settings"].find_one({"type": "tracking"})
    if doc:
        return doc
    return {}


async def _get_tracking_domains():
    """Read tracking domains from MongoDB, fall back to env config."""
    col = get_settings_collection()
    doc = await col.find_one({"type": "tracking"})
    if doc:
        return {
            "unsubscribe_domain": doc.get("unsubscribe_domain", settings.UNSUBSCRIBE_DOMAIN),
            "open_tracking_domain": doc.get("open_tracking_domain", settings.OPEN_TRACKING_DOMAIN),
            "click_tracking_domain": doc.get("click_tracking_domain", settings.CLICK_TRACKING_DOMAIN),
        }
    return {
        "unsubscribe_domain": settings.UNSUBSCRIBE_DOMAIN,
        "open_tracking_domain": settings.OPEN_TRACKING_DOMAIN,
        "click_tracking_domain": settings.CLICK_TRACKING_DOMAIN,
    }


def get_open_tracking_domain_sync() -> str:
    doc = _get_tracking_domains_from_db_sync()
    return doc.get("open_tracking_domain", settings.OPEN_TRACKING_DOMAIN)


def get_click_tracking_domain_sync() -> str:
    doc = _get_tracking_domains_from_db_sync()
    return doc.get("click_tracking_domain", settings.CLICK_TRACKING_DOMAIN)


def build_open_tracking_url(campaign_id: str, subscriber_id: str) -> str:
    domain = get_open_tracking_domain_sync()
    return f"https://{domain}/api/track/open/{campaign_id}/{subscriber_id}"


def build_click_tracking_url(campaign_id: str, subscriber_id: str, target_url: str) -> str:
    from urllib.parse import quote
    domain = get_click_tracking_domain_sync()
    encoded = quote(target_url, safe="")
    return f"https://{domain}/api/track/click/{campaign_id}/{subscriber_id}?url={encoded}"


@public_router.get("/track/open/{campaign_id}/{subscriber_id}")
async def track_open(campaign_id: str, subscriber_id: str):
    """Return a 1×1 transparent pixel and log the open event."""
    try:
        col = get_email_logs_collection()
        await col.update_one(
            {
                "campaign_id": ObjectId(campaign_id),
                "subscriber_id": subscriber_id,
            },
            {
                "$set": {"opened": True, "opened_at": datetime.utcnow(), "latest_status": "opened"},
                "$inc": {"open_count": 1},
            },
        )
    except Exception as e:
        logger.debug(f"Open tracking log failed (non-critical): {e}")

    return Response(
        content=_PIXEL_BYTES,
        media_type="image/gif",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


@public_router.get("/track/click/{campaign_id}/{subscriber_id}")
async def track_click(
    campaign_id: str,
    subscriber_id: str,
    url: Optional[str] = Query(None),
):
    """Log click event and redirect to target URL."""
    target = url or "/"
    try:
        decoded_url = unquote(target)
        col = get_email_logs_collection()
        await col.update_one(
            {
                "campaign_id": ObjectId(campaign_id),
                "subscriber_id": subscriber_id,
            },
            {
                "$set": {"clicked": True, "clicked_at": datetime.utcnow()},
                "$inc": {"click_count": 1},
                "$push": {"clicked_urls": {"url": decoded_url, "at": datetime.utcnow()}},
            },
        )
        target = decoded_url
    except Exception as e:
        logger.debug(f"Click tracking log failed (non-critical): {e}")

    return RedirectResponse(url=target, status_code=302)


# ── Auth-protected settings router ───────────────────────────────────────────
settings_router = APIRouter(tags=["Settings"])


class TrackingDomainsUpdate(BaseModel):
    unsubscribe_domain: str
    open_tracking_domain: str
    click_tracking_domain: str


@settings_router.get("/tracking")
async def get_tracking_settings():
    """Return the current tracking domain configuration."""
    domains = await _get_tracking_domains()
    return domains


@settings_router.put("/tracking")
async def update_tracking_settings(payload: TrackingDomainsUpdate):
    """Save tracking domain configuration to MongoDB."""

    def _clean(domain: str) -> str:
        return domain.strip().lower().lstrip("https://").lstrip("http://").rstrip("/")

    col = get_settings_collection()
    doc = {
        "type": "tracking",
        "unsubscribe_domain": _clean(payload.unsubscribe_domain),
        "open_tracking_domain": _clean(payload.open_tracking_domain),
        "click_tracking_domain": _clean(payload.click_tracking_domain),
        "updated_at": datetime.utcnow(),
    }
    await col.update_one({"type": "tracking"}, {"$set": doc}, upsert=True)
    logger.info(
        f"Tracking domains updated — unsub={doc['unsubscribe_domain']} "
        f"open={doc['open_tracking_domain']} click={doc['click_tracking_domain']}"
    )
    return {"status": "saved", **doc}
