from datetime import datetime
from typing import Any
import uuid as _uuid

from sqlalchemy.ext.asyncio import AsyncSession

from repositories.course import CourseRepository
from repositories.course_content import CourseContentRepository
from repositories.module_summary import ModuleSummaryRepository
from schemas.quiz_summary import (
    SummaryCreate,
    SummaryGenerateRequest,
    SummaryPatch,
    SummaryPublishUpdate,
    SummaryUpdate,
)


class ModuleSummaryService:
    """Business logic for module summary CRUD + generation."""

    def __init__(self, pg_db: AsyncSession, mongo_db: Any):
        self.course_repo = CourseRepository(pg_db)
        self.content_repo = CourseContentRepository(mongo_db)
        self.summary_repo = ModuleSummaryRepository(mongo_db)

    async def get_published_summary(
        self, course_id: _uuid.UUID, module_id: str
    ) -> dict[str, Any] | None:
        doc = await self.summary_repo.get_published_by_course_module(course_id, module_id)
        return self._to_response(doc) if doc else None

    async def get_summary_for_viewer(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        viewer_id: _uuid.UUID,
        viewer_role: str,
    ) -> dict[str, Any] | None:
        if viewer_role == "instructor":
            doc = await self.summary_repo.get_active_by_course_module(course_id, module_id)
            return self._to_response(doc) if doc else None

        return await self.get_published_summary(course_id, module_id)

    async def create_summary(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        payload: SummaryCreate,
        instructor_id: _uuid.UUID,
    ) -> dict[str, Any]:
        await self._ensure_owned_course(course_id, instructor_id)
        await self._ensure_module_exists(course_id, module_id)

        existing = await self.summary_repo.get_by_course_module(course_id, module_id)
        if existing:
            raise FileExistsError("Summary already exists for this module")

        now = datetime.utcnow()
        document = {
            "course_id": course_id,
            "module_id": module_id,
            "title": payload.title,
            "content": payload.content.model_dump(mode="python"),
            "authorship": {
                "source": "manual",
                "generated_by_user_id": instructor_id,
                "ai_model": None,
                "source_lesson_ids": [],
                "version": 1,
                "last_edited_by": instructor_id,
                "last_edited_at": now,
            },
            "is_published": payload.is_published,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        created = await self.summary_repo.create(document)
        return self._to_response(created)

    async def replace_summary(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        payload: SummaryUpdate,
        instructor_id: _uuid.UUID,
    ) -> dict[str, Any]:
        await self._ensure_owned_course(course_id, instructor_id)
        await self._ensure_module_exists(course_id, module_id)

        existing = await self.summary_repo.get_by_course_module(course_id, module_id)
        now = datetime.utcnow()
        document = {
            "course_id": course_id,
            "module_id": module_id,
            "title": payload.title,
            "content": payload.content.model_dump(mode="python"),
            "authorship": self._next_authorship(
                existing=existing,
                editor_id=instructor_id,
                generated=False,
                source_lesson_ids=(existing or {})
                .get("authorship", {})
                .get("source_lesson_ids", []),
            ),
            "is_published": payload.is_published,
            "is_active": True,
            "created_at": existing.get("created_at", now) if existing else now,
            "updated_at": now,
        }
        replaced = await self.summary_repo.replace(course_id, module_id, document)
        return self._to_response(replaced)

    async def patch_summary(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        payload: SummaryPatch,
        instructor_id: _uuid.UUID,
    ) -> dict[str, Any]:
        await self._ensure_owned_course(course_id, instructor_id)
        await self._ensure_module_exists(course_id, module_id)

        existing = await self.summary_repo.get_by_course_module(course_id, module_id)
        if not existing:
            raise LookupError("Summary not found")

        update_data = payload.model_dump(exclude_unset=True, mode="python")
        update_data["authorship"] = self._next_authorship(
            existing=existing,
            editor_id=instructor_id,
            generated=False,
            source_lesson_ids=existing.get("authorship", {}).get("source_lesson_ids", []),
        )

        updated = await self.summary_repo.patch(course_id, module_id, update_data)
        if not updated:
            raise LookupError("Summary not found")
        return self._to_response(updated)

    async def publish_summary(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        payload: SummaryPublishUpdate,
        instructor_id: _uuid.UUID,
    ) -> dict[str, Any]:
        await self._ensure_owned_course(course_id, instructor_id)

        existing = await self.summary_repo.get_active_by_course_module(course_id, module_id)
        if not existing:
            raise LookupError("Summary not found")

        updated = await self.summary_repo.patch(
            course_id,
            module_id,
            {
                "is_published": payload.is_published,
                "authorship": self._next_authorship(
                    existing=existing,
                    editor_id=instructor_id,
                    generated=False,
                    source_lesson_ids=existing.get("authorship", {}).get("source_lesson_ids", []),
                ),
            },
        )
        if not updated:
            raise LookupError("Summary not found")
        return self._to_response(updated)

    async def delete_summary(
        self, course_id: _uuid.UUID, module_id: str, instructor_id: _uuid.UUID
    ) -> bool:
        await self._ensure_owned_course(course_id, instructor_id)
        return await self.summary_repo.soft_delete(course_id, module_id)

    async def generate_summary(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        payload: SummaryGenerateRequest,
        instructor_id: _uuid.UUID,
    ) -> dict[str, Any]:
        await self._ensure_owned_course(course_id, instructor_id)

        module = await self._get_module_or_404(course_id, module_id)
        lessons = module.get("lessons", [])
        lesson_map = {lesson.get("lesson_id"): lesson for lesson in lessons}

        missing = [
            lesson_id for lesson_id in payload.source_lesson_ids if lesson_id not in lesson_map
        ]
        if missing:
            raise LookupError("One or more source lessons were not found in this module")

        selected_lessons = [lesson_map[lesson_id] for lesson_id in payload.source_lesson_ids]
        generated_content = self._build_generated_content(payload, selected_lessons)

        existing = await self.summary_repo.get_active_by_course_module(course_id, module_id)
        now = datetime.utcnow()

        document = {
            "course_id": course_id,
            "module_id": module_id,
            "title": f"{module.get('title', 'Module')} — Module Summary",
            "content": generated_content,
            "authorship": self._next_authorship(
                existing=existing,
                editor_id=instructor_id,
                generated=True,
                source_lesson_ids=payload.source_lesson_ids,
            ),
            "is_published": False,
            "is_active": True,
            "created_at": existing.get("created_at", now) if existing else now,
            "updated_at": now,
        }
        replaced = await self.summary_repo.replace(course_id, module_id, document)
        return self._to_response(replaced)

    async def _ensure_owned_course(self, course_id: _uuid.UUID, instructor_id: _uuid.UUID) -> None:
        course = await self.course_repo.get_by_id(course_id)
        if course is None or bool(getattr(course, "is_deleted", False)):
            raise LookupError("Course not found")
        if getattr(course, "instructor_id") != instructor_id:
            raise PermissionError("You do not own this course")

    async def _ensure_module_exists(self, course_id: _uuid.UUID, module_id: str) -> None:
        await self._get_module_or_404(course_id, module_id)

    async def _get_module_or_404(self, course_id: _uuid.UUID, module_id: str) -> dict[str, Any]:
        content = await self.content_repo.get_by_course_id(course_id)
        if not content:
            raise LookupError("Course content not found")

        for module in content.get("modules", []):
            if module.get("module_id") == module_id and module.get("is_active", True):
                return module

        raise LookupError("Module not found")

    def _next_authorship(
        self,
        existing: dict[str, Any] | None,
        editor_id: _uuid.UUID,
        generated: bool,
        source_lesson_ids: list[str],
    ) -> dict[str, Any]:
        now = datetime.utcnow()

        previous = (existing or {}).get("authorship") or {}
        previous_source = previous.get("source")
        previous_version = int(previous.get("version", 0))

        if generated:
            source = "ai_generated"
            ai_model = "internal-v1"
            generated_by_user_id = editor_id
        else:
            if previous_source in {"ai_generated", "ai_edited"}:
                source = "ai_edited"
                ai_model = previous.get("ai_model")
            else:
                source = "manual"
                ai_model = None
            generated_by_user_id = previous.get("generated_by_user_id") or editor_id

        return {
            "source": source,
            "generated_by_user_id": generated_by_user_id,
            "ai_model": ai_model,
            "source_lesson_ids": source_lesson_ids,
            "version": previous_version + 1 if previous_version else 1,
            "last_edited_by": editor_id,
            "last_edited_at": now,
        }

    def _build_generated_content(
        self,
        payload: SummaryGenerateRequest,
        lessons: list[dict[str, Any]],
    ) -> dict[str, Any]:
        lesson_titles = [lesson.get("title", "Untitled lesson") for lesson in lessons]
        summary_text = "This module covers the following lessons: " + ", ".join(lesson_titles) + "."

        content = {
            "summary_text": summary_text,
            "summary_html": None,
            "key_points": [],
            "learning_objectives": [],
            "glossary": [],
            "difficulty_assessment": {
                "level": "beginner",
                "estimated_read_minutes": max(1, min(15, len(lesson_titles) * 2)),
            },
        }

        if payload.include_key_points:
            content["key_points"] = [
                f"Understand the core idea of {title}" for title in lesson_titles
            ]

        if payload.include_learning_objectives:
            content["learning_objectives"] = [
                f"Explain the fundamentals of {title}" for title in lesson_titles
            ]

        if payload.include_glossary:
            content["glossary"] = [
                {"term": "Module", "definition": "A grouped set of related lessons."},
                {"term": "Learning Objective", "definition": "A measurable expected outcome."},
            ]

        return content

    def _to_response(self, doc: dict[str, Any]) -> dict[str, Any]:
        result = dict(doc)
        result["id"] = str(result.pop("_id"))
        return result
