# backend/tasks/suppression_tasks.py
from celery_app import celery_app  # Use your unified celery app
from database_sync import (
    get_sync_suppressions_collection,
    get_sync_audit_collection, 
    get_sync_subscribers_collection,
    get_sync_jobs_collection  # Use your existing jobs system
)
from datetime import datetime, timedelta
from typing import List, Dict, Any
from bson import ObjectId
import json
import logging
from pymongo import UpdateOne
import redis
import os

logger = logging.getLogger(__name__)

# Redis connection (add this to your database.py if not exists)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL)

# Cache configuration
SUPPRESSION_CACHE_KEY = "email_suppressions"
SUPPRESSION_CACHE_TTL = 3600  # 1 hour
SUPPRESSION_CACHE_BATCH_KEY = "batch_suppressions"

@celery_app.task(bind=True, max_retries=3, queue="suppressions", name="tasks.process_suppression_import")
def process_suppression_import(self, job_id: str, suppressions: List[Dict[str, Any]], default_reason: str, default_scope: str):
    """Process bulk suppression import in background (integrated with your job system)"""
    try:
        logger.info(f"Starting suppression import job {job_id} with {len(suppressions)} records")
        
        # Use your existing sync collections for Celery tasks
        suppressions_collection = get_sync_suppressions_collection()
        jobs_collection = get_sync_jobs_collection()
        
        # Update job status using your existing job system
        jobs_collection.update_one(
            {"_id": job_id},
            {"$set": {
                "status": "processing",
                "progress": 0.0,
                "processed": 0,
                "updated_at": datetime.utcnow()
            }}
        )
        
        successful_imports = 0
        failed_imports = 0
        skipped_duplicates = 0
        errors = []
        
        # Process in batches (matching your subscriber batch size)
        batch_size = 500  # Match your existing batch processing
        total_batches = (len(suppressions) + batch_size - 1) // batch_size
        
        for batch_idx in range(0, len(suppressions), batch_size):
            batch = suppressions[batch_idx:batch_idx + batch_size]
            batch_operations = []
            
            for suppression_data in batch:
                try:
                    email = suppression_data["email"].strip().lower()
                    
                    # Enhanced email validation
                    if "@" not in email or "." not in email.split("@")[-1]:
                        failed_imports += 1
                        errors.append(f"Invalid email format: {email}")
                        continue
                    
                    # Check for existing suppression
                    existing = suppressions_collection.find_one({"email": email, "is_active": True})
                    if existing:
                        skipped_duplicates += 1
                        continue
                    
                    suppression_doc = {
                        "email": email,
                        "reason": suppression_data.get("reason", default_reason),
                        "scope": suppression_data.get("scope", default_scope),
                        "target_lists": suppression_data.get("target_lists", []),
                        "notes": suppression_data.get("notes", f"Imported via job {job_id}"),
                        "source": "bulk_import",
                        "is_active": True,
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                        "created_by": f"import_job_{job_id}",
                        "metadata": {
                            "import_job_id": job_id,
                            "import_batch": batch_idx // batch_size + 1,
                            "total_batches": total_batches
                        }
                    }
                    
                    # Use insert instead of upsert for cleaner handling
                    batch_operations.append(suppression_doc)
                    
                except Exception as e:
                    failed_imports += 1
                    errors.append(f"Error processing {suppression_data.get('email', 'unknown')}: {str(e)}")
            
            # Execute batch operations
            if batch_operations:
                try:
                    result = suppressions_collection.insert_many(batch_operations, ordered=False)
                    successful_imports += len(result.inserted_ids)
                    
                except Exception as e:
                    logger.error(f"Batch operation failed: {str(e)}")
                    failed_imports += len(batch_operations)
                    errors.append(f"Batch operation failed: {str(e)}")
            
            # Update job progress using your existing system
            processed = min(batch_idx + batch_size, len(suppressions))
            progress = (processed / len(suppressions)) * 100
            
            jobs_collection.update_one(
                {"_id": job_id},
                {"$set": {
                    "progress": round(progress, 2),
                    "processed": processed,
                    "updated_at": datetime.utcnow(),
                    "metadata.successful": successful_imports,
                    "metadata.failed": failed_imports,
                    "metadata.skipped": skipped_duplicates
                }}
            )
            
            # Small delay to prevent database overload (like your subscriber system)
            import time
            time.sleep(0.1)
        
        # Mark job as completed using your job system
        jobs_collection.update_one(
            {"_id": job_id},
            {"$set": {
                "status": "completed",
                "progress": 100.0,
                "processed": len(suppressions),
                "completed_at": datetime.utcnow(),
                "metadata.successful": successful_imports,
                "metadata.failed": failed_imports,
                "metadata.skipped": skipped_duplicates,
                "metadata.errors": errors[:100]  # Store first 100 errors
            }}
        )
        
        # Log using your existing audit system pattern
        audit_collection = get_sync_audit_collection()
        audit_collection.insert_one({
            "timestamp": datetime.utcnow(),
            "action": "bulk_suppression_import",
            "entity_type": "suppression_import",
            "entity_id": job_id,
            "user_action": f"Bulk imported {successful_imports} suppressions",
            "after_data": {
                "job_id": job_id,
                "successful_imports": successful_imports,
                "failed_imports": failed_imports,
                "skipped_duplicates": skipped_duplicates
            },
            "metadata": {
                "total_records": len(suppressions),
                "default_reason": default_reason,
                "default_scope": default_scope
            }
        })
        
        # Refresh suppression cache
        refresh_suppression_cache.delay()
        
        logger.info(f"Suppression import job {job_id} completed. Success: {successful_imports}, Failed: {failed_imports}, Skipped: {skipped_duplicates}")
        
        return {
            "successful": successful_imports,
            "failed": failed_imports,
            "skipped": skipped_duplicates,
            "total": len(suppressions)
        }
        
    except Exception as e:
        logger.error(f"Suppression import job {job_id} failed: {str(e)}")
        
        # Mark job as failed using your job system
        jobs_collection = get_sync_jobs_collection()
        jobs_collection.update_one(
            {"_id": job_id},
            {"$set": {
                "status": "failed",
                "error_message": str(e),
                "updated_at": datetime.utcnow()
            }}
        )
        
        # Retry logic
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying suppression import job {job_id} (attempt {self.request.retries + 1})")
            raise self.retry(countdown=60 * (2 ** self.request.retries))

@celery_app.task(queue="suppressions", name="tasks.update_suppression_cache")
def update_suppression_cache(email: str, action: str):
    """Update Redis cache for a specific email suppression"""
    try:
        if action == "add":
            # Add email to suppressed set
            redis_client.sadd(SUPPRESSION_CACHE_KEY, email.lower())
        elif action == "remove":
            # Remove email from suppressed set
            redis_client.srem(SUPPRESSION_CACHE_KEY, email.lower())
        
        # Set TTL on the cache key
        redis_client.expire(SUPPRESSION_CACHE_KEY, SUPPRESSION_CACHE_TTL)
        
    except Exception as e:
        logger.error(f"Failed to update suppression cache for {email}: {str(e)}")

@celery_app.task(queue="suppressions", name="tasks.refresh_suppression_cache")
def refresh_suppression_cache():
    """Refresh the entire suppression cache from database"""
    try:
        logger.info("Refreshing suppression cache")
        
        suppressions_collection = get_sync_suppressions_collection()
        
        # Get all active global suppressions (most performance critical)
        cursor = suppressions_collection.find(
            {"is_active": True, "scope": "global"},
            {"email": 1}
        )
        
        # Clear existing cache
        redis_client.delete(SUPPRESSION_CACHE_KEY)
        
        # Add all suppressed emails to cache in batches
        suppressed_emails = []
        batch_size = 1000
        
        for suppression in cursor:
            suppressed_emails.append(suppression["email"].lower())
            
            # Process in batches to avoid memory issues
            if len(suppressed_emails) >= batch_size:
                if suppressed_emails:
                    redis_client.sadd(SUPPRESSION_CACHE_KEY, *suppressed_emails)
                suppressed_emails = []
        
        # Process remaining emails
        if suppressed_emails:
            redis_client.sadd(SUPPRESSION_CACHE_KEY, *suppressed_emails)
        
        # Set TTL
        redis_client.expire(SUPPRESSION_CACHE_KEY, SUPPRESSION_CACHE_TTL)
        
        # Get total count for logging
        total_count = redis_client.scard(SUPPRESSION_CACHE_KEY)
        logger.info(f"Suppression cache refreshed with {total_count} emails")
        
        return {"cached_emails": total_count}
        
    except Exception as e:
        logger.error(f"Failed to refresh suppression cache: {str(e)}")
        return {"error": str(e)}

@celery_app.task(queue="suppressions", name="tasks.bulk_suppression_check_cached")
def bulk_suppression_check_cached(emails: List[str]) -> Dict[str, bool]:
    """Fast bulk suppression check using Redis cache (for your campaign system)"""
    try:
        if not emails:
            return {}
        
        # Ensure cache is available
        if not redis_client.exists(SUPPRESSION_CACHE_KEY):
            refresh_suppression_cache.delay()
            # Fallback to database check
            return bulk_suppression_check_database(emails)
        
        results = {}
        # Check all emails in one Redis operation
        pipeline = redis_client.pipeline()
        for email in emails:
            pipeline.sismember(SUPPRESSION_CACHE_KEY, email.lower())
        
        redis_results = pipeline.execute()
        
        for email, is_suppressed in zip(emails, redis_results):
            results[email] = bool(is_suppressed)
        
        return results
        
    except Exception as e:
        logger.error(f"Failed bulk cache check: {str(e)}")
        # Fallback to database
        return bulk_suppression_check_database(emails)

def bulk_suppression_check_database(emails: List[str]) -> Dict[str, bool]:
    """Fallback database check for bulk suppressions"""
    try:
        suppressions_collection = get_sync_suppressions_collection()
        
        # Query for all emails at once
        cursor = suppressions_collection.find(
            {
                "email": {"$in": [email.lower() for email in emails]},
                "is_active": True
            },
            {"email": 1}
        )
        
        suppressed_emails = {doc["email"] for doc in cursor}
        
        return {email: email.lower() in suppressed_emails for email in emails}
        
    except Exception as e:
        logger.error(f"Failed bulk database check: {str(e)}")
        return {email: False for email in emails}  # Fail open

@celery_app.task(queue="suppressions", name="tasks.process_subscriber_bounces_complaints")
def process_subscriber_bounces_complaints():
    """Process subscriber bounce/complaint data and create suppressions (integrates with your subscriber system)"""
    try:
        subscribers_collection = get_sync_subscribers_collection()
        suppressions_collection = get_sync_suppressions_collection()
        
        # Find subscribers with recent bounces or complaints (adjust based on your subscriber schema)
        bounce_threshold = datetime.utcnow() - timedelta(days=7)
        
        cursor = subscribers_collection.find({
            "$or": [
                {"status": "bounced"},
                {"status": "complained"},
                # Add other bounce/complaint fields based on your schema
            ]
        })
        
        new_suppressions = []
        processed_count = 0
        
        for subscriber in cursor:
            email = subscriber["email"]
            processed_count += 1
            
            # Check if already suppressed
            existing = suppressions_collection.find_one({"email": email, "is_active": True})
            if existing:
                continue
            
            # Determine suppression reason based on your subscriber status
            if subscriber.get("status") == "complained":
                reason = "complaint"
            elif subscriber.get("status") == "bounced":
                reason = "bounce_hard"
            else:
                reason = "bounce_soft"
            
            suppression_doc = {
                "email": email,
                "reason": reason,
                "scope": "global",
                "target_lists": [],
                "notes": f"Auto-created from subscriber status: {subscriber.get('status')}",
                "source": "system",
                "subscriber_id": subscriber["_id"],
                "is_active": True,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "created_by": "automated_task",
                "metadata": {
                    "original_status": subscriber.get("status"),
                    "list_name": subscriber.get("list"),
                    "automation_run": datetime.utcnow().isoformat()
                }
            }
            
            new_suppressions.append(suppression_doc)
        
        # Bulk insert new suppressions
        if new_suppressions:
            result = suppressions_collection.insert_many(new_suppressions)
            
            # Update cache for each new suppression
            for suppression in new_suppressions:
                update_suppression_cache.delay(suppression["email"], "add")
            
            # Log audit trail
            audit_collection = get_sync_audit_collection()
            audit_collection.insert_one({
                "timestamp": datetime.utcnow(),
                "action": "automated_suppression_creation",
                "entity_type": "suppression_automation",
                "entity_id": f"auto_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                "user_action": f"Auto-created {len(new_suppressions)} suppressions from subscriber data",
                "after_data": {
                    "new_suppressions": len(new_suppressions),
                    "processed_subscribers": processed_count
                },
                "metadata": {
                    "bounce_threshold": bounce_threshold.isoformat(),
                    "automation_type": "subscriber_status_sync"
                }
            })
        
        logger.info(f"Processed {processed_count} subscribers, created {len(new_suppressions)} new suppressions")
        
        return {
            "processed_subscribers": processed_count,
            "new_suppressions": len(new_suppressions)
        }
        
    except Exception as e:
        logger.error(f"Failed to process subscriber bounces/complaints: {str(e)}")
        return {"error": str(e)}

@celery_app.task(queue="suppressions", name="tasks.cleanup_old_suppressions")
def cleanup_old_suppressions(days_old: int = 365):
    """Clean up old inactive suppressions (maintenance task)"""
    try:
        suppressions_collection = get_sync_suppressions_collection()
        
        # Remove suppressions older than specified days that are inactive
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        result = suppressions_collection.delete_many({
            "is_active": False,
            "updated_at": {"$lt": cutoff_date}
        })
        
        logger.info(f"Cleaned up {result.deleted_count} old inactive suppressions")
        
        return {"deleted_count": result.deleted_count}
        
    except Exception as e:
        logger.error(f"Failed to cleanup old suppressions: {str(e)}")
        return {"error": str(e)}

# Utility functions for integration with your email sending system
def is_email_suppressed_cached(email: str) -> bool:
    """Fast check if email is globally suppressed using Redis cache"""
    try:
        # Check cache first
        if redis_client.exists(SUPPRESSION_CACHE_KEY):
            return redis_client.sismember(SUPPRESSION_CACHE_KEY, email.lower())
        
        # Fallback to database if cache is empty
        suppressions_collection = get_sync_suppressions_collection()
        result = suppressions_collection.find_one({
            "email": email.lower(),
            "is_active": True,
            "scope": "global"
        })
        
        return result is not None
        
    except Exception as e:
        logger.error(f"Failed to check suppression for {email}: {str(e)}")
        return False  # Fail open to avoid blocking legitimate emails

def filter_suppressed_emails(emails: List[str], target_lists: List[str] = None) -> List[str]:
    """Filter out suppressed emails from a list (for your campaign batch processing)"""
    try:
        if not emails:
            return []
        
        # Use cached bulk check for performance
        suppression_results = bulk_suppression_check_cached(emails)
        
        # For list-specific suppressions, need database check
        if target_lists:
            suppressions_collection = get_sync_suppressions_collection()
            list_suppressions = suppressions_collection.find({
                "email": {"$in": [email.lower() for email in emails]},
                "is_active": True,
                "scope": "list_specific",
                "target_lists": {"$in": target_lists}
            })
            
            # Mark list-specific suppressions
            for suppression in list_suppressions:
                if suppression["email"] in suppression_results:
                    suppression_results[suppression["email"]] = True
        
        # Return only non-suppressed emails
        return [email for email in emails if not suppression_results.get(email, False)]
        
    except Exception as e:
        logger.error(f"Failed to filter suppressed emails: {str(e)}")
        return emails  # Return all emails if filtering fails

# Periodic tasks for maintenance
@celery_app.task(queue="suppressions", name="tasks.hourly_cache_refresh")
def hourly_cache_refresh():
    """Hourly task to refresh suppression cache"""
    refresh_suppression_cache.delay()

@celery_app.task(queue="suppressions", name="tasks.daily_bounce_processing")  
def daily_bounce_processing():
    """Daily task to process bounces and complaints"""
    process_subscriber_bounces_complaints.delay()

@celery_app.task(queue="suppressions", name="tasks.weekly_cleanup")
def weekly_cleanup():
    """Weekly cleanup of old suppressions"""
    cleanup_old_suppressions.delay(365)  # Clean up suppressions older than 1 year

