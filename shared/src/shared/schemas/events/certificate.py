"""Certificate event schemas."""

from pydantic import BaseModel


class CertificateIssuedPayload(BaseModel):
    """Payload for certificate.issued event."""

    certificate_id: int
    enrollment_id: int
    student_id: int
    student_name: str | None = None
    course_id: int
    course_title: str | None = None
    certificate_number: str
    verification_code: str
    issued_date: str | None = None
    instructor_name: str | None = None
    email: str | None = None


class CertificateRevokedPayload(BaseModel):
    """Payload for certificate.revoked event."""

    certificate_id: int
    enrollment_id: int
    reason: str
