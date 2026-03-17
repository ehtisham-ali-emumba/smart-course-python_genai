import uuid as _uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Progress(Base):
    __tablename__ = "progress"

    id: Mapped[_uuid.UUID] = mapped_column(default=_uuid.uuid4, primary_key=True)
    enrollment_id: Mapped[_uuid.UUID] = mapped_column(
        ForeignKey("enrollments.id", ondelete="CASCADE"), index=True
    )
    item_type: Mapped[str] = mapped_column(String(20))
    item_id: Mapped[str] = mapped_column(String(50))
    progress_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    completed_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "enrollment_id", "item_type", "item_id", name="uq_progress_enrollment_item"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Progress(enrollment={self.enrollment_id}, "
            f"item={self.item_type}:{self.item_id}, pct={self.progress_percentage})>"
        )
