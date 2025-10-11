# backend/tasks/simple_file_recovery.py
"""
Ultra-Simple File-First Recovery
- Save upload to file first (100% safe)
- Auto-resume on reboot
- Manual retry option
"""
import json
import os
import glob
import asyncio
from datetime import datetime
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class SimpleFileRecovery:
    """Ultra-simple file-first recovery"""
    
    def __init__(self):
        self.upload_dir = "upload_queue"
        self.processing_dir = "upload_queue/processing"
        self.completed_dir = "upload_queue/completed"
        self.setup_directories()
    
    def setup_directories(self):
        """Create directory structure"""
        for directory in [self.upload_dir, self.processing_dir, self.completed_dir]:
            os.makedirs(directory, exist_ok=True)
        logger.info("📁 Upload queue directories ready")
    
    # ===== 1. SAVE UPLOAD TO FILE =====
    async def save_upload(self, job_id: str, list_name: str, subscribers: List[Dict]) -> str:
        """Save upload to file - instantly safe"""
        try:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"upload_{job_id}_{timestamp}.json"
            file_path = os.path.join(self.upload_dir, filename)
            
            upload_data = {
                "job_id": job_id,
                "list_name": list_name,
                "total_records": len(subscribers),
                "created_at": datetime.utcnow().isoformat(),
                "status": "queued",
                "processed_count": 0,
                "subscribers": subscribers
            }
            
            # Save file atomically (safe from corruption)
            temp_path = file_path + ".tmp"
            with open(temp_path, 'w') as f:
                json.dump(upload_data, f, default=str)
            os.rename(temp_path, file_path)
            
            logger.info(f"💾 SAVED: {len(subscribers):,} subscribers to {filename}")
            return file_path
            
        except Exception as e:
            logger.error(f"❌ File save failed: {e}")
            raise Exception(f"Failed to save upload: {e}")
    
    # ===== 2. PROCESS FROM FILE =====
    async def process_upload_file(self, file_path: str) -> Dict[str, Any]:
        """Process subscribers from saved file"""
        processing_path = None
        
        try:
            # Move to processing
            filename = os.path.basename(file_path)
            processing_path = os.path.join(self.processing_dir, filename)
            os.rename(file_path, processing_path)
            
            # Load data
            with open(processing_path, 'r') as f:
                data = json.load(f)
            
            job_id = data["job_id"]
            list_name = data["list_name"]
            subscribers = data["subscribers"]
            start_from = data.get("processed_count", 0)
            
            logger.info(f"🔄 PROCESSING: {filename} - {len(subscribers):,} subscribers")
            
            # Import database functions
            from database import get_subscribers_collection
            from pymongo import UpdateOne
            subscribers_collection = get_subscribers_collection()
            
            processed_count = start_from
            failed_count = 0
            batch_size = 1000
            
            # Process in batches
            for i in range(start_from, len(subscribers), batch_size):
                batch = subscribers[i:i + batch_size]
                
                try:
                    operations = []
                    for sub_data in batch:
                        if not sub_data.get("email"):
                            failed_count += 1
                            continue
                        
                        doc = {
                            "email": sub_data["email"].lower().strip(),
                            "list": list_name,
                            "status": sub_data.get("status", "active"),
                            "standard_fields": sub_data.get("standard_fields", {}),
                            "custom_fields": sub_data.get("custom_fields", {}),
                            "created_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow(),
                            "job_id": job_id
                        }
                        
                        operations.append(UpdateOne(
                            {"email": doc["email"], "list": list_name},
                            {"$set": doc},
                            upsert=True
                        ))
                    
                    # Execute batch
                    if operations:
                        result = await subscribers_collection.bulk_write(operations, ordered=False)
                        processed_count += result.upserted_count + result.modified_count
                    
                    # Save progress (survives reboot)
                    data["processed_count"] = processed_count
                    data["status"] = "processing"
                    data["last_update"] = datetime.utcnow().isoformat()
                    
                    with open(processing_path, 'w') as f:
                        json.dump(data, f, default=str)
                    
                    # Update job progress
                    try:
                        from routes.subscribers import job_manager
                        await job_manager.update_job_progress(job_id, processed_count, failed_count)
                    except:
                        pass
                    
                    await asyncio.sleep(0.1)
                    
                except Exception as batch_error:
                    logger.error(f"Batch error: {batch_error}")
                    failed_count += len(batch)
            
            # Success - move to completed
            completed_path = os.path.join(self.completed_dir, filename)
            data.update({
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "final_processed": processed_count,
                "final_failed": failed_count
            })
            
            with open(completed_path, 'w') as f:
                json.dump(data, f, default=str)
            os.remove(processing_path)
            
            logger.info(f"✅ COMPLETED: {filename} - {processed_count:,} processed")
            
            return {
                "success": True,
                "processed": processed_count,
                "failed": failed_count,
                "file": filename
            }
            
        except Exception as e:
            logger.error(f"❌ Processing failed: {e}")
            return {"success": False, "error": str(e)}
    
    # ===== 3. AUTO-RECOVERY ON REBOOT =====
    async def auto_recovery_on_startup(self) -> Dict[str, Any]:
        """Auto-resume interrupted uploads on startup"""
        try:
            # Find interrupted files
            queued_files = glob.glob(os.path.join(self.upload_dir, "upload_*.json"))
            processing_files = glob.glob(os.path.join(self.processing_dir, "upload_*.json"))
            
            total_resumed = 0
            
            # Resume queued files
            for file_path in queued_files:
                try:
                    logger.info(f"⚡ AUTO-RECOVERY: Resuming queued file {os.path.basename(file_path)}")
                    asyncio.create_task(self.process_upload_file(file_path))
                    total_resumed += 1
                except Exception as e:
                    logger.error(f"Failed to resume {file_path}: {e}")
            
            # Resume processing files (interrupted mid-processing)
            for file_path in processing_files:
                try:
                    logger.info(f"⚡ AUTO-RECOVERY: Resuming processing file {os.path.basename(file_path)}")
                    asyncio.create_task(self.process_upload_file(file_path))
                    total_resumed += 1
                except Exception as e:
                    logger.error(f"Failed to resume {file_path}: {e}")
            
            if total_resumed > 0:
                logger.critical(f"⚡ AUTO-RECOVERY: {total_resumed} uploads resumed automatically")
            else:
                logger.info("✅ No uploads to recover")
            
            return {"files_resumed": total_resumed}
            
        except Exception as e:
            logger.error(f"Auto-recovery failed: {e}")
            return {"error": str(e)}
    
    # ===== 4. MANUAL RETRY =====
    async def manual_retry(self) -> Dict[str, Any]:
        """Manually retry failed or stuck uploads"""
        try:
            # Find files that can be retried
            queued_files = glob.glob(os.path.join(self.upload_dir, "upload_*.json"))
            processing_files = glob.glob(os.path.join(self.processing_dir, "upload_*.json"))
            
            retry_count = 0
            
            # Retry queued files
            for file_path in queued_files:
                logger.info(f"🔄 MANUAL RETRY: Retrying {os.path.basename(file_path)}")
                asyncio.create_task(self.process_upload_file(file_path))
                retry_count += 1
            
            # Retry processing files (might be stuck)
            for file_path in processing_files:
                logger.info(f"🔄 MANUAL RETRY: Retrying stuck file {os.path.basename(file_path)}")
                asyncio.create_task(self.process_upload_file(file_path))
                retry_count += 1
            
            return {
                "success": True,
                "files_retried": retry_count,
                "message": f"Manually retried {retry_count} uploads"
            }
            
        except Exception as e:
            logger.error(f"Manual retry failed: {e}")
            return {"success": False, "error": str(e)}
    
    # ===== 5. STATUS =====
    def get_status(self) -> Dict[str, Any]:
        """Get simple queue status"""
        try:
            queued = len(glob.glob(os.path.join(self.upload_dir, "upload_*.json")))
            processing = len(glob.glob(os.path.join(self.processing_dir, "upload_*.json")))
            completed = len(glob.glob(os.path.join(self.completed_dir, "upload_*.json")))
            
            return {
                "timestamp": datetime.utcnow().isoformat(),
                "queued": queued,
                "processing": processing,
                "completed": completed,
                "total": queued + processing + completed,
                "status": "operational"
            }
        except Exception as e:
            return {"error": str(e)}

# Global instance
simple_file_recovery = SimpleFileRecovery()

