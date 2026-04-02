import uuid as _uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from analytics_service.models.base import Base


class CourseMetrics(Base):
    __tablename__ = "course_metrics"

    id: Mapped[_uuid.UUID] = mapped_column(primary_key=True, default=_uuid.uuid4)
    course_id: Mapped[_uuid.UUID] = mapped_column(unique=True, index=True)
    instructor_id: Mapped[_uuid.UUID | None] = mapped_column(index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(255), default="Untitled Course")
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    total_enrollments: Mapped[int] = mapped_column(default=0)
    active_enrollments: Mapped[int] = mapped_column(default=0)
    completed_enrollments: Mapped[int] = mapped_column(default=0)
    dropped_enrollments: Mapped[int] = mapped_column(default=0)
    completion_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)

    avg_progress_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    avg_time_to_complete_hours: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )

    avg_quiz_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    total_quiz_attempts: Mapped[int] = mapped_column(default=0)

    ai_questions_asked: Mapped[int] = mapped_column(default=0)

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_enrollment_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
