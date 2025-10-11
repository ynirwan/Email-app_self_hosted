import asyncio
import sys
import os
import json
import glob
import logging
from datetime import datetime

# Add the backend directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_subscribers_collection, get_jobs_collection
from pymongo import UpdateOne

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("chunk_recovery")

class ChunkRecoveryRunner:
    def __init__(self):
        self.upload_dir = "../upload_queue"
        self.processing_dir = "../upload_queue/processing"
        self.chunks_dir = "../upload_queue/chunks"
        self.completed_dir = "../upload_queue/completed"
        
    async def scan_and_recover(self):
        """Scan for both regular files and chunk directories"""
        try:
            recovery_stats = {
                "regular_files_found": 0,
                "chunk_dirs_found": 0,
                "files_processed": 0,
                "chunks_processed": 0,
                "total_subscribers_recovered": 0
            }
            
            # Find regular upload files
            regular_files = glob.glob(os.path.join(self.processing_dir, "upload_*.json"))
            recovery_stats["regular_files_found"] = len(regular_files)
            
            # Find chunk directories
            chunk_dirs = []
            if os.path.exists(self.chunks_dir):
                chunk_dirs = [d for d in glob.glob(os.path.join(self.chunks_dir, "*")) if os.path.isdir(d)]
            recovery_stats["chunk_dirs_found"] = len(chunk_dirs)
            
            if not regular_files and not chunk_dirs:
                logger.info("✅ No files or chunks found to recover")
                return recovery_stats
            
            logger.info(f"🔍 RECOVERY SCAN: Found {len(regular_files)} regular files and {len(chunk_dirs)} chunk directories")
            
            # Process regular files first
            for file_path in regular_files:
                try:
                    logger.info(f"📄 Processing regular file: {os.path.basename(file_path)}")
                    result = await self.process_regular_file(file_path)
                    if result["success"]:
                        recovery_stats["files_processed"] += 1
                        recovery_stats["total_subscribers_recovered"] += result.get("processed", 0)
                except Exception as e:
                    logger.error(f"❌ Failed to process regular file {file_path}: {e}")
            
            # Process chunk directories
            for chunk_dir in chunk_dirs:
                try:
                    job_id = os.path.basename(chunk_dir)
                    logger.info(f"📂 Processing chunk directory: {job_id}")
                    result = await self.process_chunk_directory(chunk_dir)
                    if result["success"]:
                        recovery_stats["chunks_processed"] += 1
                        recovery_stats["total_subscribers_recovered"] += result.get("processed", 0)
                except Exception as e:
                    logger.error(f"❌ Failed to process chunk directory {chunk_dir}: {e}")
            
            # Log final stats
            logger.info(f"🎯 RECOVERY COMPLETE:")
            logger.info(f"   📄 Regular files processed: {recovery_stats['files_processed']}")
            logger.info(f"   📂 Chunk directories processed: {recovery_stats['chunks_processed']}")
            logger.info(f"   👥 Subscribers recovered: {recovery_stats['total_subscribers_recovered']:,}")
            
            return recovery_stats
            
        except Exception as e:
            logger.error(f"❌ Recovery scan failed: {e}")
            return {"error": str(e)}
    
    async def process_chunk_directory(self, chunk_dir: str):
        """Process a directory containing chunk files"""
        try:
            job_id = os.path.basename(chunk_dir)
            chunk_files = sorted(glob.glob(os.path.join(chunk_dir, "chunk_*.json")))
            
            if not chunk_files:
                logger.info(f"   ⚠️  No chunk files found in {job_id}")
                return {"success": True, "processed": 0}
            
            logger.info(f"   📂 Found {len(chunk_files)} chunk files to process")
            
            # Get job info from first chunk
            with open(chunk_files[0], 'r') as f:
                first_chunk = json.load(f)
            
            list_name = first_chunk.get("list_name")
            if not list_name:
                logger.error(f"   ❌ No list_name found in chunks")
                return {"success": False, "error": "No list_name found"}
            
            subscribers_collection = get_subscribers_collection()
            jobs_collection = get_jobs_collection()
            
            total_processed = 0
            batch_size = 1000
            
            # Process each chunk file
            for i, chunk_file in enumerate(chunk_files, 1):
                try:
                    with open(chunk_file, 'r') as f:
                        chunk_data = json.load(f)
                    
                    chunk_subscribers = chunk_data.get("subscribers", [])
                    logger.info(f"      🔄 Chunk {i}/{len(chunk_files)}: {len(chunk_subscribers):,} subscribers")
                    
                    # Process subscribers in batches
                    chunk_processed = 0
                    for j in range(0, len(chunk_subscribers), batch_size):
                        batch = chunk_subscribers[j:j + batch_size]
                        
                        operations = []
                        for sub_data in batch:
                            if not sub_data.get("email"):
                                continue
                            
                            subscriber_doc = {
                                "email": sub_data["email"].lower().strip(),
                                "list": list_name,
                                "status": sub_data.get("status", "active"),
                                "standard_fields": sub_data.get("standard_fields", {}),
                                "custom_fields": sub_data.get("custom_fields", {}),
                                "created_at": datetime.utcnow(),
                                "updated_at": datetime.utcnow(),
                                "job_id": job_id,
                                "recovered_by": "chunk_recovery_script"
                            }
                            
                            operations.append(UpdateOne(
                                {"email": subscriber_doc["email"], "list": list_name},
                                {"$set": subscriber_doc},
                                upsert=True
                            ))
                        
                        if operations:
                            result = await subscribers_collection.bulk_write(operations, ordered=False)
                            chunk_processed += result.upserted_count + result.modified_count
                            total_processed += result.upserted_count + result.modified_count
                        
                        await asyncio.sleep(0.05)
                    
                    # Remove processed chunk file
                    os.remove(chunk_file)
                    logger.info(f"         ✅ Chunk {i} processed: {chunk_processed:,} subscribers")
                    
                except Exception as chunk_error:
                    logger.error(f"         ❌ Chunk {i} failed: {chunk_error}")
            
            # Update job as completed
            try:
                await jobs_collection.update_one(
                    {"_id": job_id},
                    {"$set": {
                        "status": "completed",
                        "completion_time": datetime.utcnow(),
                        "final_processed": total_processed,
                        "recovered_by": "chunk_recovery_script"
                    }}
                )
            except:
                pass
            
            # Remove empty chunk directory
            try:
                os.rmdir(chunk_dir)
            except:
                pass
            
            logger.info(f"   ✅ CHUNK RECOVERY COMPLETE: {total_processed:,} subscribers processed")
            
            return {"success": True, "processed": total_processed}
            
        except Exception as e:
            logger.error(f"   ❌ Chunk directory processing failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def process_regular_file(self, file_path: str):
        """Process regular upload file (existing logic)"""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            job_id = data["job_id"]
            list_name = data["list_name"]
            subscribers = data["subscribers"]
            start_from = data.get("processed_count", 0)
            
            if start_from >= len(subscribers):
                logger.info(f"   ✅ Already completed")
                return {"success": True, "processed": 0}
            
            subscribers_collection = get_subscribers_collection()
            jobs_collection = get_jobs_collection()
            
            processed_count = start_from
            batch_size = 1000
            
            # Process remaining subscribers
            for i in range(start_from, len(subscribers), batch_size):
                batch = subscribers[i:i + batch_size]
                
                operations = []
                for sub_data in batch:
                    if not sub_data.get("email"):
                        continue
                    
                    subscriber_doc = {
                        "email": sub_data["email"].lower().strip(),
                        "list": list_name,
                        "status": sub_data.get("status", "active"),
                        "standard_fields": sub_data.get("standard_fields", {}),
                        "custom_fields": sub_data.get("custom_fields", {}),
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow(),
                        "job_id": job_id,
                        "recovered_by": "chunk_recovery_script"
                    }
                    
                    operations.append(UpdateOne(
                        {"email": subscriber_doc["email"], "list": list_name},
                        {"$set": subscriber_doc},
                        upsert=True
                    ))
                
                if operations:
                    result = await subscribers_collection.bulk_write(operations, ordered=False)
                    processed_count += result.upserted_count + result.modified_count
                
                # Progress
                if processed_count % 50000 == 0:
                    progress = (processed_count / len(subscribers)) * 100
                    logger.info(f"      📈 {processed_count:,}/{len(subscribers):,} ({progress:.1f}%)")
                
                await asyncio.sleep(0.1)
            
            # Complete job
            try:
                jobs_collection = get_jobs_collection()
                await jobs_collection.update_one(
                    {"_id": job_id},
                    {"$set": {
                        "status": "completed",
                        "completion_time": datetime.utcnow(),
                        "final_processed": processed_count,
                        "recovered_by": "chunk_recovery_script"
                    }}
                )
            except:
                pass
            
            # Move to completed
            completed_path = os.path.join(self.completed_dir, os.path.basename(file_path))
            os.makedirs(self.completed_dir, exist_ok=True)
            import shutil
            shutil.move(file_path, completed_path)
            
            return {"success": True, "processed": processed_count - start_from}
            
        except Exception as e:
            logger.error(f"   ❌ Regular file processing failed: {e}")
            return {"success": False, "error": str(e)}

# CLI Interface
async def main():
    print("🔧 Chunk-Aware Recovery Script")
    print("=" * 40)
    
    recovery_runner = ChunkRecoveryRunner()
    
    if len(sys.argv) > 1 and sys.argv[1].lower() == "recover":
        print("🚀 Starting recovery...")
        result = await recovery_runner.scan_and_recover()
        
        if "error" in result:
            print(f"❌ Recovery failed: {result['error']}")
        else:
            print(f"🎉 Recovery completed: {result['total_subscribers_recovered']:,} subscribers recovered")
    else:
        # Interactive mode
        result = await recovery_runner.scan_and_recover()

if __name__ == "__main__":
    asyncio.run(main())
