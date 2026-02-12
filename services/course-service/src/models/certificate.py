from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text

from core.database import Base


class Certificate(Base):
    """Certificate model — stored in PostgreSQL."""
    __tablename__ = "certificates"

    id = Column(Integer, primary_key=True, index=True)
    enrollment_id = Column(
        Integer,
        ForeignKey("enrollments.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    certificate_number = Column(String(100), unique=True, nullable=False)
    issue_date = Column(Date, nullable=False, default=date.today)
    certificate_url = Column(String(500), nullable=True)
    verification_code = Column(String(50), unique=True, nullable=False)
    grade = Column(String(10), nullable=True)  # A, B, C
    score_percentage = Column(Numeric(5, 2), nullable=True)
    issued_by_id = Column(Integer, nullable=True)  # FK to users.id (instructor)
    is_revoked = Column(Boolean, default=False, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    revoked_reason = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_certificates_enrollment", "enrollment_id"),
    )

    def __repr__(self) -> str:
        return f"<Certificate(id={self.id}, cert_number={self.certificate_number})>"
