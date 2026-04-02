from shared.kafka.topics import Topics

from analytics_service.consumers.base_consumer import BaseAnalyticsConsumer


class CertificateEventConsumer(BaseAnalyticsConsumer):
    def __init__(self, session_factory, group_id: str, bootstrap_servers: str):
        super().__init__(
            session_factory=session_factory,
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            topic=Topics.CERTIFICATE.value,
        )
