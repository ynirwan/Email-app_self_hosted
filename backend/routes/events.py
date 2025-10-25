# backend/routes/events.py
"""
Event tracking system for automation triggers
Handles cart abandonment, purchases, page views, custom events
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel, EmailStr, Field, validator
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime, timedelta
from bson import ObjectId
import logging

from database import (
    get_events_collection,
    get_subscribers_collection,
    get_audit_collection
)
from tasks.automation_tasks import process_automation_trigger

router = APIRouter(prefix="/events", tags=["events"])
logger = logging.getLogger(__name__)


# ===========================
# PYDANTIC SCHEMAS
# ===========================

class CartItem(BaseModel):
    """Cart item details"""
    product_id: str
    product_name: str
    quantity: int = 1
    price: float
    image_url: Optional[str] = None
    product_url: Optional[str] = None

class CartAbandonmentEvent(BaseModel):
    """Cart abandonment event"""
    email: EmailStr
    cart_id: str
    cart_value: float = Field(ge=0)
    cart_items: List[CartItem]
    currency: str = "USD"
    abandoned_at: Optional[datetime] = None
    cart_url: Optional[str] = None  # Recovery URL
    
    @validator('cart_items')
    def validate_items(cls, v):
        if len(v) == 0:
            raise ValueError('Cart must have at least one item')
        return v

class PurchaseEvent(BaseModel):
    """Purchase completion event"""
    email: EmailStr
    order_id: str
    order_value: float = Field(ge=0)
    currency: str = "USD"
    items: List[CartItem]
    purchased_at: Optional[datetime] = None
    order_url: Optional[str] = None

class PageViewEvent(BaseModel):
    """Page view tracking event"""
    email: EmailStr
    page_url: str
    page_title: Optional[str] = None
    referrer: Optional[str] = None
    viewed_at: Optional[datetime] = None

class CustomEvent(BaseModel):
    """Custom event for flexible automation triggers"""
    email: EmailStr
    event_name: str
    event_data: Dict[str, Any] = {}
    occurred_at: Optional[datetime] = None

class WebhookEvent(BaseModel):
    """Generic webhook event from external systems"""
    event_type: str
    email: Optional[EmailStr] = None
    subscriber_id: Optional[str] = None
    payload: Dict[str, Any]


# ===========================
# HELPER FUNCTIONS
# ===========================

async def find_or_create_subscriber(email: str, event_data: dict = None):
    """
    Find subscriber by email or create basic record
    Returns subscriber_id or None
    """
    subscribers_collection = get_subscribers_collection()
    
    subscriber = await subscribers_collection.find_one({
        "email": email.lower().strip()
    })
    
    if subscriber:
        return str(subscriber["_id"])
    
    # Create basic subscriber record
    new_subscriber = {
        "_id": ObjectId(),
        "email": email.lower().strip(),
        "status": "active",
        "list": "events",  # Default list for event-created subscribers
        "source": "event_tracking",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "standard_fields": {},
        "custom_fields": event_data or {}
    }
    
    result = await subscribers_collection.insert_one(new_subscriber)
    logger.info(f"Created subscriber from event: {email}")
    
    return str(result.inserted_id)


async def log_event_activity(action: str, event_type: str, event_id: str, details: dict, request: Request = None):
    """Log event activity to audit trail"""
    try:
        audit_collection = get_audit_collection()
        log_entry = {
            "timestamp": datetime.utcnow(),
            "action": action,
            "entity_type": "event",
            "entity_id": event_id,
            "event_type": event_type,
            "user_action": details.get("user_action", ""),
            "metadata": {
                "ip_address": str(request.client.host) if request and request.client else "unknown",
                **details
            }
        }
        await audit_collection.insert_one(log_entry)
    except Exception as e:
        logger.error(f"Failed to log event activity: {e}")


# ===========================
# CART ABANDONMENT ENDPOINTS
# ===========================

@router.post("/cart-abandoned")
async def track_cart_abandonment(
    event: CartAbandonmentEvent,
    background_tasks: BackgroundTasks,
    request: Request
):
    """
    Track cart abandonment and trigger automation
    Can be called multiple times for the same subscriber
    
    Example usage:
```
    POST /events/cart-abandoned
    {
      "email": "user@example.com",
      "cart_id": "cart_abc123",
      "cart_value": 99.99,
      "cart_items": [
        {
          "product_id": "prod_1",
          "product_name": "Product Name",
          "quantity": 2,
          "price": 49.99
        }
      ],
      "cart_url": "https://shop.com/cart/abc123"
    }
```
    """
    try:
        events_collection = get_events_collection()
        
        # Find or create subscriber
        subscriber_id = await find_or_create_subscriber(
            event.email,
            {"last_cart_abandonment": datetime.utcnow()}
        )
        
        if not subscriber_id:
            raise HTTPException(
                status_code=400,
                detail="Could not find or create subscriber"
            )
        
        # Check for duplicate cart abandonment (within 1 hour)
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        duplicate = await events_collection.find_one({
            "event_type": "cart_abandoned",
            "subscriber_id": subscriber_id,
            "cart_id": event.cart_id,
            "created_at": {"$gte": one_hour_ago}
        })
        
        if duplicate:
            logger.info(f"Duplicate cart abandonment event within 1 hour, skipping")
            return {
                "status": "duplicate",
                "message": "Cart abandonment already tracked recently",
                "event_id": str(duplicate["_id"])
            }
        
        # Create event record
        event_record = {
            "_id": ObjectId(),
            "event_type": "cart_abandoned",
            "subscriber_id": subscriber_id,
            "email": event.email.lower().strip(),
            "cart_id": event.cart_id,
            "cart_value": event.cart_value,
            "currency": event.currency,
            "cart_items": [item.dict() for item in event.cart_items],
            "cart_url": event.cart_url,
            "abandoned_at": event.abandoned_at or datetime.utcnow(),
            "processed": False,
            "automation_triggered": False,
            "created_at": datetime.utcnow()
        }
        
        result = await events_collection.insert_one(event_record)
        event_id = str(result.inserted_id)
        
        logger.info(f"🛒 Cart abandoned: {event.email} - ${event.cart_value} - Cart ID: {event.cart_id}")
        
        # Prepare trigger data with cart details
        trigger_data = {
            "event_id": event_id,
            "event_type": "cart_abandoned",
            "cart_id": event.cart_id,
            "cart_value": event.cart_value,
            "currency": event.currency,
            "cart_items": [item.dict() for item in event.cart_items],
            "cart_url": event.cart_url,
            "abandoned_at": event_record["abandoned_at"].isoformat(),
            "item_count": len(event.cart_items),
            "first_item_name": event.cart_items[0].product_name if event.cart_items else ""
        }
        
        # Trigger abandoned cart automation
        background_tasks.add_task(
            trigger_automation_async,
            trigger_type="abandoned_cart",
            subscriber_id=subscriber_id,
            trigger_data=trigger_data,
            event_id=event_id
        )
        
        # Log activity
        await log_event_activity(
            action="cart_abandoned",
            event_type="cart_abandoned",
            event_id=event_id,
            details={
                "user_action": f"Cart abandoned by {event.email}",
                "cart_value": event.cart_value,
                "items_count": len(event.cart_items)
            },
            request=request
        )
        
        return {
            "status": "success",
            "message": "Cart abandonment tracked and automation triggered",
            "event_id": event_id,
            "subscriber_id": subscriber_id,
            "cart_value": event.cart_value,
            "items_count": len(event.cart_items)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cart abandonment tracking failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cart-recovered")
async def track_cart_recovery(
    email: EmailStr,
    cart_id: str,
    order_id: Optional[str] = None,
    request: Request = None
):
    """
    Track when abandoned cart is recovered (purchased)
    This cancels any active cart abandonment automations
    """
    try:
        events_collection = get_events_collection()
        subscribers_collection = get_subscribers_collection()
        
        # Find subscriber
        subscriber = await subscribers_collection.find_one({
            "email": email.lower().strip()
        })
        
        if not subscriber:
            return {
                "status": "subscriber_not_found",
                "message": "Subscriber not found"
            }
        
        subscriber_id = str(subscriber["_id"])
        
        # Find cart abandonment event
        cart_event = await events_collection.find_one({
            "event_type": "cart_abandoned",
            "subscriber_id": subscriber_id,
            "cart_id": cart_id,
            "processed": True
        })
        
        if cart_event:
            # Mark as recovered
            await events_collection.update_one(
                {"_id": cart_event["_id"]},
                {
                    "$set": {
                        "recovered": True,
                        "recovered_at": datetime.utcnow(),
                        "order_id": order_id
                    }
                }
            )
            
            logger.info(f"💰 Cart recovered: {email} - Cart ID: {cart_id}")
            
            # Cancel any active cart abandonment automations
            from tasks.automation_tasks import cancel_automation_workflow
            
            # Find and cancel abandoned_cart automations
            from database import get_automation_rules_collection
            rules_collection = get_automation_rules_collection()
            
            cart_rules = await rules_collection.find({
                "trigger": "abandoned_cart",
                "status": "active"
            }).to_list(None)
            
            cancelled_count = 0
            for rule in cart_rules:
                result = cancel_automation_workflow.delay(
                    str(rule["_id"]),
                    subscriber_id
                )
                cancelled_count += 1
            
            return {
                "status": "success",
                "message": "Cart recovery tracked, automations cancelled",
                "cart_id": cart_id,
                "automations_cancelled": cancelled_count
            }
        
        return {
            "status": "no_event",
            "message": "No cart abandonment event found"
        }
        
    except Exception as e:
        logger.error(f"Cart recovery tracking failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================
# PURCHASE EVENTS
# ===========================

@router.post("/purchase-completed")
async def track_purchase(
    event: PurchaseEvent,
    background_tasks: BackgroundTasks,
    request: Request
):
    """
    Track purchase completion and trigger post-purchase automation
    """
    try:
        events_collection = get_events_collection()
        
        # Find or create subscriber
        subscriber_id = await find_or_create_subscriber(
            event.email,
            {"last_purchase": datetime.utcnow()}
        )
        
        if not subscriber_id:
            raise HTTPException(
                status_code=400,
                detail="Could not find or create subscriber"
            )
        
        # Create event record
        event_record = {
            "_id": ObjectId(),
            "event_type": "purchase",
            "subscriber_id": subscriber_id,
            "email": event.email.lower().strip(),
            "order_id": event.order_id,
            "order_value": event.order_value,
            "currency": event.currency,
            "items": [item.dict() for item in event.items],
            "order_url": event.order_url,
            "purchased_at": event.purchased_at or datetime.utcnow(),
            "processed": False,
            "automation_triggered": False,
            "created_at": datetime.utcnow()
        }
        
        result = await events_collection.insert_one(event_record)
        event_id = str(result.inserted_id)
        
        logger.info(f"✅ Purchase completed: {event.email} - ${event.order_value} - Order: {event.order_id}")
        
        # Prepare trigger data
        trigger_data = {
            "event_id": event_id,
            "event_type": "purchase",
            "order_id": event.order_id,
            "order_value": event.order_value,
            "currency": event.currency,
            "items": [item.dict() for item in event.items],
            "order_url": event.order_url,
            "purchased_at": event_record["purchased_at"].isoformat(),
            "item_count": len(event.items)
        }
        
        # Trigger purchase automation
        background_tasks.add_task(
            trigger_automation_async,
            trigger_type="purchase",
            subscriber_id=subscriber_id,
            trigger_data=trigger_data,
            event_id=event_id
        )
        
        # Also cancel any cart abandonment automations
        if event.items:
            # Try to find and mark any abandoned carts as recovered
            await events_collection.update_many(
                {
                    "event_type": "cart_abandoned",
                    "subscriber_id": subscriber_id,
                    "recovered": {"$ne": True},
                    "created_at": {"$gte": datetime.utcnow() - timedelta(days=7)}
                },
                {
                    "$set": {
                        "recovered": True,
                        "recovered_at": datetime.utcnow(),
                        "order_id": event.order_id
                    }
                }
            )
        
        await log_event_activity(
            action="purchase",
            event_type="purchase",
            event_id=event_id,
            details={
                "user_action": f"Purchase by {event.email}",
                "order_value": event.order_value,
                "items_count": len(event.items)
            },
            request=request
        )
        
        return {
            "status": "success",
            "message": "Purchase tracked and automation triggered",
            "event_id": event_id,
            "subscriber_id": subscriber_id,
            "order_value": event.order_value
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Purchase tracking failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================
# PAGE VIEW EVENTS
# ===========================

@router.post("/page-viewed")
async def track_page_view(
    event: PageViewEvent,
    request: Request
):
    """
    Track page views for behavior-based automation
    """
    try:
        events_collection = get_events_collection()
        
        # Find subscriber (don't create for page views)
        subscriber_id = await find_or_create_subscriber(event.email)
        
        if not subscriber_id:
            return {
                "status": "subscriber_not_found",
                "message": "Subscriber not found"
            }
        
        # Create event record
        event_record = {
            "_id": ObjectId(),
            "event_type": "page_view",
            "subscriber_id": subscriber_id,
            "email": event.email.lower().strip(),
            "page_url": event.page_url,
            "page_title": event.page_title,
            "referrer": event.referrer,
            "viewed_at": event.viewed_at or datetime.utcnow(),
            "created_at": datetime.utcnow()
        }
        
        result = await events_collection.insert_one(event_record)
        event_id = str(result.inserted_id)
        
        logger.info(f"👁️ Page viewed: {event.email} - {event.page_url}")
        
        return {
            "status": "success",
            "message": "Page view tracked",
            "event_id": event_id
        }
        
    except Exception as e:
        logger.error(f"Page view tracking failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================
# CUSTOM EVENTS
# ===========================

@router.post("/custom-event")
async def track_custom_event(
    event: CustomEvent,
    background_tasks: BackgroundTasks,
    request: Request
):
    """
    Track custom events for flexible automation triggers
    
    Example: Track "webinar_registered", "trial_expired", "milestone_reached", etc.
    """
    try:
        events_collection = get_events_collection()
        
        # Find or create subscriber
        subscriber_id = await find_or_create_subscriber(event.email)
        
        if not subscriber_id:
            raise HTTPException(
                status_code=400,
                detail="Could not find or create subscriber"
            )
        
        # Create event record
        event_record = {
            "_id": ObjectId(),
            "event_type": "custom",
            "custom_event_name": event.event_name,
            "subscriber_id": subscriber_id,
            "email": event.email.lower().strip(),
            "event_data": event.event_data,
            "occurred_at": event.occurred_at or datetime.utcnow(),
            "processed": False,
            "automation_triggered": False,
            "created_at": datetime.utcnow()
        }
        
        result = await events_collection.insert_one(event_record)
        event_id = str(result.inserted_id)
        
        logger.info(f"🎯 Custom event: {event.event_name} - {event.email}")
        
        # Prepare trigger data
        trigger_data = {
            "event_id": event_id,
            "event_type": "custom",
            "custom_event_name": event.event_name,
            "event_data": event.event_data,
            "occurred_at": event_record["occurred_at"].isoformat()
        }
        
        # Trigger automation for custom event
        # Note: Custom events need to match automation trigger name exactly
        background_tasks.add_task(
            trigger_automation_async,
            trigger_type=event.event_name,  # Use event name as trigger type
            subscriber_id=subscriber_id,
            trigger_data=trigger_data,
            event_id=event_id
        )
        
        await log_event_activity(
            action="custom_event",
            event_type=event.event_name,
            event_id=event_id,
            details={
                "user_action": f"Custom event: {event.event_name}",
                "event_data": event.event_data
            },
            request=request
        )
        
        return {
            "status": "success",
            "message": f"Custom event '{event.event_name}' tracked",
            "event_id": event_id,
            "subscriber_id": subscriber_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Custom event tracking failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================
# WEBHOOK RECEIVER
# ===========================

@router.post("/webhook/{source}")
async def receive_webhook(
    source: str,
    event: WebhookEvent,
    background_tasks: BackgroundTasks,
    request: Request
):
    """
    Generic webhook receiver for external integrations
    
    Sources: shopify, woocommerce, stripe, zapier, etc.
    """
    try:
        events_collection = get_events_collection()
        
        # Extract email from payload
        email = event.email
        if not email and "email" in event.payload:
            email = event.payload["email"]
        
        if not email:
            raise HTTPException(
                status_code=400,
                detail="Email not found in webhook payload"
            )
        
        subscriber_id = await find_or_create_subscriber(email)
        
        # Create webhook event record
        event_record = {
            "_id": ObjectId(),
            "event_type": "webhook",
            "webhook_source": source,
            "webhook_event_type": event.event_type,
            "subscriber_id": subscriber_id,
            "email": email.lower().strip(),
            "payload": event.payload,
            "processed": False,
            "created_at": datetime.utcnow()
        }
        
        result = await events_collection.insert_one(event_record)
        event_id = str(result.inserted_id)
        
        logger.info(f"🔗 Webhook received: {source} - {event.event_type}")
        
        # Map webhook to automation trigger
        trigger_mapping = {
            "order.created": "purchase",
            "checkout.abandoned": "abandoned_cart",
            "customer.subscription.trial_end": "trial_expired",
            # Add more mappings as needed
        }
        
        trigger_type = trigger_mapping.get(event.event_type, event.event_type)
        
        # Trigger automation
        background_tasks.add_task(
            trigger_automation_async,
            trigger_type=trigger_type,
            subscriber_id=subscriber_id,
            trigger_data={
                "event_id": event_id,
                "webhook_source": source,
                "webhook_event_type": event.event_type,
                "payload": event.payload
            },
            event_id=event_id
        )
        
        return {
            "status": "success",
            "message": f"Webhook from {source} processed",
            "event_id": event_id,
            "trigger_type": trigger_type
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook processing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================
# EVENT QUERIES
# ===========================

@router.get("/subscriber/{subscriber_id}/events")
async def get_subscriber_events(
    subscriber_id: str,
    event_type: Optional[str] = None,
    limit: int = 50,
    skip: int = 0
):
    """Get all events for a subscriber"""
    try:
        events_collection = get_events_collection()
        
        query = {"subscriber_id": subscriber_id}
        if event_type:
            query["event_type"] = event_type
        
        events = await events_collection.find(query) \
            .sort("created_at", -1) \
            .skip(skip) \
            .limit(limit) \
            .to_list(limit)
        
        # Convert ObjectIds to strings
        for event in events:
            event["_id"] = str(event["_id"])
        
        return {
            "subscriber_id": subscriber_id,
            "events": events,
            "count": len(events)
        }
        
    except Exception as e:
        logger.error(f"Get subscriber events failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_event_stats(days: int = 7):
    """Get event statistics for the past N days"""
    try:
        events_collection = get_events_collection()
        
        start_date = datetime.utcnow() - timedelta(days=days)
        
        pipeline = [
            {"$match": {"created_at": {"$gte": start_date}}},
            {"$group": {
                "_id": "$event_type",
                "count": {"$sum": 1}
            }}
        ]
        
        results = await events_collection.aggregate(pipeline).to_list(None)
        
        stats = {
            "period_days": days,
            "total_events": sum(r["count"] for r in results),
            "by_type": {r["_id"]: r["count"] for r in results}
        }
        
        return stats
        
    except Exception as e:
        logger.error(f"Get event stats failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================
# HELPER FUNCTION
# ===========================

def trigger_automation_async(trigger_type: str, subscriber_id: str, trigger_data: dict, event_id: str):
    """Async helper to trigger automation and mark event as processed"""
    try:
        # Trigger automation
        result = process_automation_trigger.delay(
            trigger_type=trigger_type,
            subscriber_id=subscriber_id,
            trigger_data=trigger_data
        )
        
        # Mark event as processed (sync operation)
        from database import get_sync_events_collection
        events_collection = get_sync_events_collection()
        
        events_collection.update_one(
            {"_id": ObjectId(event_id)},
            {
                "$set": {
                    "processed": True,
                    "automation_triggered": True,
                    "processed_at": datetime.utcnow(),
                    "automation_task_id": result.id
                }
            }
        )
        
        logger.info(f"✅ Event {event_id} processed, automation triggered")
        
    except Exception as e:
        logger.error(f"Failed to trigger automation for event {event_id}: {e}")
