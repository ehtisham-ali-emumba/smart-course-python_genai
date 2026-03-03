"""
Temporal activities for core-service.

All imports are re-exported here so workflows and the worker
only import from this single package — the real vs mock switch
happens in one place.
"""

from core_service.temporal.activities.user_activities import (
    fetch_user_details,
    validate_user_for_enrollment,
    FetchUserInput,
    FetchUserOutput,
    ValidateUserEnrollmentInput,
    ValidateUserEnrollmentOutput,
    USER_ACTIVITIES,
)
from core_service.temporal.activities.course_activities import (
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
from core_service.temporal.activities.notification_activities import (
    trigger_enrollment_notifications,
    send_in_app_notification,
    TriggerEnrollmentNotificationsInput,
    TriggerEnrollmentNotificationsOutput,
    SendInAppNotificationInput,
    SendInAppNotificationOutput,
    NOTIFICATION_ACTIVITIES,
)

# All activities registered with the Temporal worker
ALL_ACTIVITIES = USER_ACTIVITIES + COURSE_ACTIVITIES + NOTIFICATION_ACTIVITIES

__all__ = [
    # User
    "fetch_user_details",
    "validate_user_for_enrollment",
    "FetchUserInput",
    "FetchUserOutput",
    "ValidateUserEnrollmentInput",
    "ValidateUserEnrollmentOutput",
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
    # Notification
    "trigger_enrollment_notifications",
    "send_in_app_notification",
    "TriggerEnrollmentNotificationsInput",
    "TriggerEnrollmentNotificationsOutput",
    "SendInAppNotificationInput",
    "SendInAppNotificationOutput",
    # Combined list
    "ALL_ACTIVITIES",
]
