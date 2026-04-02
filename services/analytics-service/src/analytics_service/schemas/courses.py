import uuid as _uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class PopularCourseItem(BaseModel):
    course_id: _uuid.UUID
    title: str
    total_enrollments: int
    completion_rate: Decimal
    avg_progress: Decimal


class CourseTrendItem(BaseModel):
    date: date
    new_enrollments: int
    new_completions: int


class CourseAnalyticsResponse(BaseModel):
    course_id: _uuid.UUID
    title: str
    total_enrollments: int
    active_enrollments: int
    completed_enrollments: int
    dropped_enrollments: int
    completion_rate: Decimal
    avg_progress_percentage: Decimal
    avg_time_to_complete_hours: Decimal | None
    avg_quiz_score: Decimal | None
    total_quiz_attempts: int
    ai_questions_asked: int
    enrollment_trend: list[CourseTrendItem]
