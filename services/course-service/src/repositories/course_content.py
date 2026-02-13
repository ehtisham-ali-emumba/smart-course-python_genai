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
        self, course_id: int, module_id: str, lesson: dict[str, Any]
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

    async def update_module(
        self, course_id: int, module_id: str, update_data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Update a module's fields."""
        set_fields = {f"modules.$.{k}": v for k, v in update_data.items()}
        set_fields["updated_at"] = datetime.utcnow()

        result = await self.collection.find_one_and_update(
            {"course_id": course_id, "modules.module_id": module_id},
            {"$set": set_fields},
            return_document=ReturnDocument.AFTER,
        )
        return result

    async def update_lesson(
        self, course_id: int, module_id: str, lesson_id: str, update_data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Update a lesson's fields within a module."""
        doc = await self.collection.find_one({"course_id": course_id})
        if not doc:
            return None

        module_idx = None
        lesson_idx = None
        for m_idx, module in enumerate(doc.get("modules", [])):
            if module.get("module_id") == module_id:
                module_idx = m_idx
                for l_idx, lesson in enumerate(module.get("lessons", [])):
                    if lesson.get("lesson_id") == lesson_id:
                        lesson_idx = l_idx
                        break
                break

        if module_idx is None or lesson_idx is None:
            return None

        set_fields = {
            f"modules.{module_idx}.lessons.{lesson_idx}.{k}": v
            for k, v in update_data.items()
        }
        set_fields["updated_at"] = datetime.utcnow()

        result = await self.collection.find_one_and_update(
            {"course_id": course_id},
            {"$set": set_fields},
            return_document=ReturnDocument.AFTER,
        )
        return result

    async def soft_delete_module(
        self, course_id: int, module_id: str
    ) -> Optional[dict[str, Any]]:
        """Soft-delete a module (set is_active=false)."""
        return await self.update_module(course_id, module_id, {"is_active": False})

    async def soft_delete_lesson(
        self, course_id: int, module_id: str, lesson_id: str
    ) -> Optional[dict[str, Any]]:
        """Soft-delete a lesson (set is_active=false)."""
        return await self.update_lesson(course_id, module_id, lesson_id, {"is_active": False})

    async def add_resource_to_lesson(
        self, course_id: int, module_id: str, lesson_id: str, resource: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Add a resource to a lesson."""
        doc = await self.collection.find_one({"course_id": course_id})
        if not doc:
            return None

        module_idx = None
        lesson_idx = None
        for m_idx, module in enumerate(doc.get("modules", [])):
            if module.get("module_id") == module_id:
                module_idx = m_idx
                for l_idx, lesson in enumerate(module.get("lessons", [])):
                    if lesson.get("lesson_id") == lesson_id:
                        lesson_idx = l_idx
                        break
                break

        if module_idx is None or lesson_idx is None:
            return None

        result = await self.collection.find_one_and_update(
            {"course_id": course_id},
            {
                "$push": {f"modules.{module_idx}.lessons.{lesson_idx}.resources": resource},
                "$set": {"updated_at": datetime.utcnow()},
            },
            return_document=ReturnDocument.AFTER,
        )
        return result

    async def update_resource_in_lesson(
        self,
        course_id: int,
        module_id: str,
        lesson_id: str,
        resource_index: int,
        update_data: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Update a resource in a lesson by index."""
        doc = await self.collection.find_one({"course_id": course_id})
        if not doc:
            return None

        module_idx = None
        lesson_idx = None
        for m_idx, module in enumerate(doc.get("modules", [])):
            if module.get("module_id") == module_id:
                module_idx = m_idx
                for l_idx, lesson in enumerate(module.get("lessons", [])):
                    if lesson.get("lesson_id") == lesson_id:
                        lesson_idx = l_idx
                        resources = lesson.get("resources", [])
                        if resource_index >= len(resources):
                            return None
                        break
                break

        if module_idx is None or lesson_idx is None:
            return None

        set_fields = {
            f"modules.{module_idx}.lessons.{lesson_idx}.resources.{resource_index}.{k}": v
            for k, v in update_data.items()
        }
        set_fields["updated_at"] = datetime.utcnow()

        result = await self.collection.find_one_and_update(
            {"course_id": course_id},
            {"$set": set_fields},
            return_document=ReturnDocument.AFTER,
        )
        return result

    async def delete_resource_from_lesson(
        self, course_id: int, module_id: str, lesson_id: str, resource_index: int
    ) -> bool:
        """Delete a resource from a lesson by index."""
        doc = await self.collection.find_one({"course_id": course_id})
        if not doc:
            return False

        module_idx = None
        lesson_idx = None
        for m_idx, module in enumerate(doc.get("modules", [])):
            if module.get("module_id") == module_id:
                module_idx = m_idx
                for l_idx, lesson in enumerate(module.get("lessons", [])):
                    if lesson.get("lesson_id") == lesson_id:
                        lesson_idx = l_idx
                        resources = lesson.get("resources", [])
                        if resource_index >= len(resources):
                            return False
                        break
                break

        if module_idx is None or lesson_idx is None:
            return False

        resources = doc["modules"][module_idx]["lessons"][lesson_idx]["resources"]
        resources.pop(resource_index)

        result = await self.collection.update_one(
            {"course_id": course_id},
            {
                "$set": {
                    f"modules.{module_idx}.lessons.{lesson_idx}.resources": resources,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        return result.modified_count > 0
