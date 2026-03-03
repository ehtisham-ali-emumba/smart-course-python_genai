"""
Activities for the enrollment workflow.

Aggregates user, course, and notification activities so the workflow
and worker only need to import from this single package.
"""

from core_service.temporal.workflows.enrollment.activities.user import (
    fetch_user_details,
    validate_user_for_enrollment,
    FetchUserInput,
    FetchUserOutput,
    ValidateUserEnrollmentInput,
    ValidateUserEnrollmentOutput,
    USER_ACTIVITIES,
)
from core_service.temporal.workflows.enrollment.activities.course import (
    fetch_course_details,
    enroll_in_course,
    fetch_course_modules,
    FetchCourseInput,
    FetchCourseOutput,
    EnrollInCourseInput,
    EnrollInCourseOutput,
    FetchCourseModulesInput,
    FetchCourseModulesOutput,
    COURSE_ACTIVITIES,
)
from core_service.temporal.workflows.enrollment.activities.notification import (
    trigger_enrollment_notifications,
    send_in_app_notification,
    TriggerEnrollmentNotificationsInput,
    TriggerEnrollmentNotificationsOutput,
    SendInAppNotificationInput,
    SendInAppNotificationOutput,
    NOTIFICATION_ACTIVITIES,
)

ALL_ACTIVITIES = USER_ACTIVITIES + COURSE_ACTIVITIES + NOTIFICATION_ACTIVITIES

__all__ = [
    # User
    "fetch_user_details",
    "validate_user_for_enrollment",
    "FetchUserInput",
    "FetchUserOutput",
    "ValidateUserEnrollmentInput",
    "ValidateUserEnrollmentOutput",
    "USER_ACTIVITIES",
    # Course
    "fetch_course_details",
    "enroll_in_course",
    "fetch_course_modules",
    "FetchCourseInput",
    "FetchCourseOutput",
    "EnrollInCourseInput",
    "EnrollInCourseOutput",
    "FetchCourseModulesInput",
    "FetchCourseModulesOutput",
    "COURSE_ACTIVITIES",
    # Notification
    "trigger_enrollment_notifications",
    "send_in_app_notification",
    "TriggerEnrollmentNotificationsInput",
    "TriggerEnrollmentNotificationsOutput",
    "SendInAppNotificationInput",
    "SendInAppNotificationOutput",
    "NOTIFICATION_ACTIVITIES",
    # Aggregated
    "ALL_ACTIVITIES",
]
