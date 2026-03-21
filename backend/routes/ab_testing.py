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
    get_campaigns_collection,
)
from tasks.ab_testing import send_ab_test_batch

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
    # ── personalisation ──────────────────────────────────────
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


async def get_ab_test_target_count(target_lists: List[str]) -> int:
    subscribers_collection = get_subscribers_collection()
    return await subscribers_collection.count_documents(
        {
            "$or": [
                {"lists": {"$in": target_lists}},
                {"list": {"$in": target_lists}},
            ],
            "status": "active",
        }
    )


async def get_test_subscribers(target_lists: List[str], sample_size: int) -> List[dict]:
    subscribers_collection = get_subscribers_collection()
    query = {
        "$or": [
            {"lists": {"$in": target_lists}},
            {"list": {"$in": target_lists}},
        ],
        "status": "active",
    }
    subscribers = []
    async for doc in subscribers_collection.find(query).limit(sample_size):
        doc["_id"] = str(doc["_id"])
        subscribers.append(doc)
    return subscribers


def assign_variants(subscribers: List[dict], split_percentage: int) -> Dict:
    assignments: Dict[str, list] = {"A": [], "B": []}
    for sub in subscribers:
        bucket = hash(sub["_id"]) % 100
        variant = "A" if bucket < split_percentage else "B"
        assignments[variant].append(
            {
                "id": sub["_id"],
                "email": sub["email"],
                "first_name": sub.get("standard_fields", {}).get("first_name", ""),
                "custom_fields": sub.get("custom_fields", {}),
            }
        )
    return assignments


# ============================================================
# HELPER: metrics calculation (async)
# ============================================================


async def calculate_test_results(test_id: str) -> Dict:
    ab_test_results_collection = get_ab_test_results_collection()

    results_a = await ab_test_results_collection.find(
        {"test_id": test_id, "variant": "A"}
    ).to_list(None)

    results_b = await ab_test_results_collection.find(
        {"test_id": test_id, "variant": "B"}
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
    results_a = list(col.find({"test_id": test_id, "variant": "A"}))
    results_b = list(col.find({"test_id": test_id, "variant": "B"}))

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
# HELPER: apply winner to campaign (sync, used by Celery)
# ============================================================


def apply_winner_to_campaign_sync(test_id: str, campaign_id: str, winner_variant: str):
    """Update campaign with winner config then trigger remaining-subscriber send."""
    from database import get_sync_campaigns_collection
    from tasks.email_campaign_tasks import send_campaign_batch

    col_tests = get_sync_ab_tests_collection()
    col_campaigns = get_sync_campaigns_collection()

    test = col_tests.find_one({"_id": ObjectId(test_id)})
    if not test or not ObjectId.is_valid(campaign_id):
        logger.error(f"apply_winner: bad ids test={test_id} campaign={campaign_id}")
        return

    variant_index = 0 if winner_variant == "A" else 1
    variants = test.get("variants", [])
    if variant_index >= len(variants):
        logger.error(f"apply_winner: variant index {variant_index} out of range")
        return

    winning = variants[variant_index]
    update: Dict = {"winner_variant_applied": winner_variant}
    for field in (
        "subject",
        "sender_name",
        "sender_email",
        "reply_to",
        "content",
        "template_id",
    ):
        if field in winning and winning[field]:
            update[field] = winning[field]

    col_campaigns.update_one({"_id": ObjectId(campaign_id)}, {"$set": update})
    logger.info(
        f"apply_winner: campaign {campaign_id} updated with variant {winner_variant}"
    )

    send_campaign_batch.delay(campaign_id=campaign_id)
    logger.info(
        f"apply_winner: send_campaign_batch triggered for campaign {campaign_id}"
    )


# ============================================================
# ROUTES
# ============================================================


@router.get("/ab-tests")
async def get_all_ab_tests():
    try:
        col = get_ab_tests_collection()
        tests = []
        async for doc in col.find().sort("created_at", -1):
            tests.append(convert_objectid_to_str(doc))
        logger.info(f"Retrieved {len(tests)} A/B tests")
        return {"tests": tests, "total": len(tests)}
    except Exception as e:
        logger.error(f"Failed to list A/B tests: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve A/B tests")


@router.get("/ab-tests/lists")
async def get_available_lists():
    try:
        col = get_subscribers_collection()
        # Support subscribers that store list membership as a single string field
        # ("list") OR as an array field ("lists") — unify with $facet then merge.
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

        if not test.target_lists:
            raise HTTPException(
                status_code=400, detail="At least one target list is required"
            )
        if not test.template_id:
            raise HTTPException(status_code=400, detail="Template is required")
        if not test.subject.strip():
            raise HTTPException(status_code=400, detail="Subject line is required")
        if not test.sender_email.strip():
            raise HTTPException(status_code=400, detail="Sender email is required")

        total_subscribers = await get_ab_test_target_count(test.target_lists)
        if total_subscribers == 0:
            raise HTTPException(
                status_code=400,
                detail="No active subscribers found in the selected lists",
            )

        min_sample = min(1000, max(100, int(total_subscribers * 0.1)))
        if test.sample_size > total_subscribers:
            test.sample_size = total_subscribers
        elif test.sample_size < min_sample:
            test.sample_size = min_sample

        test_doc = {
            "test_name": test.test_name,
            "target_lists": test.target_lists,
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
            # ── personalisation ─────────────────────────────
            "field_map": test.field_map or {},
            "fallback_values": test.fallback_values or {},
            # ────────────────────────────────────────────────
            "status": TestStatus.DRAFT,
            "total_target_subscribers": total_subscribers,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        result = await col.insert_one(test_doc)
        test_id_str = str(result.inserted_id)

        # ── Create a linked campaign so the winner can be auto-applied ──
        try:
            campaigns_col = get_campaigns_collection()
            campaign_doc = {
                "title": f"[A/B Test] {test.test_name}",
                "subject": test.subject,
                "sender_name": test.sender_name,
                "sender_email": test.sender_email,
                "reply_to": test.reply_to or test.sender_email,
                "target_lists": test.target_lists,
                "template_id": test.template_id,
                "field_map": test.field_map or {},
                "fallback_values": test.fallback_values or {},
                "status": "draft",
                "ab_test_id": test_id_str,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
            campaign_result = await campaigns_col.insert_one(campaign_doc)
            campaign_id_str = str(campaign_result.inserted_id)
            # Link campaign back to the test document
            await col.update_one(
                {"_id": result.inserted_id},
                {"$set": {"campaign_id": campaign_result.inserted_id}},
            )
            test_doc["campaign_id"] = campaign_id_str
            logger.info(
                f"Linked campaign {campaign_id_str} created for A/B test {test_id_str}"
            )
        except Exception as camp_err:
            logger.warning(
                f"Could not create linked campaign for A/B test {test_id_str}: {camp_err}"
            )
            campaign_id_str = None

        test_doc["_id"] = test_id_str

        logger.info(f"A/B test created: {result.inserted_id} lists={test.target_lists}")
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

                # ── 1. Build content snapshot before changing status ─────────────────
                template_id = test.get("template_id")
                if not template_id:
                    raise HTTPException(
                        status_code=400,
                        detail="A/B test has no template_id — cannot start",
                    )

                if not ObjectId.is_valid(template_id):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid template_id '{template_id}' stored on test",
                    )

                templates_col = get_templates_collection()
                template = await templates_col.find_one({"_id": ObjectId(template_id)})
                if not template:
                    raise HTTPException(
                        status_code=404,
                        detail=(
                            f"Template '{template_id}' not found — "
                            "it may have been deleted. Update the A/B test before starting."
                        ),
                    )

                # Reuse the same snapshot builder used by campaigns.
                # The test doc acts as a "campaign-like" object for field_map / fallback.
                try:
                    from tasks.campaign.snapshot_utils import build_snapshot

                    snapshot = build_snapshot(template, test)
                except ValueError as ve:
                    raise HTTPException(status_code=422, detail=str(ve))

                # ── 2. Get subscribers and assign variants ────────────────────────────
                subscribers = await get_test_subscribers(
                    test.get("target_lists", []),
                    test["sample_size"],
                )
                if not subscribers:
                    raise HTTPException(
                        status_code=400, detail="No subscribers found for this test"
                    )

                variant_assignments = assign_variants(
                    subscribers, test["split_percentage"]
                )

                # ── 3. Persist snapshot + status=running atomically ──────────────────
                await col.update_one(
                    {"_id": ObjectId(test_id)},
                    {
                        "$set": {
                            "status": TestStatus.RUNNING,
                            "start_date": datetime.utcnow(),
                            "variant_assignments": variant_assignments,
                            "content_snapshot": snapshot,  # ← NEW
                            "snapshot_taken_at": snapshot["taken_at"],  # ← NEW
                            "updated_at": datetime.utcnow(),
                        }
                    },
                )

                # ── 4. Trigger Celery batch AFTER snapshot is persisted ───────────────
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

        results = await calculate_test_results(test_id)
        winner = determine_winner(results, test.get("winner_criteria", "open_rate"))
        significance = calculate_statistical_significance(results)

        response_data = {
            "test_id": test_id,
            "test_name": test["test_name"],
            "status": test["status"],
            "test_type": test["test_type"],
            "target_lists": test.get("target_lists", []),
            "subject": test.get("subject", ""),
            "sender_name": test.get("sender_name", ""),
            "results": results,
            "winner": winner,
            "winner_info": winner,  # alias for frontend compat
            "statistical_significance": significance,
            "start_date": test.get("start_date"),
            "end_date": test.get("end_date"),
            "sample_size": test.get("sample_size"),
            "split_percentage": test.get("split_percentage"),
            "winner_criteria": test.get("winner_criteria", "open_rate"),
            # ── new fields ──────────────────────────────────
            "test_duration_hours": test.get("test_duration_hours"),
            "auto_send_winner": test.get("auto_send_winner", True),
            "winner_variant": test.get("winner_variant"),
            "winner_variant_applied": test.get("winner_variant_applied"),
            "campaign_id": str(test["campaign_id"])
            if test.get("campaign_id")
            else None,
        }

        return convert_objectid_to_str(response_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get A/B test results: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get results: {str(e)}")


@router.post("/ab-tests/{test_id}/complete")
async def complete_ab_test(test_id: str, request: CompleteTestRequest):
    """
    Manually complete a running A/B test, declare the winner,
    and optionally apply the winner to the linked campaign.
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

        if test["status"] != TestStatus.RUNNING:
            raise HTTPException(
                status_code=400,
                detail=f"Test must be running to complete (current: {test['status']})",
            )

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
                    "updated_at": datetime.utcnow(),
                }
            },
        )

        campaign_applied = False

        if (
            request.apply_to_campaign
            and test.get("campaign_id")
            and winner.get("winner") != "TIE"
        ):
            # Fire Celery task so we don't block the API response
            from tasks.ab_testing import auto_complete_ab_test

            auto_complete_ab_test.apply_async(
                kwargs={"test_id": test_id, "apply_to_campaign": True},
                countdown=1,
            )
            campaign_applied = True

        msg = f"Test completed. Winner: Variant {winner.get('winner')}."
        if campaign_applied:
            msg += " Winner variant applied to campaign. Sending to remaining subscribers shortly."

        logger.info(
            f"A/B test manually completed: {test_id}, winner={winner.get('winner')}"
        )
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
    try:
        col = get_ab_tests_collection()
        if not ObjectId.is_valid(test_id):
            raise HTTPException(status_code=400, detail="Invalid test ID")

        result = await col.update_one(
            {"_id": ObjectId(test_id)},
            {
                "$set": {
                    "status": TestStatus.COMPLETED,
                    "end_date": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="A/B test not found")

        logger.info(f"A/B test stopped: {test_id}")
        return {"message": "A/B test stopped successfully", "test_id": test_id}

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
