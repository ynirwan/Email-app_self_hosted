"""
backend/routes/tracking.py  — PATCHED

Fixes applied vs original:
1. _record_open / _record_click: use $setOnInsert-style logic for first_open_at /
   first_click_at so NULL is correctly overwritten (MongoDB $min treats null as
   less than any date, so $min with a date never overwrites null).
   Now: $set first_open_at if it is null, $set last_open_at unconditionally.

2. create_ab_tracking_record_sync / create_ab_tracking_record for AB test sends:
   winner-send records now store campaign_id = ObjectId(test_id) in addition to
   ab_test_id so that _record_open event rows written to email_events are found
   by the winner-analytics endpoint which queries campaign_id = cid (ObjectId).
   Sample (non-winner) AB test tracking records keep campaign_id=None so they
   do NOT pollute normal campaign analytics.

3. _record_open / _record_click: when ab_test_id is set and is_unique is True,
   update ab_test_results using $set with explicit is_winner_send=True filter
   so winner-send opens update the correct result row (not sample rows).
   Also updates both winner-send rows AND sample rows that match.

4. _increment_analytics: for winner-send tracking records (campaign_id is an
   ObjectId equal to test_id), analytics counters are incremented so the
   winner report's open/click numbers reflect reality.
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

# ── 1×1 transparent GIF ──────────────────────────────────────────────────────
_PIXEL = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


def _pixel_response() -> Response:
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
# Token helpers
# ─────────────────────────────────────────────────────────────────────────────


def generate_tracking_token(campaign_id: str, subscriber_id: str, email: str) -> str:
    return secrets.token_urlsafe(24)


def _get_tracking_domain(key: str, fallback_env: str = "APP_BASE_URL") -> str:
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
    """Sync tracking master record for normal campaign emails."""
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
        return {"success": True, "token": open_token}

    except Exception as e:
        logger.exception(f"[tracking] create_tracking_record_sync FAILED token={open_token}: {e}")
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
    *,
    is_winner_send: bool = False,
) -> dict:
    """
    Sync tracking master record for A/B test emails.

    FIX: winner_send records store campaign_id = ObjectId(test_id) so that
    event rows written to email_events by _record_open/_record_click are found
    by the winner-analytics endpoint (which queries campaign_id = ObjectId(test_id)).

    Sample (non-winner) AB records keep campaign_id=None to avoid polluting
    normal campaign analytics.
    """
    try:
        from database import get_sync_email_events_collection

        col = get_sync_email_events_collection()
        now = datetime.utcnow()

        # FIX: winner sends carry campaign_id so analytics can find their events
        campaign_id_val = ObjectId(test_id) if is_winner_send and ObjectId.is_valid(test_id) else None

        result = col.update_one(
            {"open_token": open_token, "type": "tracking_master"},
            {
                "$setOnInsert": {
                    "open_token": open_token,
                    "ab_test_id": test_id,           # always string
                    "variant": variant,
                    "campaign_id": campaign_id_val,  # ObjectId for winner, None for sample
                    "is_winner_send": is_winner_send,
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
        return {"success": True, "token": open_token}
    except Exception as e:
        logger.exception(
            f"[tracking] create_ab_tracking_record_sync FAILED "
            f"token={open_token} test={test_id}: {e}"
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

    FIX: first_open_at was stored as null and never overwritten because
    MongoDB $min treats null < any date, so $min with a date never overwrites null.
    Now uses conditional $set: if first_open_at is null, set it; always set last_open_at.

    FIX: AB test results update now handles both sample and winner-send rows,
    and correctly sets first_open_at (was always null before).
    """
    try:
        col = get_email_events_collection()
        now = datetime.utcnow()
        track_unique_only = await _get_track_unique_only()

        logger.info(f"[tracking] _record_open START token={token}")

        # Atomically claim FIRST open
        claimed_first = await col.find_one_and_update(
            {
                "open_token": token,
                "type": "tracking_master",
                "open_count": 0,
            },
            {
                "$inc": {"open_count": 1},
                "$set": {
                    "first_open_at": now,   # FIX: use $set not $min (null issue)
                    "last_open_at": now,
                    "last_event_at": now,
                    "event_type": "opened",
                },
            },
            return_document=True,
        )

        if claimed_first:
            doc = claimed_first
            is_unique = True
            logger.info(f"[tracking] UNIQUE OPEN counted token={token}")
        else:
            if track_unique_only:
                doc = await col.find_one({"open_token": token, "type": "tracking_master"})
                if not doc:
                    logger.warning(f"[tracking] _record_open master doc NOT FOUND token={token}")
                    return
                await col.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"last_open_at": now, "last_event_at": now}},
                )
                logger.info(f"[tracking] DUPLICATE OPEN ignored token={token}")
                is_unique = False
            else:
                doc = await col.find_one_and_update(
                    {"open_token": token, "type": "tracking_master"},
                    {
                        "$inc": {"open_count": 1},
                        "$set": {"last_open_at": now, "last_event_at": now},
                    },
                    return_document=True,
                )
                if not doc:
                    logger.warning(f"[tracking] _record_open master doc NOT FOUND token={token}")
                    return
                logger.info(f"[tracking] NON-UNIQUE OPEN counted token={token}")
                is_unique = False

        campaign_id = doc.get("campaign_id")
        subscriber_id = doc.get("subscriber_id")
        ab_test_id = doc.get("ab_test_id")
        ab_variant = doc.get("variant")
        is_winner_send = doc.get("is_winner_send", False)

        # Event row logging
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
                    "is_winner_send": is_winner_send,
                }
            )

        # Campaign analytics (normal campaigns and winner sends that have campaign_id set)
        if is_unique and campaign_id:
            await _increment_analytics(str(campaign_id), "total_opened")

        # AB test results update — FIX: correct first_open_at, handle winner sends
        if is_unique and ab_test_id:
            try:
                from database import get_ab_test_results_collection
                ab_col = get_ab_test_results_collection()

                # Build query to find the correct result row
                result_query = {
                    "test_id": ab_test_id,
                    "subscriber_id": subscriber_id,
                    "email_sent": True,
                }
                if is_winner_send:
                    result_query["is_winner_send"] = True
                else:
                    result_query["is_winner_send"] = {"$ne": True}

                # FIX: Use proper first_open_at update (not $min which fails on null)
                await ab_col.update_one(
                    result_query,
                    {
                        "$set": {
                            "email_opened": True,
                            "last_open_at": now,
                        },
                        # Only set first_open_at if it was null
                        "$setOnInsert": {},  # placeholder
                    },
                )
                # Separately set first_open_at only if null
                await ab_col.update_one(
                    {**result_query, "first_open_at": None},
                    {"$set": {"first_open_at": now}},
                )
            except Exception as _ae:
                logger.warning(f"[tracking] ab_test open update failed: {_ae}")

    except Exception as e:
        logger.error(f"[tracking] _record_open error: {e}", exc_info=True)


async def _record_click(token: str, url: str, ip: str, ua: str):
    """
    Persist a click event.

    FIX: same first_click_at null issue as _record_open — use $set not $min.
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
                    "first_click_at": now,  # FIX: $set not $min
                    "last_click_at": now,
                    "last_event_at": now,
                },
            },
            return_document=True,
        )

        if claimed_first:
            doc = claimed_first
            is_unique = True
            logger.info(f"[tracking] UNIQUE CLICK counted token={token}")
        else:
            if track_unique_only:
                doc = await col.find_one({"open_token": token, "type": "tracking_master"})
                if not doc:
                    logger.warning(f"[tracking] _record_click master doc NOT FOUND token={token}")
                    return
                await col.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"last_click_at": now, "last_event_at": now}},
                )
                logger.info(f"[tracking] DUPLICATE CLICK ignored token={token}")
                is_unique = False
            else:
                doc = await col.find_one_and_update(
                    {"open_token": token, "type": "tracking_master"},
                    {
                        "$inc": {"click_count": 1},
                        "$set": {"last_click_at": now, "last_event_at": now},
                    },
                    return_document=True,
                )
                if not doc:
                    logger.warning(f"[tracking] _record_click master doc NOT FOUND token={token}")
                    return
                logger.info(f"[tracking] NON-UNIQUE CLICK counted token={token}")
                is_unique = False

        campaign_id = doc.get("campaign_id")
        subscriber_id = doc.get("subscriber_id")
        ab_test_id = doc.get("ab_test_id")
        is_winner_send = doc.get("is_winner_send", False)

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
                    "is_winner_send": is_winner_send,
                }
            )

        # Campaign analytics
        if is_unique and campaign_id:
            await _increment_analytics(str(campaign_id), "total_clicked")

        # AB test results update — FIX: correct first_click_at
        if is_unique and ab_test_id:
            try:
                from database import get_ab_test_results_collection
                ab_col = get_ab_test_results_collection()

                result_query = {
                    "test_id": ab_test_id,
                    "subscriber_id": subscriber_id,
                    "email_sent": True,
                }
                if is_winner_send:
                    result_query["is_winner_send"] = True
                else:
                    result_query["is_winner_send"] = {"$ne": True}

                await ab_col.update_one(
                    result_query,
                    {
                        "$set": {
                            "email_clicked": True,
                            "last_click_at": now,
                        },
                    },
                )
                # Set first_click_at only if null
                await ab_col.update_one(
                    {**result_query, "first_click_at": None},
                    {"$set": {"first_click_at": now}},
                )
            except Exception as _ae:
                logger.warning(f"[tracking] ab_test click update failed: {_ae}")

    except Exception as e:
        logger.error(f"[tracking] _record_click error: {e}", exc_info=True)


async def _increment_analytics(campaign_id: str, field: str):
    """
    Atomically increment one analytics counter and recompute rates.
    Works for both normal campaigns and winner sends (campaign_id = test_id).
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

        await analytics_col.update_one(
            {"campaign_id": cid},
            {"$inc": {field: 1}, "$set": {"updated_at": datetime.utcnow()}},
            upsert=True,
        )

        # Try to resolve total_sent from campaign doc first
        campaign = await campaigns_col.find_one(
            {"_id": cid}, {"sent_count": 1, "delivered_count": 1}
        )
        total_sent = 0
        if campaign:
            total_sent = (campaign.get("sent_count") or 0) + (
                campaign.get("delivered_count") or 0
            )

        if total_sent == 0:
            total_sent = await delivery_state_col.count_documents(
                {"campaign_id": cid, "state": {"$in": ["sent", "delivered"]}}
            )

        if total_sent == 0:
            total_sent = await logs_col.count_documents(
                {"campaign_id": cid, "latest_status": {"$in": ["sent", "delivered"]}}
            )

        if total_sent == 0:
            # For AB winner sends: count from ab_test_results
            try:
                from database import get_ab_test_results_collection
                ab_col = get_ab_test_results_collection()
                test_id_str = str(campaign_id)
                count_result = []
                async for r in ab_col.aggregate([
                    {"$match": {"test_id": test_id_str, "is_winner_send": True, "email_sent": True}},
                    {"$group": {"_id": "$subscriber_id"}},
                    {"$count": "n"},
                ]):
                    count_result.append(r)
                total_sent = count_result[0]["n"] if count_result else 0
            except Exception:
                pass

        if total_sent == 0:
            analytics_snap = await analytics_col.find_one(
                {"campaign_id": cid}, {"total_sent_snapshot": 1}
            )
            if analytics_snap:
                total_sent = analytics_snap.get("total_sent_snapshot", 0) or 0

        analytics = await analytics_col.find_one({"campaign_id": cid})

        if analytics and total_sent > 0:
            open_rate = round(analytics.get("total_opened", 0) / total_sent * 100, 2)
            click_rate = round(analytics.get("total_clicked", 0) / total_sent * 100, 2)
            unsub_rate = round(analytics.get("total_unsubscribed", 0) / total_sent * 100, 2)
            delivery_rate = round(
                max(0, total_sent - analytics.get("total_bounced", 0)) / total_sent * 100, 2
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
    token = token_gif.removesuffix(".gif")
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "")
    logger.info(f"[tracking] open_pixel HIT token={token} ip={ip}")
    asyncio.create_task(_record_open(token, ip, ua))
    return _pixel_response()


@router.get("/t/c/{token}", include_in_schema=False)
async def click_redirect(token: str, u: str = "", request: Request = None):
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
                        "campaign_id": campaign_id if campaign_id else existing_sup.get("campaign_id"),
                        "subscriber_id": subscriber_id if subscriber_id else existing_sup.get("subscriber_id"),
                    }
                },
            )
        else:
            await suppressions_col.insert_one(
                {
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
            )
    except Exception as e:
        logger.error(f"[unsubscribe] FAILED to write suppression for {email}: {e}")
        errors.append(f"suppressions: {e}")

    try:
        if campaign_id:
            await email_events_col.update_many(
                {
                    "email": email,
                    "campaign_id": ObjectId(campaign_id) if ObjectId.is_valid(campaign_id) else campaign_id,
                },
                {"$set": {"is_unsubscribed": True, "last_event_at": now}},
            )
    except Exception as e:
        logger.warning(f"[unsubscribe] could not update email_events: {e}")

    try:
        await email_events_col.insert_one(
            {
                "email": email,
                "campaign_id": ObjectId(campaign_id) if campaign_id and ObjectId.is_valid(campaign_id) else campaign_id,
                "subscriber_id": ObjectId(subscriber_id) if subscriber_id and ObjectId.is_valid(subscriber_id) else subscriber_id,
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
        doc = await col.find_one({"type": "tracking"}) or {}
        defaults = {"open_tracking_enabled": True, "click_tracking_enabled": True}
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
    return domain.strip().lower().replace("https://", "").replace("http://", "").rstrip("/")


@settings_router.get("/tracking")
async def get_tracking_settings():
    from database import get_settings_collection
    col = get_settings_collection()
    doc = await col.find_one({"type": "tracking"}) or {}
    return {
        "open_tracking_enabled": doc.get("open_tracking_enabled", _TOGGLE_DEFAULTS["open_tracking_enabled"]),
        "click_tracking_enabled": doc.get("click_tracking_enabled", _TOGGLE_DEFAULTS["click_tracking_enabled"]),
        "unsubscribe_tracking_enabled": doc.get("unsubscribe_tracking_enabled", _TOGGLE_DEFAULTS["unsubscribe_tracking_enabled"]),
        "track_unique_only": doc.get("track_unique_only", _TOGGLE_DEFAULTS["track_unique_only"]),
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
        "open_tracking_enabled": doc.get("open_tracking_enabled", _TOGGLE_DEFAULTS["open_tracking_enabled"]),
        "click_tracking_enabled": doc.get("click_tracking_enabled", _TOGGLE_DEFAULTS["click_tracking_enabled"]),
        "unsubscribe_tracking_enabled": doc.get("unsubscribe_tracking_enabled", _TOGGLE_DEFAULTS["unsubscribe_tracking_enabled"]),
        "track_unique_only": doc.get("track_unique_only", _TOGGLE_DEFAULTS["track_unique_only"]),
        "unsubscribe_domain": doc.get("unsubscribe_domain", ""),
        "open_tracking_domain": doc.get("open_tracking_domain", ""),
        "click_tracking_domain": doc.get("click_tracking_domain", ""),
    }