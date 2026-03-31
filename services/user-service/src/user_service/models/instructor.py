import uuid as _uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from user_service.core.database import Base


class InstructorProfile(Base):
    """Instructor profile extending User model."""

    __tablename__ = "instructor_profiles"

    id: Mapped[_uuid.UUID] = mapped_column(default=_uuid.uuid4, primary_key=True)
    user_id: Mapped[_uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
    )

    bio: Mapped[str | None] = mapped_column(Text, default=None)
    profile_picture_url: Mapped[str | None] = mapped_column(String(500), default=None)
    phone_number: Mapped[str | None] = mapped_column(String(20), default=None)

    total_students: Mapped[int] = mapped_column(default=0)
    total_courses: Mapped[int] = mapped_column(default=0)
    average_rating: Mapped[float] = mapped_column(Float, default=0.0)

    is_verified_instructor: Mapped[bool] = mapped_column(default=False)
    verification_date: Mapped[datetime | None] = mapped_column(default=None)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<InstructorProfile(user_id={self.user_id}, total_courses={self.total_courses})>"
