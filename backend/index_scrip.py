# backend/index_script.py - FIXED WITH CLEANUP
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

MONGO_URI = "mongodb://admin:password@mongodb:27017/user_info?authSource=admin"
DB_NAME = "email_marketing"

async def create_indexes():
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    
    print("🧹 First, cleaning up dangerous unique indexes...")
    
    # =========================
    # STEP 1: Remove Dangerous Unique Indexes
    # =========================
    
    # Check and remove problematic unique indexes
    subscribers = db["subscribers"]
    email_logs = db["email_logs"]
    
    print("\n🔍 Checking existing indexes...")
    
    # Check subscribers indexes
    try:
        sub_indexes = await subscribers.list_indexes().to_list(length=None)
        for idx in sub_indexes:
            if idx.get("unique", False) and "list_id_1_email_1" in idx["name"]:
                print(f"❌ Dropping dangerous unique index: {idx['name']}")
                await subscribers.drop_index("list_id_1_email_1")
                break
    except Exception as e:
        if "not found" in str(e).lower():
            print("  ✅ No problematic subscriber indexes found")
        else:
            print(f"  ⚠️  Subscriber index check: {e}")
    
    # Check email_logs indexes
    try:
        log_indexes = await email_logs.list_indexes().to_list(length=None)
        for idx in log_indexes:
            if idx.get("unique", False):
                if "campaign_id" in str(idx.get("key", {})) and "subscriber_id" in str(idx.get("key", {})):
                    print(f"❌ Dropping dangerous email_logs unique index: {idx['name']}")
                    await email_logs.drop_index(idx["name"])
    except Exception as e:
        if "not found" in str(e).lower():
            print("  ✅ No problematic email_logs indexes found")
        else:
            print(f"  ⚠️  Email logs index check: {e}")
    
    print("\n🚀 Creating safe performance indexes...")
    
    # =========================
    # STEP 2: Create Safe Indexes with Explicit Names
    # =========================
    
    # Subscribers Collection  
    print("\n📁 Subscribers Collection:")
    
    # Use explicit names to avoid conflicts
    try:
        await subscribers.create_index([("list_id", 1), ("email", 1)], 
                                     name="safe_list_email_perf", 
                                     background=True)
        print("  ✅ list_id + email (non-unique, safe)")
    except Exception as e:
        if "already exists" in str(e):
            print("  ✅ list_id + email (already exists)")
        else:
            print(f"  ⚠️  list_id + email: {e}")
    
    try:
        await subscribers.create_index([("list_id", 1), ("status", 1), ("updated_at", -1)], 
                                     name="safe_list_status_time", 
                                     background=True)
        print("  ✅ list_id + status + updated_at")
    except Exception as e:
        if "already exists" in str(e):
            print("  ✅ list_id + status + updated_at (already exists)")
        else:
            print(f"  ⚠️  list_id + status + updated_at: {e}")
    
    try:
        await subscribers.create_index([("lists", 1), ("_id", 1)], 
                                     name="safe_lists_id", 
                                     background=True)
        print("  ✅ lists + _id")
    except Exception as e:
        if "already exists" in str(e):
            print("  ✅ lists + _id (already exists)")
        else:
            print(f"  ⚠️  lists + _id: {e}")
    
    try:
        await subscribers.create_index([("lists", 1)], 
                                     name="safe_lists_array", 
                                     background=True)
        print("  ✅ lists (array)")
    except Exception as e:
        if "already exists" in str(e):
            print("  ✅ lists (already exists)")
        else:
            print(f"  ⚠️  lists: {e}")
    
    try:
        await subscribers.create_index([("list", 1)], 
                                     name="safe_list_legacy", 
                                     background=True)
        print("  ✅ list (legacy)")
    except Exception as e:
        if "already exists" in str(e):
            print("  ✅ list (already exists)")
        else:
            print(f"  ⚠️  list: {e}")
    
    # Simple indexes
    simple_indexes = [
        ("email", "safe_email"),
        ("status", "safe_status"), 
        ("updated_at", "safe_updated_at")
    ]
    
    for field, name in simple_indexes:
        try:
            await subscribers.create_index(field, name=name, background=True)
            print(f"  ✅ {field}")
        except Exception as e:
            if "already exists" in str(e):
                print(f"  ✅ {field} (already exists)")
            else:
                print(f"  ⚠️  {field}: {e}")

    # =========================
    # Email Logs Collection - THE IMPORTANT ONE
    # =========================
    print("\n📁 Email Logs Collection:")
    
    # This is the critical index for your slow query
    try:
        await email_logs.create_index([
            ("campaign_id", 1), 
            ("subscriber_id", 1), 
            ("latest_status", 1)
        ], name="perf_campaign_subscriber_status", background=True)
        print("  ✅ campaign_id + subscriber_id + latest_status (FIXES SLOW QUERY)")
    except Exception as e:
        if "already exists" in str(e):
            print("  ✅ campaign_id + subscriber_id + latest_status (already exists)")
        else:
            print(f"  ⚠️  Main performance index: {e}")
    
    # Non-unique campaign + subscriber
    try:
        await email_logs.create_index([("campaign_id", 1), ("subscriber_id", 1)], 
                                    name="safe_campaign_subscriber", 
                                    background=True)
        print("  ✅ campaign_id + subscriber_id (non-unique)")
    except Exception as e:
        if "already exists" in str(e):
            print("  ✅ campaign_id + subscriber_id (already exists)")
        else:
            print(f"  ⚠️  campaign_id + subscriber_id: {e}")
    
    # Other useful indexes
    email_log_indexes = [
        ([("campaign_id", 1), ("latest_status", 1)], "perf_campaign_status"),
        ([("campaign_id", 1), ("last_attempted_at", -1)], "perf_campaign_time"),
        ([("last_attempted_at", 1)], "perf_cleanup_time"),
        ([("email", 1), ("latest_status", 1)], "perf_email_status"),
        ([("message_id", 1)], "perf_message_id")
    ]
    
    for idx_spec, idx_name in email_log_indexes:
        try:
            if idx_name == "perf_message_id":
                await email_logs.create_index(idx_spec, name=idx_name, sparse=True, background=True)
            else:
                await email_logs.create_index(idx_spec, name=idx_name, background=True)
            print(f"  ✅ {idx_name}")
        except Exception as e:
            if "already exists" in str(e):
                print(f"  ✅ {idx_name} (already exists)")
            else:
                print(f"  ⚠️  {idx_name}: {e}")

    # =========================
    # Campaigns Collection
    # =========================
    print("\n📁 Campaigns Collection:")
    campaigns = db["campaigns"]
    
    campaign_indexes = [
        ([("created_at", -1)], "perf_created_at"),
        ([("status", 1)], "perf_status"),
        ([("target_lists", 1)], "perf_target_lists"),
        ([("status", 1), ("started_at", 1)], "perf_status_started"),
        ([("status", 1), ("last_batch_at", 1)], "perf_status_batch")
    ]
    
    for idx_spec, idx_name in campaign_indexes:
        try:
            await campaigns.create_index(idx_spec, name=idx_name, background=True)
            print(f"  ✅ {idx_name}")
        except Exception as e:
            if "already exists" in str(e):
                print(f"  ✅ {idx_name} (already exists)")
            else:
                print(f"  ⚠️  {idx_name}: {e}")

    # =========================
    # Templates Collection - Keep unique for names
    # =========================
    print("\n📁 Templates Collection:")
    templates = db["templates"]
    
    try:
        await templates.create_index([("name", 1)], 
                                   unique=True, 
                                   sparse=True, 
                                   name="unique_template_name", 
                                   background=True)
        print("  ✅ name (unique - safe for templates)")
    except Exception as e:
        if "already exists" in str(e):
            print("  ✅ name (already exists)")
        else:
            print(f"  ⚠️  template name: {e}")

    # =========================
    # Final Verification
    # =========================
    print("\n🔍 Final verification - checking for dangerous unique indexes:")
    
    dangerous_collections = ["email_logs", "subscribers"]
    for collection_name in dangerous_collections:
        collection = db[collection_name]
        try:
            indexes = await collection.list_indexes().to_list(length=None)
            
            dangerous_unique = []
            for idx in indexes:
                if idx.get("unique", False) and idx["name"] != "_id_":
                    # Templates with unique names are OK
                    if collection_name == "templates" and "name" in str(idx.get("key", {})):
                        continue
                    dangerous_unique.append(idx)
            
            if dangerous_unique:
                print(f"  ⚠️  {collection_name} still has unique indexes:")
                for idx in dangerous_unique:
                    print(f"     - {idx['name']}: {idx.get('key', {})}")
                    print(f"       Run: db.{collection_name}.dropIndex('{idx['name']}')")
            else:
                print(f"  ✅ {collection_name}: No dangerous unique constraints")
        except Exception as e:
            print(f"  ⚠️  Could not check {collection_name}: {e}")

    await client.close()
    print("\n✅ Safe performance indexes created!")
    print("\n🎯 Test your slow query now:")
    print('db.email_logs.explain("executionStats").find({')
    print('  "campaign_id": ObjectId("68ce840ee54c07f2c2980d45"),')
    print('  "subscriber_id": "68cae550dd562678e58de924",')
    print('  "latest_status": {"$in": ["sent","delivered"]}')
    print('}).limit(1)')

if __name__ == "__main__":
    asyncio.run(create_indexes())

