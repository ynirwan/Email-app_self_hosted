# routes/subscribers.py - COMPLETE file matching your frontend requirements
from fastapi import APIRouter, HTTPException, Query, Request, status, File, Form, UploadFile, BackgroundTasks, Depends
from database import get_subscribers_collection, get_audit_collection, get_jobs_collection
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, EmailStr, validator
from bson import ObjectId
from datetime import datetime
import logging
from fastapi.responses import StreamingResponse
import csv
import io
import os
import re
import uuid
from schemas.subscriber_schema import SubscriberIn, BulkPayload, SubscriberOut
import time
import asyncio
import json
import glob
import math 
from pymongo import UpdateOne
from pymongo.errors import BulkWriteError, DuplicateKeyError
from functools import wraps
import traceback


from datetime import datetime, timedelta
from pymongo import UpdateOne

router = APIRouter()


# ===== LOGGING SETUP =====
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
)
 # ===== RESTORE ORIGINAL AUDIT ENDPOINTS =====
@router.get("/audit/logs")
async def get_audit_logs(
    limit: int = Query(50, le=1000),
    skip: int = Query(0),
    entity_type: str = Query(None),
    action: str = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None)
):
    """Get audit trail logs with filtering - FIXED for ObjectId serialization"""
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
        logger.error(f"Get audit logs failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve audit logs")