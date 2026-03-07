"""Course publish workflow activities."""

from core_service.temporal.workflows.course_publish.activities.course import (
    validate_course_for_publish,
    mark_course_published,
    ValidateCourseInput,
    ValidateCourseOutput,
    MarkCoursePublishedInput,
    MarkCoursePublishedOutput,
    COURSE_ACTIVITIES,
)
from core_service.temporal.workflows.course_publish.activities.indexing import (
    trigger_course_indexing,
    poll_course_indexing_status,
    TriggerIndexingInput,
    TriggerIndexingOutput,
    PollIndexingStatusInput,
    PollIndexingStatusOutput,
    INDEXING_ACTIVITIES,
)
from core_service.temporal.workflows.course_publish.activities.notification import (
    notify_instructor_publish_success,
    notify_instructor_publish_failure,
    NotifyInstructorInput,
    NotifyInstructorOutput,
    NOTIFICATION_ACTIVITIES,
)

ALL_ACTIVITIES = COURSE_ACTIVITIES + INDEXING_ACTIVITIES + NOTIFICATION_ACTIVITIES

__all__ = [
    # Course
    "validate_course_for_publish",
    "mark_course_published",
    "ValidateCourseInput",
    "ValidateCourseOutput",
    "MarkCoursePublishedInput",
    "MarkCoursePublishedOutput",
    # Indexing
    "trigger_course_indexing",
    "poll_course_indexing_status",
    "TriggerIndexingInput",
    "TriggerIndexingOutput",
    "PollIndexingStatusInput",
    "PollIndexingStatusOutput",
    # Notification
    "notify_instructor_publish_success",
    "notify_instructor_publish_failure",
    "NotifyInstructorInput",
    "NotifyInstructorOutput",
    # Aggregated
    "ALL_ACTIVITIES",
]
