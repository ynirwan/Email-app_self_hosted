# backend/app/schemas/automation.py
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class AutomationStepBase(BaseModel):
    template_id: str
    delay_hours: int
    conditions: Optional[Dict[str, Any]] = {}

class AutomationStepCreate(AutomationStepBase):
    pass

class AutomationRuleBase(BaseModel):
    name: str
    trigger: str
    trigger_conditions: Dict[str, Any] = {}
    active: bool = False

class AutomationRuleCreate(AutomationRuleBase):
    steps: List[AutomationStepCreate] = []

class AutomationRuleUpdate(BaseModel):
    name: Optional[str] = None
    trigger: Optional[str] = None
    trigger_conditions: Optional[Dict[str, Any]] = None
    active: Optional[bool] = None
    steps: Optional[List[AutomationStepCreate]] = None

class AutomationRuleResponse(AutomationRuleBase):
    id: str
    status: str
    emails_sent: int = 0
    open_rate: float = 0.0
    click_rate: float = 0.0
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True

class AutomationAnalytics(BaseModel):
    total_sent: int
    open_rate: float
    click_rate: float
    active_subscribers: int
    email_performance: List[Dict[str, Any]]

class AutomationTestRequest(BaseModel):
    workflow: AutomationRuleCreate
    test_email: str


