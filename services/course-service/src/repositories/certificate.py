from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.certificate import Certificate
from repositories.base import BaseRepository


class CertificateRepository(BaseRepository[Certificate]):
    """Certificate repository for PostgreSQL operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(db, Certificate)

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
