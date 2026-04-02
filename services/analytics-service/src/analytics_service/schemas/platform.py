from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class PlatformOverviewResponse(BaseModel):
    total_students: int
    total_instructors: int
    total_courses_published: int
    total_enrollments: int
    total_completions: int
    avg_completion_rate: Decimal
    avg_courses_per_student: Decimal
    total_certificates_issued: int


class PlatformTrendItem(BaseModel):
    date: date
    new_enrollments: int
    new_completions: int
    new_drops: int


class AIUsageTrendItem(BaseModel):
    date: date
    tutor_questions: int
    instructor_requests: int
    total: int
