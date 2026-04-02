from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from shared.kafka.topics import Topics

from analytics_service.consumers.base_consumer import BaseAnalyticsConsumer, Repos


class AIEventConsumer(BaseAnalyticsConsumer):
    def __init__(self, session_factory, group_id: str, bootstrap_servers: str):
        super().__init__(
            session_factory=session_factory,
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            topic=Topics.AI.value,
        )

    async def handle_event(self, envelope, payload: dict[str, Any], repos: Repos) -> None:
        if envelope.event_type not in {"ai.question.asked", "ai.content.generated"}:
            return

        now_date = datetime.now(timezone.utc).date()
        course_id_raw = payload.get("course_id")
        course_id = UUID(course_id_raw) if course_id_raw else None

        usage_platform = await repos.ai_daily.get_or_create(now_date, None)
        usage_course = (
            await repos.ai_daily.get_or_create(now_date, course_id) if course_id else None
        )

        usage_platform.total_questions += 1
        if usage_course:
            usage_course.total_questions += 1

        if envelope.event_type == "ai.question.asked":
            usage_platform.tutor_questions += 1
            if usage_course:
                usage_course.tutor_questions += 1
            if course_id:
                course = await repos.course.get_or_create(course_id)
                course.ai_questions_asked += 1
        else:
            usage_platform.instructor_requests += 1
            if usage_course:
                usage_course.instructor_requests += 1
