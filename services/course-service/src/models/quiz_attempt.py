from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from core.database import Base


class QuizAttempt(Base):
    """Quiz attempt model for module-level assessments."""

    __tablename__ = "quiz_attempts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    enrollment_id = Column(
        Integer,
        ForeignKey("enrollments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    module_id = Column(String(50), nullable=False, index=True)
    attempt_number = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="in_progress", index=True)
    score = Column(Numeric(5, 2), nullable=True)
    passed = Column(Boolean, nullable=True)
    time_spent_seconds = Column(Integer, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    submitted_at = Column(DateTime, nullable=True)
    graded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user_answers = relationship(
        "UserAnswer",
        back_populates="quiz_attempt",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "enrollment_id",
            "module_id",
            "attempt_number",
            name="uq_quiz_attempts",
        ),
        Index("idx_quiz_attempts_user_id", "user_id"),
        Index("idx_quiz_attempts_enrollment_id", "enrollment_id"),
        Index("idx_quiz_attempts_module_id", "module_id"),
        Index("idx_quiz_attempts_status", "status"),
    )
