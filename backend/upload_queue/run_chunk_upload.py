import asyncio
import sys
import json
import os
import glob
import shutil
import logging
from datetime import datetime
from pymongo import UpdateOne

# Import your MongoDB accessors
from database import (
    get_subscribers_collection,
    get_jobs_collection,
    ping_database
)

# --- Logging Setup ---
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
)
logger = logging.getLogger("process_chunks")

async def process_upload_chunks(job_id: str, list_name: str, chunk_files: list[str], total_records: int) -> int:
    subscribers_collection = get_subscribers_collection()
    jobs_collection = get_jobs_collection()
    start_time = datetime.utcnow()

    total_processed = 0
    completed_chunks = 0
    lock = asyncio.Lock()

    for chunk_index, chunk_file in enumerate(chunk_files):
        chunk_processed = 0
        logger.debug(f"Starting processing chunk {chunk_index + 1}/{len(chunk_files)}: {chunk_file}")

        try:
            with open(chunk_file, 'r') as f:
                chunk_data = json.load(f)
            chunk_subscribers = chunk_data.get("subscribers", [])
            batch_size = 15000

            for i in range(0, len(chunk_subscribers), batch_size):
                batch = chunk_subscribers[i:i + batch_size]
                operations = []

                for sub_data in batch:
                    if not sub_data.get("email"):
                        continue
                    subscriber_doc = {
                        "email": sub_data["email"].lower().strip(),
                        "list": list_name,
                        "status": sub_data.get("status", "active"),
                        "fields": {**sub_data.get("standard_fields", {}), **sub_data.get("custom_fields", {})},
                        "job_id": job_id,
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                    operations.append(UpdateOne(
                        {"email": subscriber_doc["email"], "list": list_name},
                        {"$set": subscriber_doc},
                        upsert=True
                    ))

                if operations:
                    try:
                        result = await subscribers_collection.bulk_write(
                            operations,
                            ordered=False,
                            bypass_document_validation=True
                        )
                        chunk_processed += result.upserted_count + result.modified_count
                        logger.debug(f"Chunk {chunk_index + 1} batch processed: upserted {result.upserted_count}, modified {result.modified_count}")
                    except Exception as batch_error:
                        logger.error(f"Batch processing error in chunk {chunk_index + 1}: {batch_error}")

            total_processed += chunk_processed
            completed_chunks += 1

            progress = (total_processed / total_records) * 100 if total_records > 0 else 0
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            speed = int(total_processed / processing_time) if processing_time > 0 else 0

            update_data = {
                "processed_records": total_processed,
                "progress": min(progress, 100),
                "records_per_second": speed,
                "updated_at": datetime.utcnow(),
                "last_heartbeat": datetime.utcnow(),
                "status": "processing",
                "is_alive": True,
                "completed_chunks": completed_chunks,
                "total_chunks": len(chunk_files),
                "processing_time_seconds": processing_time
            }

            try:
                res = await jobs_collection.update_one({"_id": job_id}, {"$set": update_data}, upsert=True)
                logger.debug(f"Updated jobs collection after chunk {chunk_index + 1}: matched {res.matched_count}, modified {res.modified_count}")
            except Exception as job_update_error:
                logger.error(f"Failed to update jobs collection after chunk {chunk_index + 1}: {job_update_error}")

            logger.info(f"✅ Chunk {chunk_index + 1}/{len(chunk_files)} processed: {chunk_processed:,} records, "
                        f"Total: {total_processed:,}/{total_records:,} ({progress:.1f}%) at {speed:,}/sec")

            try:
                os.remove(chunk_file)
                logger.debug(f"Deleted chunk file {chunk_file}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to delete chunk file {chunk_file}: {cleanup_error}")

        except Exception as chunk_error:
            logger.error(f"❌ Processing failed for chunk {chunk_index + 1}: {chunk_error}")
            try:
                await jobs_collection.update_one(
                    {"_id": job_id},
                    {"$inc": {"failed_chunks": 1},
                     "$set": {"last_error": str(chunk_error), "updated_at": datetime.utcnow()}}
                )
                logger.debug(f"Incremented failed_chunks counter for job {job_id}")
            except Exception as error_update_fail:
                logger.error(f"Failed to update job failure info: {error_update_fail}")
            continue  # proceed to next chunk despite error

    # Final job status update after all chunks processed
    total_processing_time = (datetime.utcnow() - start_time).total_seconds()
    final_speed = int(total_processed / total_processing_time) if total_processing_time > 0 else 0
    successful_chunks = completed_chunks
    failed_chunks = len(chunk_files) - completed_chunks

    final_status = "completed" if failed_chunks == 0 else "partially_completed"
    final_update = {
        "status": final_status,
        "completion_time": datetime.utcnow(),
        "final_processed": total_processed,
        "processing_method": "sequential_chunks",
        "total_processing_time_seconds": total_processing_time,
        "final_records_per_second": final_speed,
        "successful_chunks": successful_chunks,
        "failed_chunks": failed_chunks,
        "chunks_processed": completed_chunks,
        "total_chunks": len(chunk_files),
        "success_rate": (successful_chunks / len(chunk_files)) * 100 if chunk_files else 0,
        "updated_at": datetime.utcnow(),
        "last_heartbeat": datetime.utcnow()
    }

    try:
        res = await jobs_collection.update_one({"_id": job_id}, {"$set": final_update})
        logger.debug(f"Final job status updated: matched {res.matched_count}, modified {res.modified_count}")
    except Exception as final_update_error:
        logger.error(f"Failed to update final job status: {final_update_error}")

    logger.info(f"🎉 Finished processing {total_processed:,} records in {total_processing_time:.2f}s"
                f" ({final_speed:,} rec/sec), {successful_chunks}/{len(chunk_files)} chunks successful")

    # Optional: clean up chunk directory (comment if you want to keep files)
    chunks_dir = os.path.dirname(chunk_files[0]) if chunk_files else None
    if chunks_dir and os.path.exists(chunks_dir):
        try:
            shutil.rmtree(chunks_dir, ignore_errors=True)
            logger.info(f"Cleaned up chunks directory: {chunks_dir}")
        except Exception as cleanup_error:
            logger.warning(f"Failed to cleanup chunks directory: {cleanup_error}")

    return total_processed


# --- Entry Point ---
async def main():
    chunks_dir = sys.argv[1] if len(sys.argv) > 1 else "chunks"

    print(f"Argv: {sys.argv}")
    print(f"Using chunks_dir: {chunks_dir}")
    print(f"Looking for JSON files in: {os.path.abspath(chunks_dir)}")
    print(f"Glob pattern: {os.path.join(chunks_dir, '*.json')}")

    chunk_files = sorted(glob.glob(os.path.join(chunks_dir, "*.json")))
    print(f"Files found: {chunk_files}")

    if not chunk_files:
        print(f"No chunk files found in {chunks_dir}/61cb5ad9-2642-40df-b34b-d0b019adb56b")
        return

    job_id = "import_job_test"
    list_name = "test_list"

    total_records = 0
    for cf in chunk_files:
        with open(cf, 'r') as f:
            data = json.load(f)
            total_records += len(data["subscribers"])

    logger.info(f"Found {len(chunk_files)} chunk files with {total_records} subscribers total.")

    # Optionally check DB connection health before running
    if not await ping_database():
        logger.error("Database connection failed. Aborting.")
        return

    processed = await process_upload_chunks(job_id, list_name, chunk_files, total_records)
    logger.info(f"Done. Processed {processed}/{total_records} records.")

if __name__ == "__main__":
    asyncio.run(main())
