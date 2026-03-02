from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from api.dependencies import get_current_user_id, require_instructor
from core.mongodb import get_mongodb
from core.s3 import get_s3_uploader
from schemas.course_content import (
    CourseContentCreate,
    CourseContentResponse,
    LessonCreate,
    LessonUpdate,
    MediaResourceCreate,
    MediaResourceUpdate,
    ModuleCreate,
    ModuleUpdate,
    ResourceSchema,
)
from services.course_content import CourseContentService
from shared.storage.s3 import S3Uploader

# ─── Map lesson type → S3 folder and allowed MIME category ───────────────────

LESSON_TYPE_CONFIG: dict[str, dict] = {
    "video": {"folder": "course-content/videos", "category": "video", "max_mb": 500},
    "text": {"folder": "course-content/documents", "category": "pdf", "max_mb": 50},
    "assignment": {"folder": "course-content/documents", "category": "document", "max_mb": 50},
    "quiz": {"folder": "course-content/images", "category": "image", "max_mb": 20},
}

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
    module_id: str,
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


@router.post(
    "/{course_id}/content/modules/{module_id}/lessons/with-file",
    response_model=CourseContentResponse,
    summary="Upload a file AND create a lesson in one multipart/form-data request",
)
async def add_lesson_with_file(
    course_id: int,
    module_id: str,
    # ── lesson metadata as Form fields ──
    title: str = Form(...),
    lesson_type: str = Form(..., alias="type"),
    order: int = Form(...),
    duration_minutes: Optional[int] = Form(None),
    is_preview: bool = Form(False),
    # ── optional file ──
    file: Optional[UploadFile] = File(
        None, description="Optional lesson file (video, pdf, image, etc.)"
    ),
    instructor_id: int = Depends(require_instructor),
    uploader: S3Uploader = Depends(get_s3_uploader),
) -> CourseContentResponse:
    """
    Create a lesson and optionally upload a file in a single multipart/form-data request.

    The uploaded file is stored in S3; its URL is written to `lesson.content`
    and an entry is appended to `lesson.resources`.

    Form fields:
    - title (str)
    - type (str): video | text | quiz | assignment
    - order (int)
    - duration_minutes (int, optional)
    - is_preview (bool, default false)
    - file (binary, optional)

    Allowed file types per lesson type:
    - video       → mp4, webm, ogg, quicktime, avi  (max 500 MB)
    - text        → pdf                              (max  50 MB)
    - assignment  → pdf, docx, xlsx, zip             (max  50 MB)
    - quiz        → jpeg, png, gif, webp, svg        (max  20 MB)
    """
    config = LESSON_TYPE_CONFIG.get(lesson_type)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid lesson type '{lesson_type}'. Must be one of: {list(LESSON_TYPE_CONFIG)}",
        )

    content_url: Optional[str] = None
    resources: list[ResourceSchema] = []

    if file and file.filename:
        try:
            result = await uploader.upload_file(
                file=file,
                folder=config["folder"],
                allowed_category=config["category"],
                max_size_mb=config["max_mb"],
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
        except RuntimeError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

        content_url = result.url
        resources.append(
            ResourceSchema(
                name=result.filename,
                url=result.url,
                type=result.content_type,
            )
        )

    lesson_data = LessonCreate(
        title=title,
        type=lesson_type,
        content=content_url,
        duration_minutes=duration_minutes,
        order=order,
        is_preview=is_preview,
        resources=resources,
    )

    db = get_mongodb()
    service = CourseContentService(db)
    content = await service.add_lesson(course_id, module_id, lesson_data)
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
    module_id: str,
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


@router.delete(
    "/{course_id}/content/modules/{module_id}",
    response_model=CourseContentResponse,
)
async def delete_module(
    course_id: int,
    module_id: str,
    instructor_id: int = Depends(require_instructor),
):
    """Soft-delete a module (set is_active=false) (instructors only)."""
    db = get_mongodb()
    service = CourseContentService(db)
    content = await service.delete_module(course_id, module_id)
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
    module_id: str,
    lesson_id: str,
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


@router.delete(
    "/{course_id}/content/modules/{module_id}/lessons/{lesson_id}",
    response_model=CourseContentResponse,
)
async def delete_lesson(
    course_id: int,
    module_id: str,
    lesson_id: str,
    instructor_id: int = Depends(require_instructor),
):
    """Soft-delete a lesson (set is_active=false) (instructors only)."""
    db = get_mongodb()
    service = CourseContentService(db)
    content = await service.delete_lesson(course_id, module_id, lesson_id)
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
    module_id: str,
    lesson_id: str,
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
    module_id: str,
    lesson_id: str,
    resource_index: int,
    data: MediaResourceUpdate,
    instructor_id: int = Depends(require_instructor),
):
    """Update a media resource by index (instructors only)."""
    db = get_mongodb()
    service = CourseContentService(db)
    content = await service.update_resource(course_id, module_id, lesson_id, resource_index, data)
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
    module_id: str,
    lesson_id: str,
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
