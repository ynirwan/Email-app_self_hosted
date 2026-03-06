import json
import os
import glob
from datetime import datetime
import asyncio

from database import get_subscribers_collection, get_jobs_collection
from pymongo import UpdateOne

async def chunk_and_process():
    print("🔪 File Chunker & Processor")
    print("=" * 40)
    
    # Find large files
    processing_files = glob.glob("../upload_queue/processing/*.json")
    
    if not processing_files:
        print("✅ No files to chunk")
        return
    
    print(f"📄 Found {len(processing_files)} files:")
    
    for file_path in processing_files:
        file_size = os.path.getsize(file_path) / (1024*1024)
        filename = os.path.basename(file_path)
        print(f"   📁 {filename} ({file_size:.1f}MB)")
    
    proceed = input(f"\n🔪 Chunk and process {len(processing_files)} files? (y/N): ")
    if proceed.lower() not in ['y', 'yes']:
        return
    
    # Process each file
    for file_path in processing_files:
        await chunk_and_process_file(file_path)

async def chunk_and_process_file(file_path: str):
    """Chunk a large file and process each chunk"""
    filename = os.path.basename(file_path)
    print(f"\n🔪 Chunking: {filename}")
    
    try:
        # STEP 1: Extract metadata without loading full file
        job_id, list_name, total_records, processed_count = extract_metadata(file_path)
        
        if not job_id:
            print(f"   ❌ Could not extract metadata")
            return
        
        print(f"   📊 Job: {job_id[:8]}... | List: {list_name}")
        print(f"   📊 Total: {total_records:,} | Already processed: {processed_count:,}")
        
        if processed_count >= total_records:
            print(f"   ✅ Already completed")
            return
        
        # STEP 2: Create chunks directory
        chunks_dir = f"../upload_queue/chunks/{job_id}"
        os.makedirs(chunks_dir, exist_ok=True)
        
        # STEP 3: Split file into chunks
        chunk_files = create_file_chunks(file_path, chunks_dir, processed_count)
        
        if not chunk_files:
            print(f"   ❌ Failed to create chunks")
            return
        
        print(f"   🔪 Created {len(chunk_files)} chunks")
        
        # STEP 4: Process each chunk
        total_processed = processed_count
        
        for i, chunk_file in enumerate(chunk_files, 1):
            print(f"   🔄 Processing chunk {i}/{len(chunk_files)}")
            
            try:
                chunk_processed = await process_chunk_file(chunk_file, list_name, job_id)
                total_processed += chunk_processed
                
                # Update job progress
                jobs_collection = get_jobs_collection()
                await jobs_collection.update_one(
                    {"_id": job_id},
                    {"$set": {
                        "processed_records": total_processed,
                        "status": "processing",
                        "updated_at": datetime.utcnow()
                    }}
                )
                
                # Remove processed chunk
                os.remove(chunk_file)
                
                progress = (total_processed / total_records) * 100
                print(f"      ✅ Chunk {i} complete: {chunk_processed:,} records | Total: {total_processed:,}/{total_records:,} ({progress:.1f}%)")
                
            except Exception as chunk_error:
                print(f"      ❌ Chunk {i} failed: {chunk_error}")
        
        # STEP 5: Complete the job
        jobs_collection = get_jobs_collection()
        await jobs_collection.update_one(
            {"_id": job_id},
            {"$set": {
                "status": "completed",
                "final_processed": total_processed,
                "completion_time": datetime.utcnow()
            }}
        )
        
        # Move original file to completed
        os.makedirs("../upload_queue/completed", exist_ok=True)
        completed_path = f"../upload_queue/completed/{filename}"
        import shutil
        shutil.move(file_path, completed_path)
        
        # Clean up chunks directory
        import shutil
        shutil.rmtree(chunks_dir, ignore_errors=True)
        
        print(f"   🎉 COMPLETED: {total_processed:,} total subscribers processed")
        
    except Exception as e:
        print(f"   ❌ Chunking failed: {e}")

def extract_metadata(file_path: str):
    """Extract metadata from file without loading everything"""
    try:
        job_id = None
        list_name = None
        total_records = 0
        processed_count = 0
        
        with open(file_path, 'r') as f:
            # Read first few KB to get metadata
            for _ in range(100):  # Read first 100 lines
                line = f.readline()
                if not line:
                    break
                
                if '"job_id":' in line and not job_id:
                    try:
                        job_id = line.split('"job_id": "')[1].split('"')[0]
                    except:
                        pass
                        
                if '"list_name":' in line and not list_name:
                    try:
                        list_name = line.split('"list_name": "')[1].split('"')[0]
                    except:
                        pass
                        
                if '"total_records":' in line and total_records == 0:
                    try:
                        total_records = int(line.split('"total_records": ')[1].split(',')[0])
                    except:
                        pass
                        
                if '"processed_count":' in line:
                    try:
                        processed_count = int(line.split('"processed_count": ')[1].split(',')[0])
                    except:
                        pass
        
        return job_id, list_name, total_records, processed_count
        
    except Exception as e:
        print(f"   ❌ Metadata extraction failed: {e}")
        return None, None, 0, 0

def create_file_chunks(file_path: str, chunks_dir: str, start_from: int):
    """Split file into small chunks"""
    try:
        chunk_files = []
        chunk_size = 10000  # 10k records per chunk
        current_chunk = []
        current_chunk_num = 0
        subscriber_count = 0
        
        with open(file_path, 'r') as f:
            in_subscribers_array = False
            current_subscriber = ""
            brace_count = 0
            
            for line in f:
                # Find subscribers array
                if '"subscribers": [' in line:
                    in_subscribers_array = True
                    continue
                
                if not in_subscribers_array:
                    continue
                
                # Skip already processed records
                if subscriber_count < start_from:
                    if line.strip() == '},' or line.strip() == '}':
                        subscriber_count += 1
                    continue
                
                # Extract subscriber objects
                if line.strip().startswith('{'):
                    current_subscriber = line
                    brace_count = 1
                elif current_subscriber:
                    current_subscriber += line
                    brace_count += line.count('{') - line.count('}')
                    
                    # Complete subscriber found
                    if brace_count <= 0:
                        try:
                            clean_json = current_subscriber.rstrip(',\n ')
                            subscriber_data = json.loads(clean_json)
                            
                            if subscriber_data.get("email"):
                                current_chunk.append(subscriber_data)
                            
                            # Save chunk when full
                            if len(current_chunk) >= chunk_size:
                                chunk_file = f"{chunks_dir}/chunk_{current_chunk_num:04d}.json"
                                save_chunk(current_chunk, chunk_file)
                                chunk_files.append(chunk_file)
                                
                                current_chunk = []
                                current_chunk_num += 1
                            
                        except json.JSONDecodeError:
                            pass
                        
                        current_subscriber = ""
                        subscriber_count += 1
        
        # Save remaining chunk
        if current_chunk:
            chunk_file = f"{chunks_dir}/chunk_{current_chunk_num:04d}.json"
            save_chunk(current_chunk, chunk_file)
            chunk_files.append(chunk_file)
        
        return chunk_files
        
    except Exception as e:
        print(f"   ❌ Chunking failed: {e}")
        return []

def save_chunk(subscribers: list, chunk_file: str):
    """Save a chunk of subscribers to file"""
    try:
        with open(chunk_file, 'w') as f:
            json.dump({"subscribers": subscribers}, f)
    except Exception as e:
        print(f"   ❌ Failed to save chunk {chunk_file}: {e}")

async def process_chunk_file(chunk_file: str, list_name: str, job_id: str):
    """Process a small chunk file"""
    try:
        # Load small chunk (safe for memory)
        with open(chunk_file, 'r') as f:
            chunk_data = json.load(f)
        
        subscribers = chunk_data["subscribers"]
        subscribers_collection = get_subscribers_collection()
        
        # Process subscribers
        operations = []
        for subscriber_data in subscribers:
            doc = {
                "email": subscriber_data["email"].lower().strip(),
                "list": list_name,
                "status": subscriber_data.get("status", "active"),
                "standard_fields": subscriber_data.get("standard_fields", {}),
                "custom_fields": subscriber_data.get("custom_fields", {}),
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
            return result.upserted_count + result.modified_count
        
        return 0
        
    except Exception as e:
        print(f"   ❌ Chunk processing failed: {e}")
        return 0

if __name__ == "__main__":
    asyncio.run(chunk_and_process())
