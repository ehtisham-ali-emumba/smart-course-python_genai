"""Instructor content generation API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from ai_service.api.dependencies import require_instructor
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
instructor_service = InstructorService()


@router.post(
    "/modules/{module_id}/generate-summary",
    response_model=GenerateSummaryResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_summary(
    module_id: str,
    course_id: int,
    request: GenerateSummaryRequest,
    user_id: int = Depends(require_instructor),
) -> GenerateSummaryResponse:
    """Generate a summary for a module.

    Args:
        module_id: Module ID (bson ObjectId hex)
        course_id: Course ID (query parameter, required)
        request: Summary generation request body
        user_id: Authenticated instructor user ID (from dependency)

    Returns:
        GenerateSummaryResponse with generation status
    """
    # TODO: Validate that course_id and module_id exist in MongoDB course_content
    # TODO: If source_lesson_ids provided, validate they exist in the module
    # TODO: Call instructor service to generate summary via LLM
    # TODO: Persist result via course-service summary CRUD
    return await instructor_service.generate_summary(course_id, module_id, request)


@router.post(
    "/modules/{module_id}/generate-quiz",
    response_model=GenerateQuizResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_quiz(
    module_id: str,
    course_id: int,
    request: GenerateQuizRequest,
    user_id: int = Depends(require_instructor),
) -> GenerateQuizResponse:
    """Generate quiz questions for a module.

    Args:
        module_id: Module ID (bson ObjectId hex)
        course_id: Course ID (query parameter, required)
        request: Quiz generation request body
        user_id: Authenticated instructor user ID (from dependency)

    Returns:
        GenerateQuizResponse with generation status
    """
    # TODO: Validate that course_id and module_id exist
    # TODO: If source_lesson_ids provided, validate they exist in the module
    # TODO: Call instructor service to generate quiz
    # TODO: Persist result via course-service quiz CRUD
    return await instructor_service.generate_quiz(course_id, module_id, request)


@router.post(
    "/modules/{module_id}/generate-all",
    response_model=GenerateAllResponse,
    status_code=status.HTTP_200_OK,
)
async def generate_all(
    module_id: str,
    course_id: int,
    request: GenerateAllRequest,
    user_id: int = Depends(require_instructor),
) -> GenerateAllResponse:
    """Generate both summary and quiz for a module.

    Args:
        module_id: Module ID (bson ObjectId hex)
        course_id: Course ID (query parameter, required)
        request: Combined generation request body
        user_id: Authenticated instructor user ID (from dependency)

    Returns:
        GenerateAllResponse with both summary and quiz responses
    """
    # TODO: Validate course and module
    return await instructor_service.generate_all(course_id, module_id, request)


@router.get(
    "/modules/{module_id}/generation-status",
    response_model=GenerationStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_generation_status(
    module_id: str,
    course_id: int,
    user_id: int = Depends(require_instructor),
) -> GenerationStatusResponse:
    """Check generation status for a module.

    Args:
        module_id: Module ID (bson ObjectId hex)
        course_id: Course ID (query parameter, required)
        user_id: Authenticated instructor user ID (from dependency)

    Returns:
        GenerationStatusResponse with current generation statuses
    """
    # TODO: Check if quiz/summary exist for this module and their generation metadata
    return await instructor_service.get_generation_status(course_id, module_id)
