from core_service.events.envelope import EventEnvelope


def get_envelope_schema() -> dict:
    """Generate JSON Schema from the EventEnvelope Pydantic model.

    This schema is what gets registered in Schema Registry.
    Every Kafka message must conform to this structure.
    """
    return EventEnvelope.model_json_schema()
