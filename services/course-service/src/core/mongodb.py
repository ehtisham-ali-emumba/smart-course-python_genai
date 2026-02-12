from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from config import settings

# Global client instance (initialized on startup, closed on shutdown)
_client: AsyncIOMotorClient | None = None
_database: AsyncIOMotorDatabase | None = None


async def connect_mongodb() -> None:
    """Initialize MongoDB connection. Call on app startup."""
    global _client, _database
    _client = AsyncIOMotorClient(settings.MONGODB_URL)
    _database = _client[settings.MONGODB_DB_NAME]

    # Create indexes on first connect
    await _database.course_content.create_index("course_id", unique=True)
    await _database.course_content.create_index("updated_at")


async def close_mongodb() -> None:
    """Close MongoDB connection. Call on app shutdown."""
    global _client
    if _client:
        _client.close()


def get_mongodb() -> AsyncIOMotorDatabase:
    """Get MongoDB database instance. Used as FastAPI dependency."""
    if _database is None:
        raise RuntimeError("MongoDB not initialized. Call connect_mongodb() first.")
    return _database
