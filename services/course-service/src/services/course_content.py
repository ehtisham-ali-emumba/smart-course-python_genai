from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from core.cache import cache_delete, cache_get, cache_set
from repositories.course_content import CourseContentRepository
from schemas.course_content import (
    CourseContentCreate,
    LessonCreate,
    LessonUpdate,
    MediaResourceCreate,
    MediaResourceUpdate,
    ModuleCreate,
    ModuleUpdate,
)


# ── TTL Constants ─────────────────────────────────────────────────
CONTENT_TTL = 900  # 15 minutes — content rarely changes after publish


class CourseContentService:
    """Business logic for course content (MongoDB)."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.content_repo = CourseContentRepository(db)

    # ── READS (with cache) ────────────────────────────────────────

    async def get_content(self, course_id: int) -> dict[str, Any] | None:
        """Get full course content by course_id."""
        cache_key = f"course:content:{course_id}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        doc = await self.content_repo.get_by_course_id(course_id)
        if doc:
            doc.pop("_id", None)
            await cache_set(cache_key, doc, ttl=CONTENT_TTL)

        return doc

    # ── WRITES (with cache invalidation) ──────────────────────────

    async def create_or_update_content(
        self, course_id: int, data: CourseContentCreate
    ) -> dict[str, Any]:
        """Create or fully replace course content (upsert)."""
        content_data = data.model_dump()

        if data.metadata is None:
            total_modules = len(data.modules)
            total_lessons = sum(len(m.lessons) for m in data.modules)
            content_data["metadata"] = {
                "total_modules": total_modules,
                "total_lessons": total_lessons,
                "total_duration_hours": None,
                "tags": [],
            }

        doc = await self.content_repo.upsert(course_id, content_data)
        doc.pop("_id", None)

        await cache_delete(f"course:content:{course_id}")

        return doc

    async def add_module(self, course_id: int, data: ModuleCreate) -> dict[str, Any] | None:
        """Add a single module to existing course content."""
        module_data = data.model_dump()
        doc = await self.content_repo.add_module(course_id, module_data)
        if doc:
            doc.pop("_id", None)
            await cache_delete(f"course:content:{course_id}")
        return doc

    async def add_lesson(
        self, course_id: int, module_id: str, data: LessonCreate
    ) -> dict[str, Any] | None:
        """Add a single lesson to a specific module."""
        lesson_data = data.model_dump()
        doc = await self.content_repo.add_lesson_to_module(
            course_id, module_id, lesson_data
        )
        if doc:
            doc.pop("_id", None)
            await cache_delete(f"course:content:{course_id}")
        return doc

    async def update_module(
        self, course_id: int, module_id: str, data: ModuleUpdate
    ) -> dict[str, Any] | None:
        """Update a module in the course content."""
        update_data = data.model_dump(exclude_unset=True)
        doc = await self.content_repo.update_module(course_id, module_id, update_data)
        if doc:
            doc.pop("_id", None)
            await cache_delete(f"course:content:{course_id}")
        return doc

    async def update_lesson(
        self, course_id: int, module_id: str, lesson_id: str, data: LessonUpdate
    ) -> dict[str, Any] | None:
        """Update a lesson in a module."""
        update_data = data.model_dump(exclude_unset=True)
        doc = await self.content_repo.update_lesson(
            course_id, module_id, lesson_id, update_data
        )
        if doc:
            doc.pop("_id", None)
            await cache_delete(f"course:content:{course_id}")
        return doc

    async def delete_module(
        self, course_id: int, module_id: str
    ) -> dict[str, Any] | None:
        """Soft-delete a module (set is_active=false)."""
        doc = await self.content_repo.soft_delete_module(course_id, module_id)
        if doc:
            doc.pop("_id", None)
            await cache_delete(f"course:content:{course_id}")
        return doc

    async def delete_lesson(
        self, course_id: int, module_id: str, lesson_id: str
    ) -> dict[str, Any] | None:
        """Soft-delete a lesson (set is_active=false)."""
        doc = await self.content_repo.soft_delete_lesson(
            course_id, module_id, lesson_id
        )
        if doc:
            doc.pop("_id", None)
            await cache_delete(f"course:content:{course_id}")
        return doc

    async def add_resource(
        self, course_id: int, module_id: str, lesson_id: str, data: MediaResourceCreate
    ) -> dict[str, Any] | None:
        """Add a media resource to a lesson."""
        resource_data = data.model_dump()
        doc = await self.content_repo.add_resource_to_lesson(
            course_id, module_id, lesson_id, resource_data
        )
        if doc:
            doc.pop("_id", None)
            await cache_delete(f"course:content:{course_id}")
        return doc

    async def update_resource(
        self,
        course_id: int,
        module_id: str,
        lesson_id: str,
        resource_index: int,
        data: MediaResourceUpdate,
    ) -> dict[str, Any] | None:
        """Update a media resource in a lesson."""
        update_data = data.model_dump(exclude_unset=True)
        doc = await self.content_repo.update_resource_in_lesson(
            course_id, module_id, lesson_id, resource_index, update_data
        )
        if doc:
            doc.pop("_id", None)
            await cache_delete(f"course:content:{course_id}")
        return doc

    async def delete_resource(
        self, course_id: int, module_id: str, lesson_id: str, resource_index: int
    ) -> bool:
        """Delete a media resource from a lesson."""
        result = await self.content_repo.delete_resource_from_lesson(
            course_id, module_id, lesson_id, resource_index
        )
        if result:
            await cache_delete(f"course:content:{course_id}")
        return result

    async def delete_content(self, course_id: int) -> bool:
        """Delete all content for a course."""
        result = await self.content_repo.delete(course_id)
        await cache_delete(f"course:content:{course_id}")
        return result
