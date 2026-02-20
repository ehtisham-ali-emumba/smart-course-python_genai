from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Request Schemas ───────────────────────────────────────────────


class ProgressCreate(BaseModel):
    """Schema for creating or updating progress on a lesson/quiz/summary."""

    enrollment_id: int
    item_type: str = Field(..., pattern=r"^(lesson|quiz|summary)$")
    item_id: str
    progress_percentage: Decimal = Field(..., ge=0, le=100)


# ── Response Schemas ──────────────────────────────────────────────


class ProgressResponse(BaseModel):
    """Schema for a single progress record."""

    id: int
    user_id: int
    enrollment_id: int
    item_type: str
    item_id: str
    progress_percentage: Decimal
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ModuleProgressDetail(BaseModel):
    """Computed progress for a single module (not stored — calculated on the fly)."""

    module_id: str
    module_title: str
    total_lessons: int
    completed_lessons: int
    progress_percentage: Decimal
    lessons: List[dict]
    is_complete: bool


class CourseProgressSummary(BaseModel):
    """Computed course-level progress (aggregated from lesson-level data)."""

    course_id: int
    user_id: int
    enrollment_id: int
    total_lessons: int
    completed_lessons: int
    progress_percentage: Decimal
    module_progress: List[ModuleProgressDetail]
    has_certificate: bool
    is_complete: bool
