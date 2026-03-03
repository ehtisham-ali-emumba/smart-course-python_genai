"""MongoDB connection module."""

import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

_mongodb_client: AsyncIOMotorClient | None = None
_mongodb: AsyncIOMotorDatabase | None = None


async def connect_mongodb(url: str, db_name: str) -> None:
    """Initialize MongoDB connection."""
    global _mongodb_client, _mongodb
    try:
        _mongodb_client = AsyncIOMotorClient(url)
        _mongodb = _mongodb_client[db_name]
        # Verify connection
        await _mongodb_client.admin.command("ping")
        logger.info("Connected to MongoDB")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise


async def close_mongodb() -> None:
    """Close MongoDB connection."""
    global _mongodb_client
    if _mongodb_client:
        _mongodb_client.close()
        logger.info("Closed MongoDB connection")


def get_mongodb() -> AsyncIOMotorDatabase | None:
    """Get MongoDB database instance."""
    return _mongodb
