# backend/app/models/domain.py
from pydantic import BaseModel, validator
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum

class DomainStatus(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified" 
    FAILED = "failed"

class VerificationRecords(BaseModel):
    domain: str
    verification_token: str
    spf_record: str
    dkim_selector: str
    dkim_record: str
    dmarc_record: str

class DomainCreate(BaseModel):
    domain: str
    
    @validator('domain')
    def validate_domain(cls, v):
        import re
        v = v.lower().strip()
        # Basic domain validation
        domain_regex = r'^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'
        if not re.match(domain_regex, v):
            raise ValueError('Invalid domain format')
        if len(v) > 253:
            raise ValueError('Domain name too long')
        return v

class Domain(BaseModel):
    domain: str
    status: DomainStatus = DomainStatus.PENDING
    verification_records: VerificationRecords
    verification_results: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    verified_at: Optional[datetime] = None

class DomainResponse(BaseModel):
    id: str
    domain: str
    status: DomainStatus
    verification_records: VerificationRecords
    verification_results: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    verified_at: Optional[datetime] = None
    
    class Config:
        # Allow ObjectId to be serialized as string
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class DomainUpdate(BaseModel):
    status: Optional[DomainStatus] = None
    verification_results: Optional[Dict[str, Any]] = None
