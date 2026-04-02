import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from analytics_service.core.cache import delete_by_patterns
from analytics_service.core.redis import get_redis
from analytics_service.repositories import (
    AIUsageDailyRepository,
    CourseMetricsRepository,
    EnrollmentDailyRepository,
    InstructorMetricsRepository,
    ProcessedEventRepository,
    StudentMetricsRepository,
)
from shared.kafka.consumer import EventConsumer

logger = logging.getLogger(__name__)

CACHE_PATTERNS = [
    "analytics:courses:popular:*",
    "analytics:course:*",
    "analytics:instructor:*",
    "analytics:student:*",
]


class Repos:
    def __init__(self, session):
        self.course = CourseMetricsRepository(session)
        self.instructor = InstructorMetricsRepository(session)
        self.student = StudentMetricsRepository(session)
        self.enrollment_daily = EnrollmentDailyRepository(session)
        self.ai_daily = AIUsageDailyRepository(session)


class BaseAnalyticsConsumer:
    topic: str

    def __init__(
        self, session_factory: async_sessionmaker, group_id: str, bootstrap_servers: str, topic: str
    ):
        self.session_factory = session_factory
        self.topic = topic
        self.consumer = EventConsumer(
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            topics=[topic],
        )

    async def run(self) -> None:
        await self.consumer.start(handler=self.handle)

    async def stop(self) -> None:
        await self.consumer.consumer.stop()

    async def handle_event(self, envelope, payload: dict[str, Any], repos: Repos) -> None:
        raise NotImplementedError

    async def handle(self, topic: str, envelope) -> None:
        async with self.session_factory() as session:
            processed_repo = ProcessedEventRepository(session)
            marked = await processed_repo.mark_processed(
                event_id=envelope.event_id,
                topic=topic,
                event_type=envelope.event_type,
            )
            if not marked:
                return

            repos = Repos(session)
            payload: dict[str, Any] = envelope.payload or {}

            await self.handle_event(envelope, payload, repos)

            await session.commit()

            await delete_by_patterns(get_redis(), CACHE_PATTERNS)

            logger.info(
                "analytics_event_processed topic=%s event_type=%s",
                topic,
                envelope.event_type,
            )
