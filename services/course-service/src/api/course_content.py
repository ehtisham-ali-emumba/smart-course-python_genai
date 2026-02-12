from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_current_user_id, require_instructor
from core.mongodb import get_mongodb
from schemas.course_content import (
    CourseContentCreate,
    CourseContentResponse,
    LessonCreate,
    LessonUpdate,
    MediaResourceCreate,
    MediaResourceUpdate,
    ModuleCreate,
    ModuleUpdate,
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


@router.patch(
    "/{course_id}/content/modules/{module_id}",
    response_model=CourseContentResponse,
)
async def update_module(
    course_id: int,
    module_id: int,
    data: ModuleUpdate,
    instructor_id: int = Depends(require_instructor),
):
    """Update a module (instructors only)."""
    db = get_mongodb()
    service = CourseContentService(db)
    content = await service.update_module(course_id, module_id, data)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course content or module not found",
        )
    return CourseContentResponse(**content)


@router.patch(
    "/{course_id}/content/modules/{module_id}/lessons/{lesson_id}",
    response_model=CourseContentResponse,
)
async def update_lesson(
    course_id: int,
    module_id: int,
    lesson_id: int,
    data: LessonUpdate,
    instructor_id: int = Depends(require_instructor),
):
    """Update a lesson (instructors only)."""
    db = get_mongodb()
    service = CourseContentService(db)
    content = await service.update_lesson(course_id, module_id, lesson_id, data)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course content, module, or lesson not found",
        )
    return CourseContentResponse(**content)


@router.post(
    "/{course_id}/content/modules/{module_id}/lessons/{lesson_id}/resources",
    response_model=CourseContentResponse,
)
async def add_media_resource(
    course_id: int,
    module_id: int,
    lesson_id: int,
    data: MediaResourceCreate,
    instructor_id: int = Depends(require_instructor),
):
    """Add media resource (video, pdf, audio, image) to a lesson (instructors only)."""
    db = get_mongodb()
    service = CourseContentService(db)
    content = await service.add_resource(course_id, module_id, lesson_id, data)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course content, module, or lesson not found",
        )
    return CourseContentResponse(**content)


@router.patch(
    "/{course_id}/content/modules/{module_id}/lessons/{lesson_id}/resources/{resource_index}",
    response_model=CourseContentResponse,
)
async def update_media_resource(
    course_id: int,
    module_id: int,
    lesson_id: int,
    resource_index: int,
    data: MediaResourceUpdate,
    instructor_id: int = Depends(require_instructor),
):
    """Update a media resource by index (instructors only)."""
    db = get_mongodb()
    service = CourseContentService(db)
    content = await service.update_resource(
        course_id, module_id, lesson_id, resource_index, data
    )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course content, module, lesson, or resource not found",
        )
    return CourseContentResponse(**content)


@router.delete(
    "/{course_id}/content/modules/{module_id}/lessons/{lesson_id}/resources/{resource_index}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_media_resource(
    course_id: int,
    module_id: int,
    lesson_id: int,
    resource_index: int,
    instructor_id: int = Depends(require_instructor),
):
    """Delete a media resource by index (instructors only)."""
    db = get_mongodb()
    service = CourseContentService(db)
    deleted = await service.delete_resource(course_id, module_id, lesson_id, resource_index)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course content, module, lesson, or resource not found",
        )


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
