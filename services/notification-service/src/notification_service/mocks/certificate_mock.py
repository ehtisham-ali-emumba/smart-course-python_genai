"""Mock PDF certificate generator — logs styled certificate cards."""

import sys
from datetime import datetime, timezone


class MockCertificateGenerator:
    """Simulated PDF certificate generator."""

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

        print(output, file=sys.stderr, flush=True)
        return {
            "status": "generated_mock",
            "certificate_id": certificate_id,
            "url": f"/certificates/{certificate_id}/download",
        }
