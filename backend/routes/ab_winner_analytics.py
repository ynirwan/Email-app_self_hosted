import csv
import io
import logging
from datetime import datetime
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from database import (
    get_ab_tests_collection,
    get_ab_test_results_collection,
    get_email_events_collection,
    get_email_logs_collection,
    get_email_delivery_state_collection,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _safe_oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid ID")


def _parse_device(ua: str) -> str:
    if not ua:
        return "Unknown"
    u = ua.lower()
    if any(x in u for x in ("iphone", "android", "mobile", "blackberry")):
        return "Mobile"
    if any(x in u for x in ("ipad", "tablet")):
        return "Tablet"
    if any(x in u for x in ("mozilla", "chrome", "safari", "firefox", "edge", "opera")):
        return "Desktop"
    return "Unknown"


# ── Summary analytics ──────────────────────────────────────────────────────────


@router.get("/ab-tests/{test_id}/winner-analytics")
async def get_winner_analytics(test_id: str):
    """
    Full analytics summary for the winner send phase.
    Returns the same metrics shape as /analytics/campaigns/{id}
    so the same frontend components can render it.
    """
    try:
        cid = _safe_oid(test_id)

        col = get_ab_tests_collection()
        test = await col.find_one({"_id": cid})
        if not test:
            raise HTTPException(status_code=404, detail="A/B test not found")

        events_col = get_email_events_collection()
        logs_col = get_email_logs_collection()
        results_col = get_ab_test_results_collection()

        # Total sent — from ab_test_results (is_winner_send=True, email_sent=True)
        total_sent = await results_col.count_documents(
            {
                "test_id": test_id,
                "is_winner_send": True,
                "email_sent": True,
            }
        )
        total_failed = await results_col.count_documents(
            {
                "test_id": test_id,
                "is_winner_send": True,
                "email_sent": False,
            }
        )

        # Events come from email_events collection with campaign_id = test_id
        # (tracking writes campaign_id=test_id for winner sends)
        total_opened = await events_col.count_documents(
            {
                "campaign_id": cid,
                "event_type": "opened",
                "type": "event",
            }
        )
        total_clicked = await events_col.count_documents(
            {
                "campaign_id": cid,
                "event_type": "clicked",
                "type": "event",
            }
        )
        total_bounced = await events_col.count_documents(
            {
                "campaign_id": cid,
                "event_type": "bounced",
                "type": "event",
            }
        )
        total_unsubscribed = await events_col.count_documents(
            {
                "campaign_id": cid,
                "event_type": "unsubscribed",
                "type": "event",
            }
        )
        total_spam = await events_col.count_documents(
            {
                "campaign_id": cid,
                "event_type": "spam_report",
                "type": "event",
            }
        )

        # Delivered = sent - bounced (same logic as normal campaign)
        total_delivered = max(0, total_sent - total_bounced)

        def rate(n, d):
            return round(n / d * 100, 1) if d else 0

        return {
            "test_id": test_id,
            "test_name": test.get("test_name", ""),
            "winner_variant": test.get("winner_variant"),
            "winner_send_status": test.get("winner_send_status"),
            "winner_send_started_at": test.get("winner_send_started_at"),
            "winner_send_completed_at": test.get("winner_send_completed_at"),
            "analytics": {
                "total_sent": total_sent,
                "total_failed": total_failed,
                "total_delivered": total_delivered,
                "total_opened": total_opened,
                "total_clicked": total_clicked,
                "total_bounced": total_bounced,
                "total_unsubscribed": total_unsubscribed,
                "total_spam_reports": total_spam,
                "delivery_rate": rate(total_delivered, total_sent),
                "open_rate": rate(total_opened, total_sent),
                "click_rate": rate(total_clicked, total_sent),
                "bounce_rate": rate(total_bounced, total_sent),
                "unsubscribe_rate": rate(total_unsubscribed, total_sent),
                "fail_rate": rate(total_failed, total_sent + total_failed),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"winner-analytics error for {test_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load winner analytics")


# ── Openers / Clickers ─────────────────────────────────────────────────────────


@router.get("/ab-tests/{test_id}/winner-openers")
async def get_winner_openers(
    test_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    try:
        cid = _safe_oid(test_id)
        col = get_email_events_collection()
        pipeline = [
            {"$match": {"campaign_id": cid, "event_type": "opened", "type": "event"}},
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
                }
            },
        ]
        rows = []
        async for doc in col.aggregate(pipeline):
            doc["device"] = _parse_device(doc.get("user_agent", ""))
            rows.append(doc)
        total = await col.count_documents(
            {"campaign_id": cid, "event_type": "opened", "type": "event"}
        )
        return {"total": total, "skip": skip, "limit": limit, "rows": rows}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"winner-openers error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load openers")


@router.get("/ab-tests/{test_id}/winner-clickers")
async def get_winner_clickers(
    test_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    try:
        cid = _safe_oid(test_id)
        col = get_email_events_collection()
        pipeline = [
            {"$match": {"campaign_id": cid, "event_type": "clicked", "type": "event"}},
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
            {"campaign_id": cid, "event_type": "clicked", "type": "event"}
        )
        return {"total": total, "skip": skip, "limit": limit, "rows": rows}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"winner-clickers error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load clickers")


# ── Unified metric detail (mirrors /analytics/campaigns/{id}/detail) ──────────


@router.get("/ab-tests/{test_id}/winner-detail")
async def get_winner_metric_detail(
    test_id: str,
    metric: str = Query(
        ..., description="opened|clicked|bounced|unsubscribed|spam_report"
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    valid = {"opened", "clicked", "bounced", "unsubscribed", "spam_report"}
    if metric not in valid:
        raise HTTPException(
            status_code=400, detail=f"metric must be one of: {', '.join(sorted(valid))}"
        )
    try:
        cid = _safe_oid(test_id)
        col = get_email_events_collection()

        group_key = (
            {"email": "$email", "url": "$url"}
            if metric == "clicked"
            else {"email": "$email"}
        )

        pipeline = [
            {"$match": {"campaign_id": cid, "event_type": metric, "type": "event"}},
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
            {"campaign_id": cid, "event_type": metric, "type": "event"}
        )

        unique_pipeline = [
            {"$match": {"campaign_id": cid, "event_type": metric, "type": "event"}},
            {"$addFields": {"email": {"$ifNull": ["$email", "$subscriber_email"]}}},
            {"$group": {"_id": group_key}},
            {"$count": "n"},
        ]
        ur = []
        async for r in col.aggregate(unique_pipeline):
            ur.append(r)
        total_unique = ur[0]["n"] if ur else 0

        return {
            "metric": metric,
            "total_all": total_all,
            "total_unique": total_unique,
            "total_duplicate": max(0, total_all - total_unique),
            "skip": skip,
            "limit": limit,
            "rows": rows,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"winner-detail error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load metric detail")


# ── Recipients list (all winner send recipients with status) ──────────────────


@router.get("/ab-tests/{test_id}/winner-recipients")
async def get_winner_recipients(
    test_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None, description="sent|failed"),
):
    """List all recipients of the winner send with their send status."""
    try:
        col = get_ab_test_results_collection()
        query = {"test_id": test_id, "is_winner_send": True}
        if status:
            query["email_sent"] = status == "sent"

        total = await col.count_documents(query)
        rows = []
        async for doc in (
            col.find(
                query,
                {
                    "_id": 0,
                    "subscriber_email": 1,
                    "email_sent": 1,
                    "email_opened": 1,
                    "email_clicked": 1,
                    "sent_at": 1,
                    "first_open_at": 1,
                    "first_click_at": 1,
                    "message_id": 1,
                    "error": 1,
                    "skipped_reason": 1,
                },
            )
            .sort("sent_at", -1)
            .skip(skip)
            .limit(limit)
        ):
            rows.append(doc)

        return {"total": total, "skip": skip, "limit": limit, "rows": rows}

    except Exception as e:
        logger.error(f"winner-recipients error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load recipients")


# ── CSV export ────────────────────────────────────────────────────────────────


@router.get("/ab-tests/{test_id}/winner-export")
async def export_winner_report(
    test_id: str,
    event_type: str = Query(
        default="all", description="all|opened|clicked|bounced|recipients"
    ),
):
    """Export winner send data as CSV — mirrors /analytics/campaigns/{id}/export."""
    try:
        cid = _safe_oid(test_id)
        col = get_ab_tests_collection()
        test = await col.find_one({"_id": cid})
        if not test:
            raise HTTPException(status_code=404, detail="A/B test not found")

        test_name = test.get("test_name", "ab_test").replace(" ", "_").lower()
        output = io.StringIO()
        writer = csv.writer(output)

        if event_type == "all":
            # Full summary report
            events_col = get_email_events_collection()
            results_col = get_ab_test_results_collection()

            total_sent = await results_col.count_documents(
                {"test_id": test_id, "is_winner_send": True, "email_sent": True}
            )
            total_failed = await results_col.count_documents(
                {"test_id": test_id, "is_winner_send": True, "email_sent": False}
            )
            total_opened = await events_col.count_documents(
                {"campaign_id": cid, "event_type": "opened", "type": "event"}
            )
            total_clicked = await events_col.count_documents(
                {"campaign_id": cid, "event_type": "clicked", "type": "event"}
            )
            total_bounced = await events_col.count_documents(
                {"campaign_id": cid, "event_type": "bounced", "type": "event"}
            )
            total_unsub = await events_col.count_documents(
                {"campaign_id": cid, "event_type": "unsubscribed", "type": "event"}
            )

            writer.writerow(["A/B Test Winner Send Report"])
            writer.writerow(["Test Name", test.get("test_name", "")])
            writer.writerow(["Winner Variant", test.get("winner_variant", "")])
            writer.writerow(["Subject", test.get("subject", "")])
            writer.writerow(["Sender Email", test.get("sender_email", "")])
            writer.writerow(["Send Status", test.get("winner_send_status", "")])
            writer.writerow(["Started At", str(test.get("winner_send_started_at", ""))])
            writer.writerow(
                ["Completed At", str(test.get("winner_send_completed_at", ""))]
            )
            writer.writerow([])
            writer.writerow(["Metric", "Count", "Rate"])
            writer.writerow(["Total Sent", total_sent, "100%"])
            writer.writerow(
                [
                    "Delivered",
                    max(0, total_sent - total_bounced),
                    f"{round(max(0, total_sent - total_bounced) / total_sent * 100, 1) if total_sent else 0}%",
                ]
            )
            writer.writerow(
                [
                    "Opened",
                    total_opened,
                    f"{round(total_opened / total_sent * 100, 1) if total_sent else 0}%",
                ]
            )
            writer.writerow(
                [
                    "Clicked",
                    total_clicked,
                    f"{round(total_clicked / total_sent * 100, 1) if total_sent else 0}%",
                ]
            )
            writer.writerow(
                [
                    "Bounced",
                    total_bounced,
                    f"{round(total_bounced / total_sent * 100, 1) if total_sent else 0}%",
                ]
            )
            writer.writerow(
                [
                    "Unsubscribed",
                    total_unsub,
                    f"{round(total_unsub / total_sent * 100, 1) if total_sent else 0}%",
                ]
            )
            writer.writerow(["Failed", total_failed, ""])
            filename = f"{test_name}_winner_send_report.csv"

        elif event_type == "recipients":
            writer.writerow(["Winner Send Recipients"])
            writer.writerow(["Test Name", test.get("test_name", "")])
            writer.writerow([])
            writer.writerow(
                [
                    "Email",
                    "Sent",
                    "Opened",
                    "Clicked",
                    "Sent At",
                    "First Open",
                    "First Click",
                    "Message ID",
                    "Error",
                ]
            )
            results_col = get_ab_test_results_collection()
            async for doc in results_col.find(
                {"test_id": test_id, "is_winner_send": True}
            ):
                writer.writerow(
                    [
                        doc.get("subscriber_email", ""),
                        "Yes" if doc.get("email_sent") else "No",
                        "Yes" if doc.get("email_opened") else "No",
                        "Yes" if doc.get("email_clicked") else "No",
                        str(doc.get("sent_at", "")),
                        str(doc.get("first_open_at", "")),
                        str(doc.get("first_click_at", "")),
                        doc.get("message_id", ""),
                        doc.get("error", "") or doc.get("skipped_reason", ""),
                    ]
                )
            filename = f"{test_name}_winner_recipients.csv"

        else:
            # Event-specific export (opened, clicked, bounced, unsubscribed)
            label_map = {
                "opened": "Opens",
                "clicked": "Clicks",
                "bounced": "Bounces",
                "unsubscribed": "Unsubscribes",
            }
            label = label_map.get(event_type, event_type.capitalize())
            writer.writerow([f"Winner Send {label} Report"])
            writer.writerow(["Test Name", test.get("test_name", "")])
            writer.writerow([])
            events_col = get_email_events_collection()
            if event_type == "clicked":
                writer.writerow(["Email", "URL", "Timestamp", "IP", "User Agent"])
                async for doc in events_col.find(
                    {"campaign_id": cid, "event_type": event_type, "type": "event"}
                ).sort("timestamp", -1):
                    writer.writerow(
                        [
                            doc.get("email") or doc.get("subscriber_email", ""),
                            doc.get("url", ""),
                            str(doc.get("timestamp", "")),
                            doc.get("ip_address", ""),
                            doc.get("user_agent", ""),
                        ]
                    )
            else:
                writer.writerow(["Email", "Timestamp", "IP", "User Agent"])
                async for doc in events_col.find(
                    {"campaign_id": cid, "event_type": event_type, "type": "event"}
                ).sort("timestamp", -1):
                    writer.writerow(
                        [
                            doc.get("email") or doc.get("subscriber_email", ""),
                            str(doc.get("timestamp", "")),
                            doc.get("ip_address", ""),
                            doc.get("user_agent", ""),
                        ]
                    )
            filename = f"{test_name}_winner_{event_type}.csv"

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"winner-export error for {test_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Export failed")
