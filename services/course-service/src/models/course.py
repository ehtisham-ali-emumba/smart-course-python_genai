from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, Numeric, String, Text

from core.database import Base


class Course(Base):
    """Course metadata model — stored in PostgreSQL."""
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    long_description = Column(Text, nullable=True)
    instructor_id = Column(Integer, nullable=False, index=True)  # FK to instructor_profiles.id (in user-service DB)
    category = Column(String(100), nullable=True, index=True)
    level = Column(String(50), nullable=True)  # beginner, intermediate, advanced
    language = Column(String(50), default="en", nullable=False)
    duration_hours = Column(Numeric(5, 2), nullable=True)
    price = Column(Numeric(10, 2), default=0.00, nullable=False)
    currency = Column(String(3), default="USD", nullable=False)
    thumbnail_url = Column(String(500), nullable=True)
    status = Column(String(50), nullable=False, default="draft", index=True)  # draft, published, archived
    published_at = Column(DateTime, nullable=True)
    max_students = Column(Integer, nullable=True)
    prerequisites = Column(Text, nullable=True)
    learning_objectives = Column(Text, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_courses_published_at", "published_at"),
    )

    def __repr__(self) -> str:
        return f"<Course(id={self.id}, title={self.title}, status={self.status})>"
