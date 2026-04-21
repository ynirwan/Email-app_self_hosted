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

    Counting strategy (mirrors campaign analytics):
    - total_sent    = distinct subscribers with email_sent=True (NOT count of all rows)
    - total_failed  = distinct subscribers that NEVER succeeded (email_sent=False AND
                      no matching email_sent=True row for same subscriber)
    - total_delivered = total_sent - total_bounced
    - Opens/clicks come from email_events collection (campaign_id = test ObjectId)

    This correctly handles retries: a subscriber with 2 failed rows + 1 success row
    counts as 1 sent, 0 failed — matching how campaigns work via email_logs latest_status.
    """
    try:
        cid = _safe_oid(test_id)

        col = get_ab_tests_collection()
        test = await col.find_one({"_id": cid})
        if not test:
            raise HTTPException(status_code=404, detail="A/B test not found")

        results_col = get_ab_test_results_collection()
        events_col = get_email_events_collection()

        # ── Deduplicated sent/failed counts ──────────────────────────────────────
        # Get all distinct subscribers that succeeded (email_sent=True)
        sent_pipeline = [
            {"$match": {"test_id": test_id, "is_winner_send": True, "email_sent": True}},
            {"$group": {"_id": "$subscriber_id"}},
            {"$count": "n"},
        ]
        sent_result = []
        async for r in results_col.aggregate(sent_pipeline):
            sent_result.append(r)
        total_sent = sent_result[0]["n"] if sent_result else 0

        # Get distinct subscribers that only ever failed (no success row exists)
        # Step 1: all subscribers with at least one failure
        failed_any_pipeline = [
            {"$match": {"test_id": test_id, "is_winner_send": True, "email_sent": False}},
            {"$group": {"_id": "$subscriber_id"}},
        ]
        failed_subscriber_ids = set()
        async for r in results_col.aggregate(failed_any_pipeline):
            failed_subscriber_ids.add(r["_id"])

        # Step 2: remove those who eventually succeeded
        succeeded_pipeline = [
            {"$match": {"test_id": test_id, "is_winner_send": True, "email_sent": True}},
            {"$group": {"_id": "$subscriber_id"}},
        ]
        succeeded_ids = set()
        async for r in results_col.aggregate(succeeded_pipeline):
            succeeded_ids.add(r["_id"])

        # Only-failed = failed but never succeeded
        total_failed = len(failed_subscriber_ids - succeeded_ids)

        # ── Event counts from email_events ────────────────────────────────────────
        total_opened = await events_col.count_documents(
            {"campaign_id": cid, "event_type": "opened", "type": "event"}
        )
        total_clicked = await events_col.count_documents(
            {"campaign_id": cid, "event_type": "clicked", "type": "event"}
        )
        total_bounced = await events_col.count_documents(
            {"campaign_id": cid, "event_type": "bounced", "type": "event"}
        )
        total_unsubscribed = await events_col.count_documents(
            {"campaign_id": cid, "event_type": "unsubscribed", "type": "event"}
        )
        total_spam = await events_col.count_documents(
            {"campaign_id": cid, "event_type": "spam_report", "type": "event"}
        )

        # Delivered = sent - bounced (same formula as campaign analytics)
        total_delivered = max(0, total_sent - total_bounced)

        def rate(n, d):
            return round(n / d * 100, 1) if d else 0

        # ── Winner send status (normalise edge cases) ─────────────────────────────
        ws_status = test.get("winner_send_status")
        ws_started = test.get("winner_send_started_at")
        ws_completed = test.get("winner_send_completed_at")

        # If test is completed but winner send was never separately initiated
        # (e.g. no auto-send), show "not_sent" rather than confusing blanks.
        if test.get("status") == "completed" and not ws_status and not ws_started:
            ws_status = "not_sent"

        return {
            "test_id": test_id,
            "test_name": test.get("test_name", ""),
            "subject": test.get("subject", ""),
            "sender_name": test.get("sender_name", ""),
            "sender_email": test.get("sender_email", ""),
            "reply_to": test.get("reply_to", ""),
            "target_lists": test.get("target_lists", []),
            "target_segments": test.get("target_segments", []),
            "winner_variant": test.get("winner_variant"),
            "winner_improvement": test.get("winner_improvement"),
            "winner_criteria": test.get("winner_criteria", "open_rate"),
            "winner_send_status": ws_status,
            "winner_send_started_at": ws_started,
            "winner_send_completed_at": ws_completed,
            "created_at": test.get("created_at"),
            "start_date": test.get("start_date"),
            "end_date": test.get("end_date"),
            "sample_size": test.get("sample_size"),
            "total_target_subscribers": test.get("total_target_subscribers"),
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


# ── Unified metric detail ──────────────────────────────────────────────────────


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


# ── Recipients list ────────────────────────────────────────────────────────────


@router.get("/ab-tests/{test_id}/winner-recipients")
async def get_winner_recipients(
    test_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None, description="sent|failed"),
):
    """
    List winner send recipients, deduplicated by subscriber.
    For each subscriber, shows the BEST outcome (sent > failed).
    This mirrors how campaign email_logs works (latest_status).
    """
    try:
        col = get_ab_test_results_collection()

        # Aggregate per subscriber: best outcome wins
        # email_sent=True trumps any email_sent=False rows for same subscriber
        pipeline = [
            {"$match": {"test_id": test_id, "is_winner_send": True}},
            {"$sort": {"email_sent": -1, "sent_at": -1}},  # True first, latest first
            {
                "$group": {
                    "_id": "$subscriber_id",
                    "subscriber_email": {"$first": "$subscriber_email"},
                    "email_sent": {"$max": "$email_sent"},  # True wins over False
                    "email_opened": {"$max": "$email_opened"},
                    "email_clicked": {"$max": "$email_clicked"},
                    "sent_at": {"$max": "$sent_at"},
                    "first_open_at": {"$max": "$first_open_at"},
                    "first_click_at": {"$max": "$first_click_at"},
                    "message_id": {
                        "$max": "$message_id"
                    },  # non-null wins over null
                    "error": {
                        "$min": "$error"
                    },  # null wins over error string (null < string)
                    "attempt_count": {"$sum": 1},
                }
            },
        ]

        # Apply status filter
        if status == "sent":
            pipeline.append({"$match": {"email_sent": True}})
        elif status == "failed":
            pipeline.append({"$match": {"email_sent": False}})

        pipeline.extend([
            {"$sort": {"sent_at": -1}},
            {"$facet": {
                "total": [{"$count": "n"}],
                "rows": [{"$skip": skip}, {"$limit": limit}],
            }},
        ])

        result = []
        async for r in col.aggregate(pipeline):
            result.append(r)

        data = result[0] if result else {"total": [], "rows": []}
        total = data["total"][0]["n"] if data["total"] else 0
        rows = data["rows"]

        # Clean up _id field
        for row in rows:
            row["subscriber_id"] = row.pop("_id", None)

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
            events_col = get_email_events_collection()
            results_col = get_ab_test_results_collection()

            # Deduplicated counts
            sent_pipeline = [
                {"$match": {"test_id": test_id, "is_winner_send": True, "email_sent": True}},
                {"$group": {"_id": "$subscriber_id"}},
                {"$count": "n"},
            ]
            sr = []
            async for r in results_col.aggregate(sent_pipeline):
                sr.append(r)
            total_sent = sr[0]["n"] if sr else 0

            failed_any = set()
            async for r in results_col.aggregate([
                {"$match": {"test_id": test_id, "is_winner_send": True, "email_sent": False}},
                {"$group": {"_id": "$subscriber_id"}},
            ]):
                failed_any.add(r["_id"])
            succeeded = set()
            async for r in results_col.aggregate([
                {"$match": {"test_id": test_id, "is_winner_send": True, "email_sent": True}},
                {"$group": {"_id": "$subscriber_id"}},
            ]):
                succeeded.add(r["_id"])
            total_failed = len(failed_any - succeeded)

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
            total_delivered = max(0, total_sent - total_bounced)

            writer.writerow(["A/B Test Winner Send Report"])
            writer.writerow(["Test Name", test.get("test_name", "")])
            writer.writerow(["Winner Variant", test.get("winner_variant", "")])
            writer.writerow(["Subject", test.get("subject", "")])
            writer.writerow(["Sender Email", test.get("sender_email", "")])
            writer.writerow(["Send Status", test.get("winner_send_status", "")])
            writer.writerow(["Started At", str(test.get("winner_send_started_at", ""))])
            writer.writerow(["Completed At", str(test.get("winner_send_completed_at", ""))])
            writer.writerow([])
            writer.writerow(["Metric", "Count", "Rate"])
            writer.writerow(["Total Sent", total_sent, "100%"])
            writer.writerow(["Failed (never delivered)", total_failed, f"{round(total_failed / (total_sent + total_failed) * 100, 1) if (total_sent + total_failed) else 0}%"])
            writer.writerow(["Delivered", total_delivered, f"{round(total_delivered / total_sent * 100, 1) if total_sent else 0}%"])
            writer.writerow(["Opened", total_opened, f"{round(total_opened / total_sent * 100, 1) if total_sent else 0}%"])
            writer.writerow(["Clicked", total_clicked, f"{round(total_clicked / total_sent * 100, 1) if total_sent else 0}%"])
            writer.writerow(["Bounced", total_bounced, f"{round(total_bounced / total_sent * 100, 1) if total_sent else 0}%"])
            writer.writerow(["Unsubscribed", total_unsub, f"{round(total_unsub / total_sent * 100, 1) if total_sent else 0}%"])
            filename = f"{test_name}_winner_send_report.csv"

        elif event_type == "recipients":
            writer.writerow(["Winner Send Recipients (deduplicated by subscriber)"])
            writer.writerow(["Test Name", test.get("test_name", "")])
            writer.writerow([])
            writer.writerow(["Email", "Final Status", "Opened", "Clicked", "Last Sent At", "Attempts", "Error"])
            results_col = get_ab_test_results_collection()
            # Deduplicated per subscriber
            async for doc in results_col.aggregate([
                {"$match": {"test_id": test_id, "is_winner_send": True}},
                {
                    "$group": {
                        "_id": "$subscriber_id",
                        "subscriber_email": {"$first": "$subscriber_email"},
                        "email_sent": {"$max": "$email_sent"},
                        "email_opened": {"$max": "$email_opened"},
                        "email_clicked": {"$max": "$email_clicked"},
                        "sent_at": {"$max": "$sent_at"},
                        "error": {"$min": "$error"},
                        "attempt_count": {"$sum": 1},
                    }
                },
                {"$sort": {"sent_at": -1}},
            ]):
                writer.writerow([
                    doc.get("subscriber_email", ""),
                    "Sent" if doc.get("email_sent") else "Failed",
                    "Yes" if doc.get("email_opened") else "No",
                    "Yes" if doc.get("email_clicked") else "No",
                    str(doc.get("sent_at", "")),
                    doc.get("attempt_count", 1),
                    doc.get("error", "") or "",
                ])
            filename = f"{test_name}_winner_recipients.csv"

        else:
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
                    writer.writerow([
                        doc.get("email") or doc.get("subscriber_email", ""),
                        doc.get("url", ""),
                        str(doc.get("timestamp", "")),
                        doc.get("ip_address", ""),
                        doc.get("user_agent", ""),
                    ])
            else:
                writer.writerow(["Email", "Timestamp", "IP", "User Agent"])
                async for doc in events_col.find(
                    {"campaign_id": cid, "event_type": event_type, "type": "event"}
                ).sort("timestamp", -1):
                    writer.writerow([
                        doc.get("email") or doc.get("subscriber_email", ""),
                        str(doc.get("timestamp", "")),
                        doc.get("ip_address", ""),
                        doc.get("user_agent", ""),
                    ])
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