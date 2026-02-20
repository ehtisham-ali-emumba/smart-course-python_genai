from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)

from core.database import Base


class Progress(Base):
    """Progress model — tracks per-lesson progress for each enrollment."""

    __tablename__ = "progress"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    enrollment_id = Column(
        Integer,
        ForeignKey("enrollments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_type = Column(String(20), nullable=False)
    item_id = Column(String(50), nullable=False)
    progress_percentage = Column(Numeric(5, 2), nullable=False, default=0)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "enrollment_id", "item_type", "item_id",
            name="uq_progress_user_enrollment_item",
        ),
        Index("ix_progress_user_enrollment", "user_id", "enrollment_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<Progress(user={self.user_id}, enrollment={self.enrollment_id}, "
            f"item={self.item_type}:{self.item_id}, pct={self.progress_percentage})>"
        )
