import asyncio
import logging

from core_service.config import core_settings
from core_service.consumers.handlers import EventHandlerRegistry
from core_service.providers.kafka.consumer import EventConsumer
from core_service.providers.kafka.topics import Topics

logger = logging.getLogger(__name__)

MAX_RETRY_DELAY = 30


async def run_event_bridge() -> None:
    """Main entry point for the Kafka → Celery event bridge.

    Retries indefinitely on connection failures with exponential backoff.
    """
    registry = EventHandlerRegistry()
    attempt = 0

    while True:
        consumer = EventConsumer(
            topics=Topics.ALL,
            bootstrap_servers=core_settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=core_settings.KAFKA_CONSUMER_GROUP,
        )
        try:
            logger.info("Starting event bridge consumer...")
            await consumer.start(handler=registry.handle)
        except Exception:
            attempt += 1
            delay = min(2 ** attempt, MAX_RETRY_DELAY)
            logger.exception(
                "Event bridge crashed (attempt %d), retrying in %ds...",
                attempt, delay,
            )
            await asyncio.sleep(delay)
        else:
            break


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_event_bridge())
