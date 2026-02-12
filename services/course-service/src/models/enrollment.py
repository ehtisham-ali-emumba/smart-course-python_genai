from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from core.database import Base


class Enrollment(Base):
    """Enrollment model with merged progress fields — stored in PostgreSQL."""
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, nullable=False, index=True)  # FK to users.id (in user-service DB)
    course_id = Column(Integer, nullable=False, index=True)  # FK to courses.id

    # Enrollment fields
    status = Column(String(50), nullable=False, default="active", index=True)  # active, completed, dropped, suspended
    enrolled_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    dropped_at = Column(DateTime, nullable=True)
    last_accessed_at = Column(DateTime, nullable=True)

    # Payment fields
    payment_status = Column(String(50), nullable=True)  # pending, completed, refunded
    payment_amount = Column(Numeric(10, 2), nullable=True)
    enrollment_source = Column(String(100), nullable=True)  # web, mobile, api

    # Progress fields (merged from former progress table)
    completed_modules = Column(ARRAY(Integer), default=list, nullable=False)
    completed_lessons = Column(ARRAY(Integer), default=list, nullable=False)
    total_modules = Column(Integer, default=0, nullable=False)
    total_lessons = Column(Integer, default=0, nullable=False)
    completion_percentage = Column(Numeric(5, 2), default=0.00, nullable=False)
    completed_quizzes = Column(ARRAY(Integer), default=list, nullable=False)
    quiz_scores = Column(JSONB, nullable=True)  # {quiz_id: score}
    time_spent_minutes = Column(Integer, default=0, nullable=False)
    current_module_id = Column(Integer, nullable=True)
    current_lesson_id = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="uq_enrollment_student_course"),
        Index("idx_enrollments_enrolled_at", "enrolled_at"),
        Index("idx_enrollments_last_accessed", "last_accessed_at"),
    )

    def __repr__(self) -> str:
        return f"<Enrollment(id={self.id}, student={self.student_id}, course={self.course_id}, status={self.status})>"
