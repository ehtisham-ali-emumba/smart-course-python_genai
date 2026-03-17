"""Notification activities for course publish workflow."""

import logging
from dataclasses import dataclass

from temporalio import activity

from core_service.config import core_settings
from core_service.temporal.common.http_client import post_json
from shared.temporal.constants import Activities

logger = logging.getLogger(__name__)

NOTIFICATION_SERVICE = core_settings.NOTIFICATION_SERVICE_URL


def _instructor_auth_headers(instructor_id: str) -> dict[str, str]:
    return {
        "X-User-ID": str(instructor_id),
        "X-User-Role": "instructor",
    }


# ── Dataclasses ───────────────────────────────────────────────


@dataclass
class NotifyInstructorInput:
    instructor_id: str
    course_id: str
    course_title: str
    error_message: str = ""


@dataclass
class NotifyInstructorOutput:
    success: bool
    error: str = ""


# ── Activities ────────────────────────────────────────────────


@activity.defn(name=Activities.NOTIFY_INSTRUCTOR_PUBLISH_SUCCESS)
async def notify_instructor_publish_success(
    input: NotifyInstructorInput,
) -> NotifyInstructorOutput:
    """Notify instructor that their course has been published successfully.

    Calls notification-service /notifications/send which enqueues Celery tasks.
    """
    activity.logger.info(
        "notify_instructor_publish_success course_id=%s instructor_id=%s",
        input.course_id,
        input.instructor_id,
    )

    try:
        await post_json(
            f"{NOTIFICATION_SERVICE}/notifications/send",
            payload={
                "user_id": input.instructor_id,
                "type": "course_published",
                "channel": "in_app",
                "priority": "normal",
                "title": "Course Published!",
                "message": (
                    f"Your course '{input.course_title}' is now live "
                    f"and available to students."
                ),
            },
            headers=_instructor_auth_headers(input.instructor_id),
        )
        return NotifyInstructorOutput(success=True)

    except Exception as e:
        activity.logger.error("notify_instructor_publish_success failed: %s", e)
        return NotifyInstructorOutput(success=False, error=str(e))


@activity.defn(name=Activities.NOTIFY_INSTRUCTOR_PUBLISH_FAILURE)
async def notify_instructor_publish_failure(
    input: NotifyInstructorInput,
) -> NotifyInstructorOutput:
    """Notify instructor that course publishing failed."""
    activity.logger.info(
        "notify_instructor_publish_failure course_id=%s",
        input.course_id,
    )

    try:
        await post_json(
            f"{NOTIFICATION_SERVICE}/notifications/send",
            payload={
                "user_id": input.instructor_id,
                "type": "course_publish_failed",
                "channel": "in_app",
                "priority": "high",
                "title": "Course Publishing Failed",
                "message": (
                    f"Your course '{input.course_title}' could not be published. "
                    f"Reason: {input.error_message or 'Unknown error'}. "
                    f"Please try again or contact support."
                ),
            },
            headers=_instructor_auth_headers(input.instructor_id),
        )
        return NotifyInstructorOutput(success=True)

    except Exception as e:
        activity.logger.error("notify_instructor_publish_failure failed: %s", e)
        return NotifyInstructorOutput(success=False, error=str(e))


NOTIFICATION_ACTIVITIES = [
    notify_instructor_publish_success,
    notify_instructor_publish_failure,
]
