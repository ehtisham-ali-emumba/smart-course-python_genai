"""
Cache utility functions.

Provides get/set/delete operations with JSON serialization.
All functions are fault-tolerant — if Redis is down, they return None
and the caller falls through to the database.
"""

import json
from typing import Any, Optional

import structlog

from user_service.core.redis import get_redis

logger = structlog.get_logger(__name__)


async def cache_get(key: str) -> Optional[Any]:
    """
    Get a value from cache.

    Returns:
        Deserialized Python object, or None on miss/error.
    """
    client = get_redis()
    if not client:
        return None

    try:
        data = await client.get(key)
        if data is not None:
            value = json.loads(data)
            logger.info("cache_hit", key=key, cached_value=value)  # TEST: log full Redis store on hit
            return value
        logger.debug("cache_miss", key=key)
        return None
    except Exception as e:
        logger.warning("cache_get_error", key=key, error=str(e))
        return None


async def cache_set(key: str, value: Any, ttl: int = 300) -> bool:
    """
    Set a value in cache with TTL.

    Args:
        key: Cache key.
        value: Any JSON-serializable Python object.
        ttl: Time-to-live in seconds (default: 5 minutes).

    Returns:
        True if stored successfully, False otherwise.
    """
    client = get_redis()
    if not client:
        return False

    try:
        serialized = json.dumps(value, default=str)  # default=str handles datetime, Decimal
        await client.set(key, serialized, ex=ttl)
        logger.debug("cache_set", key=key, ttl=ttl)
        return True
    except Exception as e:
        logger.warning("cache_set_error", key=key, error=str(e))
        return False


async def cache_delete(key: str) -> bool:
    """
    Delete a single key from cache.

    Returns:
        True if deleted, False otherwise.
    """
    client = get_redis()
    if not client:
        return False

    try:
        await client.delete(key)
        logger.debug("cache_delete", key=key)
        return True
    except Exception as e:
        logger.warning("cache_delete_error", key=key, error=str(e))
        return False


async def cache_delete_pattern(pattern: str) -> int:
    """
    Delete all keys matching a pattern using SCAN (non-blocking).

    Uses SCAN instead of KEYS to avoid blocking Redis on large datasets.
    Pattern examples: "course:published:*", "course:detail:*"

    Returns:
        Number of keys deleted.
    """
    client = get_redis()
    if not client:
        return 0

    try:
        deleted = 0
        async for key in client.scan_iter(match=pattern, count=100):
            await client.delete(key)
            deleted += 1
        if deleted > 0:
            logger.debug("cache_delete_pattern", pattern=pattern, deleted=deleted)
        return deleted
    except Exception as e:
        logger.warning("cache_delete_pattern_error", pattern=pattern, error=str(e))
        return 0


async def cache_exists(key: str) -> bool:
    """
    Check if a key exists in cache (without fetching the value).
    Useful for boolean flags like enrollment checks.

    Returns:
        True if key exists, False otherwise.
    """
    client = get_redis()
    if not client:
        return False

    try:
        return bool(await client.exists(key))
    except Exception as e:
        logger.warning("cache_exists_error", key=key, error=str(e))
        return False
