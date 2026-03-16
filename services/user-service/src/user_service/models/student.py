import uuid as _uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from user_service.core.database import Base


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    id: Mapped[_uuid.UUID] = mapped_column(default=_uuid.uuid4, primary_key=True)
    user_id: Mapped[_uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
    )

    bio: Mapped[str | None] = mapped_column(Text, default=None)
    interests: Mapped[str | None] = mapped_column(String(500), default=None)
    education_level: Mapped[str | None] = mapped_column(String(100), default=None)
    profile_picture_url: Mapped[str | None] = mapped_column(String(500), default=None)

    total_enrollments: Mapped[int] = mapped_column(default=0)
    total_completed: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<StudentProfile(user_id={self.user_id})>"
