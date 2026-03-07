"""Course event schemas."""

from pydantic import BaseModel


class CourseCreatedPayload(BaseModel):
    """Payload for course.created event."""

    course_id: int
    title: str
    instructor_id: int


class CourseUpdatedPayload(BaseModel):
    """Payload for course.updated event."""

    course_id: int
    instructor_id: int
    fields_changed: list[str]


class CoursePublishedPayload(BaseModel):
    """Payload for course.published event."""

    course_id: int
    title: str
    instructor_id: int
    published_at: str | None = None


class CourseArchivedPayload(BaseModel):
    """Payload for course.archived event."""

    course_id: int
    instructor_id: int
    title: str | None = None


class CourseDeletedPayload(BaseModel):
    """Payload for course.deleted event."""

    course_id: int
    instructor_id: int


class CoursePublishRequestedPayload(BaseModel):
    """Payload for course.publish_requested event (triggers Temporal workflow)."""

    course_id: int
    instructor_id: int
    title: str
