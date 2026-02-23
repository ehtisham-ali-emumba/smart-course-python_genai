"""Event handlers for notification service."""

from shared.schemas.envelope import EventEnvelope

from notification_service.core.logging import get_logger
from notification_service.worker import celery_app

log = get_logger("event_handlers")


class NotificationEventHandlers:
    """Maps Kafka events to Celery tasks."""

    def __init__(self):
        self._handlers = {
            "user.registered": self._on_user_registered,
            "course.published": self._on_course_published,
            "enrollment.created": self._on_enrollment_created,
            "enrollment.completed": self._on_enrollment_completed,
            "certificate.issued": self._on_certificate_issued,
        }

    async def handle(self, topic: str, event: EventEnvelope):
        log.info(
            "notification_event_received",
            topic=topic,
            event_type=event.event_type,
            event_id=event.event_id,
        )
        handler = self._handlers.get(event.event_type)
        if handler:
            await handler(event)
            return

        log.warning(
            "notification_event_unhandled",
            topic=topic,
            event_type=event.event_type,
            event_id=event.event_id,
        )

    def _enqueue_task(
        self, *, event_type: str, task_name: str, queue: str, kwargs: dict
    ) -> None:
        task = celery_app.send_task(task_name, kwargs=kwargs, queue=queue)
        log.info(
            "celery_task_enqueued",
            event_type=event_type,
            task_name=task_name,
            task_id=task.id,
            queue=queue,
        )

    # ─────────────────────────────────────────────────────────────
    #  EVENT HANDLERS
    # ─────────────────────────────────────────────────────────────

    async def _on_user_registered(self, event: EventEnvelope):
        """User registered → 2 tasks"""
        p = event.payload

        # Task 1: Welcome email
        self._enqueue_task(
            event_type=event.event_type,
            task_name="notification_service.tasks.email.send_welcome_email",
            kwargs={
                "user_id": p["user_id"],
                "email": p["email"],
                "first_name": p["first_name"],
            },
            queue="email_queue",
        )

        # Task 2: In-app welcome notification
        self._enqueue_task(
            event_type=event.event_type,
            task_name="notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["user_id"],
                "title": "Welcome to SmartCourse!",
                "message": f"Hi {p['first_name']}! Start exploring courses.",
                "notification_type": "welcome",
            },
            queue="notification_queue",
        )

    async def _on_course_published(self, event: EventEnvelope):
        """Course published → 1 task (instructor notification)"""
        p = event.payload

        # Task: Notify instructor
        self._enqueue_task(
            event_type=event.event_type,
            task_name="notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["instructor_id"],
                "title": "Course Published!",
                "message": f"Your course '{p['title']}' is now live.",
                "notification_type": "course_published",
            },
            queue="notification_queue",
        )

    async def _on_enrollment_created(self, event: EventEnvelope):
        """Enrollment created → 2 tasks"""
        p = event.payload

        # Task 1: Confirmation email
        self._enqueue_task(
            event_type=event.event_type,
            task_name="notification_service.tasks.email.send_enrollment_confirmation",
            kwargs={
                "student_id": p["student_id"],
                "course_id": p["course_id"],
                "course_title": p["course_title"],
                "email": p["email"],
            },
            queue="email_queue",
        )

        # Task 2: In-app notification
        self._enqueue_task(
            event_type=event.event_type,
            task_name="notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["student_id"],
                "title": "Enrollment Confirmed!",
                "message": f"You're enrolled in '{p['course_title']}'.",
                "notification_type": "enrollment",
            },
            queue="notification_queue",
        )

    async def _on_enrollment_completed(self, event: EventEnvelope):
        """Enrollment completed → 2 tasks"""
        p = event.payload
        course_title = p.get("course_title") or "your course"
        email = p.get("email") or ""

        # Task 1: Completion email
        self._enqueue_task(
            event_type=event.event_type,
            task_name="notification_service.tasks.email.send_course_completion_email",
            kwargs={
                "student_id": p["student_id"],
                "course_id": p["course_id"],
                "course_title": course_title,
                "email": email,
            },
            queue="email_queue",
        )

        # Task 2: In-app notification
        self._enqueue_task(
            event_type=event.event_type,
            task_name="notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["student_id"],
                "title": "Course Completed!",
                "message": f"Congratulations on completing '{course_title}'!",
                "notification_type": "completion",
            },
            queue="notification_queue",
        )

    async def _on_certificate_issued(self, event: EventEnvelope):
        """Certificate issued → 3 tasks"""
        p = event.payload
        student_email = p.get("email") or ""
        student_name = p.get("student_name") or "Student"
        course_title = p.get("course_title") or "Course"
        issued_date = p.get("issued_date") or ""
        instructor_name = p.get("instructor_name") or "Instructor"

        # Task 1: Certificate ready email
        self._enqueue_task(
            event_type=event.event_type,
            task_name="notification_service.tasks.email.send_certificate_ready_email",
            kwargs={
                "student_id": p["student_id"],
                "certificate_number": p["certificate_number"],
                "verification_code": p["verification_code"],
                "email": student_email,
            },
            queue="email_queue",
        )

        # Task 2: In-app notification
        self._enqueue_task(
            event_type=event.event_type,
            task_name="notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["student_id"],
                "title": "Certificate Ready!",
                "message": f"Your certificate #{p['certificate_number']} is ready.",
                "notification_type": "certificate",
            },
            queue="notification_queue",
        )

        # Task 3: Generate PDF
        self._enqueue_task(
            event_type=event.event_type,
            task_name="notification_service.tasks.certificate.generate_certificate_pdf",
            kwargs={
                "certificate_id": p["certificate_id"],
                "student_name": student_name,
                "course_title": course_title,
                "certificate_number": p["certificate_number"],
                "issued_date": issued_date,
                "instructor_name": instructor_name,
            },
            queue="certificate_queue",
        )
