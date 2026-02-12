from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.course_content import CourseContentRepository
from schemas.course_content import (
    CourseContentCreate,
    LessonCreate,
    ModuleCreate,
)


class CourseContentService:
    """Business logic for course content (MongoDB)."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.content_repo = CourseContentRepository(db)

    async def get_content(self, course_id: int) -> dict[str, Any] | None:
        """Get full course content by course_id."""
        doc = await self.content_repo.get_by_course_id(course_id)
        if doc:
            doc.pop("_id", None)  # Remove MongoDB ObjectId for serialization
        return doc

    async def create_or_update_content(
        self, course_id: int, data: CourseContentCreate
    ) -> dict[str, Any]:
        """Create or fully replace course content (upsert)."""
        content_data = data.model_dump()

        # Auto-calculate metadata if not provided
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
        return doc

    async def add_module(self, course_id: int, data: ModuleCreate) -> dict[str, Any] | None:
        """Add a single module to existing course content."""
        module_data = data.model_dump()
        doc = await self.content_repo.add_module(course_id, module_data)
        if doc:
            doc.pop("_id", None)
        return doc

    async def add_lesson(
        self, course_id: int, module_id: int, data: LessonCreate
    ) -> dict[str, Any] | None:
        """Add a single lesson to a specific module."""
        lesson_data = data.model_dump()
        doc = await self.content_repo.add_lesson_to_module(course_id, module_id, lesson_data)
        if doc:
            doc.pop("_id", None)
        return doc

    async def delete_content(self, course_id: int) -> bool:
        """Delete all content for a course."""
        return await self.content_repo.delete(course_id)
