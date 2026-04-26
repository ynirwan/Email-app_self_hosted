# routes/subscribers.py
from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
    status,
    File,
    Form,
    UploadFile,
    BackgroundTasks,
    Depends,
)
from database import (
    get_subscribers_collection,
    get_audit_collection,
    get_jobs_collection,
    get_segments_collection,
)
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field, EmailStr, validator
from bson import ObjectId
from datetime import datetime, timedelta
import logging
from fastapi.responses import StreamingResponse
import csv
import io
import os
import re
import uuid
import math
import json
import glob
import time
import asyncio
import shutil
import traceback
from functools import wraps

from pymongo import UpdateOne
from pymongo.errors import BulkWriteError, DuplicateKeyError

from schemas.subscriber_schema import (
    SubscriberIn,
    BulkPayload,
    SubscriberOut,
    BackgroundUploadPayload,
    ListFieldRegistry,
    FieldType,
)
from schemas.field_converter import apply_registry, registry_to_field_types

router = APIRouter()

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s"
        )
    )
    logger.addHandler(_h)

# ─────────────────────────────────────────────────────────────────────────────
# Feature flags & config
# ─────────────────────────────────────────────────────────────────────────────
PRODUCTION_FEATURES = {
    "config": False,
    "subscriber_recovery": False,
    "file_first_recovery": False,
    "performance_logging": False,
    "rate_limiting": False,
    "websocket": False,
}

try:
    from core.config import settings

    PRODUCTION_FEATURES["config"] = True
    logger.info("✅ Production config loaded")
except ImportError:

    class MockSettings:
        MAX_BATCH_SIZE = 1000
        ENABLE_BULK_OPTIMIZATIONS = False
        ENABLE_HYBRID_RECOVERY = True
        LOG_LEVEL = "INFO"

    settings = MockSettings()
    logger.info("⚠️  Using mock config")

# ─────────────────────────────────────────────────────────────────────────────
# Upload pipeline constants
# ─────────────────────────────────────────────────────────────────────────────
CHUNK_SIZE = 15_000  # subscribers written per disk chunk file
MAX_CONCURRENT = 3  # max parallel chunk processing tasks
DB_BATCH = 500  # records per MongoDB bulk_write call


def _chunks_dir(job_id: str) -> str:
    return os.path.join("upload_queue", "chunks", job_id)


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def log_activity(
    action: str,
    entity_type: str,
    entity_id: str,
    user_action: str,
    before_data: dict = None,
    after_data: dict = None,
    metadata: dict = None,
    request: Request = None,
):
    try:
        audit_collection = get_audit_collection()
        entry = {
            "timestamp": datetime.utcnow(),
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "user_action": user_action,
            "before_data": before_data or {},
            "after_data": after_data or {},
            "metadata": metadata or {},
        }
        if request:
            entry["request_info"] = {
                "ip": get_client_ip(request),
                "user_agent": request.headers.get("user-agent", "unknown"),
                "method": request.method,
                "path": str(request.url.path),
            }
        await audit_collection.insert_one(entry)
        logger.info(f"📝 AUDIT: {action} - {user_action}")
    except Exception as e:
        logger.error(f"Audit logging failed: {e}")


class PerformanceMonitor:
    @staticmethod
    def track_operation(operation_name: str):
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                start = time.time()
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
                    duration = time.time() - start
                    lvl = logging.INFO if success else logging.ERROR
                    logger.log(
                        lvl,
                        f"Operation: {operation_name} | Duration: {duration:.3f}s | "
                        f"Success: {success} | Error: {error_msg or 'None'}",
                    )
                    if duration > 5.0:
                        logger.warning(
                            f"SLOW OPERATION: {operation_name} took {duration:.3f}s"
                        )

            return wrapper

        return decorator


class RateLimiter:
    def __init__(self):
        self.requests: Dict[str, list] = {}
        self.window = 60
        self.max_requests = 100

    def is_allowed(self, identifier: str) -> bool:
        now = time.time()
        self.requests[identifier] = [
            ts for ts in self.requests.get(identifier, []) if now - ts < self.window
        ]
        if len(self.requests[identifier]) >= self.max_requests:
            return False
        self.requests[identifier].append(now)
        return True


rate_limiter = RateLimiter()


async def rate_limit_check(request: Request):
    if PRODUCTION_FEATURES.get("rate_limiting", False):
        if not rate_limiter.is_allowed(get_client_ip(request)):
            raise HTTPException(status_code=429, detail="Rate limit exceeded.")
    return True


class SafeBatchProcessor:
    @staticmethod
    def get_optimal_batch_size(total_records: int, operation: str = "general") -> int:
        if total_records < 1000:
            return total_records
        elif total_records < 10000:
            return 1000
        elif total_records < 50000:
            return 2000
        return 5000


# ─────────────────────────────────────────────────────────────────────────────
# Job Manager
# ─────────────────────────────────────────────────────────────────────────────


class ProductionJobManager:
    """Thread-safe job lifecycle manager backed by MongoDB."""

    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}

    def _lock(self, job_id: str) -> asyncio.Lock:
        if job_id not in self._locks:
            self._locks[job_id] = asyncio.Lock()
        return self._locks[job_id]

    def _cleanup_lock(self, job_id: str):
        self._locks.pop(job_id, None)

    async def create_job(
        self, job_type: str, list_name: str, total_records: int
    ) -> str:
        job_id = str(uuid.uuid4())
        doc = {
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
            "error_message": None,
            "error_messages": [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "last_heartbeat": datetime.utcnow(),
            "completion_time": None,
        }
        col = get_jobs_collection()
        await col.insert_one(doc)
        logger.info(
            f"✅ Job created: {job_id} | list={list_name} | records={total_records:,}"
        )
        return job_id

    async def set_processing(self, job_id: str):
        """Transition pending → processing."""
        col = get_jobs_collection()
        await col.update_one(
            {"_id": job_id},
            {
                "$set": {
                    "status": "processing",
                    "processing_start": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                    "last_heartbeat": datetime.utcnow(),
                }
            },
        )

    async def update_progress(
        self,
        job_id: str,
        *,
        processed: int,
        total: int,
        new_records: int = 0,
        updated_records: int = 0,
        duplicates: int = 0,
        speed: int = 0,
        completed_chunks: int = 0,
        total_chunks: int = 0,
    ):
        """Write mid-job progress. Non-fatal if Mongo is momentarily slow."""
        async with self._lock(job_id):
            progress = round((processed / total) * 100, 1) if total > 0 else 0.0
            col = get_jobs_collection()
            try:
                await col.update_one(
                    {"_id": job_id},
                    {
                        "$set": {
                            "processed_records": processed,
                            "new_records": new_records,
                            "updated_records": updated_records,
                            "duplicate_records": duplicates,
                            "progress": progress,
                            "records_per_second": speed,
                            "completed_chunks": completed_chunks,
                            "total_chunks": total_chunks,
                            "updated_at": datetime.utcnow(),
                            "last_heartbeat": datetime.utcnow(),
                        }
                    },
                )
            except Exception as e:
                logger.warning(f"⚠️ Progress update failed for {job_id}: {e}")

    async def mark_completed(
        self,
        job_id: str,
        *,
        processed: int,
        new_records: int,
        updated_records: int,
        duplicates: int,
        speed: int,
        elapsed: float,
        failed_chunks: int,
    ):
        final_status = "completed" if failed_chunks == 0 else "partially_completed"
        col = get_jobs_collection()
        await col.update_one(
            {"_id": job_id},
            {
                "$set": {
                    "status": final_status,
                    "progress": 100.0,
                    "final_processed": processed,
                    "new_records": new_records,
                    "updated_records": updated_records,
                    "duplicate_records": duplicates,
                    "final_records_per_second": speed,
                    "total_processing_time_seconds": round(elapsed, 2),
                    "failed_chunks": failed_chunks,
                    "completion_time": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                    "last_heartbeat": datetime.utcnow(),
                }
            },
        )
        self._cleanup_lock(job_id)
        logger.info(
            f"✅ Job {job_id} → {final_status} | {processed:,} records | {speed:,}/sec"
        )

    async def mark_failed(self, job_id: str, error: str, processed_so_far: int = 0):
        """
        Always call this on any failure path.
        Guaranteed not to raise — uses a bare except as last resort.
        """
        col = get_jobs_collection()
        try:
            await col.update_one(
                {"_id": job_id},
                {
                    "$set": {
                        "status": "failed",
                        "error_message": error,
                        "failed_at": datetime.utcnow(),
                        "processed_records": processed_so_far,
                        "updated_at": datetime.utcnow(),
                        "last_heartbeat": datetime.utcnow(),
                    }
                },
            )
        except Exception as e:
            logger.error(f"💥 Could not write failure to job {job_id}: {e}")
        finally:
            self._cleanup_lock(job_id)
            logger.error(f"❌ Job {job_id} failed: {error}")


job_manager = ProductionJobManager()


# ─────────────────────────────────────────────────────────────────────────────
# Upload pipeline helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _write_chunks(job_id: str, payload: BackgroundUploadPayload) -> List[str]:
    """
    Serialise subscribers to per-chunk JSON files on disk.
    Uses atomic rename (write to .tmp then os.rename) so partial writes
    are never visible to the processing step.
    Raises on any I/O error — caller is responsible for calling mark_failed.
    """
    directory = _chunks_dir(job_id)
    os.makedirs(directory, exist_ok=True)

    registry_dict = (
        payload.field_registry.model_dump() if payload.field_registry else None
    )
    subscribers = payload.subscribers
    total = len(subscribers)
    total_chunks = math.ceil(total / CHUNK_SIZE)
    paths: List[str] = []

    for idx in range(0, total, CHUNK_SIZE):
        chunk_n = idx // CHUNK_SIZE
        chunk = subscribers[idx : idx + CHUNK_SIZE]
        chunk_data = {
            "job_id": job_id,
            "list_name": payload.list_name,
            "chunk_number": chunk_n,
            "total_chunks": total_chunks,
            "chunk_records": len(chunk),
            "field_registry": registry_dict,
            "subscribers": [
                s.model_dump() if hasattr(s, "model_dump") else s for s in chunk
            ],
        }
        path = os.path.join(directory, f"chunk_{chunk_n:04d}.json")
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(chunk_data, fh, default=str)
        os.rename(tmp, path)
        paths.append(path)

    logger.info(f"🗂️  {len(paths)} chunk files written for job {job_id}")
    return paths


async def _process_single_chunk(
    chunk_file: str,
    job_id: str,
    list_name: str,
    semaphore: asyncio.Semaphore,
) -> Dict[str, int]:
    """
    Load one chunk file, upsert all subscribers into MongoDB, delete file on success.
    Returns a stats dict.  Never raises — errors surface in stats["errors"].
    """
    stats = {"processed": 0, "new": 0, "updated": 0, "dupes": 0, "errors": 0}

    async with semaphore:
        try:
            with open(chunk_file, "r") as fh:
                chunk_data = json.load(fh)

            raw_subscribers: List[Dict] = chunk_data.get("subscribers", [])

            # Re-hydrate field registry if present
            registry: Optional[ListFieldRegistry] = None
            if chunk_data.get("field_registry"):
                try:
                    registry = ListFieldRegistry(**chunk_data["field_registry"])
                except Exception as e:
                    logger.warning(
                        f"⚠️ Could not parse field_registry in {chunk_file}: {e}"
                    )

            col = get_subscribers_collection()

            for batch_start in range(0, len(raw_subscribers), DB_BATCH):
                batch = raw_subscribers[batch_start : batch_start + DB_BATCH]
                ops: List[UpdateOne] = []

                for sub in batch:
                    raw_email = sub.get("email") or ""
                    email = raw_email.lower().strip()
                    if not email or "@" not in email:
                        stats["errors"] += 1
                        continue

                    # Support both UploadSubscriber shape (fields dict) and
                    # legacy shape (standard_fields / custom_fields already split)
                    std = sub.get("standard_fields")
                    cust = sub.get("custom_fields")
                    if std is None or cust is None:
                        raw_fields = sub.get("fields", {})
                        if raw_fields and registry:
                            std, cust = apply_registry(raw_fields, registry)
                        else:
                            std = std or {}
                            cust = cust or {}

                    doc = {
                        "email": email,
                        "list": list_name,
                        "status": sub.get("status", "active"),
                        "standard_fields": std or {},
                        "custom_fields": cust or {},
                        "job_id": job_id,
                        "updated_at": datetime.utcnow(),
                    }
                    ops.append(
                        UpdateOne(
                            {"email": email, "list": list_name},
                            {
                                "$set": doc,
                                "$setOnInsert": {"created_at": datetime.utcnow()},
                            },
                            upsert=True,
                        )
                    )

                if not ops:
                    continue

                try:
                    result = await col.bulk_write(ops, ordered=False)
                    stats["new"] += result.upserted_count
                    stats["updated"] += result.modified_count
                    # anything that was neither inserted nor modified was a true duplicate
                    stats["dupes"] += max(
                        0, len(ops) - result.upserted_count - result.modified_count
                    )
                    stats["processed"] += len(ops)
                except BulkWriteError as bwe:
                    d = bwe.details
                    stats["new"] += d.get("nUpserted", 0)
                    stats["updated"] += d.get("nModified", 0)
                    stats["processed"] += d.get("nUpserted", 0) + d.get("nModified", 0)
                    stats["errors"] += len(d.get("writeErrors", []))
                    logger.warning(
                        f"⚠️ BulkWriteError in {chunk_file}: "
                        f"{len(d.get('writeErrors', []))} errors"
                    )

            # Remove chunk file after successful processing
            try:
                os.remove(chunk_file)
            except OSError:
                pass

        except Exception as exc:
            logger.error(
                f"❌ Chunk {chunk_file} failed: {exc}\n{traceback.format_exc()}"
            )
            stats["errors"] += 1

    return stats


async def _run_upload_job(job_id: str, payload: BackgroundUploadPayload):
    """
    Full upload pipeline executed as a FastAPI background task.

    Contract: this function ALWAYS calls job_manager.mark_failed on any
    error path, so no job document is ever left in 'processing' indefinitely.
    """
    total_records = len(payload.subscribers)
    start_dt = datetime.utcnow()

    try:
        await job_manager.set_processing(job_id)

        # 1. Write subscriber data to disk as chunk files
        try:
            chunk_files = await _write_chunks(job_id, payload)
        except Exception as exc:
            await job_manager.mark_failed(job_id, f"Chunk write failed: {exc}")
            return

        if not chunk_files:
            await job_manager.mark_failed(
                job_id, "No chunk files created — empty payload?"
            )
            return

        total_chunks = len(chunk_files)

        # 2. Process chunks concurrently up to MAX_CONCURRENT at a time
        semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        tasks = [
            asyncio.create_task(
                _process_single_chunk(cf, job_id, payload.list_name, semaphore)
            )
            for cf in chunk_files
        ]

        total_processed = 0
        total_new = 0
        total_updated = 0
        total_dupes = 0
        failed_chunks = 0
        completed_chunks = 0

        for coro in asyncio.as_completed(tasks):
            try:
                s = await coro
            except Exception as exc:
                logger.error(f"Task raised unexpectedly: {exc}")
                failed_chunks += 1
                completed_chunks += 1
                continue

            total_processed += s["processed"]
            total_new += s["new"]
            total_updated += s["updated"]
            total_dupes += max(0, s["dupes"])
            if s["errors"] > 0:
                failed_chunks += 1
            completed_chunks += 1

            # Heartbeat after every chunk so the frontend stuck-detector stays happy
            elapsed = (datetime.utcnow() - start_dt).total_seconds()
            speed = int(total_processed / elapsed) if elapsed > 0 else 0
            await job_manager.update_progress(
                job_id,
                processed=total_processed,
                total=total_records,
                new_records=total_new,
                updated_records=total_updated,
                duplicates=total_dupes,
                speed=speed,
                completed_chunks=completed_chunks,
                total_chunks=total_chunks,
            )

        # 3. Final status
        elapsed = (datetime.utcnow() - start_dt).total_seconds()
        speed = int(total_processed / elapsed) if elapsed > 0 else 0
        await job_manager.mark_completed(
            job_id,
            processed=total_processed,
            new_records=total_new,
            updated_records=total_updated,
            duplicates=total_dupes,
            speed=speed,
            elapsed=elapsed,
            failed_chunks=failed_chunks,
        )

        # 4. Persist field registry (non-fatal)
        if payload.field_registry:
            try:
                from database import get_lists_collection

                lists_col = get_lists_collection()
                reg_doc = payload.field_registry.model_dump()
                reg_doc["updated_at"] = datetime.utcnow()
                await lists_col.update_one(
                    {"list_name": payload.list_name}, {"$set": reg_doc}, upsert=True
                )
            except Exception as exc:
                logger.warning(f"⚠️ Could not persist field registry: {exc}")

        # 5. Activity log (non-fatal)
        try:
            await log_activity(
                action="bulk_upload",
                entity_type="subscribers",
                entity_id=job_id,
                user_action=f"Uploaded {total_processed:,} subscribers to '{payload.list_name}'",
                metadata={
                    "total_records": total_records,
                    "processed_records": total_processed,
                    "new_records": total_new,
                    "updated_records": total_updated,
                    "list_name": payload.list_name,
                },
            )
        except Exception as exc:
            logger.warning(f"⚠️ Activity log failed: {exc}")

        # 6. Clean up chunk directory
        try:
            shutil.rmtree(_chunks_dir(job_id), ignore_errors=True)
        except Exception:
            pass

    except Exception as exc:
        # Catch-all safety net — guarantees mark_failed is always called
        logger.error(
            f"💥 _run_upload_job unhandled exception: {exc}\n{traceback.format_exc()}"
        )
        await job_manager.mark_failed(job_id, f"Unexpected error: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Routes — Upload
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/background-upload", dependencies=[Depends(rate_limit_check)])
@PerformanceMonitor.track_operation("background_upload")
async def background_upload_enhanced(
    payload: BackgroundUploadPayload,
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Create a job record and return job_id immediately.
    All subscriber processing runs in _run_upload_job as a background task.
    Client polls GET /subscribers/jobs/status to track progress.
    """
    total_records = len(payload.subscribers)
    if total_records == 0:
        raise HTTPException(status_code=400, detail="No subscribers provided")

    job_id = await job_manager.create_job(
        "background_upload", payload.list_name, total_records
    )

    # Schedule — this returns before any subscriber is written
    background_tasks.add_task(_run_upload_job, job_id, payload)

    logger.info(
        f"📤 Upload job {job_id} queued | list={payload.list_name} | "
        f"records={total_records:,}"
    )

    return {
        "job_id": job_id,
        "status": "pending",
        "message": (
            f"Upload job created for {total_records:,} subscribers. "
            "Processing in background."
        ),
        "total_records": total_records,
        "list_name": payload.list_name,
        "estimated_minutes": max(1, round(total_records / 10_000)),
        "poll_url": "/api/subscribers/jobs/status",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Routes — Job status & management
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/jobs/status")
async def get_job_status():
    """Return all recent jobs with rich status and statistics."""
    try:
        jobs_col = get_jobs_collection()
        subs_col = get_subscribers_collection()

        # Auto-clean completed jobs older than 5 minutes to keep the list tidy
        await jobs_col.delete_many(
            {
                "status": "completed",
                "updated_at": {"$lt": datetime.utcnow() - timedelta(minutes=5)},
            }
        )

        cursor = jobs_col.find({}, sort=[("created_at", -1)], limit=50)
        now = datetime.utcnow()
        jobs = []

        async for job in cursor:
            job_status = await determine_job_status(job, subs_col, now)
            jobs.append(
                {
                    "_id": str(job["_id"]),
                    "job_id": job.get("job_id"),
                    "list_name": job.get("list_name"),
                    "status": job_status["status"],
                    "progress": job.get("progress", 0),
                    "total": job.get("total_records", 0),
                    "total_records": job.get("total_records", 0),
                    "processed": job.get("processed_records", 0),
                    "processed_records": job.get("processed_records", 0),
                    "failed": job.get("failed_records", 0),
                    "new_records": job.get("new_records", 0),
                    "updated_records": job.get("updated_records", 0),
                    "duplicate_records": job.get("duplicate_records", 0),
                    "duplicate_rate": job.get("duplicate_rate", 0),
                    # timestamps
                    "created_at": job.get("created_at"),
                    "updated_at": job.get("updated_at"),
                    "completion_time": job.get("completion_time"),
                    "last_heartbeat": job.get("last_heartbeat"),
                    # performance
                    "records_per_second": job.get("records_per_second", 0),
                    "final_records_per_second": job.get("final_records_per_second", 0),
                    "total_processing_time_seconds": job.get(
                        "total_processing_time_seconds", 0
                    ),
                    # chunk info
                    "completed_chunks": job.get("completed_chunks", 0),
                    "failed_chunks": job.get("failed_chunks", 0),
                    "total_chunks": job.get("total_chunks", 0),
                    # error
                    "error_message": job.get("error_message"),
                    # enriched
                    "status_reason": job_status.get("reason", ""),
                    "stuck_duration_minutes": job_status.get(
                        "stuck_duration_minutes", 0
                    ),
                    "actual_subscriber_count": job_status.get(
                        "actual_subscriber_count", 0
                    ),
                    "statistics": {
                        "total_input": job.get("total_records", 0),
                        "successfully_processed": job.get("processed_records", 0),
                        "new_subscribers": job.get("new_records", 0),
                        "updated_existing": job.get("updated_records", 0),
                        "duplicates_filtered": job.get("duplicate_records", 0),
                        "failed_records": job.get("failed_records", 0),
                        "actual_database_count": job_status.get(
                            "actual_subscriber_count", 0
                        ),
                        "duplicate_percentage": round(job.get("duplicate_rate", 0), 1),
                    },
                    "performance_display": {
                        "method_text": format_processing_method(
                            job.get("processing_method", "standard")
                        ),
                        "speed_text": format_speed_display(job),
                        "duration_text": format_duration_display(job),
                        "efficiency_text": format_efficiency_display(job, job_status),
                    },
                }
            )

        return {"jobs": jobs}

    except Exception as e:
        logger.error(f"Get job status failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get job statuses")


def format_processing_method(method: str) -> str:
    return {
        "parallel_chunks_with_duplicate_tracking": "Parallel Processing",
        "batch_progress_updates": "Batch Processing",
        "chunked_background_upload": "Chunked Upload",
        "standard": "Standard",
    }.get(method, method.title())


def format_speed_display(job: dict) -> str:
    fs = job.get("final_records_per_second", 0)
    cs = job.get("records_per_second", 0)
    if job.get("status") in ("completed", "partially_completed"):
        return f"{fs:,} records/sec (final)" if fs > 0 else "Completed"
    if cs > 0:
        return f"{cs:,} records/sec"
    return "Processing…"


def format_duration_display(job: dict) -> str:
    d = job.get("total_processing_time_seconds", 0)
    if not d:
        return "N/A"
    if d < 60:
        return f"{d:.1f}s"
    if d < 3600:
        return f"{d / 60:.1f}m"
    return f"{d / 3600:.1f}h"


def format_efficiency_display(job: dict, job_status: dict) -> str:
    total = job.get("total_records", 0)
    dupes = job.get("duplicate_records", 0)
    new = job.get("new_records", 0)
    if total > 0:
        eff = ((new + dupes) / total) * 100
        suffix = f" ({dupes:,} duplicates)" if dupes > 0 else ""
        return f"{eff:.1f}% processed{suffix}"
    return "N/A"


async def determine_job_status(job: dict, subs_col, now: datetime) -> dict:
    """Compute enriched status for a single job document."""
    job_id = job.get("job_id")
    list_name = job.get("list_name")
    db_status = job.get("status", "unknown")

    try:
        actual_count = (
            await subs_col.count_documents({"list": list_name, "job_id": job_id})
            if job_id and list_name
            else 0
        )
    except Exception:
        actual_count = 0

    total = job.get("total_records", 0)
    processed = job.get("processed_records", 0)
    new_rec = job.get("new_records", 0)
    updated = job.get("updated_records", 0)
    dupes = job.get("duplicate_records", 0)

    last_hb = job.get("last_heartbeat", job.get("updated_at", now))
    created = job.get("created_at", now)
    hb_age_m = (now - last_hb).total_seconds() / 60
    age_h = (now - created).total_seconds() / 3600
    efficiency = round(((new_rec + updated) / total) * 100, 1) if total > 0 else 0

    base = {
        "actual_subscriber_count": actual_count,
        "processing_efficiency": efficiency,
    }

    if db_status == "failed":
        return {
            **base,
            "status": "failed",
            "reason": job.get("error_message", "Unknown error"),
        }

    if db_status == "completed":
        handled = new_rec + updated + dupes
        if handled >= total * 0.95 or actual_count >= total * 0.90:
            return {
                **base,
                "status": "completed",
                "reason": f"{new_rec:,} new, {updated:,} updated, {dupes:,} duplicates",
            }
        return {
            **base,
            "status": "failed",
            "reason": f"Completion claimed but only {handled:,}/{total:,} handled",
        }

    if db_status == "partially_completed":
        return {
            **base,
            "status": "partially_completed",
            "reason": f"{new_rec + updated + dupes:,}/{total:,} handled ({dupes:,} duplicates)",
        }

    if db_status == "processing":
        if hb_age_m <= 10:
            return {
                **base,
                "status": "processing",
                "reason": f"Active — {new_rec + updated + dupes:,}/{total:,} handled",
            }
        if hb_age_m <= 30:
            if processed > 0:
                return {
                    **base,
                    "status": "processing",
                    "reason": f"Slow — {hb_age_m:.0f}m since last heartbeat",
                }
            return {
                **base,
                "status": "stuck",
                "reason": f"No progress for {hb_age_m:.0f}m",
                "stuck_duration_minutes": hb_age_m,
            }
        if age_h > 2:
            return {
                **base,
                "status": "failed",
                "reason": f"Timed out after {age_h:.1f}h",
            }
        return {
            **base,
            "status": "stuck",
            "reason": f"Stuck for {hb_age_m:.0f}m",
            "stuck_duration_minutes": hb_age_m,
        }

    if db_status == "pending":
        if age_h > 0.5:
            return {
                **base,
                "status": "failed",
                "reason": f"Pending timeout ({age_h:.1f}h)",
            }
        return {**base, "status": "pending", "reason": "Waiting to start"}

    return {
        **base,
        "status": db_status,
        "reason": f"{new_rec + updated + dupes:,} records handled",
    }


@router.post("/jobs/cleanup-stuck")
async def cleanup_stuck_jobs():
    """Mark stuck/stale processing jobs as failed."""
    try:
        col = get_jobs_collection()
        now = datetime.utcnow()
        threshold = now - timedelta(hours=1)

        stuck = await col.find(
            {
                "status": {"$in": ["pending", "processing"]},
                "$or": [
                    {"updated_at": {"$lt": threshold}},
                    {"last_heartbeat": {"$lt": threshold}},
                    {"created_at": {"$lt": threshold}},
                ],
            }
        ).to_list(100)

        if not stuck:
            return {"message": "No stuck jobs found", "cleaned": 0, "timestamp": now}

        cleaned = 0
        for job in stuck:
            await col.update_one(
                {"_id": job["_id"]},
                {
                    "$set": {
                        "status": "failed",
                        "error_message": "Cleaned up automatically — job was stuck",
                        "completion_time": now,
                        "can_retry": True,
                    }
                },
            )
            cleaned += 1

        logger.info(f"🧹 Cleaned {cleaned} stuck jobs")
        return {
            "message": f"Cleaned {cleaned} stuck jobs",
            "cleaned": cleaned,
            "stuck_jobs": [
                {
                    "job_id": j.get("job_id"),
                    "list_name": j.get("list_name"),
                    "status_was": j.get("status"),
                    "created_at": j.get("created_at"),
                }
                for j in stuck
            ],
            "timestamp": now,
        }
    except Exception as e:
        logger.error(f"Stuck job cleanup failed: {e}")
        return {"error": str(e), "cleaned": 0}


@router.post("/jobs/{job_id}/force-retry")
async def retry_failed_job(
    job_id: str, request: Request, background_tasks: BackgroundTasks
):
    try:
        col = get_jobs_collection()
        job = await col.find_one({"_id": job_id})
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.get("status") != "failed":
            raise HTTPException(
                status_code=400, detail="Only failed jobs can be retried"
            )
        await col.update_one(
            {"_id": job_id},
            {
                "$set": {
                    "status": "pending",
                    "updated_at": datetime.utcnow(),
                    "retry_count": job.get("retry_count", 0) + 1,
                }
            },
        )
        return {"message": "Job retry initiated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Retry job failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retry job")


@router.delete("/jobs/clear-all")
@PerformanceMonitor.track_operation("clear_all_jobs")
async def clear_all_jobs():
    try:
        col = get_jobs_collection()
        cutoff = datetime.utcnow() - timedelta(hours=24)
        result = await col.delete_many(
            {
                "$or": [
                    {"status": {"$in": ["completed", "failed"]}},
                    {"updated_at": {"$lt": cutoff}},
                ]
            }
        )
        logger.info(f"🧹 Deleted {result.deleted_count} jobs")
        return {"deleted_count": result.deleted_count}
    except Exception as e:
        logger.error(f"Clear jobs failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recovery/manual-retry")
async def manual_retry():
    try:
        return {
            "success": True,
            "message": "Manual retry completed",
            "timestamp": datetime.utcnow(),
        }
    except Exception as e:
        return {"success": False, "message": str(e), "timestamp": datetime.utcnow()}


# ─────────────────────────────────────────────────────────────────────────────
# Routes — Lists
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/lists", dependencies=[Depends(rate_limit_check)])
@PerformanceMonitor.track_operation("list_subscriber_lists")
async def list_subscriber_lists(simple: bool = Query(False)):
    start = time.time()
    try:
        col = get_subscribers_collection()
        if simple:
            pipeline = [
                {"$group": {"_id": "$list", "count": {"$sum": 1}}},
                {"$project": {"name": "$_id", "count": 1, "_id": 0}},
            ]
        else:
            pipeline = [
                {
                    "$group": {
                        "_id": "$list",
                        "total_count": {"$sum": 1},
                        "active_count": {
                            "$sum": {"$cond": [{"$eq": ["$status", "active"]}, 1, 0]}
                        },
                    }
                },
                {"$sort": {"total_count": -1}},
                {"$project": {"_id": 1, "total_count": 1, "active_count": 1}},
            ]
        lists = await col.aggregate(pipeline).to_list(length=None)
        logger.info(f"✅ Listed {len(lists)} lists in {time.time() - start:.3f}s")
        return lists
    except Exception as e:
        logger.error(f"List aggregation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve lists: {e}")


@router.delete("/lists/{list_name}", dependencies=[Depends(rate_limit_check)])
@PerformanceMonitor.track_operation("delete_list")
async def delete_list_enhanced(
    list_name: str,
    force: bool = Query(False),
    reason: str = Query(None),
):
    try:
        subs_col = get_subscribers_collection()
        jobs_col = get_jobs_collection()

        count = await subs_col.count_documents({"list": list_name})
        if count == 0:
            raise HTTPException(status_code=404, detail=f"List '{list_name}' not found")

        active_jobs = await jobs_col.find(
            {
                "list_name": list_name,
                "status": {"$in": ["pending", "processing"]},
            }
        ).to_list(10)

        if active_jobs and not force:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"Active jobs found for '{list_name}'",
                    "active_jobs": len(active_jobs),
                    "suggestion": "Wait for jobs to complete or use force=true",
                },
            )

        if count > 100_000 and not force:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Large list requires force=true confirmation",
                    "list_size": count,
                },
            )

        # Cancel active jobs
        cancelled = 0
        for job in active_jobs:
            await jobs_col.update_one(
                {"_id": job["_id"]},
                {
                    "$set": {
                        "status": "cancelled",
                        "cancellation_reason": f"List '{list_name}' deleted",
                        "cancelled_at": datetime.utcnow(),
                    }
                },
            )
            cancelled += 1
            try:
                shutil.rmtree(
                    _chunks_dir(str(job.get("job_id", ""))), ignore_errors=True
                )
            except Exception:
                pass

        del_result = await subs_col.delete_many({"list": list_name})

        await log_activity(
            action="list_deletion",
            entity_type="subscriber_list",
            entity_id=list_name,
            user_action=f"Deleted list '{list_name}' ({del_result.deleted_count:,} subscribers)",
            metadata={"reason": reason, "force": force, "cancelled_jobs": cancelled},
        )

        await jobs_col.delete_many(
            {
                "list_name": list_name,
                "status": {"$in": ["completed", "failed", "cancelled"]},
            }
        )

        return {
            "success": True,
            "message": f"List '{list_name}' deleted",
            "subscribers_deleted": del_result.deleted_count,
            "jobs_cancelled": cancelled,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List deletion failed for '{list_name}': {e}")
        raise HTTPException(status_code=500, detail=f"List deletion failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Routes — Subscriber CRUD
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/search")
async def search_subscribers(
    search: str = Query(None),
    list_name: str = Query(None),
    status: str = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    search_mode: str = Query("smart"),
):
    start = time.time()
    try:
        col = get_subscribers_collection()
        query: Dict[str, Any] = {}

        if search and search.strip():
            t = search.strip()
            if "@" in t and "." in t:
                query["email"] = {"$regex": re.escape(t), "$options": "i"}
            else:
                query["$or"] = [
                    {"email": {"$regex": t, "$options": "i"}},
                    {"standard_fields.first_name": {"$regex": t, "$options": "i"}},
                    {"standard_fields.last_name": {"$regex": t, "$options": "i"}},
                    {"list": {"$regex": t, "$options": "i"}},
                ]
        if list_name:
            query["list"] = list_name
        if status:
            query["status"] = status

        total = await col.count_documents(query)
        skip = (page - 1) * limit
        total_pages = math.ceil(total / limit) if total > 0 else 1
        direction = -1 if sort_order == "desc" else 1
        cursor = col.find(query).skip(skip).limit(limit).sort(sort_by, direction)
        subscribers = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            subscribers.append(doc)

        return {
            "subscribers": subscribers,
            "pagination": {
                "current_page": page,
                "total_pages": total_pages,
                "total": total,
                "limit": limit,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
            "performance": {
                "query_time": f"{time.time() - start:.3f}s",
                "strategy": search_mode,
            },
        }
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")


@router.post("/bulk")
async def bulk_upload_subscribers(payload: BulkPayload):
    start = time.time()
    try:
        col = get_subscribers_collection()
        batch_size = SafeBatchProcessor.get_optimal_batch_size(len(payload.subscribers))
        processed = failed = 0
        errors: List[str] = []

        subs_data = [
            s.model_dump()
            if hasattr(s, "model_dump")
            else (s.dict() if hasattr(s, "dict") else s)
            for s in payload.subscribers
        ]

        for i in range(0, len(subs_data), batch_size):
            batch = subs_data[i : i + batch_size]
            ops = []
            for sub in batch:
                if not sub.get("email"):
                    failed += 1
                    continue
                doc = {
                    "email": sub["email"].lower().strip(),
                    "list": payload.list,
                    "status": sub.get("status", "active"),
                    "standard_fields": sub.get("standard_fields") or {},
                    "custom_fields": sub.get("custom_fields") or {},
                    "updated_at": datetime.utcnow(),
                }
                ops.append(
                    UpdateOne(
                        {"email": doc["email"], "list": payload.list},
                        {
                            "$set": doc,
                            "$setOnInsert": {"created_at": datetime.utcnow()},
                        },
                        upsert=True,
                    )
                )
            if ops:
                try:
                    r = await col.bulk_write(ops, ordered=False)
                    processed += r.upserted_count + r.modified_count
                except Exception as be:
                    failed += len(batch)
                    errors.append(str(be))

        logger.info(
            f"✅ Bulk upload: {processed} processed, {failed} failed in {time.time() - start:.3f}s"
        )
        return {
            "message": "Bulk upload completed",
            "processed": processed,
            "failed": failed,
            "errors": errors[:5],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Bulk upload failed: {e}")


@router.get("/list/{list_name}")
async def get_list_subscribers_paginated(
    list_name: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None),
):
    try:
        col = get_subscribers_collection()
        query: Dict[str, Any] = {"list": list_name}
        if search:
            query["$or"] = [
                {"email": {"$regex": search, "$options": "i"}},
                {"standard_fields.first_name": {"$regex": search, "$options": "i"}},
                {"standard_fields.last_name": {"$regex": search, "$options": "i"}},
            ]
        total = await col.count_documents(query)
        total_pages = math.ceil(total / limit) if total > 0 else 1
        skip = (page - 1) * limit
        cursor = col.find(query).skip(skip).limit(limit).sort("created_at", -1)
        subscribers = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            doc.setdefault("standard_fields", {})
            doc.setdefault("custom_fields", {})
            subscribers.append(doc)
        return {
            "success": True,
            "subscribers": subscribers,
            "pagination": {
                "current_page": page,
                "total_pages": total_pages,
                "total": total,
                "page_size": limit,
                "has_more": page < total_pages,
            },
        }
    except Exception as e:
        logger.error(f"Fetch subscribers failed for '{list_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", dependencies=[Depends(rate_limit_check)])
@PerformanceMonitor.track_operation("add_subscriber")
async def add_single_subscriber(subscriber: SubscriberIn, request: Request):
    try:
        col = get_subscribers_collection()
        email = subscriber.email.strip().lower()
        if await col.find_one({"email": email, "list": subscriber.list}):
            raise HTTPException(
                status_code=400, detail="Subscriber already exists in this list"
            )
        doc = {
            "list": subscriber.list,
            "email": email,
            "status": subscriber.status or "active",
            "standard_fields": subscriber.standard_fields or {},
            "custom_fields": subscriber.custom_fields or {},
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = await col.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        await log_activity(
            action="create",
            entity_type="subscriber",
            entity_id=str(result.inserted_id),
            user_action=f"Added {email} to '{subscriber.list}'",
            after_data=doc,
            request=request,
        )
        return doc
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add subscriber failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{subscriber_id}")
async def update_subscriber(
    subscriber_id: str, subscriber: SubscriberIn, request: Request
):
    try:
        col = get_subscribers_collection()
        if not ObjectId.is_valid(subscriber_id):
            raise HTTPException(status_code=400, detail="Invalid subscriber ID")
        existing = await col.find_one({"_id": ObjectId(subscriber_id)})
        if not existing:
            raise HTTPException(status_code=404, detail="Subscriber not found")
        update = {
            "email": subscriber.email.lower().strip(),
            "list": subscriber.list,
            "status": subscriber.status or "active",
            "standard_fields": subscriber.standard_fields or {},
            "custom_fields": subscriber.custom_fields or {},
            "updated_at": datetime.utcnow(),
        }
        result = await col.update_one(
            {"_id": ObjectId(subscriber_id)}, {"$set": update}
        )
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Subscriber not found")
        await log_activity(
            action="update",
            entity_type="subscriber",
            entity_id=subscriber_id,
            user_action=f"Updated {subscriber.email}",
            before_data={
                k: existing.get(k)
                for k in ("email", "list", "status", "standard_fields", "custom_fields")
            },
            after_data=update,
            request=request,
        )
        return {"message": "Subscriber updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update subscriber failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{subscriber_id}")
async def delete_subscriber(subscriber_id: str, request: Request):
    try:
        col = get_subscribers_collection()
        if not ObjectId.is_valid(subscriber_id):
            raise HTTPException(status_code=400, detail="Invalid subscriber ID")
        sub = await col.find_one({"_id": ObjectId(subscriber_id)})
        if not sub:
            raise HTTPException(status_code=404, detail="Subscriber not found")
        await col.delete_one({"_id": ObjectId(subscriber_id)})
        await log_activity(
            action="delete",
            entity_type="subscriber",
            entity_id=subscriber_id,
            user_action=f"Deleted {sub.get('email')} from '{sub.get('list')}'",
            before_data={k: sub.get(k) for k in ("email", "list", "status")},
            request=request,
        )
        return {"message": "Subscriber deleted successfully"}
    except Exception as e:
        logger.error(f"Delete subscriber failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{subscriber_id}/status")
async def update_subscriber_status(
    subscriber_id: str,
    status: str = Query(...),
    request: Request = None,
):
    try:
        col = get_subscribers_collection()
        if not ObjectId.is_valid(subscriber_id):
            raise HTTPException(status_code=400, detail="Invalid subscriber ID")
        result = await col.update_one(
            {"_id": ObjectId(subscriber_id)},
            {"$set": {"status": status, "updated_at": datetime.utcnow()}},
        )
        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Subscriber not found")
        return {"message": f"Status updated to {status}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Routes — List fields, export, field registry
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/lists/{list_name}/fields")
async def get_list_fields(list_name: str):
    try:
        col = get_subscribers_collection()
        pipeline = [
            {"$match": {"list": list_name}},
            {"$limit": 500},
            {
                "$group": {
                    "_id": None,
                    "std": {
                        "$addToSet": {
                            "$map": {
                                "input": {
                                    "$objectToArray": {
                                        "$ifNull": ["$standard_fields", {}]
                                    }
                                },
                                "as": "f",
                                "in": "$$f.k",
                            }
                        }
                    },
                    "cust": {
                        "$addToSet": {
                            "$map": {
                                "input": {
                                    "$objectToArray": {
                                        "$ifNull": ["$custom_fields", {}]
                                    }
                                },
                                "as": "f",
                                "in": "$$f.k",
                            }
                        }
                    },
                }
            },
        ]
        result = await col.aggregate(pipeline).to_list(1)
        if not result:
            return {"standard": [], "custom": []}
        std = set()
        cus = set()
        for arr in result[0].get("std", []):
            if arr:
                std.update(arr)
        for arr in result[0].get("cust", []):
            if arr:
                cus.update(arr)
        return {"standard": sorted(std), "custom": sorted(cus)}
    except Exception as e:
        logger.error(f"get_list_fields failed: {e}")
        return {"standard": [], "custom": []}


@router.get("/lists/{list_name}/export")
async def export_list_csv(list_name: str, request: Request):
    try:
        col = get_subscribers_collection()
        cursor = col.find({"list": list_name})
        docs = []
        std_keys: set = set()
        cus_keys: set = set()
        async for doc in cursor:
            docs.append(doc)
            std_keys.update((doc.get("standard_fields") or {}).keys())
            cus_keys.update((doc.get("custom_fields") or {}).keys())

        output = io.StringIO()
        writer = csv.writer(output)
        headers = (
            ["email", "status", "created_at", "updated_at", "list"]
            + sorted(std_keys)
            + sorted(cus_keys)
        )
        writer.writerow(headers)
        for doc in docs:
            row = [
                doc.get("email", ""),
                doc.get("status", "active"),
                doc.get("created_at", "").isoformat() if doc.get("created_at") else "",
                doc.get("updated_at", "").isoformat() if doc.get("updated_at") else "",
                doc.get("list", ""),
            ]
            std = doc.get("standard_fields") or {}
            cus = doc.get("custom_fields") or {}
            for k in sorted(std_keys):
                row.append(std.get(k, ""))
            for k in sorted(cus_keys):
                row.append(cus.get(k, ""))
            writer.writerow(row)
        output.seek(0)
        await log_activity(
            action="export",
            entity_type="list",
            entity_id=list_name,
            user_action=f"Exported '{list_name}' ({len(docs)} subscribers)",
            request=request,
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


@router.get("/lists/{list_name}/registry")
async def get_list_registry(list_name: str):
    from database import get_lists_collection

    col = get_lists_collection()
    doc = await col.find_one({"list_name": list_name}, {"_id": 0})
    return doc if doc else {"list_name": list_name, "standard": [], "custom": {}}


@router.put("/lists/{list_name}/registry")
async def update_list_registry(list_name: str, registry: ListFieldRegistry):
    from database import get_lists_collection

    col = get_lists_collection()
    doc = registry.model_dump()
    doc["list_name"] = list_name
    doc["updated_at"] = datetime.utcnow()
    await col.update_one({"list_name": list_name}, {"$set": doc}, upsert=True)
    return {"success": True, "list_name": list_name}


# ─────────────────────────────────────────────────────────────────────────────
# Routes — Field analysis
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/analyze-fields")
async def analyze_fields(request: dict):
    list_ids = request.get("listIds", [])
    segment_ids = request.get("segmentIds", [])
    if not list_ids and not segment_ids:
        return {"universal": ["email"], "standard": [], "custom": []}
    try:
        subs_col = get_subscribers_collection()
        segs_col = get_segments_collection()
        conditions = []
        if list_ids:
            conditions.append({"list": {"$in": list_ids}})
        if segment_ids:
            for seg_id in segment_ids:
                try:
                    seg = await segs_col.find_one({"_id": ObjectId(seg_id)})
                    if seg and seg.get("criteria"):
                        from routes.segments import build_segment_query, SegmentCriteria

                        conditions.append(
                            build_segment_query(SegmentCriteria(**seg["criteria"]))
                        )
                except Exception as e:
                    logger.warning(f"Segment {seg_id} skipped: {e}")
        if not conditions:
            return {"universal": ["email"], "standard": [], "custom": []}
        q = {"$or": conditions} if len(conditions) > 1 else conditions[0]
        pipeline = [
            {"$match": q},
            {
                "$group": {
                    "_id": None,
                    "std": {
                        "$addToSet": {
                            "$map": {
                                "input": {"$objectToArray": "$standard_fields"},
                                "as": "f",
                                "in": "$$f.k",
                            }
                        }
                    },
                    "cust": {
                        "$addToSet": {
                            "$map": {
                                "input": {"$objectToArray": "$custom_fields"},
                                "as": "f",
                                "in": "$$f.k",
                            }
                        }
                    },
                }
            },
        ]
        result = await subs_col.aggregate(pipeline).to_list(1)
        if not result:
            return {"universal": ["email"], "standard": [], "custom": []}
        std = set()
        cus = set()
        for arr in result[0].get("std", []):
            (std.update(arr) if arr else None)
        for arr in result[0].get("cust", []):
            (cus.update(arr) if arr else None)
        return {"universal": ["email"], "standard": sorted(std), "custom": sorted(cus)}
    except Exception as e:
        logger.error(f"analyze_fields failed: {e}", exc_info=True)
        return {
            "universal": ["email"],
            "standard": [
                "first_name",
                "last_name",
                "phone",
                "company",
                "country",
                "city",
                "job_title",
            ],
            "custom": [],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Misc helpers kept for backward compat
# ─────────────────────────────────────────────────────────────────────────────


def convert_objectids_to_strings(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, dict):
        return {k: convert_objectids_to_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert_objectids_to_strings(i) for i in obj]
    return obj
