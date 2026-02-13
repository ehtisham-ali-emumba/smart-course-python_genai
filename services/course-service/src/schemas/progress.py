from datetime import datetime
from decimal import Decimal
from typing import List

from pydantic import BaseModel, ConfigDict, Field


class ProgressCreate(BaseModel):
    """Schema for marking an item as completed."""

    course_id: int
    item_type: str = Field(..., pattern=r"^(lesson|quiz|summary)$")
    item_id: str


class ProgressResponse(BaseModel):
    """Schema for a single progress record."""

    id: int
    user_id: int
    course_id: int
    item_type: str
    item_id: str
    completed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CourseProgressSummary(BaseModel):
    """Schema for computed course progress."""

    course_id: int
    user_id: int
    enrollment_id: int
    total_items: int
    completed_items: int
    completion_percentage: Decimal
    completed_lessons: List[str]
    completed_quizzes: List[str]
    completed_summaries: List[str]
    has_certificate: bool
    is_complete: bool


class ProgressUpdate(BaseModel):
    """Schema for marking a lesson/quiz/summary as completed."""

    item_type: str = Field(..., pattern=r"^(lesson|quiz|summary)$")
    item_id: str
