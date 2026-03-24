"""Generation status tracker using Redis."""

import json
import uuid as _uuid
from datetime import datetime, timezone

import structlog
from redis.asyncio import Redis

from ai_service.schemas.common import GenerationStatus

logger = structlog.get_logger(__name__)


# Keys expire after 1 hour — plenty of time for polling, no manual cleanup needed
_TTL_SECONDS = 3600


def _key(course_id: _uuid.UUID, module_id: str, content_type: str) -> str:
    """Build Redis key for generation status."""
    return f"generation_status:{course_id}:{module_id}:{content_type}"


class GenerationStatusTracker:
    """Tracks in-flight generation status in Redis."""

    def __init__(self, redis: Redis):
        self._redis = redis

    async def set_in_progress(
        self, course_id: _uuid.UUID, module_id: str, content_type: str
    ) -> None:
        """Mark a generation task as in-progress. Call this BEFORE starting LLM work."""
        key = _key(course_id, module_id, content_type)
        payload = json.dumps(
            {
                "status": GenerationStatus.IN_PROGRESS.value,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "completed_at": None,
                "error": None,
            }
        )
        logger.debug(
            "Setting generation status to in_progress",
            key=key,
            course_id=course_id,
            module_id=module_id,
            content_type=content_type,
        )
        await self._redis.set(key, payload, ex=_TTL_SECONDS)
        logger.debug(
            "Generation status set to in_progress in Redis",
            key=key,
            ttl_seconds=_TTL_SECONDS,
        )

    async def set_completed(self, course_id: _uuid.UUID, module_id: str, content_type: str) -> None:
        """Mark a generation task as completed. Call this AFTER successful save."""
        key = _key(course_id, module_id, content_type)
        payload = json.dumps(
            {
                "status": GenerationStatus.COMPLETED.value,
                "started_at": None,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error": None,
            }
        )
        logger.debug(
            "Setting generation status to completed",
            key=key,
            course_id=course_id,
            module_id=module_id,
            content_type=content_type,
        )
        await self._redis.set(key, payload, ex=_TTL_SECONDS)
        logger.debug(
            "Generation status set to completed in Redis",
            key=key,
            ttl_seconds=_TTL_SECONDS,
        )

    async def set_failed(
        self, course_id: _uuid.UUID, module_id: str, content_type: str, error: str
    ) -> None:
        """Mark a generation task as failed. Call this in the except block."""
        key = _key(course_id, module_id, content_type)
        truncated_error = error[:500]
        payload = json.dumps(
            {
                "status": GenerationStatus.FAILED.value,
                "started_at": None,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error": truncated_error,
            }
        )
        logger.warning(
            "Setting generation status to failed",
            key=key,
            course_id=course_id,
            module_id=module_id,
            content_type=content_type,
            error=truncated_error,
        )
        await self._redis.set(key, payload, ex=_TTL_SECONDS)
        logger.warning(
            "Generation status set to failed in Redis",
            key=key,
            ttl_seconds=_TTL_SECONDS,
        )

    async def get_status(
        self, course_id: _uuid.UUID, module_id: str, content_type: str
    ) -> dict | None:
        """Get current generation status. Returns parsed dict or None if no key exists."""
        key = _key(course_id, module_id, content_type)
        logger.debug(
            "Fetching generation status from Redis",
            key=key,
            course_id=course_id,
            module_id=module_id,
            content_type=content_type,
        )
        raw = await self._redis.get(key)
        if raw is None:
            logger.debug("No generation status found in Redis", key=key)
            return None
        status_data = json.loads(raw)
        logger.debug(
            "Generation status retrieved from Redis",
            key=key,
            status=status_data.get("status"),
        )
        return status_data

    async def is_running(self, course_id: _uuid.UUID, module_id: str, content_type: str) -> bool:
        """Return True when a task is currently in progress for this resource."""
        status_data = await self.get_status(course_id, module_id, content_type)
        if status_data is None:
            return False
        return status_data.get("status") == GenerationStatus.IN_PROGRESS.value
