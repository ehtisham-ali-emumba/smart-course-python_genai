"""Kafka event handlers for email, in-app notifications, and certificate generation."""

import sys
from typing import Any

from core_service.events.envelope import EventEnvelope

from notification_service.mocks import (
    MockCertificateGenerator,
    MockEmailService,
    MockNotificationService,
)

mock_notification = MockNotificationService()
mock_certificate = MockCertificateGenerator()
mock_email = MockEmailService()


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


class NotificationEventHandlers:
    """Handles Kafka events for email, notifications, and certificate mocks."""

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

    async def _on_user_registered(self, event: EventEnvelope) -> None:
        p = event.payload
        mock_email.send(
            to=p["email"],
            subject=f"Welcome to SmartCourse, {p.get('first_name', '')}!",
            body=(
                f"Hi {p.get('first_name', '')},\n"
                f"\n"
                f"Welcome to SmartCourse! Your account has been created\n"
                f"successfully. Start exploring our course catalog and begin\n"
                f"your learning journey today.\n"
                f"\n"
                f"-- The SmartCourse Team"
            ),
            email_type="WELCOME_EMAIL",
            metadata={"user_id": p["user_id"]},
        )
        mock_notification.create(
            user_id=p["user_id"],
            title="Welcome to SmartCourse!",
            message=f"Hi {p.get('first_name', '')}! Start exploring courses and begin your learning journey.",
            notification_type="welcome",
        )

    async def _on_course_published(self, event: EventEnvelope) -> None:
        p = event.payload
        mock_email.send(
            to=f"instructor-{p['instructor_id']}@smartcourse.local",
            subject=f"Your Course is Live: {p.get('title', '')}",
            body=(
                f"Great news!\n"
                f"\n"
                f"Your course '{p.get('title', '')}' is now published\n"
                f"and available to students on the platform.\n"
                f"\n"
                f"Share the link and start building your audience.\n"
                f"\n"
                f"-- The SmartCourse Team"
            ),
            email_type="COURSE_PUBLISHED",
            metadata={"instructor_id": p["instructor_id"], "course_id": p["course_id"]},
        )
        mock_notification.create(
            user_id=p["instructor_id"],
            title="Course Published!",
            message=f"Your course '{p.get('title', '')}' is now live and available to students.",
            notification_type="course_published",
        )

    async def _on_course_archived(self, event: EventEnvelope) -> None:
        p = event.payload
        mock_notification.create(
            user_id=p["instructor_id"],
            title="Course Archived",
            message=f"Your course '{p.get('title', '')}' has been archived.",
            notification_type="course_archived",
        )

    async def _on_enrollment_created(self, event: EventEnvelope) -> None:
        p = event.payload
        email = p.get("email") or f"student-{p['student_id']}@smartcourse.local"
        mock_email.send(
            to=email,
            subject=f"Enrollment Confirmed: {p.get('course_title', 'your course')}",
            body=(
                f"You're in!\n"
                f"\n"
                f"You have successfully enrolled in '{p.get('course_title', 'your course')}'.\n"
                f"Head over to your dashboard to start the first module.\n"
                f"\n"
                f"Happy learning!\n"
                f"-- The SmartCourse Team"
            ),
            email_type="ENROLLMENT_CONFIRMATION",
            metadata={"student_id": p["student_id"], "course_id": p["course_id"]},
        )
        mock_notification.create(
            user_id=p["student_id"],
            title="Enrollment Confirmed!",
            message=f"You're now enrolled in '{p.get('course_title', 'a course')}'. Start learning!",
            notification_type="enrollment",
        )

    async def _on_enrollment_dropped(self, event: EventEnvelope) -> None:
        p = event.payload
        mock_notification.create(
            user_id=p["student_id"],
            title="Course Dropped",
            message="You've dropped a course. You can re-enroll anytime.",
            notification_type="enrollment",
        )

    async def _on_enrollment_completed(self, event: EventEnvelope) -> None:
        p = event.payload
        email = p.get("email") or f"student-{p['student_id']}@smartcourse.local"
        mock_email.send(
            to=email,
            subject=f"Congratulations! You completed {p.get('course_title', 'your course')}",
            body=(
                f"Amazing work!\n"
                f"\n"
                f"You have completed all modules in '{p.get('course_title', 'your course')}'.\n"
                f"Your certificate is being generated and will be\n"
                f"available in your profile shortly.\n"
                f"\n"
                f"Keep up the great work!\n"
                f"-- The SmartCourse Team"
            ),
            email_type="COURSE_COMPLETION",
            metadata={"student_id": p["student_id"], "course_id": p["course_id"]},
        )
        mock_notification.create(
            user_id=p["student_id"],
            title="Course Completed!",
            message=f"Congratulations! You've completed '{p.get('course_title', 'a course')}'. Your certificate is being prepared.",
            notification_type="completion",
        )

    async def _on_certificate_issued(self, event: EventEnvelope) -> None:
        p = event.payload
        email = p.get("email") or f"student-{p['student_id']}@smartcourse.local"
        mock_email.send(
            to=email,
            subject=f"Your Certificate is Ready! #{p['certificate_number']}",
            body=(
                f"Your certificate has been issued!\n"
                f"\n"
                f"Certificate:    {p['certificate_number']}\n"
                f"Verification:   {p['verification_code']}\n"
                f"\n"
                f"Download it from your profile or share the\n"
                f"verification code with employers.\n"
                f"\n"
                f"-- The SmartCourse Team"
            ),
            email_type="CERTIFICATE_READY",
            metadata={"student_id": p["student_id"], "cert": p["certificate_number"]},
        )
        mock_notification.create(
            user_id=p["student_id"],
            title="Certificate Ready!",
            message=f"Your certificate #{p['certificate_number']} is ready. Download it from your profile.",
            notification_type="certificate",
        )
        mock_certificate.generate(
            certificate_id=p["certificate_id"],
            enrollment_id=p["enrollment_id"],
            student_name=p.get("student_name", ""),
            course_title=p.get("course_title", ""),
        )

    async def _on_certificate_revoked(self, event: EventEnvelope) -> None:
        p = event.payload
        mock_notification.create(
            user_id=p.get("student_id", 0),
            title="Certificate Revoked",
            message=f"Certificate for enrollment #{p['enrollment_id']} has been revoked. Reason: {p.get('reason', 'N/A')}",
            notification_type="certificate",
        )
