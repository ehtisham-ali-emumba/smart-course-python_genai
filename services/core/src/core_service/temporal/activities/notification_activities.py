"""Real HTTP activities that call notification-service."""

import logging
from dataclasses import dataclass

from temporalio import activity

from core_service.config import core_settings
from core_service.temporal.activities.http_client import post_json

logger = logging.getLogger(__name__)

NOTIFICATION_SERVICE = core_settings.NOTIFICATION_SERVICE_URL


# ── Data classes ───────────────────────────────────────────────────────────────


@dataclass
class TriggerEnrollmentNotificationsInput:
    student_id: int
    student_email: str
    student_name: str | None
    course_id: int
    course_title: str
    enrollment_id: int = 0


@dataclass
class TriggerEnrollmentNotificationsOutput:
    success: bool
    notification_id: str | None = None
    error: str | None = None


@dataclass
class SendInAppNotificationInput:
    user_id: int
    title: str
    message: str
    notification_type: str = "info"


@dataclass
class SendInAppNotificationOutput:
    success: bool
    notification_id: str | None = None
    error: str | None = None


@dataclass
class SendCoursePublishedNotificationInput:
    course_id: int
    course_title: str
    instructor_id: int
    affected_student_ids: list[int]
    event: str = "published"


@dataclass
class SendCoursePublishedNotificationOutput:
    success: bool
    students_notified: int = 0
    error: str | None = None


@dataclass
class SendInstructorNotificationInput:
    instructor_id: int
    course_id: int
    course_title: str
    rag_indexed: bool = True


@dataclass
class SendInstructorNotificationOutput:
    success: bool
    error: str | None = None


# ── Activities ─────────────────────────────────────────────────────────────────


@activity.defn(name="trigger_enrollment_notifications")
async def trigger_enrollment_notifications(
    input: TriggerEnrollmentNotificationsInput,
) -> TriggerEnrollmentNotificationsOutput:
    """
    POST http://notification-service:8005/notifications/enrollment

    Triggers both email and in-app notifications via Celery tasks
    in the notification service.
    """
    url = f"{NOTIFICATION_SERVICE}/notifications/enrollment"
    headers = {"X-User-ID": str(input.student_id)}

    payload = {
        "user_id": input.student_id,
        "email": "test@test.com",
        "course_id": input.course_id,
        "course_title": input.course_title,
        "enrollment_id": 1,
        "instructor_name": "",  # Not available at this step
    }

    try:
        resp = await post_json(url, payload, headers=headers)
        return TriggerEnrollmentNotificationsOutput(
            success=resp.get("success", True),
            notification_id=resp.get("notification_id"),
        )
    except Exception as e:
        logger.warning("trigger_enrollment_notifications failed: %s", e)
        return TriggerEnrollmentNotificationsOutput(success=False, error=str(e))


@activity.defn(name="send_in_app_notification")
async def send_in_app_notification(
    input: SendInAppNotificationInput,
) -> SendInAppNotificationOutput:
    """
    POST http://notification-service:8005/notifications/send
    Uses SendNotificationRequest schema.
    """
    url = f"{NOTIFICATION_SERVICE}/notifications/send"
    headers = {"X-User-ID": str(input.user_id)}

    payload = {
        "user_id": input.user_id,
        "type": input.notification_type,
        "channel": "in_app",
        "priority": "normal",
        "title": input.title,
        "message": input.message,
    }

    try:
        resp = await post_json(url, payload, headers=headers)
        return SendInAppNotificationOutput(
            success=resp.get("success", True),
            notification_id=resp.get("notification_id"),
        )
    except Exception as e:
        logger.warning("send_in_app_notification failed: %s", e)
        return SendInAppNotificationOutput(success=False, error=str(e))


@activity.defn(name="send_course_published_notification")
async def send_course_published_notification(
    input: SendCoursePublishedNotificationInput,
) -> SendCoursePublishedNotificationOutput:
    """
    POST http://notification-service:8005/notifications/course
    Notifies all enrolled students that the course is now published.
    Uses CourseNotificationRequest schema with affected_user_ids.
    """
    url = f"{NOTIFICATION_SERVICE}/notifications/course"
    headers = {"X-User-ID": str(input.instructor_id)}

    payload = {
        "course_id": input.course_id,
        "course_title": input.course_title,
        "event": input.event,
        "affected_user_ids": input.affected_student_ids,
    }

    try:
        resp = await post_json(url, payload, headers=headers)
        return SendCoursePublishedNotificationOutput(
            success=resp.get("success", True),
            students_notified=len(input.affected_student_ids),
        )
    except Exception as e:
        logger.warning("send_course_published_notification failed: %s", e)
        return SendCoursePublishedNotificationOutput(success=False, error=str(e))


@activity.defn(name="send_instructor_course_published_notification")
async def send_instructor_course_published_notification(
    input: SendInstructorNotificationInput,
) -> SendInstructorNotificationOutput:
    """
    POST http://notification-service:8005/notifications/course
    Notifies the instructor their course is live (and whether RAG was indexed).
    """
    url = f"{NOTIFICATION_SERVICE}/notifications/course"
    headers = {"X-User-ID": str(input.instructor_id)}

    rag_note = (
        " Course content has been indexed for AI Tutor." if input.rag_indexed else ""
    )
    payload = {
        "course_id": input.course_id,
        "course_title": input.course_title,
        "event": "published",
        "message": f"Your course '{input.course_title}' is now live and available to students.{rag_note}",
        "affected_user_ids": [input.instructor_id],
    }

    try:
        resp = await post_json(url, payload, headers=headers)
        return SendInstructorNotificationOutput(success=resp.get("success", True))
    except Exception as e:
        logger.warning("send_instructor_course_published_notification failed: %s", e)
        return SendInstructorNotificationOutput(success=False, error=str(e))


NOTIFICATION_ACTIVITIES = [
    trigger_enrollment_notifications,
    send_in_app_notification,
    send_course_published_notification,
    send_instructor_course_published_notification,
]

__all__ = [
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
    "NOTIFICATION_ACTIVITIES",
]
