import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    """Standard event wrapper for all Kafka messages in SmartCourse.

    Every event published to Kafka follows this structure. Consumers
    deserialize the outer envelope, then use event_type to determine
    how to parse the payload dict.
    """

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    service: str
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    payload: dict[str, Any] = Field(default_factory=dict)
