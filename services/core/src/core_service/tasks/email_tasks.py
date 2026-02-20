import logging
from datetime import datetime, timezone

from core_service.providers.rabbitmq.celery_app import celery_app

logger = logging.getLogger(__name__)


class MockEmailService:
    """Simulated email service that renders styled email previews to logs.

    In production, replace this class with a real provider:
    - SendGridEmailService
    - SESEmailService
    - SMTPEmailService

    The interface stays the same: .send(to, subject, body, email_type, metadata)
    """

    @staticmethod
    def send(
        to: str,
        subject: str,
        body: str,
        email_type: str,
        metadata: dict | None = None,
    ) -> dict:
        meta = metadata or {}
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        body_lines = body.strip().split("\n")
        formatted_body = "\n".join(f"  │  {line:<56} │" for line in body_lines)

        output = f"""
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  SMARTCOURSE EMAIL SERVICE (MOCK)                    {timestamp}  ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃  To:       {to:<55} ┃
┃  Subject:  {subject:<55} ┃
┃  Type:     {email_type:<55} ┃
┃                                                                    ┃
┃  Body:                                                             ┃
┃  ┌──────────────────────────────────────────────────────────────┐  ┃
{formatted_body}
┃  └──────────────────────────────────────────────────────────────┘  ┃
┃                                                                    ┃
┃  Status:   DELIVERED (mock)                                        ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛"""

        print(output)
        logger.info(
            "Mock email sent | to=%s | type=%s | subject=%s",
            to, email_type, subject,
        )
        return {"status": "delivered_mock", "to": to, "type": email_type, **meta}


mock_email = MockEmailService()


# ── Task Definitions ─────────────────────────────────────────────


@celery_app.task(
    bind=True,
    max_retries=3,
    name="core_service.tasks.email_tasks.send_welcome_email",
)
def send_welcome_email(self, user_id: int, email: str, first_name: str):
    try:
        return mock_email.send(
            to=email,
            subject=f"Welcome to SmartCourse, {first_name}!",
            body=(
                f"Hi {first_name},\n"
                f"\n"
                f"Welcome to SmartCourse! Your account has been created\n"
                f"successfully. Start exploring our course catalog and begin\n"
                f"your learning journey today.\n"
                f"\n"
                f"-- The SmartCourse Team"
            ),
            email_type="WELCOME_EMAIL",
            metadata={"user_id": user_id},
        )
    except Exception as exc:
        self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(
    bind=True,
    max_retries=3,
    name="core_service.tasks.email_tasks.send_enrollment_confirmation",
)
def send_enrollment_confirmation(
    self, student_id: int, course_id: int, course_title: str, email: str
):
    try:
        return mock_email.send(
            to=email,
            subject=f"Enrollment Confirmed: {course_title}",
            body=(
                f"You're in!\n"
                f"\n"
                f"You have successfully enrolled in '{course_title}'.\n"
                f"Head over to your dashboard to start the first module.\n"
                f"\n"
                f"Happy learning!\n"
                f"-- The SmartCourse Team"
            ),
            email_type="ENROLLMENT_CONFIRMATION",
            metadata={"student_id": student_id, "course_id": course_id},
        )
    except Exception as exc:
        self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(
    bind=True,
    max_retries=3,
    name="core_service.tasks.email_tasks.send_course_completion_email",
)
def send_course_completion_email(
    self, student_id: int, course_id: int, course_title: str, email: str
):
    try:
        return mock_email.send(
            to=email,
            subject=f"Congratulations! You completed {course_title}",
            body=(
                f"Amazing work!\n"
                f"\n"
                f"You have completed all modules in '{course_title}'.\n"
                f"Your certificate is being generated and will be\n"
                f"available in your profile shortly.\n"
                f"\n"
                f"Keep up the great work!\n"
                f"-- The SmartCourse Team"
            ),
            email_type="COURSE_COMPLETION",
            metadata={"student_id": student_id, "course_id": course_id},
        )
    except Exception as exc:
        self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(
    bind=True,
    max_retries=3,
    name="core_service.tasks.email_tasks.send_certificate_ready_email",
)
def send_certificate_ready_email(
    self, student_id: int, certificate_number: str, verification_code: str, email: str
):
    try:
        return mock_email.send(
            to=email,
            subject=f"Your Certificate is Ready! #{certificate_number}",
            body=(
                f"Your certificate has been issued!\n"
                f"\n"
                f"Certificate:    {certificate_number}\n"
                f"Verification:   {verification_code}\n"
                f"\n"
                f"Download it from your profile or share the\n"
                f"verification code with employers.\n"
                f"\n"
                f"-- The SmartCourse Team"
            ),
            email_type="CERTIFICATE_READY",
            metadata={"student_id": student_id, "cert": certificate_number},
        )
    except Exception as exc:
        self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(
    bind=True,
    max_retries=3,
    name="core_service.tasks.email_tasks.send_course_published_email",
)
def send_course_published_email(
    self, instructor_id: int, course_id: int, course_title: str
):
    try:
        return mock_email.send(
            to=f"instructor-{instructor_id}@smartcourse.local",
            subject=f"Your Course is Live: {course_title}",
            body=(
                f"Great news!\n"
                f"\n"
                f"Your course '{course_title}' is now published\n"
                f"and available to students on the platform.\n"
                f"\n"
                f"Share the link and start building your audience.\n"
                f"\n"
                f"-- The SmartCourse Team"
            ),
            email_type="COURSE_PUBLISHED",
            metadata={"instructor_id": instructor_id, "course_id": course_id},
        )
    except Exception as exc:
        self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
