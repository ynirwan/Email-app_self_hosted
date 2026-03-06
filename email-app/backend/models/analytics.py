# In backend/models/analytics.py or add to existing models
from pydantic import BaseModel, Field
from typing import Optional, Dict, List
from datetime import datetime

class CampaignAnalytics(BaseModel):
    campaign_id: str = Field(..., description="Campaign ID reference")
    total_sent: int = Field(default=0)
    total_delivered: int = Field(default=0)
    total_bounced: int = Field(default=0)
    total_opened: int = Field(default=0)
    total_clicked: int = Field(default=0)
    total_unsubscribed: int = Field(default=0)
    total_spam_reports: int = Field(default=0)
    
    # Calculated metrics
    delivery_rate: float = Field(default=0.0)  # delivered/sent
    open_rate: float = Field(default=0.0)      # opened/delivered
    click_rate: float = Field(default=0.0)     # clicked/delivered
    bounce_rate: float = Field(default=0.0)    # bounced/sent
    unsubscribe_rate: float = Field(default=0.0)
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class EmailEvent(BaseModel):
    campaign_id: str
    subscriber_email: str
    event_type: str  # 'sent', 'delivered', 'opened', 'clicked', 'bounced', 'unsubscribed', 'spam'
    event_data: Optional[Dict] = Field(default={})  # Additional data like click URL, bounce reason
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

