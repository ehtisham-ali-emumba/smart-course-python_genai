"""RAG indexing API routes."""

from fastapi import APIRouter, Depends, status

from ai_service.api.dependencies import require_instructor, get_index_service
from ai_service.schemas.index import (
    BuildIndexRequest,
    IndexBuildResponse,
    IndexStatusResponse,
)
from ai_service.services.index import IndexService

router = APIRouter()


@router.post(
    "/courses/{course_id}/build",
    response_model=IndexBuildResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def build_course_index(
    course_id: int,
    request: BuildIndexRequest | None = None,
    user_id: int = Depends(require_instructor),
    index_service: IndexService = Depends(get_index_service),
) -> IndexBuildResponse:
    """Build index for entire course.

    Args:
        course_id: Course ID from path parameter
        request: Optional index build request with force_rebuild flag
        user_id: Authenticated instructor user ID (from dependency)
        index_service: IndexService from dependency injection

    Returns:
        IndexBuildResponse with build status
    """
    if request is None:
        request = BuildIndexRequest(force_rebuild=False)
    return await index_service.build_course_index(course_id, request)


@router.post(
    "/modules/{module_id}/build",
    response_model=IndexBuildResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def build_module_index(
    module_id: str,
    course_id: int,
    request: BuildIndexRequest | None = None,
    user_id: int = Depends(require_instructor),
    index_service: IndexService = Depends(get_index_service),
) -> IndexBuildResponse:
    """Build index for a single module.

    Args:
        module_id: Module ID from path parameter (bson ObjectId hex)
        course_id: Course ID (query parameter, required)
        request: Optional index build request with force_rebuild flag
        user_id: Authenticated instructor user ID (from dependency)
        index_service: IndexService from dependency injection

    Returns:
        IndexBuildResponse with build status
    """
    if request is None:
        request = BuildIndexRequest(force_rebuild=False)
    return await index_service.build_module_index(course_id, module_id, request)


@router.get(
    "/courses/{course_id}/status",
    response_model=IndexStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_course_index_status(
    course_id: int,
    user_id: int = Depends(require_instructor),
    index_service: IndexService = Depends(get_index_service),
) -> IndexStatusResponse:
    """Get index status for a course.

    Args:
        course_id: Course ID from path parameter
        user_id: Authenticated instructor user ID (from dependency)
        index_service: IndexService from dependency injection

    Returns:
        IndexStatusResponse with index status
    """
    return await index_service.get_course_status(course_id)


@router.get(
    "/modules/{module_id}/status",
    response_model=IndexStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_module_index_status(
    module_id: str,
    course_id: int,
    user_id: int = Depends(require_instructor),
    index_service: IndexService = Depends(get_index_service),
) -> IndexStatusResponse:
    """Get index status for a module.

    Args:
        module_id: Module ID from path parameter (bson ObjectId hex)
        course_id: Course ID (query parameter, required)
        user_id: Authenticated instructor user ID (from dependency)
        index_service: IndexService from dependency injection

    Returns:
        IndexStatusResponse with index status
    """
    return await index_service.get_module_status(course_id, module_id)
