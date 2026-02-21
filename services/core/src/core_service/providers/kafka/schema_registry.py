import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class SchemaRegistryClient:
    """Lightweight JSON Schema Registry client using httpx.

    Responsibilities:
    - Register JSON schemas derived from Pydantic models
    - Validate that producers/consumers agree on payload shape
    - Cache schema IDs to avoid repeated HTTP calls

    This replaces the heavier confluent-kafka[schemaregistry] package.
    """

    def __init__(self, registry_url: str):
        self._url = registry_url.rstrip("/")
        self._schema_id_cache: dict[str, int] = {}

    async def register_schema(self, subject: str, schema: dict[str, Any]) -> int:
        """Register a JSON schema and return its ID.

        Schema Registry uses "subjects" to namespace schemas.
        Convention: <topic>-value (e.g., "user.events-value").
        """
        if subject in self._schema_id_cache:
            return self._schema_id_cache[subject]

        payload = {
            "schemaType": "JSON",
            "schema": json.dumps(schema),
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._url}/subjects/{subject}/versions",
                json=payload,
                headers={"Content-Type": "application/vnd.schemaregistry.v1+json"},
            )
            resp.raise_for_status()
            schema_id = resp.json()["id"]

        self._schema_id_cache[subject] = schema_id
        logger.info("Registered schema for %s (id=%d)", subject, schema_id)
        return schema_id

    async def get_latest_schema(self, subject: str) -> dict[str, Any]:
        """Fetch the latest schema for a subject."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._url}/subjects/{subject}/versions/latest"
            )
            resp.raise_for_status()
            return json.loads(resp.json()["schema"])
