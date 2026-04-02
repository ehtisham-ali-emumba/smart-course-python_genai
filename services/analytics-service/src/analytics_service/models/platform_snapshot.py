import uuid as _uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from analytics_service.models.base import Base


class PlatformSnapshot(Base):
    __tablename__ = "platform_snapshots"

    id: Mapped[_uuid.UUID] = mapped_column(primary_key=True, default=_uuid.uuid4)
    snapshot_date: Mapped[date] = mapped_column(Date, unique=True, index=True)

    total_students: Mapped[int] = mapped_column(default=0)
    total_instructors: Mapped[int] = mapped_column(default=0)
    total_courses_published: Mapped[int] = mapped_column(default=0)
    total_enrollments: Mapped[int] = mapped_column(default=0)
    total_completions: Mapped[int] = mapped_column(default=0)
    total_certificates_issued: Mapped[int] = mapped_column(default=0)

    new_students_today: Mapped[int] = mapped_column(default=0)
    new_instructors_today: Mapped[int] = mapped_column(default=0)
    new_enrollments_today: Mapped[int] = mapped_column(default=0)
    new_completions_today: Mapped[int] = mapped_column(default=0)

    avg_courses_per_student: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=0)
    avg_completion_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)

    ai_questions_asked_today: Mapped[int] = mapped_column(default=0)
    ai_questions_answered_today: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
