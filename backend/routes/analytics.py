# backend/routes/analytics.py
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import Optional
from datetime import datetime, timedelta
from database import (
    get_analytics_collection,
    get_email_events_collection,
    get_campaigns_collection,
    get_email_logs_collection,
    get_email_delivery_state_collection,
)
from bson import ObjectId
from bson.errors import InvalidId
import logging
import csv
import io

logger = logging.getLogger(__name__)
router = APIRouter()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _safe_oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid campaign id")


def _serialize_event(doc: dict) -> dict:
    """
    Recursively convert ObjectId values to strings in an email_events document.
    Needed because tracking stores subscriber_id and campaign_id as ObjectId.
    """
    out = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            out[k] = str(v)
        elif isinstance(v, dict):
            out[k] = _serialize_event(v)
        elif isinstance(v, list):
            new_list = []
            for i in v:
                if isinstance(i, ObjectId):
                    new_list.append(str(i))
                elif isinstance(i, dict):
                    new_list.append(_serialize_event(i))
                else:
                    new_list.append(i)
            out[k] = new_list
        else:
            out[k] = v
    return out


def _parse_device(ua: str) -> str:
    """Best-effort device type from User-Agent string."""
    if not ua:
        return "Unknown"
    ua_lower = ua.lower()
    if any(x in ua_lower for x in ("iphone", "android", "mobile", "blackberry")):
        return "Mobile"
    if any(x in ua_lower for x in ("ipad", "tablet")):
        return "Tablet"
    if any(
        x in ua_lower
        for x in ("mozilla", "chrome", "safari", "firefox", "edge", "opera", "msie")
    ):
        return "Desktop"
    return "Unknown"


def _get_event_email(event: dict) -> str:
    """Handle both old/new field names."""
    return event.get("email") or event.get("subscriber_email") or ""


# ──────────────────────────────────────────────────────────────────────────────
# Campaign Analytics
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/campaigns/{campaign_id}")
async def get_campaign_analytics(campaign_id: str):
    try:
        cid = _safe_oid(campaign_id)

        analytics_collection = get_analytics_collection()
        events_collection = get_email_events_collection()
        campaigns_collection = get_campaigns_collection()
        logs_col = get_email_logs_collection()

        campaign = await campaigns_collection.find_one({"_id": cid})
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        campaign["_id"] = str(campaign["_id"])

        analytics = await analytics_collection.find_one({"campaign_id": cid})

        if not analytics:
            analytics = {
                "campaign_id": cid,
                "total_delivered": 0,
                "total_bounced": 0,
                "total_opened": 0,
                "total_clicked": 0,
                "total_unsubscribed": 0,
                "total_spam_reports": 0,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
            res = await analytics_collection.insert_one(analytics)
            analytics["_id"] = res.inserted_id

        analytics["_id"] = str(analytics["_id"])
        analytics["campaign_id"] = str(analytics["campaign_id"])

        # ── total_sent resolution ─────────────────
        total_sent = campaign.get("sent_count", 0) or 0

        if total_sent == 0:
            delivery_state_col = get_email_delivery_state_collection()
            total_sent = await delivery_state_col.count_documents(
                {"campaign_id": cid, "state": {"$in": ["sent", "delivered"]}}
            )

        if total_sent == 0:
            total_sent = await logs_col.count_documents(
                {"campaign_id": cid, "latest_status": {"$in": ["sent", "delivered"]}}
            )

        # ── FIX: always recompute ─────────────────

        total_delivered = await logs_col.count_documents(
            {"campaign_id": cid, "latest_status": "delivered"}
        )

        total_bounced = await events_collection.count_documents(
            {"campaign_id": cid, "event_type": "bounced", "type": "event"}
        )
        if total_bounced == 0:
            total_bounced = await logs_col.count_documents(
                {"campaign_id": cid, "latest_status": {"$in": ["bounced", "bounce"]}}
            )

        total_opened = await events_collection.count_documents(
            {"campaign_id": cid, "event_type": "opened", "type": "event"}
        )

        total_clicked = await events_collection.count_documents(
            {"campaign_id": cid, "event_type": "clicked", "type": "event"}
        )

        total_unsubscribed = await events_collection.count_documents(
            {"campaign_id": cid, "event_type": "unsubscribed", "type": "event"}
        )

        total_spam_reports = await events_collection.count_documents(
            {"campaign_id": cid, "event_type": "spam_report", "type": "event"}
        )

        if total_delivered == 0 and total_sent > 0:
            total_delivered = max(0, total_sent - total_bounced)

        delivery_rate = round((total_delivered / total_sent) * 100, 1) if total_sent else 0
        open_rate = round((total_opened / total_sent) * 100, 1) if total_sent else 0
        click_rate = round((total_clicked / total_sent) * 100, 1) if total_sent else 0
        bounce_rate = round((total_bounced / total_sent) * 100, 1) if total_sent else 0
        unsubscribe_rate = round((total_unsubscribed / total_sent) * 100, 1) if total_sent else 0

        await analytics_collection.update_one(
            {"campaign_id": cid},
            {
                "$max": {
                    "total_delivered": total_delivered,
                    "total_bounced": total_bounced,
                    "total_spam_reports": total_spam_reports,
                },
                "$set": {
                    "total_sent_snapshot": total_sent,
                    "total_opened": total_opened,
                    "total_clicked": total_clicked,
                    "total_unsubscribed": total_unsubscribed,
                    "delivery_rate": delivery_rate,
                    "open_rate": open_rate,
                    "click_rate": click_rate,
                    "bounce_rate": bounce_rate,
                    "unsubscribe_rate": unsubscribe_rate,
                    "updated_at": datetime.utcnow(),
                },
            },
        )

        return {
            "campaign": campaign,
            "analytics": {
                "total_sent": total_sent,
                "total_delivered": total_delivered,
                "total_bounced": total_bounced,
                "total_opened": total_opened,
                "total_clicked": total_clicked,
                "total_unsubscribed": total_unsubscribed,
                "total_spam_reports": total_spam_reports,
                "delivery_rate": delivery_rate,
                "open_rate": open_rate,
                "click_rate": click_rate,
                "bounce_rate": bounce_rate,
                "unsubscribe_rate": unsubscribe_rate,
            },
        }

    except Exception as e:
        logger.error(f"Error getting campaign analytics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


async def get_top_clicked_links(campaign_id: str, limit: int = 10):
    """Get top clicked links for a campaign"""
    events_collection = get_email_events_collection()
    cid = _safe_oid(campaign_id)

    pipeline = [
        {
            "$match": {
                "campaign_id": cid,
                "event_type": "clicked",
                "type": "event",
                "url": {"$exists": True, "$ne": None, "$ne": ""},
            }
        },
        {"$group": {"_id": "$url", "clicks": {"$sum": 1}}},
        {"$sort": {"clicks": -1}},
        {"$limit": limit},
        {"$project": {"url": "$_id", "clicks": 1, "_id": 0}},
    ]

    top_links = []
    async for link in events_collection.aggregate(pipeline):
        top_links.append(link)

    return top_links


# ──────────────────────────────────────────────────────────────────────────────
# Analytics Counter Updater
# ──────────────────────────────────────────────────────────────────────────────


async def update_analytics_counters(
    campaign_id: str, event_type: str, increment: int = 1
):
    """Update analytics counters based on email events"""
    analytics_collection = get_analytics_collection()
    campaigns_collection = get_campaigns_collection()

    cid = _safe_oid(campaign_id)

    campaign = await campaigns_collection.find_one({"_id": cid}, {"sent_count": 1})
    total_sent = campaign.get("sent_count", 0) if campaign else 0

    field_mapping = {
        "delivered": "total_delivered",
        "opened": "total_opened",
        "clicked": "total_clicked",
        "bounced": "total_bounced",
        "unsubscribed": "total_unsubscribed",
        "spam_report": "total_spam_reports",
    }

    if event_type not in field_mapping:
        return

    field_name = field_mapping[event_type]

    await analytics_collection.update_one(
        {"campaign_id": cid},
        {
            "$inc": {field_name: increment},
            "$set": {"updated_at": datetime.utcnow()},
            "$setOnInsert": {
                "campaign_id": cid,
                "created_at": datetime.utcnow(),
            },
        },
        upsert=True,
    )

    if total_sent > 0:
        analytics = await analytics_collection.find_one({"campaign_id": cid})
        if analytics:
            total_delivered = analytics.get("total_delivered", 0)
            total_bounced = analytics.get("total_bounced", 0)
            total_opened = analytics.get("total_opened", 0)
            total_clicked = analytics.get("total_clicked", 0)
            total_unsubscribed = analytics.get("total_unsubscribed", 0)

            if total_delivered == 0:
                total_delivered = max(0, total_sent - total_bounced)

            rates_update = {
                "delivery_rate": round((total_delivered / total_sent) * 100, 1),
                "open_rate": round((total_opened / total_sent) * 100, 1),
                "click_rate": round((total_clicked / total_sent) * 100, 1),
                "bounce_rate": round((total_bounced / total_sent) * 100, 1),
                "unsubscribe_rate": round((total_unsubscribed / total_sent) * 100, 1),
                "updated_at": datetime.utcnow(),
            }

            await analytics_collection.update_one(
                {"campaign_id": cid}, {"$set": rates_update}
            )


# ──────────────────────────────────────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/dashboard")
async def get_analytics_dashboard(days: int = Query(default=30, ge=1, le=365)):
    """Get dashboard analytics for multiple campaigns"""
    try:
        campaigns_collection = get_campaigns_collection()
        analytics_collection = get_analytics_collection()
        delivery_state_col = get_email_delivery_state_collection()
        logs_col = get_email_logs_collection()

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        campaigns = []
        async for campaign in campaigns_collection.find(
            {
                "created_at": {"$gte": start_date, "$lte": end_date},
                # Exclude ghost campaigns created by old A/B test code
                "ab_test_id": {"$exists": False},
            }
        ).sort("created_at", -1):
            campaign_id_str = str(campaign["_id"])
            campaign["_id"] = campaign_id_str
            cid = _safe_oid(campaign_id_str)

            # 3-tier sent_count resolution
            camp_sent = campaign.get("sent_count", 0) or 0
            if camp_sent == 0:
                camp_sent = await delivery_state_col.count_documents(
                    {"campaign_id": cid, "state": {"$in": ["sent", "delivered"]}}
                )
            if camp_sent == 0:
                camp_sent = await logs_col.count_documents(
                    {"campaign_id": cid, "latest_status": {"$in": ["sent", "delivered"]}}
                )

            analytics = await analytics_collection.find_one({"campaign_id": cid})

            if analytics:
                analytics["_id"] = str(analytics["_id"])
                analytics["campaign_id"] = campaign_id_str
                # Use total_sent_snapshot if available (written by get_campaign_analytics)
                # to avoid recounting on every dashboard load
                resolved_sent = analytics.get("total_sent_snapshot") or camp_sent
                analytics["total_sent"] = resolved_sent

                if resolved_sent > 0:
                    analytics["open_rate"] = round(
                        (analytics.get("total_opened", 0) / resolved_sent) * 100, 2
                    )
                    analytics["click_rate"] = round(
                        (analytics.get("total_clicked", 0) / resolved_sent) * 100, 2
                    )
                    analytics["delivery_rate"] = round(
                        (
                            analytics.get(
                                "total_delivered",
                                max(0, resolved_sent - analytics.get("total_bounced", 0)),
                            )
                            / resolved_sent
                        )
                        * 100,
                        2,
                    )

                campaign["analytics"] = analytics
            else:
                campaign["analytics"] = {
                    "total_sent": camp_sent,
                    "total_opened": 0,
                    "total_clicked": 0,
                    "total_delivered": 0,
                    "open_rate": 0.0,
                    "click_rate": 0.0,
                    "delivery_rate": 0.0,
                }

            campaigns.append(campaign)

        total_campaigns = len(campaigns)
        total_sent = sum(c["analytics"].get("total_sent", 0) for c in campaigns)
        total_opened = sum(c["analytics"].get("total_opened", 0) for c in campaigns)
        total_clicked = sum(c["analytics"].get("total_clicked", 0) for c in campaigns)

        avg_open_rate = (total_opened / total_sent * 100) if total_sent else 0
        avg_click_rate = (total_clicked / total_sent * 100) if total_sent else 0

        return {
            "summary": {
                "total_campaigns": total_campaigns,
                "total_emails_sent": total_sent,
                "total_opens": total_opened,
                "total_clicks": total_clicked,
                "average_open_rate": round(avg_open_rate, 2),
                "average_click_rate": round(avg_click_rate, 2),
            },
            "campaigns": campaigns,
            "date_range": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": days,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting dashboard analytics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


# ──────────────────────────────────────────────────────────────────────────────
# Openers / Clickers
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/campaigns/{campaign_id}/openers")
async def get_campaign_openers(
    campaign_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Return a list of subscribers who opened this campaign.
    """
    try:
        cid = _safe_oid(campaign_id)
        col = get_email_events_collection()

        pipeline = [
            {
                "$match": {
                    "campaign_id": cid,
                    "event_type": "opened",
                    "type": "event",
                }
            },
            {"$sort": {"timestamp": -1}},
            {"$skip": skip},
            {"$limit": limit},
            {
                "$project": {
                    "_id": 0,
                    "email": {"$ifNull": ["$email", "$subscriber_email"]},
                    "ip_address": 1,
                    "user_agent": 1,
                    "timestamp": 1,
                    "open_token": 1,
                }
            },
        ]

        rows = []
        async for doc in col.aggregate(pipeline):
            doc["device"] = _parse_device(doc.get("user_agent", ""))
            rows.append(doc)

        total = await col.count_documents(
            {
                "campaign_id": cid,
                "event_type": "opened",
                "type": "event",
            }
        )

        return {"total": total, "skip": skip, "limit": limit, "rows": rows}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_campaign_openers error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load openers")


@router.get("/campaigns/{campaign_id}/clickers")
async def get_campaign_clickers(
    campaign_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Return a list of subscribers who clicked a link in this campaign.
    """
    try:
        cid = _safe_oid(campaign_id)
        col = get_email_events_collection()

        pipeline = [
            {
                "$match": {
                    "campaign_id": cid,
                    "event_type": "clicked",
                    "type": "event",
                }
            },
            {"$sort": {"timestamp": -1}},
            {"$skip": skip},
            {"$limit": limit},
            {
                "$project": {
                    "_id": 0,
                    "email": {"$ifNull": ["$email", "$subscriber_email"]},
                    "url": 1,
                    "ip_address": 1,
                    "user_agent": 1,
                    "timestamp": 1,
                }
            },
        ]

        rows = []
        async for doc in col.aggregate(pipeline):
            doc["device"] = _parse_device(doc.get("user_agent", ""))
            rows.append(doc)

        total = await col.count_documents(
            {
                "campaign_id": cid,
                "event_type": "clicked",
                "type": "event",
            }
        )

        return {"total": total, "skip": skip, "limit": limit, "rows": rows}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_campaign_clickers error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load clickers")


# ──────────────────────────────────────────────────────────────────────────────
# Unified Metric Detail
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/campaigns/{campaign_id}/detail")
async def get_campaign_metric_detail(
    campaign_id: str,
    metric: str = Query(
        ...,
        description="opened | clicked | bounced | unsubscribed | delivered | spam_report",
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    """
    Unified detail endpoint for any campaign metric.
    """
    try:
        col = get_email_events_collection()
        valid = {
            "opened",
            "clicked",
            "bounced",
            "unsubscribed",
            "delivered",
            "spam_report",
        }
        if metric not in valid:
            raise HTTPException(
                status_code=400,
                detail=f"metric must be one of: {', '.join(sorted(valid))}",
            )

        cid = _safe_oid(campaign_id)

        # ── Special handling for "delivered" ─────────────────────────────────
        # email_events only has "delivered" rows if the provider sends delivery
        # confirmation webhooks. Most SMTP/SES setups write to email_logs instead
        # (ses_webhook_tasks writes latest_status="delivered").
        # Fall back to email_logs when email_events has no delivered records.
        if metric == "delivered":
            events_delivered_count = await col.count_documents(
                {"campaign_id": cid, "event_type": "delivered", "type": "event"}
            )
            if events_delivered_count == 0:
                logs_col = get_email_logs_collection()
                total_log = await logs_col.count_documents(
                    {"campaign_id": cid, "latest_status": "delivered"}
                )
                log_rows = []
                async for doc in logs_col.find(
                    {"campaign_id": cid, "latest_status": "delivered"},
                    {"email": 1, "delivered_at": 1, "sent_at": 1, "subscriber_id": 1},
                ).sort("delivered_at", -1).skip(skip).limit(limit):
                    log_rows.append({
                        "email": doc.get("email", ""),
                        "timestamp": doc.get("delivered_at") or doc.get("sent_at"),
                        "is_unique": True,
                        "total_count": 1,
                        "source": "email_logs",
                    })
                return {
                    "metric": metric,
                    "total_all": total_log,
                    "total_unique": total_log,
                    "total_duplicate": 0,
                    "skip": skip,
                    "limit": limit,
                    "rows": log_rows,
                    "source": "email_logs",
                }

        group_key = (
            {"email": "$email", "url": "$url"}
            if metric == "clicked"
            else {"email": "$email"}
        )

        pipeline = [
            {
                "$match": {
                    "campaign_id": cid,
                    "event_type": metric,
                    "type": "event",
                }
            },
            {"$addFields": {"email": {"$ifNull": ["$email", "$subscriber_email"]}}},
            {"$sort": {"timestamp": 1}},
            {
                "$group": {
                    "_id": group_key,
                    "all_events": {
                        "$push": {
                            "timestamp": "$timestamp",
                            "ip_address": "$ip_address",
                            "user_agent": "$user_agent",
                        }
                    },
                    "total_count": {"$sum": 1},
                }
            },
            {
                "$unwind": {
                    "path": "$all_events",
                    "includeArrayIndex": "occurrence_index",
                }
            },
            {
                "$addFields": {
                    "is_unique": {"$eq": ["$occurrence_index", 0]},
                    "email": "$_id.email",
                    "url": "$_id.url",
                    "timestamp": "$all_events.timestamp",
                    "ip_address": "$all_events.ip_address",
                    "user_agent": "$all_events.user_agent",
                }
            },
            {"$sort": {"timestamp": -1}},
            {"$skip": skip},
            {"$limit": limit},
            {
                "$project": {
                    "_id": 0,
                    "email": 1,
                    "url": 1,
                    "ip_address": 1,
                    "user_agent": 1,
                    "timestamp": 1,
                    "is_unique": 1,
                    "total_count": 1,
                }
            },
        ]

        rows = []
        async for doc in col.aggregate(pipeline):
            doc["device"] = _parse_device(doc.get("user_agent", ""))
            rows.append(doc)

        total_all = await col.count_documents(
            {
                "campaign_id": cid,
                "event_type": metric,
                "type": "event",
            }
        )

        unique_group_key = (
            {"email": "$email", "url": "$url"}
            if metric == "clicked"
            else {"email": "$email"}
        )

        unique_pipeline = [
            {
                "$match": {
                    "campaign_id": cid,
                    "event_type": metric,
                    "type": "event",
                }
            },
            {"$addFields": {"email": {"$ifNull": ["$email", "$subscriber_email"]}}},
            {"$group": {"_id": unique_group_key}},
            {"$count": "n"},
        ]

        unique_result = []
        async for r in col.aggregate(unique_pipeline):
            unique_result.append(r)

        total_unique = unique_result[0]["n"] if unique_result else 0
        total_duplicate = max(0, total_all - total_unique)

        return {
            "metric": metric,
            "total_all": total_all,
            "total_unique": total_unique,
            "total_duplicate": total_duplicate,
            "skip": skip,
            "limit": limit,
            "rows": rows,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_campaign_metric_detail error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load metric detail")


# ──────────────────────────────────────────────────────────────────────────────
# CSV Export
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/campaigns/{campaign_id}/export")
async def export_campaign_report(
    campaign_id: str,
    event_type: str = Query(
        default="all",
        description="Event type: all, opened, clicked, bounced, unsubscribed, spam_report, delivered",
    ),
):
    """Export campaign analytics as a CSV file"""
    try:
        cid = _safe_oid(campaign_id)

        campaigns_collection = get_campaigns_collection()
        events_collection = get_email_events_collection()
        analytics_collection = get_analytics_collection()

        campaign = await campaigns_collection.find_one({"_id": cid})
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        campaign_title = campaign.get("title", "campaign").replace(" ", "_").lower()

        output = io.StringIO()
        writer = csv.writer(output)

        if event_type == "all":
            analytics = await analytics_collection.find_one({"campaign_id": cid}) or {}
            total_sent = campaign.get("sent_count", 0)

            writer.writerow(["Campaign Report"])
            writer.writerow(["Campaign Title", campaign.get("title", "")])
            writer.writerow(["Subject", campaign.get("subject", "")])
            writer.writerow(["Sender Email", campaign.get("sender_email", "")])
            writer.writerow(["Reply To", campaign.get("reply_to", "")])
            writer.writerow(["Status", campaign.get("status", "")])
            writer.writerow(
                ["Target Lists", ", ".join(campaign.get("target_lists", []))]
            )
            writer.writerow(["Started At", str(campaign.get("started_at", ""))])
            writer.writerow(["Completed At", str(campaign.get("completed_at", ""))])
            writer.writerow([])
            writer.writerow(["Metric", "Count", "Rate"])
            writer.writerow(["Total Sent", total_sent, "100%"])
            writer.writerow(
                [
                    "Delivered",
                    analytics.get("total_delivered", 0),
                    f"{analytics.get('delivery_rate', 0)}%",
                ]
            )
            writer.writerow(
                [
                    "Opened",
                    analytics.get("total_opened", 0),
                    f"{analytics.get('open_rate', 0)}%",
                ]
            )
            writer.writerow(
                [
                    "Clicked",
                    analytics.get("total_clicked", 0),
                    f"{analytics.get('click_rate', 0)}%",
                ]
            )
            writer.writerow(
                [
                    "Bounced",
                    analytics.get("total_bounced", 0),
                    f"{analytics.get('bounce_rate', 0)}%",
                ]
            )
            writer.writerow(
                [
                    "Unsubscribed",
                    analytics.get("total_unsubscribed", 0),
                    f"{analytics.get('unsubscribe_rate', 0)}%",
                ]
            )
            writer.writerow(
                ["Spam Reports", analytics.get("total_spam_reports", 0), ""]
            )
            writer.writerow([])
            writer.writerow(["--- Event Log ---"])
            writer.writerow(
                ["Email", "Event Type", "Timestamp", "URL", "IP", "User Agent"]
            )

            async for event in events_collection.find(
                {"campaign_id": cid, "type": "event"}
            ).sort("timestamp", -1):
                writer.writerow(
                    [
                        _get_event_email(event),
                        event.get("event_type", ""),
                        str(event.get("timestamp", "")),
                        event.get("url", ""),
                        event.get("ip_address", ""),
                        event.get("user_agent", ""),
                    ]
                )

            filename = f"{campaign_title}_full_report.csv"

        else:
            query = {
                "campaign_id": cid,
                "event_type": event_type,
                "type": "event",
            }

            label_map = {
                "opened": "Opens",
                "clicked": "Clicks",
                "bounced": "Bounces",
                "unsubscribed": "Unsubscribes",
                "spam_report": "Spam Reports",
                "delivered": "Delivered",
            }
            label = label_map.get(event_type, event_type.capitalize())

            writer.writerow([f"Campaign {label} Report"])
            writer.writerow(["Campaign", campaign.get("title", "")])
            writer.writerow([])

            if event_type == "clicked":
                writer.writerow(["Email", "URL", "Timestamp", "IP", "User Agent"])
                async for event in events_collection.find(query).sort("timestamp", -1):
                    writer.writerow(
                        [
                            _get_event_email(event),
                            event.get("url", ""),
                            str(event.get("timestamp", "")),
                            event.get("ip_address", ""),
                            event.get("user_agent", ""),
                        ]
                    )
            else:
                writer.writerow(["Email", "Timestamp", "IP", "User Agent"])
                async for event in events_collection.find(query).sort("timestamp", -1):
                    writer.writerow(
                        [
                            _get_event_email(event),
                            str(event.get("timestamp", "")),
                            event.get("ip_address", ""),
                            event.get("user_agent", ""),
                        ]
                    )

            filename = f"{campaign_title}_{event_type}.csv"

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting campaign report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Export failed")