# config/field_tiers.py
FIELD_TIERS = {
"universal": {
"email": {"required": True, "type": "email", "validation": "email_format"},
"created_at": {"required": True, "type": "datetime", "auto_generated": True},
Changes Needed for Subscription Upload with
Three-Tier Field Classification
1. Database Schema Changes
A) Standardized Subscriber Document Structure
B) Field Classification Configuration
"updated_at": {"required": True, "type": "datetime", "auto_generated": True},
"status": {"required": True, "type": "enum", "default": "active",
"values": ["active", "inactive", "bounced", "unsubscribed"]}
},
"standard": {
"first_name": {"type": "string", "max_length": 50},
"last_name": {"type": "string", "max_length": 50},
"phone": {"type": "string", "validation": "phone_format"},
"company": {"type": "string", "max_length": 100},
"country": {"type": "string", "max_length": 50},
"city": {"type": "string", "max_length": 50},
"job_title": {"type": "string", "max_length": 100},
"date_of_birth": {"type": "date"},
"gender": {"type": "enum", "values": ["male", "female", "other", "prefer_not_to_s
"language": {"type": "string", "max_length": 10}
}
}

