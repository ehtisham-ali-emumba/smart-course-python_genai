import asyncio

from analytics_service.config import settings
from analytics_service.consumers.ai_consumer import AIEventConsumer
from analytics_service.consumers.certificate_consumer import CertificateEventConsumer
from analytics_service.consumers.course_consumer import CourseEventConsumer
from analytics_service.consumers.enrollment_consumer import EnrollmentEventConsumer
from analytics_service.consumers.progress_consumer import ProgressEventConsumer
from analytics_service.consumers.user_consumer import UserEventConsumer


class ConsumerManager:
    def __init__(self, db_session_factory):
        self.consumers = [
            UserEventConsumer(
                db_session_factory,
                group_id="analytics-user",
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            ),
            CourseEventConsumer(
                db_session_factory,
                group_id="analytics-course",
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            ),
            EnrollmentEventConsumer(
                db_session_factory,
                group_id="analytics-enrollment",
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            ),
            ProgressEventConsumer(
                db_session_factory,
                group_id="analytics-progress",
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            ),
            AIEventConsumer(
                db_session_factory,
                group_id="analytics-ai",
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            ),
            CertificateEventConsumer(
                db_session_factory,
                group_id="analytics-certificate",
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            ),
        ]
        self.tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        self.tasks = [asyncio.create_task(consumer.run()) for consumer in self.consumers]

    async def stop(self) -> None:
        for consumer in self.consumers:
            await consumer.stop()
        for task in self.tasks:
            task.cancel()
