"""
File upload endpoint for course-service.

Generic upload (Pattern A) — Two-step (recommended for large files):
  1. POST /uploads/file  → returns { key, url, filename, content_type, size_bytes }
  2. Use the returned `url` in any lesson creation request:
     POST /{course_id}/content/modules/{module_id}/lessons   (JSON body)
     POST /{course_id}/content/modules/{module_id}/lessons/with-file  (multipart, in course_content router)
"""

from typing import Optional
import uuid as _uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from api.dependencies import require_instructor
from api.course_content import LESSON_TYPE_CONFIG
from core.s3 import get_s3_uploader
from schemas.course_content import S3UploadResponse
from shared.storage.s3 import S3Uploader

router = APIRouter()


# ─── Pattern A: standalone file upload ───────────────────────────────────────


@router.post(
    "/file",
    response_model=S3UploadResponse,
    summary="Generic file upload to S3 — returns key + URL for use in any lesson creation request",
)
async def upload_file(
    file: UploadFile = File(..., description="File to upload (video, pdf, audio, image)"),
    lesson_type: str = Form(..., description="video | text | quiz | audio"),
    instructor_id: _uuid.UUID = Depends(require_instructor),
    uploader: S3Uploader = Depends(get_s3_uploader),
) -> S3UploadResponse:
    """
    Generic file upload to S3.

    Returns the S3 key and URL. Use the `url` in the `content` field when
    calling either:
    - POST /{course_id}/content/modules/{module_id}/lessons  (JSON body)
    - POST /{course_id}/content/modules/{module_id}/lessons/with-file  (multipart)
    """
    config = LESSON_TYPE_CONFIG.get(lesson_type)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid lesson_type '{lesson_type}'. Must be one of: {list(LESSON_TYPE_CONFIG)}",
        )

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

    return S3UploadResponse(
        key=result.key,
        url=result.url,
        filename=result.filename,
        content_type=result.content_type,
        size_bytes=result.size_bytes,
    )
