"""Kafka event handlers — dispatch work to Celery via RabbitMQ."""

import sys
from typing import Any

from celery import Celery
from core_service.events.envelope import EventEnvelope

from notification_service.config import settings


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


celery_app = Celery(broker=settings.RABBITMQ_URL)


class NotificationEventHandlers:
    """Receives Kafka events and dispatches Celery tasks to RabbitMQ.

    This is the bridge between Kafka (events) and RabbitMQ (tasks).
    The Kafka consumer tells us WHAT happened.
    We decide WHAT WORK to do and put it in the right queue.
    The Celery worker does the actual work.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Any] = {
            "user.registered": self._on_user_registered,
            "course.published": self._on_course_published,
            "course.archived": self._on_course_archived,
            "enrollment.created": self._on_enrollment_created,
            "enrollment.dropped": self._on_enrollment_dropped,
            "enrollment.completed": self._on_enrollment_completed,
            "certificate.issued": self._on_certificate_issued,
            "certificate.revoked": self._on_certificate_revoked,
        }

    async def handle(self, topic: str, event: EventEnvelope) -> None:
        handler = self._handlers.get(event.event_type)
        if handler:
            _log(f"[notification-service] {event.event_type} from {topic} (id={event.event_id})")
            await handler(event)

    # ── Dispatchers ──────────────────────────────────────────

    async def _on_user_registered(self, event: EventEnvelope) -> None:
        p = event.payload
        celery_app.send_task(
            "notification_service.tasks.email.send_welcome_email",
            kwargs={
                "user_id": p["user_id"],
                "email": p["email"],
                "first_name": p.get("first_name", ""),
            },
            queue="email_queue",
        )
        celery_app.send_task(
            "notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["user_id"],
                "title": "Welcome to SmartCourse!",
                "message": f"Hi {p.get('first_name', '')}! Start exploring courses.",
                "notification_type": "welcome",
            },
            queue="notification_queue",
        )
        _log(f"[dispatch] user.registered → email_queue + notification_queue")

    async def _on_course_published(self, event: EventEnvelope) -> None:
        p = event.payload
        celery_app.send_task(
            "notification_service.tasks.email.send_enrollment_confirmation",
            kwargs={
                "student_id": p["instructor_id"],
                "course_id": p["course_id"],
                "course_title": p.get("title", ""),
                "email": f"instructor-{p['instructor_id']}@smartcourse.local",
            },
            queue="email_queue",
        )
        celery_app.send_task(
            "notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["instructor_id"],
                "title": "Course Published!",
                "message": f"Your course '{p.get('title', '')}' is now live.",
                "notification_type": "course_published",
            },
            queue="notification_queue",
        )

    async def _on_course_archived(self, event: EventEnvelope) -> None:
        p = event.payload
        celery_app.send_task(
            "notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["instructor_id"],
                "title": "Course Archived",
                "message": f"Your course '{p.get('title', '')}' has been archived.",
                "notification_type": "course_archived",
            },
            queue="notification_queue",
        )

    async def _on_enrollment_created(self, event: EventEnvelope) -> None:
        p = event.payload
        email = p.get("email") or f"student-{p['student_id']}@smartcourse.local"
        celery_app.send_task(
            "notification_service.tasks.email.send_enrollment_confirmation",
            kwargs={
                "student_id": p["student_id"],
                "course_id": p["course_id"],
                "course_title": p.get("course_title", "your course"),
                "email": email,
            },
            queue="email_queue",
        )
        celery_app.send_task(
            "notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["student_id"],
                "title": "Enrollment Confirmed!",
                "message": f"You're enrolled in '{p.get('course_title', 'a course')}'.",
                "notification_type": "enrollment",
            },
            queue="notification_queue",
        )

    async def _on_enrollment_dropped(self, event: EventEnvelope) -> None:
        p = event.payload
        celery_app.send_task(
            "notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["student_id"],
                "title": "Course Dropped",
                "message": "You've dropped a course. You can re-enroll anytime.",
                "notification_type": "enrollment",
            },
            queue="notification_queue",
        )

    async def _on_enrollment_completed(self, event: EventEnvelope) -> None:
        p = event.payload
        email = p.get("email") or f"student-{p['student_id']}@smartcourse.local"
        celery_app.send_task(
            "notification_service.tasks.email.send_course_completion_email",
            kwargs={
                "student_id": p["student_id"],
                "course_id": p["course_id"],
                "course_title": p.get("course_title", "your course"),
                "email": email,
            },
            queue="email_queue",
        )
        celery_app.send_task(
            "notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["student_id"],
                "title": "Course Completed!",
                "message": f"Congratulations on completing '{p.get('course_title', 'a course')}'!",
                "notification_type": "completion",
            },
            queue="notification_queue",
        )

    async def _on_certificate_issued(self, event: EventEnvelope) -> None:
        p = event.payload
        email = p.get("email") or f"student-{p['student_id']}@smartcourse.local"

        # 3 tasks dispatched for certificate.issued
        celery_app.send_task(
            "notification_service.tasks.email.send_certificate_ready_email",
            kwargs={
                "student_id": p["student_id"],
                "certificate_number": p["certificate_number"],
                "verification_code": p["verification_code"],
                "email": email,
            },
            queue="email_queue",
        )
        celery_app.send_task(
            "notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["student_id"],
                "title": "Certificate Ready!",
                "message": f"Certificate #{p['certificate_number']} is ready to download.",
                "notification_type": "certificate",
            },
            queue="notification_queue",
        )
        celery_app.send_task(
            "notification_service.tasks.certificate.generate_certificate_pdf",
            kwargs={
                "certificate_id": p["certificate_id"],
                "enrollment_id": p["enrollment_id"],
                "student_name": p.get("student_name", ""),
                "course_title": p.get("course_title", ""),
            },
            queue="certificate_queue",
        )
        _log(f"[dispatch] certificate.issued → email_queue + notification_queue + certificate_queue")

    async def _on_certificate_revoked(self, event: EventEnvelope) -> None:
        p = event.payload
        celery_app.send_task(
            "notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p.get("student_id", 0),
                "title": "Certificate Revoked",
                "message": f"Certificate for enrollment #{p['enrollment_id']} revoked.",
                "notification_type": "certificate",
            },
            queue="notification_queue",
        )
