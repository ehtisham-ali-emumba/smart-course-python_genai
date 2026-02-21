from notification_service.mocks import MockCertificateGenerator
from notification_service.worker import celery_app

mock_certificate = MockCertificateGenerator()


@celery_app.task(
    bind=True,
    max_retries=3,
    name="notification_service.tasks.certificate.generate_certificate_pdf",
)
def generate_certificate_pdf(
    self,
    certificate_id: int,
    enrollment_id: int,
    student_name: str,
    course_title: str,
):
    """Generate a PDF certificate.

    In production: use WeasyPrint/ReportLab, upload to S3, store URL in DB.
    """
    try:
        return mock_certificate.generate(
            certificate_id=certificate_id,
            enrollment_id=enrollment_id,
            student_name=student_name,
            course_title=course_title,
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
