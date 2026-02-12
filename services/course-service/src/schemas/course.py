from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CourseCreate(BaseModel):
    """Schema for creating a new course."""
    title: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: Optional[str] = None
    long_description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=100)
    level: Optional[str] = Field(None, pattern=r"^(beginner|intermediate|advanced)$")
    language: str = Field(default="en", max_length=50)
    duration_hours: Optional[Decimal] = None
    price: Decimal = Field(default=Decimal("0.00"), ge=0)
    currency: str = Field(default="USD", max_length=3)
    thumbnail_url: Optional[str] = Field(None, max_length=500)
    max_students: Optional[int] = Field(None, gt=0)
    prerequisites: Optional[str] = None
    learning_objectives: Optional[str] = None


class CourseUpdate(BaseModel):
    """Schema for updating a course."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    long_description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=100)
    level: Optional[str] = Field(None, pattern=r"^(beginner|intermediate|advanced)$")
    language: Optional[str] = Field(None, max_length=50)
    duration_hours: Optional[Decimal] = None
    price: Optional[Decimal] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=3)
    thumbnail_url: Optional[str] = Field(None, max_length=500)
    max_students: Optional[int] = Field(None, gt=0)
    prerequisites: Optional[str] = None
    learning_objectives: Optional[str] = None


class CourseStatusUpdate(BaseModel):
    """Schema for changing course status (publish, archive)."""
    status: str = Field(..., pattern=r"^(draft|published|archived)$")


class CourseResponse(BaseModel):
    """Schema for course API responses."""
    id: int
    title: str
    slug: str
    description: Optional[str]
    long_description: Optional[str]
    instructor_id: int
    category: Optional[str]
    level: Optional[str]
    language: str
    duration_hours: Optional[Decimal]
    price: Decimal
    currency: str
    thumbnail_url: Optional[str]
    status: str
    published_at: Optional[datetime]
    max_students: Optional[int]
    prerequisites: Optional[str]
    learning_objectives: Optional[str]
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CourseListResponse(BaseModel):
    """Paginated list of courses."""
    items: list[CourseResponse]
    total: int
    skip: int
    limit: int
