import uuid as _uuid
from datetime import date as dt_date

from sqlalchemy import Date, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from analytics_service.models.base import Base


class EnrollmentDaily(Base):
    __tablename__ = "enrollment_daily"

    id: Mapped[_uuid.UUID] = mapped_column(primary_key=True, default=_uuid.uuid4)
    date: Mapped[dt_date] = mapped_column(Date, index=True)
    course_id: Mapped[_uuid.UUID | None] = mapped_column(nullable=True, index=True)

    new_enrollments: Mapped[int] = mapped_column(default=0)
    new_completions: Mapped[int] = mapped_column(default=0)
    new_drops: Mapped[int] = mapped_column(default=0)

    __table_args__ = (
        UniqueConstraint("date", "course_id", name="uq_enrollment_daily_date_course"),
    )
