# backend/models/suppression.py
from pydantic import BaseModel, EmailStr, Field, validator
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from bson import ObjectId
from enum import Enum

class SuppressionReason(str, Enum):
    UNSUBSCRIBE = "unsubscribe"
    BOUNCE_HARD = "bounce_hard"
    BOUNCE_SOFT = "bounce_soft"
    COMPLAINT = "complaint"
    MANUAL = "manual"
    IMPORT = "import"
    INVALID_EMAIL = "invalid_email"  # Added for your email validation
    DUPLICATE_COMPLAINT = "duplicate_complaint"  # Added for multiple complaints

class SuppressionScope(str, Enum):
    GLOBAL = "global"
    LIST_SPECIFIC = "list_specific"

class SuppressionSource(str, Enum):
    """Track where the suppression came from"""
    API = "api"
    CAMPAIGN = "campaign" 
    WEBHOOK = "webhook"  # For ESP webhooks (AWS SES, etc.)
    MANUAL = "manual"
    BULK_IMPORT = "bulk_import"
    SYSTEM = "system"

# Pydantic Models
class SuppressionCreate(BaseModel):
    email: EmailStr
    reason: SuppressionReason
    scope: SuppressionScope = SuppressionScope.GLOBAL
    target_lists: Optional[List[str]] = Field(default_factory=list)
    notes: Optional[str] = Field(default="", max_length=500)
    source: SuppressionSource = SuppressionSource.MANUAL
    campaign_id: Optional[str] = None  # Link to your campaigns collection
    subscriber_id: Optional[str] = None  # Link to your subscribers collection
    
    @validator('target_lists')
    def validate_target_lists(cls, v, values):
        if values.get('scope') == SuppressionScope.LIST_SPECIFIC and not v:
            raise ValueError('target_lists required for list_specific scope')
        if values.get('scope') == SuppressionScope.GLOBAL:
            return []
        return v

    @validator('campaign_id')
    def validate_campaign_id(cls, v):
        if v and not ObjectId.is_valid(v):
            raise ValueError('Invalid campaign_id format')
        return v

    @validator('subscriber_id') 
    def validate_subscriber_id(cls, v):
        if v and not ObjectId.is_valid(v):
            raise ValueError('Invalid subscriber_id format')
        return v

class SuppressionUpdate(BaseModel):
    reason: Optional[SuppressionReason] = None
    scope: Optional[SuppressionScope] = None
    target_lists: Optional[List[str]] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    source: Optional[SuppressionSource] = None

class SuppressionOut(BaseModel):
    id: str = Field(alias="_id")
    email: str
    reason: str
    scope: str
    target_lists: List[str]
    notes: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: str
    source: str
    campaign_id: Optional[str] = None
    subscriber_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}

class BulkSuppressionImport(BaseModel):
    suppressions: List[Dict[str, Any]]
    default_reason: SuppressionReason = SuppressionReason.IMPORT
    default_scope: SuppressionScope = SuppressionScope.GLOBAL
    override_existing: bool = False
    source: SuppressionSource = SuppressionSource.BULK_IMPORT

class SuppressionCheck(BaseModel):
    """For checking if emails should be suppressed before sending"""
    email: str
    target_lists: List[str] = Field(default_factory=list)

class SuppressionCheckResult(BaseModel):
    email: str
    is_suppressed: bool
    reason: Optional[str] = None
    scope: Optional[str] = None
    suppression_id: Optional[str] = None
    notes: Optional[str] = None

class BulkSuppressionCheck(BaseModel):
    """For checking multiple emails at once (optimized for your batch sending)"""
    emails: List[str]
    target_lists: List[str] = Field(default_factory=list)

class BulkSuppressionCheckResult(BaseModel):
    total_checked: int
    suppressed_count: int
    results: Dict[str, SuppressionCheckResult]  # email -> result mapping

# Integration Models for Your Existing Workflow
class CampaignSuppressionFilter(BaseModel):
    """Filter suppressions for your campaign sending"""
    campaign_id: str
    target_lists: List[str]
    batch_size: int = 500  # Match your existing batch size
    
    @validator('campaign_id')
    def validate_campaign_id(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError('Invalid campaign_id format')
        return v

class SubscriberSuppressionSync(BaseModel):
    """Sync suppression status with your subscriber status"""
    email: str
    list_name: str
    action: str = Field(pattern=r"^(suppress|unsuppress)$")
    reason: SuppressionReason
    update_subscriber_status: bool = True  # Whether to update subscriber.status

# MongoDB Schema Setup - Optimized for your 25k emails/day volume
SUPPRESSION_INDEXES = [
    # Primary lookup index for email checking (most important for performance)
    {"keys": [("email", 1), ("is_active", 1)], "name": "email_active_lookup"},
    
    # List-specific suppression checks (for your list-based campaigns)
    {"keys": [("email", 1), ("target_lists", 1), ("is_active", 1)], "name": "email_lists_active"},
    
    # Campaign integration index
    {"keys": [("campaign_id", 1), ("created_at", -1)], "name": "campaign_suppressions"},
    
    # Reason-based queries for reporting
    {"keys": [("reason", 1), ("created_at", -1)], "name": "reason_timeline"},
    
    # Source tracking for analytics
    {"keys": [("source", 1), ("created_at", -1)], "name": "source_analytics"},
    
    # Admin interface queries
    {"keys": [("created_at", -1)], "name": "recent_suppressions"},
    
    # Subscriber integration index
    {"keys": [("subscriber_id", 1)], "name": "subscriber_link", "sparse": True},
    
    # Compound index for efficient bulk checking
    {"keys": [("is_active", 1), ("scope", 1), ("email", 1)], "name": "bulk_check_optimized"}
]

# Enhanced MongoDB Document Structure for Your Integration
"""
{
    "_id": ObjectId("..."),
    "email": "user@example.com",
    "reason": "unsubscribe",
    "scope": "global",
    "target_lists": [],  # Empty for global, specific lists for list_specific
    "notes": "User requested unsubscribe via email",
    "is_active": true,
    "created_at": ISODate("2025-09-09T10:00:00.000Z"),
    "updated_at": ISODate("2025-09-09T10:00:00.000Z"),
    "created_by": "system",
    "source": "webhook",
    
    # Integration with your existing collections
    "campaign_id": ObjectId("68bf01c9da7851ae09f098e3"),  # Links to campaigns
    "subscriber_id": ObjectId("68bf00c2897cd784db431071"),  # Links to subscribers
    
    # Enhanced metadata for your email system
    "metadata": {
        "bounce_type": "hard",  # For bounce reasons
        "user_agent": "Mozilla/5.0...",  # For unsubscribe tracking  
        "ip_address": "192.168.1.1",
        "esp_message_id": "0000014a-f4d4-4f89-93f5-28f39085e1f0",  # AWS SES message ID
        "list_name": "list2",  # For easier reporting
        "original_campaign_title": "cam",  # Campaign context
        
        # Integration with your audit system
        "audit_trail": {
            "action": "suppress_email",
            "entity_type": "suppression",
            "user_action": "Email suppressed due to hard bounce"
        },
        
        # For your background job tracking
        "processing_job_id": "uuid-of-background-job",
        
        # ESP integration data
        "esp_data": {
            "bounce_reason": "550 5.1.1 The email account that you tried to reach does not exist",
            "esp_timestamp": ISODate("2025-09-09T10:00:00.000Z"),
            "esp_event_type": "bounce"
        }
    }
}
"""

