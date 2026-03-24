"""Instructor content generation API routes."""

import uuid as _uuid
import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from ai_service.api.dependencies import require_instructor, get_instructor_service
from ai_service.schemas.instructor import (
    GenerateSummaryRequest,
    GenerateSummaryResponse,
    GenerateQuizRequest,
    GenerateQuizResponse,
    GenerationStatusResponse,
)
from ai_service.services.instructor import InstructorService

router = APIRouter()

logger = structlog.get_logger(__name__)


@router.post(
    "/modules/{module_id}/generate-summary",
    response_model=GenerateSummaryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_summary(
    module_id: str,
    course_id: _uuid.UUID,
    request: GenerateSummaryRequest,
    instructor: tuple[_uuid.UUID, _uuid.UUID] = Depends(require_instructor),
    service: InstructorService = Depends(get_instructor_service),
) -> GenerateSummaryResponse:
    """Generate a summary for a module.

    Args:
        module_id: Module ID (bson ObjectId hex)
        course_id: Course ID (query parameter, required)
        request: Summary generation request body
        instructor: Authenticated instructor context (user_id, profile_id)
        service: InstructorService instance (dependency injection)

    Returns:
        GenerateSummaryResponse with generation status PENDING (work runs in background)
    """
    user_id, profile_id = instructor

    logger.info(
        "Received generate-summary request",
        course_id=course_id,
        module_id=module_id,
        user_id=user_id,
        source_lesson_ids=request.source_lesson_ids,
        include_glossary=request.include_glossary,
        include_key_points=request.include_key_points,
    )
    return await service.generate_summary(course_id, module_id, request, user_id, profile_id)


@router.post(
    "/modules/{module_id}/generate-quiz",
    response_model=GenerateQuizResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_quiz(
    module_id: str,
    course_id: _uuid.UUID,
    request: GenerateQuizRequest,
    instructor: tuple[_uuid.UUID, _uuid.UUID] = Depends(require_instructor),
    service: InstructorService = Depends(get_instructor_service),
) -> GenerateQuizResponse:
    """Generate quiz questions for a module.

    Args:
        module_id: Module ID (bson ObjectId hex)
        course_id: Course ID (query parameter, required)
        request: Quiz generation request body
        instructor: Authenticated instructor context (user_id, profile_id)
        service: InstructorService instance (dependency injection)

    Returns:
        GenerateQuizResponse with generation status PENDING (work runs in background)
    """
    user_id, profile_id = instructor

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
    return await service.generate_quiz(course_id, module_id, request, user_id, profile_id)


@router.get(
    "/modules/{module_id}/generation-status",
    response_model=GenerationStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_generation_status(
    module_id: str,
    course_id: _uuid.UUID,
    _instructor: tuple[_uuid.UUID, _uuid.UUID] = Depends(require_instructor),
    service: InstructorService = Depends(get_instructor_service),
) -> GenerationStatusResponse:
    """Check generation status for a module.

    Args:
        module_id: Module ID (bson ObjectId hex)
        course_id: Course ID (query parameter, required)
        _instructor: Authenticated instructor context (user_id, profile_id)
        service: InstructorService instance (dependency injection)

    Returns:
        GenerationStatusResponse with current generation statuses
    """
    return await service.get_generation_status(course_id, module_id)
