"""Certificate Celery tasks for notification service."""

from notification_service.mocks import MockCertificateGenerator
from notification_service.worker import celery_app


@celery_app.task(
    bind=True, max_retries=3, name="notification_service.tasks.certificate.generate_certificate_pdf"
)
def generate_certificate_pdf(
    self,
    certificate_id: int,
    student_name: str,
    course_title: str,
    certificate_number: str,
    issued_date: str,
    instructor_name: str,
):
    """
    Triggered by: certificate.issued event
    Purpose: Generate a downloadable PDF certificate

    Steps:
    1. Load certificate template (HTML/Jinja2)
    2. Render with student/course data
    3. Convert to PDF (weasyprint/reportlab)
    4. Upload to S3/MinIO
    5. Update certificate record with PDF URL
    """
    try:
        result = MockCertificateGenerator.generate(
            certificate_id=certificate_id,
            # Current event payload doesn't include enrollment_id, so we mirror id for mock output.
            enrollment_id=certificate_id,
            student_name=student_name,
            course_title=course_title,
        )
        return {
            **result,
            "certificate_number": certificate_number,
            "issued_date": issued_date,
            "instructor_name": instructor_name,
        }

    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))
