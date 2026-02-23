"""Enrollment event schemas."""

from pydantic import BaseModel


class EnrollmentCreatedPayload(BaseModel):
    """Payload for enrollment.created event."""

    student_id: int
    course_id: int
    course_title: str
    email: str


class EnrollmentCompletedPayload(BaseModel):
    """Payload for enrollment.completed event."""

    enrollment_id: int
    student_id: int
    course_id: int
    completed_at: str
    course_title: str | None = None
    email: str | None = None


class EnrollmentDroppedPayload(BaseModel):
    """Payload for enrollment.dropped event."""

    enrollment_id: int
    student_id: int
    course_id: int


class EnrollmentReactivatedPayload(BaseModel):
    """Payload for enrollment.reactivated event."""

    enrollment_id: int
    student_id: int
    course_id: int
