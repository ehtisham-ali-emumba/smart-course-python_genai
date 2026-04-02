import uuid as _uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from analytics_service.models.base import Base


class InstructorMetrics(Base):
    __tablename__ = "instructor_metrics"

    id: Mapped[_uuid.UUID] = mapped_column(primary_key=True, default=_uuid.uuid4)
    instructor_id: Mapped[_uuid.UUID] = mapped_column(unique=True, index=True)

    total_courses: Mapped[int] = mapped_column(default=0)
    published_courses: Mapped[int] = mapped_column(default=0)
    total_students: Mapped[int] = mapped_column(default=0)
    total_enrollments: Mapped[int] = mapped_column(default=0)
    total_completions: Mapped[int] = mapped_column(default=0)
    avg_completion_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    avg_quiz_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
