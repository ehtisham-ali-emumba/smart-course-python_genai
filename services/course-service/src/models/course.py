import uuid as _uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[_uuid.UUID] = mapped_column(default=_uuid.uuid4, primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    long_description: Mapped[str | None] = mapped_column(Text, default=None)
    instructor_id: Mapped[_uuid.UUID] = mapped_column(index=True)
    category: Mapped[str | None] = mapped_column(String(100), default=None, index=True)
    level: Mapped[str | None] = mapped_column(String(50), default=None)
    language: Mapped[str] = mapped_column(String(50), default="en")
    duration_hours: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), default=None)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), default=None)
    status: Mapped[str] = mapped_column(String(50), default="draft", index=True)
    published_at: Mapped[datetime | None] = mapped_column(default=None)
    max_students: Mapped[int | None] = mapped_column(default=None)
    prerequisites: Mapped[str | None] = mapped_column(Text, default=None)
    learning_objectives: Mapped[str | None] = mapped_column(Text, default=None)
    is_deleted: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (Index("idx_courses_published_at", "published_at"),)

    def __repr__(self) -> str:
        return f"<Course(id={self.id}, title={self.title}, status={self.status})>"
