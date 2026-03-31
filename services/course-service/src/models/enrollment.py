import uuid as _uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Enrollment(Base):
    __tablename__ = "enrollments"

    id: Mapped[_uuid.UUID] = mapped_column(default=_uuid.uuid4, primary_key=True)
    student_id: Mapped[_uuid.UUID] = mapped_column(index=True)
    course_id: Mapped[_uuid.UUID] = mapped_column(ForeignKey("courses.id"), index=True)

    status: Mapped[str] = mapped_column(String(50), default="active", index=True)
    enrolled_at: Mapped[datetime] = mapped_column(server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)
    dropped_at: Mapped[datetime | None] = mapped_column(default=None)
    last_accessed_at: Mapped[datetime | None] = mapped_column(default=None)

    payment_status: Mapped[str | None] = mapped_column(String(50), default=None)
    payment_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), default=None)
    enrollment_source: Mapped[str | None] = mapped_column(String(100), default=None)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="uq_enrollment_student_course"),
        Index("idx_enrollments_enrolled_at", "enrolled_at"),
        Index("idx_enrollments_last_accessed", "last_accessed_at"),
    )

    def __repr__(self) -> str:
        return f"<Enrollment(id={self.id}, student={self.student_id}, course={self.course_id})>"
