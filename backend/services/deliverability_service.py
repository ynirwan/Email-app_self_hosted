# backend/services/deliverability_service.py
"""
Deliverability health service.

Aggregates bounce, complaint, and unsubscribe data from email_logs and
events collections alongside domain verification status to produce a
composite deliverability health score and actionable recommendations.

Score breakdown (0–100):
  - Bounce rate      40 pts  (< 2% = full; 2–5% = partial; > 5% = 0)
  - Complaint rate   35 pts  (< 0.08% = full; 0.08–0.1% = partial; > 0.1% = 0)
  - Unsubscribe rate 15 pts  (< 0.5% = full; 0.5–1% = partial; > 1% = 0)
  - Domain health    10 pts  (all verified = full; some = partial; none = 0)

Industry reference thresholds:
  - Google / Yahoo 2024 bulk-sender requirements:
      bounce < 2%, spam complaint < 0.1% (hard limit 0.08% recommended)
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from database import (
    get_analytics_collection,
    get_domains_collection,
    get_email_logs_collection,
)

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────

BOUNCE_HEALTHY    = 2.0    # %
BOUNCE_WARNING    = 5.0    # %

COMPLAINT_HEALTHY = 0.08   # %  (Google/Yahoo recommended ceiling)
COMPLAINT_WARNING = 0.10   # %  (hard limit)

UNSUB_HEALTHY     = 0.5    # %
UNSUB_WARNING     = 1.0    # %

# ── Score weights (must sum to 100) ──────────────────────────────────────────

W_BOUNCE    = 40
W_COMPLAINT = 35
W_UNSUB     = 15
W_DOMAIN    = 10


# ── Internal helpers ─────────────────────────────────────────────────────────

def _rate_score(rate: float, healthy: float, warning: float, weight: int) -> tuple[int, str]:
    """
    Return (points_earned, status) for a single rate metric.

    status is one of: "healthy" | "warning" | "critical"
    """
    if rate <= healthy:
        return weight, "healthy"
    if rate <= warning:
        # Linear interpolation between healthy and warning boundaries
        fraction = 1.0 - (rate - healthy) / max(warning - healthy, 0.001)
        pts = round(weight * fraction * 0.5)   # partial — never full at warning
        return pts, "warning"
    return 0, "critical"


def _score_label(score: int) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Fair"
    if score >= 25:
        return "Poor"
    return "Critical"


# ── Core aggregation ─────────────────────────────────────────────────────────

async def _fetch_rate_metrics(days: int = 30) -> dict[str, Any]:
    """
    Aggregate sent / bounced / complained / unsubscribed counts from
    the analytics collection (campaign-level summaries) for the last N days.

    Falls back to email_logs direct scan if analytics collection is sparse.
    """
    analytics_col = get_analytics_collection()
    since = datetime.utcnow() - timedelta(days=days)

    pipeline = [
        {"$match": {"updated_at": {"$gte": since}}},
        {
            "$group": {
                "_id": None,
                "total_sent":          {"$sum": "$total_sent"},
                "total_bounced":       {"$sum": "$total_bounced"},
                "total_complaints":    {"$sum": "$total_spam_reports"},
                "total_unsubscribed":  {"$sum": "$total_unsubscribed"},
                "total_delivered":     {"$sum": "$total_delivered"},
            }
        },
    ]

    result = await analytics_col.aggregate(pipeline).to_list(length=1)

    if result and result[0].get("total_sent", 0) > 0:
        row = result[0]
        sent       = max(row["total_sent"], 1)
        bounced    = row.get("total_bounced", 0)
        complaints = row.get("total_complaints", 0)
        unsubs     = row.get("total_unsubscribed", 0)
        delivered  = row.get("total_delivered", 0)
    else:
        # Fallback: scan email_logs directly
        logs_col = get_email_logs_collection()
        fallback_pipeline = [
            {"$match": {"created_at": {"$gte": since}}},
            {
                "$group": {
                    "_id": None,
                    "total_sent": {"$sum": 1},
                    "total_bounced": {
                        "$sum": {
                            "$cond": [
                                {"$in": ["$latest_status", ["bounce", "bounced"]]},
                                1, 0
                            ]
                        }
                    },
                    "total_complaints": {
                        "$sum": {
                            "$cond": [
                                {"$in": ["$latest_status", ["complaint", "complained"]]},
                                1, 0
                            ]
                        }
                    },
                }
            },
        ]
        fb = await logs_col.aggregate(fallback_pipeline).to_list(length=1)
        if fb:
            sent       = max(fb[0].get("total_sent", 1), 1)
            bounced    = fb[0].get("total_bounced", 0)
            complaints = fb[0].get("total_complaints", 0)
        else:
            sent = bounced = complaints = 0
        unsubs    = 0
        delivered = max(sent - bounced, 0)

    bounce_rate    = round(bounced    / sent * 100, 3) if sent else 0.0
    complaint_rate = round(complaints / sent * 100, 3) if sent else 0.0
    unsub_rate     = round(unsubs     / sent * 100, 3) if sent else 0.0
    delivery_rate  = round(delivered  / sent * 100, 1) if sent else 0.0

    return {
        "total_sent":         sent,
        "total_delivered":    delivered,
        "total_bounced":      bounced,
        "total_complaints":   complaints,
        "total_unsubscribed": unsubs,
        "bounce_rate":        bounce_rate,
        "complaint_rate":     complaint_rate,
        "unsubscribe_rate":   unsub_rate,
        "delivery_rate":      delivery_rate,
    }


async def _fetch_daily_trend(days: int = 30) -> dict[str, list[dict]]:
    """
    Build per-day time series for bounce rate and complaint rate.
    Uses analytics collection, bucketed by updated_at day.

    Returns dict with keys: bounce_trend, complaint_trend
    """
    analytics_col = get_analytics_collection()
    since = datetime.utcnow() - timedelta(days=days)

    pipeline = [
        {"$match": {"updated_at": {"$gte": since}, "total_sent": {"$gt": 0}}},
        {
            "$group": {
                "_id": {
                    "$dateToString": {"format": "%Y-%m-%d", "date": "$updated_at"}
                },
                "sent":       {"$sum": "$total_sent"},
                "bounced":    {"$sum": "$total_bounced"},
                "complaints": {"$sum": "$total_spam_reports"},
            }
        },
        {"$sort": {"_id": 1}},
    ]

    rows = await analytics_col.aggregate(pipeline).to_list(length=60)

    bounce_by_date:    dict[str, float] = {}
    complaint_by_date: dict[str, float] = {}

    for row in rows:
        day  = row["_id"]
        sent = max(row.get("sent", 0), 1)
        bounce_by_date[day]    = round(row.get("bounced", 0)    / sent * 100, 3)
        complaint_by_date[day] = round(row.get("complaints", 0) / sent * 100, 3)

    today = datetime.utcnow().date()
    bounce_trend:    list[dict] = []
    complaint_trend: list[dict] = []

    for i in range(days - 1, -1, -1):
        day   = today - timedelta(days=i)
        key   = str(day)
        label = day.strftime("%b %d")
        bounce_trend.append(   {"date": label, "value": bounce_by_date.get(key, 0)})
        complaint_trend.append({"date": label, "value": complaint_by_date.get(key, 0)})

    return {
        "bounce_trend":    bounce_trend,
        "complaint_trend": complaint_trend,
    }


async def _fetch_domain_health() -> dict[str, Any]:
    """
    Return verification status for all registered domains and an
    aggregate domain health score component (0–W_DOMAIN).
    """
    domains_col = get_domains_collection()
    all_domains = await domains_col.find(
        {},
        {"domain": 1, "status": 1, "verified_at": 1, "verification_results": 1, "created_at": 1}
    ).to_list(length=100)

    total    = len(all_domains)
    verified = sum(1 for d in all_domains if d.get("status") == "verified")
    pending  = sum(1 for d in all_domains if d.get("status") == "pending")
    failed   = sum(1 for d in all_domains if d.get("status") == "failed")

    domain_list = []
    for d in all_domains:
        vr = d.get("verification_results") or {}
        domain_list.append({
            "domain":      d["domain"],
            "status":      d.get("status", "pending"),
            "verified_at": d["verified_at"].isoformat() if d.get("verified_at") else None,
            "checks": {
                "spf":   vr.get("spf",   False),
                "dkim":  vr.get("dkim",  False),
                "dmarc": vr.get("dmarc", False),
                "token": vr.get("verification_token", False),
            },
        })

    # Score: full points if all verified, partial if some, zero if none
    if total == 0:
        domain_pts    = 0
        domain_status = "warning"   # no domains configured is a concern
    elif verified == total:
        domain_pts    = W_DOMAIN
        domain_status = "healthy"
    elif verified > 0:
        domain_pts    = round(W_DOMAIN * (verified / total) * 0.7)
        domain_status = "warning"
    else:
        domain_pts    = 0
        domain_status = "critical"

    return {
        "domain_pts":    domain_pts,
        "domain_status": domain_status,
        "summary": {
            "total":    total,
            "verified": verified,
            "pending":  pending,
            "failed":   failed,
        },
        "domains": domain_list,
    }


def _build_recommendations(
    bounce_status:    str,
    complaint_status: str,
    unsub_status:     str,
    domain_status:    str,
    metrics:          dict,
    domain_health:    dict,
) -> list[dict]:
    """
    Produce actionable, prioritised recommendations based on current health.
    Each recommendation has: severity, title, description, action.
    """
    recs: list[dict] = []

    if bounce_status == "critical":
        recs.append({
            "severity":    "critical",
            "title":       "Bounce rate exceeds safe threshold",
            "description": (
                f"Your bounce rate is {metrics['bounce_rate']}% — above the 5% critical threshold. "
                "Major ISPs will throttle or block your sending domain."
            ),
            "action": "Clean your contact list immediately and remove all hard-bounced addresses.",
        })
    elif bounce_status == "warning":
        recs.append({
            "severity":    "warning",
            "title":       "Bounce rate approaching danger zone",
            "description": (
                f"Your bounce rate is {metrics['bounce_rate']}% (warning threshold: 2%). "
                "Proactive list hygiene is recommended."
            ),
            "action": "Review recent campaigns for high-bounce lists and run a re-engagement check.",
        })

    if complaint_status == "critical":
        recs.append({
            "severity":    "critical",
            "title":       "Spam complaint rate is above Google/Yahoo limit",
            "description": (
                f"Complaint rate {metrics['complaint_rate']}% exceeds the 0.1% hard limit set by "
                "Google and Yahoo for bulk senders (Feb 2024 requirements)."
            ),
            "action": "Pause campaigns immediately. Review content, sender name, and opt-in quality.",
        })
    elif complaint_status == "warning":
        recs.append({
            "severity":    "warning",
            "title":       "Spam complaint rate near Google/Yahoo threshold",
            "description": (
                f"Complaint rate {metrics['complaint_rate']}% is approaching the 0.1% hard limit. "
                "Google recommends staying below 0.08%."
            ),
            "action": "Audit recent campaign content. Ensure unsubscribe links are prominent.",
        })

    if unsub_status in ("warning", "critical"):
        recs.append({
            "severity":    unsub_status,
            "title":       "Elevated unsubscribe rate",
            "description": (
                f"Unsubscribe rate of {metrics['unsubscribe_rate']}% suggests audience mismatch or "
                "excessive send frequency."
            ),
            "action": "Review send cadence and segment targeting. Consider preference centre.",
        })

    if domain_status == "critical":
        recs.append({
            "severity":    "critical",
            "title":       "No sending domains verified",
            "description": "Without SPF/DKIM/DMARC verification, emails are likely to be rejected or land in spam.",
            "action":      "Verify at least one domain in Settings → Domain Settings.",
        })
    elif domain_status == "warning":
        failed_domains = [d["domain"] for d in domain_health["domains"] if d["status"] != "verified"]
        recs.append({
            "severity":    "warning",
            "title":       "Some sending domains are unverified",
            "description": f"Unverified: {', '.join(failed_domains) or 'check domain settings'}.",
            "action":      "Complete DNS verification for all sending domains.",
        })

    if not recs:
        recs.append({
            "severity":    "info",
            "title":       "Deliverability looks healthy",
            "description": "All key metrics are within safe thresholds.",
            "action":      "Keep monitoring. Schedule regular list hygiene reviews.",
        })

    return recs


# ── Public API ────────────────────────────────────────────────────────────────

async def get_deliverability_health(days: int = 30) -> dict[str, Any]:
    """
    Compute and return the full deliverability health payload.

    This is the single source of truth consumed by the dashboard route.
    Raises on hard database errors — caller is responsible for HTTP mapping.
    """
    import asyncio
    metrics, trends, domain_health = await asyncio.gather(
        _fetch_rate_metrics(days),
        _fetch_daily_trend(days),
        _fetch_domain_health(),
    )

    # Score each dimension
    bounce_pts,    bounce_status    = _rate_score(metrics["bounce_rate"],      BOUNCE_HEALTHY,    BOUNCE_WARNING,    W_BOUNCE)
    complaint_pts, complaint_status = _rate_score(metrics["complaint_rate"],   COMPLAINT_HEALTHY, COMPLAINT_WARNING, W_COMPLAINT)
    unsub_pts,     unsub_status     = _rate_score(metrics["unsubscribe_rate"], UNSUB_HEALTHY,     UNSUB_WARNING,     W_UNSUB)
    domain_pts    = domain_health["domain_pts"]
    domain_status = domain_health["domain_status"]

    total_score = bounce_pts + complaint_pts + unsub_pts + domain_pts

    # Overall status derived from worst individual status (not averaged score)
    status_priority = {"critical": 0, "warning": 1, "healthy": 2, "info": 3}
    statuses = [bounce_status, complaint_status, unsub_status, domain_status]
    overall_status = min(statuses, key=lambda s: status_priority.get(s, 2))

    recommendations = _build_recommendations(
        bounce_status, complaint_status, unsub_status, domain_status,
        metrics, domain_health,
    )

    return {
        "generated_at": datetime.utcnow().isoformat(),
        "period_days":  days,
        "score": {
            "total":          total_score,
            "max":            100,
            "label":          _score_label(total_score),
            "overall_status": overall_status,
            "breakdown": {
                "bounce":    {"pts": bounce_pts,    "max": W_BOUNCE,    "status": bounce_status},
                "complaint": {"pts": complaint_pts, "max": W_COMPLAINT, "status": complaint_status},
                "unsub":     {"pts": unsub_pts,     "max": W_UNSUB,     "status": unsub_status},
                "domain":    {"pts": domain_pts,    "max": W_DOMAIN,    "status": domain_status},
            },
        },
        "metrics": {
            **metrics,
            "thresholds": {
                "bounce":    {"healthy": BOUNCE_HEALTHY,    "warning": BOUNCE_WARNING},
                "complaint": {"healthy": COMPLAINT_HEALTHY, "warning": COMPLAINT_WARNING},
                "unsub":     {"healthy": UNSUB_HEALTHY,     "warning": UNSUB_WARNING},
            },
        },
        "trends":          trends,
        "domain_health":   domain_health,
        "recommendations": recommendations,
    }
