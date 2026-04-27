# backend/routes/ab_testing.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum
from bson import ObjectId
import logging
from tasks.campaign.snapshot_utils import build_snapshot
from database import (
    get_subscribers_collection,
    get_ab_tests_collection,
    get_ab_test_results_collection,
    get_templates_collection,
    get_sync_ab_tests_collection,
    get_sync_ab_test_results_collection,
)
from tasks.ab.ab_testing import send_ab_test_batch


logger = logging.getLogger(__name__)
router = APIRouter()

# ============================================================
# ENUMS
# ============================================================


class TestType(str, Enum):
    SUBJECT_LINE = "subject_line"
    SENDER_NAME = "sender_name"
    SENDER_EMAIL = "sender_email"
    REPLY_TO = "reply_to"


class TestStatus(str, Enum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    STOPPED = "stopped"
    PAUSED = "paused"
    FAILED = "failed"


# ============================================================
# PYDANTIC MODELS
# ============================================================


class ABTestVariant(BaseModel):
    name: str
    subject: Optional[str] = None
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    reply_to: Optional[str] = None


class ABTestCreate(BaseModel):
    test_name: str
    target_lists: List[str]
    target_segments: Optional[List[str]] = Field(default_factory=list)
    template_id: str
    subject: str
    sender_name: str
    sender_email: str
    reply_to: Optional[str] = None
    test_type: TestType
    variants: List[ABTestVariant]
    split_percentage: int = 50
    sample_size: int = 1000
    winner_criteria: str = "open_rate"
    test_duration_hours: Optional[int] = Field(
        default=24,
        ge=1,
        le=168,
        description="Hours to run before auto-declaring winner",
    )
    auto_send_winner: bool = Field(
        default=True, description="Auto-send winning variant to remaining subscribers"
    )
    field_map: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Maps template {{variables}} to subscriber data columns",
    )
    fallback_values: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Default values used when mapped field is empty",
    )


class CompleteTestRequest(BaseModel):
    apply_to_campaign: bool = True

def _safe_provider_error(pe):
    """Serialise provider_error for JSON — handles datetime fields."""
    if not pe:
        return None
    out = dict(pe)
    if "detected_at" in out and hasattr(out["detected_at"], "isoformat"):
        out["detected_at"] = out["detected_at"].isoformat()
    return out

    

# ============================================================
# UTILITY: ObjectId → str
# ============================================================


def convert_objectid_to_str(document):
    if isinstance(document, list):
        return [convert_objectid_to_str(item) for item in document]
    elif isinstance(document, dict):
        return {
            k: (
                str(v)
                if isinstance(v, ObjectId)
                else convert_objectid_to_str(v)
                if isinstance(v, (dict, list))
                else v
            )
            for k, v in document.items()
        }
    elif isinstance(document, ObjectId):
        return str(document)
    return document


# ============================================================
# HELPER: subscriber queries
# ============================================================


async def get_ab_test_target_count(
    target_lists: List[str], target_segments: Optional[List[str]] = None
) -> int:
    subscribers_collection = get_subscribers_collection()
    target_segments = target_segments or []

    match_conditions = []
    if target_lists:
        match_conditions.extend(
            [
                {"lists": {"$in": target_lists}},
                {"list": {"$in": target_lists}},
            ]
        )

    if target_segments:
        from database import get_segments_collection
        from routes.segments import build_segment_query, SegmentCriteria

        segments_collection = get_segments_collection()
        for segment_id in target_segments:
            try:
                if not ObjectId.is_valid(segment_id):
                    continue
                segment = await segments_collection.find_one(
                    {"_id": ObjectId(segment_id)}
                )
                if segment and segment.get("criteria"):
                    match_conditions.append(
                        build_segment_query(SegmentCriteria(**segment["criteria"]))
                    )
            except Exception as e:
                logger.warning(f"Failed to process target segment {segment_id}: {e}")

    if not match_conditions:
        return 0

    query = {
        "$and": [
            {"status": "active"},
            {"$or": match_conditions},
        ]
    }
    return await subscribers_collection.count_documents(query)


async def get_test_subscribers(
    target_lists: List[str],
    sample_size: int,
    target_segments: Optional[List[str]] = None,
) -> List[dict]:
    subscribers_collection = get_subscribers_collection()
    target_segments = target_segments or []

    match_conditions = []
    if target_lists:
        match_conditions.extend(
            [
                {"lists": {"$in": target_lists}},
                {"list": {"$in": target_lists}},
            ]
        )

    if target_segments:
        from database import get_segments_collection
        from routes.segments import build_segment_query, SegmentCriteria

        segments_collection = get_segments_collection()
        for segment_id in target_segments:
            try:
                if not ObjectId.is_valid(segment_id):
                    continue
                segment = await segments_collection.find_one(
                    {"_id": ObjectId(segment_id)}
                )
                if segment and segment.get("criteria"):
                    match_conditions.append(
                        build_segment_query(SegmentCriteria(**segment["criteria"]))
                    )
            except Exception as e:
                logger.warning(f"Failed to process target segment {segment_id}: {e}")

    if not match_conditions:
        return []

    query = {"$and": [{"status": "active"}, {"$or": match_conditions}]}
    subscribers = []
    async for doc in subscribers_collection.find(query).limit(int(sample_size)):
        doc["_id"] = str(doc["_id"])
        subscribers.append(doc)
    return subscribers


def assign_variants(subscribers: List[dict], split_percentage: int) -> Dict:
    """
    Assign subscribers to variants deterministically using MD5-based hashing.
    """
    import hashlib

    assignments: Dict[str, list] = {"A": [], "B": []}
    for sub in subscribers:
        digest = hashlib.md5(str(sub["_id"]).encode()).hexdigest()
        bucket = int(digest[:8], 16) % 100
        variant = "A" if bucket < split_percentage else "B"
        assignments[variant].append(
            {
                "id": sub["_id"],
                "email": sub["email"],
                "standard_fields": sub.get("standard_fields", {}),
                "custom_fields": sub.get("custom_fields", {}),
                "first_name": sub.get("standard_fields", {}).get("first_name", ""),
            }
        )
    return assignments


# ============================================================
# HELPER: metrics calculation (async)
# FIX: Only count SAMPLE sends (is_winner_send != True)
# ============================================================


async def calculate_test_results(test_id: str) -> Dict:
    ab_test_results_collection = get_ab_test_results_collection()

    # FIX: Exclude winner send records from sample metrics
    sample_filter = {"is_winner_send": {"$ne": True}}

    results_a = await ab_test_results_collection.find(
        {"test_id": test_id, "variant": "A", **sample_filter}
    ).to_list(None)

    results_b = await ab_test_results_collection.find(
        {"test_id": test_id, "variant": "B", **sample_filter}
    ).to_list(None)

    def metrics(results):
        if not results:
            return {
                "sent": 0,
                "opened": 0,
                "clicked": 0,
                "open_rate": 0,
                "click_rate": 0,
                "ctr": 0,
            }
        sent = len([r for r in results if r.get("email_sent")])
        opened = len([r for r in results if r.get("email_opened")])
        clicked = len([r for r in results if r.get("email_clicked")])
        return {
            "sent": sent,
            "opened": opened,
            "clicked": clicked,
            "open_rate": round((opened / sent * 100), 2) if sent else 0,
            "click_rate": round((clicked / sent * 100), 2) if sent else 0,
            "ctr": round((clicked / opened * 100), 2) if opened else 0,
        }

    return {"variant_a": metrics(results_a), "variant_b": metrics(results_b)}


# SYNC version used by Celery tasks
def calculate_test_results_sync(test_id: str) -> Dict:
    col = get_sync_ab_test_results_collection()
    # FIX: Exclude winner send records
    sample_filter = {"is_winner_send": {"$ne": True}}
    results_a = list(col.find({"test_id": test_id, "variant": "A", **sample_filter}))
    results_b = list(col.find({"test_id": test_id, "variant": "B", **sample_filter}))

    def metrics(results):
        if not results:
            return {
                "sent": 0,
                "opened": 0,
                "clicked": 0,
                "open_rate": 0,
                "click_rate": 0,
                "ctr": 0,
            }
        sent = len([r for r in results if r.get("email_sent")])
        opened = len([r for r in results if r.get("email_opened")])
        clicked = len([r for r in results if r.get("email_clicked")])
        return {
            "sent": sent,
            "opened": opened,
            "clicked": clicked,
            "open_rate": round((opened / sent * 100), 2) if sent else 0,
            "click_rate": round((clicked / sent * 100), 2) if sent else 0,
            "ctr": round((clicked / opened * 100), 2) if opened else 0,
        }

    return {"variant_a": metrics(results_a), "variant_b": metrics(results_b)}


# ============================================================
# HELPER: determine winner
# ============================================================


def determine_winner(results: Dict, criteria: str = "open_rate") -> Dict:
    a = results["variant_a"].get(criteria, 0)
    b = results["variant_b"].get(criteria, 0)

    if a > b:
        improvement = ((a - b) / b * 100) if b > 0 else 100
        return {
            "winner": "A",
            "improvement": round(improvement, 2),
            "improvement_percentage": round(improvement, 2),
            "criteria": criteria,
        }
    elif b > a:
        improvement = ((b - a) / a * 100) if a > 0 else 100
        return {
            "winner": "B",
            "improvement": round(improvement, 2),
            "improvement_percentage": round(improvement, 2),
            "criteria": criteria,
        }
    return {
        "winner": "TIE",
        "improvement": 0,
        "improvement_percentage": 0,
        "criteria": criteria,
    }


# ============================================================
# HELPER: statistical significance
# ============================================================


def calculate_statistical_significance(results: Dict) -> Dict:
    total = results["variant_a"].get("sent", 0) + results["variant_b"].get("sent", 0)
    level = "low"
    if total > 1000:
        level = "high"
    elif total > 500:
        level = "medium"
    return {
        "confidence_level": level,
        "total_samples": total,
        "is_significant": total > 100,
    }


# ============================================================
# ROUTES
# ============================================================


@router.get("/ab-tests")
        async def get_all_ab_tests():
            try:
                ab_tests_collection = get_ab_tests_collection()
                tests = []

                cursor = ab_tests_collection.find().sort("created_at", -1)
                async for test in cursor:
                    test = convert_objectid_to_str(test)

                    # ── NEW: expose provider_error + fail_reason so the dashboard
                    #         can show "✕ Failed — Provider Error" badges ────────────
                    test["provider_error"] = _safe_provider_error(test.get("provider_error"))
                    test["fail_reason"]    = test.get("fail_reason")

                    tests.append(test)

                logger.info(f"Retrieved {len(tests)} A/B tests")
                return {
                    "tests": tests,
                    "total": len(tests),
                }

            except Exception as e:
                logger.error(f"Failed to list A/B tests: {e}")
                raise HTTPException(status_code=500, detail="Failed to retrieve A/B tests")


@router.get("/ab-tests/lists")
async def get_available_lists():
    try:
        col = get_subscribers_collection()
        pipeline = [
            {"$match": {"status": "active"}},
            {
                "$facet": {
                    "from_list_field": [
                        {"$match": {"list": {"$exists": True, "$ne": None, "$ne": ""}}},
                        {"$group": {"_id": "$list", "count": {"$sum": 1}}},
                    ],
                    "from_lists_field": [
                        {"$match": {"lists": {"$exists": True, "$not": {"$size": 0}}}},
                        {"$unwind": "$lists"},
                        {"$match": {"lists": {"$ne": None, "$ne": ""}}},
                        {"$group": {"_id": "$lists", "count": {"$sum": 1}}},
                    ],
                }
            },
            {
                "$project": {
                    "combined": {
                        "$concatArrays": ["$from_list_field", "$from_lists_field"]
                    }
                }
            },
            {"$unwind": "$combined"},
            {"$replaceRoot": {"newRoot": "$combined"}},
            {"$group": {"_id": "$_id", "count": {"$sum": "$count"}}},
            {"$sort": {"_id": 1}},
        ]
        lists = []
        async for doc in col.aggregate(pipeline):
            if doc["_id"]:
                lists.append({"name": doc["_id"], "count": doc["count"]})
        return {"lists": lists}
    except Exception as e:
        logger.error(f"Failed to fetch lists for A/B testing: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch lists")


@router.get("/ab-tests/templates")
async def get_available_templates():
    try:
        col = get_templates_collection()
        templates = []
        async for doc in col.find({}, {"_id": 1, "name": 1, "subject": 1}).sort(
            "updated_at", -1
        ):
            templates.append(
                {
                    "_id": str(doc["_id"]),
                    "name": doc.get("name", "Untitled"),
                    "subject": doc.get("subject", ""),
                }
            )
        return {"templates": templates}
    except Exception as e:
        logger.error(f"Failed to fetch templates for A/B testing: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch templates")


@router.post("/ab-tests")
async def create_ab_test(test: ABTestCreate):
    try:
        col = get_ab_tests_collection()

        if not test.target_lists and not test.target_segments:
            raise HTTPException(
                status_code=400,
                detail="At least one target list or segment is required",
            )
        if not test.template_id:
            raise HTTPException(status_code=400, detail="Template is required")
        if not test.subject.strip():
            raise HTTPException(status_code=400, detail="Subject line is required")
        if not test.sender_email.strip():
            raise HTTPException(status_code=400, detail="Sender email is required")

        total_subscribers = await get_ab_test_target_count(
            test.target_lists, test.target_segments
        )
        if total_subscribers == 0:
            raise HTTPException(
                status_code=400,
                detail="No active subscribers found in the selected audience",
            )

        min_sample = min(1000, max(100, int(total_subscribers * 0.1)))
        if test.sample_size > total_subscribers:
            test.sample_size = int(total_subscribers)
        elif test.sample_size < min_sample:
            test.sample_size = int(min_sample)
        else:
            test.sample_size = int(test.sample_size)

        test_doc = {
            "test_name": test.test_name,
            "target_lists": test.target_lists,
            "target_segments": test.target_segments or [],
            "template_id": test.template_id,
            "subject": test.subject,
            "sender_name": test.sender_name,
            "sender_email": test.sender_email,
            "reply_to": test.reply_to or test.sender_email,
            "test_type": test.test_type,
            "variants": [v.dict() for v in test.variants],
            "split_percentage": test.split_percentage,
            "sample_size": test.sample_size,
            "winner_criteria": test.winner_criteria,
            "test_duration_hours": test.test_duration_hours,
            "auto_send_winner": test.auto_send_winner,
            "field_map": test.field_map or {},
            "fallback_values": test.fallback_values or {},
            "status": TestStatus.DRAFT,
            "total_target_subscribers": total_subscribers,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        result = await col.insert_one(test_doc)
        test_id_str = str(result.inserted_id)
        test_doc["_id"] = test_id_str

        logger.info(f"A/B test created: {result.inserted_id}")
        return {
            "message": "A/B test created successfully",
            "test_id": test_id_str,
            "test": test_doc,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create A/B test: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create A/B test: {str(e)}"
        )
@router.put("/ab-tests/{test_id}")
async def update_ab_test(test_id: str, test: ABTestCreate):
    """
    Update a draft A/B test. Only allowed while status == 'draft'.
    All fields from creation are editable at this stage.
    """
    try:
        col = get_ab_tests_collection()
        if not ObjectId.is_valid(test_id):
            raise HTTPException(status_code=400, detail="Invalid test ID format")

        existing = await col.find_one({"_id": ObjectId(test_id)})
        if not existing:
            raise HTTPException(status_code=404, detail="A/B test not found")

        if existing.get("status") != TestStatus.DRAFT:
            raise HTTPException(
                status_code=400,
                detail=f"Only draft tests can be edited. This test is '{existing.get('status')}'.",
            )

        if not test.target_lists and not test.target_segments:
            raise HTTPException(status_code=400, detail="At least one target list or segment is required")
        if not test.template_id:
            raise HTTPException(status_code=400, detail="Template is required")
        if not test.subject.strip():
            raise HTTPException(status_code=400, detail="Subject line is required")
        if not test.sender_email.strip():
            raise HTTPException(status_code=400, detail="Sender email is required")

        total_subscribers = await get_ab_test_target_count(
            test.target_lists, test.target_segments
        )
        if total_subscribers == 0:
            raise HTTPException(
                status_code=400,
                detail="No active subscribers found in the selected audience",
            )

        # Recalculate sample_size bounds against new audience
        min_sample = min(1000, max(100, int(total_subscribers * 0.1)))
        if test.sample_size > total_subscribers:
            test.sample_size = int(total_subscribers)
        elif test.sample_size < min_sample:
            test.sample_size = int(min_sample)
        else:
            test.sample_size = int(test.sample_size)

        update_doc = {
            "test_name": test.test_name,
            "target_lists": test.target_lists,
            "target_segments": test.target_segments or [],
            "template_id": test.template_id,
            "subject": test.subject,
            "sender_name": test.sender_name,
            "sender_email": test.sender_email,
            "reply_to": test.reply_to or test.sender_email,
            "test_type": test.test_type,
            "variants": [v.dict() for v in test.variants],
            "split_percentage": test.split_percentage,
            "sample_size": test.sample_size,
            "winner_criteria": test.winner_criteria,
            "test_duration_hours": test.test_duration_hours,
            "auto_send_winner": test.auto_send_winner,
            "field_map": test.field_map or {},
            "fallback_values": test.fallback_values or {},
            "total_target_subscribers": total_subscribers,
            "updated_at": datetime.utcnow(),
        }

        await col.update_one({"_id": ObjectId(test_id)}, {"$set": update_doc})

        updated = await col.find_one({"_id": ObjectId(test_id)})
        logger.info(f"A/B test updated: {test_id}")
        return {
            "message": "A/B test updated successfully",
            "test_id": test_id,
            "test": convert_objectid_to_str(updated),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update A/B test {test_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update A/B test: {str(e)}")



@router.get("/ab-tests/{test_id}")
async def get_ab_test(test_id: str):
    try:
        col = get_ab_tests_collection()
        if not ObjectId.is_valid(test_id):
            raise HTTPException(status_code=400, detail="Invalid test ID format")
        test = await col.find_one({"_id": ObjectId(test_id)})
        if not test:
            raise HTTPException(status_code=404, detail="A/B test not found")
        return convert_objectid_to_str(test)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get A/B test {test_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve A/B test: {str(e)}"
        )


@router.post("/ab-tests/{test_id}/start")
async def start_ab_test(test_id: str):
    try:
        col = get_ab_tests_collection()
        if not ObjectId.is_valid(test_id):
            raise HTTPException(status_code=400, detail="Invalid test ID")

        test = await col.find_one({"_id": ObjectId(test_id)})
        if not test:
            raise HTTPException(status_code=404, detail="A/B test not found")
        if test["status"] != TestStatus.DRAFT:
            raise HTTPException(
                status_code=400, detail="Test must be in draft status to start"
            )

        # Build content snapshot
        template_id = test.get("template_id")
        if not template_id:
            raise HTTPException(status_code=400, detail="A/B test has no template_id")

        if not ObjectId.is_valid(template_id):
            raise HTTPException(status_code=400, detail=f"Invalid template_id '{template_id}'")

        templates_col = get_templates_collection()
        template = await templates_col.find_one({"_id": ObjectId(template_id)})
        if not template:
            raise HTTPException(
                status_code=404,
                detail=f"Template '{template_id}' not found — it may have been deleted.",
            )

        try:
            from tasks.campaign.snapshot_utils import build_snapshot
            snapshot = build_snapshot(template, test)
        except ValueError as ve:
            raise HTTPException(status_code=422, detail=str(ve))

        # Get subscribers and assign variants
        subscribers = await get_test_subscribers(
            test.get("target_lists", []),
            int(test["sample_size"]),
            test.get("target_segments", []),
        )
        if not subscribers:
            raise HTTPException(
                status_code=400, detail="No subscribers found for this test"
            )

        variant_assignments = assign_variants(subscribers, test["split_percentage"])

        # Persist snapshot + status=running atomically
        await col.update_one(
            {"_id": ObjectId(test_id)},
            {
                "$set": {
                    "status": TestStatus.RUNNING,
                    "start_date": datetime.utcnow(),
                    "variant_assignments": variant_assignments,
                    "content_snapshot": snapshot,
                    "snapshot_taken_at": snapshot["taken_at"],
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        task = send_ab_test_batch.delay(test_id, variant_assignments)
        logger.info(f"A/B test started: {test_id}, task={task.id}")

        return {
            "message": "A/B test started successfully",
            "test_id": test_id,
            "task_id": task.id,
            "variant_a_count": len(variant_assignments["A"]),
            "variant_b_count": len(variant_assignments["B"]),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start A/B test: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to start A/B test: {str(e)}"
        )


@router.get("/ab-tests/{test_id}/results")
async def get_ab_test_results(test_id: str):
    try:
        col = get_ab_tests_collection()
        if not ObjectId.is_valid(test_id):
            raise HTTPException(status_code=400, detail="Invalid test ID")

        test = await col.find_one({"_id": ObjectId(test_id)})
        if not test:
            raise HTTPException(status_code=404, detail="A/B test not found")

        # FIX: If test is completed and winner was snapshotted, use stored values.
        # This prevents the winner % from changing after completion.
        stored_results = test.get("final_results")
        stored_winner = test.get("final_winner")

        if test["status"] == TestStatus.COMPLETED and stored_results and stored_winner:
            results = stored_results
            winner = stored_winner
        else:
            # Live calculation for running/stopped tests
            results = await calculate_test_results(test_id)
            winner = determine_winner(results, test.get("winner_criteria", "open_rate"))

        significance = calculate_statistical_significance(results)

        response_data = {
            "test_id": test_id,
            "test_name": test["test_name"],
            "status": test["status"],
            "test_type": test["test_type"],
            "target_lists": test.get("target_lists", []),
            "target_segments": test.get("target_segments", []),
            "subject": test.get("subject", ""),
            "sender_name": test.get("sender_name", ""),
            "sender_email": test.get("sender_email", ""),
            "reply_to": test.get("reply_to", ""),
            "results": results,
            "winner": winner,
            "winner_info": winner,
            "provider_error": _safe_provider_error(test.get("provider_error")),
            "fail_reason":    test.get("fail_reason"),
            "statistical_significance": significance,
            "start_date": test.get("start_date"),
            "end_date": test.get("end_date"),
            "sample_size": test.get("sample_size"),
            "split_percentage": test.get("split_percentage"),
            "winner_criteria": test.get("winner_criteria", "open_rate"),
            "test_duration_hours": test.get("test_duration_hours"),
            "auto_send_winner": test.get("auto_send_winner", True),
            "winner_variant": test.get("winner_variant"),
            "winner_variant_applied": test.get("winner_variant_applied"),
            "winner_send_status": test.get("winner_send_status"),
            "winner_send_count": test.get("winner_send_count"),
            "winner_send_sent": test.get("winner_send_sent", 0),
            "winner_send_failed": test.get("winner_send_failed", 0),
            "winner_send_total": test.get("winner_send_total"),
            "winner_send_started_at": test.get("winner_send_started_at"),
            "winner_send_completed_at": test.get("winner_send_completed_at"),
        }

        return convert_objectid_to_str(response_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get A/B test results: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get results: {str(e)}")


@router.get("/ab-tests/{test_id}/winner-send-progress")
async def get_winner_send_progress(test_id: str):
    """
    Return current winner send progress for polling.
    Reads from Redis if available, falls back to DB.
    """
    try:
        # Try Redis first (written by send_winner_batch)
        try:
            from core.redis_client import get_redis
            r = get_redis()
            progress_key = f"ab_winner_send_progress:{test_id}"
            import json
            raw = r.get(progress_key)
            if raw:
                data = json.loads(raw)
                return data
        except Exception:
            pass

        # Fallback to DB
        col = get_ab_tests_collection()
        if not ObjectId.is_valid(test_id):
            raise HTTPException(status_code=400, detail="Invalid test ID")
        test = await col.find_one(
            {"_id": ObjectId(test_id)},
            {
                "winner_send_sent": 1,
                "winner_send_failed": 1,
                "winner_send_total": 1,
                "winner_send_queued": 1,
                "winner_send_status": 1,
            },
        )
        if not test:
            raise HTTPException(status_code=404, detail="A/B test not found")

        sent = test.get("winner_send_sent", 0)
        failed = test.get("winner_send_failed", 0)
        total = test.get("winner_send_total")
        status = test.get("winner_send_status", "pending")

        return {
            "sent": sent,
            "failed": failed,
            "total": total,
            "progress_pct": round(sent / total * 100, 1) if total else None,
            "status": status,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get winner send progress: {e}")
        raise HTTPException(status_code=500, detail="Failed to get progress")


@router.post("/ab-tests/{test_id}/stop-winner-send")
async def stop_winner_send(test_id: str):
    """Set a stop flag so send_winner_batch halts after the current batch."""
    try:
        from core.redis_client import get_redis
        r = get_redis()
        r.setex(f"ab_winner_send_stop:{test_id}", 86400, "1")

        col = get_ab_tests_collection()
        if not ObjectId.is_valid(test_id):
            raise HTTPException(status_code=400, detail="Invalid test ID")
        await col.update_one(
            {"_id": ObjectId(test_id)},
            {"$set": {"winner_send_status": "stopped", "updated_at": datetime.utcnow()}},
        )
        return {"message": "Winner send stop signal sent", "test_id": test_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stop winner send: {e}")
        raise HTTPException(status_code=500, detail="Failed to stop winner send")


@router.post("/ab-tests/{test_id}/complete")
async def complete_ab_test(test_id: str, request: CompleteTestRequest):
    """
    Manually complete a running A/B test, declare the winner,
    snapshot the final results so they don't drift, and optionally
    send the winning variant to remaining subscribers.
    """
    try:
        col = get_ab_tests_collection()
        if not ObjectId.is_valid(test_id):
            raise HTTPException(status_code=400, detail="Invalid test ID")

        test = await col.find_one({"_id": ObjectId(test_id)})
        if not test:
            raise HTTPException(status_code=404, detail="A/B test not found")

        if test["status"] == TestStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Test is already completed")

        if test["status"] not in (TestStatus.RUNNING, TestStatus.STOPPED):
            raise HTTPException(
                status_code=400,
                detail=f"Test must be running or stopped to complete (current: {test['status']})",
            )

        # Calculate and SNAPSHOT results so they never change again
        results = await calculate_test_results(test_id)
        winner = determine_winner(results, test.get("winner_criteria", "open_rate"))

        await col.update_one(
            {"_id": ObjectId(test_id)},
            {
                "$set": {
                    "status": TestStatus.COMPLETED,
                    "end_date": datetime.utcnow(),
                    "winner_variant": winner.get("winner"),
                    "winner_improvement": winner.get("improvement", 0),
                    # FIX: Snapshot final results so they don't drift
                    "final_results": results,
                    "final_winner": winner,
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        campaign_applied = False

        if request.apply_to_campaign and winner.get("winner") not in (None, "TIE"):
            from tasks.ab.winner_send import send_winner_to_remaining

            send_winner_to_remaining.apply_async(
                args=[test_id, winner["winner"]],
                countdown=2,
            )
            campaign_applied = True

        msg = f"Test completed. Winner: Variant {winner.get('winner')}."
        if campaign_applied:
            msg += " Sending winning variant to remaining subscribers."

        logger.info(f"A/B test completed: {test_id}, winner={winner.get('winner')}")
        return {
            "message": msg,
            "test_id": test_id,
            "winner": winner,
            "campaign_applied": campaign_applied,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to complete A/B test {test_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to complete test: {str(e)}"
        )


@router.post("/ab-tests/{test_id}/stop")
async def stop_ab_test(test_id: str):
    """Stop a running test without completing it or declaring a winner."""
    try:
        col = get_ab_tests_collection()
        if not ObjectId.is_valid(test_id):
            raise HTTPException(status_code=400, detail="Invalid test ID")

        test = await col.find_one({"_id": ObjectId(test_id)})
        if not test:
            raise HTTPException(status_code=404, detail="A/B test not found")

        if test["status"] != TestStatus.RUNNING:
            raise HTTPException(
                status_code=400,
                detail=f"Only running tests can be stopped (current: {test['status']})",
            )

        result = await col.update_one(
            {"_id": ObjectId(test_id)},
            {
                "$set": {
                    "status": TestStatus.STOPPED,
                    "stopped_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="A/B test not found")

        logger.info(f"A/B test stopped: {test_id}")
        return {
            "message": "A/B test stopped. You can still complete it and declare a winner.",
            "test_id": test_id,
            "status": "stopped",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stop A/B test: {e}")
        raise HTTPException(status_code=500, detail="Failed to stop A/B test")


@router.delete("/ab-tests/{test_id}")
async def delete_ab_test(test_id: str):
    try:
        col = get_ab_tests_collection()
        results_col = get_ab_test_results_collection()

        if not ObjectId.is_valid(test_id):
            raise HTTPException(status_code=400, detail="Invalid test ID")

        await results_col.delete_many({"test_id": test_id})
        result = await col.delete_one({"_id": ObjectId(test_id)})

        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="A/B test not found")

        logger.info(f"A/B test deleted: {test_id}")
        return {"message": "A/B test deleted successfully", "deleted_test_id": test_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete A/B test: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete A/B test")