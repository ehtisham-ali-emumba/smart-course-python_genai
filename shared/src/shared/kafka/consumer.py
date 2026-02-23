"""Kafka event consumer for SmartCourse."""

import json
from collections.abc import Awaitable, Callable
from enum import Enum

from aiokafka import AIOKafkaConsumer

from shared.schemas.envelope import EventEnvelope


class EventConsumer:
    """Kafka event consumer."""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topics: list[str] | None = None,
    ):
        self._topics = [self._topic_name(topic) for topic in (topics or [])]
        self.consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            auto_offset_reset="earliest",
        )
        self.handlers: dict[str, Callable[[EventEnvelope], Awaitable[None]]] = {}

    @staticmethod
    def _topic_name(topic: str | Enum) -> str:
        return str(topic.value if isinstance(topic, Enum) else topic)

    def subscribe(self, topics: list[str]):
        """Subscribe to topics."""
        self._topics = [self._topic_name(topic) for topic in topics]
        self.consumer.subscribe(self._topics)

    def add_handler(self, event_type: str, handler: Callable[[EventEnvelope], Awaitable[None]]):
        """Add event handler."""
        self.handlers[event_type] = handler

    async def start(
        self,
        handler: Callable[[str, EventEnvelope], Awaitable[None]] | None = None,
    ):
        """Start consuming.

        Supports two modes:
        - `start(handler=...)`: per-message callback with (topic, envelope)
        - `add_handler(...)` + `start()`: dispatch by `event_type`
        """
        await self.consumer.start()
        try:
            async for message in self.consumer:
                envelope_data = message.value
                envelope = EventEnvelope(**envelope_data)
                if handler:
                    await handler(message.topic, envelope)
                    continue

                event_handler = self.handlers.get(envelope.event_type)
                if event_handler:
                    await event_handler(envelope)
        finally:
            await self.consumer.stop()
