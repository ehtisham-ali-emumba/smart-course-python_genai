"""Progress event schemas."""

from uuid import UUID

from pydantic import BaseModel


class ProgressUpdatedPayload(BaseModel):
    """Payload for progress.updated event."""

    user_id: UUID
    enrollment_id: UUID
    course_id: UUID
    item_type: str
    item_id: str
    progress_percentage: float


class CourseCompletedPayload(BaseModel):
    """Payload for progress.course_completed event."""

    user_id: UUID
    enrollment_id: UUID
    course_id: UUID
