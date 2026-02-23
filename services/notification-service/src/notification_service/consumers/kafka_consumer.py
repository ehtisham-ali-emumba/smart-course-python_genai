"""Background Kafka consumer for notification and certificate events."""

import asyncio
import sys

from shared.kafka.consumer import EventConsumer
from shared.kafka.topics import Topics

from notification_service.config import settings
from notification_service.consumers.event_handlers import NotificationEventHandlers

MAX_RETRY_DELAY = 30


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


async def run_notification_consumer() -> None:
    handlers = NotificationEventHandlers()
    topics = [Topics.USER, Topics.COURSE, Topics.ENROLLMENT]
    attempt = 0

    _log(
        f"[notification-service] Kafka consumer starting | topics={topics} broker={settings.KAFKA_BOOTSTRAP_SERVERS}"
    )

    while True:
        consumer = EventConsumer(
            topics=topics,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id="notification-service",
        )
        try:
            await consumer.start(handler=handlers.handle)
        except asyncio.CancelledError:
            _log("[notification-service] Consumer shutting down.")
            raise
        except Exception as e:
            attempt += 1
            delay = min(2**attempt, MAX_RETRY_DELAY)
            _log(
                f"[notification-service] Consumer error (attempt {attempt}), retry in {delay}s: {e!r}"
            )
            await asyncio.sleep(delay)
        else:
            break
