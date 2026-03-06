# backend/scripts/create_event_indexes.py
"""
Create database indexes for events collection
Run once: python -m backend.scripts.create_event_indexes
"""
import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_events_collection
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_indexes():
    """Create all necessary indexes for events"""
    events_collection = get_events_collection()
    
    logger.info("Creating indexes for events collection...")
    
    # Subscriber + Event Type + Date
    await events_collection.create_index([
        ("subscriber_id", 1),
        ("event_type", 1),
        ("created_at", -1)
    ])
    logger.info("✅ Created index: subscriber + event_type + created_at")
    
    # Email lookup
    await events_collection.create_index([("email", 1)])
    logger.info("✅ Created index: email")
    
    # Cart ID lookup (for abandonment)
    await events_collection.create_index([("cart_id", 1)])
    logger.info("✅ Created index: cart_id")
    
    # Order ID lookup (for purchases)
    await events_collection.create_index([("order_id", 1)])
    logger.info("✅ Created index: order_id")
    
    # Processed status
    await events_collection.create_index([
        ("event_type", 1),
        ("processed", 1),
        ("created_at", -1)
    ])
    logger.info("✅ Created index: event_type + processed + created_at")
    
    # Custom event name
    await events_collection.create_index([("custom_event_name", 1)])
    logger.info("✅ Created index: custom_event_name")
    
    # Webhook source
    await events_collection.create_index([
        ("webhook_source", 1),
        ("webhook_event_type", 1)
    ])
    logger.info("✅ Created index: webhook_source + webhook_event_type")
    
    logger.info("✨ All event indexes created successfully!")


if __name__ == "__main__":
    asyncio.run(create_indexes())
