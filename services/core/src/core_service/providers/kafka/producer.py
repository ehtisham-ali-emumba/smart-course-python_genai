import json
import logging
from typing import Any

from aiokafka import AIOKafkaProducer

from core_service.events.envelope import EventEnvelope

logger = logging.getLogger(__name__)


class EventProducer:
    """Async Kafka producer that wraps every message in a standard EventEnvelope.

    Lifecycle:
        producer = EventProducer(bootstrap_servers="kafka:29092", service_name="user-service")
        await producer.start()       # call in FastAPI lifespan startup
        await producer.publish(...)  # call from API endpoints
        await producer.stop()        # call in FastAPI lifespan shutdown
    """

    def __init__(self, bootstrap_servers: str, service_name: str):
        self._bootstrap_servers = bootstrap_servers
        self._service_name = service_name
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
        )
        await self._producer.start()
        logger.info("Kafka producer started for %s", self._service_name)

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()
            logger.info("Kafka producer stopped for %s", self._service_name)

    async def publish(
        self,
        topic: str,
        event_type: str,
        payload: dict[str, Any],
        key: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        if not self._producer:
            logger.warning("Producer not started — dropping event %s", event_type)
            return

        envelope = EventEnvelope(
            event_type=event_type,
            service=self._service_name,
            payload=payload,
        )
        if correlation_id:
            envelope.correlation_id = correlation_id

        await self._producer.send_and_wait(
            topic, value=envelope.model_dump(), key=key,
        )
        logger.info("Published %s to %s (key=%s)", event_type, topic, key)
