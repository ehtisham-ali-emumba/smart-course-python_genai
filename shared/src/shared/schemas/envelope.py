"""Event envelope schema."""

from datetime import datetime
from typing import Any, Dict
from pydantic import BaseModel


class EventEnvelope(BaseModel):
    """Envelope for all events."""

    event_id: str
    event_type: str
    timestamp: datetime = None
    payload: Dict[str, Any]

    def __init__(self, **data):
        super().__init__(**data)
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
