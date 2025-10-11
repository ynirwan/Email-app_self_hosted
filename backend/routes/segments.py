# routes/segments.py - Enhanced segmentation backend with 8 types
from fastapi import APIRouter, HTTPException, Query, Request, status, BackgroundTasks
from database import get_subscribers_collection, get_segments_collection, get_audit_collection
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime, timedelta
import logging
import re

logger = logging.getLogger("uvicorn.error")
router = APIRouter()

# Enhanced Pydantic Models for 8 Segmentation Types
class GeographicCriteria(BaseModel):
    country: Optional[str] = ""
    city: Optional[str] = ""

class SegmentCriteria(BaseModel):
    # 1. 📊 Subscriber Status
    status: Optional[List[str]] = None
    
    # 2. 📋 Lists
    lists: Optional[List[str]] = None
    
    # 3. 📅 Subscription Date
    dateRange: Optional[int] = None  # days
    
    # 4. 👤 Profile Completeness
    profileCompleteness: Optional[Dict[str, bool]] = None
    
    # 5. 🌍 Geographic
    geographic: Optional[GeographicCriteria] = None
    
    # 6. 📈 Engagement Level
    engagement: Optional[List[str]] = None
    
    # 7. 📧 Email Domain
    emailDomain: Optional[List[str]] = None
    
    # 8. 🏷️ Custom Fields
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

# Enhanced Query Builder for 8 Segmentation Types
def build_segment_query(criteria: SegmentCriteria) -> dict:
    """Convert segment criteria to MongoDB query with 8 types of segmentation"""
    query = {}
    
    # 1. 📊 Subscriber Status
    if criteria.status and len(criteria.status) > 0:
        query["status"] = {"$in": criteria.status}
    
    # 2. 📋 Lists
    if criteria.lists and len(criteria.lists) > 0:
        query["list"] = {"$in": criteria.lists}
    
    # 3. 📅 Subscription Date (Time-based)
    if criteria.dateRange:
        cutoff_date = datetime.utcnow() - timedelta(days=criteria.dateRange)
        query["created_at"] = {"$gte": cutoff_date}
    
    # 4. 👤 Profile Completeness
    if criteria.profileCompleteness:
        for field, required in criteria.profileCompleteness.items():
            if required:
                query[f"standard_fields.{field}"] = {"$exists": True, "$ne": ""}
    
    # 5. 🌍 Geographic
    if criteria.geographic:
        if criteria.geographic.country:
            query["custom_fields.country"] = {"$regex": criteria.geographic.country, "$options": "i"}
        if criteria.geographic.city:
            query["custom_fields.city"] = {"$regex": criteria.geographic.city, "$options": "i"}
    
    # 6. 📈 Engagement Level (placeholder - can be enhanced with actual engagement data)
    if criteria.engagement and len(criteria.engagement) > 0:
        # This is a placeholder - you would implement actual engagement tracking
        # For now, we'll map engagement levels to custom fields
        engagement_conditions = []
        for level in criteria.engagement:
            if level == "high":
                engagement_conditions.append({"custom_fields.engagement_score": {"$gte": "8"}})
            elif level == "medium":
                engagement_conditions.append({"custom_fields.engagement_score": {"$gte": "5", "$lt": "8"}})
            elif level == "low":
                engagement_conditions.append({"custom_fields.engagement_score": {"$lt": "5"}})
        
        if engagement_conditions:
            query["$or"] = engagement_conditions
    
    # 7. 📧 Email Domain
    if criteria.emailDomain and len(criteria.emailDomain) > 0:
        domain_conditions = []
        for domain in criteria.emailDomain:
            if domain == "corporate":
                # Exclude common consumer domains for corporate emails
                domain_conditions.append({
                    "email": {
                        "$not": {"$regex": "@(gmail|yahoo|hotmail|outlook|aol)\\.com$", "$options": "i"}
                    }
                })
            else:
                domain_conditions.append({"email": {"$regex": f"@{re.escape(domain)}$", "$options": "i"}})
        
        if domain_conditions:
            if "$or" in query:
                # Combine with existing OR conditions
                query["$and"] = [{"$or": query["$or"]}, {"$or": domain_conditions}]
                del query["$or"]
            else:
                query["$or"] = domain_conditions
    
    # 8. 🏷️ Custom Fields
    # Industry
    if criteria.industry and criteria.industry.strip():
        query["custom_fields.industry"] = {"$regex": criteria.industry, "$options": "i"}
    
    # Company Size
    if criteria.companySize and criteria.companySize.strip():
        query["custom_fields.companySize"] = {"$regex": criteria.companySize, "$options": "i"}
    
    # Additional Custom Fields
    if criteria.customFields:
        for field, value in criteria.customFields.items():
            if value and value.strip():
                query[f"custom_fields.{field}"] = {"$regex": value, "$options": "i"}
    
    return query

# Enhanced audit logging
async def log_segment_activity(
    action: str,
    segment_id: str,
    user_action: str,
    before_data: dict = None,
    after_data: dict = None,
    metadata: dict = None,
    request: Request = None
):
    """Log segment activities for audit trail"""
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
                "ip_address": str(request.client.host) if request and request.client else "unknown",
                "segmentation_types": 8
            },
        }
        await audit_collection.insert_one(log_entry)
        logger.info(f"ENHANCED SEGMENT AUDIT: {action} - {user_action}")
    except Exception as e:
        logger.error(f"Failed to log segment activity: {e}")

# API Endpoints

@router.get("")
async def list_segments(
    active_only: bool = Query(default=True),
    limit: int = Query(default=100, le=500),
    skip: int = Query(default=0, ge=0)
):
    """Get all segments with 8-type segmentation support"""
    try:
        segments_collection = get_segments_collection()
        subscribers_collection = get_subscribers_collection()
        
        query = {}
        if active_only:
            query["is_active"] = True
        
        cursor = segments_collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        segments = []
        
        async for segment in cursor:
            segment["_id"] = str(segment["_id"])
            
            # Update subscriber count if stale
            last_calculated = segment.get("last_calculated")
            if not last_calculated or (datetime.utcnow() - last_calculated) > timedelta(hours=1):
                try:
                    query_filter = build_segment_query(SegmentCriteria(**segment.get("criteria", {})))
                    current_count = await subscribers_collection.count_documents(query_filter)
                    
                    await segments_collection.update_one(
                        {"_id": ObjectId(segment["_id"])},
                        {
                            "$set": {
                                "subscriber_count": current_count,
                                "last_calculated": datetime.utcnow()
                            }
                        }
                    )
                    segment["subscriber_count"] = current_count
                except Exception as e:
                    logger.error(f"Error updating segment count for {segment['name']}: {e}")
                    segment["subscriber_count"] = segment.get("subscriber_count", 0)
            
            segments.append(segment)
        
        total = await segments_collection.count_documents(query)
        
        return {
            "segments": segments,
            "total": total,
            "page": (skip // limit) + 1,
            "total_pages": (total + limit - 1) // limit,
            "segmentation_types": 8
        }
    
    except Exception as e:
        logger.error(f"List segments failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("")
async def create_segment(segment_data: SegmentCreate, request: Request):
    """Create a new segment with 8-type criteria support"""
    try:
        segments_collection = get_segments_collection()
        subscribers_collection = get_subscribers_collection()
        
        # Check if segment name already exists
        existing = await segments_collection.find_one({"name": segment_data.name})
        if existing:
            raise HTTPException(
                status_code=400, 
                detail=f"Segment with name '{segment_data.name}' already exists"
            )
        
        # Build query and count subscribers using enhanced query builder
        query_filter = build_segment_query(segment_data.criteria)
        subscriber_count = await subscribers_collection.count_documents(query_filter)
        
        # Analyze criteria types for metadata
        criteria_types = []
        if segment_data.criteria.status: criteria_types.append("status")
        if segment_data.criteria.lists: criteria_types.append("lists")
        if segment_data.criteria.dateRange: criteria_types.append("dateRange")
        if segment_data.criteria.profileCompleteness: criteria_types.append("profileCompleteness")
        if segment_data.criteria.geographic and (segment_data.criteria.geographic.country or segment_data.criteria.geographic.city):
            criteria_types.append("geographic")
        if segment_data.criteria.engagement: criteria_types.append("engagement")
        if segment_data.criteria.emailDomain: criteria_types.append("emailDomain")
        if segment_data.criteria.industry or segment_data.criteria.companySize or segment_data.criteria.customFields:
            criteria_types.append("customFields")
        
        # Create segment document
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
            "last_calculated": datetime.utcnow()
        }
        
        result = await segments_collection.insert_one(segment_doc)
        segment_id = str(result.inserted_id)
        
        # Log activity with enhanced metadata
        await log_segment_activity(
            action="create",
            segment_id=segment_id,
            user_action=f"Created segment '{segment_data.name}' with {len(criteria_types)} criteria types and {subscriber_count} subscribers",
            after_data=segment_doc,
            metadata={
                "segment_name": segment_data.name,
                "subscriber_count": subscriber_count,
                "criteria_types": criteria_types,
                "criteria_types_count": len(criteria_types)
            },
            request=request
        )
        
        return {
            "message": "Enhanced segment created successfully",
            "segment_id": segment_id,
            "subscriber_count": subscriber_count,
            "criteria_types": criteria_types
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create segment failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{segment_id}")
async def get_segment(segment_id: str):
    """Get a specific segment by ID"""
    try:
        if not ObjectId.is_valid(segment_id):
            raise HTTPException(status_code=400, detail="Invalid segment ID")
        
        segments_collection = get_segments_collection()
        segment = await segments_collection.find_one({"_id": ObjectId(segment_id)})
        
        if not segment:
            raise HTTPException(status_code=404, detail="Segment not found")
        
        segment["_id"] = str(segment["_id"])
        return segment
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get segment failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{segment_id}")
async def update_segment(segment_id: str, segment_data: SegmentUpdate, request: Request):
    """Update an existing segment with 8-type criteria support"""
    try:
        if not ObjectId.is_valid(segment_id):
            raise HTTPException(status_code=400, detail="Invalid segment ID")
        
        segments_collection = get_segments_collection()
        subscribers_collection = get_subscribers_collection()
        
        existing_segment = await segments_collection.find_one({"_id": ObjectId(segment_id)})
        if not existing_segment:
            raise HTTPException(status_code=404, detail="Segment not found")
        
        update_data = {"updated_at": datetime.utcnow()}
        
        if segment_data.name:
            name_conflict = await segments_collection.find_one({
                "name": segment_data.name,
                "_id": {"$ne": ObjectId(segment_id)}
            })
            if name_conflict:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Segment name '{segment_data.name}' already exists"
                )
            update_data["name"] = segment_data.name
        
        if segment_data.description is not None:
            update_data["description"] = segment_data.description
        
        if segment_data.is_active is not None:
            update_data["is_active"] = segment_data.is_active
        
        if segment_data.criteria:
            query_filter = build_segment_query(segment_data.criteria)
            subscriber_count = await subscribers_collection.count_documents(query_filter)
            
            # Analyze updated criteria types
            criteria_types = []
            if segment_data.criteria.status: criteria_types.append("status")
            if segment_data.criteria.lists: criteria_types.append("lists")
            if segment_data.criteria.dateRange: criteria_types.append("dateRange")
            if segment_data.criteria.profileCompleteness: criteria_types.append("profileCompleteness")
            if segment_data.criteria.geographic and (segment_data.criteria.geographic.country or segment_data.criteria.geographic.city):
                criteria_types.append("geographic")
            if segment_data.criteria.engagement: criteria_types.append("engagement")
            if segment_data.criteria.emailDomain: criteria_types.append("emailDomain")
            if segment_data.criteria.industry or segment_data.criteria.companySize or segment_data.criteria.customFields:
                criteria_types.append("customFields")
            
            update_data.update({
                "criteria": segment_data.criteria.dict(),
                "query": query_filter,
                "subscriber_count": subscriber_count,
                "criteria_types": criteria_types,
                "last_calculated": datetime.utcnow()
            })
        
        result = await segments_collection.update_one(
            {"_id": ObjectId(segment_id)},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Segment not found")
        
        # Log activity
        await log_segment_activity(
            action="update",
            segment_id=segment_id,
            user_action=f"Updated segment '{segment_data.name or existing_segment['name']}' with enhanced criteria",
            before_data=existing_segment,
            after_data=update_data,
            metadata={
                "segment_name": segment_data.name or existing_segment["name"],
                "changes": list(update_data.keys()),
                "criteria_types": update_data.get("criteria_types", [])
            },
            request=request
        )
        
        return {
            "message": "Segment updated successfully",
            "criteria_types": update_data.get("criteria_types", [])
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update segment failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{segment_id}")
async def delete_segment(segment_id: str, request: Request):
    """Delete a segment"""
    try:
        if not ObjectId.is_valid(segment_id):
            raise HTTPException(status_code=400, detail="Invalid segment ID")
        
        segments_collection = get_segments_collection()
        
        segment = await segments_collection.find_one({"_id": ObjectId(segment_id)})
        if not segment:
            raise HTTPException(status_code=404, detail="Segment not found")
        
        result = await segments_collection.delete_one({"_id": ObjectId(segment_id)})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Segment not found")
        
        # Log activity
        await log_segment_activity(
            action="delete",
            segment_id=segment_id,
            user_action=f"Deleted segment '{segment['name']}'",
            before_data=segment,
            metadata={
                "segment_name": segment["name"],
                "subscriber_count": segment.get("subscriber_count", 0),
                "criteria_types": segment.get("criteria_types", [])
            },
            request=request
        )
        
        return {"message": "Segment deleted successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete segment failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/preview")
async def preview_segment(preview_data: SegmentPreview):
    """Preview subscribers matching 8-type segment criteria"""
    try:
        subscribers_collection = get_subscribers_collection()
        
        query_filter = build_segment_query(preview_data.criteria)
        
        cursor = subscribers_collection.find(query_filter).limit(preview_data.limit)
        subscribers = []
        
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            doc.setdefault("standard_fields", {})
            doc.setdefault("custom_fields", {})
            subscribers.append(doc)
        
        # Get total count for the preview
        total_count = await subscribers_collection.count_documents(query_filter)
        
        return {
            "subscribers": subscribers,
            "total_matching": total_count,
            "preview_count": len(subscribers),
            "query": query_filter,
            "segmentation_types_used": len([
                k for k, v in preview_data.criteria.dict().items() 
                if v and (isinstance(v, list) and len(v) > 0 or 
                         isinstance(v, dict) and any(v.values()) or
                         isinstance(v, str) and v.strip() or
                         isinstance(v, int) and v)
            ])
        }
    
    except Exception as e:
        logger.error(f"Preview segment failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/count")
async def count_segment_subscribers(count_data: SegmentCount):
    """Get count of subscribers matching 8-type segment criteria"""
    try:
        subscribers_collection = get_subscribers_collection()
        
        query_filter = build_segment_query(count_data.criteria)
        count = await subscribers_collection.count_documents(query_filter)
        
        return {
            "count": count,
            "query": query_filter,
            "criteria_summary": {
                "status": bool(count_data.criteria.status),
                "lists": bool(count_data.criteria.lists),
                "dateRange": bool(count_data.criteria.dateRange),
                "profileCompleteness": bool(count_data.criteria.profileCompleteness),
                "geographic": bool(count_data.criteria.geographic and 
                                 (count_data.criteria.geographic.country or count_data.criteria.geographic.city)),
                "engagement": bool(count_data.criteria.engagement),
                "emailDomain": bool(count_data.criteria.emailDomain),
                "customFields": bool(count_data.criteria.industry or count_data.criteria.companySize or 
                                   count_data.criteria.customFields)
            }
        }
    
    except Exception as e:
        logger.error(f"Count segment failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{segment_id}/refresh")
async def refresh_segment_count(segment_id: str, request: Request):
    """Manually refresh subscriber count for a segment"""
    try:
        if not ObjectId.is_valid(segment_id):
            raise HTTPException(status_code=400, detail="Invalid segment ID")
        
        segments_collection = get_segments_collection()
        subscribers_collection = get_subscribers_collection()
        
        segment = await segments_collection.find_one({"_id": ObjectId(segment_id)})
        if not segment:
            raise HTTPException(status_code=404, detail="Segment not found")
        
        # Recalculate count using enhanced query builder
        query_filter = build_segment_query(SegmentCriteria(**segment["criteria"]))
        new_count = await subscribers_collection.count_documents(query_filter)
        
        # Update segment
        await segments_collection.update_one(
            {"_id": ObjectId(segment_id)},
            {
                "$set": {
                    "subscriber_count": new_count,
                    "last_calculated": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                    "query": query_filter  # Update query in case criteria format changed
                }
            }
        )
        
        # Log activity
        await log_segment_activity(
            action="refresh",
            segment_id=segment_id,
            user_action=f"Refreshed subscriber count for segment '{segment['name']}' with enhanced query - new count: {new_count}",
            metadata={
                "segment_name": segment["name"],
                "old_count": segment.get("subscriber_count", 0),
                "new_count": new_count,
                "criteria_types": segment.get("criteria_types", [])
            },
            request=request
        )
        
        return {
            "message": "Segment count refreshed with enhanced criteria support",
            "new_count": new_count,
            "previous_count": segment.get("subscriber_count", 0),
            "criteria_types": segment.get("criteria_types", [])
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Refresh segment failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{segment_id}/subscribers")
async def get_segment_subscribers(
    segment_id: str,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, le=1000)
):
    """Get paginated subscribers for a specific segment using enhanced querying"""
    try:
        if not ObjectId.is_valid(segment_id):
            raise HTTPException(status_code=400, detail="Invalid segment ID")
        
        segments_collection = get_segments_collection()
        subscribers_collection = get_subscribers_collection()
        
        segment = await segments_collection.find_one({"_id": ObjectId(segment_id)})
        if not segment:
            raise HTTPException(status_code=404, detail="Segment not found")
        
        # Build query using enhanced query builder
        query_filter = build_segment_query(SegmentCriteria(**segment["criteria"]))
        
        # Get paginated subscribers
        skip = (page - 1) * limit
        cursor = subscribers_collection.find(query_filter).skip(skip).limit(limit).sort("created_at", -1)
        
        subscribers = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            doc.setdefault("standard_fields", {})
            doc.setdefault("custom_fields", {})
            subscribers.append(doc)
        
        # Get total count
        total = await subscribers_collection.count_documents(query_filter)
        total_pages = (total + limit - 1) // limit
        
        return {
            "subscribers": subscribers,
            "segment": {
                "name": segment["name"],
                "description": segment["description"],
                "criteria_types": segment.get("criteria_types", [])
            },
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            },
            "query": query_filter
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get segment subscribers failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Bulk operations
@router.post("/bulk-refresh")
async def refresh_all_segments(request: Request, background_tasks: BackgroundTasks):
    """Refresh subscriber counts for all active segments using enhanced querying"""
    try:
        segments_collection = get_segments_collection()
        segments_cursor = segments_collection.find({"is_active": True})
        
        segment_ids = []
        async for segment in segments_cursor:
            segment_ids.append(str(segment["_id"]))
        
        # Add background task to refresh all segments
        background_tasks.add_task(refresh_segments_background_enhanced, segment_ids)
        
        return {
            "message": f"Started enhanced background refresh for {len(segment_ids)} segments",
            "segment_count": len(segment_ids),
            "segmentation_types": 8
        }
    
    except Exception as e:
        logger.error(f"Bulk refresh failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def refresh_segments_background_enhanced(segment_ids: List[str]):
    """Enhanced background task to refresh multiple segments"""
    try:
        segments_collection = get_segments_collection()
        subscribers_collection = get_subscribers_collection()
        
        for segment_id in segment_ids:
            try:
                segment = await segments_collection.find_one({"_id": ObjectId(segment_id)})
                if not segment:
                    continue
                
                # Use enhanced query builder
                query_filter = build_segment_query(SegmentCriteria(**segment["criteria"]))
                new_count = await subscribers_collection.count_documents(query_filter)
                
                await segments_collection.update_one(
                    {"_id": ObjectId(segment_id)},
                    {
                        "$set": {
                            "subscriber_count": new_count,
                            "last_calculated": datetime.utcnow(),
                            "query": query_filter  # Update stored query
                        }
                    }
                )
                
                logger.info(f"Enhanced refresh - Segment {segment['name']}: {new_count} subscribers")
                
            except Exception as e:
                logger.error(f"Failed to refresh segment {segment_id}: {e}")
                continue
        
        logger.info(f"Enhanced background refresh completed for {len(segment_ids)} segments")
        
    except Exception as e:
        logger.error(f"Enhanced background refresh task failed: {e}")

# Health check endpoint
@router.get("/health")
async def segmentation_health():
    """Health check for segmentation system"""
    try:
        segments_collection = get_segments_collection()
        total_segments = await segments_collection.count_documents({})
        active_segments = await segments_collection.count_documents({"is_active": True})
        
        return {
            "status": "healthy",
            "segmentation_system": "8-type enhanced",
            "total_segments": total_segments,
            "active_segments": active_segments,
            "supported_types": [
                "status", "lists", "dateRange", "profileCompleteness", 
                "geographic", "engagement", "emailDomain", "customFields"
            ],
            "version": "2.0"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

