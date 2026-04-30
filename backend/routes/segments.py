# backend/routes/segments.py
# ------------------------------------------------------------------------------
# Segment definitions and query builder.
#
# Changes vs previous version:
#   - P0 FIX: Geographic now queries `standard_fields.country/city` (matches schema).
#   - P0 FIX: Engagement Level removed entirely (was a non-functional placeholder).
#   - P1 FIX: All user-supplied regex inputs are escaped via `re.escape`.
#   - P1 FIX: Profile completeness checks `$nin: ["", None]` instead of `$ne: ""`.
#   - P1 FIX: industry/companySize/customFields are guarded against duplicate keys.
#   - NEW:    Edit/delete/disable is blocked when the segment is referenced by
#             a live automation rule, a sending/scheduled/draft campaign, a
#             running/draft/paused A/B test, or an in-progress workflow instance.
#             A new GET /{id}/usage endpoint returns the reference list so the
#             UI can show users *why* a segment is locked.
#
# Source-of-truth notes:
#   - country/city are STANDARD fields (see schemas/subscriber_schema.py).
#   - Engagement data lives in email_events_collection. Real engagement-based
#     segmentation is a tracked feature; do not silently approximate it here.
#   - Segments are referenced by string ObjectId in:
#       * campaigns.target_segments
#       * automation_rules.target_segments
#       * ab_tests.target_segments
# ------------------------------------------------------------------------------

from fastapi import APIRouter, HTTPException, Query, Request, BackgroundTasks
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime, timedelta
import logging
import re

from database import (
    get_subscribers_collection,
    get_segments_collection,
    get_audit_collection,
    get_campaigns_collection,
    get_automation_rules_collection,
    get_ab_tests_collection,
    get_workflow_instances_collection,
)

logger = logging.getLogger("uvicorn.error")
router = APIRouter()


# ==============================================================================
# Constants — which entity statuses count as "in use"
# ==============================================================================
# A segment is locked while any referencing entity is in one of these states.
# Editing criteria mid-flight could change who receives an email, so we are
# deliberately conservative.

CAMPAIGN_LIVE_STATUSES = {
    "draft",  # may be sent without further confirmation
    "scheduled",  # will be sent at a fixed future time
    "queued",
    "sending",
    "processing",
    "paused",  # paused campaigns can be resumed
}

AUTOMATION_LIVE_STATUSES = {
    "active",
    "draft",  # toggling draft -> active should not require re-attaching segments
    "paused",
}

AB_TEST_LIVE_STATUSES = {
    "draft",
    "running",
    "paused",
}

WORKFLOW_LIVE_STATUSES = {
    "in_progress",
}


# ==============================================================================
# Pydantic models (7 segmentation types — engagement removed)
# ==============================================================================


class GeographicCriteria(BaseModel):
    country: Optional[str] = ""
    city: Optional[str] = ""


class SegmentCriteria(BaseModel):
    # 1. Subscriber Status
    status: Optional[List[str]] = None

    # 2. Lists
    lists: Optional[List[str]] = None

    # 3. Subscription Date (days back from now, inclusive)
    dateRange: Optional[int] = None

    # 4. Profile Completeness — keys are standard field names
    profileCompleteness: Optional[Dict[str, bool]] = None

    # 5. Geographic — country/city are STANDARD fields per the subscriber schema
    geographic: Optional[GeographicCriteria] = None

    # 6. Email Domain
    emailDomain: Optional[List[str]] = None

    # 7. Custom Fields
    industry: Optional[str] = ""
    companySize: Optional[str] = ""
    customFields: Optional[Dict[str, str]] = None


class SegmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default="", max_length=500)
    criteria: SegmentCriteria
    is_active: Optional[bool] = True


class SegmentUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    criteria: Optional[SegmentCriteria] = None
    is_active: Optional[bool] = None


class SegmentPreview(BaseModel):
    criteria: SegmentCriteria
    limit: Optional[int] = Field(default=50, le=100)


class SegmentCount(BaseModel):
    criteria: SegmentCriteria


# ==============================================================================
# Query builder
# ==============================================================================


def _ci_regex(value: str, anchor: bool = False) -> Dict[str, str]:
    """
    Build a case-insensitive Mongo regex filter from user input.
    Escapes regex metacharacters so values like '(B2B)' or 'Côte d'Ivoire'
    don't blow up the query. Set anchor=True for exact-match-ish behaviour.
    """
    escaped = re.escape(value.strip())
    if anchor:
        escaped = f"^{escaped}$"
    return {"$regex": escaped, "$options": "i"}


def build_segment_query(criteria: SegmentCriteria) -> dict:
    """
    Convert SegmentCriteria into a MongoDB filter document.

    Returns {} when no criteria are set (matches everyone). Callers that
    don't want that behaviour should validate before invoking.
    """
    query: Dict[str, Any] = {}

    # 1. Subscriber Status
    if criteria.status:
        query["status"] = {"$in": criteria.status}

    # 2. Lists
    if criteria.lists:
        query["list"] = {"$in": criteria.lists}

    # 3. Subscription Date — created_at >= now - dateRange days
    if criteria.dateRange:
        cutoff_date = datetime.utcnow() - timedelta(days=int(criteria.dateRange))
        query["created_at"] = {"$gte": cutoff_date}

    # 4. Profile Completeness — true means "field has a non-empty value"
    if criteria.profileCompleteness:
        for field, required in criteria.profileCompleteness.items():
            if required:
                query[f"standard_fields.{field}"] = {
                    "$exists": True,
                    "$nin": ["", None],
                }

    # 5. Geographic — STANDARD fields (P0 FIX)
    if criteria.geographic:
        if criteria.geographic.country and criteria.geographic.country.strip():
            query["standard_fields.country"] = _ci_regex(criteria.geographic.country)
        if criteria.geographic.city and criteria.geographic.city.strip():
            query["standard_fields.city"] = _ci_regex(criteria.geographic.city)

    # 6. Email Domain
    if criteria.emailDomain:
        domain_conditions: List[Dict[str, Any]] = []
        for domain in criteria.emailDomain:
            if not domain:
                continue
            if domain == "corporate":
                # Anything NOT on the common-consumer list
                domain_conditions.append(
                    {
                        "email": {
                            "$not": {
                                "$regex": r"@(gmail|yahoo|hotmail|outlook|aol)\.com$",
                                "$options": "i",
                            }
                        }
                    }
                )
            else:
                domain_conditions.append(
                    {
                        "email": {
                            "$regex": f"@{re.escape(domain)}$",
                            "$options": "i",
                        }
                    }
                )
        if domain_conditions:
            query["$or"] = domain_conditions

    # 7. Custom Fields — industry/companySize are convenience inputs that map
    # into custom_fields.* exactly like the dynamic ones. We dedupe so the UI
    # can either offer them as shortcuts or via the dynamic control without
    # generating conflicting filters.
    custom_filters: Dict[str, Dict[str, str]] = {}

    if criteria.industry and criteria.industry.strip():
        custom_filters["industry"] = _ci_regex(criteria.industry)
    if criteria.companySize and criteria.companySize.strip():
        custom_filters["companySize"] = _ci_regex(criteria.companySize)
    if criteria.customFields:
        for field, value in criteria.customFields.items():
            if not field or not value or not str(value).strip():
                continue
            # Dynamic control wins on conflict — user typed it most recently.
            custom_filters[field] = _ci_regex(str(value))

    for field, regex_filter in custom_filters.items():
        query[f"custom_fields.{field}"] = regex_filter

    return query


# ==============================================================================
# Usage / lock detection
# ==============================================================================


async def get_segment_usage(segment_id: str) -> Dict[str, Any]:
    """
    Return all live references to a segment. A segment with any references
    here MUST NOT have its criteria modified, must not be deleted, and must
    not be deactivated — doing so could change who receives in-flight email.

    Returned shape is shaped for direct UI consumption.
    """
    if not ObjectId.is_valid(segment_id):
        return {
            "in_use": False,
            "campaigns": [],
            "automations": [],
            "ab_tests": [],
            "workflows": 0,
        }

    segment_id_str = str(segment_id)

    campaigns_collection = get_campaigns_collection()
    rules_collection = get_automation_rules_collection()
    ab_tests_collection = get_ab_tests_collection()
    workflow_instances_collection = get_workflow_instances_collection()

    # --- Campaigns -----------------------------------------------------------
    campaign_cursor = campaigns_collection.find(
        {
            "target_segments": segment_id_str,
            "status": {"$in": list(CAMPAIGN_LIVE_STATUSES)},
        },
        {"title": 1, "status": 1},
    )
    campaigns = []
    async for doc in campaign_cursor:
        campaigns.append(
            {
                "id": str(doc["_id"]),
                "title": doc.get("title", "Untitled"),
                "status": doc.get("status", "unknown"),
            }
        )

    # --- Automation rules ----------------------------------------------------
    rule_cursor = rules_collection.find(
        {
            "target_segments": segment_id_str,
            "status": {"$in": list(AUTOMATION_LIVE_STATUSES)},
        },
        {"name": 1, "status": 1},
    )
    automations = []
    async for doc in rule_cursor:
        automations.append(
            {
                "id": str(doc["_id"]),
                "name": doc.get("name", "Untitled"),
                "status": doc.get("status", "unknown"),
            }
        )

    # --- A/B tests -----------------------------------------------------------
    ab_cursor = ab_tests_collection.find(
        {
            "target_segments": segment_id_str,
            "status": {"$in": list(AB_TEST_LIVE_STATUSES)},
        },
        {"test_name": 1, "status": 1},
    )
    ab_tests = []
    async for doc in ab_cursor:
        ab_tests.append(
            {
                "id": str(doc["_id"]),
                "name": doc.get("test_name", "Untitled"),
                "status": doc.get("status", "unknown"),
            }
        )

    # --- Workflow instances --------------------------------------------------
    # Defence in depth: even if the parent rule is paused, an in-progress
    # workflow instance referencing this segment via its rule is still a hard
    # block. We count rather than list, since this can be large.
    rule_ids_with_segment = []
    async for doc in rules_collection.find(
        {"target_segments": segment_id_str},
        {"_id": 1},
    ):
        rule_ids_with_segment.append(str(doc["_id"]))

    workflow_count = 0
    if rule_ids_with_segment:
        workflow_count = await workflow_instances_collection.count_documents(
            {
                "automation_rule_id": {"$in": rule_ids_with_segment},
                "status": {"$in": list(WORKFLOW_LIVE_STATUSES)},
            }
        )

    in_use = bool(campaigns or automations or ab_tests or workflow_count)

    return {
        "in_use": in_use,
        "campaigns": campaigns,
        "automations": automations,
        "ab_tests": ab_tests,
        "workflows": workflow_count,
    }


def _format_lock_message(usage: Dict[str, Any]) -> str:
    """Human-readable summary for HTTP error details."""
    parts = []
    if usage["automations"]:
        parts.append(f"{len(usage['automations'])} automation rule(s)")
    if usage["workflows"]:
        parts.append(f"{usage['workflows']} active workflow run(s)")
    if usage["campaigns"]:
        parts.append(f"{len(usage['campaigns'])} campaign(s)")
    if usage["ab_tests"]:
        parts.append(f"{len(usage['ab_tests'])} A/B test(s)")
    return ", ".join(parts) or "active references"


# ==============================================================================
# Audit log
# ==============================================================================


async def log_segment_activity(
    action: str,
    segment_id: str,
    user_action: str,
    before_data: dict = None,
    after_data: dict = None,
    metadata: dict = None,
    request: Request = None,
):
    try:
        audit_collection = get_audit_collection()
        log_entry = {
            "timestamp": datetime.utcnow(),
            "action": action,
            "entity_type": "segment",
            "entity_id": segment_id,
            "user_action": user_action,
            "before_data": before_data or {},
            "after_data": after_data or {},
            "metadata": {
                **(metadata or {}),
                "ip_address": str(request.client.host)
                if request and request.client
                else "unknown",
                "segmentation_types": 7,
            },
        }
        await audit_collection.insert_one(log_entry)
        logger.info(f"SEGMENT AUDIT: {action} - {user_action}")
    except Exception as e:
        logger.error(f"Failed to log segment activity: {e}")


# ==============================================================================
# Helpers
# ==============================================================================


def _criteria_types(criteria: SegmentCriteria) -> List[str]:
    """Compact list of which segmentation buckets the criteria touches."""
    types: List[str] = []
    if criteria.status:
        types.append("status")
    if criteria.lists:
        types.append("lists")
    if criteria.dateRange:
        types.append("dateRange")
    if criteria.profileCompleteness and any(criteria.profileCompleteness.values()):
        types.append("profileCompleteness")
    if criteria.geographic and (
        criteria.geographic.country or criteria.geographic.city
    ):
        types.append("geographic")
    if criteria.emailDomain:
        types.append("emailDomain")
    if (
        (criteria.industry and criteria.industry.strip())
        or (criteria.companySize and criteria.companySize.strip())
        or criteria.customFields
    ):
        types.append("customFields")
    return types


# ==============================================================================
# API: list / read
# ==============================================================================


@router.get("")
async def list_segments(
    active_only: bool = Query(default=True),
    limit: int = Query(default=100, le=500),
    skip: int = Query(default=0, ge=0),
):
    """List segments. Stale subscriber counts (>1h old) are recalculated inline."""
    try:
        segments_collection = get_segments_collection()
        subscribers_collection = get_subscribers_collection()

        query: Dict[str, Any] = {}
        if active_only:
            query["is_active"] = True

        cursor = (
            segments_collection.find(query)
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        segments: List[Dict[str, Any]] = []

        async for segment in cursor:
            segment["_id"] = str(segment["_id"])

            last_calculated = segment.get("last_calculated")
            if not last_calculated or (datetime.utcnow() - last_calculated) > timedelta(
                hours=1
            ):
                try:
                    query_filter = build_segment_query(
                        SegmentCriteria(**segment.get("criteria", {}))
                    )
                    current_count = await subscribers_collection.count_documents(
                        query_filter
                    )

                    await segments_collection.update_one(
                        {"_id": ObjectId(segment["_id"])},
                        {
                            "$set": {
                                "subscriber_count": current_count,
                                "last_calculated": datetime.utcnow(),
                            }
                        },
                    )
                    segment["subscriber_count"] = current_count
                except Exception as e:
                    logger.error(
                        f"Error refreshing count for segment {segment.get('name')}: {e}"
                    )
                    segment["subscriber_count"] = segment.get("subscriber_count", 0)

            segments.append(segment)

        total = await segments_collection.count_documents(query)

        return {
            "segments": segments,
            "total": total,
            "page": (skip // limit) + 1,
            "total_pages": (total + limit - 1) // limit,
            "segmentation_types": 7,
        }

    except Exception as e:
        logger.error(f"List segments failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{segment_id}")
async def get_segment(segment_id: str):
    if not ObjectId.is_valid(segment_id):
        raise HTTPException(status_code=400, detail="Invalid segment ID")

    segments_collection = get_segments_collection()
    segment = await segments_collection.find_one({"_id": ObjectId(segment_id)})
    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")

    segment["_id"] = str(segment["_id"])
    # Attach lock state so the editor can disable controls in a single round-trip.
    segment["usage"] = await get_segment_usage(segment_id)
    return segment


@router.get("/{segment_id}/usage")
async def get_segment_usage_endpoint(segment_id: str):
    """
    Return what's currently using this segment. Used by the UI to explain why
    edit/delete are disabled and to deep-link to the offending entities.
    """
    if not ObjectId.is_valid(segment_id):
        raise HTTPException(status_code=400, detail="Invalid segment ID")
    return await get_segment_usage(segment_id)


# ==============================================================================
# API: create
# ==============================================================================


@router.post("")
async def create_segment(segment_data: SegmentCreate, request: Request):
    try:
        segments_collection = get_segments_collection()
        subscribers_collection = get_subscribers_collection()

        existing = await segments_collection.find_one({"name": segment_data.name})
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Segment with name '{segment_data.name}' already exists",
            )

        query_filter = build_segment_query(segment_data.criteria)
        subscriber_count = await subscribers_collection.count_documents(query_filter)

        criteria_types = _criteria_types(segment_data.criteria)

        segment_doc = {
            "name": segment_data.name,
            "description": segment_data.description,
            "criteria": segment_data.criteria.dict(),
            "query": query_filter,
            "subscriber_count": subscriber_count,
            "criteria_types": criteria_types,
            "is_active": segment_data.is_active,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "last_calculated": datetime.utcnow(),
        }

        result = await segments_collection.insert_one(segment_doc)
        segment_id = str(result.inserted_id)

        await log_segment_activity(
            action="create",
            segment_id=segment_id,
            user_action=(
                f"Created segment '{segment_data.name}' "
                f"with {len(criteria_types)} criteria type(s) and {subscriber_count} subscribers"
            ),
            after_data=segment_doc,
            metadata={
                "segment_name": segment_data.name,
                "subscriber_count": subscriber_count,
                "criteria_types": criteria_types,
            },
            request=request,
        )

        return {
            "message": "Segment created successfully",
            "segment_id": segment_id,
            "subscriber_count": subscriber_count,
            "criteria_types": criteria_types,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create segment failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# API: update
# ==============================================================================


@router.put("/{segment_id}")
async def update_segment(
    segment_id: str, segment_data: SegmentUpdate, request: Request
):
    """
    Update a segment.

    Lock policy:
      - `name` and `description` are always editable (cosmetic only; nothing
        in the system looks segments up by name).
      - `criteria` and `is_active` are blocked when the segment is in use by a
        live campaign, automation rule, A/B test, or in-progress workflow.
        This protects active sends from a sudden audience shift.
    """
    try:
        if not ObjectId.is_valid(segment_id):
            raise HTTPException(status_code=400, detail="Invalid segment ID")

        segments_collection = get_segments_collection()
        subscribers_collection = get_subscribers_collection()

        existing_segment = await segments_collection.find_one(
            {"_id": ObjectId(segment_id)}
        )
        if not existing_segment:
            raise HTTPException(status_code=404, detail="Segment not found")

        wants_criteria_change = segment_data.criteria is not None
        wants_active_change = (
            segment_data.is_active is not None
            and segment_data.is_active != existing_segment.get("is_active", True)
        )

        if wants_criteria_change or wants_active_change:
            usage = await get_segment_usage(segment_id)
            if usage["in_use"]:
                blocked_field = "criteria" if wants_criteria_change else "is_active"
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "segment_in_use",
                        "message": (
                            f"Cannot modify '{blocked_field}' while this segment is "
                            f"referenced by {_format_lock_message(usage)}. "
                            "Pause or complete those first, or duplicate the segment."
                        ),
                        "usage": usage,
                    },
                )

        # Name uniqueness check (skip if name unchanged)
        if segment_data.name and segment_data.name != existing_segment["name"]:
            duplicate = await segments_collection.find_one({"name": segment_data.name})
            if duplicate:
                raise HTTPException(
                    status_code=400,
                    detail=f"Segment with name '{segment_data.name}' already exists",
                )

        update_data: Dict[str, Any] = {"updated_at": datetime.utcnow()}

        if segment_data.name is not None:
            update_data["name"] = segment_data.name
        if segment_data.description is not None:
            update_data["description"] = segment_data.description
        if segment_data.is_active is not None:
            update_data["is_active"] = segment_data.is_active

        if wants_criteria_change:
            query_filter = build_segment_query(segment_data.criteria)
            subscriber_count = await subscribers_collection.count_documents(
                query_filter
            )
            update_data.update(
                {
                    "criteria": segment_data.criteria.dict(),
                    "query": query_filter,
                    "subscriber_count": subscriber_count,
                    "criteria_types": _criteria_types(segment_data.criteria),
                    "last_calculated": datetime.utcnow(),
                }
            )

        result = await segments_collection.update_one(
            {"_id": ObjectId(segment_id)},
            {"$set": update_data},
        )
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Segment not found")

        await log_segment_activity(
            action="update",
            segment_id=segment_id,
            user_action=(
                f"Updated segment '{segment_data.name or existing_segment['name']}' "
                f"({', '.join(k for k in update_data if k != 'updated_at')})"
            ),
            before_data=existing_segment,
            after_data=update_data,
            metadata={
                "segment_name": segment_data.name or existing_segment["name"],
                "changed_fields": [k for k in update_data if k != "updated_at"],
                "criteria_types": update_data.get(
                    "criteria_types", existing_segment.get("criteria_types", [])
                ),
            },
            request=request,
        )

        return {
            "message": "Segment updated successfully",
            "criteria_types": update_data.get(
                "criteria_types", existing_segment.get("criteria_types", [])
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update segment failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# API: delete
# ==============================================================================


@router.delete("/{segment_id}")
async def delete_segment(segment_id: str, request: Request):
    """
    Delete a segment. Hard-blocked when in use; deletion is irrecoverable and
    would orphan references in campaigns/automations/A/B tests.
    """
    try:
        if not ObjectId.is_valid(segment_id):
            raise HTTPException(status_code=400, detail="Invalid segment ID")

        segments_collection = get_segments_collection()
        segment = await segments_collection.find_one({"_id": ObjectId(segment_id)})
        if not segment:
            raise HTTPException(status_code=404, detail="Segment not found")

        usage = await get_segment_usage(segment_id)
        if usage["in_use"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "segment_in_use",
                    "message": (
                        f"Cannot delete this segment while it is referenced by "
                        f"{_format_lock_message(usage)}. Remove those references first."
                    ),
                    "usage": usage,
                },
            )

        result = await segments_collection.delete_one({"_id": ObjectId(segment_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Segment not found")

        await log_segment_activity(
            action="delete",
            segment_id=segment_id,
            user_action=f"Deleted segment '{segment['name']}'",
            before_data=segment,
            metadata={
                "segment_name": segment["name"],
                "subscriber_count": segment.get("subscriber_count", 0),
                "criteria_types": segment.get("criteria_types", []),
            },
            request=request,
        )

        return {"message": "Segment deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete segment failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# API: preview / count / refresh / subscribers
# ==============================================================================


@router.post("/preview")
async def preview_segment(preview_data: SegmentPreview):
    try:
        subscribers_collection = get_subscribers_collection()
        query_filter = build_segment_query(preview_data.criteria)

        cursor = subscribers_collection.find(query_filter).limit(preview_data.limit)
        subscribers: List[Dict[str, Any]] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            doc.setdefault("standard_fields", {})
            doc.setdefault("custom_fields", {})
            subscribers.append(doc)

        total_count = await subscribers_collection.count_documents(query_filter)

        return {
            "subscribers": subscribers,
            "total_matching": total_count,
            "preview_count": len(subscribers),
            "query": query_filter,
            "segmentation_types_used": len(_criteria_types(preview_data.criteria)),
        }

    except Exception as e:
        logger.error(f"Preview segment failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/count")
async def count_segment_subscribers(count_data: SegmentCount):
    try:
        subscribers_collection = get_subscribers_collection()
        query_filter = build_segment_query(count_data.criteria)
        count = await subscribers_collection.count_documents(query_filter)

        return {
            "count": count,
            "query": query_filter,
            "criteria_types": _criteria_types(count_data.criteria),
        }

    except Exception as e:
        logger.error(f"Count segment failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{segment_id}/refresh")
async def refresh_segment_count(segment_id: str, request: Request):
    try:
        if not ObjectId.is_valid(segment_id):
            raise HTTPException(status_code=400, detail="Invalid segment ID")

        segments_collection = get_segments_collection()
        subscribers_collection = get_subscribers_collection()

        segment = await segments_collection.find_one({"_id": ObjectId(segment_id)})
        if not segment:
            raise HTTPException(status_code=404, detail="Segment not found")

        query_filter = build_segment_query(SegmentCriteria(**segment["criteria"]))
        new_count = await subscribers_collection.count_documents(query_filter)

        await segments_collection.update_one(
            {"_id": ObjectId(segment_id)},
            {
                "$set": {
                    "subscriber_count": new_count,
                    "last_calculated": datetime.utcnow(),
                    "query": query_filter,
                }
            },
        )

        return {
            "message": "Segment count refreshed",
            "subscriber_count": new_count,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Refresh segment failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{segment_id}/subscribers")
async def get_segment_subscribers(
    segment_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    try:
        if not ObjectId.is_valid(segment_id):
            raise HTTPException(status_code=400, detail="Invalid segment ID")

        segments_collection = get_segments_collection()
        subscribers_collection = get_subscribers_collection()

        segment = await segments_collection.find_one({"_id": ObjectId(segment_id)})
        if not segment:
            raise HTTPException(status_code=404, detail="Segment not found")

        query_filter = build_segment_query(SegmentCriteria(**segment["criteria"]))
        skip = (page - 1) * limit

        cursor = (
            subscribers_collection.find(query_filter)
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        subscribers: List[Dict[str, Any]] = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            doc.setdefault("standard_fields", {})
            doc.setdefault("custom_fields", {})
            subscribers.append(doc)

        total = await subscribers_collection.count_documents(query_filter)
        total_pages = (total + limit - 1) // limit

        return {
            "subscribers": subscribers,
            "segment": {
                "name": segment["name"],
                "description": segment.get("description", ""),
                "criteria_types": segment.get("criteria_types", []),
            },
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
            "query": query_filter,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get segment subscribers failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
# API: bulk refresh
# ==============================================================================


@router.post("/bulk-refresh")
async def refresh_all_segments(request: Request, background_tasks: BackgroundTasks):
    try:
        segments_collection = get_segments_collection()
        cursor = segments_collection.find({"is_active": True}, {"_id": 1})
        segment_ids = [str(s["_id"]) async for s in cursor]

        background_tasks.add_task(_refresh_segments_background, segment_ids)

        return {
            "message": f"Started background refresh for {len(segment_ids)} segments",
            "segment_count": len(segment_ids),
        }

    except Exception as e:
        logger.error(f"Bulk refresh failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _refresh_segments_background(segment_ids: List[str]):
    try:
        segments_collection = get_segments_collection()
        subscribers_collection = get_subscribers_collection()

        for segment_id in segment_ids:
            try:
                segment = await segments_collection.find_one(
                    {"_id": ObjectId(segment_id)}
                )
                if not segment:
                    continue

                query_filter = build_segment_query(
                    SegmentCriteria(**segment["criteria"])
                )
                new_count = await subscribers_collection.count_documents(query_filter)

                await segments_collection.update_one(
                    {"_id": ObjectId(segment_id)},
                    {
                        "$set": {
                            "subscriber_count": new_count,
                            "last_calculated": datetime.utcnow(),
                            "query": query_filter,
                        }
                    },
                )

                logger.info(
                    f"Refreshed segment '{segment['name']}': {new_count} subscribers"
                )

            except Exception as e:
                logger.error(f"Failed to refresh segment {segment_id}: {e}")
                continue

        logger.info(f"Background refresh completed for {len(segment_ids)} segments")

    except Exception as e:
        logger.error(f"Background refresh task failed: {e}")


# ==============================================================================
# Health
# ==============================================================================


@router.get("/health")
async def segmentation_health():
    try:
        segments_collection = get_segments_collection()
        total_segments = await segments_collection.count_documents({})
        active_segments = await segments_collection.count_documents({"is_active": True})

        return {
            "status": "healthy",
            "segmentation_system": "7-type",
            "total_segments": total_segments,
            "active_segments": active_segments,
            "supported_types": [
                "status",
                "lists",
                "dateRange",
                "profileCompleteness",
                "geographic",
                "emailDomain",
                "customFields",
            ],
            "version": "3.0",
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}
