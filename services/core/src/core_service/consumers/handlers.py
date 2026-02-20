import logging
from typing import Any

from core_service.events.envelope import EventEnvelope

logger = logging.getLogger(__name__)


class EventHandlerRegistry:
    """Routes Kafka events — analytics/logging only.

    Email, notifications, and certificates handled by notification-service
    via Kafka (fire-and-forget). This bridge logs for analytics (Week 4).
    """

    def __init__(self) -> None:
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
        logger.info("User registered: user_id=%s", event.payload.get("user_id"))

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
        logger.info("Course published: course_id=%s", event.payload.get("course_id"))

    async def _on_course_updated(self, event: EventEnvelope) -> None:
        # Analytics-only (Week 4)
        logger.info("Course updated tracked: course_id=%s", event.payload.get("course_id"))

    async def _on_course_archived(self, event: EventEnvelope) -> None:
        # In-app notification handled by notification-service via Kafka
        logger.debug("Course archived: course_id=%s", event.payload.get("course_id"))

    # ── Enrollment Events ────────────────────────────────────

    async def _on_enrollment_created(self, event: EventEnvelope) -> None:
        logger.info("Enrollment created: enrollment_id=%s", event.payload.get("enrollment_id"))

    async def _on_enrollment_dropped(self, event: EventEnvelope) -> None:
        # In-app notification handled by notification-service via Kafka
        logger.debug("Enrollment dropped: student_id=%s", event.payload.get("student_id"))

    async def _on_enrollment_completed(self, event: EventEnvelope) -> None:
        logger.info("Enrollment completed: enrollment_id=%s", event.payload.get("enrollment_id"))

    # ── Certificate Events ───────────────────────────────────

    async def _on_certificate_issued(self, event: EventEnvelope) -> None:
        logger.info("Certificate issued: cert_id=%s", event.payload.get("certificate_id"))

    async def _on_certificate_revoked(self, event: EventEnvelope) -> None:
        # In-app notification handled by notification-service via Kafka
        logger.debug("Certificate revoked: enrollment_id=%s", event.payload.get("enrollment_id"))

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
