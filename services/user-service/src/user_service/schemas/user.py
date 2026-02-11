from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Optional


class UserResponse(BaseModel):
    """User response schema for API responses."""
    id: int
    email: EmailStr
    first_name: str
    last_name: str
    role: str
    is_active: bool
    is_verified: bool
    phone_number: Optional[str] = None        # <-- NEW
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        ser_json_timedelta="iso8601",
    )


class UserUpdate(BaseModel):
    """User update schema."""
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone_number: Optional[str] = Field(None, min_length=10, max_length=20)  # <-- NEW


class InstructorProfileResponse(BaseModel):
    """Instructor profile response schema."""
    id: int
    user_id: int
    bio: Optional[str]
    expertise: Optional[str]
    profile_picture_url: Optional[str]
    phone_number: Optional[str]
    total_students: int
    total_courses: int
    average_rating: float
    is_verified_instructor: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        ser_json_timedelta="iso8601",
    )


class InstructorProfileUpdate(BaseModel):
    """Instructor profile update schema."""
    bio: Optional[str] = None
    expertise: Optional[str] = None
    profile_picture_url: Optional[str] = None
    phone_number: Optional[str] = Field(None, min_length=10, max_length=20)
