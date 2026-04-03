from datetime import datetime
from typing import Any
import uuid as _uuid
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from repositories.course import CourseRepository
from repositories.course_content import CourseContentRepository
from repositories.module_quiz import ModuleQuizRepository
from schemas.quiz_summary import (
    QuizCreate,
    QuizGenerateRequest,
    QuizPatch,
    QuizPublishUpdate,
    QuizUpdate,
)


def _mongo_id() -> str:
    return uuid4().hex


class ModuleQuizService:
    """Business logic for module quiz CRUD + generation."""

    def __init__(self, pg_db: AsyncSession, mongo_db: Any):
        self.course_repo = CourseRepository(pg_db)
        self.content_repo = CourseContentRepository(mongo_db)
        self.quiz_repo = ModuleQuizRepository(mongo_db)

    async def get_published_quiz(
        self, course_id: _uuid.UUID, module_id: str
    ) -> dict[str, Any] | None:
        doc = await self.quiz_repo.get_published_by_course_module(course_id, module_id)
        return self._to_response(doc) if doc else None

    async def get_quiz_for_viewer(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        viewer_id: _uuid.UUID,
        viewer_role: str,
    ) -> dict[str, Any] | None:
        if viewer_role == "instructor":
            doc = await self.quiz_repo.get_active_by_course_module(course_id, module_id)
            return self._to_response(doc) if doc else None

        if viewer_role == "instructor":
            course = await self.course_repo.get_by_id(course_id)
            if (
                course is not None
                and not bool(getattr(course, "is_deleted", False))
                and getattr(course, "instructor_id") == viewer_id
            ):
                doc = await self.quiz_repo.get_active_by_course_module(course_id, module_id)
                return self._to_response(doc) if doc else None

        return await self.get_published_quiz(course_id, module_id)

    async def create_quiz(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        payload: QuizCreate,
        instructor_id: _uuid.UUID,
    ) -> dict[str, Any]:
        await self._ensure_owned_course(course_id, instructor_id)
        await self._ensure_module_exists(course_id, module_id)

        existing = await self.quiz_repo.get_by_course_module(course_id, module_id)
        if existing:
            raise FileExistsError("Quiz already exists for this module")

        now = datetime.utcnow()
        document = {
            "course_id": course_id,
            "module_id": module_id,
            "title": payload.title,
            "description": payload.description,
            "settings": payload.settings.model_dump(mode="python"),
            "questions": self._normalize_questions(payload.questions),
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
        created = await self.quiz_repo.create(document)
        return self._to_response(created)

    async def replace_quiz(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        payload: QuizUpdate,
        instructor_id: _uuid.UUID,
    ) -> dict[str, Any]:
        await self._ensure_owned_course(course_id, instructor_id)
        await self._ensure_module_exists(course_id, module_id)

        existing = await self.quiz_repo.get_by_course_module(course_id, module_id)
        now = datetime.utcnow()
        authorship = self._next_authorship(
            existing=existing,
            editor_id=instructor_id,
            generated=False,
            source_lesson_ids=[],
        )

        document = {
            "course_id": course_id,
            "module_id": module_id,
            "title": payload.title,
            "description": payload.description,
            "settings": payload.settings.model_dump(mode="python"),
            "questions": self._normalize_questions(payload.questions),
            "authorship": authorship,
            "is_published": payload.is_published,
            "is_active": True,
            "created_at": existing.get("created_at", now) if existing else now,
            "updated_at": now,
        }
        replaced = await self.quiz_repo.replace(course_id, module_id, document)
        return self._to_response(replaced)

    async def patch_quiz(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        payload: QuizPatch,
        instructor_id: _uuid.UUID,
    ) -> dict[str, Any]:
        await self._ensure_owned_course(course_id, instructor_id)
        await self._ensure_module_exists(course_id, module_id)

        existing = await self.quiz_repo.get_by_course_module(course_id, module_id)
        if not existing:
            raise LookupError("Quiz not found")

        update_data = payload.model_dump(exclude_unset=True, mode="python")
        if "questions" in update_data and update_data["questions"] is not None:
            update_data["questions"] = self._normalize_questions(update_data["questions"])

        update_data["authorship"] = self._next_authorship(
            existing=existing,
            editor_id=instructor_id,
            generated=False,
            source_lesson_ids=existing.get("authorship", {}).get("source_lesson_ids", []),
        )

        updated = await self.quiz_repo.patch(course_id, module_id, update_data)
        if not updated:
            raise LookupError("Quiz not found")
        return self._to_response(updated)

    async def publish_quiz(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        payload: QuizPublishUpdate,
        instructor_id: _uuid.UUID,
    ) -> dict[str, Any]:
        await self._ensure_owned_course(course_id, instructor_id)

        existing = await self.quiz_repo.get_active_by_course_module(course_id, module_id)
        if not existing:
            raise LookupError("Quiz not found")

        updated = await self.quiz_repo.patch(
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
            raise LookupError("Quiz not found")
        return self._to_response(updated)

    async def delete_quiz(
        self, course_id: _uuid.UUID, module_id: str, instructor_id: _uuid.UUID
    ) -> bool:
        await self._ensure_owned_course(course_id, instructor_id)
        return await self.quiz_repo.soft_delete(course_id, module_id)

    async def generate_quiz(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        payload: QuizGenerateRequest,
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
        questions = self._build_generated_questions(selected_lessons, payload.num_questions)

        existing = await self.quiz_repo.get_active_by_course_module(course_id, module_id)
        now = datetime.utcnow()
        settings = {
            "passing_score": payload.passing_score,
            "time_limit_minutes": payload.time_limit_minutes,
            "max_attempts": payload.max_attempts,
            "shuffle_questions": True,
            "shuffle_options": True,
            "show_correct_answers_after": "completion",
        }
        document = {
            "course_id": course_id,
            "module_id": module_id,
            "title": f"{module.get('title', 'Module')} — Module Quiz",
            "description": "AI-generated quiz based on selected module lessons",
            "settings": settings,
            "questions": questions,
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
        replaced = await self.quiz_repo.replace(course_id, module_id, document)
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

    def _normalize_questions(self, questions: list[Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for index, question in enumerate(questions, start=1):
            question_data = (
                question.model_dump(mode="python")
                if hasattr(question, "model_dump")
                else dict(question)
            )
            question_data["question_id"] = question_data.get("question_id") or _mongo_id()
            question_data["order"] = question_data.get("order") or index

            options = question_data.get("options")
            if options:
                normalized_options = []
                for option in options:
                    option_data = (
                        option.model_dump(mode="python")
                        if hasattr(option, "model_dump")
                        else dict(option)
                    )
                    option_data["option_id"] = option_data.get("option_id") or _mongo_id()
                    normalized_options.append(option_data)
                question_data["options"] = normalized_options

            normalized.append(question_data)

        return normalized

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
            else:
                source = "manual"
            ai_model = previous.get("ai_model") if source == "ai_edited" else None
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

    def _build_generated_questions(
        self,
        lessons: list[dict[str, Any]],
        num_questions: int,
    ) -> list[dict[str, Any]]:
        questions: list[dict[str, Any]] = []
        lesson_titles = [lesson.get("title", "Untitled lesson") for lesson in lessons]

        for index in range(num_questions):
            lesson_title = lesson_titles[index % len(lesson_titles)]
            questions.append(
                {
                    "question_id": _mongo_id(),
                    "order": index + 1,
                    "question_text": f"Which statement best describes '{lesson_title}'?",
                    "question_type": "multiple_choice",
                    "options": [
                        {
                            "option_id": "opt_true",
                            "text": f"It covers key concepts from {lesson_title}.",
                            "is_correct": True,
                        },
                        {
                            "option_id": "opt_false",
                            "text": "It is unrelated to this module.",
                            "is_correct": False,
                        },
                    ],
                    "explanation": f"This question checks understanding of {lesson_title}.",
                    "hint": "Recall the lesson's main objective.",
                }
            )

        return questions

    def _to_response(self, doc: dict[str, Any]) -> dict[str, Any]:
        result = dict(doc)
        result["id"] = str(result.pop("_id"))
        return result
