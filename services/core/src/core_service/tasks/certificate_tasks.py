import logging
from datetime import datetime, timezone

from core_service.providers.rabbitmq.celery_app import celery_app

logger = logging.getLogger(__name__)


class MockCertificateGenerator:
    """Simulated PDF certificate generator.

    In production, replace with reportlab / weasyprint to generate
    a real PDF, then upload to S3/MinIO.
    """

    @staticmethod
    def generate(
        certificate_id: int,
        enrollment_id: int,
        student_name: str,
        course_title: str,
    ) -> dict:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        output = f"""
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  SMARTCOURSE CERTIFICATE GENERATOR (MOCK)          {timestamp}  ┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃                                                                    ┃
┃                  ~~~  CERTIFICATE OF COMPLETION  ~~~                ┃
┃                                                                    ┃
┃   This certifies that                                              ┃
┃                                                                    ┃
┃               {student_name:^48}     ┃
┃                                                                    ┃
┃   has successfully completed the course                            ┃
┃                                                                    ┃
┃               {course_title:^48}     ┃
┃                                                                    ┃
┃   Certificate ID:  {certificate_id:<47}┃
┃   Enrollment ID:   {enrollment_id:<47}┃
┃                                                                    ┃
┃   Status:  PDF GENERATED (mock -- would upload to S3)              ┃
┃                                                                    ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛"""

        print(output)
        logger.info(
            "Mock certificate PDF generated | cert_id=%d | student=%s | course=%s",
            certificate_id, student_name, course_title,
        )
        return {
            "status": "generated_mock",
            "certificate_id": certificate_id,
            "url": f"/certificates/{certificate_id}/download",
        }


mock_cert_gen = MockCertificateGenerator()


@celery_app.task(
    bind=True,
    max_retries=3,
    name="core_service.tasks.certificate_tasks.generate_certificate_pdf",
)
def generate_certificate_pdf(
    self,
    certificate_id: int,
    enrollment_id: int,
    student_name: str,
    course_title: str,
):
    try:
        return mock_cert_gen.generate(
            certificate_id=certificate_id,
            enrollment_id=enrollment_id,
            student_name=student_name,
            course_title=course_title,
        )
    except Exception as exc:
        self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
