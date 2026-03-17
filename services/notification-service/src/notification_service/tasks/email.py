"""Email Celery tasks for notification service."""

from notification_service.mocks import MockEmailService
from notification_service.worker import celery_app


@celery_app.task(
    bind=True, max_retries=3, name="notification_service.tasks.email.send_welcome_email"
)
def send_welcome_email(self, user_id: str, email: str, first_name: str):
    """
    Triggered by: user.registered event
    Purpose: Send welcome email to new user
    Retry: 3 times with exponential backoff (60s, 120s, 240s)
    """
    try:
        return MockEmailService.send(
            to=email,
            subject=f"Welcome to SmartCourse, {first_name}!",
            body=(
                f"Hi {first_name},\n\n"
                "Welcome to SmartCourse.\n"
                "Your account is ready and you can start learning now."
            ),
            email_type="welcome",
            metadata={"user_id": user_id},
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@celery_app.task(
    bind=True, max_retries=3, name="notification_service.tasks.email.send_enrollment_confirmation"
)
def send_enrollment_confirmation(
    self, student_id: str, course_id: str, course_title: str, email: str
):
    """
    Triggered by: enrollment.created event
    Purpose: Confirm student's enrollment in a course
    """
    try:
        return MockEmailService.send(
            to=email,
            subject=f"Enrollment Confirmed: {course_title}",
            body=(
                f"You're successfully enrolled in '{course_title}'.\n\n"
                "Open your dashboard to start the course."
            ),
            email_type="enrollment_confirmation",
            metadata={"student_id": student_id, "course_id": course_id},
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@celery_app.task(
    bind=True, max_retries=3, name="notification_service.tasks.email.send_course_completion_email"
)
def send_course_completion_email(
    self, student_id: str, course_id: str, course_title: str, email: str
):
    """
    Triggered by: enrollment.completed event
    Purpose: Congratulate student on completing a course
    """
    try:
        return MockEmailService.send(
            to=email,
            subject=f"Congratulations! You completed {course_title}",
            body=(
                f"Great work completing '{course_title}'.\n\n" "Your achievement has been recorded."
            ),
            email_type="course_completion",
            metadata={"student_id": student_id, "course_id": course_id},
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@celery_app.task(
    bind=True, max_retries=3, name="notification_service.tasks.email.send_certificate_ready_email"
)
def send_certificate_ready_email(
    self, student_id: str, certificate_number: str, verification_code: str, email: str
):
    """
    Triggered by: certificate.issued event
    Purpose: Notify student their certificate is ready for download
    """
    try:
        return MockEmailService.send(
            to=email,
            subject=f"Your Certificate is Ready! #{certificate_number}",
            body=(
                f"Your certificate #{certificate_number} is ready.\n\n"
                f"Verification code: {verification_code}"
            ),
            email_type="certificate_ready",
            metadata={"student_id": student_id, "certificate_number": certificate_number},
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))
