from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
from bson import ObjectId
import random
import logging
from database import (
    get_subscribers_collection, 
    get_ab_tests_collection,
    get_ab_test_results_collection,
    get_templates_collection
)
from tasks.ab_testing import send_ab_test_batch

logger = logging.getLogger(__name__)
router = APIRouter()

# ===== MODELS =====
class TestType(str, Enum):
    SUBJECT_LINE = "subject_line"
    SENDER_NAME = "sender_name"
    SENDER_EMAIL = "sender_email"
    REPLY_TO = "reply_to"

class TestStatus(str, Enum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    PAUSED = "paused"
    FAILED = "failed"

class ABTestVariant(BaseModel):
    name: str
    subject: Optional[str] = None
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    reply_to: Optional[str] = None

class ABTestCreate(BaseModel):
    test_name: str
    target_lists: List[str]
    template_id: str
    subject: str
    sender_name: str
    sender_email: str
    reply_to: Optional[str] = None
    test_type: TestType
    variants: List[ABTestVariant]
    split_percentage: int = 50
    sample_size: int
    winner_criteria: str = "open_rate"

# ===== HELPER FUNCTIONS =====
def convert_objectid_to_str(document):
    if isinstance(document, list):
        return [convert_objectid_to_str(item) for item in document]
    elif isinstance(document, dict):
        converted = {}
        for key, value in document.items():
            if isinstance(value, ObjectId):
                converted[key] = str(value)
            elif isinstance(value, dict):
                converted[key] = convert_objectid_to_str(value)
            elif isinstance(value, list):
                converted[key] = convert_objectid_to_str(value)
            else:
                converted[key] = value
        return converted
    elif isinstance(document, ObjectId):
        return str(document)
    else:
        return document

async def get_ab_test_target_count(target_lists: List[str]) -> int:
    subscribers_collection = get_subscribers_collection()
    count = await subscribers_collection.count_documents({
        "$or": [
            {"lists": {"$in": target_lists}},
            {"list": {"$in": target_lists}}
        ],
        "status": "active"
    })
    return count

async def get_test_subscribers(target_lists: List[str], sample_size: int) -> List[dict]:
    subscribers_collection = get_subscribers_collection()
    
    query = {
        "$or": [
            {"lists": {"$in": target_lists}},
            {"list": {"$in": target_lists}}
        ],
        "status": "active"
    }
    
    cursor = subscribers_collection.find(query).limit(sample_size)
    subscribers = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        subscribers.append(doc)
    
    return subscribers

def assign_variants(subscribers: List[dict], split_percentage: int) -> Dict:
    variant_assignments = {"A": [], "B": []}
    
    for subscriber in subscribers:
        subscriber_hash = hash(subscriber["_id"]) % 100
        
        if subscriber_hash < split_percentage:
            variant_assignments["A"].append({
                "id": subscriber["_id"],
                "email": subscriber["email"],
                "first_name": subscriber.get("standard_fields", {}).get("first_name", ""),
                "custom_fields": subscriber.get("custom_fields", {})
            })
        else:
            variant_assignments["B"].append({
                "id": subscriber["_id"], 
                "email": subscriber["email"],
                "first_name": subscriber.get("standard_fields", {}).get("first_name", ""),
                "custom_fields": subscriber.get("custom_fields", {})
            })
    
    return variant_assignments

async def calculate_test_results(test_id: str) -> Dict:
    ab_test_results_collection = get_ab_test_results_collection()
    
    results_a = await ab_test_results_collection.find({
        "test_id": test_id,
        "variant": "A"
    }).to_list(None)
    
    results_b = await ab_test_results_collection.find({
        "test_id": test_id,
        "variant": "B"
    }).to_list(None)
    
    def calculate_metrics(results):
        if not results:
            return {
                "sent": 0, "opened": 0, "clicked": 0,
                "open_rate": 0, "click_rate": 0, "ctr": 0
            }
            
        total_sent = len([r for r in results if r["email_sent"]])
        total_opened = len([r for r in results if r["email_opened"]])
        total_clicked = len([r for r in results if r["email_clicked"]])
        
        return {
            "sent": total_sent,
            "opened": total_opened,
            "clicked": total_clicked,
            "open_rate": (total_opened / total_sent * 100) if total_sent > 0 else 0,
            "click_rate": (total_clicked / total_sent * 100) if total_sent > 0 else 0,
            "ctr": (total_clicked / total_opened * 100) if total_opened > 0 else 0
        }
    
    return {
        "variant_a": calculate_metrics(results_a),
        "variant_b": calculate_metrics(results_b)
    }

def determine_winner(results: Dict, criteria: str = "open_rate") -> Dict:
    a_metric = results["variant_a"].get(criteria, 0)
    b_metric = results["variant_b"].get(criteria, 0)
    
    if a_metric > b_metric:
        improvement = ((a_metric - b_metric) / b_metric * 100) if b_metric > 0 else 100
        return {"winner": "A", "improvement": round(improvement, 2)}
    elif b_metric > a_metric:
        improvement = ((b_metric - a_metric) / a_metric * 100) if a_metric > 0 else 100
        return {"winner": "B", "improvement": round(improvement, 2)}
    else:
        return {"winner": "TIE", "improvement": 0}

def calculate_statistical_significance(results: Dict) -> Dict:
    a_results = results["variant_a"]
    b_results = results["variant_b"]
    
    total_samples = a_results.get("sent", 0) + b_results.get("sent", 0)
    
    confidence_level = "low"
    if total_samples > 1000:
        confidence_level = "high"
    elif total_samples > 500:
        confidence_level = "medium"
    
    return {
        "confidence_level": confidence_level,
        "total_samples": total_samples,
        "is_significant": total_samples > 100
    }

# ===== API ROUTES =====
@router.get("/ab-tests")
async def get_all_ab_tests():
    try:
        ab_tests_collection = get_ab_tests_collection()
        tests = []
        
        cursor = ab_tests_collection.find().sort("created_at", -1)
        async for test in cursor:
            test = convert_objectid_to_str(test)
            tests.append(test)
        
        logger.info(f"Retrieved {len(tests)} A/B tests")
        return {
            "tests": tests,
            "total": len(tests)
        }
        
    except Exception as e:
        logger.error(f"Failed to list A/B tests: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve A/B tests")

@router.get("/ab-tests/lists")
async def get_available_lists():
    try:
        subscribers_collection = get_subscribers_collection()
        pipeline = [
            {"$match": {"status": "active"}},
            {"$group": {"_id": "$list", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}}
        ]
        lists = []
        async for doc in subscribers_collection.aggregate(pipeline):
            if doc["_id"]:
                lists.append({"name": doc["_id"], "count": doc["count"]})
        
        return {"lists": lists}
    except Exception as e:
        logger.error(f"Failed to fetch lists for A/B testing: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch lists")

@router.get("/ab-tests/templates")
async def get_available_templates():
    try:
        templates_collection = get_templates_collection()
        templates = []
        cursor = templates_collection.find({}, {"_id": 1, "name": 1, "subject": 1}).sort("updated_at", -1)
        async for doc in cursor:
            templates.append({
                "_id": str(doc["_id"]),
                "name": doc.get("name", "Untitled"),
                "subject": doc.get("subject", "")
            })
        
        return {"templates": templates}
    except Exception as e:
        logger.error(f"Failed to fetch templates for A/B testing: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch templates")

@router.post("/ab-tests")
async def create_ab_test(test: ABTestCreate):
    try:
        ab_tests_collection = get_ab_tests_collection()
        
        if not test.target_lists or len(test.target_lists) == 0:
            raise HTTPException(status_code=400, detail="At least one target list is required")
        
        if not test.template_id:
            raise HTTPException(status_code=400, detail="Template is required")
        
        if not test.subject.strip():
            raise HTTPException(status_code=400, detail="Subject line is required")
        
        if not test.sender_email.strip():
            raise HTTPException(status_code=400, detail="Sender email is required")
        
        total_subscribers = await get_ab_test_target_count(test.target_lists)
        if total_subscribers == 0:
            raise HTTPException(status_code=400, detail="No active subscribers found in the selected lists")
        
        min_sample_size = min(1000, max(100, int(total_subscribers * 0.1)))
        
        if test.sample_size > total_subscribers:
            test.sample_size = total_subscribers
        elif test.sample_size < min_sample_size:
            test.sample_size = min_sample_size
        
        test_doc = {
            "test_name": test.test_name,
            "target_lists": test.target_lists,
            "template_id": test.template_id,
            "subject": test.subject,
            "sender_name": test.sender_name,
            "sender_email": test.sender_email,
            "reply_to": test.reply_to or test.sender_email,
            "test_type": test.test_type,
            "variants": [variant.dict() for variant in test.variants],
            "split_percentage": test.split_percentage,
            "sample_size": test.sample_size,
            "winner_criteria": test.winner_criteria,
            "status": TestStatus.DRAFT,
            "total_target_subscribers": total_subscribers,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        result = await ab_tests_collection.insert_one(test_doc)
        
        test_doc["_id"] = str(result.inserted_id)
        
        logger.info(f"A/B test created: {result.inserted_id} targeting lists: {test.target_lists}")
        
        return {
            "message": "A/B test created successfully",
            "test_id": str(result.inserted_id),
            "test": test_doc
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create A/B test: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create A/B test: {str(e)}")

@router.get("/ab-tests/{test_id}")
async def get_ab_test(test_id: str):
    try:
        ab_tests_collection = get_ab_tests_collection()
        
        if not ObjectId.is_valid(test_id):
            raise HTTPException(status_code=400, detail="Invalid test ID format")
        
        test = await ab_tests_collection.find_one({"_id": ObjectId(test_id)})
        if not test:
            raise HTTPException(status_code=404, detail="A/B test not found")
        
        test = convert_objectid_to_str(test)
        
        logger.info(f"Retrieved A/B test: {test_id}")
        return test
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get A/B test {test_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve A/B test: {str(e)}")


@router.post("/ab-tests/{test_id}/start")
async def start_ab_test(test_id: str):
    try:
        ab_tests_collection = get_ab_tests_collection()
        
        if not ObjectId.is_valid(test_id):
            raise HTTPException(status_code=400, detail="Invalid test ID")
        
        test = await ab_tests_collection.find_one({"_id": ObjectId(test_id)})
        if not test:
            raise HTTPException(status_code=404, detail="A/B test not found")
        
        if test["status"] != TestStatus.DRAFT:
            raise HTTPException(
                status_code=400, 
                detail="Test must be in draft status to start"
            )
        
        subscribers = await get_test_subscribers(
            test.get("target_lists", []),
            test["sample_size"]
        )
        
        if not subscribers:
            raise HTTPException(
                status_code=400,
                detail="No subscribers found for this test"
            )
        
        variant_assignments = assign_variants(subscribers, test["split_percentage"])
        
        await ab_tests_collection.update_one(
            {"_id": ObjectId(test_id)},
            {
                "$set": {
                    "status": TestStatus.RUNNING,
                    "start_date": datetime.utcnow(),
                    "variant_assignments": variant_assignments,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        task = send_ab_test_batch.delay(test_id, variant_assignments)
        
        logger.info(f"A/B test started: {test_id}, Task: {task.id}")
        
        return {
            "message": "A/B test started successfully",
            "test_id": test_id,
            "task_id": task.id,
            "variant_a_count": len(variant_assignments["A"]),
            "variant_b_count": len(variant_assignments["B"])
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start A/B test: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start A/B test: {str(e)}")

@router.get("/ab-tests/{test_id}/results")
async def get_ab_test_results(test_id: str):
    try:
        ab_tests_collection = get_ab_tests_collection()
        
        if not ObjectId.is_valid(test_id):
            raise HTTPException(status_code=400, detail="Invalid test ID")
        
        test = await ab_tests_collection.find_one({"_id": ObjectId(test_id)})
        if not test:
            raise HTTPException(status_code=404, detail="A/B test not found")
        
        results = await calculate_test_results(test_id)
        winner = determine_winner(results, test["winner_criteria"])
        significance = calculate_statistical_significance(results)
        
        response_data = {
            "test_id": test_id,
            "test_name": test["test_name"],
            "status": test["status"],
            "test_type": test["test_type"],
            "target_lists": test.get("target_lists", []),
            "subject": test.get("subject", ""),
            "sender_name": test.get("sender_name", ""),
            "results": results,
            "winner": winner,
            "statistical_significance": significance,
            "start_date": test.get("start_date"),
            "end_date": test.get("end_date"),
            "sample_size": test["sample_size"],
            "split_percentage": test["split_percentage"]
        }
        
        return convert_objectid_to_str(response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get A/B test results: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get results: {str(e)}")

@router.post("/ab-tests/{test_id}/stop")
async def stop_ab_test(test_id: str):
    try:
        ab_tests_collection = get_ab_tests_collection()
        
        if not ObjectId.is_valid(test_id):
            raise HTTPException(status_code=400, detail="Invalid test ID")
        
        result = await ab_tests_collection.update_one(
            {"_id": ObjectId(test_id)},
            {
                "$set": {
                    "status": TestStatus.COMPLETED,
                    "end_date": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="A/B test not found")
        
        logger.info(f"A/B test stopped: {test_id}")
        return {
            "message": "A/B test stopped successfully",
            "test_id": test_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stop A/B test: {e}")
        raise HTTPException(status_code=500, detail="Failed to stop A/B test")

@router.delete("/ab-tests/{test_id}")
async def delete_ab_test(test_id: str):
    try:
        ab_tests_collection = get_ab_tests_collection()
        ab_test_results_collection = get_ab_test_results_collection()
        
        if not ObjectId.is_valid(test_id):
            raise HTTPException(status_code=400, detail="Invalid test ID")
        
        await ab_test_results_collection.delete_many({"test_id": test_id})
        
        result = await ab_tests_collection.delete_one({"_id": ObjectId(test_id)})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="A/B test not found")
        
        logger.info(f"A/B test deleted: {test_id}")
        return {
            "message": "A/B test deleted successfully",
            "deleted_test_id": test_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete A/B test: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete A/B test")
