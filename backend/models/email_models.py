from pydantic import BaseModel, EmailStr, validator
from typing import Optional
from datetime import datetime
from enum import Enum

class BounceHandling(BaseModel):
    enabled: bool = True
    webhook_url: Optional[str] = None
    forward_bounces: bool = False
    forward_email: Optional[EmailStr] = None

    @validator("webhook_url", "forward_email", pre=True)
    def empty_str_to_none(cls, v):
        if v == "":
            return None
        return v

class HostedEmailSettings(BaseModel):
    smtp_choice: str  # "managed" or "client"
    # Client SMTP fields (required only when smtp_choice = "client")
    provider: Optional[str] = None
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = 587
    username: Optional[str] = None
    password: Optional[str] = None
    # Daily sending limit based on subscription plan
    daily_limit: Optional[int] = 1000
    # Bounce handling limited options for hosted plans
    bounce_forward_email: Optional[EmailStr] = None

    @validator('provider', 'smtp_server', 'username', 'password')
    def validate_client_smtp(cls, v, values):
        if values.get('smtp_choice') == 'client' and not v:
            raise ValueError('Required for client SMTP configuration')
        return v

class EmailUsageRecord(BaseModel):
    # Single-user system, usage tracked per day (not monthly)
    date: str  # "2025-09-02"
    emails_sent: int = 0
    daily_limit: int
    overage_emails: int = 0
    smtp_choice: Optional[str] = "managed"
    last_updated: datetime

class SMTPTestSettings(BaseModel):
    smtp_server: str
    smtp_port: int
    username: str
    password: str

