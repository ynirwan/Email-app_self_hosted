# utils/field_mapping.py
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
from ..database import subscribers_collection
from ..config.field_tiers import FIELD_TIERS

logger = logging.getLogger(__name__)

async def render_email_for_subscriber(
    template_content: str, 
    subscriber: dict, 
    field_map: Dict[str, str],
    fallback_values: Optional[Dict[str, str]] = None
) -> str:
    """
    Render email template with three-tier field support
    """
    rendered_content = template_content
    fallback_values = fallback_values or {}
    
    # Process each mapped field
    for template_field, mapping in field_map.items():
        placeholder = f"{{{template_field}}}"
        if placeholder not in rendered_content:
            continue
        
        value = get_subscriber_field_value(
            subscriber, 
            mapping, 
            template_field, 
            fallback_values
        )
        
        # Replace placeholder with actual value
        rendered_content = rendered_content.replace(placeholder, str(value))
    
    return rendered_content

def get_subscriber_field_value(
    subscriber: dict, 
    mapping: str, 
    template_field: str, 
    fallback_values: Dict[str, str]
) -> str:
    """
    Extract field value from subscriber using three-tier system
    """
    if mapping == "__EMPTY__":
        return ""
    
    if mapping == "__DEFAULT__":
        return fallback_values.get(template_field, f"[{template_field}]")
    
    if "." not in mapping:
        # Legacy mapping - try to find in any tier
        return get_legacy_field_value(subscriber, mapping)
    
    tier, field_name = mapping.split(".", 1)
    
    try:
        value = None
        
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
        if value is not None and str(value).strip():
            return str(value)
        else:
            return fallback_values.get(template_field, "")
            
    except Exception as e:
        logger.error(f"Error extracting field {mapping} for {template_field}: {e}")
        return fallback_values.get(template_field, f"[Error: {template_field}]")

def get_legacy_field_value(subscriber: dict, field_name: str) -> str:
    """
    Fallback for legacy field mappings - search all tiers
    """
    # Try universal fields first
    if field_name in subscriber:
        value = subscriber[field_name]
        if value is not None:
            return str(value)
    
    # Try standard fields
    standard_fields = subscriber.get("standard_fields", {})
    if field_name in standard_fields:
        value = standard_fields[field_name]
        if value is not None:
            return str(value)
    
    # Try custom fields
    custom_fields = subscriber.get("custom_fields", {})
    if field_name in custom_fields:
        value = custom_fields[field_name]
        if value is not None:
            return str(value)
    
    return ""

async def get_campaign_subscribers_tiered(target_lists: List[str]) -> List[dict]:
    """
    Get subscribers from target lists with three-tier field structure
    """
    query = {
        "list": {"$in": target_lists},
        "status": "active"  # Only active subscribers
    }
    
    subscribers = await subscribers_collection.find(query).to_list(None)
    
    # Ensure all subscribers have proper three-tier structure
    normalized_subscribers = []
    
    for sub in subscribers:
        normalized_sub = {
            "email": sub.get("email", ""),
            "list": sub.get("list", ""),
            "status": sub.get("status", "active"),
            "created_at": sub.get("created_at"),
            "updated_at": sub.get("updated_at"),
            "standard_fields": sub.get("standard_fields", {}),
            "custom_fields": sub.get("custom_fields", {})
        }
        
        # Handle legacy data - move non-system fields to appropriate tiers
        system_fields = {
            "_id", "email", "list", "status", "created_at", "updated_at", 
            "standard_fields", "custom_fields"
        }
        
        for key, value in sub.items():
            if key not in system_fields:
                # Determine if this should be standard or custom field
                if key in FIELD_TIERS["standard"]:
                    normalized_sub["standard_fields"][key] = value
                else:
                    normalized_sub["custom_fields"][key] = value
        
        normalized_subscribers.append(normalized_sub)
    
    return normalized_subscribers

async def get_sample_subscriber_tiered(
    target_lists: List[str], 
    preferred_list: Optional[str] = None,
    subscriber_id: Optional[str] = None
) -> dict:
    """
    Get a sample subscriber with rich field data for testing
    """
    query = {"list": {"$in": target_lists}, "status": "active"}
    
    if subscriber_id:
        from bson import ObjectId
        query["_id"] = ObjectId(subscriber_id)
    elif preferred_list:
        query["list"] = preferred_list
    
    # Find subscriber with most populated fields
    subscribers = await subscribers_collection.find(query).limit(10).to_list(None)
    
    if not subscribers:
        # Return mock subscriber for testing
        return create_mock_subscriber_tiered(target_lists[0] if target_lists else "sample_list")
    
    # Choose subscriber with most field data
    best_subscriber = max(subscribers, key=lambda s: count_populated_fields(s))
    
    # Normalize the subscriber structure
    return normalize_subscriber_structure(best_subscriber)

def count_populated_fields(subscriber: dict) -> int:
    """
    Count how many fields have actual data
    """
    count = 0
    
    # Count universal fields
    if subscriber.get("email"):
        count += 1
    
    # Count standard fields
    standard_fields = subscriber.get("standard_fields", {})
    count += len([v for v in standard_fields.values() if v is not None and str(v).strip()])
    
    # Count custom fields
    custom_fields = subscriber.get("custom_fields", {})
    count += len([v for v in custom_fields.values() if v is not None and str(v).strip()])
    
    return count

def normalize_subscriber_structure(subscriber: dict) -> dict:
    """
    Ensure subscriber has proper three-tier structure
    """
    normalized = {
        "email": subscriber.get("email", ""),
        "list": subscriber.get("list", ""),
        "status": subscriber.get("status", "active"),
        "created_at": subscriber.get("created_at"),
        "updated_at": subscriber.get("updated_at"),
        "standard_fields": subscriber.get("standard_fields", {}),
        "custom_fields": subscriber.get("custom_fields", {})
    }
    
    # Handle legacy fields
    system_fields = {
        "_id", "email", "list", "status", "created_at", "updated_at", 
        "standard_fields", "custom_fields"
    }
    
    for key, value in subscriber.items():
        if key not in system_fields and value is not None:
            if key in FIELD_TIERS["standard"]:
                normalized["standard_fields"][key] = value
            else:
                normalized["custom_fields"][key] = value
    
    return normalized

def create_mock_subscriber_tiered(list_name: str = "sample_list") -> dict:
    """
    Create a mock subscriber with sample data for all tiers
    """
    return {
        "email": "test@example.com",
        "list": list_name,
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

def suggest_field_mapping(template_field: str, available_fields: Dict[str, List[str]]) -> List[Dict[str, str]]:
    """
    Suggest field mappings based on template field name
    """
    suggestions = []
    field_lower = template_field.lower().strip()
    
    # Universal field suggestions
    if "email" in field_lower:
        suggestions.append({"tier": "universal", "field_name": "email", "confidence": 1.0})
    
    # Standard field suggestions
    standard_mappings = {
        "first_name": ["first", "fname", "firstname", "given_name"],
        "last_name": ["last", "lname", "lastname", "surname", "family_name"],
        "phone": ["phone", "mobile", "telephone", "tel"],
        "company": ["company", "organization", "org", "business"],
        "country": ["country", "nation"],
        "city": ["city", "town", "locality"],
        "job_title": ["title", "position", "job", "role"]
    }
    
    for std_field, keywords in standard_mappings.items():
        if std_field in available_fields.get("standard", []):
            for keyword in keywords:
                if keyword in field_lower:
                    confidence = 0.9 if keyword == field_lower else 0.7
                    suggestions.append({
                        "tier": "standard", 
                        "field_name": std_field, 
                        "confidence": confidence
                    })
                    break
    
    # Custom field suggestions
    for custom_field in available_fields.get("custom", []):
        if custom_field.lower() in field_lower or field_lower in custom_field.lower():
            confidence = 0.8 if custom_field.lower() == field_lower else 0.6
            suggestions.append({
                "tier": "custom", 
                "field_name": custom_field, 
                "confidence": confidence
            })
    
    # Sort by confidence
    suggestions.sort(key=lambda x: x["confidence"], reverse=True)
    
    return suggestions[:3]  # Return top 3 suggestions

def auto_suggest_csv_mappings(csv_columns: List[str]) -> Dict[str, Dict[str, str]]:
    """
    Auto-suggest mappings for CSV columns
    """
    suggestions = {}
    
    for col in csv_columns:
        col_lower = col.lower().strip()
        
        # Universal field mapping
        if any(keyword in col_lower for keyword in ["email", "e-mail", "mail"]):
            suggestions[col] = {"tier": "universal", "field_name": "email"}
        
        # Standard field mappings
        elif any(keyword in col_lower for keyword in ["first", "fname", "given"]) and "name" in col_lower:
            suggestions[col] = {"tier": "standard", "field_name": "first_name"}
        elif any(keyword in col_lower for keyword in ["last", "lname", "surname", "family"]) and "name" in col_lower:
            suggestions[col] = {"tier": "standard", "field_name": "last_name"}
        elif any(keyword in col_lower for keyword in ["phone", "mobile", "tel"]):
            suggestions[col] = {"tier": "standard", "field_name": "phone"}
        elif any(keyword in col_lower for keyword in ["company", "organization", "org"]):
            suggestions[col] = {"tier": "standard", "field_name": "company"}
        elif "country" in col_lower:
            suggestions[col] = {"tier": "standard", "field_name": "country"}
        elif "city" in col_lower:
            suggestions[col] = {"tier": "standard", "field_name": "city"}
        elif any(keyword in col_lower for keyword in ["title", "position", "job", "role"]):
            suggestions[col] = {"tier": "standard", "field_name": "job_title"}
        
        # Custom field mapping (fallback)
        else:
            # Clean column name for custom field
            clean_name = col.lower().replace(" ", "_").replace("-", "_")
            clean_name = "".join(c for c in clean_name if c.isalnum() or c == "_")
            suggestions[col] = {"tier": "custom", "field_name": clean_name}
    
    return suggestions

def validate_template_placeholders(template_content: str, field_map: Dict[str, str]) -> Dict[str, Any]:
    """
    Validate that all template placeholders have corresponding field mappings
    """
    import re
    
    # Find all placeholders in template
    placeholders = re.findall(r'\{([^}]+)\}', template_content)
    
    validation_result = {
        "valid": True,
        "missing_mappings": [],
        "unused_mappings": [],
        "total_placeholders": len(set(placeholders))
    }
    
    # Check for missing mappings
    for placeholder in set(placeholders):
        if placeholder not in field_map:
            validation_result["missing_mappings"].append(placeholder)
            validation_result["valid"] = False
    
    # Check for unused mappings
    for mapped_field in field_map.keys():
        if mapped_field not in placeholders:
            validation_result["unused_mappings"].append(mapped_field)
    
    return validation_result

def get_field_statistics(subscribers: List[dict], field_mapping: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    """
    Generate statistics for field usage across subscribers
    """
    stats = {}
    total_subscribers = len(subscribers)
    
    for template_field, mapping in field_mapping.items():
        populated_count = 0
        unique_values = set()
        sample_values = []
        
        for subscriber in subscribers:
            value = get_subscriber_field_value(subscriber, mapping, template_field, {})
            
            if value and str(value).strip():
                populated_count += 1
                unique_values.add(str(value).strip())
                
                if len(sample_values) < 5:
                    sample_values.append(str(value).strip())
        
        stats[template_field] = {
            "mapping": mapping,
            "populated_count": populated_count,
            "population_rate": populated_count / total_subscribers if total_subscribers > 0 else 0,
            "unique_values_count": len(unique_values),
            "sample_values": sample_values,
            "recommended": populated_count / total_subscribers >= 0.5 if total_subscribers > 0 else False
        }
    
    return stats

def optimize_field_mappings(
    template_placeholders: List[str], 
    available_fields: Dict[str, Dict[str, float]],
    current_mappings: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """
    Optimize field mappings for maximum data population
    """
    optimized_mappings = current_mappings.copy() if current_mappings else {}
    
    for placeholder in template_placeholders:
        if placeholder in optimized_mappings:
            continue  # Keep existing mapping
        
        best_mapping = None
        best_score = 0
        
        # Check all tiers for best match
        for tier, fields in available_fields.items():
            for field_name, population_rate in fields.items():
                # Calculate matching score
                match_score = calculate_field_match_score(placeholder, field_name)
                final_score = match_score * population_rate
                
                if final_score > best_score:
                    best_score = final_score
                    best_mapping = f"{tier}.{field_name}"
        
        if best_mapping and best_score > 0.3:  # Minimum confidence threshold
            optimized_mappings[placeholder] = best_mapping
        else:
            optimized_mappings[placeholder] = "__DEFAULT__"  # Use fallback
    
    return optimized_mappings

def calculate_field_match_score(template_field: str, target_field: str) -> float:
    """
    Calculate similarity score between template field and target field
    """
    template_lower = template_field.lower().replace("_", " ")
    target_lower = target_field.lower().replace("_", " ")
    
    # Exact match
    if template_lower == target_lower:
        return 1.0
    
    # Contains match
    if template_lower in target_lower or target_lower in template_lower:
        return 0.8
    
    # Keyword matching
    template_words = set(template_lower.split())
    target_words = set(target_lower.split())
    
    if template_words & target_words:  # Any common words
        common_ratio = len(template_words & target_words) / len(template_words | target_words)
        return 0.6 * common_ratio
    
    # Fuzzy matching could be added here using libraries like fuzzywuzzy
    return 0.0
