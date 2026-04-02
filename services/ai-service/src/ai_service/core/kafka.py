"""Kafka producer singleton for the AI service."""

from shared.kafka.producer import EventProducer

_producer: EventProducer | None = None


async def connect_kafka(bootstrap_servers: str, schema_registry_url: str) -> None:
    global _producer
    _producer = EventProducer(
        bootstrap_servers=bootstrap_servers,
        service_name="ai-service",
        schema_registry_url=schema_registry_url,
    )
    await _producer.start()


async def close_kafka() -> None:
    global _producer
    if _producer:
        await _producer.stop()
        _producer = None


def get_producer() -> EventProducer:
    if _producer is None:
        raise RuntimeError("Kafka producer not initialized. Check app startup.")
    return _producer
