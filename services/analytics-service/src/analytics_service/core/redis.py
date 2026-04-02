import redis.asyncio as redis
import structlog

logger = structlog.get_logger(__name__)

_redis_client: redis.Redis | None = None


async def connect_redis(redis_url: str) -> None:
    global _redis_client
    try:
        _redis_client = redis.from_url(
            redis_url,
            decode_responses=True,
            max_connections=20,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        await _redis_client.ping()
        logger.info("redis_connected", url=redis_url.split("@")[-1])
    except Exception as exc:
        logger.warning("redis_connection_failed", error=str(exc))
        _redis_client = None


async def close_redis() -> None:
    global _redis_client
    if _redis_client:
        await _redis_client.close()


def get_redis() -> redis.Redis | None:
    return _redis_client
