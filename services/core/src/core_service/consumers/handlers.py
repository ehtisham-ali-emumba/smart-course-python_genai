import logging
from typing import Any

from core_service.events.envelope import EventEnvelope
from core_service.providers.rabbitmq.dispatcher import CeleryDispatcher

logger = logging.getLogger(__name__)


class EventHandlerRegistry:
    """Routes Kafka events to appropriate Celery task dispatches.

    Each handler method receives the event envelope and dispatches
    zero or more Celery tasks via the CeleryDispatcher.
    """

    def __init__(self) -> None:
        self.dispatcher = CeleryDispatcher()
        self._handlers: dict[str, Any] = {
            "user.registered": self._on_user_registered,
            "user.login": self._on_user_login,
            "user.profile_updated": self._on_user_profile_updated,
            "course.created": self._on_course_created,
            "course.published": self._on_course_published,
            "course.updated": self._on_course_updated,
            "course.archived": self._on_course_archived,
            "enrollment.created": self._on_enrollment_created,
            "enrollment.dropped": self._on_enrollment_dropped,
            "enrollment.completed": self._on_enrollment_completed,
            "certificate.issued": self._on_certificate_issued,
            "certificate.revoked": self._on_certificate_revoked,
            "progress.updated": self._on_progress_updated,
            "progress.course_completed": self._on_progress_course_completed,
        }

    async def handle(self, topic: str, event: EventEnvelope) -> None:
        handler = self._handlers.get(event.event_type)
        if handler:
            logger.info(
                "Handling %s from %s (event_id=%s)",
                event.event_type, topic, event.event_id,
            )
            await handler(event)
        else:
            logger.debug("No handler for event_type=%s", event.event_type)

    # ── User Events ──────────────────────────────────────────

    async def _on_user_registered(self, event: EventEnvelope) -> None:
        p = event.payload
        self.dispatcher.send_welcome_email(
            user_id=p["user_id"],
            email=p["email"],
            first_name=p.get("first_name", ""),
        )
        self.dispatcher.create_in_app_notification(
            user_id=p["user_id"],
            title="Welcome to SmartCourse!",
            message=f"Hi {p.get('first_name', '')}! Start exploring courses and begin your learning journey.",
            notification_type="welcome",
        )

    async def _on_user_login(self, event: EventEnvelope) -> None:
        # Analytics-only — no tasks dispatched (Week 4)
        logger.info("User login tracked: user_id=%s", event.payload.get("user_id"))

    async def _on_user_profile_updated(self, event: EventEnvelope) -> None:
        # Analytics-only — no tasks dispatched (Week 4)
        logger.info("Profile update tracked: user_id=%s", event.payload.get("user_id"))

    # ── Course Events ────────────────────────────────────────

    async def _on_course_created(self, event: EventEnvelope) -> None:
        # Analytics-only (Week 4)
        logger.info("Course created tracked: course_id=%s", event.payload.get("course_id"))

    async def _on_course_published(self, event: EventEnvelope) -> None:
        p = event.payload
        self.dispatcher.send_course_published_email(
            instructor_id=p["instructor_id"],
            course_id=p["course_id"],
            course_title=p.get("title", ""),
        )
        self.dispatcher.create_in_app_notification(
            user_id=p["instructor_id"],
            title="Course Published!",
            message=f"Your course '{p.get('title', '')}' is now live and available to students.",
            notification_type="course_published",
        )

    async def _on_course_updated(self, event: EventEnvelope) -> None:
        # Analytics-only (Week 4)
        logger.info("Course updated tracked: course_id=%s", event.payload.get("course_id"))

    async def _on_course_archived(self, event: EventEnvelope) -> None:
        p = event.payload
        self.dispatcher.create_in_app_notification(
            user_id=p["instructor_id"],
            title="Course Archived",
            message=f"Your course '{p.get('title', '')}' has been archived.",
            notification_type="course_archived",
        )

    # ── Enrollment Events ────────────────────────────────────

    async def _on_enrollment_created(self, event: EventEnvelope) -> None:
        p = event.payload
        self.dispatcher.send_enrollment_confirmation(
            student_id=p["student_id"],
            course_id=p["course_id"],
            course_title=p.get("course_title", "your course"),
            email=p.get("email", ""),
        )
        self.dispatcher.create_in_app_notification(
            user_id=p["student_id"],
            title="Enrollment Confirmed!",
            message=f"You're now enrolled in '{p.get('course_title', 'a course')}'. Start learning!",
            notification_type="enrollment",
        )

    async def _on_enrollment_dropped(self, event: EventEnvelope) -> None:
        p = event.payload
        self.dispatcher.create_in_app_notification(
            user_id=p["student_id"],
            title="Course Dropped",
            message="You've dropped a course. You can re-enroll anytime.",
            notification_type="enrollment",
        )

    async def _on_enrollment_completed(self, event: EventEnvelope) -> None:
        p = event.payload
        self.dispatcher.send_course_completion_email(
            student_id=p["student_id"],
            course_id=p["course_id"],
            course_title=p.get("course_title", "your course"),
            email=p.get("email", ""),
        )
        self.dispatcher.create_in_app_notification(
            user_id=p["student_id"],
            title="Course Completed!",
            message=f"Congratulations! You've completed '{p.get('course_title', 'a course')}'. Your certificate is being prepared.",
            notification_type="completion",
        )

    # ── Certificate Events ───────────────────────────────────

    async def _on_certificate_issued(self, event: EventEnvelope) -> None:
        p = event.payload
        self.dispatcher.send_certificate_ready_email(
            student_id=p["student_id"],
            certificate_number=p["certificate_number"],
            verification_code=p["verification_code"],
            email=p.get("email", ""),
        )
        self.dispatcher.generate_certificate_pdf(
            certificate_id=p["certificate_id"],
            enrollment_id=p["enrollment_id"],
            student_name=p.get("student_name", ""),
            course_title=p.get("course_title", ""),
        )
        self.dispatcher.create_in_app_notification(
            user_id=p["student_id"],
            title="Certificate Ready!",
            message=f"Your certificate #{p['certificate_number']} is ready. Download it from your profile.",
            notification_type="certificate",
        )

    async def _on_certificate_revoked(self, event: EventEnvelope) -> None:
        p = event.payload
        self.dispatcher.create_in_app_notification(
            user_id=p.get("student_id", 0),
            title="Certificate Revoked",
            message=f"Certificate for enrollment #{p['enrollment_id']} has been revoked. Reason: {p.get('reason', 'N/A')}",
            notification_type="certificate",
        )

    # ── Progress Events ──────────────────────────────────────

    async def _on_progress_updated(self, event: EventEnvelope) -> None:
        # Analytics-only (Week 4)
        logger.info(
            "Progress tracked: user_id=%s, item=%s/%s, pct=%s",
            event.payload.get("user_id"),
            event.payload.get("item_type"),
            event.payload.get("item_id"),
            event.payload.get("progress_percentage"),
        )

    async def _on_progress_course_completed(self, event: EventEnvelope) -> None:
        # Fires enrollment.completed which handles tasks
        logger.info(
            "Course completed tracked: user_id=%s, enrollment_id=%s, course_id=%s",
            event.payload.get("user_id"),
            event.payload.get("enrollment_id"),
            event.payload.get("course_id"),
        )
