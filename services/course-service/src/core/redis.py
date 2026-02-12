"""
Redis client management.

Provides async Redis connection with connection pooling.
Initialize on app startup, close on shutdown.
If Redis is unavailable, the app continues to work (cache misses fall through to DB).
"""

import redis.asyncio as redis
import structlog

logger = structlog.get_logger(__name__)

# Global Redis client (initialized on startup)
_redis_client: redis.Redis | None = None


async def connect_redis(redis_url: str) -> None:
    """
    Initialize Redis connection pool. Call on app startup.

    Args:
        redis_url: Full Redis URL including database number.
                   e.g., redis://:password@redis:6379/0
    """
    global _redis_client
    try:
        _redis_client = redis.from_url(
            redis_url,
            decode_responses=True,   # Return strings, not bytes
            max_connections=10,      # Connection pool size
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        # Verify connection
        await _redis_client.ping()
        logger.info("redis_connected", url=redis_url.split("@")[-1])  # Log without password
    except Exception as e:
        logger.warning("redis_connection_failed", error=str(e))
        _redis_client = None  # App will work without cache


async def close_redis() -> None:
    """Close Redis connection pool. Call on app shutdown."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        logger.info("redis_disconnected")


def get_redis() -> redis.Redis | None:
    """
    Get Redis client instance.

    Returns None if Redis is not connected (graceful degradation).
    """
    return _redis_client
