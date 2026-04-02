import uuid as _uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from analytics_service.models.base import Base


class StudentMetrics(Base):
    __tablename__ = "student_metrics"

    id: Mapped[_uuid.UUID] = mapped_column(primary_key=True, default=_uuid.uuid4)
    student_id: Mapped[_uuid.UUID] = mapped_column(unique=True, index=True)

    total_enrollments: Mapped[int] = mapped_column(default=0)
    active_enrollments: Mapped[int] = mapped_column(default=0)
    completed_courses: Mapped[int] = mapped_column(default=0)
    dropped_courses: Mapped[int] = mapped_column(default=0)
    avg_progress: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    avg_quiz_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    total_certificates: Mapped[int] = mapped_column(default=0)

    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
