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

import asyncio
import base64
import logging
import os
import secrets
import urllib.parse
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
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


def _pixel_response() -> Response:
    """
    IMPORTANT:
    Return a NEW Response object every request.
    Reusing a shared Response object can cause weird behavior under repeated
    image hits / mail client prefetches.
    """
    return Response(
        content=_PIXEL,
        media_type="image/gif",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0",
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
    Stored in MongoDB so we can look it up on hit.
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
        val = (doc.get(key) or "").strip()
        if val:
            return val if val.startswith("http") else f"https://{val}"
    except Exception:
        pass

    return os.environ.get(
        fallback_env, os.environ.get("APP_BASE_URL", "http://localhost:8000")
    )


def build_open_pixel_url(token: str, base_url: str = None) -> str:
    domain = base_url or _get_tracking_domain("open_tracking_domain")
    return f"{domain}/t/o/{token}.gif"


def build_click_redirect_url(token: str, target_url: str, base_url: str = None) -> str:
    domain = base_url or _get_tracking_domain("click_tracking_domain")
    encoded = urllib.parse.quote(target_url, safe="")
    return f"{domain}/t/c/{token}?u={encoded}"


def create_tracking_record_sync(
    campaign_id: str,
    subscriber_id: str,
    email: str,
    open_token: str,
) -> dict:
    """
    Sync-safe tracking master record insert for Celery workers.
    Uses PyMongo, never Motor/asyncio.
    """
    try:
        from database import get_sync_email_events_collection

        col = get_sync_email_events_collection()
        now = datetime.utcnow()

        cid = ObjectId(campaign_id) if ObjectId.is_valid(campaign_id) else campaign_id

        result = col.update_one(
            {"open_token": open_token, "type": "tracking_master"},
            {
                "$setOnInsert": {
                    "open_token": open_token,
                    "campaign_id": cid,
                    "subscriber_id": subscriber_id,
                    "email": email.lower().strip(),
                    "event_type": "sent",
                    "type": "tracking_master",
                    "open_count": 0,
                    "click_count": 0,
                    "is_unsubscribed": False,
                    "first_open_at": None,
                    "first_click_at": None,
                    "timestamp": now,
                },
                "$set": {"last_event_at": now},
            },
            upsert=True,
        )

        logger.info(
            f"[tracking] create_tracking_record_sync token={open_token} "
            f"campaign={campaign_id} email={email} "
            f"matched={result.matched_count} upserted={result.upserted_id}"
        )
        return {"success": True, "token": open_token}

    except Exception as e:
        logger.exception(
            f"[tracking] create_tracking_record_sync FAILED "
            f"token={open_token} campaign={campaign_id} email={email} err={e}"
        )
        return {"success": False, "error": str(e), "token": open_token}


async def create_tracking_record(
    campaign_id: str,
    subscriber_id: str,
    email: str,
    open_token: str,
) -> None:
    import asyncio

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        create_tracking_record_sync,
        campaign_id,
        subscriber_id,
        email,
        open_token,
    )


def create_ab_tracking_record_sync(
    test_id: str,
    variant: str,
    subscriber_id: str,
    email: str,
    open_token: str,
) -> dict:
    """
    Sync tracking master record for A/B test emails.

    Identical structure to create_tracking_record_sync but stores
    ab_test_id + variant instead of campaign_id so _record_open /
    _record_click can update ab_test_results instead of analytics.
    """
    try:
        from database import get_sync_email_events_collection

        col = get_sync_email_events_collection()
        now = datetime.utcnow()

        result = col.update_one(
            {"open_token": open_token, "type": "tracking_master"},
            {
                "$setOnInsert": {
                    "open_token": open_token,
                    "ab_test_id": test_id,        # distinguishes from campaign
                    "variant": variant,
                    "campaign_id": None,           # explicitly None — not a campaign
                    "subscriber_id": subscriber_id,
                    "email": email.lower().strip(),
                    "event_type": "sent",
                    "type": "tracking_master",
                    "open_count": 0,
                    "click_count": 0,
                    "is_unsubscribed": False,
                    "first_open_at": None,
                    "first_click_at": None,
                    "timestamp": now,
                },
                "$set": {"last_event_at": now},
            },
            upsert=True,
        )
        logger.info(
            f"[tracking] ab_test master record token={open_token} "
            f"test={test_id} variant={variant} email={email}"
        )
        return {"success": True, "token": open_token}
    except Exception as e:
        logger.exception(
            f"[tracking] create_ab_tracking_record_sync FAILED "
            f"token={open_token} test={test_id} err={e}"
        )
        return {"success": False, "error": str(e), "token": open_token}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _get_track_unique_only() -> bool:
    try:
        from database import get_settings_collection

        settings_col = get_settings_collection()
        doc = await settings_col.find_one({"type": "tracking"}) or {}
        return doc.get("track_unique_only", True)
    except Exception:
        return True


# ─────────────────────────────────────────────────────────────────────────────
# Background helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _record_open(token: str, ip: str, ua: str):
    """
    Persist an open event.

    FIXED LOGIC:
    - Uses atomic update so only ONE request can claim first-open
    - Prevents duplicate unique-open increments
    - Optional event logging based on track_unique_only
    """
    try:
        col = get_email_events_collection()
        now = datetime.utcnow()
        track_unique_only = await _get_track_unique_only()

        logger.info(f"[tracking] _record_open START token={token}")

        # 1) Atomically claim FIRST open
        claimed_first = await col.find_one_and_update(
            {
                "open_token": token,
                "type": "tracking_master",
                "open_count": 0,
            },
            {
                "$inc": {"open_count": 1},
                "$set": {
                    "first_open_at": now,
                    "last_event_at": now,
                    "event_type": "opened",
                },
            },
            return_document=True,
        )

        if claimed_first:
            logger.info(f"[tracking] UNIQUE OPEN counted token={token}")
            doc = claimed_first
            is_unique = True
        else:
            # 2) Already opened before → only increment if not unique-only mode
            if track_unique_only:
                doc = await col.find_one(
                    {"open_token": token, "type": "tracking_master"}
                )
                if not doc:
                    logger.warning(
                        f"[tracking] _record_open master doc NOT FOUND token={token}"
                    )
                    return

                await col.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"last_event_at": now}},
                )

                logger.info(f"[tracking] DUPLICATE OPEN ignored token={token}")
                is_unique = False
            else:
                doc = await col.find_one_and_update(
                    {"open_token": token, "type": "tracking_master"},
                    {
                        "$inc": {"open_count": 1},
                        "$set": {"last_event_at": now},
                    },
                    return_document=True,
                )
                if not doc:
                    logger.warning(
                        f"[tracking] _record_open master doc NOT FOUND token={token}"
                    )
                    return

                logger.info(f"[tracking] NON-UNIQUE OPEN counted token={token}")
                is_unique = False

        campaign_id = doc.get("campaign_id")
        subscriber_id = doc.get("subscriber_id")
        ab_test_id = doc.get("ab_test_id")
        ab_variant = doc.get("variant")

        # 3) Event row logging
        # If track_unique_only=True → log only first open event
        # If False → log every open event
        if is_unique or not track_unique_only:
            await col.insert_one(
                {
                    "open_token": token,
                    "campaign_id": campaign_id,
                    "ab_test_id": ab_test_id,
                    "subscriber_id": subscriber_id,
                    "email": doc.get("email"),
                    "event_type": "opened",
                    "type": "event",
                    "ip_address": ip,
                    "user_agent": ua,
                    "timestamp": now,
                    "is_unique": is_unique,
                }
            )

        # 4a) Campaign analytics — only for real campaigns
        if is_unique and campaign_id:
            await _increment_analytics(str(campaign_id), "total_opened")

        # 4b) AB test results — update email_opened flag on the result doc
        if is_unique and ab_test_id:
            try:
                from database import get_ab_test_results_collection
                ab_col = get_ab_test_results_collection()
                await ab_col.update_one(
                    {
                        "test_id": ab_test_id,
                        "subscriber_id": subscriber_id,
                        "email_sent": True,
                    },
                    {
                        "$set": {
                            "email_opened": True,
                            "last_open_at": now,
                        },
                        "$min": {"first_open_at": now},  # only sets if null/lower
                    },
                )
            except Exception as _ae:
                logger.warning(f"[tracking] ab_test open update failed: {_ae}")

    except Exception as e:
        logger.error(f"[tracking] _record_open error: {e}", exc_info=True)


async def _record_click(token: str, url: str, ip: str, ua: str):
    """
    Persist a click event.
    - Unique click counting is atomic
    - Event logging obeys track_unique_only
    """
    try:
        col = get_email_events_collection()
        now = datetime.utcnow()
        track_unique_only = await _get_track_unique_only()

        logger.info(f"[tracking] _record_click START token={token}")

        claimed_first = await col.find_one_and_update(
            {
                "open_token": token,
                "type": "tracking_master",
                "click_count": 0,
            },
            {
                "$inc": {"click_count": 1},
                "$set": {
                    "first_click_at": now,
                    "last_event_at": now,
                },
            },
            return_document=True,
        )

        if claimed_first:
            logger.info(f"[tracking] UNIQUE CLICK counted token={token}")
            doc = claimed_first
            is_unique = True
        else:
            if track_unique_only:
                doc = await col.find_one(
                    {"open_token": token, "type": "tracking_master"}
                )
                if not doc:
                    logger.warning(
                        f"[tracking] _record_click master doc NOT FOUND token={token}"
                    )
                    return

                await col.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"last_event_at": now}},
                )

                logger.info(f"[tracking] DUPLICATE CLICK ignored token={token}")
                is_unique = False
            else:
                doc = await col.find_one_and_update(
                    {"open_token": token, "type": "tracking_master"},
                    {
                        "$inc": {"click_count": 1},
                        "$set": {"last_event_at": now},
                    },
                    return_document=True,
                )
                if not doc:
                    logger.warning(
                        f"[tracking] _record_click master doc NOT FOUND token={token}"
                    )
                    return

                logger.info(f"[tracking] NON-UNIQUE CLICK counted token={token}")
                is_unique = False

        campaign_id = doc.get("campaign_id")
        subscriber_id = doc.get("subscriber_id")
        ab_test_id = doc.get("ab_test_id")

        if is_unique or not track_unique_only:
            await col.insert_one(
                {
                    "open_token": token,
                    "campaign_id": campaign_id,
                    "ab_test_id": ab_test_id,
                    "subscriber_id": subscriber_id,
                    "email": doc.get("email"),
                    "event_type": "clicked",
                    "type": "event",
                    "url": url,
                    "ip_address": ip,
                    "user_agent": ua,
                    "timestamp": now,
                    "is_unique": is_unique,
                }
            )

        # Campaign analytics
        if is_unique and campaign_id:
            await _increment_analytics(str(campaign_id), "total_clicked")

        # AB test results — update email_clicked flag
        if is_unique and ab_test_id:
            try:
                from database import get_ab_test_results_collection
                ab_col = get_ab_test_results_collection()
                await ab_col.update_one(
                    {
                        "test_id": ab_test_id,
                        "subscriber_id": subscriber_id,
                        "email_sent": True,
                    },
                    {
                        "$set": {
                            "email_clicked": True,
                            "last_click_at": now,
                        },
                        "$min": {"first_click_at": now},
                    },
                )
            except Exception as _ae:
                logger.warning(f"[tracking] ab_test click update failed: {_ae}")

    except Exception as e:
        logger.error(f"[tracking] _record_click error: {e}", exc_info=True)


async def _increment_analytics(campaign_id: str, field: str):
    """
    Atomically increment one analytics counter and recompute rates.

    FIX: sent_count on the campaign doc is only written by finalize_campaign.
    During active sending it is 0, causing all rates to compute as 0.
    Now falls back to email_delivery_state then email_logs so rates are
    correct even while the campaign is still running.
    """
    try:
        analytics_col = get_analytics_collection()
        campaigns_col = get_campaigns_collection()
        from database import (
            get_email_delivery_state_collection,
            get_email_logs_collection,
        )
        delivery_state_col = get_email_delivery_state_collection()
        logs_col = get_email_logs_collection()

        cid = ObjectId(campaign_id) if ObjectId.is_valid(campaign_id) else campaign_id

        # Increment the counter first
        await analytics_col.update_one(
            {"campaign_id": cid},
            {"$inc": {field: 1}, "$set": {"updated_at": datetime.utcnow()}},
            upsert=True,
        )

        # Resolve total_sent — 3-tier fallback
        campaign = await campaigns_col.find_one(
            {"_id": cid}, {"sent_count": 1, "delivered_count": 1}
        )
        total_sent = 0
        if campaign:
            total_sent = (campaign.get("sent_count") or 0) + (
                campaign.get("delivered_count") or 0
            )

        if total_sent == 0:
            # Delivery state (written by workers on every send, pre-finalization)
            total_sent = await delivery_state_col.count_documents(
                {"campaign_id": cid, "state": {"$in": ["sent", "delivered"]}}
            )

        if total_sent == 0:
            # Legacy fallback: email_logs
            total_sent = await logs_col.count_documents(
                {"campaign_id": cid, "latest_status": {"$in": ["sent", "delivered"]}}
            )

        if total_sent == 0:
            # 4th fallback: use the snapshot stored by get_campaign_analytics
            # on the last page load — avoids re-counting if collection is large
            analytics_snap = await analytics_col.find_one(
                {"campaign_id": cid}, {"total_sent_snapshot": 1}
            )
            if analytics_snap:
                total_sent = analytics_snap.get("total_sent_snapshot", 0) or 0

        analytics = await analytics_col.find_one({"campaign_id": cid})

        if analytics and total_sent > 0:
            open_rate = round(
                analytics.get("total_opened", 0) / total_sent * 100, 2
            )
            click_rate = round(
                analytics.get("total_clicked", 0) / total_sent * 100, 2
            )
            unsub_rate = round(
                analytics.get("total_unsubscribed", 0) / total_sent * 100, 2
            )
            delivery_rate = round(
                max(0, total_sent - analytics.get("total_bounced", 0))
                / total_sent * 100,
                2,
            )

            await analytics_col.update_one(
                {"campaign_id": cid},
                {
                    "$set": {
                        "open_rate": open_rate,
                        "click_rate": click_rate,
                        "unsubscribe_rate": unsub_rate,
                        "delivery_rate": delivery_rate,
                        "total_sent_snapshot": total_sent,
                    }
                },
            )

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
async def open_pixel(token_gif: str, request: Request):
    """
    Serve 1×1 GIF and record an open event.

    IMPORTANT FIX:
    Use asyncio.create_task instead of BackgroundTasks.
    This avoids token mixups under rapid mail-client image fetches.
    """
    token = token_gif.removesuffix(".gif")
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")

    logger.info(f"[tracking] open_pixel HIT token={token} ip={ip}")

    asyncio.create_task(_record_open(token, ip, ua))

    return _pixel_response()


@router.get("/t/c/{token}", include_in_schema=False)
async def click_redirect(token: str, u: str = "", request: Request = None):
    """
    Record a click and redirect to the target URL.
    """
    target = urllib.parse.unquote(u) if u else "/"

    parsed = urllib.parse.urlparse(target)
    if parsed.scheme not in ("http", "https", ""):
        target = "/"

    if token:
        ip = request.client.host if request and request.client else "unknown"
        ua = request.headers.get("user-agent", "") if request else ""
        asyncio.create_task(_record_click(token, target, ip, ua))

    return RedirectResponse(url=target, status_code=302)


@router.get("/t/verify/{token}")
async def verify_unsubscribe_token(token: str):
    tokens_col = get_unsubscribe_tokens_collection()
    doc = await tokens_col.find_one({"token": token})

    if not doc:
        raise HTTPException(status_code=404, detail="Invalid unsubscribe link")
    if doc.get("used"):
        raise HTTPException(status_code=410, detail="This link has already been used")

    return {
        "valid": True,
        "email": doc["email"],
        "email_masked": _mask_email(doc["email"]),
        "campaign_id": doc.get("campaign_id"),
    }


@router.post("/t/u/{token}")
async def confirm_unsubscribe(token: str, request: Request):
    result = await _atomic_unsubscribe(token, request)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["reason"])
    return {"status": "ok", "email": result["email"]}


# ─────────────────────────────────────────────────────────────────────────────
# Shared atomic unsubscribe logic
# ─────────────────────────────────────────────────────────────────────────────


async def _atomic_unsubscribe(token: str, request: Request = None) -> dict:
    tokens_col = get_unsubscribe_tokens_collection()
    subscribers_col = get_subscribers_collection()
    suppressions_col = get_suppressions_collection()
    email_events_col = get_email_events_collection()

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

    try:
        await tokens_col.update_one(
            {"token": token},
            {"$set": {"used": True, "used_at": now, "used_from_ip": ip}},
        )
    except Exception as e:
        logger.error(f"[unsubscribe] failed to mark token used: {e}")
        return {"success": False, "reason": "internal_error"}

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

    try:
        existing_sup = await suppressions_col.find_one(
            {"email": email, "scope": "global"}
        )
        if existing_sup:
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
                "type": "unsubscribe",
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
                "type": "event",
                "timestamp": now,
                "ip_address": ip,
            }
        )
    except Exception as e:
        logger.warning(f"[unsubscribe] could not log event row: {e}")

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
    """
    import re

    def _replace(m):
        original_url = m.group(1)
        if original_url.startswith(("mailto:", "tel:", "#", "/t/c/")):
            return m.group(0)
        wrapped = build_click_redirect_url(open_token, original_url, base_url)
        return f'href="{wrapped}"'

    html = re.sub(r'href="([^"]+)"', _replace, html)

    def _replace_sq(m):
        original_url = m.group(1)
        if original_url.startswith(("mailto:", "tel:", "#", "/t/c/")):
            return m.group(0)
        wrapped = build_click_redirect_url(open_token, original_url, base_url)
        return f"href='{wrapped}'"

    html = re.sub(r"href='([^']+)'", _replace_sq, html)
    return html


# ── Settings helpers ──────────────────────────────────────────────────────────


async def get_tracking_flags() -> dict:
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


# ── Settings router ───────────────────────────────────────────────────────────
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
    return (
        domain.strip()
        .lower()
        .replace("https://", "")
        .replace("http://", "")
        .rstrip("/")
    )


@settings_router.get("/tracking")
async def get_tracking_settings():
    from database import get_settings_collection

    col = get_settings_collection()
    doc = await col.find_one({"type": "tracking"}) or {}
    return {
        "open_tracking_enabled": doc.get(
            "open_tracking_enabled", _TOGGLE_DEFAULTS["open_tracking_enabled"]
        ),
        "click_tracking_enabled": doc.get(
            "click_tracking_enabled", _TOGGLE_DEFAULTS["click_tracking_enabled"]
        ),
        "unsubscribe_tracking_enabled": doc.get(
            "unsubscribe_tracking_enabled",
            _TOGGLE_DEFAULTS["unsubscribe_tracking_enabled"],
        ),
        "track_unique_only": doc.get(
            "track_unique_only", _TOGGLE_DEFAULTS["track_unique_only"]
        ),
        "unsubscribe_domain": doc.get("unsubscribe_domain", ""),
        "open_tracking_domain": doc.get("open_tracking_domain", ""),
        "click_tracking_domain": doc.get("click_tracking_domain", ""),
    }


@settings_router.put("/tracking")
async def update_tracking_settings(payload: _TrackingSettingsUpdate):
    from database import get_settings_collection

    col = get_settings_collection()
    fields: dict = {"updated_at": datetime.utcnow()}

    if payload.open_tracking_enabled is not None:
        fields["open_tracking_enabled"] = payload.open_tracking_enabled
    if payload.click_tracking_enabled is not None:
        fields["click_tracking_enabled"] = payload.click_tracking_enabled
    if payload.unsubscribe_tracking_enabled is not None:
        fields["unsubscribe_tracking_enabled"] = payload.unsubscribe_tracking_enabled
    if payload.track_unique_only is not None:
        fields["track_unique_only"] = payload.track_unique_only

    if payload.unsubscribe_domain is not None:
        fields["unsubscribe_domain"] = _clean_domain(payload.unsubscribe_domain)
    if payload.open_tracking_domain is not None:
        fields["open_tracking_domain"] = _clean_domain(payload.open_tracking_domain)
    if payload.click_tracking_domain is not None:
        fields["click_tracking_domain"] = _clean_domain(payload.click_tracking_domain)

    await col.update_one(
        {"type": "tracking"},
        {"$set": fields, "$setOnInsert": {"type": "tracking"}},
        upsert=True,
    )
    logger.info(f"Tracking settings updated: {list(fields.keys())}")

    doc = await col.find_one({"type": "tracking"}) or {}
    return {
        "status": "saved",
        "open_tracking_enabled": doc.get(
            "open_tracking_enabled", _TOGGLE_DEFAULTS["open_tracking_enabled"]
        ),
        "click_tracking_enabled": doc.get(
            "click_tracking_enabled", _TOGGLE_DEFAULTS["click_tracking_enabled"]
        ),
        "unsubscribe_tracking_enabled": doc.get(
            "unsubscribe_tracking_enabled",
            _TOGGLE_DEFAULTS["unsubscribe_tracking_enabled"],
        ),
        "track_unique_only": doc.get(
            "track_unique_only", _TOGGLE_DEFAULTS["track_unique_only"]
        ),
        "unsubscribe_domain": doc.get("unsubscribe_domain", ""),
        "open_tracking_domain": doc.get("open_tracking_domain", ""),
        "click_tracking_domain": doc.get("click_tracking_domain", ""),
    }