from fastapi import APIRouter, HTTPException, Query
from database import get_audit_collection
from datetime import datetime
import logging
from fastapi.responses import StreamingResponse
import csv
import io

router = APIRouter()
logger = logging.getLogger(__name__)

def convert_objectids_to_strings(doc):
    """Convert ObjectId fields to strings for JSON serialization"""
    if isinstance(doc, dict):
        return {k: str(v) if k == '_id' or str(type(v)) == "<class 'bson.objectid.ObjectId'>" else convert_objectids_to_strings(v) for k, v in doc.items()}
    elif isinstance(doc, list):
        return [convert_objectids_to_strings(item) for item in doc]
    else:
        return doc


@router.get("/logs")
async def get_audit_logs(
    limit: int = Query(50, le=1000),
    skip: int = Query(0),
    entity_type: str = Query(None),
    action: str = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None)
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
                try:
                    date_query["$gte"] = datetime.fromisoformat(start_date.replace("T", " "))
                except ValueError:
                    date_query["$gte"] = datetime.fromisoformat(start_date)
            if end_date:
                try:
                    date_query["$lte"] = datetime.fromisoformat(end_date.replace("T", " "))
                except ValueError:
                    date_query["$lte"] = datetime.fromisoformat(end_date)
            if date_query:
                query["timestamp"] = date_query

        # Get total count for pagination
        total_count = await audit_collection.count_documents(query)

        # Get paginated results
        cursor = audit_collection.find(query).sort("timestamp", -1).skip(skip).limit(limit)
        logs = []

        async for doc in cursor:
            # Convert ObjectIds to strings for JSON serialization
            log_entry = convert_objectids_to_strings(doc)
            logs.append(log_entry)

        return {
            "logs": logs,
            "total_count": total_count,
            "limit": limit,
            "skip": skip,
            "has_more": skip + limit < total_count
        }

    except Exception as e:
        logger.error(f"Get audit logs failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve audit logs: {str(e)}")


@router.get("/export")
async def export_audit_logs(
    entity_type: str = Query(None),
    action: str = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None)
):
    """Export audit logs as CSV"""
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
                try:
                    date_query["$gte"] = datetime.fromisoformat(start_date.replace("T", " "))
                except ValueError:
                    date_query["$gte"] = datetime.fromisoformat(start_date)
            if end_date:
                try:
                    date_query["$lte"] = datetime.fromisoformat(end_date.replace("T", " "))
                except ValueError:
                    date_query["$lte"] = datetime.fromisoformat(end_date)
            if date_query:
                query["timestamp"] = date_query

        # Fetch logs
        cursor = audit_collection.find(query).sort("timestamp", -1).limit(10000)  # Limit exports
        logs = []
        async for doc in cursor:
            logs.append(convert_objectids_to_strings(doc))

        # Create CSV
        output = io.StringIO()
        if logs:
            fieldnames = ['timestamp', 'entity_type', 'entity_id', 'action', 'user_action']
            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            
            for log in logs:
                writer.writerow({
                    'timestamp': log.get('timestamp', ''),
                    'entity_type': log.get('entity_type', ''),
                    'entity_id': log.get('entity_id', ''),
                    'action': log.get('action', ''),
                    'user_action': log.get('user_action', '')
                })

        output.seek(0)
        
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=audit-logs-{datetime.utcnow().isoformat()}.csv"
            }
        )

    except Exception as e:
        logger.error(f"Export audit logs failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to export audit logs: {str(e)}")