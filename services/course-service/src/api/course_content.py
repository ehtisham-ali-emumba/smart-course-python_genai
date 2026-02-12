from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_current_user_id, require_instructor
from core.mongodb import get_mongodb
from schemas.course_content import (
    CourseContentCreate,
    CourseContentResponse,
    LessonCreate,
    ModuleCreate,
)
from services.course_content import CourseContentService

router = APIRouter()


@router.get("/{course_id}/content", response_model=CourseContentResponse)
async def get_course_content(
    course_id: int,
    user_id: int = Depends(get_current_user_id),
):
    """Get full course content (modules and lessons)."""
    db = get_mongodb()
    service = CourseContentService(db)
    content = await service.get_content(course_id)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course content not found",
        )
    return CourseContentResponse(**content)


@router.put("/{course_id}/content", response_model=CourseContentResponse)
async def upsert_course_content(
    course_id: int,
    data: CourseContentCreate,
    instructor_id: int = Depends(require_instructor),
):
    """Create or fully replace course content (instructors only)."""
    db = get_mongodb()
    service = CourseContentService(db)
    content = await service.create_or_update_content(course_id, data)
    return CourseContentResponse(**content)


@router.post("/{course_id}/content/modules", response_model=CourseContentResponse)
async def add_module(
    course_id: int,
    data: ModuleCreate,
    instructor_id: int = Depends(require_instructor),
):
    """Add a module to existing course content (instructors only)."""
    db = get_mongodb()
    service = CourseContentService(db)
    content = await service.add_module(course_id, data)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course content not found — create content first",
        )
    return CourseContentResponse(**content)


@router.post(
    "/{course_id}/content/modules/{module_id}/lessons",
    response_model=CourseContentResponse,
)
async def add_lesson(
    course_id: int,
    module_id: int,
    data: LessonCreate,
    instructor_id: int = Depends(require_instructor),
):
    """Add a lesson to a module (instructors only)."""
    db = get_mongodb()
    service = CourseContentService(db)
    content = await service.add_lesson(course_id, module_id, data)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course content or module not found",
        )
    return CourseContentResponse(**content)


@router.delete("/{course_id}/content", status_code=status.HTTP_204_NO_CONTENT)
async def delete_course_content(
    course_id: int,
    instructor_id: int = Depends(require_instructor),
):
    """Delete all content for a course (instructors only)."""
    db = get_mongodb()
    service = CourseContentService(db)
    deleted = await service.delete_content(course_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course content not found",
        )
