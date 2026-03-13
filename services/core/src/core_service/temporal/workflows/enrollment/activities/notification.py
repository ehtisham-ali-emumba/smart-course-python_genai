"""Real HTTP activities that call notification-service."""

import logging
from dataclasses import dataclass

from temporalio import activity

from core_service.config import core_settings
from core_service.temporal.common.http_client import post_json
from shared.temporal.constants import Activities

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


# ── Activities ─────────────────────────────────────────────────────────────────


@activity.defn(name=Activities.TRIGGER_ENROLLMENT_NOTIFICATIONS)
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


@activity.defn(name=Activities.SEND_IN_APP_NOTIFICATION)
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


NOTIFICATION_ACTIVITIES = [
    trigger_enrollment_notifications,
    send_in_app_notification,
]

__all__ = [
    "trigger_enrollment_notifications",
    "send_in_app_notification",
    "TriggerEnrollmentNotificationsInput",
    "TriggerEnrollmentNotificationsOutput",
    "SendInAppNotificationInput",
    "SendInAppNotificationOutput",
    "NOTIFICATION_ACTIVITIES",
]
