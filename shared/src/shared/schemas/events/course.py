"""Course event schemas."""

from uuid import UUID

from pydantic import BaseModel


class CourseCreatedPayload(BaseModel):
    """Payload for course.created event."""

    course_id: UUID
    title: str
    instructor_id: UUID


class CourseUpdatedPayload(BaseModel):
    """Payload for course.updated event."""

    course_id: UUID
    instructor_id: UUID
    fields_changed: list[str]


class CoursePublishedPayload(BaseModel):
    """Payload for course.published event."""

    course_id: UUID
    title: str
    instructor_id: UUID
    published_at: str | None = None


class CourseArchivedPayload(BaseModel):
    """Payload for course.archived event."""

    course_id: UUID
    instructor_id: UUID
    title: str | None = None


class CourseDeletedPayload(BaseModel):
    """Payload for course.deleted event."""

    course_id: UUID
    instructor_id: UUID


class CoursePublishRequestedPayload(BaseModel):
    """Payload for course.publish_requested event (triggers Temporal workflow)."""

    course_id: UUID
    instructor_id: UUID
    title: str
