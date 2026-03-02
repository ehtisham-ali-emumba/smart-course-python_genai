from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from core.database import Base


class UserAnswer(Base):
    """User answer model for individual question responses."""

    __tablename__ = "user_answers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    quiz_attempt_id = Column(
        Integer,
        ForeignKey("quiz_attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(Integer, nullable=False, index=True)
    question_id = Column(String(50), nullable=False, index=True)
    question_type = Column(String(20), nullable=False)
    user_response = Column(JSONB, nullable=False)
    is_correct = Column(Boolean, nullable=True)
    time_spent_seconds = Column(Integer, nullable=True)
    answered_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    quiz_attempt = relationship("QuizAttempt", back_populates="user_answers")

    __table_args__ = (
        Index("idx_user_answers_attempt_id", "quiz_attempt_id"),
        Index("idx_user_answers_user_id", "user_id"),
        Index("idx_user_answers_question_id", "question_id"),
    )
