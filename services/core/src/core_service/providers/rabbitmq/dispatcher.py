import logging

from celery import Celery

from core_service.config import core_settings

logger = logging.getLogger(__name__)


class CeleryDispatcher:
    """Dispatches Celery tasks by name via send_task().

    Services that need to trigger background work use this dispatcher
    instead of importing task functions directly. This keeps services
    decoupled from the worker implementation.

    Usage (from event bridge or API endpoints):
        dispatcher = CeleryDispatcher()
        dispatcher.send_welcome_email(user_id=1, email="a@b.com", first_name="Ali")
    """

    def __init__(self) -> None:
        self._app = Celery(broker=core_settings.RABBITMQ_URL)

    # ── Email Tasks ──────────────────────────────────────────

    def send_welcome_email(self, user_id: int, email: str, first_name: str) -> None:
        self._app.send_task(
            "core_service.tasks.email_tasks.send_welcome_email",
            kwargs={"user_id": user_id, "email": email, "first_name": first_name},
            queue="email_queue",
        )
        logger.info("Dispatched send_welcome_email for user_id=%s", user_id)

    def send_enrollment_confirmation(
        self, student_id: int, course_id: int, course_title: str, email: str
    ) -> None:
        self._app.send_task(
            "core_service.tasks.email_tasks.send_enrollment_confirmation",
            kwargs={
                "student_id": student_id,
                "course_id": course_id,
                "course_title": course_title,
                "email": email,
            },
            queue="email_queue",
        )
        logger.info("Dispatched send_enrollment_confirmation for student_id=%s", student_id)

    def send_course_completion_email(
        self, student_id: int, course_id: int, course_title: str, email: str
    ) -> None:
        self._app.send_task(
            "core_service.tasks.email_tasks.send_course_completion_email",
            kwargs={
                "student_id": student_id,
                "course_id": course_id,
                "course_title": course_title,
                "email": email,
            },
            queue="email_queue",
        )
        logger.info("Dispatched send_course_completion_email for student_id=%s", student_id)

    def send_certificate_ready_email(
        self, student_id: int, certificate_number: str, verification_code: str, email: str
    ) -> None:
        self._app.send_task(
            "core_service.tasks.email_tasks.send_certificate_ready_email",
            kwargs={
                "student_id": student_id,
                "certificate_number": certificate_number,
                "verification_code": verification_code,
                "email": email,
            },
            queue="email_queue",
        )
        logger.info("Dispatched send_certificate_ready_email for student_id=%s", student_id)

    def send_course_published_email(
        self, instructor_id: int, course_id: int, course_title: str
    ) -> None:
        self._app.send_task(
            "core_service.tasks.email_tasks.send_course_published_email",
            kwargs={
                "instructor_id": instructor_id,
                "course_id": course_id,
                "course_title": course_title,
            },
            queue="email_queue",
        )
        logger.info("Dispatched send_course_published_email for instructor_id=%s", instructor_id)

    # In-app notifications and certificate PDF generation moved to
    # notification-service (Kafka consumer, fire-and-forget)
