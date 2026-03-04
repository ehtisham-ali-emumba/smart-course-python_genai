"""Centralized content extraction for course materials.

Used by: InstructorService (summary/quiz generation), IndexService (RAG indexing).
Fetches course content from MongoDB, downloads+extracts PDF text, and combines
everything into structured text ready for LLM or embedding consumption.
"""

import structlog

from ai_service.repositories.course_content import CourseContentRepository
from ai_service.clients.resource_extractor import ResourceTextExtractor

logger = structlog.get_logger(__name__)


class ContentExtractor:
    """Fetches and combines course content (MongoDB text + PDF resources) into text."""

    def __init__(
        self,
        repo: CourseContentRepository,
        resource_extractor: ResourceTextExtractor,
    ):
        self.repo = repo
        self.resource_extractor = resource_extractor

    async def extract_module_content(
        self,
        course_id: int,
        module_id: str,
        lesson_ids: list[str] | None = None,
    ) -> dict | None:
        """Extract all text content for a module (MongoDB text + PDF resources).

        Returns:
            Dict with keys:
              - module_title: str
              - module_description: str
              - lessons: list[dict] — each with lesson_id, title, text_content, resources
              - combined_text: str — all content merged into one text block
              - lesson_texts: dict[str, str] — mapping lesson_id → full text (inline + PDF)
            Returns None if module not found.
        """
        # 1. Fetch module + lessons from MongoDB
        context_data = await self.repo.get_module_with_lessons(course_id, module_id, lesson_ids)
        if not context_data:
            return None

        # 2. Extract PDF text from lesson resources
        pdf_texts = await self.resource_extractor.extract_text_from_lessons(context_data["lessons"])

        # 3. Build enriched text per lesson and combined
        sections = [
            f"## Module: {context_data['module_title']}\n{context_data['module_description']}"
        ]
        lesson_texts: dict[str, str] = {}

        for lesson in context_data["lessons"]:
            lesson_id = lesson["lesson_id"]
            lesson_title = lesson["title"]
            text_content = lesson.get("text_content", "")

            # Build per-lesson text
            parts = []
            if text_content:
                parts.append(text_content)
            if lesson_id in pdf_texts:
                parts.append(pdf_texts[lesson_id])

            full_lesson_text = "\n\n".join(parts)
            if full_lesson_text.strip():
                lesson_texts[lesson_id] = full_lesson_text

            # Build section for combined text
            section = f"### Lesson: {lesson_title}\n{text_content}"
            if lesson_id in pdf_texts:
                section += f"\n\n#### PDF Resources:\n{pdf_texts[lesson_id]}"
            sections.append(section)

        combined_text = "\n\n".join(sections)

        return {
            "module_title": context_data["module_title"],
            "module_description": context_data["module_description"],
            "lessons": context_data["lessons"],
            "combined_text": combined_text,
            "lesson_texts": lesson_texts,
        }

    async def extract_course_content(
        self,
        course_id: int,
    ) -> dict | None:
        """Extract all text content for an entire course (all modules, all lessons).

        Returns:
            Dict with keys:
              - course_id: int
              - modules: list[dict] — each module's extraction result
              - total_lessons: int
            Returns None if course not found.
        """
        course_doc = await self.repo.get_course_content(course_id)
        if not course_doc:
            return None

        modules_data = []
        total_lessons = 0

        for module in course_doc.get("modules", []):
            module_id = module.get("module_id", "")
            module_result = await self.extract_module_content(course_id, module_id)
            if module_result:
                modules_data.append(
                    {
                        "module_id": module_id,
                        **module_result,
                    }
                )
                total_lessons += len(module_result.get("lesson_texts", {}))

        return {
            "course_id": course_id,
            "modules": modules_data,
            "total_lessons": total_lessons,
        }
