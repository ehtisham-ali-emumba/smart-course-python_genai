"""Instructor content generation service."""

import asyncio
import structlog
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status

from ai_service.repositories.course_content import CourseContentRepository
from ai_service.clients.openai_client import OpenAIClient
from ai_service.clients.course_service_client import CourseServiceClient
from ai_service.clients.resource_extractor import ResourceTextExtractor
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
        resource_extractor: ResourceTextExtractor,
        status_tracker: GenerationStatusTracker,
    ):
        """Initialize instructor service with dependencies.

        Args:
            repo: CourseContentRepository for reading course data
            openai_client: OpenAIClient for LLM calls
            course_client: CourseServiceClient for persistence
            resource_extractor: ResourceTextExtractor for PDF extraction
            status_tracker: GenerationStatusTracker for Redis-based status tracking
        """
        self.repo = repo
        self.openai_client = openai_client
        self.course_client = course_client
        self.resource_extractor = resource_extractor
        self.status_tracker = status_tracker

    async def _validate_course_ownership_and_module(
        self,
        course_id: int,
        module_id: str,
        user_id: int,
    ) -> None:
        """Validate course existence, instructor ownership, and module existence.

        Raises HTTPException 404 if course or module is not found.
        Raises HTTPException 403 if the requesting user is not the course owner.

        Args:
            course_id: Course ID to validate
            module_id: Module ID to validate (checked against MongoDB)
            user_id: Requesting instructor user ID
        """
        log = logger.bind(course_id=course_id, module_id=module_id, user_id=user_id)

        # 1. Verify course exists via course-service
        log.debug("Validating course existence")
        course = await self.course_client.get_course(course_id, user_id)
        if course is None:
            log.warning("Course not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Course {course_id} not found",
            )

        # 2. Verify the requesting user is the course owner
        instructor_id = int(course.get("instructor_id", -1))
        if instructor_id != user_id:
            log.warning(
                "Forbidden: user is not the course owner",
                course_instructor_id=instructor_id,
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
        course_id: int,
        module_id: str,
        request: GenerateSummaryRequest,
        user_id: int,
    ) -> GenerateSummaryResponse:
        """Generate a summary for a module (async task).

        Validates course ownership and module existence before kicking off the
        background task and returning immediately.

        Args:
            course_id: Course ID
            module_id: Module ID
            request: Summary generation request
            user_id: Authenticated instructor user ID

        Returns:
            GenerateSummaryResponse with status PENDING
        """
        log = logger.bind(course_id=course_id, module_id=module_id, user_id=user_id)
        log.info("Summary generation requested")

        # Guard: validate before firing the background task
        await self._validate_course_ownership_and_module(course_id, module_id, user_id)

        log.info(
            "Validation passed — dispatching summary generation task",
            source_lesson_ids=request.source_lesson_ids,
        )

        # Fire background task (no await)
        asyncio.create_task(self._process_and_save_summary(course_id, module_id, request, user_id))

        return GenerateSummaryResponse(
            course_id=course_id,
            module_id=module_id,
            source_lesson_ids=request.source_lesson_ids or [],
            summary_id=None,
            status=GenerationStatus.PENDING,
            message="Summary generation started.",
        )

    async def _process_and_save_summary(
        self,
        course_id: int,
        module_id: str,
        request: GenerateSummaryRequest,
        user_id: int,
    ) -> None:
        """Background task: fetch content, generate summary, persist to course-service."""
        try:
            # ✅ Mark IN_PROGRESS before doing any work
            await self.status_tracker.set_in_progress(course_id, module_id, "summary")

            # Fetch module and lessons from MongoDB
            context_data = await self.repo.get_module_with_lessons(
                course_id, module_id, request.source_lesson_ids
            )
            if not context_data:
                logger.error(
                    "Module not found for summary generation",
                    course_id=course_id,
                    module_id=module_id,
                )
                await self.status_tracker.set_failed(
                    course_id, module_id, "summary", "Module not found"
                )
                return

            # Extract PDF text from lesson resources
            pdf_texts = await self.resource_extractor.extract_text_from_lessons(
                context_data["lessons"]
            )

            # Build enriched context with PDF content inline
            sections = [
                f"## Module: {context_data['module_title']}\n{context_data['module_description']}"
            ]
            for lesson in context_data["lessons"]:
                lesson_id = lesson["lesson_id"]
                section = f"### Lesson: {lesson['title']}\n{lesson.get('text_content', '')}"
                if lesson_id in pdf_texts:
                    section += f"\n\n#### PDF Resources:\n{pdf_texts[lesson_id]}"
                sections.append(section)

            combined_text = "\n\n".join(sections)

            # Call OpenAI to generate summary
            generated = await self.openai_client.generate_summary(
                combined_text,
                include_glossary=request.include_glossary,
                include_key_points=request.include_key_points,
                include_learning_objectives=request.include_learning_objectives,
                max_length_words=request.max_length_words,
                tone=request.tone,
                language=request.language,
            )

            # Build persistence payload matching course-service SummaryCreate schema
            payload = {
                "title": generated.title,
                "content": {
                    "summary_text": generated.content.summary_text,
                    "key_points": generated.content.key_points,
                    "learning_objectives": generated.content.learning_objectives,
                    "glossary": [
                        {"term": g.term, "definition": g.definition}
                        for g in generated.content.glossary
                    ],
                    "difficulty_assessment": (
                        {
                            "level": generated.content.difficulty_assessment.level,
                            "estimated_read_minutes": generated.content.difficulty_assessment.estimated_read_minutes,
                        }
                        if generated.content.difficulty_assessment
                        else None
                    ),
                },
                "is_published": False,
            }

            # Save via HTTP to course-service
            result = await self.course_client.save_summary(course_id, module_id, payload, user_id)
            if result:
                # ✅ Mark COMPLETED after successful save
                await self.status_tracker.set_completed(course_id, module_id, "summary")
                logger.info(
                    "Summary generated and saved successfully",
                    course_id=course_id,
                    module_id=module_id,
                )
            else:
                # ✅ Mark FAILED on save failure
                await self.status_tracker.set_failed(
                    course_id, module_id, "summary", "Failed to save to course-service"
                )
                logger.warning(
                    "Summary generated but failed to save to course-service",
                    course_id=course_id,
                    module_id=module_id,
                )

        except Exception as e:
            # ✅ Mark FAILED on error
            await self.status_tracker.set_failed(course_id, module_id, "summary", str(e))
            logger.exception(
                "Error during summary generation",
                course_id=course_id,
                module_id=module_id,
                error=str(e),
            )

    async def generate_quiz(
        self,
        course_id: int,
        module_id: str,
        request: GenerateQuizRequest,
        user_id: int,
    ) -> GenerateQuizResponse:
        """Generate quiz questions for a module (async task).

        Validates course ownership and module existence before kicking off the
        background task and returning immediately.

        Args:
            course_id: Course ID
            module_id: Module ID
            request: Quiz generation request
            user_id: Authenticated instructor user ID

        Returns:
            GenerateQuizResponse with status PENDING
        """
        log = logger.bind(course_id=course_id, module_id=module_id, user_id=user_id)
        log.info("Quiz generation requested")

        # Guard: validate before firing the background task
        await self._validate_course_ownership_and_module(course_id, module_id, user_id)

        log.info(
            "Validation passed — dispatching quiz generation task",
            source_lesson_ids=request.source_lesson_ids,
            num_questions=request.num_questions,
            difficulty=request.difficulty,
        )

        # Fire background task (no await)
        asyncio.create_task(self._process_and_save_quiz(course_id, module_id, request, user_id))

        return GenerateQuizResponse(
            course_id=course_id,
            module_id=module_id,
            source_lesson_ids=request.source_lesson_ids or [],
            quiz_id=None,
            status=GenerationStatus.PENDING,
            message="Quiz generation started.",
        )

    async def _process_and_save_quiz(
        self,
        course_id: int,
        module_id: str,
        request: GenerateQuizRequest,
        user_id: int,
    ) -> None:
        """Background task: fetch content, generate quiz, persist to course-service."""
        try:
            # ✅ Mark IN_PROGRESS before doing any work
            await self.status_tracker.set_in_progress(course_id, module_id, "quiz")

            # Fetch module and lessons from MongoDB
            context_data = await self.repo.get_module_with_lessons(
                course_id, module_id, request.source_lesson_ids
            )
            if not context_data:
                logger.error(
                    "Module not found for quiz generation",
                    course_id=course_id,
                    module_id=module_id,
                )
                await self.status_tracker.set_failed(
                    course_id, module_id, "quiz", "Module not found"
                )
                return

            # Extract PDF text from lesson resources
            pdf_texts = await self.resource_extractor.extract_text_from_lessons(
                context_data["lessons"]
            )

            # Build enriched context with PDF content inline
            sections = [
                f"## Module: {context_data['module_title']}\n{context_data['module_description']}"
            ]
            for lesson in context_data["lessons"]:
                lesson_id = lesson["lesson_id"]
                section = f"### Lesson: {lesson['title']}\n{lesson.get('text_content', '')}"
                if lesson_id in pdf_texts:
                    section += f"\n\n#### PDF Resources:\n{pdf_texts[lesson_id]}"
                sections.append(section)

            combined_text = "\n\n".join(sections)

            # Convert question types from enums to strings
            question_types = [qt.value for qt in request.question_types]

            # Call OpenAI to generate quiz
            generated = await self.openai_client.generate_quiz(
                combined_text,
                num_questions=request.num_questions,
                difficulty=request.difficulty.value if request.difficulty else None,
                question_types=question_types,
                language=request.language,
            )

            payload = self._build_quiz_payload(generated, request)

            # Save via HTTP to course-service
            result = await self.course_client.save_quiz(course_id, module_id, payload, user_id)
            if result:
                # ✅ Mark COMPLETED after successful save
                await self.status_tracker.set_completed(course_id, module_id, "quiz")
                logger.info(
                    "Quiz generated and saved successfully",
                    course_id=course_id,
                    module_id=module_id,
                )
            else:
                # ✅ Mark FAILED on save failure
                await self.status_tracker.set_failed(
                    course_id, module_id, "quiz", "Failed to save to course-service"
                )
                logger.warning(
                    "Quiz generated but failed to save to course-service",
                    course_id=course_id,
                    module_id=module_id,
                )

        except Exception as e:
            # ✅ Mark FAILED on error
            await self.status_tracker.set_failed(course_id, module_id, "quiz", str(e))
            logger.exception(
                "Error during quiz generation",
                course_id=course_id,
                module_id=module_id,
                error=str(e),
            )

    def _build_quiz_payload(self, generated: Any, request: GenerateQuizRequest) -> dict[str, Any]:
        questions: list[dict[str, Any]] = []
        for index, question in enumerate(generated.questions, start=1):
            normalized = self._normalize_generated_question(question, index)
            if normalized is not None:
                questions.append(normalized)

        if not questions:
            raise ValueError("No valid quiz questions generated from AI response")

        title = (generated.title or "Module Quiz").strip()[:300] or "Module Quiz"
        description = generated.description.strip() if generated.description else None

        return {
            "title": title,
            "description": description,
            "settings": {
                "passing_score": request.passing_score,
                "time_limit_minutes": request.time_limit_minutes,
                "max_attempts": request.max_attempts,
                "shuffle_questions": True,
                "shuffle_options": True,
                "show_correct_answers_after": "completion",
            },
            "questions": questions,
            "is_published": False,
        }

    def _normalize_generated_question(self, question: Any, index: int) -> dict[str, Any] | None:
        question_type = question.question_type
        question_text = (question.question_text or "").strip() or f"Question {index}"
        explanation = question.explanation.strip() if question.explanation else None
        hint = question.hint.strip() if question.hint else None

        if question_type == "short_answer":
            correct_answers = [
                answer.strip()
                for answer in (question.correct_answers or [])
                if isinstance(answer, str) and answer.strip()
            ]
            if not correct_answers:
                logger.warning("Skipping invalid short_answer question with no correct_answers")
                return None

            return {
                "order": index,
                "question_text": question_text,
                "question_type": "short_answer",
                "options": None,
                "correct_answers": correct_answers,
                "explanation": explanation,
                "hint": hint,
            }

        options = []
        for option in question.options or []:
            option_text = (option.text or "").strip()
            if not option_text:
                continue
            options.append(
                {
                    "option_id": (option.option_id or "").strip(),
                    "text": option_text,
                    "is_correct": bool(option.is_correct),
                }
            )

        if question_type == "true_false":
            true_is_correct = True
            for option in options:
                option_id = option["option_id"].lower()
                option_text = option["text"].strip().lower()
                if option_id == "opt_false" or option_text in {"false", "no"}:
                    if option["is_correct"]:
                        true_is_correct = False
                        break
                if option_id == "opt_true" or option_text in {"true", "yes"}:
                    if option["is_correct"]:
                        true_is_correct = True
                        break

            normalized_options = [
                {"option_id": "opt_true", "text": "True", "is_correct": true_is_correct},
                {"option_id": "opt_false", "text": "False", "is_correct": not true_is_correct},
            ]
            return {
                "order": index,
                "question_text": question_text,
                "question_type": "true_false",
                "options": normalized_options,
                "correct_answers": None,
                "explanation": explanation,
                "hint": hint,
            }

        if len(options) < 2:
            logger.warning(
                "Skipping invalid objective question with insufficient options",
                question_type=question_type,
            )
            return None

        normalized_options = []
        for option_index, option in enumerate(options):
            letter = chr(ord("a") + option_index)
            normalized_options.append(
                {
                    "option_id": f"opt_{letter}",
                    "text": option["text"],
                    "is_correct": bool(option["is_correct"]),
                }
            )

        if question_type == "multiple_choice":
            first_correct_index = next(
                (i for i, option in enumerate(normalized_options) if option["is_correct"]),
                0,
            )
            for option_index, option in enumerate(normalized_options):
                option["is_correct"] = option_index == first_correct_index

        if question_type == "multiple_select" and not any(
            option["is_correct"] for option in normalized_options
        ):
            normalized_options[0]["is_correct"] = True

        return {
            "order": index,
            "question_text": question_text,
            "question_type": question_type,
            "options": normalized_options,
            "correct_answers": None,
            "explanation": explanation,
            "hint": hint,
        }

    async def get_generation_status(
        self, course_id: int, module_id: str
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
