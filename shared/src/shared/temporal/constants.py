"""Temporal workflow and activity name constants.

Both the worker (core-service) and any client (course-service, etc.)
import from here so names stay in sync.
"""


class TaskQueues:
    """Temporal task queue names."""

    CORE = "core-service"


class Workflows:
    """Temporal workflow names — must match @workflow.defn(name=...) in core-service."""

    ENROLLMENT = "EnrollmentWorkflow"
    COURSE_PUBLISH = "CoursePublishWorkflow"


class Activities:
    """Temporal activity names — must match @activity.defn(name=...) in core-service."""

    # ── Enrollment workflow activities ──
    VALIDATE_USER_FOR_ENROLLMENT = "validate_user_for_enrollment"
    FETCH_USER_DETAILS = "fetch_user_details"
    FETCH_COURSE_DETAILS = "fetch_course_details"
    ENROLL_IN_COURSE = "enroll_in_course"
    FETCH_COURSE_MODULES = "fetch_course_modules"
    TRIGGER_ENROLLMENT_NOTIFICATIONS = "trigger_enrollment_notifications"
    SEND_IN_APP_NOTIFICATION = "send_in_app_notification"

    # ── Course publish workflow activities ──
    VALIDATE_COURSE_FOR_PUBLISH = "validate_course_for_publish"
    MARK_COURSE_PUBLISHED = "mark_course_published"
    TRIGGER_COURSE_INDEXING = "trigger_course_indexing"
    POLL_COURSE_INDEXING_STATUS = "poll_course_indexing_status"
    NOTIFY_INSTRUCTOR_PUBLISH_SUCCESS = "notify_instructor_publish_success"
    NOTIFY_INSTRUCTOR_PUBLISH_FAILURE = "notify_instructor_publish_failure"
