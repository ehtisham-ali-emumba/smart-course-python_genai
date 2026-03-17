import uuid as _uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[_uuid.UUID] = mapped_column(default=_uuid.uuid4, primary_key=True)
    enrollment_id: Mapped[_uuid.UUID] = mapped_column(
        ForeignKey("enrollments.id", ondelete="CASCADE"), index=True
    )
    module_id: Mapped[str] = mapped_column(String(50), index=True)
    attempt_number: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(20), default="in_progress", index=True)
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), default=None)
    passed: Mapped[bool | None] = mapped_column(default=None)
    time_spent_seconds: Mapped[int | None] = mapped_column(default=None)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(default=None)
    graded_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    user_answers = relationship(
        "UserAnswer",
        back_populates="quiz_attempt",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("enrollment_id", "module_id", "attempt_number", name="uq_quiz_attempts"),
    )
