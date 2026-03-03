"""Redis connection module."""

import logging
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_redis_client: Redis | None = None


async def connect_redis(url: str) -> None:
    """Initialize Redis connection."""
    global _redis_client
    try:
        _redis_client = await Redis.from_url(url)
        await _redis_client.ping()
        logger.info("Connected to Redis")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise


async def close_redis() -> None:
    """Close Redis connection."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        logger.info("Closed Redis connection")


def get_redis() -> Redis | None:
    """Get Redis client instance."""
    return _redis_client
