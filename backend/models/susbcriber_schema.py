# models/schemas.py
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, EmailStr, validator, Field
from datetime import datetime
from bson import ObjectId
from .field_tiers import FIELD_TIERS, FieldType, SubscriberStatus

class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid objectid")
        return ObjectId(v)

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")

# Subscriber Models
class SubscriberDocument(BaseModel):
    """Complete subscriber document structure"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    list: str = Field(..., description="List identifier")
    email: EmailStr = Field(..., description="Primary email address")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    status: SubscriberStatus = Field(default=SubscriberStatus.ACTIVE)
    standard_fields: Dict[str, Any] = Field(default_factory=dict)
    custom_fields: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

    @validator('standard_fields')
    def validate_standard_fields(cls, v):
        """Validate standard fields against configuration"""
        if not v:
            return {}
        
        validated = {}
        for field_name, value in v.items():
            field_config = FIELD_TIERS["standard"].get(field_name)
            if field_config and value is not None:
                try:
                    validated[field_name] = validate_field_value(field_name, value, field_config)
                except ValueError as e:
                    # Log warning but don't fail validation
                    print(f"Warning: Invalid value for {field_name}: {e}")
        return validated

class SubscriberUploadModel(BaseModel):
    """Model for subscriber upload requests"""
    email: EmailStr
    list_name: str
    standard_fields: Dict[str, Any] = Field(default_factory=dict)
    custom_fields: Dict[str, Any] = Field(default_factory=dict)
    status: SubscriberStatus = Field(default=SubscriberStatus.ACTIVE)

    @validator('email')
    def normalize_email(cls, v):
        return v.lower().strip()

    @validator('standard_fields', pre=True)
    def validate_standard_fields(cls, v):
        if not v:
            return {}
        
        validated = {}
        for field_name, value in v.items():
            if field_name in FIELD_TIERS["standard"] and value is not None:
                field_config = FIELD_TIERS["standard"][field_name]
                try:
                    validated[field_name] = validate_field_value(field_name, value, field_config)
                except ValueError:
                    # Skip invalid fields
                    continue
        return validated

class FieldMappingInfo(BaseModel):
    """Field mapping configuration"""
    tier: str = Field(..., description="Field tier (universal, standard, custom)")
    field_name: str = Field(..., description="Target field name")

class BulkUploadRequest(BaseModel):
    """Request model for bulk subscriber upload"""
    list_name: str
    field_mapping: Dict[str, FieldMappingInfo]
    overwrite_existing: bool = False

# Campaign Models
class CampaignModel(BaseModel):
    """Enhanced campaign model with three-tier field support"""
    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    title: str
    subject: str
    sender_name: str = ""
    sender_email: EmailStr = ""
    reply_to: EmailStr = ""
    target_lists: List[str]
    template_id: str
    field_map: Dict[str, str] = Field(default_factory=dict)
    status: str = "draft"
    
    # Three-tier system fields
    field_mapping_strategy: Dict[str, Any] = Field(default_factory=dict)
    fallback_values: Dict[str, str] = Field(default_factory=dict)
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    sent_at: Optional[datetime] = None
    target_list_count: int = 0
    sent_count: int = 0
    failed_count: int = 0

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class CampaignCreateRequest(BaseModel):
    """Request model for creating campaigns"""
    title: str
    subject: str
    sender_name: Optional[str] = ""
    sender_email: Optional[EmailStr] = ""
    reply_to: Optional[EmailStr] = ""
    target_lists: List[str]
    template_id: str
    field_map: Dict[str, str]
    fallback_values: Optional[Dict[str, str]] = Field(default_factory=dict)

class TestEmailRequest(BaseModel):
    """Request model for test emails"""
    campaign_id: str
    test_email: EmailStr
    selected_list_id: Optional[str] = None
    subscriber_id: Optional[str] = None

# Analytics Models
class FieldAnalytics(BaseModel):
    """Field usage analytics"""
    count: int
    population_rate: float
    sample_values: List[str] = Field(default_factory=list)
    recommended: bool = False

class ListFieldAnalysis(BaseModel):
    """Complete field analysis for a list"""
    total_subscribers: int
    tiers: Dict[str, Dict[str, FieldAnalytics]]

class CampaignFieldStats(BaseModel):
    """Campaign field mapping statistics"""
    mapping: str
    populated_count: int
    empty_count: int
    population_rate: float
    sample_values: List[str]

class CampaignAnalytics(BaseModel):
    """Complete campaign analytics"""
    campaign_info: Dict[str, Any]
    performance: Dict[str, Any]
    field_mapping_analysis: Dict[str, CampaignFieldStats]

# Utility Functions
def validate_field_value(field_name: str, value: Any, field_config: Dict[str, Any]) -> Any:
    """Validate and convert field value based on configuration"""
    if value is None or (isinstance(value, str) and value.strip() == ''):
        return None

    field_type = field_config.get("type", FieldType.STRING)
    
    try:
        if field_type == FieldType.STRING:
            result = str(value).strip()
            max_length = field_config.get("max_length")
            if max_length and len(result) > max_length:
                result = result[:max_length]
            return result
            
        elif field_type == FieldType.EMAIL:
            from email_validator import validate_email, EmailNotValidError
            try:
                valid = validate_email(str(value))
                return valid.email
            except EmailNotValidError:
                raise ValueError(f"Invalid email format: {value}")
                
        elif field_type == FieldType.PHONE:
            # Basic phone validation - can be enhanced with phonenumbers library
            phone_str = str(value).strip()
            # Remove common formatting
            cleaned = ''.join(c for c in phone_str if c.isdigit() or c in '+- ()')
            if len(cleaned) < 7:
                raise ValueError(f"Phone number too short: {value}")
            return cleaned
            
        elif field_type == FieldType.DATE:
            from dateutil import parser
            if isinstance(value, datetime):
                return value.date()
            return parser.parse(str(value)).date()
            
        elif field_type == FieldType.DATETIME:
            from dateutil import parser
            if isinstance(value, datetime):
                return value
            return parser.parse(str(value))
            
        elif field_type == FieldType.ENUM:
            allowed_values = field_config.get("values", [])
            str_value = str(value).lower()
            if str_value in [v.lower() for v in allowed_values]:
                return str_value
            raise ValueError(f"Value '{value}' not in allowed values: {allowed_values}")
            
        elif field_type == FieldType.INTEGER:
            return int(float(value))
            
        elif field_type == FieldType.FLOAT:
            return float(value)
            
        elif field_type == FieldType.BOOLEAN:
            if isinstance(value, bool):
                return value
            str_value = str(value).lower()
            if str_value in ['true', '1', 'yes', 'on']:
                return True
            elif str_value in ['false', '0', 'no', 'off']:
                return False
            raise ValueError(f"Cannot convert '{value}' to boolean")
            
        else:
            return str(value)
            
    except Exception as e:
        raise ValueError(f"Failed to validate field {field_name} with value {value}: {str(e)}")
