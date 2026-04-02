from typing import Any
from uuid import UUID

from shared.kafka.topics import Topics

from analytics_service.consumers.base_consumer import BaseAnalyticsConsumer, Repos


class CertificateEventConsumer(BaseAnalyticsConsumer):
    def __init__(self, session_factory, group_id: str, bootstrap_servers: str):
        super().__init__(
            session_factory=session_factory,
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            topic=Topics.CERTIFICATE.value,
        )

    async def handle_event(self, envelope, payload: dict[str, Any], repos: Repos) -> None:
        if envelope.event_type == "certificate.issued":
            student_id = UUID(payload["student_id"])
            student = await repos.student.get_or_create(student_id)
            student.total_certificates += 1
