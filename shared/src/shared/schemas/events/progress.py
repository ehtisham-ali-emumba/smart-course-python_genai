"""Progress event schemas."""

from pydantic import BaseModel


class ProgressUpdatedPayload(BaseModel):
    """Payload for progress.updated event."""

    user_id: int
    enrollment_id: int
    course_id: int
    item_type: str
    item_id: str
    progress_percentage: float


class CourseCompletedPayload(BaseModel):
    """Payload for progress.course_completed event."""

    user_id: int
    enrollment_id: int
    course_id: int
