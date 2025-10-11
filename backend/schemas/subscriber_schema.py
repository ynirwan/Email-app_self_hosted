# backend/schemas/subscriber_schema.py

# schemas/subscriber_schema.py
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

class SubscriberStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BOUNCED = "bounced"
    UNSUBSCRIBED = "unsubscribed"

class StandardFields(BaseModel):
    """Standard subscriber fields with validation"""
    first_name: Optional[str] = Field(None, max_length=50)
    last_name: Optional[str] = Field(None, max_length=50)


# Models
class ChunkMetadata(BaseModel):
    job_id: str
    list_name: str
    total_subscribers: int
    chunk_size: int
    total_chunks: int
    field_mapping: Dict[str, Any]
    created_at: datetime
    original_filename: Optional[str] = None

class BackgroundUploadPayload(BaseModel):
    list_name: str
    subscribers: List[Dict]
    processing_mode: str = "background"
    field_mapping: Dict[str, Any]
    original_filename: Optional[str] = None



# 3. Define other models
class SubscriberIn(BaseModel):
    """Input model for creating subscribers"""
    email: EmailStr = Field(..., description="Primary email address")
    list: str = Field(..., description="Target list name")  # Changed from list_name
    standard_fields: Dict[str, Any] = Field(default_factory=dict)
    custom_fields: Dict[str, Any] = Field(default_factory=dict)
    status: SubscriberStatus = Field(default=SubscriberStatus.ACTIVE)
    
    @field_validator('email')
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip()
    
    @field_validator('list')
    @classmethod
    def validate_list_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("List name cannot be empty")
        return v.strip()


class SubscriberOut(BaseModel):
    """Output model for subscriber data"""
    id: Optional[str] = Field(None, alias="_id")
    email: EmailStr
    list: str  # No more alias confusion
    status: SubscriberStatus
    created_at: datetime
    updated_at: datetime
    standard_fields: Dict[str, Any] = Field(default_factory=dict)
    custom_fields: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        populate_by_name = True



# 1. Define BulkSubscriberIn FIRST
class BulkSubscriberIn(BaseModel):
    """Individual subscriber for bulk operations"""
    email: EmailStr
    standard_fields: Dict[str, Any] = Field(default_factory=dict)
    custom_fields: Dict[str, Any] = Field(default_factory=dict)
    status: SubscriberStatus = Field(default=SubscriberStatus.ACTIVE)
    
    @field_validator('email')
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower().strip()

# 2. Then define BulkPayload that uses BulkSubscriberIn
class BulkPayload(BaseModel):
    """Model for bulk subscriber operations"""
    list: str = Field(..., description="Target list name")  # Changed from list_name
    subscribers: List[BulkSubscriberIn] = Field(..., description="List of subscribers")
    
    @field_validator('list')
    @classmethod
    def validate_list_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("List name cannot be empty")
        return v.strip()



class FieldMappingInfo(BaseModel):
    """Field mapping configuration"""
    tier: str = Field(..., description="Field tier (universal, standard, custom)")
    field_name: str = Field(..., description="Target field name")




class BulkUploadRequest(BaseModel):  
    """Enhanced bulk upload request"""
    list_name: str
    field_mapping: Dict[str, FieldMappingInfo]
    overwrite_existing: bool = False

