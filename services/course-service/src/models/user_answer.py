import uuid as _uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class UserAnswer(Base):
    __tablename__ = "user_answers"

    id: Mapped[_uuid.UUID] = mapped_column(default=_uuid.uuid4, primary_key=True)
    quiz_attempt_id: Mapped[_uuid.UUID] = mapped_column(
        ForeignKey("quiz_attempts.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(String(50), index=True)
    question_type: Mapped[str] = mapped_column(String(20))
    user_response: Mapped[dict] = mapped_column(JSONB)
    is_correct: Mapped[bool | None] = mapped_column(default=None)
    time_spent_seconds: Mapped[int | None] = mapped_column(default=None)
    answered_at: Mapped[datetime] = mapped_column(server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    quiz_attempt = relationship("QuizAttempt", back_populates="user_answers")
