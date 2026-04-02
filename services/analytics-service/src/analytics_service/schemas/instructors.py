import uuid as _uuid
from decimal import Decimal

from pydantic import BaseModel


class InstructorCourseItem(BaseModel):
    course_id: _uuid.UUID
    title: str
    enrollments: int
    completion_rate: Decimal


class InstructorAnalyticsResponse(BaseModel):
    instructor_id: _uuid.UUID
    total_courses: int
    published_courses: int
    total_students: int
    total_enrollments: int
    total_completions: int
    avg_completion_rate: Decimal
    avg_quiz_score: Decimal | None
    courses: list[InstructorCourseItem]


class InstructorLeaderboardItem(BaseModel):
    instructor_id: _uuid.UUID
    total_students: int
    avg_completion_rate: Decimal
