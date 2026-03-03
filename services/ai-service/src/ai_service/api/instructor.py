"""Instructor content generation API routes."""

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from ai_service.api.dependencies import require_instructor
from ai_service.core.mongodb import get_mongodb
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
from ai_service.services.instructor import InstructorService

router = APIRouter()

logger = structlog.get_logger(__name__)


def get_instructor_service() -> InstructorService:
    """Dependency injection function to build InstructorService with all dependencies."""
    db = get_mongodb()
    if db is None:
        raise RuntimeError("MongoDB connection not initialized")

    repo = CourseContentRepository(db)
    openai_client = OpenAIClient()
    course_client = CourseServiceClient()
    resource_extractor = ResourceTextExtractor()

    return InstructorService(repo, openai_client, course_client, resource_extractor)


@router.post(
    "/modules/{module_id}/generate-summary",
    response_model=GenerateSummaryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_summary(
    module_id: str,
    course_id: int,
    request: GenerateSummaryRequest,
    user_id: int = Depends(require_instructor),
    service: InstructorService = Depends(get_instructor_service),
) -> GenerateSummaryResponse:
    """Generate a summary for a module.

    Args:
        module_id: Module ID (bson ObjectId hex)
        course_id: Course ID (query parameter, required)
        request: Summary generation request body
        user_id: Authenticated instructor user ID (from dependency)
        service: InstructorService instance (dependency injection)

    Returns:
        GenerateSummaryResponse with generation status PENDING (work runs in background)
    """
    logger.info(
        "Received generate-summary request",
        course_id=course_id,
        module_id=module_id,
        user_id=user_id,
        source_lesson_ids=request.source_lesson_ids,
        include_glossary=request.include_glossary,
        include_key_points=request.include_key_points,
    )
    return await service.generate_summary(course_id, module_id, request, user_id)


@router.post(
    "/modules/{module_id}/generate-quiz",
    response_model=GenerateQuizResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_quiz(
    module_id: str,
    course_id: int,
    request: GenerateQuizRequest,
    user_id: int = Depends(require_instructor),
    service: InstructorService = Depends(get_instructor_service),
) -> GenerateQuizResponse:
    """Generate quiz questions for a module.

    Args:
        module_id: Module ID (bson ObjectId hex)
        course_id: Course ID (query parameter, required)
        request: Quiz generation request body
        user_id: Authenticated instructor user ID (from dependency)
        service: InstructorService instance (dependency injection)

    Returns:
        GenerateQuizResponse with generation status PENDING (work runs in background)
    """
    logger.info(
        "Received generate-quiz request",
        course_id=course_id,
        module_id=module_id,
        user_id=user_id,
        source_lesson_ids=request.source_lesson_ids,
        num_questions=request.num_questions,
        difficulty=request.difficulty,
        question_types=request.question_types,
    )
    return await service.generate_quiz(course_id, module_id, request, user_id)


@router.post(
    "/modules/{module_id}/generate-all",
    response_model=GenerateAllResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_all(
    module_id: str,
    course_id: int,
    request: GenerateAllRequest,
    user_id: int = Depends(require_instructor),
    service: InstructorService = Depends(get_instructor_service),
) -> GenerateAllResponse:
    """Generate both summary and quiz for a module.

    Args:
        module_id: Module ID (bson ObjectId hex)
        course_id: Course ID (query parameter, required)
        request: Combined generation request body
        user_id: Authenticated instructor user ID (from dependency)
        service: InstructorService instance (dependency injection)

    Returns:
        GenerateAllResponse with both responses (status PENDING, work runs in background)
    """
    return await service.generate_all(course_id, module_id, request, user_id)


@router.get(
    "/modules/{module_id}/generation-status",
    response_model=GenerationStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_generation_status(
    module_id: str,
    course_id: int,
    user_id: int = Depends(require_instructor),
    service: InstructorService = Depends(get_instructor_service),
) -> GenerationStatusResponse:
    """Check generation status for a module.

    Args:
        module_id: Module ID (bson ObjectId hex)
        course_id: Course ID (query parameter, required)
        user_id: Authenticated instructor user ID (from dependency)
        service: InstructorService instance (dependency injection)

    Returns:
        GenerationStatusResponse with current generation statuses
    """
    return await service.get_generation_status(course_id, module_id)
