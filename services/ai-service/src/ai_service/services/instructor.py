"""Instructor content generation service."""

import asyncio
import structlog
from datetime import datetime

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
    GenerateAllRequest,
    GenerateAllResponse,
    GenerationStatusResponse,
)
from ai_service.schemas.common import GenerationStatus

logger = structlog.get_logger(__name__)


class InstructorService:
    """Handles AI content generation for instructors."""

    def __init__(
        self,
        repo: CourseContentRepository,
        openai_client: OpenAIClient,
        course_client: CourseServiceClient,
        resource_extractor: ResourceTextExtractor,
    ):
        """Initialize instructor service with dependencies.

        Args:
            repo: CourseContentRepository for reading course data
            openai_client: OpenAIClient for LLM calls
            course_client: CourseServiceClient for persistence
            resource_extractor: ResourceTextExtractor for PDF extraction
        """
        self.repo = repo
        self.openai_client = openai_client
        self.course_client = course_client
        self.resource_extractor = resource_extractor

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
                logger.info(
                    "Summary generated and saved successfully",
                    course_id=course_id,
                    module_id=module_id,
                )
            else:
                logger.warning(
                    "Summary generated but failed to save to course-service",
                    course_id=course_id,
                    module_id=module_id,
                )

        except Exception as e:
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

            # Build persistence payload matching course-service QuizCreate schema
            payload = {
                "title": generated.title,
                "description": generated.description,
                "settings": {
                    "passing_score": request.passing_score,
                    "time_limit_minutes": request.time_limit_minutes,
                    "max_attempts": request.max_attempts,
                    "shuffle_questions": True,
                    "shuffle_options": True,
                    "show_correct_answers_after": "completion",
                },
                "questions": [
                    {
                        "order": q.order,
                        "question_text": q.question_text,
                        "question_type": q.question_type,
                        "options": (
                            [
                                {
                                    "option_id": opt.option_id,
                                    "text": opt.text,
                                    "is_correct": opt.is_correct,
                                }
                                for opt in q.options
                            ]
                            if q.options
                            else None
                        ),
                        "correct_answers": q.correct_answers,
                        "explanation": q.explanation,
                        "hint": q.hint,
                    }
                    for q in generated.questions
                ],
                "is_published": False,
            }

            # Save via HTTP to course-service
            result = await self.course_client.save_quiz(course_id, module_id, payload, user_id)
            if result:
                logger.info(
                    "Quiz generated and saved successfully",
                    course_id=course_id,
                    module_id=module_id,
                )
            else:
                logger.warning(
                    "Quiz generated but failed to save to course-service",
                    course_id=course_id,
                    module_id=module_id,
                )

        except Exception as e:
            logger.exception(
                "Error during quiz generation",
                course_id=course_id,
                module_id=module_id,
                error=str(e),
            )

    async def generate_all(
        self,
        course_id: int,
        module_id: str,
        request: GenerateAllRequest,
        user_id: int,
    ) -> GenerateAllResponse:
        """Generate both summary and quiz for a module (async tasks).

        Validates course ownership and module existence before kicking off both
        background tasks in parallel and returning immediately.

        Args:
            course_id: Course ID
            module_id: Module ID
            request: Combined generation request
            user_id: Authenticated instructor user ID

        Returns:
            GenerateAllResponse with both responses (status PENDING)
        """
        log = logger.bind(course_id=course_id, module_id=module_id, user_id=user_id)
        log.info("Generate-all requested (summary + quiz)")

        # Guard: validate before firing the background tasks
        await self._validate_course_ownership_and_module(course_id, module_id, user_id)

        log.info("Validation passed — dispatching summary and quiz generation tasks")

        # Fire both background tasks in parallel
        asyncio.create_task(
            self._process_and_save_summary(
                course_id,
                module_id,
                GenerateSummaryRequest(
                    source_lesson_ids=request.source_lesson_ids,
                    include_glossary=request.include_glossary,
                    include_key_points=request.include_key_points,
                    include_learning_objectives=request.include_learning_objectives,
                    language=request.summary_language,
                    tone=None,
                    max_length_words=None,
                ),
                user_id,
            )
        )
        asyncio.create_task(
            self._process_and_save_quiz(
                course_id,
                module_id,
                GenerateQuizRequest(
                    source_lesson_ids=request.source_lesson_ids,
                    num_questions=request.num_questions,
                    difficulty=request.difficulty,
                    question_types=request.question_types,
                    passing_score=70,
                    max_attempts=3,
                    time_limit_minutes=None,
                    language=request.quiz_language,
                ),
                user_id,
            )
        )

        summary = GenerateSummaryResponse(
            course_id=course_id,
            module_id=module_id,
            source_lesson_ids=request.source_lesson_ids or [],
            summary_id=None,
            status=GenerationStatus.PENDING,
            message="Summary generation started.",
        )
        quiz = GenerateQuizResponse(
            course_id=course_id,
            module_id=module_id,
            source_lesson_ids=request.source_lesson_ids or [],
            quiz_id=None,
            status=GenerationStatus.PENDING,
            message="Quiz generation started.",
        )

        return GenerateAllResponse(
            course_id=course_id,
            module_id=module_id,
            summary=summary,
            quiz=quiz,
        )

    async def get_generation_status(
        self, course_id: int, module_id: str
    ) -> GenerationStatusResponse:
        """Check generation status for a module.

        Args:
            course_id: Course ID
            module_id: Module ID

        Returns:
            GenerationStatusResponse with completion status and timestamps
        """
        # Check if summary and quiz exist
        existing_summary = await self.repo.get_existing_summary(course_id, module_id)
        existing_quiz = await self.repo.get_existing_quiz(course_id, module_id)

        # Determine status and timestamps
        summary_status = (
            GenerationStatus.COMPLETED if existing_summary else GenerationStatus.PENDING
        )
        quiz_status = GenerationStatus.COMPLETED if existing_quiz else GenerationStatus.PENDING

        last_generation_at = None
        if existing_summary:
            last_generation_at = existing_summary.get("created_at")
        if existing_quiz:
            quiz_created = existing_quiz.get("created_at")
            if quiz_created and (not last_generation_at or quiz_created > last_generation_at):
                last_generation_at = quiz_created

        return GenerationStatusResponse(
            course_id=course_id,
            module_id=module_id,
            summary_status=summary_status,
            quiz_status=quiz_status,
            last_generation_at=last_generation_at,
        )
