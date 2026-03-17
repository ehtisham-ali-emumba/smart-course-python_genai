from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Request Schemas ───────────────────────────────────────────────


class ProgressCreate(BaseModel):
    """Schema for creating or updating progress on a lesson/quiz/summary."""

    enrollment_id: UUID
    item_type: str = Field(..., pattern=r"^(lesson|quiz|summary|module_quiz|module_summary)$")
    item_id: str
    progress_percentage: Decimal = Field(..., ge=0, le=100)


# ── Response Schemas ──────────────────────────────────────────────


class ProgressResponse(BaseModel):
    """Schema for a single progress record."""

    id: UUID
    enrollment_id: UUID
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

    course_id: UUID
    enrollment_id: UUID
    total_lessons: int
    completed_lessons: int
    progress_percentage: Decimal
    module_progress: List[ModuleProgressDetail]
    has_certificate: bool
    is_complete: bool
