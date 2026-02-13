from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, Numeric, String, UniqueConstraint

from core.database import Base


class Enrollment(Base):
    """Enrollment model — stored in PostgreSQL."""

    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, nullable=False, index=True)
    course_id = Column(Integer, nullable=False, index=True)

    status = Column(String(50), nullable=False, default="active", index=True)
    enrolled_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    dropped_at = Column(DateTime, nullable=True)
    last_accessed_at = Column(DateTime, nullable=True)

    payment_status = Column(String(50), nullable=True)
    payment_amount = Column(Numeric(10, 2), nullable=True)
    enrollment_source = Column(String(100), nullable=True)

    time_spent_minutes = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="uq_enrollment_student_course"),
        Index("idx_enrollments_enrolled_at", "enrolled_at"),
        Index("idx_enrollments_last_accessed", "last_accessed_at"),
    )

    def __repr__(self) -> str:
        return f"<Enrollment(id={self.id}, student={self.student_id}, course={self.course_id})>"
