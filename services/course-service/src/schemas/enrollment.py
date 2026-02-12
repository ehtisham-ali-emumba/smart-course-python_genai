from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class EnrollmentCreate(BaseModel):
    """Schema for enrolling a student in a course."""
    course_id: int
    payment_amount: Optional[Decimal] = None
    enrollment_source: Optional[str] = Field(None, max_length=100)


class EnrollmentUpdate(BaseModel):
    """Schema for updating enrollment (progress)."""
    status: Optional[str] = Field(None, pattern=r"^(active|completed|dropped|suspended)$")
    current_module_id: Optional[int] = None
    current_lesson_id: Optional[int] = None


class ProgressUpdate(BaseModel):
    """Schema for updating lesson/module completion progress."""
    lesson_id: Optional[int] = None  # Mark this lesson as completed
    module_id: Optional[int] = None  # Mark this module as completed
    time_spent_minutes: Optional[int] = Field(None, ge=0)


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
    completed_modules: list[int]
    completed_lessons: list[int]
    total_modules: int
    total_lessons: int
    completion_percentage: Decimal
    completed_quizzes: list[int]
    quiz_scores: Optional[dict[str, Any]]
    time_spent_minutes: int
    current_module_id: Optional[int]
    current_lesson_id: Optional[int]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EnrollmentListResponse(BaseModel):
    """Paginated list of enrollments."""
    items: list[EnrollmentResponse]
    total: int
    skip: int
    limit: int
