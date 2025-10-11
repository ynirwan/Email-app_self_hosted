# routes/subscribers.py - Complete file with all required endpoints
from fastapi import APIRouter, HTTPException, Query, Request, status, File, Form, UploadFile, BackgroundTasks
from database import get_subscribers_collection, get_audit_collection  # ✅ Use standardized AsyncIOMotorClient
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, EmailStr
from bson import ObjectId
from datetime import datetime
import logging
from fastapi.responses import StreamingResponse
import csv
import io
import re
from schemas.subscriber_schema import SubscriberIn, BulkPayload, SubscriberOut



logger = logging.getLogger("uvicorn.error")
router = APIRouter()


@router.get("/lists")
async def get_subscriber_lists():
    try:
        subscribers_collection = get_subscribers_collection()

        pipeline = [
            {
                "$group": {
                    "_id": "$list",
                    "count": {"$sum": 1},
                    "active_count": {
                        "$sum": {"$cond": [{"$eq": ["$status", "active"]}, 1, 0]}
                    },
                    "last_updated": {"$max": "$updated_at"}
                }
            },
            {"$sort": {"last_updated": -1}}
        ]

        cursor = subscribers_collection.aggregate(pipeline)
        lists = await cursor.to_list(length=None)


        return lists
    except Exception as e:
        logger.error(f"Get subscriber lists failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ✅ Required route: POST /subscribers/bulk
@router.post("/bulk")
async def bulk_upload_subscribers(payload: BulkPayload, request: Request, background_tasks: BackgroundTasks):
    try:
        subscribers_collection = get_subscribers_collection()
        if not payload.subscribers:
            raise HTTPException(status_code=400, detail="No subscribers provided")

        # Process in background for large uploads
        if len(payload.subscribers) > 100:
            background_tasks.add_task(
                process_bulk_subscribers,
                subscribers_collection,
                payload,
                request,
            )
            return {"message": f"Processing {len(payload.subscribers)} subscribers in background"}
        else:
            # Process small batches immediately
            result = await process_bulk_subscribers(subscribers_collection, payload, request)
            return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def process_bulk_subscribers(subscribers_collection, payload: BulkPayload, request: Request):
    try:
        new_docs = []
        skipped = []
        for sub in payload.subscribers:
            email = sub.email.strip().lower()
            existing = await subscribers_collection.find_one(
                {"email": email, "list": payload.list}  # Use payload.list not payload.list_name
            )
            if existing:
                skipped.append({"email": email, "reason": "Already exists"})
                continue

            # --- split fields into universal / standard / custom ---
            standard_fields = sub.standard_fields or {}
            custom_fields = sub.custom_fields or {}

            doc = {
                "list": payload.list,
                "email": email,
                "status": sub.status or "active",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "standard_fields": standard_fields,
                "custom_fields": custom_fields,
            }

            new_docs.append(doc)

        if not new_docs:
            await log_activity(
                action="upload",
                entity_type="bulk_upload",
                entity_id=payload.list,
                user_action=(
                    f"Attempted bulk upload to list '{payload.list}' - "
                    f"all {len(payload.subscribers)} subscribers were duplicates"
                ),
                metadata={
                    "ip_address": str(request.client.host)
                    if request.client
                    else "unknown",
                    "list_name": payload.list,
                    "attempted_count": len(payload.subscribers),
                    "inserted_count": 0,
                    "skipped_count": len(skipped),
                },
            )
            return {
                "inserted": 0,
                "skipped": len(skipped),
                "message": "No new subscribers added - all were duplicates",
            }

        result = await subscribers_collection.insert_many(new_docs)

        await log_activity(
            action="upload",
            entity_type="bulk_upload",
            entity_id=payload.list,
            user_action=(
                f"Bulk uploaded {len(result.inserted_ids)} subscribers "
                f"to list '{payload.list}'"
            ),
            after_data={
                "sample_emails": [doc.get("email") for doc in new_docs[:5]],
                "total_count": len(result.inserted_ids),
            },
            metadata={
                "ip_address": str(request.client.host)
                if request.client
                else "unknown",
                "list_name": payload.list,
                "inserted_count": len(result.inserted_ids),
                "skipped_count": len(skipped),
                "attempted_count": len(payload.subscribers),
            },
        )

        logger.info(
            f"Bulk upload completed: {len(result.inserted_ids)} subscribers added"
        )

        return {"inserted": len(result.inserted_ids), "skipped": len(skipped)}

    except Exception as e:
        logger.error(f"Bulk processing failed: {e}")
        raise HTTPException(status_code=500, detail="Bulk upload failed")

# Add this missing function
async def get_estimated_count(collection, query, max_limit=None):
    """Get estimated count with performance optimization"""
    try:
        # For simple queries, use count_documents with limit
        if not max_limit or max_limit > 10000:
            # Use sampling for large datasets
            sample_size = min(1000, max_limit or 1000)
            pipeline = [
                {"$match": query},
                {"$limit": sample_size},
                {"$count": "count"}
            ]
            
            cursor = collection.aggregate(pipeline)
            result = await cursor.to_list(length=1)
            if result:
                # Estimate based on sample
                estimated = result[0]["count"] * (max_limit or 100000) // sample_size
                return min(estimated, max_limit or estimated)
            return 0
        else:
            # For smaller limits, use accurate count
            return await collection.count_documents(query, limit=max_limit)
    except Exception as e:
        logger.error(f"Count estimation failed: {e}")
        return 0



@router.get("/search")
async def get_subscribers(
    list_name: str = None,
    search: str = None,
    page: int = 1,
    limit: int = 50,
    search_mode: str = "smart"  # "smart", "exact", "paginated"
):
    try:
        subscribers_collection = get_subscribers_collection()
        
        # Determine search strategy
        is_search_query = search and search.strip()
        search_term = search.strip() if is_search_query else ""
        
        # Analyze search term specificity
        search_specificity = analyze_search_specificity(search_term) if is_search_query else "none"
        
        # Set limits based on search type and dataset size
        if is_search_query:
            if search_specificity == "exact":
                # Email or ID searches - very specific, limit to 100
                effective_limit = 100
                max_results = 100
            elif search_specificity == "specific":
                # Specific searches (long terms) - limit to 1000
                effective_limit = min(limit, 1000)
                max_results = 5000
            elif search_specificity == "general":
                # General searches (short terms) - use pagination
                effective_limit = min(limit, 500)
                max_results = 50000  # Allow pagination up to 50k
            else:
                # Very broad searches - force pagination
                effective_limit = min(limit, 200)
                max_results = 10000
        else:
            # Default browsing mode
            effective_limit = min(limit, 1000)
            max_results = None  # No limit for browsing
        
        # Build optimized query
        query = {}
        sort_order = [("_id", 1)]  # Default sort
        
        if list_name:
            query["list"] = list_name
        
        if is_search_query:
            query, sort_order = build_optimized_search_query(search_term, search_specificity)
            if list_name:
                query["list"] = list_name
        
        # Execute query with smart pagination
        skip = (page - 1) * effective_limit
        
        # For very specific searches, don't use skip (get all results)
        if is_search_query and search_specificity == "exact":
            skip = 0
        
        cursor = subscribers_collection.find(query).sort(sort_order).skip(skip).limit(effective_limit)
        subscribers = await cursor.to_list(length=effective_limit)
        
        # Process results
        for sub in subscribers:
            sub["_id"] = str(sub["_id"])
            sub.setdefault("standard_fields", {})
            sub.setdefault("custom_fields", {})
        
        # Smart count calculation
        if is_search_query:
            if search_specificity == "exact":
                total_count = len(subscribers)
                has_more = False
            else:
                # Use estimated count for performance on large datasets
                total_count = await get_estimated_count(subscribers_collection, query, max_results)
                has_more = total_count > (page * effective_limit) and total_count < max_results
        else:
            # For browsing, use estimated count
            total_count = await subscribers_collection.estimated_document_count()
            has_more = skip + len(subscribers) < total_count
        
        pages = (min(total_count, max_results or total_count) + effective_limit - 1) // effective_limit
        
        return {
            "subscribers": subscribers,
            "pagination": {
                "page": page,
                "limit": effective_limit,
                "total": min(total_count, max_results or total_count),
                "pages": pages,
                "has_more": has_more,
                "is_search": is_search_query,
                "search_specificity": search_specificity
            },
            "performance": {
                "result_count": len(subscribers),
               # "query_time": "< 100ms",  # Add actual timing if needed
                "strategy": search_specificity if is_search_query else "browse"
            }
        }
        
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def analyze_search_specificity(search_term: str) -> str:
    """Analyze search term to determine query strategy"""
    if not search_term:
        return "none"

    # Email pattern
    if "@" in search_term and "." in search_term:
        return "exact"

    # ObjectId pattern
    if len(search_term) == 24 and all(c in '0123456789abcdef' for c in search_term.lower()):
        return "exact"

    # Phone number pattern
    if len(search_term) >= 10 and search_term.replace("+", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "").isdigit():
        return "exact"

    # Long specific terms
    if len(search_term) >= 8:
        return "specific"

    # Medium terms
    if len(search_term) >= 4:
        return "general"

    # Very short terms
    return "broad"


def build_optimized_search_query(search_term: str, specificity: str):
    """Build optimized MongoDB query based on search specificity"""
    query = {}
    sort_order = [("_id", 1)]

    if specificity == "exact":
        # Exact searches - use precise matching
        conditions = []

        if "@" in search_term:
            # Email search - use exact match first, then regex
            conditions.extend([
                {"email": search_term.lower()},
                {"email": {"$regex": f"^{re.escape(search_term)}", "$options": "i"}}
            ])
            sort_order = [("email", 1), ("_id", 1)]

        elif len(search_term) == 24:
            # Potential ObjectId
            try:
                from bson import ObjectId
                conditions.append({"_id": ObjectId(search_term)})
            except:
                conditions.append({"email": {"$regex": search_term, "$options": "i"}})

        query["$or"] = conditions

    elif specificity == "specific":
        # Specific searches - focused field search
        query["$or"] = [
            {"email": {"$regex": search_term, "$options": "i"}},
            {"standard_fields.first_name": {"$regex": search_term, "$options": "i"}},
            {"standard_fields.last_name": {"$regex": search_term, "$options": "i"}},
        ]
        sort_order = [("email", 1), ("standard_fields.first_name", 1)]

    else:
        # General/broad searches - comprehensive but limited
        query["$or"] = [
            {"email": {"$regex": search_term, "$options": "i"}},
            {"standard_fields.first_name": {"$regex": search_term, "$options": "i"}},
            {"standard_fields.last_name": {"$regex": search_term, "$options": "i"}},
            {"list": {"$regex": search_term, "$options": "i"}},
            {"custom_fields.company": {"$regex": search_term, "$options": "i"}},
            {"custom_fields.city": {"$regex": search_term, "$options": "i"}},
        ]
        sort_order = [("email", 1)]

    return query, sort_order

@router.get("/list/{list_name}")
async def get_subscribers_by_list(list_name: str):
    try:
        subscribers_collection = get_subscribers_collection()
        cursor = subscribers_collection.find({"list": list_name}).limit(100)

        results = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            doc.setdefault("standard_fields", {})
            doc.setdefault("custom_fields", {})
            results.append(doc)

        return results
    except Exception as e:
        logger.error(f"Get subscribers by list failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@router.delete("/{subscriber_id}")
async def delete_subscriber(subscriber_id: str, request: Request):
    try:
        subscribers_collection = get_subscribers_collection()

        if not ObjectId.is_valid(subscriber_id):
            raise HTTPException(status_code=400, detail="Invalid subscriber ID")

        subscriber = await subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not subscriber:
            raise HTTPException(status_code=404, detail="Subscriber not found")

        result = await subscribers_collection.delete_one({"_id": ObjectId(subscriber_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Subscriber not found")

        await log_activity(
            action="delete",
            entity_type="subscriber",
            entity_id=subscriber_id,
            user_action=f"Deleted subscriber {subscriber.get('email')} from list '{subscriber.get('list')}'",
            before_data={
                "email": subscriber.get("email"),
                "list": subscriber.get("list"),
                "status": subscriber.get("status", "active"),
                "created_at": subscriber.get("created_at"),
                "standard_fields": subscriber.get("standard_fields", {}),
                "custom_fields": subscriber.get("custom_fields", {}),
            },
            metadata={
                "ip_address": str(request.client.host)
                if request.client
                else "unknown",
                "list_name": subscriber.get("list"),
                "email": subscriber.get("email"),
            },
        )

        return {"message": "Subscriber deleted successfully"}

    except Exception as e:
        logger.error(f"Delete subscriber failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))





@router.post("")
async def add_single_subscriber(subscriber: SubscriberIn, request: Request):
    try:
        subscribers_collection = get_subscribers_collection()

        # normalize email
        email = subscriber.email.strip().lower()

        existing = await subscribers_collection.find_one(
            {"email": email, "list": subscriber.list}
        )
        if existing:
            raise HTTPException(
                status_code=400, detail="Subscriber already exists in this list"
            )

        # --- build doc with universal + standard + custom fields ---
        doc = {
            "list": subscriber.list,
            "email": email,
            "status": subscriber.status or "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "standard_fields": subscriber.standard_fields or {},
            "custom_fields": subscriber.custom_fields or {},
        }

        result = await subscribers_collection.insert_one(doc)
        doc["_id"] = str(result.inserted_id)

        await log_activity(
            action="create",
            entity_type="subscriber",
            entity_id=str(result.inserted_id),
            user_action=f"Added subscriber {email} to list '{subscriber.list}'",
            after_data={
                "email": email,
                "list": subscriber.list,
                "status": doc["status"],
                "standard_fields": doc["standard_fields"],
                "custom_fields": doc["custom_fields"],
            },
            metadata={
                "ip_address": str(request.client.host)
                if request.client
                else "unknown",
                "list_name": subscriber.list,
                "email": email,
            },
        )

        return doc

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add subscriber failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@router.put("/{subscriber_id}")
async def update_subscriber(subscriber_id: str, subscriber: SubscriberIn, request: Request):
    try:
        subscribers_collection = get_subscribers_collection()

        if not ObjectId.is_valid(subscriber_id):
            raise HTTPException(status_code=400, detail="Invalid subscriber ID")

        old_subscriber = await subscribers_collection.find_one(
            {"_id": ObjectId(subscriber_id)}
        )
        if not old_subscriber:
            raise HTTPException(status_code=404, detail="Subscriber not found")

        # normalize email
        email = subscriber.email.strip().lower()

        # --- prepare update document ---
        update_data = {
            "list": subscriber.list,
            "email": email,
            "status": subscriber.status or old_subscriber.get("status", "active"),
            "updated_at": datetime.utcnow(),
            "standard_fields": subscriber.standard_fields or {},
            "custom_fields": subscriber.custom_fields or {},
        }

        result = await subscribers_collection.update_one(
            {"_id": ObjectId(subscriber_id)}, {"$set": update_data}
        )

        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Subscriber not found")

        await log_activity(
            action="update",
            entity_type="subscriber",
            entity_id=subscriber_id,
            user_action=f"Updated subscriber {email} in list '{subscriber.list}'",
            before_data={
                "email": old_subscriber.get("email"),
                "list": old_subscriber.get("list"),
                "status": old_subscriber.get("status"),
                "standard_fields": old_subscriber.get("standard_fields", {}),
                "custom_fields": old_subscriber.get("custom_fields", {}),
            },
            after_data=update_data,
            metadata={
                "ip_address": str(request.client.host)
                if request.client
                else "unknown",
                "old_list": old_subscriber.get("list"),
                "new_list": subscriber.list,
            },
        )

        return {"message": "Subscriber updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update subscriber failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{subscriber_id}/status")
async def update_subscriber_status(
    subscriber_id: str,
    request: Request,
    status: str = Query(..., regex="^(active|unsubscribed|inactive|bounced)$"),
):
    try:
        subscribers_collection = get_subscribers_collection()

        if not ObjectId.is_valid(subscriber_id):
            raise HTTPException(status_code=400, detail="Invalid subscriber ID")

        old_subscriber = await subscribers_collection.find_one(
            {"_id": ObjectId(subscriber_id)}
        )
        if not old_subscriber:
            raise HTTPException(status_code=404, detail="Subscriber not found")

        result = await subscribers_collection.update_one(
            {"_id": ObjectId(subscriber_id)},
            {"$set": {"status": status, "updated_at": datetime.utcnow()}},
        )

        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Subscriber not found")

        await log_activity(
            action="update",
            entity_type="subscriber_status",
            entity_id=subscriber_id,
            user_action=f"Updated subscriber {old_subscriber.get('email')} status to {status}",
            before_data={
                "email": old_subscriber.get("email"),
                "list": old_subscriber.get("list"),
                "status": old_subscriber.get("status"),
            },
            after_data={
                "email": old_subscriber.get("email"),
                "list": old_subscriber.get("list"),
                "status": status,
            },
            metadata={
                "ip_address": str(request.client.host)
                if request.client
                else "unknown",
                "list_name": old_subscriber.get("list"),
                "email": old_subscriber.get("email"),
            },
        )

        return {"message": f"Subscriber status updated to {status}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))






@router.delete("/{subscriber_id}")
async def delete_subscriber(subscriber_id: str, request: Request):
    try:
        subscribers_collection = get_subscribers_collection()

        if not ObjectId.is_valid(subscriber_id):
            raise HTTPException(status_code=400, detail="Invalid subscriber ID")

        subscriber = await subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not subscriber:
            raise HTTPException(status_code=404, detail="Subscriber not found")

        result = await subscribers_collection.delete_one({"_id": ObjectId(subscriber_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Subscriber not found")

        await log_activity(
            action="delete",
            entity_type="subscriber",
            entity_id=subscriber_id,
            user_action=f"Deleted subscriber {subscriber.get('email')} from list '{subscriber.get('list')}'",
            before_data={
                "name": subscriber.get("name", ""),
                "email": subscriber.get("email", ""),
                "list": subscriber.get("list", ""),
                "status": subscriber.get("status", "active"),
                "created_at": subscriber.get("created_at"),
            },
            metadata={
                "ip_address": str(request.client.host)
                if request.client
                else "unknown",
                "list_name": subscriber.get("list"),
                "email": subscriber.get("email"),
            },
        )

        return {"message": "Subscriber deleted successfully"}
    except Exception as e:
        logger.error(f"Delete subscriber failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/lists/{list_name}")
async def delete_list_by_name(list_name: str, request: Request):
    try:
        subscribers_collection = get_subscribers_collection()

        # Count + snapshot before deletion
        count_before = await subscribers_collection.count_documents({"list": list_name})
        if count_before == 0:
            raise HTTPException(status_code=404, detail="List not found or already empty")

        # Take a small sample of subscribers for audit
        sample_docs = await subscribers_collection.find(
            {"list": list_name}, {"email": 1, "standard_fields": 1, "custom_fields": 1}
        ).to_list(5)

        # Perform deletion
        result = await subscribers_collection.delete_many({"list": list_name})

        await log_activity(
            action="delete",
            entity_type="list",
            entity_id=list_name,
            user_action=f"Deleted entire list '{list_name}' with {result.deleted_count} subscribers",
            before_data={
                "list_name": list_name,
                "subscriber_count": count_before,
                "sample_subscribers": [
                    {
                        "email": doc.get("email"),
                        "standard_fields": doc.get("standard_fields", {}),
                        "custom_fields": doc.get("custom_fields", {}),
                    }
                    for doc in sample_docs
                ],
            },
            metadata={
                "ip_address": str(request.client.host)
                if request.client
                else "unknown",
                "list_name": list_name,
                "deleted_count": result.deleted_count,
            },
        )

        return {
            "message": f"✅ Deleted {result.deleted_count} subscribers from list '{list_name}'"
        }

    except Exception as e:
        logger.error(f"Delete list failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/lists/{list_name}/export")
async def export_list_csv(list_name: str, request: Request):
    try:
        subscribers_collection = get_subscribers_collection()
        cursor = subscribers_collection.find({"list": list_name})

        output = io.StringIO()
        writer = csv.writer(output)

        # Collect all possible columns across subscribers
        standard_keys = set()
        custom_keys = set()
        docs = []
        async for doc in cursor:
            docs.append(doc)
            standard_keys.update((doc.get("standard_fields") or {}).keys())
            custom_keys.update((doc.get("custom_fields") or {}).keys())

        # Define header: universal + standard + custom
        headers = (
            ["email", "status", "created_at", "updated_at", "list"]
            + sorted(list(standard_keys))
            + sorted(list(custom_keys))
        )
        writer.writerow(headers)

        # Write rows
        subscriber_count = 0
        for doc in docs:
            row = [
                doc.get("email", ""),
                doc.get("status", "active"),
                doc.get("created_at", "").isoformat() if doc.get("created_at") else "",
                doc.get("updated_at", "").isoformat() if doc.get("updated_at") else "",
                doc.get("list", ""),
            ]

            # Standard fields
            std = doc.get("standard_fields", {}) or {}
            for key in sorted(list(standard_keys)):
                row.append(std.get(key, ""))

            # Custom fields
            custom = doc.get("custom_fields", {}) or {}
            for key in sorted(list(custom_keys)):
                row.append(custom.get(key, ""))

            writer.writerow(row)
            subscriber_count += 1

        output.seek(0)

        await log_activity(
            action="export",
            entity_type="list",
            entity_id=list_name,
            user_action=f"Exported list '{list_name}' as CSV with {subscriber_count} subscribers",
            metadata={
                "ip_address": str(request.client.host)
                if request.client
                else "unknown",
                "list_name": list_name,
                "export_count": subscriber_count,
                "export_format": "csv",
            },
        )

        return StreamingResponse(
            io.BytesIO(output.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={list_name}_subscribers.csv"
            },
        )

    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Background Task for Large Operations
import asyncio
from fastapi import BackgroundTasks

class UploadTaskManager:
    def __init__(self):
        self.tasks = {}
    
    def create_task(self, task_id: str, coro):
        task = asyncio.create_task(coro)
        self.tasks[task_id] = {
            "task": task,
            "status": "running",
            "created_at": datetime.utcnow()
        }
        return task_id
    
    def get_task_status(self, task_id: str):
        if task_id not in self.tasks:
            return {"status": "not_found"}
        
        task_info = self.tasks[task_id]
        task = task_info["task"]
        
        if task.done():
            if task.exception():
                return {"status": "failed", "error": str(task.exception())}
            else:
                return {"status": "completed", "result": task.result()}
        else:
            return {"status": "running", "created_at": task_info["created_at"]}

# Global task manager
upload_manager = UploadTaskManager()

@router.get("/upload-status/{task_id}")
async def get_upload_status(task_id: str):
    """Check the status of a background upload task"""
    return upload_manager.get_task_status(task_id)

#  Memory Efficient CSV Processing
@router.post("/bulk-stream")
async def stream_bulk_upload(
    file: UploadFile = File(...),
    list_name: str = Form(...)
):
    """Stream process large CSV files without loading everything into memory"""

    subscribers_collection = get_subscribers_collection()

    # Process file in chunks
    chunk_size = 1000
    processed_count = 0

    content = await file.read()
    csv_reader = csv.DictReader(io.StringIO(content.decode("utf-8")))

    batch = []
    for row in csv_reader:
        # Process and validate row
        subscriber = {
            "email": row.get("email", "").strip(),
            "list": list_name,
            "status": "active",
            "standard_fields": {
                "first_name": row.get("first_name", "").strip(),
                "last_name": row.get("last_name", "").strip(),
            },
            "custom_fields": {
                k: v for k, v in row.items() if k not in ["email", "first_name", "last_name"]
            },
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        if subscriber["email"]:  # Only add valid emails
            batch.append(subscriber)

        # Process in chunks
        if len(batch) >= chunk_size:
            await process_batch(subscribers_collection, batch)
            processed_count += len(batch)
            batch = []

    # Process remaining items
    if batch:
        await process_batch(subscribers_collection, batch)
        processed_count += len(batch)

    return {"message": f"Processed {processed_count} subscribers"}


async def process_batch(subscribers_collection, batch: List[Dict]):
    """Process a batch of subscribers efficiently"""
    operations = []

    for subscriber in batch:
        operations.append(
            UpdateOne(
                {"email": subscriber["email"], "list": subscriber["list"]},
                {
                    "$set": subscriber,
                    "$setOnInsert": {"created_at": datetime.utcnow()},
                },
                upsert=True,
            )
        )

    if operations:
        await subscribers_collection.bulk_write(operations, ordered=False)

@router.get("/audit/logs")
async def get_audit_logs(
    limit: int = Query(50, le=1000),
    skip: int = Query(0),
    entity_type: str = Query(None),
    action: str = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None),
):
    """Get audit trail logs with filtering"""
    try:
        audit_collection = get_audit_collection()

        query = {}
        if entity_type:
            query["entity_type"] = entity_type
        if action:
            query["action"] = action
        if start_date or end_date:
            date_query = {}
            if start_date:
                date_query["$gte"] = datetime.fromisoformat(start_date.replace("T", " "))
            if end_date:
                date_query["$lte"] = datetime.fromisoformat(end_date.replace("T", " "))
            query["timestamp"] = date_query

        cursor = (
            audit_collection.find(query)
            .sort("timestamp", -1)
            .skip(skip)
            .limit(limit)
        )

        logs = []
        async for log in cursor:
            log["_id"] = str(log["_id"])

            # Ensure before/after data always contain tier fields
            if "before_data" in log:
                log["before_data"].setdefault("standard_fields", {})
                log["before_data"].setdefault("custom_fields", {})
            if "after_data" in log:
                log["after_data"].setdefault("standard_fields", {})
                log["after_data"].setdefault("custom_fields", {})

            logs.append(log)

        total = await audit_collection.count_documents(query)

        return {
            "logs": logs,
            "total": total,
            "page": skip // limit + 1,
            "total_pages": (total + limit - 1) // limit,
        }

    except Exception as e:
        logger.error(f"Get audit logs failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))



#Required for logger 
async def log_activity(
    action: str,
    entity_type: str,
    entity_id: str,
    user_action: str,
    before_data: dict = None,
    after_data: dict = None,
    metadata: dict = None,
):
    """Log all activities for audit trail"""
    try:
        audit_collection = get_audit_collection()
        log_entry = {
            "timestamp": datetime.utcnow(),
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "user_action": user_action,
            "before_data": before_data or {},
            "after_data": after_data or {},
            "metadata": metadata or {},
        }

        await audit_collection.insert_one(log_entry)
        logger.info(f"AUDIT: {action} - {user_action}")  # Add this line

    except Exception as e:
        logger.error(f"Failed to log activity: {e}")

