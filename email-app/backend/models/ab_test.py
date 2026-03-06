# models/ab_test.py
from pydantic import BaseModel
from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum

class TestType(str, Enum):
    SUBJECT_LINE = "subject_line"
    CONTENT = "content"
    SENDER_NAME = "sender_name"
    SEND_TIME = "send_time"
    CTA_BUTTON = "cta_button"

class TestStatus(str, Enum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    PAUSED = "paused"

class ABTestSchema(BaseModel):
    id: Optional[str]
    campaign_id: str
    test_name: str
    test_type: TestType
    variants: List[Dict]  # Variant A and B configurations
    split_percentage: int = 50  # 50/50 split by default
    sample_size: int  # Number of subscribers to test
    winner_criteria: str = "open_rate"  # open_rate, click_rate, conversion_rate
    status: TestStatus = TestStatus.DRAFT
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    results: Optional[Dict]
    created_at: datetime
    updated_at: datetime

class ABTestResult(BaseModel):
    test_id: str
    variant: str  # "A" or "B"
    subscriber_id: str
    email_sent: bool = False
    email_opened: bool = False
    email_clicked: bool = False
    conversion: bool = False
    sent_at: Optional[datetime]
    opened_at: Optional[datetime]
    clicked_at: Optional[datetime]

