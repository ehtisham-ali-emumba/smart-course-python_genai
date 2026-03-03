"""Course content repository for reading from MongoDB."""

from motor.motor_asyncio import AsyncIOMotorDatabase


class CourseContentRepository:
    """Read-only access to course content in MongoDB."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.course_content = db["course_content"]
        self.module_quizzes = db["module_quizzes"]
        self.module_summaries = db["module_summaries"]

    async def get_course_content(self, course_id: int) -> dict | None:
        """Fetch the full course_content document for a course."""
        return await self.course_content.find_one({"course_id": course_id})

    async def get_module(self, course_id: int, module_id: str) -> dict | None:
        """Fetch a specific module from course_content."""
        doc = await self.course_content.find_one(
            {"course_id": course_id, "modules.module_id": module_id},
            {"modules.$": 1},
        )
        if doc and doc.get("modules"):
            return doc["modules"][0]
        return None

    async def get_lessons_for_module(
        self, course_id: int, module_id: str, lesson_ids: list[str] | None = None
    ) -> list[dict]:
        """Fetch lessons for a module, optionally filtered by lesson_ids."""
        module = await self.get_module(course_id, module_id)
        if not module:
            return []
        lessons = module.get("lessons", [])
        if lesson_ids:
            lessons = [l for l in lessons if l["lesson_id"] in lesson_ids]
        return lessons

    async def get_existing_quiz(self, course_id: int, module_id: str) -> dict | None:
        """Check if a quiz already exists for this module."""
        return await self.module_quizzes.find_one(
            {"course_id": course_id, "module_id": module_id, "is_active": True}
        )

    async def get_existing_summary(self, course_id: int, module_id: str) -> dict | None:
        """Check if a summary already exists for this module."""
        return await self.module_summaries.find_one(
            {"course_id": course_id, "module_id": module_id, "is_active": True}
        )

    async def get_module_with_lessons(
        self, course_id: int, module_id: str, lesson_ids: list[str] | None = None
    ) -> dict | None:
        """Build a structured context payload from module and its lessons for LLM processing.

        Args:
            course_id: Course ID
            module_id: Module ID
            lesson_ids: Optional list of lesson IDs to filter to specific lessons

        Returns:
            Dict with module_title, module_description, lessons list, and combined_text,
            or None if module not found.
        """
        module = await self.get_module(course_id, module_id)
        if not module:
            return None

        module_title = module.get("title", "")
        module_description = module.get("description", "")

        # Get lessons (optionally filtered)
        lessons = module.get("lessons", [])
        if lesson_ids:
            lessons = [l for l in lessons if l.get("lesson_id") in lesson_ids]

        # Build lesson entries with resources
        lesson_entries = []
        combined_parts = [f"## Module: {module_title}"]
        if module_description:
            combined_parts.append(module_description)

        for lesson in lessons:
            lesson_id = lesson.get("lesson_id", "")
            lesson_title = lesson.get("title", "")

            # Handle both dict and string formats for content
            content = lesson.get("content", {})
            if isinstance(content, str):
                text_content = content
            elif isinstance(content, dict):
                text_content = content.get("text_content", "")
            else:
                text_content = ""

            resources = lesson.get("resources", [])

            lesson_entries.append(
                {
                    "lesson_id": lesson_id,
                    "title": lesson_title,
                    "text_content": text_content,
                    "resources": resources,
                }
            )

            # Add to combined text
            combined_parts.append(f"### Lesson: {lesson_title}")
            if text_content:
                combined_parts.append(text_content)

        combined_text = "\n\n".join(combined_parts)

        return {
            "module_title": module_title,
            "module_description": module_description,
            "lessons": lesson_entries,
            "combined_text": combined_text,
        }
