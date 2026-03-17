"""Enrollment event schemas."""

from uuid import UUID

from pydantic import BaseModel


class EnrollmentCreatedPayload(BaseModel):
    """Payload for enrollment.created event."""

    enrollment_id: UUID
    student_id: UUID
    course_id: UUID
    course_title: str
    email: str = ""


class EnrollmentCompletedPayload(BaseModel):
    """Payload for enrollment.completed event."""

    enrollment_id: UUID
    student_id: UUID
    course_id: UUID
    completed_at: str
    course_title: str | None = None
    email: str | None = None


class EnrollmentDroppedPayload(BaseModel):
    """Payload for enrollment.dropped event."""

    enrollment_id: UUID
    student_id: UUID
    course_id: UUID


class EnrollmentReactivatedPayload(BaseModel):
    """Payload for enrollment.reactivated event."""

    enrollment_id: UUID
    student_id: UUID
    course_id: UUID
