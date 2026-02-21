import json
import logging
from typing import Any

from aiokafka import AIOKafkaProducer

from core_service.events.envelope import EventEnvelope
from core_service.providers.kafka.schema_registry import SchemaRegistryClient
from core_service.providers.kafka.schema_utils import get_envelope_schema

logger = logging.getLogger(__name__)


class EventProducer:
    """Async Kafka producer with Schema Registry validation.

    On startup, registers the EventEnvelope JSON schema with Schema Registry.
    On each publish, the message is still validated by Pydantic (EventEnvelope),
    and Schema Registry ensures all consumers know the expected shape.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        service_name: str,
        schema_registry_url: str = "",
    ):
        self._bootstrap_servers = bootstrap_servers
        self._service_name = service_name
        self._producer: AIOKafkaProducer | None = None
        self._schema_registry: SchemaRegistryClient | None = None
        if schema_registry_url:
            self._schema_registry = SchemaRegistryClient(schema_registry_url)

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
        )
        await self._producer.start()
        logger.info("Kafka producer started for %s", self._service_name)

    async def _ensure_schema_registered(self, topic: str) -> None:
        """Register the EventEnvelope schema for this topic (once)."""
        if not self._schema_registry:
            return
        subject = f"{topic}-value"
        try:
            await self._schema_registry.register_schema(
                subject, get_envelope_schema()
            )
        except Exception:
            logger.warning("Schema registration failed for %s (non-fatal)", subject)

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

        await self._ensure_schema_registered(topic)

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
