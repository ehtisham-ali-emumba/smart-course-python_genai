"""Instructor content generation service."""

import asyncio
import uuid as _uuid
import structlog
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status

from ai_service.repositories.course_content import CourseContentRepository
from ai_service.clients.openai_client import OpenAIClient
from ai_service.clients.course_service_client import CourseServiceClient
from ai_service.services.content_extractor import ContentExtractor
from ai_service.services.instructor_graphs import build_quiz_graph, build_summary_graph
from ai_service.schemas.instructor import (
    GenerateSummaryRequest,
    GenerateSummaryResponse,
    GenerateQuizRequest,
    GenerateQuizResponse,
    GenerationStatusResponse,
)
from ai_service.schemas.common import GenerationStatus
from ai_service.services.generation_status import GenerationStatusTracker

logger = structlog.get_logger(__name__)


class InstructorService:
    """Handles AI content generation for instructors."""

    def __init__(
        self,
        repo: CourseContentRepository,
        openai_client: OpenAIClient,
        course_client: CourseServiceClient,
        content_extractor: ContentExtractor,
        status_tracker: GenerationStatusTracker,
    ):
        """Initialize instructor service with dependencies.

        Args:
            repo: CourseContentRepository for reading course data
            openai_client: OpenAIClient for LLM calls
            course_client: CourseServiceClient for persistence
            content_extractor: ContentExtractor for centralized content fetching
            status_tracker: GenerationStatusTracker for Redis-based status tracking
        """
        self.repo = repo
        self.openai_client = openai_client
        self.course_client = course_client
        self.content_extractor = content_extractor
        self.status_tracker = status_tracker

    async def _validate_course_ownership_and_module(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        user_id: _uuid.UUID,
        profile_id: _uuid.UUID,
    ) -> None:
        """Validate course existence, instructor ownership, and module existence.

        Raises HTTPException 404 if course or module is not found.
        Raises HTTPException 403 if the requesting user is not the course owner.

        Args:
            course_id: Course ID to validate
            module_id: Module ID to validate (checked against MongoDB)
            user_id: Requesting instructor user ID
            profile_id: Requesting instructor profile ID
        """
        log = logger.bind(course_id=course_id, module_id=module_id, user_id=user_id)

        # 1. Verify course exists via course-service
        log.debug("Validating course existence")
        course = await self.course_client.get_course(course_id, user_id, profile_id)
        if course is None:
            log.warning("Course not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Course {course_id} not found",
            )

        # 2. Verify the requesting user is the course owner
        instructor_id_raw = course.get("instructor_id")
        if not instructor_id_raw or _uuid.UUID(str(instructor_id_raw)) != profile_id:
            log.warning(
                "Forbidden: user is not the course owner",
                course_instructor_id=instructor_id_raw,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not the owner of this course",
            )

        # 3. Verify module exists in MongoDB
        log.debug("Validating module existence")
        module = await self.repo.get_module(course_id, module_id)
        if module is None:
            log.warning("Module not found in course")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Module {module_id} not found in course {course_id}",
            )

        log.debug("Course ownership and module validation passed")

    async def generate_summary(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        request: GenerateSummaryRequest,
        user_id: _uuid.UUID,
        profile_id: _uuid.UUID,
    ) -> GenerateSummaryResponse:
        """Generate a summary for a module (async task).

        Validates course ownership and module existence before kicking off the
        background task and returning immediately.

        Args:
            course_id: Course ID
            module_id: Module ID
            request: Summary generation request
            user_id: Authenticated instructor user ID
            profile_id: Authenticated instructor profile ID

        Returns:
            GenerateSummaryResponse with status PENDING
        """
        log = logger.bind(course_id=course_id, module_id=module_id, user_id=user_id)
        log.info("Summary generation requested")

        # Guard: validate before firing the background task
        await self._validate_course_ownership_and_module(course_id, module_id, user_id, profile_id)

        log.info(
            "Validation passed — dispatching summary generation task",
            source_lesson_ids=request.source_lesson_ids,
        )

        # Fire background task (no await)
        asyncio.create_task(
            self._run_summary_graph(course_id, module_id, request, user_id, profile_id)
        )

        return GenerateSummaryResponse(
            course_id=course_id,
            module_id=module_id,
            source_lesson_ids=request.source_lesson_ids or [],
            summary_id=None,
            status=GenerationStatus.PENDING,
            message="Summary generation started.",
        )

    async def _run_summary_graph(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        request: GenerateSummaryRequest,
        user_id: _uuid.UUID,
        profile_id: _uuid.UUID,
    ) -> None:
        """Background task: invoke summary generation LangGraph, handle completion/failure."""
        try:
            # Mark IN_PROGRESS before starting the graph
            await self.status_tracker.set_in_progress(course_id, module_id, "summary")

            # Build and invoke the graph
            graph = build_summary_graph(
                self.openai_client,
                self.course_client,
                self.content_extractor,
            )

            result = await graph.ainvoke(
                {
                    "course_id": course_id,
                    "module_id": module_id,
                    "user_id": user_id,
                    "profile_id": profile_id,
                    "source_lesson_ids": request.source_lesson_ids,
                    "include_glossary": request.include_glossary,
                    "include_key_points": request.include_key_points,
                    "include_learning_objectives": request.include_learning_objectives,
                    "max_length_words": request.max_length_words,
                    "tone": request.tone,
                    "language": request.language,
                    "retry_count": 0,
                }
            )

            # Check result: if persisted, mark completed; otherwise mark failed
            if result.get("persisted"):
                await self.status_tracker.set_completed(course_id, module_id, "summary")
                logger.info(
                    "Summary generation graph completed successfully",
                    course_id=course_id,
                    module_id=module_id,
                )
            else:
                error_msg = result.get("error", "Summary generation failed")
                await self.status_tracker.set_failed(course_id, module_id, "summary", error_msg)
                logger.warning(
                    "Summary generation graph did not persist",
                    course_id=course_id,
                    module_id=module_id,
                    error=error_msg,
                )

        except Exception as e:
            await self.status_tracker.set_failed(course_id, module_id, "summary", str(e))
            logger.exception(
                "Summary generation graph encountered an exception",
                course_id=course_id,
                module_id=module_id,
                error=str(e),
            )

    async def generate_quiz(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        request: GenerateQuizRequest,
        user_id: _uuid.UUID,
        profile_id: _uuid.UUID,
    ) -> GenerateQuizResponse:
        """Generate quiz questions for a module (async task).

        Validates course ownership and module existence before kicking off the
        background task and returning immediately.

        Args:
            course_id: Course ID
            module_id: Module ID
            request: Quiz generation request
            user_id: Authenticated instructor user ID
            profile_id: Authenticated instructor profile ID

        Returns:
            GenerateQuizResponse with status PENDING
        """
        log = logger.bind(course_id=course_id, module_id=module_id, user_id=user_id)
        log.info("Quiz generation requested")

        # Guard: validate before firing the background task
        await self._validate_course_ownership_and_module(course_id, module_id, user_id, profile_id)

        log.info(
            "Validation passed — dispatching quiz generation task",
            source_lesson_ids=request.source_lesson_ids,
            num_questions=request.num_questions,
            difficulty=request.difficulty,
        )

        # Fire background task (no await)
        asyncio.create_task(
            self._run_quiz_graph(course_id, module_id, request, user_id, profile_id)
        )

        return GenerateQuizResponse(
            course_id=course_id,
            module_id=module_id,
            source_lesson_ids=request.source_lesson_ids or [],
            quiz_id=None,
            status=GenerationStatus.PENDING,
            message="Quiz generation started.",
        )

    async def _run_quiz_graph(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        request: GenerateQuizRequest,
        user_id: _uuid.UUID,
        profile_id: _uuid.UUID,
    ) -> None:
        """Background task: invoke quiz generation LangGraph, handle completion/failure."""
        try:
            # Mark IN_PROGRESS before starting the graph
            await self.status_tracker.set_in_progress(course_id, module_id, "quiz")

            # Build and invoke the graph
            graph = build_quiz_graph(
                self.openai_client,
                self.course_client,
                self.content_extractor,
            )

            result = await graph.ainvoke(
                {
                    "course_id": course_id,
                    "module_id": module_id,
                    "user_id": user_id,
                    "profile_id": profile_id,
                    "source_lesson_ids": request.source_lesson_ids,
                    "num_questions": request.num_questions,
                    "difficulty": request.difficulty.value if request.difficulty else None,
                    "question_types": [qt.value for qt in request.question_types],
                    "language": request.language,
                    "passing_score": request.passing_score,
                    "max_attempts": request.max_attempts,
                    "time_limit_minutes": request.time_limit_minutes,
                    "retry_count": 0,
                }
            )

            # Check result: if persisted, mark completed; otherwise mark failed
            if result.get("persisted"):
                await self.status_tracker.set_completed(course_id, module_id, "quiz")
                logger.info(
                    "Quiz generation graph completed successfully",
                    course_id=course_id,
                    module_id=module_id,
                )
            else:
                error_msg = result.get("error", "Quiz generation failed")
                await self.status_tracker.set_failed(course_id, module_id, "quiz", error_msg)
                logger.warning(
                    "Quiz generation graph did not persist",
                    course_id=course_id,
                    module_id=module_id,
                    error=error_msg,
                )

        except Exception as e:
            await self.status_tracker.set_failed(course_id, module_id, "quiz", str(e))
            logger.exception(
                "Quiz generation graph encountered an exception",
                course_id=course_id,
                module_id=module_id,
                error=str(e),
            )

    async def get_generation_status(
        self, course_id: _uuid.UUID, module_id: str
    ) -> GenerationStatusResponse:
        """Check generation status for a module.

        Uses Redis for in-flight/recent status, falls back to MongoDB for persisted content.

        Args:
            course_id: Course ID
            module_id: Module ID

        Returns:
            GenerationStatusResponse with completion status and timestamps
        """
        # 1. Check Redis for active/recent status
        redis_summary = await self.status_tracker.get_status(course_id, module_id, "summary")
        redis_quiz = await self.status_tracker.get_status(course_id, module_id, "quiz")

        # 2. Determine summary status
        if redis_summary:
            summary_status = GenerationStatus(redis_summary["status"])
            summary_error = redis_summary.get("error")
        else:
            # Fallback: check if content already exists in MongoDB
            existing = await self.repo.get_existing_summary(course_id, module_id)
            summary_status = (
                GenerationStatus.COMPLETED if existing else GenerationStatus.NOT_STARTED
            )
            summary_error = None

        # 3. Determine quiz status
        if redis_quiz:
            quiz_status = GenerationStatus(redis_quiz["status"])
            quiz_error = redis_quiz.get("error")
        else:
            existing = await self.repo.get_existing_quiz(course_id, module_id)
            quiz_status = GenerationStatus.COMPLETED if existing else GenerationStatus.NOT_STARTED
            quiz_error = None

        # 4. Determine last_generation_at from whichever source has data
        last_generation_at = None
        for redis_data in [redis_summary, redis_quiz]:
            if redis_data and redis_data.get("completed_at"):
                ts = datetime.fromisoformat(redis_data["completed_at"])
                if not last_generation_at or ts > last_generation_at:
                    last_generation_at = ts

        # Fallback timestamps from MongoDB if no Redis data
        if not last_generation_at:
            for getter in [self.repo.get_existing_summary, self.repo.get_existing_quiz]:
                doc = await getter(course_id, module_id)
                if doc and doc.get("created_at"):
                    ts = doc["created_at"]
                    if not last_generation_at or ts > last_generation_at:
                        last_generation_at = ts

        return GenerationStatusResponse(
            course_id=course_id,
            module_id=module_id,
            summary_status=summary_status,
            quiz_status=quiz_status,
            summary_error=summary_error,
            quiz_error=quiz_error,
            last_generation_at=last_generation_at,
        )
