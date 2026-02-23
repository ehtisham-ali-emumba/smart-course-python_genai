"""Kafka event producer for SmartCourse."""

import json
import uuid
from enum import Enum
from typing import Any

from aiokafka import AIOKafkaProducer

from shared.schemas.envelope import EventEnvelope


class EventProducer:
    """Kafka event producer."""

    def __init__(
        self,
        bootstrap_servers: str,
        service_name: str | None = None,
        schema_registry_url: str | None = None,
        **_: Any,
    ):
        # Accept optional args for compatibility with services using
        # the richer constructor signature.
        self.service_name = service_name
        self.schema_registry_url = schema_registry_url
        self.producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )

    async def start(self):
        """Start the producer."""
        await self.producer.start()

    async def stop(self):
        """Stop the producer."""
        await self.producer.stop()

    async def publish(
        self, topic: str | Enum, event_type: str, payload: dict[str, Any], key: str | None = None
    ):
        """Publish an event to Kafka."""
        envelope = EventEnvelope(
            event_id=str(uuid.uuid4()), event_type=event_type, payload=payload
        )
        message = envelope.model_dump(mode="json")
        await self.producer.send_and_wait(
            topic=str(topic.value if isinstance(topic, Enum) else topic),
            value=message,
            key=key.encode("utf-8") if key else None,
        )
