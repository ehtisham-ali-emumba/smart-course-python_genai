from datetime import datetime
from typing import Any


class ModuleSummaryRepository:
    """MongoDB repository for module summary documents."""

    def __init__(self, db: Any):
        self.collection = db["module_summaries"]

    async def get_active_by_course_module(
        self, course_id: int, module_id: str
    ) -> dict[str, Any] | None:
        return await self.collection.find_one(
            {"course_id": course_id, "module_id": module_id, "is_active": True}
        )

    async def get_by_course_module(self, course_id: int, module_id: str) -> dict[str, Any] | None:
        return await self.collection.find_one({"course_id": course_id, "module_id": module_id})

    async def get_published_by_course_module(
        self, course_id: int, module_id: str
    ) -> dict[str, Any] | None:
        return await self.collection.find_one(
            {
                "course_id": course_id,
                "module_id": module_id,
                "is_active": True,
                "is_published": True,
            }
        )

    async def create(self, document: dict[str, Any]) -> dict[str, Any]:
        result = await self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    async def replace(
        self,
        course_id: int,
        module_id: str,
        document: dict[str, Any],
    ) -> dict[str, Any]:
        await self.collection.replace_one(
            {"course_id": course_id, "module_id": module_id},
            document,
            upsert=True,
        )
        return await self.collection.find_one({"course_id": course_id, "module_id": module_id})

    async def patch(
        self,
        course_id: int,
        module_id: str,
        update_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        update_data["updated_at"] = datetime.utcnow()
        await self.collection.update_one(
            {"course_id": course_id, "module_id": module_id, "is_active": True},
            {"$set": update_data},
        )
        return await self.collection.find_one(
            {"course_id": course_id, "module_id": module_id, "is_active": True}
        )

    async def soft_delete(self, course_id: int, module_id: str) -> bool:
        result = await self.collection.update_one(
            {"course_id": course_id, "module_id": module_id, "is_active": True},
            {"$set": {"is_active": False, "updated_at": datetime.utcnow()}},
        )
        return result.modified_count > 0
