import uuid
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from models.certificate import Certificate
from repositories.certificate import CertificateRepository
from repositories.enrollment import EnrollmentRepository
from schemas.certificate import CertificateCreate


class CertificateService:
    """Business logic for certificate operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.cert_repo = CertificateRepository(db)
        self.enrollment_repo = EnrollmentRepository(db)

    async def issue_certificate(
        self, data: CertificateCreate, issued_by_id: int
    ) -> Certificate:
        """Issue a certificate for a completed enrollment."""
        # Verify enrollment exists and is completed
        enrollment = await self.enrollment_repo.get_by_id(data.enrollment_id)
        if not enrollment:
            raise ValueError("Enrollment not found")
        if enrollment.status != "completed":
            raise ValueError("Enrollment is not completed — cannot issue certificate")

        # Check if certificate already exists for this enrollment
        existing = await self.cert_repo.get_by_enrollment(data.enrollment_id)
        if existing:
            raise ValueError("Certificate already issued for this enrollment")

        cert_data = {
            "enrollment_id": data.enrollment_id,
            "certificate_number": f"SC-{uuid.uuid4().hex[:12].upper()}",
            "issue_date": date.today(),
            "verification_code": uuid.uuid4().hex[:8].upper(),
            "grade": data.grade,
            "score_percentage": data.score_percentage,
            "issued_by_id": issued_by_id,
        }
        return await self.cert_repo.create(cert_data)

    async def get_certificate(self, certificate_id: int) -> Certificate | None:
        """Get certificate by ID."""
        return await self.cert_repo.get_by_id(certificate_id)

    async def get_certificate_by_enrollment(self, enrollment_id: int) -> Certificate | None:
        """Get certificate by enrollment ID."""
        return await self.cert_repo.get_by_enrollment(enrollment_id)

    async def verify_certificate(self, verification_code: str) -> Certificate | None:
        """Public verification — look up certificate by verification code."""
        return await self.cert_repo.get_by_verification_code(verification_code)

    async def revoke_certificate(
        self, certificate_id: int, reason: str, revoked_by_id: int
    ) -> Certificate | None:
        """Revoke a certificate."""
        cert = await self.cert_repo.get_by_id(certificate_id)
        if not cert:
            return None

        return await self.cert_repo.update(certificate_id, {
            "is_revoked": True,
            "revoked_at": datetime.utcnow(),
            "revoked_reason": reason,
        })
