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

# ===== LOGGING SETUP =====
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
)

# Add console handler if not exists
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)



# ===== PRODUCTION IMPORTS =====
PRODUCTION_FEATURES = {
    'config': False,
    'subscriber_recovery': False,
    'file_first_recovery': False,
    'performance_logging': False,
    'rate_limiting': False,
    'websocket': False
}
# ===== MISSING AUDIT LOGGING FUNCTION =====
async def log_activity(
    action: str,
    entity_type: str,
    entity_id: str,
    user_action: str,
    before_data: dict = None,
    after_data: dict = None,
    metadata: dict = None,
    request: Request = None
):
    """Enhanced audit logging with request context"""
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
            "metadata": metadata or {}
        }
        
        # Add request context if available
        if request:
            log_entry["request_info"] = {
                "ip": get_client_ip(request),
                "user_agent": request.headers.get("user-agent", "unknown"),
                "method": request.method,
                "path": str(request.url.path)
            }
        
        await audit_collection.insert_one(log_entry)
        logger.info(f"📝 AUDIT: {action} - {user_action}")
        
    except Exception as e:
        # Don't fail the operation if audit logging fails
        logger.error(f"Audit logging failed: {e}")

# Safe production imports
try:
    from core.config import settings
    PRODUCTION_FEATURES['config'] = True
    logger = logging.getLogger(__name__)
    logger.info(" Production config loaded")
except ImportError:
    logger = logging.getLogger("uvicorn.error")
    logger.info("  Using basic configuration")
    class MockSettings:
        MAX_BATCH_SIZE = 1000
        ENABLE_BULK_OPTIMIZATIONS = False
        ENABLE_HYBRID_RECOVERY = True
        LOG_LEVEL = "INFO"
    settings = MockSettings()

try:
    from tasks.simple_file_recovery import simple_file_recovery
    PRODUCTION_FEATURES['file_first_recovery'] = True
    logger.info(" File-First Recovery enabled")
except ImportError:
    logger.info("  File-First Recovery not available")

router = APIRouter()

# Models
class JobStatus(BaseModel):
    job_id: str
    list_name: str
    status: str
    total: int
    processed: int
    progress: float
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None
    new_records: Optional[int] = 0
    updated_records: Optional[int] = 0
    duplicate_records: Optional[int] = 0
    records_per_second: Optional[int] = 0

class BackgroundUploadPayload(BaseModel):
    list_name: str
    subscribers: List[Dict[str, Any]]
    processing_mode: Optional[str] = "background"
    @validator('list_name')
    def validate_list_name(cls, v):
        if not v or not v.strip():
            raise ValueError("List name cannot be empty")
        if len(v) > 100:
            raise ValueError("List name too long (max 100 characters)")
        # Sanitize list name
        return v.strip().replace('/', '_').replace('\\', '_')
    
    @validator('subscribers')
    def validate_subscribers(cls, v):
        if not v:
            raise ValueError("Subscribers list cannot be empty")
        if len(v) > 1000000:  # 1M limit
            raise ValueError("Too many subscribers in single request (max 1M)")
        return v

# ===== UTILITIES =====
class PerformanceMonitor:
    @staticmethod
    def track_operation(operation_name: str):
        """Decorator for tracking operation performance"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start_time = time.time()
                success = False
                error_msg = None

                try:
                    result = await func(*args, **kwargs)
                    success = True
                    return result
                except Exception as e:
                    error_msg = str(e)
                    raise
                finally:
                    duration = time.time() - start_time
                    log_level = logging.INFO if success else logging.ERROR
                    logger.log(
                        log_level,
                        f"Operation: {operation_name} | Duration: {duration:.3f}s | "
                        f"Success: {success} | Error: {error_msg or 'None'}"
                    )
                    if duration > 5.0:
                        logger.warning(
                            f"SLOW OPERATION: {operation_name} took {duration:.3f}s"
                        )
            return wrapper
        return decorator


class RateLimiter:
    """Simple in-memory rate limiter"""
    
    def __init__(self):
        self.requests = {}  # {ip: [timestamps]}
        self.window = 60  # 1 minute window
        self.max_requests = 100  # 100 requests per minute
    
    def is_allowed(self, identifier: str) -> bool:
        """Check if request is allowed"""
        now = time.time()
        
        # Clean old entries
        if identifier in self.requests:
            self.requests[identifier] = [
                ts for ts in self.requests[identifier] 
                if now - ts < self.window
            ]
        else:
            self.requests[identifier] = []
        
        # Check limit
        if len(self.requests[identifier]) >= self.max_requests:
            return False
        
        self.requests[identifier].append(now)
        return True

rate_limiter = RateLimiter()

def get_client_ip(request: Request) -> str:
    """Get client IP address"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

async def rate_limit_check(request: Request):
    """Dependency for rate limiting"""
    if PRODUCTION_FEATURES.get('rate_limiting', False):
        client_ip = get_client_ip(request)
        if not rate_limiter.is_allowed(client_ip):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later."
            )
    return True

class SafeBatchProcessor:
    @staticmethod
    def get_optimal_batch_size(total_records: int, operation: str = "general") -> int:
        """Calculate optimal batch size based on record count"""
        if PRODUCTION_FEATURES.get('config', False):
            return settings.get_batch_size_for_operation(total_records, operation)
        
        # Conservative defaults
        if total_records < 1000:
            return total_records
        elif total_records < 10000:
            return 1000
        elif total_records < 50000:
            return 2000
        else:
            return 5000

# ===== JOB MANAGER =====
class ProductionJobManager:
    def __init__(self):
        self.active_jobs = {}
        self.job_locks = {}

    async def create_job(self, job_type: str, list_name: str, total_records: int) -> str:
        job_id = str(uuid.uuid4())
        job_doc = {
            "_id": job_id,
            "job_id": job_id,
            "job_type": job_type,
            "list_name": list_name,
            "status": "pending",
            "progress": 0.0,
            "total_records": total_records,
            "processed_records": 0,
            "new_records": 0,
            "updated_records": 0,
            "duplicate_records": 0,
            "failed_records": 0,
            "records_per_second": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "last_heartbeat": datetime.utcnow(),
            "completion_time": None,
            "error_messages": [],
            "file_first_enabled": PRODUCTION_FEATURES.get('file_first_recovery', False)
        }

        try:
            jobs_collection = get_jobs_collection()
            await jobs_collection.insert_one(job_doc)
            self.active_jobs[job_id] = job_doc
            self.job_locks[job_id] = asyncio.Lock()

            logger.info(f" Job created: {job_id} (file-first: {job_doc['file_first_enabled']})")
            return job_id
        except Exception as e:
            logger.error(f" Job creation failed: {e}")
            raise HTTPException(status_code=500, detail=f"Job creation failed: {str(e)}")

    async def update_job_progress(self, job_id: str, processed: int, new_records: int = 0,
updated_records: int = 0, duplicate_records: int = 0, failed: int = 0, error_message: str = None):
        try:
            if job_id in self.job_locks:
                async with self.job_locks[job_id]:
                    await self._update_job_internal(
                        job_id, processed, new_records, updated_records,
                        duplicate_records, failed, error_message
                    )
            else:
                await self._update_job_internal(
                    job_id, processed, new_records, updated_records,
                    duplicate_records, failed, error_message
                )
        except Exception as e:
            logger.error(f"❌ Job progress update failed for {job_id}: {e}")
    
    async def _update_job_internal(
        self, job_id, processed, new_records, updated_records,
        duplicate_records, failed, error_message
    ):
            
            jobs_collection = get_jobs_collection()
            job = await jobs_collection.find_one({"_id": job_id})
            if not job:
                logger.warning(f"Job {job_id} not found for update")
                return

            total = job.get("total_records", 1)
            progress = (processed / total) * 100 if total > 0 else 0

            created_at = job.get("created_at", datetime.utcnow())
            elapsed = (datetime.utcnow() - created_at).total_seconds()
            speed = int(processed / elapsed) if elapsed > 0 else 0

            update_doc = {
                "processed_records": processed,
                "new_records": new_records,
                "updated_records": updated_records,
                "duplicate_records": duplicate_records,
                "failed_records": failed,
                "progress": progress,
                "records_per_second": speed,
                "updated_at": datetime.utcnow(),
                "last_heartbeat": datetime.utcnow()
            }

            if error_message:
                current_errors = job.get("error_messages", [])
                current_errors.append({
                "timestamp": datetime.utcnow().isoformat(),
                "message": error_message
            })
                update_doc["error_messages"] = current_errors[-10:]

            if processed >= total:
                update_doc["status"] = "completed"
                update_doc["completion_time"] = datetime.utcnow()
                update_doc["final_records_per_second"] = speed
                if job_id in self.active_jobs:
                    del self.active_jobs[job_id]
                if job_id in self.job_locks:
                    del self.job_locks[job_id]    

            await jobs_collection.update_one({"_id": job_id}, {"$set": update_doc})
            if job_id in self.active_jobs:
                self.active_jobs[job_id].update(update_doc)

    async def mark_job_failed(
        self, 
        job_id: str, 
        error_message: str,
        failed_at_record: int = 0
    ):
        """Mark job as failed with error details"""
        try:
            jobs_collection = get_jobs_collection()
            
            await jobs_collection.update_one(
                {"_id": job_id},
                {"$set": {
                    "status": "failed",
                    "error_message": error_message,
                    "failed_at_record": failed_at_record,
                    "failed_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }}
            )
            
            if job_id in self.active_jobs:
                del self.active_jobs[job_id]
            if job_id in self.job_locks:
                del self.job_locks[job_id]
            
            logger.error(
                f"❌ Job {job_id} marked as failed: {error_message} "
                f"(at record {failed_at_record})"
            )
            
        except Exception as e:
            logger.error(f"Failed to mark job as failed: {e}")

# Global job manager
job_manager = ProductionJobManager()



@router.post("/background-upload", dependencies=[Depends(rate_limit_check)])
@PerformanceMonitor.track_operation("background_upload")
async def background_upload_enhanced(payload: BackgroundUploadPayload, request: Request, background_tasks: BackgroundTasks):
    """Background upload with chunked processing for all upload sizes"""
    try:
        total_records = len(payload.subscribers)
        if total_records == 0:
            raise HTTPException(
                status_code=400,
                detail="No subscribers provided"
            )
        job_id = await job_manager.create_job("background_upload", payload.list_name, total_records)

        logger.info(f"📤 Background upload started: {total_records:,} subscribers for list '{payload.list_name}'")

        # IMMEDIATELY UPDATE STATUS TO PROCESSING
        jobs_collection = get_jobs_collection()
        await jobs_collection.update_one(
            {"_id": job_id},
            {"$set": {
                "status": "processing",
                "updated_at": datetime.utcnow(),
                "last_heartbeat": datetime.utcnow(),
                "processing_start": datetime.utcnow()
            }}
        )
        logger.info(f"✔ Job {job_id} status updated to PROCESSING immediately")

        # SAVE UPLOAD IN CHUNKS
        chunk_files = await save_upload_in_chunks(job_id, payload)
        if not chunk_files:
            await job_manager.mark_job_failed(
                job_id,
                "Failed to create upload chunks"
            )
            raise HTTPException(
                status_code=500,
                detail="Failed to create upload chunks"
            )

        # PROCESS EACH CHUNK
        total_processed = await process_upload_chunks(job_id, payload.list_name, chunk_files, total_records)

        # Log activity
        await log_activity(
            action="bulk_upload",
            entity_type="subscribers",
            entity_id=job_id,
            user_action=f"Uploaded {total_processed:,} subscribers to '{payload.list_name}'",
            metadata={
                "total_records": total_records,
                "processed_records": total_processed,
                "list_name": payload.list_name
            },
        )
        
        logger.info(
            f"✅ Upload completed: {total_processed:,} subscribers | Job: {job_id}"
        )
        
        return {
            "job_id": job_id,
            "message": f"Upload completed for {total_processed:,} subscribers",
            "total_records": total_records,
            "processed_records": total_processed
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Background upload failed: {e}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {str(e)}"
        )


# ===== SAVE UPLOAD IN CHUNKS =====
async def save_upload_in_chunks(job_id: str, payload: BackgroundUploadPayload) -> List[str]:
    try:
        chunk_size = 15000
        subscribers = payload.subscribers
        total_records = len(subscribers)
        chunks_dir = f"upload_queue/chunks/{job_id}"
        os.makedirs(chunks_dir, exist_ok=True)
        chunk_files = []

        for i in range(0, total_records, chunk_size):
            chunk_number = i // chunk_size
            chunk = subscribers[i:i + chunk_size]
            chunk_filename = f"chunk_{chunk_number:04d}.json"
            chunk_path = os.path.join(chunks_dir, chunk_filename)

            chunk_data = {
                "job_id": job_id,
                "list_name": payload.list_name,
                "chunk_number": chunk_number,
                "total_chunks": (total_records + chunk_size - 1) // chunk_size,
                "chunk_records": len(chunk),
                "created_at": datetime.utcnow().isoformat(),
                "subscribers": chunk
            }

            temp_path = chunk_path + ".tmp"
            with open(temp_path, 'w') as f:
                json.dump(chunk_data, f, default=str)
            os.rename(temp_path, chunk_path)
            
            chunk_files.append(chunk_path)
        
        logger.info(f"🗂️ Created {len(chunk_files)} chunk files for job {job_id}")
        return chunk_files
        
    except Exception as e:
        logger.error(f"❌ Failed to create chunks: {e}")
        return []
    
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Tuple

async def process_upload_chunks(job_id: str, list_name: str, chunk_files: List[str], total_records: int) -> int:
    """Enhanced parallel chunk processing with duplicate tracking"""
    subscribers_collection = get_subscribers_collection()
    jobs_collection = get_jobs_collection()
    start_time = datetime.utcnow()

    # ✅ Initialize tracking variables
    total_processed = 0
    total_duplicates = 0
    total_new_records = 0
    total_updated_records = 0
    completed_chunks = 0
    failed_chunks = 0
    
    # ✅ Parallel processing configuration
    max_concurrent_chunks = min(4, len(chunk_files))  # Process up to 4 chunks simultaneously
    semaphore = asyncio.Semaphore(max_concurrent_chunks)
    
    # ✅ Thread-safe counters
    import threading
    counters_lock = threading.Lock()
    
    async def process_single_chunk(chunk_index: int, chunk_file: str) -> Dict:
        """Process a single chunk with duplicate tracking"""
        async with semaphore:
            chunk_stats = {
                "processed": 0,
                "new_records": 0,
                "updated_records": 0,
                "duplicates": 0,
                "errors": 0,
                "chunk_index": chunk_index
            }
            
            try:
                logger.info(f"🚀 Starting chunk {chunk_index + 1}/{len(chunk_files)}: {chunk_file}")
                
                # Load chunk data
                with open(chunk_file, 'r') as f:
                    chunk_data = json.load(f)
                
                chunk_subscribers = chunk_data.get("subscribers", [])
                batch_size = 15000
                
                # ✅ Track emails in this chunk for duplicate detection
                chunk_emails_processed = set()
                
                for i in range(0, len(chunk_subscribers), batch_size):
                    batch = chunk_subscribers[i:i + batch_size]
                    operations = []
                    batch_emails = []
                    
                    for subscriber_data in batch:
                        email = subscriber_data.get("email")
                        if not email:
                            continue
                            
                        email = email.lower().strip()
                        batch_emails.append(email)
                        
                        # ✅ Track duplicates within the same chunk
                        if email in chunk_emails_processed:
                            chunk_stats["duplicates"] += 1
                            continue
                        
                        chunk_emails_processed.add(email)
                        
                        subscriber_doc = {
                            "email": email,
                            "list": list_name,
                            "status": subscriber_data.get("status", "active"),
                            "standard_fields": subscriber_data.get("standard_fields", {}),
                            "custom_fields": subscriber_data.get("custom_fields", {}),
                            "job_id": job_id,
                            "created_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        }
                        
                        operations.append(UpdateOne(
                            {"email": email, "list": list_name},
                            {"$set": subscriber_doc},
                            upsert=True
                        ))
                    
                    if operations:
                        try:
                            # ✅ Check for existing records before bulk write
                            existing_emails = set()
                            if batch_emails:
                                existing_cursor = subscribers_collection.find(
                                    {"email": {"$in": batch_emails}, "list": list_name},
                                    {"email": 1}
                                )
                                async for doc in existing_cursor:
                                    existing_emails.add(doc["email"])
                            
                            # Execute bulk write
                            result = await subscribers_collection.bulk_write(
                                operations,
                                ordered=False,
                                bypass_document_validation=True
                            )
                            
                            # ✅ Calculate accurate stats
                            chunk_stats["new_records"] += result.upserted_count
                            chunk_stats["updated_records"] += result.modified_count
                            chunk_stats["processed"] += result.upserted_count + result.modified_count
                            
                            # ✅ Count duplicates that were updated (existing records)
                            for email in batch_emails:
                                if email in existing_emails and email in chunk_emails_processed:
                                    chunk_stats["duplicates"] += 1
                            
                            logger.debug(f"Chunk {chunk_index + 1} batch: "
                                       f"upserted {result.upserted_count}, "
                                       f"modified {result.modified_count}, "
                                       f"duplicates {chunk_stats['duplicates']}")
                                       
                        except Exception as batch_error:
                            logger.error(f"Batch error in chunk {chunk_index + 1}: {batch_error}")
                            chunk_stats["errors"] += len(operations)
                
                logger.info(f"✅ Completed chunk {chunk_index + 1}: "
                          f"{chunk_stats['processed']} processed, "
                          f"{chunk_stats['duplicates']} duplicates")
                
                # Cleanup chunk file
                try:
                    os.remove(chunk_file)
                    logger.debug(f"Deleted chunk file: {chunk_file}")
                except Exception as cleanup_error:
                    logger.warning(f"Failed deleting chunk file {chunk_file}: {cleanup_error}")
                
                return chunk_stats
                
            except Exception as chunk_error:
                logger.error(f"❌ Failed processing chunk {chunk_index + 1}: {chunk_error}")
                chunk_stats["errors"] += 1
                return chunk_stats

    # ✅ Process all chunks in parallel
    logger.info(f"🚀 Starting parallel processing of {len(chunk_files)} chunks "
              f"(max {max_concurrent_chunks} concurrent)")
    
    # Create tasks for all chunks
    tasks = [
        process_single_chunk(i, chunk_file) 
        for i, chunk_file in enumerate(chunk_files)
    ]
    
    # Execute chunks in parallel and track progress
    for i, task in enumerate(asyncio.as_completed(tasks)):
        try:
            chunk_stats = await task
            
            # ✅ Thread-safe counter updates
            with counters_lock:
                total_processed += chunk_stats["processed"]
                total_new_records += chunk_stats["new_records"]
                total_updated_records += chunk_stats["updated_records"]
                total_duplicates += chunk_stats["duplicates"]
                completed_chunks += 1
                
                if chunk_stats["errors"] > 0:
                    failed_chunks += 1
            
            # ✅ Update job progress after each completed chunk
            progress = (completed_chunks / len(chunk_files)) * 100
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            speed = int(total_processed / processing_time) if processing_time > 0 else 0
            
            update_data = {
                "processed_records": total_processed,
                "new_records": total_new_records,
                "updated_records": total_updated_records,
                "duplicate_records": total_duplicates,
                "progress": min(progress, 100),
                "records_per_second": speed,
                "updated_at": datetime.utcnow(),
                "last_heartbeat": datetime.utcnow(),
                "status": "processing",
                "completed_chunks": completed_chunks,
                "failed_chunks": failed_chunks,
                "total_chunks": len(chunk_files),
            }
            
            try:
                await jobs_collection.update_one(
                    {"_id": job_id},
                    {"$set": update_data},
                    upsert=True
                )
                logger.info(f"📊 Progress: {completed_chunks}/{len(chunk_files)} chunks, "
                          f"{total_processed:,} processed ({total_new_records:,} new, "
                          f"{total_updated_records:,} updated, {total_duplicates:,} duplicates)")
            except Exception as job_update_err:
                logger.error(f"Failed to update job progress: {job_update_err}")
                
        except Exception as task_error:
            logger.error(f"Task execution error: {task_error}")
            with counters_lock:
                failed_chunks += 1

    # ✅ Enhanced final job update with detailed statistics
    total_processing_time = (datetime.utcnow() - start_time).total_seconds()
    final_speed = int(total_processed / total_processing_time) if total_processing_time > 0 else 0
    successful_chunks = completed_chunks - failed_chunks
    
    # Determine final status
    if failed_chunks == 0:
        final_status = "completed"
        status_reason = f"Successfully processed {total_processed:,} records"
    elif successful_chunks > 0:
        final_status = "partially_completed"
        status_reason = f"Processed {total_processed:,} records with {failed_chunks} failed chunks"
    else:
        final_status = "failed"
        status_reason = "All chunks failed to process"
    
    final_update = {
        "status": final_status,
        "status_reason": status_reason,
        "completion_time": datetime.utcnow(),
        "final_processed": total_processed,
        "total_records": total_records,
        # ✅ Detailed statistics
        "new_records": total_new_records,
        "updated_records": total_updated_records,
        "duplicate_records": total_duplicates,
        "processing_method": "parallel_chunks_with_duplicate_tracking",
        "max_concurrent_chunks": max_concurrent_chunks,
        "total_processing_time_seconds": total_processing_time,
        "final_records_per_second": final_speed,
        "successful_chunks": successful_chunks,
        "failed_chunks": failed_chunks,
        "chunks_processed": completed_chunks,
        "total_chunks": len(chunk_files),
        "success_rate": (successful_chunks / len(chunk_files)) * 100 if chunk_files else 0,
        "duplicate_rate": (total_duplicates / total_records) * 100 if total_records > 0 else 0,
        "updated_at": datetime.utcnow(),
        "last_heartbeat": datetime.utcnow()
    }

    try:
        await jobs_collection.update_one(
            {"_id": job_id},
            {"$set": final_update},
            upsert=True
        )
        logger.info(f"✅ Final job update: {final_status} - "
                   f"{total_processed:,} processed ({total_new_records:,} new, "
                   f"{total_updated_records:,} updated, {total_duplicates:,} duplicates) "
                   f"at {final_speed:,} rec/sec in {total_processing_time:.1f}s")
    except Exception as final_update_error:
        logger.error(f"❌ Failed final job update: {final_update_error}")

    # Cleanup chunks directory
    chunks_dir = os.path.dirname(chunk_files[0]) if chunk_files else None
    if chunks_dir and os.path.exists(chunks_dir):
        try:
            import shutil
            shutil.rmtree(chunks_dir, ignore_errors=True)
            logger.info(f"Cleaned up chunks directory: {chunks_dir}")
        except Exception as cleanup_error:
            logger.warning(f"Failed to cleanup chunks directory: {cleanup_error}")

    return total_processed


@router.get("/jobs/status")
async def get_job_status():
    """Enhanced job status with comprehensive duplicate tracking and statistics"""
    try:
        jobs_collection = get_jobs_collection()
        subscribers_collection = get_subscribers_collection()
        cursor = jobs_collection.find({}, sort=[("created_at", -1)], limit=50)
        
        jobs = []
        now = datetime.utcnow()
        
        async for job in cursor:
            job_status = await determine_job_status(job, subscribers_collection, now)
            
            job_data = {
                "_id": str(job["_id"]),
                "job_id": job.get("job_id"),
                "list_name": job.get("list_name"),
                "status": job_status["status"],  # ✅ Updated status
                "progress": job.get("progress", 0),
                "total": job.get("total_records", 0),
                "processed": job.get("processed_records", 0),
                "failed": job.get("failed_records", 0),
                
                # ✅ Enhanced duplicate and record tracking
                "new_records": job.get("new_records", 0),
                "updated_records": job.get("updated_records", 0),
                "duplicate_records": job.get("duplicate_records", 0),
                "duplicate_rate": job.get("duplicate_rate", 0),
                
                # Timestamps
                "created_at": job.get("created_at"),
                "updated_at": job.get("updated_at"),
                "completion_time": job.get("completion_time"),
                "last_heartbeat": job.get("last_heartbeat"),
                
                # Performance metrics
                "records_per_second": job.get("records_per_second", 0),
                "final_records_per_second": job.get("final_records_per_second", 0),
                "total_processing_time_seconds": job.get("total_processing_time_seconds", 0),
                
                # Processing details
                "processing_method": job.get("processing_method", "standard"),
                "max_concurrent_chunks": job.get("max_concurrent_chunks", 1),
                "successful_chunks": job.get("successful_chunks", 0),
                "failed_chunks": job.get("failed_chunks", 0),
                "total_chunks": job.get("total_chunks", 0),
                "chunks_processed": job.get("chunks_processed", 0),
                "success_rate": job.get("success_rate", 0),
                
                # ✅ Enhanced status info
                "actual_subscriber_count": job_status.get("actual_subscriber_count", 0),
                "status_reason": job_status.get("reason", ""),
                "stuck_duration_minutes": job_status.get("stuck_duration_minutes", 0),
                
                # ✅ Detailed statistics display
                "statistics": {
                    "total_input": job.get("total_records", 0),
                    "successfully_processed": job.get("processed_records", 0),
                    "new_subscribers": job.get("new_records", 0),
                    "updated_existing": job.get("updated_records", 0),
                    "duplicates_filtered": job.get("duplicate_records", 0),
                    "failed_records": job.get("failed_records", 0),
                    "actual_database_count": job_status.get("actual_subscriber_count", 0),
                    "duplicate_percentage": round(job.get("duplicate_rate", 0), 1),
                    "processing_efficiency": job_status.get("processing_efficiency", 0)
                },
                
                # ✅ FIXED: Call functions without self
                "performance_display": {
                    "method_text": format_processing_method(job.get("processing_method", "standard")),
                    "speed_text": format_speed_display(job),
                    "duration_text": format_duration_display(job),
                    "efficiency_text": format_efficiency_display(job, job_status)
                }
            }
            jobs.append(job_data)
        
        return {"jobs": jobs}
        
    except Exception as e:
        logger.error(f"Get job status failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get job statuses")

# ✅ FIXED: Remove 'self' parameter from all helper functions
def format_processing_method(method: str) -> str:
    """Format processing method for display"""
    method_map = {
        "parallel_chunks_with_duplicate_tracking": "Parallel Processing",
        "batch_progress_updates": "Batch Processing", 
        "chunked_background_upload": "Chunked Upload",
        "standard": "Standard"
    }
    return method_map.get(method, method.title())

def format_speed_display(job: dict) -> str:
    """Format speed display based on job status"""
    final_speed = job.get("final_records_per_second", 0)
    current_speed = job.get("records_per_second", 0)
    
    if job.get("status") in ["completed", "partially_completed"]:
        return f"{final_speed:,} records/sec (final)" if final_speed > 0 else "Completed"
    elif current_speed > 0:
        return f"{current_speed:,} records/sec (current)"
    else:
        return "Processing..."

def format_duration_display(job: dict) -> str:
    """Format processing duration"""
    duration = job.get("total_processing_time_seconds", 0)
    if duration > 0:
        if duration < 60:
            return f"{duration:.1f}s"
        elif duration < 3600:
            return f"{duration/60:.1f}m"
        else:
            return f"{duration/3600:.1f}h"
    return "N/A"

def format_efficiency_display(job: dict, job_status: dict) -> str:
    """Format processing efficiency display"""
    total = job.get("total_records", 0)
    duplicates = job.get("duplicate_records", 0)
    new_records = job.get("new_records", 0)
    
    if total > 0:
        efficiency = ((new_records + duplicates) / total) * 100
        if duplicates > 0:
            return f"{efficiency:.1f}% processed ({duplicates:,} duplicates)"
        else:
            return f"{efficiency:.1f}% processed"
    return "N/A"

async def determine_job_status(job: dict, subscribers_collection, now: datetime) -> dict:
    """
    Enhanced job status determination with comprehensive duplicate analysis
    """
    job_id = job.get("job_id")
    list_name = job.get("list_name")
    current_status = job.get("status", "unknown")
    
    # ✅ STEP 1: Get comprehensive subscriber statistics
    try:
        # Count actual subscribers for this specific job
        actual_count = await subscribers_collection.count_documents({
            "list": list_name,
            "job_id": job_id
        }) if job_id and list_name else 0
        
        # Count total subscribers in the list (for context)
        list_total = await subscribers_collection.count_documents({
            "list": list_name
        }) if list_name else 0
        
    except Exception as e:
        logger.error(f"Failed to count subscribers for job {job_id}: {e}")
        actual_count = 0
        list_total = 0
    
    # ✅ STEP 2: Get job metadata with duplicate tracking
    total_records = job.get("total_records", 0)
    processed_records = job.get("processed_records", 0)
    new_records = job.get("new_records", 0)
    updated_records = job.get("updated_records", 0)
    duplicate_records = job.get("duplicate_records", 0)
    
    last_heartbeat = job.get("last_heartbeat", job.get("updated_at", now))
    created_at = job.get("created_at", now)
    
    # Time calculations
    heartbeat_age_minutes = (now - last_heartbeat).total_seconds() / 60
    job_age_hours = (now - created_at).total_seconds() / 3600
    
    # ✅ STEP 3: Calculate processing efficiency
    processing_efficiency = 0
    if total_records > 0:
        # Efficiency = (actual new records + updated records) / total input
        effective_processing = new_records + updated_records
        processing_efficiency = (effective_processing / total_records) * 100
    
    # ✅ STEP 4: Enhanced status determination with duplicate awareness
    
    # If job shows as completed, verify with comprehensive data
    if current_status == "completed":
        # Consider duplicates in completion verification
        total_handled = new_records + updated_records + duplicate_records
        
        if total_handled >= total_records * 0.95:  # 95% tolerance
            return {
                "status": "completed",
                "reason": f"Verified complete: {new_records:,} new, {updated_records:,} updated, {duplicate_records:,} duplicates",
                "actual_subscriber_count": actual_count,
                "processing_efficiency": round(processing_efficiency, 1)
            }
        elif actual_count >= total_records * 0.90:  # Fallback check
            return {
                "status": "completed",
                "reason": f"Completed with {actual_count:,} subscribers added to list",
                "actual_subscriber_count": actual_count,
                "processing_efficiency": round(processing_efficiency, 1)
            }
        else:
            return {
                "status": "failed",
                "reason": f"Completion claimed but data mismatch: {total_handled:,}/{total_records:,} handled",
                "actual_subscriber_count": actual_count,
                "processing_efficiency": round(processing_efficiency, 1)
            }
    
    # If job is processing, enhanced progress checks
    elif current_status == "processing":
        
        # ✅ Check actual progress including duplicates
        total_handled = new_records + updated_records + duplicate_records
        data_progress_ok = (total_handled > 0 and processed_records > 0)
        reasonable_progress = (actual_count + updated_records >= processed_records * 0.7)
        
        # ✅ Time-based stuck detection with duplicate awareness
        if heartbeat_age_minutes <= 10:
            # Recent activity - still processing
            progress_text = f"{total_handled:,}/{total_records:,} handled"
            if duplicate_records > 0:
                progress_text += f" ({duplicate_records:,} duplicates)"
            
            return {
                "status": "processing",
                "reason": f"Active processing - {progress_text}",
                "actual_subscriber_count": actual_count,
                "processing_efficiency": round(processing_efficiency, 1)
            }
            
        elif heartbeat_age_minutes <= 30:
            # Moderate delay - check comprehensive progress
            if data_progress_ok and reasonable_progress:
                return {
                    "status": "processing",
                    "reason": f"Processing (slow): {total_handled:,} handled, {duplicate_records:,} duplicates",
                    "actual_subscriber_count": actual_count,
                    "processing_efficiency": round(processing_efficiency, 1)
                }
            else:
                return {
                    "status": "stuck",
                    "reason": f"Minimal progress for {heartbeat_age_minutes:.1f}m: {total_handled:,} handled",
                    "actual_subscriber_count": actual_count,
                    "stuck_duration_minutes": heartbeat_age_minutes,
                    "processing_efficiency": round(processing_efficiency, 1)
                }
        else:
            # Long delay - definitely stuck or failed
            if job_age_hours > 2:
                return {
                    "status": "failed",
                    "reason": f"Timeout after {job_age_hours:.1f}h: {total_handled:,}/{total_records:,} handled",
                    "actual_subscriber_count": actual_count,
                    "stuck_duration_minutes": heartbeat_age_minutes,
                    "processing_efficiency": round(processing_efficiency, 1)
                }
            else:
                return {
                    "status": "stuck",
                    "reason": f"Stuck for {heartbeat_age_minutes:.1f}m: {total_handled:,} handled",
                    "actual_subscriber_count": actual_count,
                    "stuck_duration_minutes": heartbeat_age_minutes,
                    "processing_efficiency": round(processing_efficiency, 1)
                }
    
    # For partially completed jobs
    elif current_status == "partially_completed":
        total_handled = new_records + updated_records + duplicate_records
        return {
            "status": "partially_completed", 
            "reason": f"Partial success: {total_handled:,}/{total_records:,} handled ({duplicate_records:,} duplicates)",
            "actual_subscriber_count": actual_count,
            "processing_efficiency": round(processing_efficiency, 1)
        }
    
    # For pending jobs
    elif current_status == "pending":
        if job_age_hours > 0.5:  # Pending for more than 30 minutes
            return {
                "status": "failed",
                "reason": f"Pending timeout ({job_age_hours:.1f}h)",
                "actual_subscriber_count": actual_count,
                "processing_efficiency": 0
            }
        else:
            return {
                "status": "pending",
                "reason": "Waiting to start",
                "actual_subscriber_count": actual_count,
                "processing_efficiency": 0
            }
    
    # For any other status, return with comprehensive info
    else:
        total_handled = new_records + updated_records + duplicate_records
        return {
            "status": current_status,
            "reason": f"Status: {current_status} - {total_handled:,} records handled",
            "actual_subscriber_count": actual_count,
            "processing_efficiency": round(processing_efficiency, 1)
        }


#  ADD THIS ENDPOINT for cleaning stuck jobs
@router.post("/jobs/cleanup-stuck")
async def cleanup_stuck_jobs():
    """Clean up stuck/stale jobs after backend restart"""
    try:
        jobs_collection = get_jobs_collection()
        
        #  FIXED: More aggressive stuck job detection
        now = datetime.utcnow()
        
        # Jobs older than 1 hour in pending/processing are considered stuck
        stuck_threshold_1h = now - timedelta(hours=1)

        
        # Also check jobs from yesterday
        yesterday = now - timedelta(days=1)
        
        stuck_jobs = await jobs_collection.find({
            "$and": [
                {"status": {"$in": ["pending", "processing"]}},
                {"$or": [
                    # Jobs older than 1 hour
                    {"updated_at": {"$lt": stuck_threshold_1h}},
                    {"created_at": {"$lt": stuck_threshold_1h}},
                    # Jobs from yesterday
                    {"created_at": {"$lt": yesterday}},
                    # Jobs with no recent heartbeat
                    {"last_heartbeat": {"$lt": stuck_threshold_1h}},
                    # Jobs with no heartbeat at all and old
                    {"$and": [
                        {"last_heartbeat": {"$exists": False}},
                        {"created_at": {"$lt": stuck_threshold_1h}}
                    ]}
                ]}
            ]
        }).to_list(100)
        
        if not stuck_jobs:
            return {
                "message": "No stuck jobs found",
                "cleaned": 0,
                "timestamp": now,
                "criteria_checked": "Jobs older than 1 hour or from yesterday"
            }
        
        # Mark stuck jobs as failed
        cleaned_count = 0
        for job in stuck_jobs:
            await jobs_collection.update_one(
                {"_id": job["_id"]},
                {"$set": {
                    "status": "failed",
                    "error_message": "Job stuck - cleaned up automatically",
                    "completion_time": now,
                    "failure_type": "stuck_cleanup",
                    "recovery_available": True,
                    "can_retry": True,
                    "cleanup_reason": "automatic_stuck_cleanup"
                }}
            )
            cleaned_count += 1
        
        logger.info(f"ðŸ§¹ Cleaned {cleaned_count} stuck jobs")
        
        return {
            "message": f"Cleaned {cleaned_count} stuck jobs",
            "cleaned": cleaned_count,
            "stuck_jobs": [
                {
                    "job_id": job.get("job_id"), 
                    "list_name": job.get("list_name"),
                    "created_at": job.get("created_at"),
                    "status_was": job.get("status")
                } for job in stuck_jobs
            ],
            "timestamp": now
        }
        
    except Exception as e:
        logger.error(f" Stuck job cleanup failed: {e}")
        return {
            "error": str(e),
            "cleaned": 0,
            "timestamp": now
        }


# ===== ALL YOUR OTHER ENDPOINTS THAT FRONTEND NEEDS =====
@router.get("/lists", dependencies=[Depends(rate_limit_check)])
@PerformanceMonitor.track_operation("list_subscriber_lists")
async def list_subscriber_lists(simple: bool = Query(False)):
    """Get subscriber lists - matches your frontend exactly"""
    start_time = time.time()
    try:
        subscribers_collection = get_subscribers_collection()

        if simple:
            pipeline = [{"$group": {"_id": "$list", "count": {"$sum": 1}}}]
            cursor = subscribers_collection.aggregate(pipeline)
            lists = []
            async for doc in cursor:
                lists.append({"name": doc["_id"], "count": doc["count"]})
        else:
            pipeline = [
                {"$group": {"_id": "$list", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            cursor = subscribers_collection.aggregate(pipeline)
            lists = []
            async for doc in cursor:
                lists.append(doc)

        duration = time.time() - start_time
        logger.info(f" Listed {len(lists)} subscriber lists in {duration:.3f}s")
        return lists

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f" List aggregation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve lists: {str(e)}")

@router.get("/search")
async def search_subscribers(
    search: str = Query(None),
    list_name: str = Query(None),
    status: str = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    search_mode: str = Query("smart")
):
    """Enhanced search for your frontend"""
    start_time = time.time()
    try:
        subscribers_collection = get_subscribers_collection()

        # Build query
        query = {}
        if search and search.strip():
            search_term = search.strip()
            if "@" in search_term and "." in search_term:
                query["email"] = {"$regex": re.escape(search_term), "$options": "i"}
            else:
                query["$or"] = [
                    {"email": {"$regex": search_term, "$options": "i"}},
                    {"standard_fields.first_name": {"$regex": search_term, "$options": "i"}},
                    {"standard_fields.last_name": {"$regex": search_term, "$options": "i"}},
                    {"list": {"$regex": search_term, "$options": "i"}}
                ]

        if list_name:
            query["list"] = list_name
        if status:
            query["status"] = status

        # Get total count and paginated results
        total_count = await subscribers_collection.count_documents(query)
        skip = (page - 1) * limit
        total_pages = math.ceil(total_count / limit) if total_count > 0 else 1

        sort_direction = -1 if sort_order == "desc" else 1
        cursor = subscribers_collection.find(query).skip(skip).limit(limit).sort(sort_by, sort_direction)

        subscribers = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            subscribers.append(doc)

        duration = time.time() - start_time

        response = {
            "subscribers": subscribers,
            "pagination": {
                "current_page": page,
                "total_pages": total_pages,
                "total": total_count,
                "limit": limit,
                "has_next": page < total_pages,
                "has_prev": page > 1
            },
            "performance": {
                "query_time": f"{duration:.3f}s",
                "strategy": search_mode,
                "results_count": len(subscribers)
            }
        }

        logger.info(f" Search completed: {len(subscribers)} results in {duration:.3f}s")
        return response

    except Exception as e:
        logger.error(f" Search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post("/bulk")
async def bulk_upload_subscribers(payload: BulkPayload):
    """Bulk upload - Convert Pydantic to dict approach"""
    start_time = time.time()
    try:
        subscribers_collection = get_subscribers_collection()
        
        # ✅ Convert Pydantic models to dictionaries if needed
        subscribers_data = []
        for sub in payload.subscribers:
            if hasattr(sub, 'model_dump'):
                # Pydantic v2
                subscribers_data.append(sub.model_dump())
            elif hasattr(sub, 'dict'):
                # Pydantic v1
                subscribers_data.append(sub.dict())
            else:
                # Already a dictionary
                subscribers_data.append(sub)
        
        total_records = len(subscribers_data)
        batch_size = SafeBatchProcessor.get_optimal_batch_size(total_records, "subscriber_upload")
        
        processed_count = 0
        failed_count = 0
        errors = []

        for i in range(0, total_records, batch_size):
            batch = subscribers_data[i:i + batch_size]

            try:
                operations = []
                for sub_data in batch:
                    # Now we can safely use .get() since sub_data is a dictionary
                    if not sub_data.get("email"):
                        failed_count += 1
                        errors.append("Missing email address")
                        continue

                    subscriber_doc = {
                        "email": sub_data["email"].lower().strip(),
                        "list": payload.list,
                        "status": sub_data.get("status", "active"),
                        "standard_fields": sub_data.standard_fields or {},
                        "custom_fields": sub_data.custom_fields or {},
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }

                    operations.append(UpdateOne(
                        {"email": subscriber_doc["email"], "list": payload.list},
                        {"$set": subscriber_doc},
                        upsert=True
                    ))

                if operations:
                    result = await subscribers_collection.bulk_write(operations, ordered=False)
                    processed_count += result.upserted_count + result.modified_count

            except Exception as batch_error:
                failed_count += len(batch)
                error_msg = f"Batch processing failed: {str(batch_error)}"
                errors.append(error_msg)
                logger.error(error_msg)

        duration = time.time() - start_time
        logger.info(f"✅ Bulk upload completed: {processed_count} processed, {failed_count} failed in {duration:.3f}s")

        return {
            "message": f"Bulk upload completed",
            "processed": processed_count,
            "failed": failed_count,
            "errors": errors[:5]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Bulk upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Bulk upload failed: {str(e)}")

@router.get("/list/{list_name}")
async def get_list_subscribers_paginated(
    list_name: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None)
):
    """Get subscribers by list with proper pagination and full field support"""
    try:
        subscribers_collection = get_subscribers_collection()

        # Build query
        query = {"list": list_name}
        if search:
            query["$or"] = [
                {"email": {"$regex": search, "$options": "i"}},
                {"standard_fields.first_name": {"$regex": search, "$options": "i"}},
                {"standard_fields.last_name": {"$regex": search, "$options": "i"}},
                {"custom_fields.list": {"$regex": search, "$options": "i"}}
            ]

        # Count total
        total_count = await subscribers_collection.count_documents(query)
        total_pages = math.ceil(total_count / limit) if total_count > 0 else 1
        skip = (page - 1) * limit

        # Projection: include everything needed
        projection = {
            "_id": 1,
            "email": 1,
            "status": 1,
            "list": 1,
            "created_at": 1,
            "updated_at": 1,
            "standard_fields": 1,
            "custom_fields": 1,
            "job_id": 1
        }

        cursor = (
            subscribers_collection
            .find(query, projection)
            .skip(skip)
            .limit(limit)
            .sort("created_at", -1)
        )

        subscribers = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])

            # Always ensure both keys exist
            doc["standard_fields"] = doc.get("standard_fields", {})
            doc["custom_fields"] = doc.get("custom_fields", {})

            subscribers.append(doc)

        return {
            "success": True,
            "subscribers": subscribers,
            "pagination": {
                "current_page": page,
                "total_pages": total_pages,
                "total": total_count,
                "page_size": limit,
                "has_more": page < total_pages,
            },
        }

    except Exception as e:
        logger.error(f"Failed to fetch subscribers for list '{list_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/lists/{list_name}", dependencies=[Depends(rate_limit_check)])
@PerformanceMonitor.track_operation("delete_list")
async def delete_list_enhanced(
    list_name: str,
    force: bool = Query(False, description="Force delete without confirmation checks"),
    reason: str = Query(None, description="Reason for deletion")
):
    """Enhanced list deletion with safety features (no backup, single-user optimized)"""
    try:
        subscribers_collection = get_subscribers_collection()
        jobs_collection = get_jobs_collection()

        logger.info(f" Enhanced deletion initiated for list '{list_name}'")

        # ===== 1. PRE-DELETION SAFETY CHECKS =====

        # Check if list exists and get count
        list_count = await subscribers_collection.count_documents({"list": list_name})
        if list_count == 0:
            raise HTTPException(status_code=404, detail=f"List '{list_name}' not found or already empty")

        # Check for active/pending jobs for this list
        active_jobs = await jobs_collection.find({
            "list_name": list_name,
            "status": {"$in": ["pending", "processing", "uploading"]}
        }).to_list(10)

        if active_jobs and not force:
            job_details = [f"Job {job['job_id']}: {job['status']}" for job in active_jobs]
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"Cannot delete list '{list_name}' - active jobs found",
                    "active_jobs": len(active_jobs),
                    "jobs": job_details,
                    "suggestion": "Wait for jobs to complete or use force=true to override"
                }
            )

        # Large list warning (unless forced)
        if list_count > 100000 and not force:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": f"Large list deletion requires confirmation",
                    "list_size": list_count,
                    "warning": f"You are about to delete {list_count:,} subscribers",
                    "suggestion": "Add force=true parameter to confirm deletion"
                }
            )

        # ===== 2. CANCEL/CLEANUP RELATED JOBS =====
        cancelled_jobs = 0
        if active_jobs:
            logger.info(f" Cancelling {len(active_jobs)} active jobs for list '{list_name}'")

            for job in active_jobs:
                await jobs_collection.update_one(
                    {"_id": job["_id"]},
                    {"$set": {
                        "status": "cancelled",
                        "cancellation_reason": f"List '{list_name}' deleted",
                        "cancelled_at": datetime.utcnow(),
                        "error_message": "Job cancelled due to list deletion"
                    }}
                )
                cancelled_jobs += 1

            # Clean up chunk files for cancelled jobs
            for job in active_jobs:
                chunk_dir = f"upload_queue/chunks/{job['job_id']}"
                if os.path.exists(chunk_dir):
                    try:
                        import shutil
                        shutil.rmtree(chunk_dir, ignore_errors=True)
                        logger.info(f" Cleaned up chunks for job {job['job_id']}")
                    except Exception as cleanup_error:
                        logger.warning(f" Chunk cleanup failed for job {job['job_id']}: {cleanup_error}")

        # ===== 3. PERFORM THE DELETION =====
        logger.info(f" Deleting {list_count:,} subscribers from list '{list_name}'")

        deletion_start = datetime.utcnow()

        # Get sample of data before deletion (for audit)
        sample_subscribers = []
        cursor = subscribers_collection.find({"list": list_name}).limit(3)
        async for sub in cursor:
            sub["_id"] = str(sub["_id"])
            sample_subscribers.append({
                "email": sub.get("email", ""),
                "standard_fields": sub.get("standard_fields", {}),
                "status": sub.get("status", "")
            })

        # Perform the actual deletion
        deletion_start = datetime.utcnow()
        delete_result = await subscribers_collection.delete_many({"list": list_name})
        deletion_time = (datetime.utcnow() - deletion_start).total_seconds()

        if delete_result.deleted_count == 0:
            raise HTTPException(status_code=500, detail="Deletion failed - no records were deleted")

        logger.info(f" Successfully deleted {delete_result.deleted_count:,} subscribers in {deletion_time:.2f}s")

        # ===== 4. AUDIT LOGGING =====
        await log_activity(
            action="list_deletion",
            entity_type="subscriber_list",
            entity_id=list_name,
            user_action=f"Deleted entire list '{list_name}' containing {delete_result.deleted_count:,} subscribers",
            before_data={
                "list_name": list_name,
                "subscriber_count": list_count,
                "sample_subscribers": sample_subscribers,
                "active_jobs_cancelled": cancelled_jobs
            },
            after_data={
                "deleted_count": delete_result.deleted_count,
                "deletion_time_seconds": deletion_time,
                "cancelled_jobs": cancelled_jobs
            },
            metadata={
                "deletion_reason": reason or "Not specified",
                "force_deletion": force,
                "deletion_method": "enhanced_bulk_delete",
                "safety_checks_performed": True,
                "large_list": list_count > 100000,
                "single_user_app": True
            }
        )

        # ===== 5. CLEANUP RELATED JOBS =====
        cleanup_result = await jobs_collection.delete_many({
            "list_name": list_name,
            "status": {"$in": ["completed", "failed", "cancelled"]}
        })

        logger.info(f" Cleaned up {cleanup_result.deleted_count} related job records")

        # ===== 6. SIMPLIFIED RESPONSE =====
        response = {
            "success": True,
            "message": f"List '{list_name}' deleted successfully",
            "deletion_summary": {
                "list_name": list_name,
                "subscribers_deleted": delete_result.deleted_count,
                "deletion_time_seconds": round(deletion_time, 2),
                "deletion_speed_per_second": int(delete_result.deleted_count / deletion_time) if deletion_time > 0 else 0,
                "deletion_timestamp": deletion_start.isoformat(),
                "reason": reason or "Not specified"
            },
            "cleanup_actions": {
                "jobs_cancelled": cancelled_jobs,
                "chunk_files_cleaned": len(active_jobs) if active_jobs else 0,
                "job_records_cleaned": cleanup_result.deleted_count,
                "audit_logged": True
            },
            "performance": {
                "records_per_second": int(delete_result.deleted_count / deletion_time) if deletion_time > 0 else 0,
                "was_large_operation": list_count > 100000,
                "required_force": bool(active_jobs) and force
            }
        }

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"âŒ Enhanced list deletion failed for '{list_name}': {e}")

        # Log the failure for audit
        try:
            await log_activity(
                action="list_deletion_failed",
                entity_type="subscriber_list",
                entity_id=list_name,
                user_action=f"Failed to delete list '{list_name}'",
                metadata={
                    "error": str(e),
                    "failure_reason": reason,
                    "single_user_app": True
                }
            )
        except:
            pass

        raise HTTPException(status_code=500, detail=f"List deletion failed: {str(e)}")


@router.post("/", dependencies=[Depends(rate_limit_check)])
@PerformanceMonitor.track_operation("add_subscriber")
async def add_single_subscriber(subscriber: SubscriberIn, request: Request):
    """Add single subscriber for your frontend"""
    try:
        from schemas.subscriber_schema import SubscriberIn
        
        # Validate with Pydantic
        validated = SubscriberIn(**subscriber)

        subscribers_collection = get_subscribers_collection()
        # email = subscriber.email.strip().lower()
        email = validated.email.strip().lower()


        existing = await subscribers_collection.find_one(
            {"email": email, "list": validated.list}
        )
        if existing:
            raise HTTPException(
                status_code=400, detail="Subscriber already exists in this list"
            )

        doc = {
            "list": validated.list,
            "email": email,
            "status": validated.status or "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "standard_fields": validated.standard_fields or {},
            "custom_fields": validated.custom_fields or {},
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
                "ip_address": str(request.client.host) if request.client else "unknown",
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
    """Update subscriber for your frontend"""
    try:
        subscribers_collection = get_subscribers_collection()

        if not ObjectId.is_valid(subscriber_id):
            raise HTTPException(status_code=400, detail="Invalid subscriber ID")

        existing = await subscribers_collection.find_one({"_id": ObjectId(subscriber_id)})
        if not existing:
            raise HTTPException(status_code=404, detail="Subscriber not found")

        update_doc = {
            "email": subscriber.email.lower().strip(),
            "list": subscriber.list,
            "status": subscriber.status or "active",
            "standard_fields": subscriber.standard_fields or {},
            "custom_fields": subscriber.custom_fields or {},
            "updated_at": datetime.utcnow()
        }

        result = await subscribers_collection.update_one(
            {"_id": ObjectId(subscriber_id)},
            {"$set": update_doc}
        )

        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Subscriber not found")

        await log_activity(
            action="update",
            entity_type="subscriber",
            entity_id=subscriber_id,
            user_action=f"Updated subscriber {subscriber.email}",
            before_data={
                "email": existing.get("email"),
                "list": existing.get("list"),
                "status": existing.get("status"),
                "standard_fields": existing.get("standard_fields", {}),
                "custom_fields": existing.get("custom_fields", {}),
            },
            after_data={
                "email": subscriber.email,
                "list": subscriber.list,
                "status": subscriber.status,
                "standard_fields": subscriber.standard_fields or {},
                "custom_fields": subscriber.custom_fields or {},
            },
            metadata={
                "ip_address": str(request.client.host) if request.client else "unknown",
            },
        )

        return {"message": "Subscriber updated successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update subscriber failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{subscriber_id}")
async def delete_subscriber(subscriber_id: str, request: Request):
    """Delete subscriber for your frontend"""
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
                "ip_address": str(request.client.host) if request.client else "unknown",
                "list_name": subscriber.get("list"),
                "email": subscriber.get("email"),
            },
        )

        return {"message": "Subscriber deleted successfully"}

    except Exception as e:
        logger.error(f"Delete subscriber failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{subscriber_id}/status")
async def update_subscriber_status(subscriber_id: str, status: str = Query(...), request: Request = None):
    """Update subscriber status for your frontend"""
    try:
        subscribers_collection = get_subscribers_collection()

        if not ObjectId.is_valid(subscriber_id):
            raise HTTPException(status_code=400, detail="Invalid subscriber ID")

        result = await subscribers_collection.update_one(
            {"_id": ObjectId(subscriber_id)},
            {"$set": {"status": status, "updated_at": datetime.utcnow()}}
        )

        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Subscriber not found")

        return {"message": f"Subscriber status updated to {status}"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update status failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/lists/{list_name}/export")
async def export_list_csv(list_name: str, request: Request):
    """Export list as CSV for your frontend"""
    try:
        subscribers_collection = get_subscribers_collection()
        cursor = subscribers_collection.find({"list": list_name})

        output = io.StringIO()
        writer = csv.writer(output)

        # Collect all possible columns
        standard_keys = set()
        custom_keys = set()
        docs = []
        async for doc in cursor:
            docs.append(doc)
            standard_keys.update((doc.get("standard_fields") or {}).keys())
            custom_keys.update((doc.get("custom_fields") or {}).keys())

        # Define header
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
                "ip_address": str(request.client.host) if request.client else "unknown",
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

@router.post("/jobs/{job_id}/force-retry")
async def retry_failed_job(job_id: str, request: Request, background_tasks: BackgroundTasks):
    """Retry failed job for your frontend"""
    try:
        jobs_collection = get_jobs_collection()
        job = await jobs_collection.find_one({"_id": job_id})
        
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if job.get("status") != "failed":
            raise HTTPException(status_code=400, detail="Only failed jobs can be retried")
        
        # Reset job status
        await jobs_collection.update_one(
            {"_id": job_id},
            {"$set": {
                "status": "pending",
                "updated_at": datetime.utcnow(),
                "retry_count": job.get("retry_count", 0) + 1
            }}
        )
        
        return {"message": "Job retry initiated"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Retry job failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retry job")

# ===== FILE-FIRST RECOVERY ENDPOINTS =====
@router.get("/upload-queue/status")
async def get_upload_queue_status():
    """Get upload queue status for file-first system"""
    try:
        if PRODUCTION_FEATURES.get('file_first_recovery', False):
            return simple_file_recovery.get_status()
        else:
            return {"error": "File-first recovery not available", "queued": 0, "processing": 0, "completed": 0}
    except Exception as e:
        return {"error": str(e)}

@router.post("/upload-queue/retry")
async def manual_retry_uploads():
    """Manually retry stuck/failed uploads"""
    try:
        if PRODUCTION_FEATURES.get('file_first_recovery', False):
            result = await simple_file_recovery.manual_retry()
            return result
        else:
            return {"error": "File-first recovery not available"}
    except Exception as e:
        logger.error(f"Manual retry failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== UTILITY FUNCTIONS =====
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
        logger.info(f"AUDIT: {action} - {user_action}")

    except Exception as e:
        logger.error(f"Failed to log activity: {e}")
 
# ===== MISSING UTILITY FUNCTIONS =====
def convert_objectids_to_strings(obj):
    """Recursively convert all ObjectId instances to strings"""
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, dict):
        return {key: convert_objectids_to_strings(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_objectids_to_strings(item) for item in obj]
    else:
        return obj

async def get_estimated_count(collection, query, max_limit=None):
    """Get estimated count with performance optimization"""
    try:
        if not max_limit or max_limit <= 10000:
            return await collection.count_documents(query, limit=max_limit)
        else:
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
                estimated = (result[0]["count"] / sample_size) * (max_limit or 100000)
                return min(estimated, max_limit or estimated)
            return 0
    except Exception as e:
        logger.error(f"Count estimation failed: {e}")
        return 0

def analyze_search_specificity(search_term: str) -> str:
    """Analyze search term to determine query strategy"""
    if not search_term:
        return "none"
        
    # Email pattern
    if "@" in search_term and "." in search_term:
        return "exact"
        
    # ObjectId pattern  
    if len(search_term) == 24 and all(c in "0123456789abcdef" for c in search_term.lower()):
        return "exact"
        
    # Phone number pattern
    if len(search_term) >= 10 and search_term.replace("(", "").replace(")", "").replace("-", "").replace(" ", "").replace("+", "").replace(".", "").isdigit():
        return "exact"
        
    # Long specific terms
    if len(search_term) >= 8:
        return "specific"
        
    # Medium terms 
    if len(search_term) >= 4:
        return "general"
        
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
            {"standard_fields.last_name": {"$regex": search_term, "$options": "i"}}
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
            {"custom_fields.city": {"$regex": search_term, "$options": "i"}}
        ]
        sort_order = [("email", 1)]
    
    return query, sort_order

@router.post("/analyze-fields")
async def analyze_fields(request: dict):
    """Analyze subscriber data to find available fields for field mapping"""
    list_ids = request.get("listIds", [])
    if not list_ids:
        return {"universal": ["email"], "standard": [], "custom": []}
    
    try:
        subscribers_collection = get_subscribers_collection()
        
        # Analyze actual subscriber data to find available fields
        pipeline = [
            {"$match": {"list": {"$in": list_ids}}},
            {
                "$group": {
                    "_id": None,
                    "standard_field_keys": {"$addToSet": {"$map": {"input": {"$objectToArray": "$standard_fields"}, "as": "field", "in": "$$field.k"}}},
                    "custom_field_keys": {"$addToSet": {"$map": {"input": {"$objectToArray": "$custom_fields"}, "as": "field", "in": "$$field.k"}}}
                }
            }
        ]
        
        result = await subscribers_collection.aggregate(pipeline).to_list(1)
        
        if not result:
            return {"universal": ["email"], "standard": [], "custom": []}
        
        # Flatten the nested arrays and remove duplicates  
        standard_fields = set()
        custom_fields = set()
        
        for std_array in result[0].get("standard_field_keys", []):
            if std_array:  # Check if array is not None
                standard_fields.update(std_array)
                
        for cust_array in result[0].get("custom_field_keys", []):
            if cust_array:  # Check if array is not None
                custom_fields.update(cust_array)
        
        return {
            "universal": ["email"],  # Email is always universal
            "standard": list(standard_fields), 
            "custom": list(custom_fields)
        }
        
    except Exception as e:
        logger.error(f"Field analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Field analysis failed: {str(e)}")

# ===== ADD THIS MISSING ENDPOINT =====
@router.post("/recovery/manual-retry")
async def manual_retry():
    """Manual retry system for recovery"""
    try:
        # Simple implementation - you can enhance this
        return {
            "success": True,
            "message": "Manual retry completed",
            "timestamp": datetime.utcnow()
        }
    except Exception as e:
        logger.error(f"Manual retry failed: {e}")
        return {
            "success": False,
            "message": str(e),
            "timestamp": datetime.utcnow()
        }
    

@router.delete("/jobs/clear-all")
@PerformanceMonitor.track_operation("clear_all_jobs")
async def clear_all_jobs():
    """Clear completed/failed jobs"""
    try:
        jobs_collection = get_jobs_collection()
        cutoff = datetime.utcnow() - timedelta(hours=24)

        delete_filter = {
            "$or": [
                {"status": {"$in": ["completed", "failed"]}},
                {"updated_at": {"$lt": cutoff}},
            ]
        }

        match_count = await jobs_collection.count_documents(delete_filter)
        logger.info(f"Matched {match_count} jobs (cutoff: {cutoff})")

        result = await jobs_collection.delete_many(delete_filter)
        logger.info(f"🧹 Deleted {result.deleted_count} jobs older than 24h or completed/failed")

        return {"deleted_count": result.deleted_count}

        
    except Exception as e:
        logger.error(f"Clear jobs failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
   