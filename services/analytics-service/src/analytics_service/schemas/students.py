import uuid as _uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class StudentAnalyticsResponse(BaseModel):
    student_id: _uuid.UUID
    total_enrollments: int
    active_enrollments: int
    completed_courses: int
    dropped_courses: int
    avg_progress: Decimal
    avg_quiz_score: Decimal | None
    total_certificates: int
    last_active_at: datetime | None
