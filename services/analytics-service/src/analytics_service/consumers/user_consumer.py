from typing import Any
from uuid import UUID

from shared.kafka.topics import Topics

from analytics_service.consumers.base_consumer import BaseAnalyticsConsumer, Repos


class UserEventConsumer(BaseAnalyticsConsumer):
    def __init__(self, session_factory, group_id: str, bootstrap_servers: str):
        super().__init__(
            session_factory=session_factory,
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            topic=Topics.USER.value,
        )

    async def handle_event(self, envelope, payload: dict[str, Any], repos: Repos) -> None:
        if envelope.event_type == "user.registered":
            role = payload.get("role")
            profile_id = payload.get("profile_id") or payload.get("user_id")
            if role == "instructor":
                if profile_id:
                    await repos.instructor.get_or_create(UUID(profile_id))
            else:
                if profile_id:
                    await repos.student.get_or_create(UUID(profile_id))
