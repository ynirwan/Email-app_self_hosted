from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime


class TemplateCreate(BaseModel):
    name: str
    description: Optional[str]
    content_json: Dict[str, Any]
    fields: List[str]


class TemplateOut(TemplateCreate):
    id: str = Field(alias="_id")  # Map 'id' to '_id' from MongoDB

    class Config:
        allow_population_by_field_name = True  # Allow using both 'id' and '_id'


class Campaign(BaseModel):
    name: str
    subject: str
    content: str
    scheduled_time: Optional[datetime] = None
    status: str = "draft"
    created_at: Optional[datetime] = None


class CampaignInDB(Campaign):
    id: Optional[str] = Field(alias="_id")

    class Config:
        allow_population_by_field_name = True

