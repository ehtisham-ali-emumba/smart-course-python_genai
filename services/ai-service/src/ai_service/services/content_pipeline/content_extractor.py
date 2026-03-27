"""Centralized content extraction for course materials.
Responsible for:
    1. Fetching course/module/lesson data from MongoDB
    2. Combining inline text content with PDF-extracted text (provided via state)
    3. Building structured output for downstream LLM or embedding consumption
"""

import structlog
import uuid as _uuid

from ai_service.repositories.course_content import CourseContentRepository

logger = structlog.get_logger(__name__)


class ContentExtractor:
    """Fetches course content from MongoDB and combines with extracted PDF text."""

    def __init__(self, repo: CourseContentRepository):
        self.repo = repo

    async def fetch_module_data(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        lesson_ids: list[str] | None = None,
    ) -> dict | None:
        """Fetch raw module + lessons from MongoDB (no PDF processing).

        Returns:
            Dict with keys: module_title, module_description, lessons
            Returns None if module not found.
        """
        context_data = await self.repo.get_module_with_lessons(course_id, module_id, lesson_ids)
        if not context_data:
            return None
        return context_data

    async def fetch_course_data(
        self,
        course_id: _uuid.UUID,
    ) -> dict | None:
        """Fetch all modules and lessons for a course from MongoDB.

        Returns:
            Dict with keys: course_id, modules (list of module data dicts)
            Returns None if course not found.
        """
        course_doc = await self.repo.get_course_content(course_id)
        if not course_doc:
            return None

        modules_data = []
        for module in course_doc.get("modules", []):
            module_id = module.get("module_id", "")
            module_data = await self.fetch_module_data(course_id, module_id)
            if module_data:
                modules_data.append({"module_id": module_id, **module_data})

        return {"course_id": course_id, "modules": modules_data}

    @staticmethod
    def build_combined_text(
        module_data: dict,
        pdf_texts: dict[str, str],
        audio_texts: dict[str, str] | None = None,  # NEW
    ) -> str:
        audio_texts = audio_texts or {}
        sections = [
            f"## Module: {module_data['module_title']}\n{module_data['module_description']}"
        ]

        for lesson in module_data["lessons"]:
            lesson_id = lesson["lesson_id"]
            lesson_title = lesson["title"]
            text_content = lesson.get("text_content", "")

            section = f"### Lesson: {lesson_title}\n{text_content}"
            if lesson_id in pdf_texts:
                section += f"\n\n#### PDF Resources:\n{pdf_texts[lesson_id]}"
            if lesson_id in audio_texts:  # NEW
                section += f"\n\n#### Audio Transcripts:\n{audio_texts[lesson_id]}"  # NEW
            sections.append(section)

        return "\n\n".join(sections)

    @staticmethod
    def build_lesson_texts(
        lessons: list[dict],
        pdf_texts: dict[str, str],
        audio_texts: dict[str, str] | None = None,  # NEW
    ) -> dict[str, str]:
        audio_texts = audio_texts or {}
        lesson_texts: dict[str, str] = {}

        for lesson in lessons:
            lesson_id = lesson["lesson_id"]
            parts = []
            text_content = lesson.get("text_content", "")
            if text_content:
                parts.append(text_content)
            if lesson_id in pdf_texts:
                parts.append(pdf_texts[lesson_id])
            if lesson_id in audio_texts:  # NEW
                parts.append(audio_texts[lesson_id])  # NEW

            full_text = "\n\n".join(parts)
            if full_text.strip():
                lesson_texts[lesson_id] = full_text

        return lesson_texts
