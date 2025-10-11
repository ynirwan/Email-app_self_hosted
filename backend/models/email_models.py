# models/email_models.py
from pydantic import BaseModel, EmailStr, validator
from typing import Optional, List
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


class SendingLimits(BaseModel):
    per_minute: int = 100
    per_hour: int = 3600
    per_day: int = 50000


class SMTPSettings(BaseModel):
    provider: str
    smtp_server: str
    smtp_port: int = 587
    username: str
    password: str
    # Optional limits (not enforced on self-hosted)
    daily_limit: Optional[int] = None
    # Bounce handling
    bounce_handling: BounceHandling


class HostedEmailSettings(BaseModel):
    smtp_choice: str  # "managed" or "client"
    # Client SMTP fields (only when smtp_choice = "client")
    provider: Optional[str] = None
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = 587
    username: Optional[str] = None
    password: Optional[str] = None
    # User-configurable limits (within quota)
    daily_limit: Optional[int] = 1000
    # Bounce handling (limited options)
    bounce_forward_email: Optional[str] = None

    @validator('provider', 'smtp_server', 'username', 'password')
    def validate_client_smtp(cls, v, values):
        if values.get('smtp_choice') == 'client' and not v:
            raise ValueError('Required for client SMTP configuration')
        return v


class EmailUsageRecord(BaseModel):
    user_id: str
    month: str  # "2025-08"
    emails_sent: int = 0
    emails_remaining: int = 50000
    overage_emails: int = 0
    smtp_choice: Optional[str] = "managed"
    last_updated: datetime


class SMTPTestSettings(BaseModel):
    smtp_server: str
    smtp_port: int
    username: str
    password: str

