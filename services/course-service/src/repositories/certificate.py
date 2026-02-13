from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.certificate import Certificate
from models.enrollment import Enrollment
from repositories.base import BaseRepository


class CertificateRepository(BaseRepository[Certificate]):
    """Certificate repository for PostgreSQL operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(db, Certificate)

    async def get_all_by_student_id(
        self, student_id: int, skip: int = 0, limit: int = 100
    ) -> List[Certificate]:
        """Get all certificates for a student (via their enrollments)."""
        result = await self.db.execute(
            select(Certificate)
            .join(Enrollment, Certificate.enrollment_id == Enrollment.id)
            .where(Enrollment.student_id == student_id)
            .order_by(Certificate.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_student_id(self, student_id: int) -> int:
        """Count certificates for a student."""
        result = await self.db.execute(
            select(func.count(Certificate.id))
            .join(Enrollment, Certificate.enrollment_id == Enrollment.id)
            .where(Enrollment.student_id == student_id)
        )
        return result.scalar() or 0

    async def get_by_enrollment(self, enrollment_id: int) -> Optional[Certificate]:
        """Get certificate by enrollment ID."""
        result = await self.db.execute(
            select(Certificate).where(Certificate.enrollment_id == enrollment_id)
        )
        return result.scalars().first()

    async def get_by_certificate_number(self, cert_number: str) -> Optional[Certificate]:
        """Get certificate by its unique certificate number."""
        result = await self.db.execute(
            select(Certificate).where(Certificate.certificate_number == cert_number)
        )
        return result.scalars().first()

    async def get_by_verification_code(self, code: str) -> Optional[Certificate]:
        """Get certificate by its public verification code."""
        result = await self.db.execute(
            select(Certificate).where(Certificate.verification_code == code)
        )
        return result.scalars().first()
