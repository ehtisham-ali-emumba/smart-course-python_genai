import json
import logging
from typing import Any, Callable, Coroutine

from aiokafka import AIOKafkaConsumer

from core_service.events.envelope import EventEnvelope

logger = logging.getLogger(__name__)

EventHandler = Callable[[str, EventEnvelope], Coroutine[Any, Any, None]]


class EventConsumer:
    """Async Kafka consumer that deserializes EventEnvelope messages.

    Usage:
        consumer = EventConsumer(
            topics=Topics.ALL,
            bootstrap_servers="kafka:29092",
            group_id="core-event-bridge",
        )
        await consumer.start(handler=my_handler_fn)
        await consumer.stop()
    """

    def __init__(self, topics: list[str], bootstrap_servers: str, group_id: str):
        self._topics = topics
        self._bootstrap_servers = bootstrap_servers
        self._group_id = group_id
        self._consumer: AIOKafkaConsumer | None = None
        self._running = False

    async def start(self, handler: EventHandler) -> None:
        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="earliest",
        )
        await self._consumer.start()
        self._running = True
        logger.info("Consumer started [group=%s, topics=%s]", self._group_id, self._topics)

        try:
            async for msg in self._consumer:
                if not self._running:
                    break
                try:
                    envelope = EventEnvelope(**msg.value)
                    await handler(msg.topic, envelope)
                except Exception:
                    logger.exception(
                        "Error processing message from %s offset %s",
                        msg.topic, msg.offset,
                    )
        finally:
            await self._consumer.stop()

    async def stop(self) -> None:
        self._running = False
