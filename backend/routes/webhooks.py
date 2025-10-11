# backend/routes/webhooks.py
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from pydantic import BaseModel, validator
import redis.asyncio as redis
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
import aiohttp
import hashlib
import hmac
import base64
from urllib.parse import urlparse
import asyncio
from contextlib import asynccontextmanager

# 🔥 NEW: Import your database and suppression functions
from database import get_email_logs_collection, get_subscribers_collection, get_suppressions_collection
from models.suppression_filter import create_suppression_from_bounce, create_suppression_from_complaint
from bson import ObjectId

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)

# Redis connection pool
redis_pool = None

# Webhook configuration
WEBHOOK_CONFIG = {
    "verify_sns_signature": True,  # Set to False for development
    "auto_confirm_subscription": True,
    "max_message_age": 300,  # 5 minutes
    "supported_regions": ["us-east-1", "us-west-2", "eu-west-1"],
    "rate_limit_per_minute": 10000
}

async def get_redis_pool():
    """Initialize and return Redis connection pool"""
    global redis_pool
    if not redis_pool:
        redis_pool = redis.ConnectionPool.from_url(
            "redis://redis:6379/0",
            max_connections=50,
            decode_responses=True,
            retry_on_timeout=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
    return redis_pool

@asynccontextmanager
async def get_redis_client():
    """Async context manager for Redis client"""
    pool = await get_redis_pool()
    client = redis.Redis(connection_pool=pool)
    try:
        yield client
    finally:
        await client.close()

# Pydantic models for request validation
class SNSPayload(BaseModel):
    Type: str
    Message: str = ""
    MessageId: Optional[str] = None
    TopicArn: Optional[str] = None
    Subject: Optional[str] = None
    Timestamp: Optional[str] = None
    SignatureVersion: Optional[str] = None
    Signature: Optional[str] = None
    SigningCertURL: Optional[str] = None
    SubscribeURL: Optional[str] = None
    UnsubscribeURL: Optional[str] = None
    Token: Optional[str] = None

    @validator('Type')
    def validate_type(cls, v):
        valid_types = ['SubscriptionConfirmation', 'Notification', 'UnsubscribeConfirmation']
        if v not in valid_types:
            raise ValueError(f'Invalid SNS message type: {v}')
        return v

class WebhookStats(BaseModel):
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    events_processed: Dict[str, int] = {}
    queue_sizes: Dict[str, int] = {}
    last_reset: str = datetime.utcnow().isoformat()

# 🔥 FIX: Thread-safe stats using Redis instead of global variable
async def get_webhook_stats() -> WebhookStats:
    """Get webhook stats from Redis (thread-safe)"""
    try:
        async with get_redis_client() as redis_client:
            stats_data = await redis_client.get("webhook_stats")
            if stats_data:
                return WebhookStats(**json.loads(stats_data))
            return WebhookStats()
    except Exception as e:
        logger.error(f"Error getting webhook stats: {e}")
        return WebhookStats()

async def update_webhook_stats(update_dict: Dict[str, Any]):
    """Update webhook stats in Redis"""
    try:
        async with get_redis_client() as redis_client:
            current_stats = await get_webhook_stats()
            for key, value in update_dict.items():
                if hasattr(current_stats, key):
                    if isinstance(getattr(current_stats, key), dict):
                        current_dict = getattr(current_stats, key)
                        if isinstance(value, dict):
                            current_dict.update(value)
                        else:
                            current_dict[key] = current_dict.get(key, 0) + value
                    else:
                        setattr(current_stats, key, getattr(current_stats, key) + value)
            
            await redis_client.set("webhook_stats", current_stats.json(), ex=3600)
    except Exception as e:
        logger.error(f"Error updating webhook stats: {e}")

async def verify_sns_signature(payload: SNSPayload) -> bool:
    """Verify SNS message signature for security"""
    if not WEBHOOK_CONFIG["verify_sns_signature"]:
        return True
    
    try:
        # Download and verify the signing certificate
        if not payload.SigningCertURL:
            logger.warning("Missing SigningCertURL in SNS message")
            return False
        
        # Verify the certificate URL is from AWS
        parsed_url = urlparse(payload.SigningCertURL)
        if not (parsed_url.netloc.endswith('.amazonaws.com') and
                parsed_url.scheme == 'https'):
            logger.warning(f"Invalid certificate URL: {payload.SigningCertURL}")
            return False
        
        # 🔥 TODO: In production, implement full certificate verification
        # For now, basic URL validation
        return True
        
    except Exception as e:
        logger.error(f"SNS signature verification failed: {e}")
        return False

async def confirm_sns_subscription(subscribe_url: str) -> bool:
    """Confirm SNS subscription automatically"""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(subscribe_url) as response:
                if response.status == 200:
                    logger.info("SNS subscription confirmed successfully")
                    return True
                else:
                    logger.error(f"Failed to confirm SNS subscription: {response.status}")
                    return False
    except Exception as e:
        logger.error(f"Error confirming SNS subscription: {e}")
        return False

def parse_ses_message(message: str) -> Optional[Dict[str, Any]]:
    """Parse and validate SES message from SNS"""
    try:
        ses_message = json.loads(message)
        
        # Validate required fields
        if 'eventType' not in ses_message:
            logger.warning("Missing eventType in SES message")
            return None
        
        if 'mail' not in ses_message:
            logger.warning("Missing mail object in SES message")
            return None
            
        return ses_message
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse SES message JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"Error parsing SES message: {e}")
        return None

# 🔥 NEW: Enhanced SES event processing with suppression integration
async def process_ses_event_immediate(ses_message: Dict[str, Any]) -> bool:
    """Process critical SES events immediately (bounces, complaints)"""
    try:
        event_type = ses_message.get('eventType', '').lower()
        mail_data = ses_message.get('mail', {})
        
        # Extract recipient email
        destination = mail_data.get('destination', [])
        if not destination:
            logger.warning("No destination email found in SES message")
            return False
            
        recipient_email = destination[0] if isinstance(destination, list) else destination
        message_id = mail_data.get('messageId')
        
        # Update your email logs collection
        email_logs_collection = get_email_logs_collection()
        
        # Find the corresponding email log entry
        email_log_query = {}
        if message_id:
            email_log_query["message_id"] = message_id
        else:
            email_log_query["email"] = recipient_email
            
        # Update email log status
        await email_logs_collection.update_many(
            email_log_query,
            {
                "$set": {
                    f"{event_type}_at": datetime.utcnow(),
                    "latest_status": event_type,
                    "last_event_at": datetime.utcnow()
                },
                "$push": {
                    "status_history": {
                        "status": event_type,
                        "ts": datetime.utcnow(),
                        "ses_event_data": ses_message
                    }
                }
            }
        )
        
        # 🔥 NEW: Create suppressions for bounces and complaints
        if event_type == 'bounce':
            bounce_data = ses_message.get('bounce', {})
            bounce_type = bounce_data.get('bounceType', '').lower()
            
            if bounce_type in ['permanent', 'transient']:
                await create_suppression_from_bounce(
                    email=recipient_email,
                    bounce_type='hard' if bounce_type == 'permanent' else 'soft',
                    metadata={
                        'ses_message_id': message_id,
                        'bounce_sub_type': bounce_data.get('bounceSubType'),
                        'bounce_timestamp': bounce_data.get('timestamp'),
                        'diagnostic_code': bounce_data.get('diagnosticCode')
                    }
                )
                
        elif event_type == 'complaint':
            await create_suppression_from_complaint(
                email=recipient_email,
                metadata={
                    'ses_message_id': message_id,
                    'complaint_feedback_type': ses_message.get('complaint', {}).get('complaintFeedbackType'),
                    'complaint_timestamp': ses_message.get('complaint', {}).get('timestamp')
                }
            )
            
        # Update subscriber status
        subscribers_collection = get_subscribers_collection()
        if event_type in ['bounce', 'complaint']:
            new_status = 'bounced' if event_type == 'bounce' else 'complained'
            await subscribers_collection.update_many(
                {"email": recipient_email},
                {
                    "$set": {
                        "status": new_status,
                        "updated_at": datetime.utcnow(),
                        f"last_{event_type}": datetime.utcnow()
                    },
                    "$inc": {f"{event_type}_count": 1}
                }
            )
            
        logger.info(f"Processed SES {event_type} event for {recipient_email}")
        return True
        
    except Exception as e:
        logger.error(f"Error processing SES event immediately: {e}")
        return False

# 🔥 FIX: Improved event queuing with proper Redis management
async def queue_ses_event(event_payload: Dict[str, Any]) -> bool:
    """Queue SES event for processing with error handling"""
    try:
        async with get_redis_client() as redis_client:
            # Serialize event payload
            event_json = json.dumps(event_payload, default=str)
            event_type = event_payload.get("event_type", "unknown")
            
            # Process critical events immediately AND queue them
            if event_type in ['bounce', 'complaint', 'reject']:
                # Immediate processing for suppression creation
                ses_message = json.loads(event_payload.get("message", "{}"))
                await process_ses_event_immediate(ses_message)
                
                queue_name = "ses_events_critical"
                # Trigger additional background processing
                try:
                    from tasks.ses_webhook_tasks import process_critical_ses_events
                    process_critical_ses_events.apply_async(countdown=0.1)
                except ImportError:
                    logger.warning("SES webhook tasks not available")
            else:
                queue_name = "ses_events_normal"
                try:
                    from tasks.ses_webhook_tasks import process_ses_events_batch
                    process_ses_events_batch.apply_async(countdown=0.1)
                except ImportError:
                    logger.warning("SES webhook tasks not available")
            
            # Queue the event
            await redis_client.lpush(queue_name, event_json)
            
            # Update stats
            await update_webhook_stats({
                "events_processed": {event_type: 1}
            })
            
            logger.info(f"SES event queued and processed: {event_type} -> {queue_name}")
            return True
            
    except Exception as e:
        logger.error(f"Failed to queue SES event: {e}")
        return False

@router.post("/ses-events")
async def handle_ses_webhook(request: Request, background_tasks: BackgroundTasks):
    """Main SES webhook endpoint with enhanced processing"""
    start_time = datetime.utcnow()
    
    # Update request stats
    await update_webhook_stats({"total_requests": 1})
    
    try:
        # Get request body
        body = await request.body()
        if not body:
            raise HTTPException(status_code=400, detail="Empty request body")

        # Parse JSON payload
        try:
            raw_payload = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        # Validate payload structure
        try:
            payload = SNSPayload(**raw_payload)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid SNS payload: {str(e)}")

        # Verify SNS signature (in production)
        if not await verify_sns_signature(payload):
            raise HTTPException(status_code=403, detail="Invalid SNS signature")

        # Handle different SNS message types
        if payload.Type == 'SubscriptionConfirmation':
            if WEBHOOK_CONFIG["auto_confirm_subscription"] and payload.SubscribeURL:
                # Confirm subscription in background
                background_tasks.add_task(confirm_sns_subscription, payload.SubscribeURL)
                return {
                    "status": "subscription_confirmation_initiated",
                    "message": "SNS subscription confirmation initiated"
                }
            else:
                return {
                    "status": "subscription_confirmation_required",
                    "message": "Manual SNS subscription confirmation required",
                    "subscribe_url": payload.SubscribeURL
                }

        elif payload.Type == 'UnsubscribeConfirmation':
            logger.warning("SNS unsubscribe confirmation received")
            return {
                "status": "unsubscribe_confirmed",
                "message": "SNS unsubscription confirmed"
            }

        elif payload.Type == 'Notification':
            # Parse SES message
            ses_message = parse_ses_message(payload.Message)
            if not ses_message:
                raise HTTPException(status_code=400, detail="Invalid SES message format")

            # Extract event details
            event_type = ses_message.get('eventType', '').lower()
            mail_data = ses_message.get('mail', {})
            message_id = mail_data.get('messageId')
            
            if not message_id:
                logger.warning("Missing messageId in SES message")
                raise HTTPException(status_code=400, detail="Missing messageId in SES message")

            # Create event payload for queue
            event_payload = {
                "service": "ses",
                "message": payload.Message,
                "event_type": event_type,
                "message_id": message_id,
                "sns_message_id": payload.MessageId,
                "topic_arn": payload.TopicArn,
                "received_at": datetime.utcnow().isoformat(),
                "webhook_version": "1.1",  # Updated version
                "recipient_email": mail_data.get('destination', [None])[0] if mail_data.get('destination') else None
            }

            # Queue event for processing
            success = await queue_ses_event(event_payload)
            
            if success:
                await update_webhook_stats({"successful_requests": 1})
                processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                return {
                    "status": "success",
                    "event_type": event_type,
                    "message_id": message_id,
                    "queued_to": "ses_events_critical" if event_type in ['bounce', 'complaint', 'reject'] else "ses_events_normal",
                    "processing_time_ms": round(processing_time, 2),
                    "timestamp": datetime.utcnow().isoformat(),
                    "immediate_processing": event_type in ['bounce', 'complaint', 'reject']
                }
            else:
                await update_webhook_stats({"failed_requests": 1})
                raise HTTPException(status_code=500, detail="Failed to queue event for processing")

        else:
            logger.warning(f"Unknown SNS message type: {payload.Type}")
            return {
                "status": "ignored",
                "message": f"Unknown SNS message type: {payload.Type}"
            }

    except HTTPException:
        await update_webhook_stats({"failed_requests": 1})
        raise
    except Exception as e:
        await update_webhook_stats({"failed_requests": 1})
        logger.exception("Unexpected error in SES webhook")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/health")
async def webhook_health():
    """Comprehensive webhook health check"""
    try:
        health_status = {
            "status": "healthy",
            "service": "ses_webhook",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.1"
        }

        # Check Redis connectivity
        try:
            async with get_redis_client() as redis_client:
                await redis_client.ping()
                health_status["redis_connected"] = True
        except Exception as e:
            health_status["redis_connected"] = False
            health_status["redis_error"] = str(e)
            health_status["status"] = "degraded"

        # Check queue sizes
        try:
            async with get_redis_client() as redis_client:
                queue_sizes = {
                    "critical": await redis_client.llen("ses_events_critical"),
                    "normal": await redis_client.llen("ses_events_normal"),
                    "failed": await redis_client.llen("ses_events_failed")
                }
                health_status["queue_sizes"] = queue_sizes
                
                # Alert if queues are backing up
                total_queued = sum(queue_sizes.values())
                if total_queued > 1000:
                    health_status["status"] = "degraded"
                    health_status["warning"] = f"High queue backlog: {total_queued} events pending"
        except Exception as e:
            health_status["queue_check_error"] = str(e)

        # Include webhook stats
        webhook_stats = await get_webhook_stats()
        health_status["stats"] = {
            "total_requests": webhook_stats.total_requests,
            "successful_requests": webhook_stats.successful_requests,
            "failed_requests": webhook_stats.failed_requests,
            "success_rate": round(
                (webhook_stats.successful_requests / max(webhook_stats.total_requests, 1)) * 100, 2
            )
        }

        return health_status

    except Exception as e:
        logger.exception("Health check error")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

@router.get("/stats")
async def webhook_statistics():
    """Detailed webhook statistics"""
    try:
        async with get_redis_client() as redis_client:
            # Get queue information
            queue_info = {
                "critical": {
                    "size": await redis_client.llen("ses_events_critical"),
                    "description": "High priority events (bounces, complaints)"
                },
                "normal": {
                    "size": await redis_client.llen("ses_events_normal"),
                    "description": "Standard events (delivery, open, click)"
                },
                "failed": {
                    "size": await redis_client.llen("ses_events_failed"),
                    "description": "Failed processing events"
                }
            }

        webhook_stats = await get_webhook_stats()

        return {
            "webhook_stats": webhook_stats.dict(),
            "queue_info": queue_info,
            "configuration": {
                "verify_sns_signature": WEBHOOK_CONFIG["verify_sns_signature"],
                "auto_confirm_subscription": WEBHOOK_CONFIG["auto_confirm_subscription"],
                "max_message_age": WEBHOOK_CONFIG["max_message_age"],
                "supported_regions": WEBHOOK_CONFIG["supported_regions"]
            },
            "supported_events": [
                "send", "delivery", "bounce", "complaint",
                "open", "click", "reject"
            ],
            "endpoints": {
                "webhook": "/api/webhooks/ses-events",
                "health": "/api/webhooks/health",
                "stats": "/api/webhooks/stats",
                "test": "/api/webhooks/test"
            }
        }
    except Exception as e:
        logger.exception("Error getting webhook stats")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/test")
async def test_webhook():
    """Test webhook endpoint with sample SES event"""
    sample_ses_event = {
        "Type": "Notification",
        "MessageId": "test-message-id",
        "TopicArn": "arn:aws:sns:us-east-1:123456789012:ses-events",
        "Message": json.dumps({
            "eventType": "delivery",
            "mail": {
                "messageId": "test-ses-message-id-" + datetime.utcnow().strftime("%Y%m%d%H%M%S"),
                "source": "test@example.com",
                "destination": ["recipient@example.com"]
            },
            "delivery": {
                "timestamp": "2025-09-08T06:00:00.000Z",
                "processingTimeMillis": 1234
            }
        }),
        "Timestamp": datetime.utcnow().isoformat(),
        "SignatureVersion": "1",
        "Signature": "test-signature"
    }

    try:
        # Process test event
        event_payload = {
            "service": "ses",
            "message": sample_ses_event["Message"],
            "event_type": "delivery",
            "message_id": "test-ses-message-id-" + datetime.utcnow().strftime("%Y%m%d%H%M%S"),
            "sns_message_id": sample_ses_event["MessageId"],
            "received_at": datetime.utcnow().isoformat(),
            "test_event": True
        }

        success = await queue_ses_event(event_payload)
        return {
            "status": "success" if success else "failed",
            "message": "Test event processed",
            "event": event_payload,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.exception("Test webhook error")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/queues/clear")
async def clear_webhook_queues():
    """Clear all webhook queues (admin operation)"""
    try:
        async with get_redis_client() as redis_client:
            cleared_counts = {
                "critical": await redis_client.delete("ses_events_critical") or 0,
                "normal": await redis_client.delete("ses_events_normal") or 0,
                "failed": await redis_client.delete("ses_events_failed") or 0
            }

            # Reset stats
            await redis_client.delete("webhook_stats")

        logger.warning("All webhook queues cleared by admin request")
        return {
            "status": "success",
            "message": "All webhook queues cleared",
            "cleared_counts": cleared_counts,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.exception("Error clearing webhook queues")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/queues/inspect/{queue_name}")
async def inspect_queue(queue_name: str, limit: int = 10):
    """Inspect queue contents for debugging"""
    valid_queues = ["ses_events_critical", "ses_events_normal", "ses_events_failed"]
    if queue_name not in valid_queues:
        raise HTTPException(status_code=400, detail=f"Invalid queue name. Must be one of: {valid_queues}")

    try:
        async with get_redis_client() as redis_client:
            # Get queue size
            queue_size = await redis_client.llen(queue_name)
            
            # Get sample items (without removing them)
            items = []
            if queue_size > 0:
                raw_items = await redis_client.lrange(queue_name, 0, limit - 1)
                for item in raw_items:
                    try:
                        parsed_item = json.loads(item)
                        items.append(parsed_item)
                    except json.JSONDecodeError:
                        items.append({"raw": item, "parse_error": True})

        return {
            "queue_name": queue_name,
            "total_size": queue_size,
            "sample_size": len(items),
            "items": items,
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.exception(f"Error inspecting queue {queue_name}")
        raise HTTPException(status_code=500, detail=str(e))

