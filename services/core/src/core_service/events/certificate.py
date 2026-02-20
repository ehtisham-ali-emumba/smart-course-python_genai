from pydantic import BaseModel


class CertificateIssuedPayload(BaseModel):
    certificate_id: int
    enrollment_id: int
    student_id: int
    course_id: int
    certificate_number: str
    verification_code: str


class CertificateRevokedPayload(BaseModel):
    certificate_id: int
    enrollment_id: int
    reason: str
