from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class EnrollmentCreate(BaseModel):
    """Schema for enrolling a student in a course."""

    course_id: int
    payment_amount: Optional[Decimal] = None
    enrollment_source: Optional[str] = Field(None, max_length=100)


class EnrollmentUpdate(BaseModel):
    """Schema for updating enrollment."""

    status: Optional[str] = Field(None, pattern=r"^(active|completed|dropped|suspended)$")


class EnrollmentResponse(BaseModel):
    """Schema for enrollment API responses."""

    id: int
    student_id: int
    course_id: int
    status: str
    enrolled_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    dropped_at: Optional[datetime]
    last_accessed_at: Optional[datetime]
    payment_status: Optional[str]
    payment_amount: Optional[Decimal]
    enrollment_source: Optional[str]
    time_spent_minutes: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EnrollmentListResponse(BaseModel):
    """Paginated list of enrollments."""

    items: list[EnrollmentResponse]
    total: int
    skip: int
    limit: int
