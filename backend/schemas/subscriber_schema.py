# backend/schemas/subscriber_schema.py
"""
Contract-based subscriber schema.
Every custom field has a declared type. Upload converts at ingest.
Renderer receives native Python types — no guessing at render time.
"""

from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum


class SubscriberStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BOUNCED = "bounced"
    UNSUBSCRIBED = "unsubscribed"


class FieldType(str, Enum):
    """Declared type applied at upload time, travels in snapshot to renderer."""

    STRING = "string"  # never auto-cast (safe for zip codes, IDs)
    NUMBER = "number"  # int or float
    BOOLEAN = "boolean"  # true/false/yes/no/1/0 -> bool
    DATE = "date"  # any parseable date -> "YYYY-MM-DD"


STANDARD_FIELD_NAMES = {
    "first_name",
    "last_name",
    "phone",
    "company",
    "country",
    "city",
    "state",
    "zip_code",
    "language",
    "timezone",
    "gender",
    "date_of_birth",
    "website",
    "job_title",
}


class CustomFieldDef(BaseModel):
    type: FieldType = FieldType.STRING


class ListFieldRegistry(BaseModel):
    """Stored in lists collection. All uploads to this list conform to this."""

    list_name: str
    standard: List[str] = Field(default_factory=list)
    custom: Dict[str, CustomFieldDef] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class UploadSubscriber(BaseModel):
    """One row from CSV after frontend parsing. Backend applies type conversion."""

    email: EmailStr
    status: SubscriberStatus = SubscriberStatus.ACTIVE
    fields: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("email")
    @classmethod
    def normalize(cls, v):
        return v.lower().strip()


class BackgroundUploadPayload(BaseModel):
    list_name: str
    field_registry: ListFieldRegistry
    subscribers: List[UploadSubscriber]
    processing_mode: str = "background"

    @field_validator("list_name")
    @classmethod
    def clean_name(cls, v):
        v = v.strip().replace("/", "_").replace("\\", "_")
        if not v:
            raise ValueError("list_name cannot be empty")
        if len(v) > 100:
            raise ValueError("list_name max 100 chars")
        return v

    @field_validator("subscribers")
    @classmethod
    def check_not_empty(cls, v):
        if not v:
            raise ValueError("subscribers cannot be empty")
        if len(v) > 1_000_000:
            raise ValueError("max 1M subscribers per request")
        return v


class SubscriberIn(BaseModel):
    email: EmailStr
    list: str
    standard_fields: Dict[str, Any] = Field(default_factory=dict)
    custom_fields: Dict[str, Any] = Field(default_factory=dict)
    status: SubscriberStatus = SubscriberStatus.ACTIVE

    @field_validator("email")
    @classmethod
    def normalize(cls, v):
        return v.lower().strip()

    @field_validator("list")
    @classmethod
    def validate_list(cls, v):
        if not v or not v.strip():
            raise ValueError("list cannot be empty")
        return v.strip()


class SubscriberOut(BaseModel):
    id: Optional[str] = Field(None, alias="_id")
    email: EmailStr
    list: str
    status: SubscriberStatus
    created_at: datetime
    updated_at: datetime
    standard_fields: Dict[str, Any] = Field(default_factory=dict)
    custom_fields: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        populate_by_name = True


class BulkSubscriberIn(BaseModel):
    email: EmailStr
    standard_fields: Dict[str, Any] = Field(default_factory=dict)
    custom_fields: Dict[str, Any] = Field(default_factory=dict)
    status: SubscriberStatus = SubscriberStatus.ACTIVE

    @field_validator("email")
    @classmethod
    def normalize(cls, v):
        return v.lower().strip()


class BulkPayload(BaseModel):
    list: str
    subscribers: List[BulkSubscriberIn]

    @field_validator("list")
    @classmethod
    def validate_list(cls, v):
        if not v or not v.strip():
            raise ValueError("list cannot be empty")
        return v.strip()


class FieldMappingEntry(BaseModel):
    """One campaign field_map entry — source + declared type from registry."""

    source: str
    type: FieldType = FieldType.STRING


class ChunkMetadata(BaseModel):
    job_id: str
    list_name: str
    total_subscribers: int
    chunk_size: int
    total_chunks: int
    created_at: datetime
    original_filename: Optional[str] = None


class BulkUploadRequest(BaseModel):
    list_name: str
    overwrite_existing: bool = False
