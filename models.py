from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field, field_validator
import re
import base64

# Base models
class TimestampMixin(BaseModel):
    """Mixin for models with timestamps"""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# User models
class UserBase(BaseModel):
    """Base user model"""
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=255)
    age: int = Field(..., ge=13, le=120)

def validate_base64_image(v: Optional[str]) -> Optional[str]:
    """Validate base64 encoded image"""
    if v is None:
        return v
    # Check if it's a data URL
    if v.startswith("data:image/"):
        try:
            header, data = v.split(",", 1)
            base64.b64decode(data)
            return v
        except Exception:
            raise ValueError("Invalid base64 image data")
    else:
        # Assume raw base64
        try:
            base64.b64decode(v)
            return v
        except Exception:
            raise ValueError("Invalid base64 image data")

class UserCreate(UserBase):
    """User creation model"""
    password: str = Field(..., min_length=6)
    avatar: Optional[str] = None  # Base64 encoded image

    @field_validator("avatar")
    @classmethod
    def validate_base64_image(cls, v: Optional[str]) -> Optional[str]:
        return validate_base64_image(v)

class UserLogin(BaseModel):
    """User login model"""
    password: str
    email: EmailStr

class UserUpdate(BaseModel):
    """User update model"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    age: Optional[int] = Field(None, ge=13, le=120)
    avatar: Optional[str] = None  # Base64 encoded image

    @field_validator("avatar")
    @classmethod
    def validate_base64_avatar(cls, v: Optional[str]) -> Optional[str]:
        """Validate base64 encoded image for avatar"""
        return validate_base64_image(v)

class UserInDB(UserBase, TimestampMixin):
    """User model as stored in database"""
    id: str
    avatar_url: Optional[str] = None
    password_hash: Optional[str] = None
    email_verified: Optional[bool] = False

class UserResponse(BaseModel):
    """User response model"""
    user: Dict[str, Any]
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    email_sent: Optional[bool] = None
    email_message: Optional[str] = None

# Supplement models
class DoseInfo(BaseModel):
    """Dose information model"""
    quantity: str
    unit: str

class TimesOfDay(BaseModel):
    """Times of day model"""
    Morning: List[str] = []
    Afternoon: List[str] = []
    Evening: List[str] = []

class SupplementBase(BaseModel):
    """Base supplement model"""
    name: str = Field(..., min_length=1, max_length=255)
    brand: str = Field(..., min_length=1, max_length=255)
    dosage_form: Optional[str] = Field(None, min_length=1, max_length=100)
    dose_quantity: str = Field(..., min_length=1, max_length=50)
    dose_unit: str = Field(..., min_length=1, max_length=50)
    frequency: str = Field(..., min_length=1, max_length=100)
    times_of_day: Dict[str, Any] = Field(default_factory=dict)
    interactions: List[str] = Field(default_factory=list)
    remind_me: bool = True
    expiration_date: date
    quantity: str = Field(..., min_length=1, max_length=100)
    image_url: Optional[str] = None

class SupplementCreate(SupplementBase):
    """Supplement creation model"""
    pass

class SupplementUpdate(BaseModel):
    """Supplement update model"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    brand: Optional[str] = Field(None, min_length=1, max_length=255)
    dosage_form: Optional[str] = Field(None, min_length=1, max_length=100)
    dose_quantity: Optional[str] = Field(None, min_length=1, max_length=50)
    dose_unit: Optional[str] = Field(None, min_length=1, max_length=50)
    frequency: Optional[str] = Field(None, min_length=1, max_length=100)
    times_of_day: Optional[Dict[str, Any]] = None
    interactions: Optional[List[str]] = None
    remind_me: Optional[bool] = None
    expiration_date: Optional[date] = None
    quantity: Optional[str] = Field(None, min_length=1, max_length=100)
    image_url: Optional[str] = None

class SupplementInDB(SupplementBase, TimestampMixin):
    """Supplement model as stored in database"""
    id: int
    user_id: str

class SupplementResponse(BaseModel):
    """Supplement response model"""
    id: int
    user_id: str
    name: str
    brand: str
    dosage_form: Optional[str] = None
    dose_quantity: str
    dose_unit: str
    frequency: str
    times_of_day: Dict[str, Any]
    interactions: List[str]
    remind_me: bool
    expiration_date: date
    quantity: str
    image_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# Chat models
class ChatMessage(BaseModel):
    """Chat message model"""
    message: str = Field(..., min_length=1, max_length=2000)

class ChatMessageInDB(BaseModel):
    """Chat message as stored in database"""
    id: str
    user_id: str
    sender: str  # 'user' or 'assistant'
    message: str
    timestamp: datetime
    context: Optional[Dict[str, Any]] = None

class ChatResponse(BaseModel):
    """Chat response model"""
    reply: str

class ChatHistoryResponse(BaseModel):
    """Chat history response model"""
    messages: List[Dict[str, Any]]

# Supplement log models
class SupplementLogBase(BaseModel):
    """Base supplement log model"""
    supplement_id: int
    scheduled_time: str  # Time in HH:MM format
    status: str = Field(default="pending", pattern="^(pending|taken|missed|skipped)$")
    notes: Optional[str] = None

    @field_validator("scheduled_time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Validate time format (HH:MM)"""
        if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", v):
            raise ValueError("Time must be in HH:MM format")
        return v

class SupplementLogCreate(SupplementLogBase):
    """Supplement log creation model"""
    pass

class SupplementLogUpdate(BaseModel):
    """Supplement log update model"""
    status: Optional[str] = Field(None, pattern="^(pending|taken|missed|skipped)$")
    taken_at: Optional[datetime] = None
    notes: Optional[str] = None

class SupplementLogInDB(SupplementLogBase, TimestampMixin):
    """Supplement log as stored in database"""
    id: str
    user_id: str
    taken_at: Optional[datetime] = None

class SupplementLogResponse(BaseModel):
    """Supplement log response model"""
    id: str
    user_id: str
    supplement_id: int
    scheduled_time: str
    taken_at: Optional[datetime] = None
    status: str
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class MarkCompletedRequest(BaseModel):
    """Request model for marking supplement as completed"""
    supplement_id: int
    scheduled_time: str
    status: str = Field(pattern="^(taken|missed|skipped)$")
    notes: Optional[str] = None

    @field_validator("scheduled_time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Validate time format (HH:MM)"""
        if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", v):
            raise ValueError("Time must be in HH:MM format")
        return v

# Health check model
class HealthResponse(BaseModel):
    """Health check response model"""
    status: str
    timestamp: datetime
    gemini_configured: bool
    supabase_configured: bool
    email_configured: Optional[bool] = None

# Error models
class ErrorResponse(BaseModel):
    """Error response model"""
    error: str
    detail: Optional[str] = None

# Token models
class Token(BaseModel):
    """Token model"""
    access_token: str
    token_type: str

class TokenData(BaseModel):
    """Token data model"""
    user_id: Optional[str] = None

# File upload models
class ImageUploadResponse(BaseModel):
    """Image upload response model"""
    image_url: str

# Email delivery models
class EmailStatusResponse(BaseModel):
    """Email delivery status response"""
    success: bool
    message: str
    error_code: Optional[str] = None
    timestamp: datetime

# Configuration for all models
class ConfigModel(BaseModel):
    """Base configuration for all models"""
    model_config = {
        "populate_by_name": True,
        "use_enum_values": True,
        "validate_assignment": True,
        "extra": "forbid",
    }