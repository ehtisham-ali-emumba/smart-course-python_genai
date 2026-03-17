import uuid as _uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Certificate(Base):
    __tablename__ = "certificates"

    id: Mapped[_uuid.UUID] = mapped_column(default=_uuid.uuid4, primary_key=True)
    enrollment_id: Mapped[_uuid.UUID] = mapped_column(
        ForeignKey("enrollments.id", ondelete="CASCADE"), unique=True
    )
    certificate_number: Mapped[str] = mapped_column(String(100), unique=True)
    issue_date: Mapped[date] = mapped_column(server_default=func.current_date())
    certificate_url: Mapped[str | None] = mapped_column(String(500), default=None)
    verification_code: Mapped[str] = mapped_column(String(50), unique=True)
    grade: Mapped[str | None] = mapped_column(String(10), default=None)
    score_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), default=None)
    issued_by_id: Mapped[_uuid.UUID | None] = mapped_column(default=None)
    is_revoked: Mapped[bool] = mapped_column(default=False)
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)
    revoked_reason: Mapped[str | None] = mapped_column(Text, default=None)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (Index("idx_certificates_enrollment", "enrollment_id"),)

    def __repr__(self) -> str:
        return f"<Certificate(id={self.id}, cert_number={self.certificate_number})>"
