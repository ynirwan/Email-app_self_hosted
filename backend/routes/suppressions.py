# backend/routes/suppressions.py - Complete file with all fixes and business logic applied
from fastapi import APIRouter, HTTPException, Query, Request, status, File, UploadFile, BackgroundTasks
from fastapi.responses import StreamingResponse
from database import get_suppressions_collection, get_audit_collection, get_subscribers_collection, get_campaigns_collection
import pandas as pd
from models.suppression import (
    SuppressionCreate, SuppressionUpdate, SuppressionOut, BulkSuppressionImport,
    SuppressionReason, SuppressionScope, SuppressionSource, BulkSuppressionCheck,
    BulkSuppressionCheckResult, SuppressionCheckResult
)
from typing import List, Dict, Any, Optional
from bson import ObjectId
from datetime import datetime
import logging
import csv
import io
import uuid
from pymongo import UpdateOne
import asyncio
import re

logger = logging.getLogger("uvicorn.error")
router = APIRouter()

# Utility function to convert ObjectIds to strings recursively
def convert_objectids_to_strings(obj):
    """Recursively convert all ObjectId instances to strings in nested data structures"""
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, dict):
        return {key: convert_objectids_to_strings(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_objectids_to_strings(item) for item in obj]
    else:
        return obj

# Enhanced helper functions with business logic
async def email_exists_in_suppressions(email: str) -> bool:
    """Check if email exists in active suppressions"""
    collection = get_suppressions_collection()
    result = await collection.find_one({"email": email, "is_active": True})
    return result is not None

async def is_email_suppressed(email: str, target_lists: List[str] = None) -> Dict[str, Any]:
    """
    Check if an email should be suppressed for given target lists with hierarchy logic
    Returns: {is_suppressed: bool, reason: str, scope: str, suppression_id: str}
    """
    collection = get_suppressions_collection()
    
    # Check global suppressions first (highest priority)
    global_suppression = await collection.find_one({
        "email": email,
        "is_active": True,
        "scope": "global"
    })
    if global_suppression:
        return {
            "is_suppressed": True,
            "reason": global_suppression["reason"],
            "scope": "global",
            "suppression_id": str(global_suppression["_id"]),
            "notes": global_suppression.get("notes", "")
        }
    
    # Check list-specific suppressions only if no global suppression exists
    if target_lists:
        list_suppression = await collection.find_one({
            "email": email,
            "is_active": True,
            "scope": "list_specific",
            "target_lists": {"$in": target_lists}
        })
        if list_suppression:
            return {
                "is_suppressed": True,
                "reason": list_suppression["reason"],
                "scope": "list_specific",
                "suppression_id": str(list_suppression["_id"]),
                "affected_lists": list(set(list_suppression["target_lists"]).intersection(set(target_lists))),
                "notes": list_suppression.get("notes", "")
            }
    
    return {"is_suppressed": False}

async def handle_suppression_hierarchy(email: str, new_reason: str, new_scope: str, new_target_lists: List[str] = None):
    """Handle suppression hierarchy - global overrides list-specific"""
    collection = get_suppressions_collection()
    
    if new_scope == "global":
        # Deactivate any existing list-specific suppressions for this email
        await collection.update_many(
            {
                "email": email,
                "scope": "list_specific",
                "is_active": True
            },
            {
                "$set": {
                    "is_active": False,
                    "updated_at": datetime.utcnow(),
                    "notes": f"Deactivated - superseded by global {new_reason}"
                }
            }
        )
        logger.info(f"Deactivated list-specific suppressions for {email} due to global {new_reason}")
    
    # Check for existing suppression of same type
    existing = await collection.find_one({
        "email": email,
        "reason": new_reason,
        "scope": new_scope
    })
    
    return existing

async def log_suppression_activity(
    action: str,
    entity_id: str,
    user_action: str,
    request: Request = None,
    before_data: dict = None,
    after_data: dict = None,
    metadata: dict = None,
):
    """Log suppression activities using your existing audit system with ObjectId conversion"""
    try:
        audit_collection = get_audit_collection()
        
        # Convert ObjectIds in nested data
        if before_data:
            before_data = convert_objectids_to_strings(before_data)
        if after_data:
            after_data = convert_objectids_to_strings(after_data)
        if metadata:
            metadata = convert_objectids_to_strings(metadata)
            
        log_entry = {
            "timestamp": datetime.utcnow(),
            "action": action,
            "entity_type": "suppression",
            "entity_id": entity_id,
            "user_action": user_action,
            "before_data": before_data or {},
            "after_data": after_data or {},
            "metadata": metadata or {},
        }
        
        # Add IP address if request is available
        if request and request.client:
            log_entry["metadata"]["ip_address"] = str(request.client.host)
            
        await audit_collection.insert_one(log_entry)
        logger.info(f"SUPPRESSION AUDIT: {action} - {user_action}")
    except Exception as e:
        logger.error(f"Failed to log suppression activity: {e}")

# Enhanced bulk suppression checking (optimized for your campaign system)
async def bulk_check_suppressions_optimized(emails: List[str], target_lists: List[str] = None) -> Dict[str, SuppressionCheckResult]:
    """Optimized bulk suppression checking for your batch email sending"""
    collection = get_suppressions_collection()
    results = {}
    if not emails:
        return results

    # Build efficient query for bulk checking with hierarchy
    query = {
        "email": {"$in": emails},
        "is_active": True,
        "$or": [
            {"scope": "global"},
            {"scope": "list_specific", "target_lists": {"$in": target_lists or []}}
        ]
    }

    # Get all suppressions in one query
    suppressions_cursor = collection.find(query)
    suppressions = {}
    async for suppression in suppressions_cursor:
        email = suppression["email"]
        # Global scope takes precedence over list-specific
        if email not in suppressions or suppression["scope"] == "global":
            suppressions[email] = suppression

    # Build results for all emails
    for email in emails:
        if email in suppressions:
            suppression = suppressions[email]
            results[email] = SuppressionCheckResult(
                email=email,
                is_suppressed=True,
                reason=suppression["reason"],
                scope=suppression["scope"],
                suppression_id=str(suppression["_id"]),
                notes=suppression.get("notes", "")
            )
        else:
            results[email] = SuppressionCheckResult(
                email=email,
                is_suppressed=False
            )

    return results

# Subscriber status synchronization function with enhanced logic
async def update_subscriber_suppression_status(email: str, target_lists: List[str], action: str, reason: str = None):
    """Update subscriber status based on suppression changes - synced with your subscribers pattern"""
    try:
        subscribers_collection = get_subscribers_collection()
        
        # Map suppression action to subscriber status
        if action == "suppress":
            if reason == "unsubscribe":
                new_status = "unsubscribed"
            elif reason in ["bounce_hard", "bounce_soft"]:
                new_status = "inactive" 
            elif reason == "complaint":
                new_status = "inactive"
            else:
                new_status = "inactive"  # Default for manual/other suppressions
        else:
            new_status = "active"  # Restore to active when unsuppressed

        # Update subscribers in affected lists
        if target_lists:
            query = {"email": email, "list": {"$in": target_lists}}
        else:
            query = {"email": email}  # Global suppression affects all

        result = await subscribers_collection.update_many(
            query,
            {"$set": {"status": new_status, "updated_at": datetime.utcnow()}}
        )
        
        logger.info(f"Updated {result.modified_count} subscribers for {email} to status {new_status}")
        
    except Exception as e:
        logger.error(f"Failed to update subscriber suppression status: {e}")

# API Endpoints - Enhanced with all fixes and business logic
@router.get("/stats")
async def get_suppression_stats():
    """Get suppression statistics for dashboard"""
    try:
        collection = get_suppressions_collection()
        
        pipeline = [
            {
                "$facet": {
                    "total": [{"$match": {"is_active": True}}, {"$count": "count"}],
                    "by_scope": [
                        {"$match": {"is_active": True}},
                        {"$group": {"_id": "$scope", "count": {"$sum": 1}}}
                    ],
                    "by_reason": [
                        {"$match": {"is_active": True}},
                        {"$group": {"_id": "$reason", "count": {"$sum": 1}}}
                    ]
                }
            }
        ]
        
        cursor = collection.aggregate(pipeline)
        result = await cursor.to_list(1)
        
        if result:
            data = result[0]
            
            # Format response for frontend
            stats = {
                "total": data["total"][0]["count"] if data["total"] else 0,
                "global": 0,
                "listSpecific": 0,
                "byReason": {}
            }
            
            # Process scope statistics
            for scope_stat in data["by_scope"]:
                if scope_stat["_id"] == "global":
                    stats["global"] = scope_stat["count"]
                elif scope_stat["_id"] == "list_specific":
                    stats["listSpecific"] = scope_stat["count"]
            
            # Process reason statistics
            for reason_stat in data["by_reason"]:
                stats["byReason"][reason_stat["_id"]] = reason_stat["count"]
            
            return stats
        
        # Return empty stats if no data
        return {
            "total": 0,
            "global": 0, 
            "listSpecific": 0,
            "byReason": {}
        }
        
    except Exception as e:
        logger.error(f"Error fetching suppression stats: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch stats: {str(e)}")


@router.get("/export")
async def export_suppressions(
    reason: Optional[SuppressionReason] = Query(None),
    scope: Optional[SuppressionScope] = Query(None),
    is_active: Optional[bool] = Query(True)
):
    """Export suppressions to CSV"""
    try:
        collection = get_suppressions_collection()
        filter_query = {}
        if reason:
            filter_query["reason"] = reason
        if scope:
            filter_query["scope"] = scope
        if is_active is not None:
            filter_query["is_active"] = is_active

        cursor = collection.find(filter_query).sort("created_at", -1)

        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(['email', 'reason', 'scope', 'target_lists', 'notes', 'created_at', 'is_active', 'source'])

        # Write data
        async for suppression in cursor:
            target_lists_str = ','.join(suppression.get('target_lists', []))
            writer.writerow([
                suppression['email'],
                suppression['reason'],
                suppression['scope'],
                target_lists_str,
                suppression.get('notes', ''),
                suppression['created_at'].isoformat(),
                suppression.get('is_active', True),
                suppression.get('source', 'unknown')
            ])

        output.seek(0)
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode('utf-8')),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=suppressions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
        )

    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=SuppressionOut)
async def create_suppression(suppression: SuppressionCreate, request: Request):
    """Create a new suppression entry with hierarchy handling and subscriber sync"""
    try:
        collection = get_suppressions_collection()
        
        # Handle hierarchy conflicts
        existing = await handle_suppression_hierarchy(
            suppression.email, 
            suppression.reason, 
            suppression.scope,
            suppression.target_lists
        )
        
        if existing:
            if existing.get("is_active"):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Active suppression already exists for {suppression.email}"
                )
            else:
                # Reactivate existing suppression
                await collection.update_one(
                    {"_id": existing["_id"]},
                    {
                        "$set": {
                            "is_active": True,
                            "updated_at": datetime.utcnow(),
                            "notes": f"Reactivated: {suppression.notes}",
                            "source": suppression.source,
                            "target_lists": suppression.target_lists
                        }
                    }
                )
                
                # Update subscriber status
                await update_subscriber_suppression_status(
                    suppression.email,
                    suppression.target_lists,
                    "suppress",
                    suppression.reason
                )
                
                # Get the updated record
                updated = await collection.find_one({"_id": existing["_id"]})
                updated = convert_objectids_to_strings(updated)
                
                await log_suppression_activity(
                    action="reactivate",
                    entity_id=str(existing["_id"]),
                    user_action=f"Reactivated suppression for {suppression.email}",
                    request=request,
                    before_data=existing,
                    after_data=updated
                )
                
                return SuppressionOut(**updated)

        # Build suppression document for new suppression
        suppression_doc = {
            "email": suppression.email,
            "reason": suppression.reason,
            "scope": suppression.scope,
            "target_lists": suppression.target_lists or [],
            "notes": suppression.notes or "",
            "source": suppression.source,
            "is_active": True,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "created_by": "api"
        }

        # Add optional fields if provided
        if suppression.campaign_id:
            suppression_doc["campaign_id"] = ObjectId(suppression.campaign_id)
        if suppression.subscriber_id:
            suppression_doc["subscriber_id"] = ObjectId(suppression.subscriber_id)

        result = await collection.insert_one(suppression_doc)
        suppression_doc["_id"] = result.inserted_id

        # Update subscriber status - SYNC WITH SUBSCRIBERS
        await update_subscriber_suppression_status(
            suppression.email,
            suppression.target_lists,
            "suppress",
            suppression.reason
        )

        # Log activity using your existing audit system
        await log_suppression_activity(
            action="create",
            entity_id=str(result.inserted_id),
            user_action=f"Created suppression for {suppression.email} - reason: {suppression.reason}",
            request=request,
            after_data=suppression_doc,
            metadata={
                "source": suppression.source,
                "campaign_id": suppression.campaign_id,
                "subscriber_id": suppression.subscriber_id
            }
        )

        # 🔥 FIX: Convert ObjectId to string before returning
        suppression_doc = convert_objectids_to_strings(suppression_doc)

        return SuppressionOut(**suppression_doc)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating suppression: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create suppression"
        )

@router.get("/", response_model=List[SuppressionOut])
async def list_suppressions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    email: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    reason: Optional[SuppressionReason] = Query(None),
    scope: Optional[SuppressionScope] = Query(None),
    source: Optional[SuppressionSource] = Query(None),
    is_active: Optional[bool] = Query(True),
    list_name: Optional[str] = Query(None)
):
    """List suppressions with filtering and search (matches your subscriber search pattern)"""
    collection = get_suppressions_collection()
    filter_query = {}
    
    # Search functionality (similar to your subscriber search)
    if search and search.strip():
        search_term = search.strip()
        if "@" in search_term:  # Email search
            filter_query["email"] = {"$regex": f"^{re.escape(search_term)}", "$options": "i"}
        else:  # General search
            filter_query["$or"] = [
                {"email": {"$regex": search_term, "$options": "i"}},
                {"notes": {"$regex": search_term, "$options": "i"}},
                {"reason": {"$regex": search_term, "$options": "i"}}
            ]
    elif email:
        filter_query["email"] = {"$regex": email, "$options": "i"}

    # Other filters
    if reason:
        filter_query["reason"] = reason
    if scope:
        filter_query["scope"] = scope
    if source:
        filter_query["source"] = source
    if is_active is not None:
        filter_query["is_active"] = is_active
    if list_name:
        filter_query["target_lists"] = {"$in": [list_name]}

    cursor = collection.find(filter_query).skip(skip).limit(limit).sort("created_at", -1)
    suppressions = await cursor.to_list(length=limit)

    # 🔥 FIX: Convert ObjectIds to strings for all suppressions
    suppressions = convert_objectids_to_strings(suppressions)

    return [SuppressionOut(**suppression) for suppression in suppressions]

# Enhanced check endpoints for your campaign system
@router.post("/check")
async def check_suppression(email: str, target_lists: Optional[List[str]] = None):
    """Check if an email is suppressed with hierarchy logic"""
    result = await is_email_suppressed(email, target_lists)
    return result

@router.post("/import")
async def import_suppressions(
    request: Request,
    file: UploadFile = File(...)
):
    """Import suppressions from CSV with validation and audit logging"""
    try:
        content = await file.read()
        df = pd.read_csv(io.BytesIO(content))
        
        # Validation
        if 'email' not in df.columns:
            raise HTTPException(status_code=400, detail="CSV must contain an 'email' column")
            
        collection = get_suppressions_collection()
        operations = []
        for _, row in df.iterrows():
            email = str(row['email']).strip().lower()
            if not email: continue
            
            suppression_doc = {
                "email": email,
                "reason": row.get('reason', 'import'),
                "scope": row.get('scope', 'global'),
                "target_lists": str(row.get('target_lists', '')).split(',') if row.get('target_lists') else [],
                "notes": row.get('notes', 'Bulk import'),
                "source": "bulk_import",
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            operations.append(UpdateOne({"email": email}, {"$set": suppression_doc}, upsert=True))
            
        if operations:
            await collection.bulk_write(operations)
        
        # Log successful import
        await log_suppression_activity(
            action="import",
            entity_id="bulk",
            user_action=f"Imported {len(df)} suppressions from CSV",
            request=request,
            metadata={"filename": file.filename, "count": len(df)}
        )
        
        return {"imported": len(df)}
    except Exception as e:
        logger.error(f"Import failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/bulk-check", response_model=BulkSuppressionCheckResult)
async def bulk_check_suppressions(check_request: BulkSuppressionCheck, request: Request):
    """Optimized bulk suppression check for your campaign system"""
    results = await bulk_check_suppressions_optimized(
        check_request.emails,
        check_request.target_lists
    )
    
    # Audit log bulk check
    await log_suppression_activity(
        action="bulk_check",
        entity_id="bulk",
        user_action=f"Performed bulk suppression check for {len(check_request.emails)} emails",
        request=request,
        metadata={"count": len(check_request.emails), "suppressed_count": sum(1 for r in results.values() if r.is_suppressed)}
    )
    
    return BulkSuppressionCheckResult(
        total_checked=len(check_request.emails),
        suppressed_count=sum(1 for r in results.values() if r.is_suppressed),
        results=results
    )

# Enhanced synchronization endpoints with proper duplicate handling
@router.post("/sync-from-subscribers")
async def create_suppressions_from_subscribers():
    """Create suppressions from existing subscriber data - FIXED for duplicates and hierarchy"""
    try:
        collection = get_suppressions_collection()
        subscribers_collection = get_subscribers_collection()
        
        # Find subscribers with problematic statuses (adjusted for your schema)
        problem_subscribers = subscribers_collection.find({
            "$or": [
                {"status": "inactive"},
                {"status": "unsubscribed"},
            ]
        })

        processed_count = 0
        created_count = 0
        updated_count = 0
        skipped_count = 0
        
        async for subscriber in problem_subscribers:
            email = subscriber["email"]
            
            # Map subscriber status to suppression details
            if subscriber.get("status") == "unsubscribed":
                reason = "unsubscribe"
                scope = "global"
                target_lists = []
            elif subscriber.get("status") == "inactive":
                reason = "manual"  # Could be bounce_hard if you track that
                scope = "list_specific"
                target_lists = [subscriber.get("list")] if subscriber.get("list") else []
            else:
                skipped_count += 1
                continue

            processed_count += 1

            # Handle hierarchy - check for existing suppressions
            existing = await handle_suppression_hierarchy(email, reason, scope, target_lists)
            
            if existing:
                if not existing.get("is_active", False):
                    # Reactivate existing suppression
                    await collection.update_one(
                        {"_id": existing["_id"]},
                        {
                            "$set": {
                                "is_active": True,
                                "updated_at": datetime.utcnow(),
                                "notes": f"Reactivated from subscriber status: {subscriber.get('status')}",
                                "source": "system"
                            }
                        }
                    )
                    updated_count += 1
                else:
                    # Already active, skip
                    skipped_count += 1
                continue
            
            # Create new suppression only if none exists
            suppression_doc = {
                "email": email,
                "reason": reason,
                "scope": scope,
                "target_lists": target_lists,
                "notes": f"Auto-created from subscriber status: {subscriber.get('status')}",
                "source": "system",
                "subscriber_id": str(subscriber["_id"]) if subscriber.get("_id") else None,
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "created_by": "system_sync"
            }
            
            await collection.insert_one(suppression_doc)
            created_count += 1

        return {
            "message": f"Sync completed: {created_count} created, {updated_count} updated, {skipped_count} skipped",
            "processed_subscribers": processed_count,
            "new_suppressions": created_count,
            "updated_suppressions": updated_count,
            "skipped_suppressions": skipped_count
        }
        
    except Exception as e:
        logger.error(f"Sync from subscribers failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sync-with-subscribers")
async def sync_suppressions_with_subscribers():
    """Bulk sync suppression status with subscriber status using proper hierarchy"""
    try:
        suppressions_collection = get_suppressions_collection()
        subscribers_collection = get_subscribers_collection()
        
        # Find active suppressions
        cursor = suppressions_collection.find({"is_active": True})
        
        sync_count = 0
        operations = []  # Use bulk operations like your subscribers pattern
        
        async for suppression in cursor:
            email = suppression["email"]
            target_lists = suppression.get("target_lists", [])
            reason = suppression["reason"]
            
            # Determine appropriate subscriber status based on suppression reason
            if reason == "unsubscribe":
                new_status = "unsubscribed"
            elif reason in ["bounce_hard", "bounce_soft"]:
                new_status = "inactive"
            elif reason == "complaint":
                new_status = "inactive"
            else:
                new_status = "inactive"  # Default for manual/other
            
            # Build query for affected subscribers with hierarchy respect
            if suppression["scope"] == "global":
                query = {"email": email}  # Global affects all lists
            elif target_lists:
                query = {"email": email, "list": {"$in": target_lists}}
            else:
                continue  # Skip invalid list-specific suppressions
            
            # Add to bulk operations
            operations.append(
                UpdateOne(
                    query,
                    {"$set": {"status": new_status, "updated_at": datetime.utcnow()}},
                    upsert=False
                )
            )
            
            sync_count += 1
            
            # Process in chunks (same pattern as your bulk upload)
            if len(operations) >= 1000:
                if operations:
                    await subscribers_collection.bulk_write(operations, ordered=False)
                operations = []
        
        # Process remaining operations
        if operations:
            await subscribers_collection.bulk_write(operations, ordered=False)
        
        return {
            "message": f"Synchronized {sync_count} suppressions with subscriber statuses",
            "synced_count": sync_count
        }
        
    except Exception as e:
        logger.error(f"Bulk sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status-inconsistencies")
async def check_status_inconsistencies():
    """Find subscribers and suppressions with inconsistent statuses"""
    try:
        subscribers_collection = get_subscribers_collection()
        suppressions_collection = get_suppressions_collection()
        
        # Find active subscribers who should be suppressed
        pipeline = [
            {
                "$lookup": {
                    "from": "suppressions",
                    "localField": "email",
                    "foreignField": "email",
                    "as": "suppressions"
                }
            },
            {
                "$match": {
                    "status": "active",
                    "suppressions": {
                        "$elemMatch": {
                            "is_active": True
                        }
                    }
                }
            },
            {
                "$project": {
                    "email": 1,
                    "list": 1,
                    "status": 1,
                    "suppression_count": {"$size": "$suppressions"}
                }
            },
            {"$limit": 100}  # Limit for performance
        ]
        
        cursor = subscribers_collection.aggregate(pipeline)
        inconsistencies = await cursor.to_list(100)
        
        # Convert ObjectIds in results
        inconsistencies = convert_objectids_to_strings(inconsistencies)
        
        return {
            "inconsistent_records": len(inconsistencies),
            "records": inconsistencies
        }
        
    except Exception as e:
        logger.error(f"Consistency check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Import/Export endpoints with ObjectId handling
@router.post("/import")
async def import_suppressions(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    default_reason: SuppressionReason = SuppressionReason.IMPORT,
    default_scope: SuppressionScope = SuppressionScope.GLOBAL
):
    """Import suppressions from CSV file with hierarchy handling"""
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are supported"
        )
    
    try:
        content = await file.read()
        csv_data = content.decode('utf-8')
        
        # Parse CSV
        reader = csv.DictReader(io.StringIO(csv_data))
        suppressions = []
        for row in reader:
            if 'email' not in row or not row['email'].strip():
                continue
                
            suppression_data = {
                "email": row['email'].strip().lower(),
                "reason": row.get('reason', default_reason),
                "scope": row.get('scope', default_scope),
                "notes": row.get('notes', ''),
                "target_lists": [l.strip() for l in row.get('target_lists', '').split(',') if l.strip()] or []
            }
            suppressions.append(suppression_data)

        if not suppressions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid suppression records found in CSV"
            )

        # Process import using your existing background job pattern
        job_id = str(uuid.uuid4())
        background_tasks.add_task(
            process_suppression_import_background,
            job_id,
            suppressions,
            default_reason,
            default_scope
        )

        return {
            "message": "Import started",
            "job_id": job_id,
            "total_records": len(suppressions)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Suppression import failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

async def process_suppression_import_background(
    job_id: str,
    suppressions: List[Dict],
    default_reason: str,
    default_scope: str
):
    """Background processing for suppression import with hierarchy handling"""
    try:
        collection = get_suppressions_collection()
        
        # Process in chunks to avoid memory issues
        CHUNK_SIZE = 1000
        processed_count = 0
        
        for i in range(0, len(suppressions), CHUNK_SIZE):
            chunk = suppressions[i:i + CHUNK_SIZE]
            
            # Process each suppression with hierarchy handling
            for suppression_data in chunk:
                email = suppression_data["email"]
                reason = suppression_data.get("reason", default_reason)
                scope = suppression_data.get("scope", default_scope)
                target_lists = suppression_data.get("target_lists", [])
                
                # Handle hierarchy for this suppression
                existing = await handle_suppression_hierarchy(email, reason, scope, target_lists)
                
                if existing and existing.get("is_active"):
                    # Skip if already active
                    continue
                elif existing:
                    # Reactivate existing
                    await collection.update_one(
                        {"_id": existing["_id"]},
                        {
                            "$set": {
                                "is_active": True,
                                "updated_at": datetime.utcnow(),
                                "notes": f"Reactivated from import: {suppression_data.get('notes', '')}",
                                "source": "bulk_import"
                            }
                        }
                    )
                else:
                    # Create new suppression
                    doc = {
                        "email": email,
                        "reason": reason,
                        "scope": scope,
                        "target_lists": target_lists,
                        "notes": suppression_data.get("notes", ""),
                        "source": "bulk_import",
                        "is_active": True,
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                        "created_by": "import"
                    }
                    await collection.insert_one(doc)

                processed_count += 1

            # Small delay to prevent overwhelming the database
            await asyncio.sleep(0.1)

        logger.info(f"Suppression import job {job_id} completed: {processed_count} processed")
        
    except Exception as e:
        logger.error(f"Suppression import job {job_id} failed: {e}")


# Database cleanup endpoints
@router.post("/cleanup-duplicates")
async def cleanup_duplicate_suppressions():
    """Clean up duplicate suppressions maintaining proper hierarchy"""
    try:
        collection = get_suppressions_collection()
        
        # Find duplicates
        pipeline = [
            {
                "$group": {
                    "_id": {"email": "$email", "reason": "$reason", "scope": "$scope"},
                    "docs": {"$push": "$$ROOT"},
                    "count": {"$sum": 1}
                }
            },
            {"$match": {"count": {"$gt": 1}}}
        ]
        
        duplicates = await collection.aggregate(pipeline).to_list(None)
        cleaned_count = 0
        
        for group in duplicates:
            docs = group["docs"]
            # Sort by created_at desc, prefer active over inactive
            docs.sort(key=lambda x: (x.get("is_active", False), x["created_at"]), reverse=True)
            
            # Keep the first (most recent active or most recent inactive)
            keep_doc = docs[0]
            
            # Remove others
            for doc in docs[1:]:
                await collection.delete_one({"_id": doc["_id"]})
                cleaned_count += 1
                logger.info(f"Removed duplicate suppression: {doc['email']} - {doc['reason']}")
        
        return {
            "message": f"Cleaned up {cleaned_count} duplicate suppressions",
            "cleaned_count": cleaned_count
        }
        
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{suppression_id}", response_model=SuppressionOut)
async def get_suppression(suppression_id: str):
    """Get a specific suppression by ID"""
    if not ObjectId.is_valid(suppression_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid suppression ID")

    collection = get_suppressions_collection()
    suppression = await collection.find_one({"_id": ObjectId(suppression_id)})

    if not suppression:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suppression not found")

    # 🔥 FIX: Convert ObjectIds to strings
    suppression = convert_objectids_to_strings(suppression)

    return SuppressionOut(**suppression)

@router.put("/{suppression_id}", response_model=SuppressionOut)
async def update_suppression(suppression_id: str, update_data: SuppressionUpdate, request: Request):
    """Update a suppression entry with hierarchy handling"""
    if not ObjectId.is_valid(suppression_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid suppression ID")

    collection = get_suppressions_collection()

    # Get current suppression for audit log
    current = await collection.find_one({"_id": ObjectId(suppression_id)})
    if not current:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suppression not found")

    # Handle hierarchy if scope or reason changes
    if update_data.scope or update_data.reason:
        new_scope = update_data.scope or current["scope"]
        new_reason = update_data.reason or current["reason"]
        await handle_suppression_hierarchy(
            current["email"],
            new_reason,
            new_scope,
            update_data.target_lists
        )

    update_doc = {k: v for k, v in update_data.dict().items() if v is not None}
    update_doc["updated_at"] = datetime.utcnow()

    result = await collection.find_one_and_update(
        {"_id": ObjectId(suppression_id)},
        {"$set": update_doc},
        return_document=True
    )

    # Update subscriber status if scope or reason changed
    if update_data.scope or update_data.reason:
        await update_subscriber_suppression_status(
            current["email"],
            update_data.target_lists or current.get("target_lists", []),
            "suppress",
            update_data.reason or current["reason"]
        )

    # Log activity
    await log_suppression_activity(
        action="update",
        entity_id=suppression_id,
        user_action=f"Updated suppression for {current['email']}",
        request=request,
        before_data=current,
        after_data=update_doc
    )

    # 🔥 FIX: Convert ObjectIds to strings
    result = convert_objectids_to_strings(result)

    return SuppressionOut(**result)

@router.delete("/{suppression_id}")
async def delete_suppression(suppression_id: str, request: Request):
    """Soft delete a suppression entry with subscriber sync"""
    if not ObjectId.is_valid(suppression_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid suppression ID")

    collection = get_suppressions_collection()

    # Get current for logging
    current = await collection.find_one({"_id": ObjectId(suppression_id)})
    if not current:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Suppression not found")

    result = await collection.find_one_and_update(
        {"_id": ObjectId(suppression_id)},
        {"$set": {"is_active": False, "updated_at": datetime.utcnow()}},
        return_document=True
    )

    # Update subscriber status back to active if needed - SYNC WITH SUBSCRIBERS
    await update_subscriber_suppression_status(
        current["email"],
        current.get("target_lists", []),
        "unsuppress"
    )

    # Log activity
    await log_suppression_activity(
        action="delete",
        entity_id=suppression_id,
        user_action=f"Deleted suppression for {current['email']}",
        request=request,
        before_data=current
    )

    return {"message": "Suppression deleted successfully"}

