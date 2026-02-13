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
        self,
        data: CertificateCreate,
        user_id: int,
        role: str,
    ) -> Certificate:
        """
        Issue a certificate for a completed enrollment.
        - Instructors/admins: can issue for any completed enrollment.
        - Students: can only claim for their own enrollment (verified by ownership).
        """
        enrollment = await self.enrollment_repo.get_by_id(data.enrollment_id)
        if not enrollment:
            raise ValueError("Enrollment not found")
        if enrollment.status != "completed":
            raise ValueError(
                "Enrollment is not completed — complete all modules first to earn a certificate"
            )

        # Students can only claim cert for their own enrollment
        if role not in ("instructor", "admin"):
            if enrollment.student_id != user_id:
                raise ValueError("You can only request a certificate for your own enrollment")

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
            "issued_by_id": user_id,
        }
        return await self.cert_repo.create(cert_data)

    async def get_certificate(self, certificate_id: int) -> Certificate | None:
        """Get certificate by ID."""
        return await self.cert_repo.get_by_id(certificate_id)

    async def get_certificates_for_user(
        self, user_id: int, role: str, skip: int = 0, limit: int = 50
    ) -> tuple[list[Certificate], int]:
        """Get all certificates for a user. Students see only their own; instructors see all (future)."""
        certs = await self.cert_repo.get_all_by_student_id(user_id, skip=skip, limit=limit)
        total = await self.cert_repo.count_by_student_id(user_id)
        return certs, total

    async def get_certificate_by_enrollment(
        self, enrollment_id: int, user_id: int, role: str
    ) -> Certificate:
        """Get certificate by enrollment ID. Students must own the enrollment."""
        enrollment = await self.enrollment_repo.get_by_id(enrollment_id)
        if not enrollment:
            raise ValueError("Enrollment not found")
        if role not in ("instructor", "admin") and enrollment.student_id != user_id:
            raise ValueError("You can only view certificates for your own enrollments")
        cert = await self.cert_repo.get_by_enrollment(enrollment_id)
        if not cert:
            raise ValueError("No certificate issued for this enrollment")
        return cert

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
