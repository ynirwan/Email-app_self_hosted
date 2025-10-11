# utils/field_handler.py
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Field tier definitions
FIELD_TIERS = {
    "universal": ["email"],
    "standard": [
        "first_name", "last_name"
    ]
}

def get_subscriber_field_value(subscriber: dict, mapping: str, template_field: str, fallback_values: dict = None) -> str:
    """Extract field value from subscriber using three-tier system"""
    
    fallback_values = fallback_values or {}
    
    if mapping == "__EMPTY__":
        return ""
    
    if mapping == "__DEFAULT__":
        return fallback_values.get(template_field, f"[{template_field}]")
    
    if "." not in mapping:
        # Legacy mapping - try to find in any tier
        return get_legacy_field_value(subscriber, mapping)
    
    tier, field_name = mapping.split(".", 1)
    
    try:
        if tier == "universal":
            # Universal fields are at root level
            value = subscriber.get(field_name)
        
        elif tier == "standard":
            # Standard fields are in standard_fields object
            standard_fields = subscriber.get("standard_fields", {})
            value = standard_fields.get(field_name)
        
        elif tier == "custom":
            # Custom fields are in custom_fields object
            custom_fields = subscriber.get("custom_fields", {})
            value = custom_fields.get(field_name)
        
        else:
            logger.warning(f"Unknown tier: {tier}")
            value = None
        
        # Return value or fallback
        if value and str(value).strip():
            return str(value)
        else:
            return fallback_values.get(template_field, "")
    
    except Exception as e:
        logger.error(f"Error extracting field {mapping} for {template_field}: {e}")
        return fallback_values.get(template_field, f"[Error: {template_field}]")

def get_legacy_field_value(subscriber: dict, field_name: str) -> str:
    """Fallback for legacy field mappings - search all tiers"""
    
    # Try universal fields first
    if field_name in subscriber:
        return str(subscriber[field_name])
    
    # Try standard fields
    standard_fields = subscriber.get("standard_fields", {})
    if field_name in standard_fields:
        return str(standard_fields[field_name])
    
    # Try custom fields
    custom_fields = subscriber.get("custom_fields", {})
    if field_name in custom_fields:
        return str(custom_fields[field_name])
    
    return ""

async def render_email_for_subscriber(template_content: str, subscriber: dict, field_map: dict, fallback_values: dict = None) -> str:
    """Render email template with three-tier field support"""
    
    rendered_content = template_content
    fallback_values = fallback_values or {}
    
    # Process each mapped field
    for template_field, mapping in field_map.items():
        placeholder = f"{{{template_field}}}"
        
        if placeholder not in rendered_content:
            continue
        
        value = get_subscriber_field_value(subscriber, mapping, template_field, fallback_values)
        rendered_content = rendered_content.replace(placeholder, str(value))
    
    return rendered_content

def count_populated_fields(subscriber: dict) -> int:
    """Count how many fields have actual data"""
    count = 0
    
    # Count universal fields
    if subscriber.get("email"):
        count += 1
    
    # Count standard fields
    standard_fields = subscriber.get("standard_fields", {})
    count += len([v for v in standard_fields.values() if v and str(v).strip()])
    
    # Count custom fields
    custom_fields = subscriber.get("custom_fields", {})
    count += len([v for v in custom_fields.values() if v and str(v).strip()])
    
    return count

def create_mock_subscriber_tiered() -> dict:
    """Create a mock subscriber with sample data for all tiers"""
    from datetime import datetime
    
    return {
        "email": "test@example.com",
        "list": "sample_list",
        "status": "active",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "standard_fields": {
            "first_name": "John",
            "last_name": "Doe",
            "phone": "+1-555-123-4567",
            "company": "Sample Company Inc.",
            "country": "United States",
            "city": "New York",
            "job_title": "Marketing Manager"
        },
        "custom_fields": {
            "membership_level": "Premium",
            "signup_source": "website",
            "last_purchase": "2024-01-15",
            "preferences": "newsletter,promotions"
        }
    }






async def get_sample_subscriber_tiered(target_lists: List[str], preferred_list: str = None, subscriber_id: str = None) -> dict:
    """Get a sample subscriber with rich field data for testing"""
    
    from database import get_subscribers_collection
    subscribers_collection = get_subscribers_collection()
    
    query = {"list": {"$in": target_lists}, "status": "active"}
    
    if subscriber_id and ObjectId.is_valid(subscriber_id):
        query["_id"] = ObjectId(subscriber_id)
    elif preferred_list:
        query["list"] = preferred_list
    
    # Find subscriber with most populated fields
    try:
        subscribers = await subscribers_collection.find(query).to_list(10)
        
        if not subscribers:
            # Return mock subscriber for testing
            logger.info("No real subscribers found, using mock data for test")
            return create_mock_subscriber_tiered()
        
        # Choose subscriber with most field data
        best_subscriber = max(subscribers, key=lambda s: count_populated_fields(s))
        logger.info(f"Using subscriber with {count_populated_fields(best_subscriber)} populated fields for test")
        
        return best_subscriber
        
    except Exception as e:
        logger.error(f"Error fetching sample subscriber: {e}")
        return create_mock_subscriber_tiered()


