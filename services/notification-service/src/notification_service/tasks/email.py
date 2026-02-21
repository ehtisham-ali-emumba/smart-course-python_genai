from notification_service.mocks import MockEmailService
from notification_service.worker import celery_app

mock_email = MockEmailService()


@celery_app.task(
    bind=True,
    max_retries=3,
    name="notification_service.tasks.email.send_welcome_email",
)
def send_welcome_email(self, user_id: int, email: str, first_name: str):
    """Send welcome email after user registration.

    Retries up to 3 times with exponential backoff on failure.
    In production: replace mock with SMTP/SendGrid.
    """
    try:
        return mock_email.send(
            to=email,
            subject=f"Welcome to SmartCourse, {first_name}!",
            body=(
                f"Hi {first_name},\n\n"
                f"Welcome to SmartCourse! Your account has been created\n"
                f"successfully. Start exploring our course catalog.\n\n"
                f"-- The SmartCourse Team"
            ),
            email_type="WELCOME_EMAIL",
            metadata={"user_id": user_id},
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(
    bind=True,
    max_retries=3,
    name="notification_service.tasks.email.send_enrollment_confirmation",
)
def send_enrollment_confirmation(
    self, student_id: int, course_id: int, course_title: str, email: str
):
    try:
        return mock_email.send(
            to=email,
            subject=f"Enrollment Confirmed: {course_title}",
            body=(
                f"You're in!\n\n"
                f"You have successfully enrolled in '{course_title}'.\n"
                f"Head to your dashboard to start learning.\n\n"
                f"-- The SmartCourse Team"
            ),
            email_type="ENROLLMENT_CONFIRMATION",
            metadata={"student_id": student_id, "course_id": course_id},
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(
    bind=True,
    max_retries=3,
    name="notification_service.tasks.email.send_course_completion_email",
)
def send_course_completion_email(
    self, student_id: int, course_id: int, course_title: str, email: str
):
    try:
        return mock_email.send(
            to=email,
            subject=f"Congratulations! You completed {course_title}",
            body=(
                f"Amazing work!\n\n"
                f"You've completed all modules in '{course_title}'.\n"
                f"Your certificate is being generated.\n\n"
                f"-- The SmartCourse Team"
            ),
            email_type="COURSE_COMPLETION",
            metadata={"student_id": student_id, "course_id": course_id},
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(
    bind=True,
    max_retries=3,
    name="notification_service.tasks.email.send_certificate_ready_email",
)
def send_certificate_ready_email(
    self,
    student_id: int,
    certificate_number: str,
    verification_code: str,
    email: str,
):
    try:
        return mock_email.send(
            to=email,
            subject=f"Your Certificate is Ready! #{certificate_number}",
            body=(
                f"Your certificate has been issued!\n\n"
                f"Certificate:    {certificate_number}\n"
                f"Verification:   {verification_code}\n\n"
                f"Download it from your profile.\n\n"
                f"-- The SmartCourse Team"
            ),
            email_type="CERTIFICATE_READY",
            metadata={"student_id": student_id, "cert": certificate_number},
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
