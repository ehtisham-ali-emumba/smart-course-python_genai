from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from shared.kafka.topics import Topics

from analytics_service.consumers.base_consumer import BaseAnalyticsConsumer, Repos


class CourseEventConsumer(BaseAnalyticsConsumer):
    def __init__(self, session_factory, group_id: str, bootstrap_servers: str):
        super().__init__(
            session_factory=session_factory,
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            topic=Topics.COURSE.value,
        )

    async def handle_event(self, envelope, payload: dict[str, Any], repos: Repos) -> None:
        if envelope.event_type == "course.published":
            course_id = UUID(payload["course_id"])
            instructor_id_raw = payload.get("instructor_id")

            course = await repos.course.get_or_create(course_id)
            course.title = payload.get("title", course.title)
            course.category = payload.get("category")
            course.published_at = datetime.now(timezone.utc)

            if instructor_id_raw:
                instructor_id = UUID(instructor_id_raw)
                course.instructor_id = instructor_id
                inst = await repos.instructor.get_or_create(instructor_id)
                inst.total_courses += 1
                inst.published_courses += 1
