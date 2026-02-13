from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, UniqueConstraint

from core.database import Base


class Progress(Base):
    """Progress model — tracks individual content item completions."""

    __tablename__ = "progress"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    course_id = Column(Integer, nullable=False, index=True)
    item_type = Column(String(20), nullable=False)
    item_id = Column(String(50), nullable=False)
    completed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "item_type", "item_id", name="uq_progress_user_item"),
        Index("ix_progress_user_course", "user_id", "course_id"),
    )

    def __repr__(self) -> str:
        return f"<Progress(user={self.user_id}, item={self.item_type}:{self.item_id})>"
