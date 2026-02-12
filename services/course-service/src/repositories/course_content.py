from datetime import datetime
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument


class CourseContentRepository:
    """Course content repository for MongoDB operations."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db["course_content"]

    async def get_by_course_id(self, course_id: int) -> Optional[dict[str, Any]]:
        """Get course content document by course_id."""
        return await self.collection.find_one({"course_id": course_id})

    async def create(self, course_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new course content document."""
        now = datetime.utcnow()
        document = {
            "course_id": course_id,
            "modules": data.get("modules", []),
            "metadata": data.get("metadata", {}),
            "created_at": now,
            "updated_at": now,
        }
        result = await self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    async def update(self, course_id: int, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Replace course content for a given course_id."""
        now = datetime.utcnow()
        update_data = {
            "modules": data.get("modules", []),
            "metadata": data.get("metadata", {}),
            "updated_at": now,
        }
        result = await self.collection.find_one_and_update(
            {"course_id": course_id},
            {"$set": update_data},
            return_document=ReturnDocument.AFTER,
        )
        return result

    async def upsert(self, course_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Create or update course content (upsert)."""
        now = datetime.utcnow()
        update_data = {
            "modules": data.get("modules", []),
            "metadata": data.get("metadata", {}),
            "updated_at": now,
        }
        result = await self.collection.find_one_and_update(
            {"course_id": course_id},
            {
                "$set": update_data,
                "$setOnInsert": {"course_id": course_id, "created_at": now},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return result

    async def delete(self, course_id: int) -> bool:
        """Delete course content document."""
        result = await self.collection.delete_one({"course_id": course_id})
        return result.deleted_count > 0

    async def add_module(self, course_id: int, module: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Add a module to course content."""
        result = await self.collection.find_one_and_update(
            {"course_id": course_id},
            {
                "$push": {"modules": module},
                "$set": {"updated_at": datetime.utcnow()},
            },
            return_document=ReturnDocument.AFTER,
        )
        return result

    async def add_lesson_to_module(
        self, course_id: int, module_id: int, lesson: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Add a lesson to a specific module."""
        result = await self.collection.find_one_and_update(
            {"course_id": course_id, "modules.module_id": module_id},
            {
                "$push": {"modules.$.lessons": lesson},
                "$set": {"updated_at": datetime.utcnow()},
            },
            return_document=ReturnDocument.AFTER,
        )
        return result
