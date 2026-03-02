from typing import cast

from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorDatabase,
)

from config import settings

# Global client instance (initialized on startup, closed on shutdown)
_client: AsyncIOMotorClient | None = None
_database: AsyncIOMotorDatabase | None = None


async def connect_mongodb() -> None:
    """Initialize MongoDB connection. Call on app startup."""
    global _client, _database
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    database = client[settings.MONGODB_DB_NAME]

    _client = client
    _database = database

    # Create indexes on first connect
    await database["course_content"].create_index("course_id", unique=True)
    await database["course_content"].create_index("updated_at")

    await database["module_quizzes"].create_index(
        [("course_id", 1), ("module_id", 1)],
        unique=True,
    )
    await database["module_quizzes"].create_index("course_id")

    await database["module_summaries"].create_index(
        [("course_id", 1), ("module_id", 1)],
        unique=True,
    )
    await database["module_summaries"].create_index("course_id")


async def close_mongodb() -> None:
    """Close MongoDB connection. Call on app shutdown."""
    global _client
    if _client:
        _client.close()


def get_mongodb() -> AsyncIOMotorDatabase:
    """Get MongoDB database instance. Used as FastAPI dependency."""
    if _database is None:
        raise RuntimeError("MongoDB not initialized. Call connect_mongodb() first.")
    return cast(AsyncIOMotorDatabase, _database)
