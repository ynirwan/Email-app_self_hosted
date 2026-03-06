# backend/routes/automation_analytics.py
"""
Comprehensive analytics dashboard for automation workflows
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from bson import ObjectId
import logging

from database import (
    get_automation_rules_collection,
    get_automation_steps_collection,
    get_automation_executions_collection,
    get_workflow_instances_collection,
    get_email_events_collection,
    get_subscribers_collection,
    get_events_collection
)

router = APIRouter(prefix="/automation/analytics", tags=["automation-analytics"])
logger = logging.getLogger(__name__)


# ===========================
# OVERVIEW ANALYTICS
# ===========================

@router.get("/overview")
async def get_automation_overview(days: int = 30):
    """
    Get high-level automation overview statistics
    """
    try:
        rules_collection = get_automation_rules_collection()
        workflow_instances_collection = get_workflow_instances_collection()
        executions_collection = get_automation_executions_collection()
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Total automation rules
        total_rules = await rules_collection.count_documents({
            "deleted_at": {"$exists": False}
        })
        
        active_rules = await rules_collection.count_documents({
            "status": "active",
            "deleted_at": {"$exists": False}
        })
        
        # Workflow statistics
        total_workflows = await workflow_instances_collection.count_documents({
            "started_at": {"$gte": start_date}
        })
        
        completed_workflows = await workflow_instances_collection.count_documents({
            "status": "completed",
            "started_at": {"$gte": start_date}
        })
        
        in_progress_workflows = await workflow_instances_collection.count_documents({
            "status": "in_progress",
            "started_at": {"$gte": start_date}
        })
        
        cancelled_workflows = await workflow_instances_collection.count_documents({
            "status": "cancelled",
            "started_at": {"$gte": start_date}
        })
        
        # Email statistics
        total_emails_sent = await executions_collection.count_documents({
            "status": "sent",
            "executed_at": {"$gte": start_date}
        })
        
        failed_emails = await executions_collection.count_documents({
            "status": "failed",
            "executed_at": {"$gte": start_date}
        })
        
        # Calculate completion rate
        completion_rate = (completed_workflows / total_workflows * 100) if total_workflows > 0 else 0
        
        # Calculate failure rate
        failure_rate = (failed_emails / total_emails_sent * 100) if total_emails_sent > 0 else 0
        
        return {
            "period_days": days,
            "automation_rules": {
                "total": total_rules,
                "active": active_rules,
                "inactive": total_rules - active_rules
            },
            "workflows": {
                "total_started": total_workflows,
                "completed": completed_workflows,
                "in_progress": in_progress_workflows,
                "cancelled": cancelled_workflows,
                "completion_rate": round(completion_rate, 2)
            },
            "emails": {
                "total_sent": total_emails_sent,
                "failed": failed_emails,
                "failure_rate": round(failure_rate, 2)
            },
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get automation overview failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================
# RULE PERFORMANCE
# ===========================

@router.get("/rules/performance")
async def get_rules_performance(
    days: int = 30,
    sort_by: str = "emails_sent",
    limit: int = 20
):
    """
    Get performance metrics for all automation rules
    """
    try:
        rules_collection = get_automation_rules_collection()
        workflow_instances_collection = get_workflow_instances_collection()
        executions_collection = get_automation_executions_collection()
        email_events_collection = get_email_events_collection()
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Get all rules
        rules = await rules_collection.find({
            "deleted_at": {"$exists": False}
        }).to_list(None)
        
        performance_data = []
        
        for rule in rules:
            rule_id = str(rule["_id"])
            
            # Workflow stats
            total_workflows = await workflow_instances_collection.count_documents({
                "automation_rule_id": rule_id,
                "started_at": {"$gte": start_date}
            })
            
            completed_workflows = await workflow_instances_collection.count_documents({
                "automation_rule_id": rule_id,
                "status": "completed",
                "started_at": {"$gte": start_date}
            })
            
            # Email stats
            emails_sent = await executions_collection.count_documents({
                "automation_rule_id": rule_id,
                "status": "sent",
                "executed_at": {"$gte": start_date}
            })
            
            # Engagement stats
            opens_pipeline = [
                {
                    "$match": {
                        "automation_rule_id": rule_id,
                        "event_type": "opened",
                        "timestamp": {"$gte": start_date}
                    }
                },
                {
                    "$group": {
                        "_id": "$subscriber_id",
                        "count": {"$sum": 1}
                    }
                }
            ]
            
            unique_opens = len(await email_events_collection.aggregate(opens_pipeline).to_list(None))
            
            clicks_pipeline = [
                {
                    "$match": {
                        "automation_rule_id": rule_id,
                        "event_type": "clicked",
                        "timestamp": {"$gte": start_date}
                    }
                },
                {
                    "$group": {
                        "_id": "$subscriber_id",
                        "count": {"$sum": 1}
                    }
                }
            ]
            
            unique_clicks = len(await email_events_collection.aggregate(clicks_pipeline).to_list(None))
            
            # Calculate rates
            open_rate = (unique_opens / emails_sent * 100) if emails_sent > 0 else 0
            click_rate = (unique_clicks / emails_sent * 100) if emails_sent > 0 else 0
            completion_rate = (completed_workflows / total_workflows * 100) if total_workflows > 0 else 0
            
            # Revenue tracking (if available)
            revenue_pipeline = [
                {
                    "$match": {
                        "automation_rule_id": rule_id,
                        "event_type": "purchase",
                        "timestamp": {"$gte": start_date}
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "total_revenue": {"$sum": "$order_value"},
                        "order_count": {"$sum": 1}
                    }
                }
            ]
            
            revenue_data = await email_events_collection.aggregate(revenue_pipeline).to_list(1)
            total_revenue = revenue_data[0]["total_revenue"] if revenue_data else 0
            order_count = revenue_data[0]["order_count"] if revenue_data else 0
            
            performance_data.append({
                "rule_id": rule_id,
                "rule_name": rule["name"],
                "trigger": rule["trigger"],
                "status": rule.get("status", "draft"),
                "workflows_started": total_workflows,
                "workflows_completed": completed_workflows,
                "completion_rate": round(completion_rate, 2),
                "emails_sent": emails_sent,
                "unique_opens": unique_opens,
                "unique_clicks": unique_clicks,
                "open_rate": round(open_rate, 2),
                "click_rate": round(click_rate, 2),
                "revenue": round(total_revenue, 2),
                "orders": order_count,
                "revenue_per_email": round(total_revenue / emails_sent, 2) if emails_sent > 0 else 0
            })
        
        # Sort by specified metric
        valid_sort_fields = [
            "emails_sent", "open_rate", "click_rate", 
            "completion_rate", "revenue", "workflows_started"
        ]
        
        if sort_by in valid_sort_fields:
            performance_data.sort(key=lambda x: x[sort_by], reverse=True)
        
        return {
            "period_days": days,
            "total_rules": len(performance_data),
            "rules": performance_data[:limit],
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get rules performance failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================
# INDIVIDUAL RULE ANALYTICS
# ===========================

@router.get("/rules/{rule_id}/detailed")
async def get_rule_detailed_analytics(
    rule_id: str,
    days: int = 30
):
    """
    Get detailed analytics for a specific automation rule
    """
    try:
        if not ObjectId.is_valid(rule_id):
            raise HTTPException(status_code=400, detail="Invalid rule ID")
        
        rules_collection = get_automation_rules_collection()
        workflow_instances_collection = get_workflow_instances_collection()
        executions_collection = get_automation_executions_collection()
        email_events_collection = get_email_events_collection()
        
        # Get rule details
        rule = await rules_collection.find_one({"_id": ObjectId(rule_id)})
        if not rule:
            raise HTTPException(status_code=404, detail="Automation rule not found")
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Workflow progression
        workflow_pipeline = [
            {
                "$match": {
                    "automation_rule_id": rule_id,
                    "started_at": {"$gte": start_date}
                }
            },
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1},
                    "avg_completion_time": {
                        "$avg": {
                            "$subtract": [
                                {"$ifNull": ["$completed_at", datetime.utcnow()]},
                                "$started_at"
                            ]
                        }
                    }
                }
            }
        ]
        
        workflow_stats = await workflow_instances_collection.aggregate(workflow_pipeline).to_list(None)
        
        # Email step performance
        step_pipeline = [
            {
                "$match": {
                    "automation_rule_id": rule_id,
                    "executed_at": {"$gte": start_date}
                }
            },
            {
                "$group": {
                    "_id": "$automation_step_id",
                    "emails_sent": {
                        "$sum": {"$cond": [{"$eq": ["$status", "sent"]}, 1, 0]}
                    },
                    "emails_failed": {
                        "$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}
                    }
                }
            }
        ]
        
        step_stats = await executions_collection.aggregate(step_pipeline).to_list(None)
        
        # Engagement over time (daily)
        daily_pipeline = [
            {
                "$match": {
                    "automation_rule_id": rule_id,
                    "timestamp": {"$gte": start_date}
                }
            },
            {
                "$group": {
                    "_id": {
                        "date": {
                            "$dateToString": {
                                "format": "%Y-%m-%d",
                                "date": "$timestamp"
                            }
                        },
                        "event_type": "$event_type"
                    },
                    "count": {"$sum": 1}
                }
            },
            {
                "$sort": {"_id.date": 1}
            }
        ]
        
        daily_engagement = await email_events_collection.aggregate(daily_pipeline).to_list(None)
        
        # Format daily data
        daily_data = {}
        for item in daily_engagement:
            date = item["_id"]["date"]
            event_type = item["_id"]["event_type"]
            
            if date not in daily_data:
                daily_data[date] = {"date": date, "sent": 0, "opened": 0, "clicked": 0}
            
            if event_type == "sent":
                daily_data[date]["sent"] = item["count"]
            elif event_type == "opened":
                daily_data[date]["opened"] = item["count"]
            elif event_type == "clicked":
                daily_data[date]["clicked"] = item["count"]
        
        # Subscriber journey analysis
        journey_pipeline = [
            {
                "$match": {
                    "automation_rule_id": rule_id,
                    "started_at": {"$gte": start_date}
                }
            },
            {
                "$group": {
                    "_id": "$completed_steps",
                    "count": {"$sum": 1}
                }
            },
            {
                "$sort": {"_id": 1}
            }
        ]
        
        journey_data = await workflow_instances_collection.aggregate(journey_pipeline).to_list(None)
        
        # Exit points (where subscribers drop off)
        exit_pipeline = [
            {
                "$match": {
                    "automation_rule_id": rule_id,
                    "status": {"$in": ["cancelled", "failed"]},
                    "started_at": {"$gte": start_date}
                }
            },
            {
                "$group": {
                    "_id": "$completed_steps",
                    "exit_count": {"$sum": 1},
                    "exit_reasons": {
                        "$push": "$status"
                    }
                }
            },
            {
                "$sort": {"_id": 1}
            }
        ]
        
        exit_data = await workflow_instances_collection.aggregate(exit_pipeline).to_list(None)
        
        return {
            "rule_id": rule_id,
            "rule_name": rule["name"],
            "trigger": rule["trigger"],
            "period_days": days,
            "workflow_stats": {
                item["_id"]: {
                    "count": item["count"],
                    "avg_completion_hours": round(item["avg_completion_time"] / 3600000, 2) if item["avg_completion_time"] else 0
                }
                for item in workflow_stats
            },
            "step_performance": [
                {
                    "step_id": item["_id"],
                    "emails_sent": item["emails_sent"],
                    "emails_failed": item["emails_failed"],
                    "success_rate": round(
                        item["emails_sent"] / (item["emails_sent"] + item["emails_failed"]) * 100, 2
                    ) if (item["emails_sent"] + item["emails_failed"]) > 0 else 0
                }
                for item in step_stats
            ],
            "daily_engagement": sorted(daily_data.values(), key=lambda x: x["date"]),
            "subscriber_journey": [
                {
                    "steps_completed": item["_id"],
                    "subscriber_count": item["count"]
                }
                for item in journey_data
            ],
            "exit_points": [
                {
                    "exit_at_step": item["_id"],
                    "exit_count": item["exit_count"]
                }
                for item in exit_data
            ],
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get rule detailed analytics failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================
# TRIGGER TYPE ANALYTICS
# ===========================

@router.get("/triggers/comparison")
async def compare_trigger_performance(days: int = 30):
    """
    Compare performance across different trigger types
    """
    try:
        rules_collection = get_automation_rules_collection()
        workflow_instances_collection = get_workflow_instances_collection()
        executions_collection = get_automation_executions_collection()
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Get all trigger types
        triggers = await rules_collection.distinct("trigger", {
            "status": "active",
            "deleted_at": {"$exists": False}
        })
        
        comparison_data = []
        
        for trigger in triggers:
            # Get rules for this trigger
            trigger_rules = await rules_collection.find({
                "trigger": trigger,
                "status": "active",
                "deleted_at": {"$exists": False}
            }).to_list(None)
            
            rule_ids = [str(r["_id"]) for r in trigger_rules]
            
            # Aggregate stats
            total_workflows = await workflow_instances_collection.count_documents({
                "automation_rule_id": {"$in": rule_ids},
                "started_at": {"$gte": start_date}
            })
            
            completed_workflows = await workflow_instances_collection.count_documents({
                "automation_rule_id": {"$in": rule_ids},
                "status": "completed",
                "started_at": {"$gte": start_date}
            })
            
            emails_sent = await executions_collection.count_documents({
                "automation_rule_id": {"$in": rule_ids},
                "status": "sent",
                "executed_at": {"$gte": start_date}
            })
            
            # Calculate rates
            completion_rate = (completed_workflows / total_workflows * 100) if total_workflows > 0 else 0
            
            comparison_data.append({
                "trigger_type": trigger,
                "rule_count": len(trigger_rules),
                "workflows_started": total_workflows,
                "workflows_completed": completed_workflows,
                "completion_rate": round(completion_rate, 2),
                "emails_sent": emails_sent,
                "avg_emails_per_workflow": round(emails_sent / total_workflows, 2) if total_workflows > 0 else 0
            })
        
        # Sort by workflows started
        comparison_data.sort(key=lambda x: x["workflows_started"], reverse=True)
        
        return {
            "period_days": days,
            "triggers": comparison_data,
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Compare trigger performance failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================
# SUBSCRIBER ENGAGEMENT
# ===========================

@router.get("/engagement/subscribers")
async def get_subscriber_engagement_stats(days: int = 30):
    """
    Get subscriber engagement statistics across all automations
    """
    try:
        workflow_instances_collection = get_workflow_instances_collection()
        email_events_collection = get_email_events_collection()
        subscribers_collection = get_subscribers_collection()
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Subscribers in workflows
        unique_subscribers_pipeline = [
            {
                "$match": {
                    "started_at": {"$gte": start_date}
                }
            },
            {
                "$group": {
                    "_id": "$subscriber_id"
                }
            }
        ]
        
        unique_subscribers = len(
            await workflow_instances_collection.aggregate(unique_subscribers_pipeline).to_list(None)
        )
        
        # Total active subscribers
        total_subscribers = await subscribers_collection.count_documents({
            "status": "active"
        })
        
        # Engagement levels
        engagement_pipeline = [
            {
                "$match": {
                    "timestamp": {"$gte": start_date}
                }
            },
            {
                "$group": {
                    "_id": "$subscriber_id",
                    "opens": {
                        "$sum": {"$cond": [{"$eq": ["$event_type", "opened"]}, 1, 0]}
                    },
                    "clicks": {
                        "$sum": {"$cond": [{"$eq": ["$event_type", "clicked"]}, 1, 0]}
                    }
                }
            }
        ]
        
        engagement_data = await email_events_collection.aggregate(engagement_pipeline).to_list(None)
        
        # Categorize engagement
        highly_engaged = len([s for s in engagement_data if s["opens"] >= 5 or s["clicks"] >= 2])
        moderately_engaged = len([s for s in engagement_data if 1 <= s["opens"] < 5 and s["clicks"] < 2])
        low_engaged = len([s for s in engagement_data if s["opens"] < 1])
        
        return {
            "period_days": days,
            "total_active_subscribers": total_subscribers,
            "subscribers_in_automations": unique_subscribers,
            "automation_reach_percentage": round(
                unique_subscribers / total_subscribers * 100, 2
            ) if total_subscribers > 0 else 0,
            "engagement_levels": {
                "highly_engaged": highly_engaged,
                "moderately_engaged": moderately_engaged,
                "low_engaged": low_engaged,
                "no_engagement": unique_subscribers - len(engagement_data)
            },
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get subscriber engagement stats failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================
# REVENUE ANALYTICS
# ===========================

@router.get("/revenue/attribution")
async def get_revenue_attribution(days: int = 30):
    """
    Get revenue attribution for automation workflows
    """
    try:
        events_collection = get_events_collection()
        workflow_instances_collection = get_workflow_instances_collection()
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Revenue by automation trigger
        revenue_pipeline = [
            {
                "$match": {
                    "event_type": "purchase",
                    "created_at": {"$gte": start_date}
                }
            },
            {
                "$lookup": {
                    "from": "workflow_instances",
                    "localField": "subscriber_id",
                    "foreignField": "subscriber_id",
                    "as": "workflows"
                }
            },
            {
                "$unwind": "$workflows"
            },
            {
                "$lookup": {
                    "from": "automation_rules",
                    "localField": "workflows.automation_rule_id",
                    "foreignField": "_id",
                    "as": "rule"
                }
            },
            {
                "$unwind": "$rule"
            },
            {
                "$group": {
                    "_id": {
                        "trigger": "$rule.trigger",
                        "rule_name": "$rule.name"
                    },
                    "total_revenue": {"$sum": "$order_value"},
                    "order_count": {"$sum": 1},
                    "avg_order_value": {"$avg": "$order_value"}
                }
            },
            {
                "$sort": {"total_revenue": -1}
            }
        ]
        
        revenue_data = await events_collection.aggregate(revenue_pipeline).to_list(None)
        
        # Format response
        attribution = [
            {
                "trigger": item["_id"]["trigger"],
                "rule_name": item["_id"]["rule_name"],
                "total_revenue": round(item["total_revenue"], 2),
                "order_count": item["order_count"],
                "avg_order_value": round(item["avg_order_value"], 2)
            }
            for item in revenue_data
        ]
        
        total_revenue = sum(item["total_revenue"] for item in attribution)
        
        return {
            "period_days": days,
            "total_revenue": round(total_revenue, 2),
            "attribution": attribution,
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get revenue attribution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================
# REAL-TIME STATS
# ===========================

@router.get("/realtime")
async def get_realtime_stats():
    """
    Get real-time automation statistics (last hour)
    """
    try:
        workflow_instances_collection = get_workflow_instances_collection()
        executions_collection = get_automation_executions_collection()
        
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        
        # Workflows started
        workflows_started = await workflow_instances_collection.count_documents({
            "started_at": {"$gte": one_hour_ago}
        })
        
        # Emails sent
        emails_sent = await executions_collection.count_documents({
            "status": "sent",
            "executed_at": {"$gte": one_hour_ago}
        })
        
        # Scheduled emails
        scheduled_emails = await executions_collection.count_documents({
            "status": "scheduled",
            "scheduled_for": {"$lte": datetime.utcnow() + timedelta(hours=1)}
        })
        
        # Active workflows
        active_workflows = await workflow_instances_collection.count_documents({
            "status": "in_progress"
        })
        
        return {
            "last_hour": {
                "workflows_started": workflows_started,
                "emails_sent": emails_sent
            },
            "next_hour": {
                "emails_scheduled": scheduled_emails
            },
            "current": {
                "active_workflows": active_workflows
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get realtime stats failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================
# EXPORT ANALYTICS
# ===========================

@router.get("/export/csv")
async def export_analytics_csv(
    rule_id: Optional[str] = None,
    days: int = 30
):
    """
    Export analytics data as CSV
    """
    try:
        from fastapi.responses import StreamingResponse
        import csv
        from io import StringIO
        
        # Get performance data
        if rule_id:
            # Single rule export
            data = await get_rule_detailed_analytics(rule_id, days)
            # Format for CSV
            # TODO: Implement CSV formatting
        else:
            # All rules export
            data = await get_rules_performance(days, "emails_sent", 1000)
        
        # Create CSV
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=data["rules"][0].keys())
        writer.writeheader()
        writer.writerows(data["rules"])
        
        # Return as downloadable file
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=automation_analytics_{datetime.utcnow().strftime('%Y%m%d')}.csv"
            }
        )
        
    except Exception as e:
        logger.error(f"Export analytics CSV failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
