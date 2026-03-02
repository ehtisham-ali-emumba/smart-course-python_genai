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
    initialize_course_progress,
    fetch_course_modules,
    FetchCourseInput,
    FetchCourseOutput,
    InitializeProgressInput,
    InitializeProgressOutput,
    FetchCourseModulesInput,
    FetchCourseModulesOutput,
    COURSE_ACTIVITIES,
)
from core_service.temporal.activities.notification_activities import (
    trigger_enrollment_notifications,
    send_in_app_notification,
    send_course_published_notification,
    send_instructor_course_published_notification,
    TriggerEnrollmentNotificationsInput,
    TriggerEnrollmentNotificationsOutput,
    SendInAppNotificationInput,
    SendInAppNotificationOutput,
    SendCoursePublishedNotificationInput,
    SendCoursePublishedNotificationOutput,
    SendInstructorNotificationInput,
    SendInstructorNotificationOutput,
    NOTIFICATION_ACTIVITIES,
)
from core_service.temporal.activities.ai_activities import (
    validate_course_for_publishing,
    fetch_course_content_for_rag,
    generate_rag_embeddings,
    store_rag_index,
    fetch_enrolled_students,
    ValidateCoursePublishInput,
    ValidateCoursePublishOutput,
    FetchCourseContentForRagInput,
    FetchCourseContentForRagOutput,
    GenerateRagEmbeddingsInput,
    GenerateRagEmbeddingsOutput,
    StoreRagIndexInput,
    StoreRagIndexOutput,
    FetchEnrolledStudentsInput,
    FetchEnrolledStudentsOutput,
    AI_ACTIVITIES,
)

# All activities registered with the Temporal worker
ALL_ACTIVITIES = (
    USER_ACTIVITIES + COURSE_ACTIVITIES + NOTIFICATION_ACTIVITIES + AI_ACTIVITIES
)

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
    "initialize_course_progress",
    "fetch_course_modules",
    "FetchCourseInput",
    "FetchCourseOutput",
    "InitializeProgressInput",
    "InitializeProgressOutput",
    "FetchCourseModulesInput",
    "FetchCourseModulesOutput",
    # Notification
    "trigger_enrollment_notifications",
    "send_in_app_notification",
    "send_course_published_notification",
    "send_instructor_course_published_notification",
    "TriggerEnrollmentNotificationsInput",
    "TriggerEnrollmentNotificationsOutput",
    "SendInAppNotificationInput",
    "SendInAppNotificationOutput",
    "SendCoursePublishedNotificationInput",
    "SendCoursePublishedNotificationOutput",
    "SendInstructorNotificationInput",
    "SendInstructorNotificationOutput",
    # AI
    "validate_course_for_publishing",
    "fetch_course_content_for_rag",
    "generate_rag_embeddings",
    "store_rag_index",
    "fetch_enrolled_students",
    "ValidateCoursePublishInput",
    "ValidateCoursePublishOutput",
    "FetchCourseContentForRagInput",
    "FetchCourseContentForRagOutput",
    "GenerateRagEmbeddingsInput",
    "GenerateRagEmbeddingsOutput",
    "StoreRagIndexInput",
    "StoreRagIndexOutput",
    "FetchEnrolledStudentsInput",
    "FetchEnrolledStudentsOutput",
    # Combined list
    "ALL_ACTIVITIES",
]
