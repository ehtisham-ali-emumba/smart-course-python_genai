# S3 File Upload — Centralized Implementation Guide

**Date:** March 2, 2026  
**Scope:** AWS S3 bucket setup → centralized `shared` upload utility → `course-service` lesson file upload endpoints  
**Services affected:** `shared`, `course-service` (and ready for `user-service`)

---

## Table of Contents

1. [AWS S3 Bucket Setup](#1-aws-s3-bucket-setup)
2. [IAM User & Permissions](#2-iam-user--permissions)
3. [CORS Configuration](#3-cors-configuration)
4. [Environment Variables](#4-environment-variables)
5. [Centralized S3 Utility in `shared`](#5-centralized-s3-utility-in-shared)
6. [course-service Integration](#6-course-service-integration)
7. [New API Endpoints](#7-new-api-endpoints)
8. [Docker Compose Updates](#8-docker-compose-updates)
9. [Testing with Postman](#9-testing-with-postman)
10. [How It All Fits Together](#10-how-it-all-fits-together)

---

## 1. AWS S3 Bucket Setup

### Step 1 — Create the Bucket

1. Go to **https://console.aws.amazon.com/s3**
2. Click **"Create bucket"**
3. Fill in:
   | Field | Value |
   |-------|-------|
   | **Bucket name** | `smartcourse-uploads` (must be globally unique — append your name/id if taken, e.g. `smartcourse-uploads-bucket`) |
   | **AWS Region** | Choose the region closest to your users, e.g. `ap-south-1` (Mumbai) or `us-east-1` |
   | **Object Ownership** | Keep default: **ACLs disabled** |
   | **Block Public Access** | Keep **all four checkboxes checked** (we use pre-signed URLs, never public objects) |
   | **Versioning** | Disabled (enable later if you need version history) |
   | **Encryption** | SSE-S3 (server-side encryption, enabled by default) |

4. Click **"Create bucket"**

### Step 2 — Note Your Bucket Details

After creation you will need:

- **Bucket name** — e.g. `smartcourse-uploads-bucket`
- **Region** — e.g. `ap-south-1`

> **Why no public access?**  
> Files are served via pre-signed URLs that expire after a configurable time (default 1 hour in this guide). Students never get permanent public links. This gives you access control for paid content.

---

## 2. IAM User & Permissions

Never use your root AWS account credentials in application code. Create a dedicated IAM user with minimum permissions.

### Step 1 — Create an IAM User

1. Go to **IAM → Users → "Create user"**
2. Username: `smartcourse-s3-uploader`
3. **Access type:** Programmatic access only (no AWS Console login needed)
4. Click **"Next: Permissions"**

### Step 2 — Attach a Permissions Policy

Click **"Attach policies directly"** → **"Create policy"** → **JSON tab** → paste:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SmartCourseS3Access",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:GetObjectAttributes"
      ],
      "Resource": "arn:aws:s3:::smartcourse-uploads-bucket/*"
    },
    {
      "Sid": "SmartCourseListBucket",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::smartcourse-uploads-bucket"
    }
  ]
}
```

> Replace `smartcourse-uploads-bucket` with your actual bucket name in both `Resource` lines.

3. Name the policy: `SmartCourseS3Policy`
4. Save, go back, attach it to the `smartcourse-s3-uploader` user
5. After creation click **"Create access key"** → choose **"Application running outside AWS"**
6. **Download the CSV** — this is the only time you see the secret key

You now have:

- `AWS_ACCESS_KEY_ID` — starts with `AKIA...`
- `AWS_SECRET_ACCESS_KEY` — long string

---

## 3. CORS Configuration

This is needed if you ever upload directly from a browser (presigned PUT URLs). Even if you upload server-side today, set it up now.

1. Go to your bucket → **Permissions** tab → scroll to **"Cross-origin resource sharing (CORS)"**
2. Click **Edit** and paste:

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["GET", "PUT", "POST", "DELETE", "HEAD"],
    "AllowedOrigins": ["*"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3000
  }
]
```

> For production, replace `"*"` in `AllowedOrigins` with your actual frontend domain, e.g. `"https://smartcourse.com"`.

---

## 4. Environment Variables

### 4.1 — `course-service/.env`

Add these S3 variables alongside your existing ones:

```dotenv
# ─── Existing vars ───────────────────────────────────
DATABASE_URL=postgresql+asyncpg://...
MONGODB_URL=mongodb://...
MONGODB_DB_NAME=smartcourse
REDIS_URL=redis://...
KAFKA_BOOTSTRAP_SERVERS=...
SCHEMA_REGISTRY_URL=...

# ─── S3 File Upload (NEW) ────────────────────────────
AWS_ACCESS_KEY_ID=AKIAxxxxxxxxxxxxxxxxx
AWS_SECRET_ACCESS_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AWS_REGION=ap-south-1
S3_BUCKET_NAME=smartcourse-uploads-bucket
S3_PRESIGNED_URL_EXPIRY=3600        # seconds (1 hour)
S3_MAX_FILE_SIZE_MB=500             # hard limit enforced server-side
```

### 4.2 — `user-service/.env` (for future avatar/document uploads)

Add the same S3 block:

```dotenv
AWS_ACCESS_KEY_ID=AKIAxxxxxxxxxxxxxxxxx
AWS_SECRET_ACCESS_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AWS_REGION=ap-south-1
S3_BUCKET_NAME=smartcourse-uploads-bucket
S3_PRESIGNED_URL_EXPIRY=3600
S3_MAX_FILE_SIZE_MB=10
```

> You can use the **same bucket** for both services — they just use different key prefixes (folder paths) inside the bucket, e.g. `course-content/` vs `user-avatars/`.

---

## 5. Centralized S3 Utility in `shared`

### Why centralize?

Both `course-service` (video, PDF, audio lesson files) and `user-service` (profile picture, resume) upload to S3. Putting the logic once in `shared` means:

- One place to update credentials/logic
- Consistent error handling across services
- DRY — no copy-paste

### 5.1 — Add `boto3` to `shared/pyproject.toml`

File: `shared/pyproject.toml`

```toml
[project]
name = "shared"
version = "0.1.0"
description = "Shared library for SmartCourse microservices"
authors = [
    {name = "SmartCourse Team"}
]
dependencies = [
    "pydantic",
    "aiokafka",
    "confluent-kafka",
    "fastapi",
    "uvicorn",
    "boto3>=1.34.0",          # ← ADD THIS
    "botocore>=1.34.0",       # ← ADD THIS
    "python-multipart>=0.0.6" # ← ADD THIS (for UploadFile support)
]
```

### 5.2 — Create `shared/src/shared/storage/__init__.py`

```python
# shared/src/shared/storage/__init__.py
```

_(empty file — marks the directory as a Python package)_

### 5.3 — Create `shared/src/shared/storage/s3.py`

This is the core utility. Create the file at `shared/src/shared/storage/s3.py`:

```python
"""
Centralized AWS S3 upload utility for SmartCourse microservices.

Usage:
    from shared.storage.s3 import S3Uploader, S3UploadResult

    uploader = S3Uploader(
        bucket=settings.S3_BUCKET_NAME,
        region=settings.AWS_REGION,
        access_key=settings.AWS_ACCESS_KEY_ID,
        secret_key=settings.AWS_SECRET_ACCESS_KEY,
    )

    result = await uploader.upload_file(
        file=upload_file,          # FastAPI UploadFile
        folder="course-content",   # S3 "folder" prefix
        max_size_mb=500,
    )

    print(result.url)              # permanent S3 URL (private)
    print(result.key)              # S3 object key
"""

import asyncio
import mimetypes
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

import boto3
import structlog
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import UploadFile

logger = structlog.get_logger(__name__)

# ─── Allowed MIME types per upload category ────────────────────────────────────

ALLOWED_MIME_TYPES: dict[str, list[str]] = {
    "video": [
        "video/mp4",
        "video/webm",
        "video/ogg",
        "video/quicktime",
        "video/x-msvideo",
    ],
    "pdf": [
        "application/pdf",
    ],
    "audio": [
        "audio/mpeg",
        "audio/ogg",
        "audio/wav",
        "audio/webm",
    ],
    "image": [
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/svg+xml",
    ],
    "document": [
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
    ],
}

# Flattened set for quick membership checks when category is "any"
ALL_ALLOWED_MIME_TYPES: set[str] = {
    mime for mimes in ALLOWED_MIME_TYPES.values() for mime in mimes
}


# ─── Result dataclass ─────────────────────────────────────────────────────────


@dataclass
class S3UploadResult:
    """Result of a successful S3 upload."""

    key: str             # full S3 object key, e.g. "course-content/abc123.mp4"
    bucket: str          # bucket name
    region: str          # AWS region
    filename: str        # original file name supplied by client
    content_type: str    # detected MIME type
    size_bytes: int      # uploaded file size

    @property
    def url(self) -> str:
        """Permanent (non-expiring) S3 URL. Objects are private; use presigned_url() for access."""
        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{self.key}"


# ─── Uploader ─────────────────────────────────────────────────────────────────


class S3Uploader:
    """
    Async-friendly wrapper around boto3 S3 client.

    boto3 is not natively async; uploads are run via asyncio.to_thread()
    so they do not block the FastAPI event loop.
    """

    def __init__(
        self,
        bucket: str,
        region: str,
        access_key: str,
        secret_key: str,
    ) -> None:
        self._bucket = bucket
        self._region = region
        self._client = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    # ── Public interface ──────────────────────────────────────────────────────

    async def upload_file(
        self,
        file: UploadFile,
        folder: str,
        *,
        allowed_category: Optional[str] = None,
        max_size_mb: float = 500.0,
    ) -> S3UploadResult:
        """
        Validate and upload a FastAPI UploadFile to S3.

        Args:
            file:              FastAPI UploadFile from the request.
            folder:            S3 key prefix / "folder", e.g. "course-content/videos".
            allowed_category:  One of ("video","pdf","audio","image","document") or None
                               for any allowed type.
            max_size_mb:       Hard size limit in megabytes.

        Returns:
            S3UploadResult with the key, url, and metadata.

        Raises:
            ValueError:  Validation failures (type, size, no content).
            RuntimeError: S3 upload failures.
        """
        content = await file.read()
        if not content:
            raise ValueError("Uploaded file is empty.")

        size_bytes = len(content)
        max_bytes = int(max_size_mb * 1024 * 1024)
        if size_bytes > max_bytes:
            raise ValueError(
                f"File size {size_bytes / 1024 / 1024:.1f} MB exceeds "
                f"the {max_size_mb} MB limit."
            )

        content_type = self._detect_mime(file, content)
        self._validate_mime(content_type, allowed_category)

        ext = self._extension_for(content_type, file.filename or "")
        key = f"{folder.rstrip('/')}/{uuid.uuid4().hex}{ext}"

        logger.info(
            "s3_upload_start",
            key=key,
            bucket=self._bucket,
            size_bytes=size_bytes,
            content_type=content_type,
        )

        await asyncio.to_thread(
            self._sync_upload,
            content=content,
            key=key,
            content_type=content_type,
        )

        logger.info("s3_upload_success", key=key)

        return S3UploadResult(
            key=key,
            bucket=self._bucket,
            region=self._region,
            filename=file.filename or "",
            content_type=content_type,
            size_bytes=size_bytes,
        )

    async def delete_file(self, key: str) -> None:
        """Delete an object from S3 by its key."""
        try:
            await asyncio.to_thread(
                self._client.delete_object,
                Bucket=self._bucket,
                Key=key,
            )
            logger.info("s3_delete_success", key=key)
        except (BotoCoreError, ClientError) as exc:
            logger.error("s3_delete_failed", key=key, error=str(exc))
            raise RuntimeError(f"S3 delete failed for key '{key}': {exc}") from exc

    async def generate_presigned_url(
        self,
        key: str,
        expiry_seconds: int = 3600,
    ) -> str:
        """
        Generate a temporary pre-signed GET URL for a private S3 object.

        The URL is valid for `expiry_seconds` seconds (default 1 hour).
        """
        try:
            url: str = await asyncio.to_thread(
                self._client.generate_presigned_url,
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expiry_seconds,
            )
            return url
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeError(f"Could not generate presigned URL: {exc}") from exc

    # ── Private helpers ───────────────────────────────────────────────────────

    def _sync_upload(self, *, content: bytes, key: str, content_type: str) -> None:
        """Blocking S3 put_object — always call inside asyncio.to_thread."""
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
            )
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeError(f"S3 upload failed: {exc}") from exc

    @staticmethod
    def _detect_mime(file: UploadFile, content: bytes) -> str:
        """
        Determine MIME type using:
        1. FastAPI-supplied content_type header
        2. Guessing from filename extension
        3. Fallback: application/octet-stream
        """
        ct = (file.content_type or "").strip().lower()
        if ct and ct != "application/octet-stream":
            return ct
        if file.filename:
            guessed, _ = mimetypes.guess_type(file.filename)
            if guessed:
                return guessed
        return "application/octet-stream"

    @staticmethod
    def _validate_mime(content_type: str, category: Optional[str]) -> None:
        if category is None:
            if content_type not in ALL_ALLOWED_MIME_TYPES:
                raise ValueError(
                    f"File type '{content_type}' is not allowed. "
                    f"Allowed types: {sorted(ALL_ALLOWED_MIME_TYPES)}"
                )
        else:
            allowed = ALLOWED_MIME_TYPES.get(category, [])
            if content_type not in allowed:
                raise ValueError(
                    f"File type '{content_type}' is not allowed for category '{category}'. "
                    f"Allowed: {allowed}"
                )

    @staticmethod
    def _extension_for(content_type: str, filename: str) -> str:
        """Return the file extension to use for the S3 key."""
        # Prefer the original extension if present
        if "." in filename:
            return "." + filename.rsplit(".", 1)[-1].lower()
        # Fall back to guessing from MIME
        ext = mimetypes.guess_extension(content_type)
        return ext if ext else ""
```

### 5.4 — Export from `shared/__init__.py`

Open `shared/src/shared/__init__.py` and add:

```python
# Existing exports (keep whatever is already here) ...

# S3
from shared.storage.s3 import S3Uploader, S3UploadResult  # noqa: F401
```

### 5.5 — Rebuild the shared package inside Docker

The `shared` package is installed as an editable install (`pip install -e ./shared`) inside Docker. After adding new files the containers pick up changes automatically in dev (because of the volume mount). But after adding a new dependency (`boto3`) you must rebuild:

```bash
docker compose build shared course-service user-service
# or rebuild everything:
docker compose build
```

---

## 6. course-service Integration

### 6.1 — Update `course-service/src/config.py`

Add the S3 settings to `Settings`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # PostgreSQL
    DATABASE_URL: str

    # MongoDB
    MONGODB_URL: str
    MONGODB_DB_NAME: str

    # Redis
    REDIS_URL: str

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str
    SCHEMA_REGISTRY_URL: str

    # ── S3 File Upload ────────────────────────────────
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str
    S3_BUCKET_NAME: str
    S3_PRESIGNED_URL_EXPIRY: int = 3600
    S3_MAX_FILE_SIZE_MB: float = 500.0

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()  # type: ignore[call-arg]
```

### 6.2 — Create `course-service/src/core/s3.py`

This file creates a single shared `S3Uploader` instance (dependency injection pattern):

```python
"""S3 uploader singleton for course-service."""

from functools import lru_cache

from shared.storage.s3 import S3Uploader

from config import settings


@lru_cache(maxsize=1)
def get_s3_uploader() -> S3Uploader:
    """Return a cached S3Uploader configured from settings."""
    return S3Uploader(
        bucket=settings.S3_BUCKET_NAME,
        region=settings.AWS_REGION,
        access_key=settings.AWS_ACCESS_KEY_ID,
        secret_key=settings.AWS_SECRET_ACCESS_KEY,
    )
```

### 6.3 — Update `course-service/src/schemas/course_content.py`

Add an `S3UploadResponse` schema that the new upload endpoints return:

```python
# Add this at the bottom of the file, after the existing schemas

class S3UploadResponse(BaseModel):
    """Returned after a successful file upload to S3."""
    key: str                  # S3 object key, store this in MongoDB
    url: str                  # Permanent S3 URL  (private — use presigned for access)
    filename: str             # Original filename uploaded by the client
    content_type: str         # Detected MIME type
    size_bytes: int           # File size in bytes

class PresignedUrlResponse(BaseModel):
    """Time-limited URL for accessing a private S3 file."""
    presigned_url: str
    expires_in_seconds: int
    key: str
```

### 6.4 — Create `course-service/src/api/uploads.py`

This is the new upload router. It provides:

1. A **standalone** file upload endpoint that returns S3 key + URL for use in other requests.
2. A **combined** endpoint that uploads a file **and** adds the lesson in one request.
3. A **presigned URL** endpoint to generate temporary access links for private files.

```python
"""
File upload endpoints for course-service.

Two upload patterns are supported:

Pattern A — Two-step (recommended for large files):
  1. POST /uploads/lesson-file  → returns { key, url }
  2. POST /{course_id}/content/modules/{module_id}/lessons
        with the url already filled in the JSON body

Pattern B — One-step combined:
  POST /{course_id}/content/modules/{module_id}/lessons/with-file
  multipart/form-data with both JSON lesson fields + an uploaded file
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from api.dependencies import require_instructor
from config import settings
from core.mongodb import get_mongodb
from core.s3 import get_s3_uploader
from schemas.course_content import (
    CourseContentResponse,
    LessonCreate,
    PresignedUrlResponse,
    ResourceSchema,
    S3UploadResponse,
)
from services.course_content import CourseContentService
from shared.storage.s3 import S3Uploader

router = APIRouter()

# ─── Map lesson type → S3 folder and allowed MIME category ───────────────────

LESSON_TYPE_CONFIG: dict[str, dict] = {
    "video":      {"folder": "course-content/videos",    "category": "video",    "max_mb": 500},
    "text":       {"folder": "course-content/documents", "category": "pdf",      "max_mb": 50},
    "assignment": {"folder": "course-content/documents", "category": "document", "max_mb": 50},
    "quiz":       {"folder": "course-content/images",    "category": "image",    "max_mb": 20},
}


# ─── Pattern A: standalone file upload ───────────────────────────────────────


@router.post(
    "/lesson-file",
    response_model=S3UploadResponse,
    summary="Upload a file to S3 (returns key + URL for use in lesson creation)",
)
async def upload_lesson_file(
    file: UploadFile = File(..., description="File to upload (video, pdf, audio, image)"),
    lesson_type: str = Form(..., description="video | text | quiz | assignment"),
    instructor_id: int = Depends(require_instructor),
    uploader: S3Uploader = Depends(get_s3_uploader),
) -> S3UploadResponse:
    """
    Upload a lesson file to S3.

    Returns the S3 key and URL. Use the `url` in the `content` field when
    calling POST /{course_id}/content/modules/{module_id}/lessons.
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


# ─── Pattern B: combined upload + lesson creation ────────────────────────────


@router.post(
    "/{course_id}/modules/{module_id}/lessons/with-file",
    response_model=CourseContentResponse,
    summary="Upload a file AND create a lesson in one request (multipart/form-data)",
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
    file: Optional[UploadFile] = File(None, description="Optional lesson file"),
    instructor_id: int = Depends(require_instructor),
    uploader: S3Uploader = Depends(get_s3_uploader),
) -> CourseContentResponse:
    """
    Create a lesson and optionally attach a file in one multipart/form-data request.

    The uploaded file URL is stored in `lesson.content`.
    An additional entry is also added to `lesson.resources`.

    Form fields:
    - title (str)
    - type (str): video | text | quiz | assignment
    - order (int)
    - duration_minutes (int, optional)
    - is_preview (bool, default false)
    - file (binary, optional)
    """
    config = LESSON_TYPE_CONFIG.get(lesson_type)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid lesson type '{lesson_type}'.",
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


# ─── Presigned URL for accessing a private file ───────────────────────────────


@router.get(
    "/presigned-url",
    response_model=PresignedUrlResponse,
    summary="Generate a temporary pre-signed URL to access a private S3 file",
)
async def get_presigned_url(
    key: str,
    user_id: int = Depends(require_instructor),   # or use get_current_user_id to allow students too
    uploader: S3Uploader = Depends(get_s3_uploader),
) -> PresignedUrlResponse:
    """
    Generate a time-limited URL for accessing a private S3 object.

    Query param:
    - key: The S3 object key (returned from the upload endpoint)
    """
    expiry = settings.S3_PRESIGNED_URL_EXPIRY
    try:
        url = await uploader.generate_presigned_url(key=key, expiry_seconds=expiry)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return PresignedUrlResponse(
        presigned_url=url,
        expires_in_seconds=expiry,
        key=key,
    )
```

### 6.5 — Register the Router in `course-service/src/main.py`

Find the section where other routers are registered and add:

```python
from api.uploads import router as uploads_router

# In the app setup, alongside the other include_router calls:
app.include_router(
    uploads_router,
    prefix="/api/v1/uploads",
    tags=["File Uploads"],
)

# The combined lesson+file endpoint is nested under courses:
app.include_router(
    uploads_router,
    prefix="/api/v1/courses",
    tags=["Lessons with File Upload"],
    include_in_schema=False,  # avoids duplicates in Swagger; set True if you want both
)
```

> **Tip:** If you prefer to keep it cleaner, split `uploads.py` into two files: `upload_standalone.py` and `upload_lesson.py` — but one file with both is fine for now.

---

## 7. New API Endpoints

After implementation these endpoints are available (all behind API Gateway JWT auth):

| Method | Path                                                                | Description                             |
| ------ | ------------------------------------------------------------------- | --------------------------------------- |
| `POST` | `/api/v1/uploads/lesson-file`                                       | Upload file to S3, get back key + URL   |
| `POST` | `/api/v1/courses/{course_id}/modules/{module_id}/lessons/with-file` | Upload file + create lesson in one shot |
| `GET`  | `/api/v1/uploads/presigned-url?key=...`                             | Get temp access URL for private S3 file |

### Request Example — Pattern A (two-step)

**Step 1: Upload the file**

```
POST /api/v1/uploads/lesson-file
Content-Type: multipart/form-data
Authorization: Bearer <token>

file=@intro-video.mp4
lesson_type=video
```

Response:

```json
{
  "key": "course-content/videos/a3f9e1b2c4d5.mp4",
  "url": "https://smartcourse-uploads-bucket.s3.ap-south-1.amazonaws.com/course-content/videos/a3f9e1b2c4d5.mp4",
  "filename": "intro-video.mp4",
  "content_type": "video/mp4",
  "size_bytes": 52428800
}
```

**Step 2: Create the lesson using the URL**

```
POST /api/v1/courses/2/content/modules/699bee9c.../lessons
Content-Type: application/json
Authorization: Bearer <token>

{
  "title": "Welcome Video",
  "type": "video",
  "content": "https://smartcourse-uploads-bucket.s3.ap-south-1.amazonaws.com/course-content/videos/a3f9e1b2c4d5.mp4",
  "duration_minutes": 10,
  "order": 1,
  "is_preview": true,
  "resources": [
    {
      "name": "intro-video.mp4",
      "url": "https://smartcourse-uploads-bucket.s3.ap-south-1.amazonaws.com/course-content/videos/a3f9e1b2c4d5.mp4",
      "type": "video/mp4"
    }
  ]
}
```

### Request Example — Pattern B (one-step)

```
POST /api/v1/courses/2/modules/699bee9c.../lessons/with-file
Content-Type: multipart/form-data
Authorization: Bearer <token>

title=Welcome Video
type=video
order=1
duration_minutes=10
is_preview=true
file=@intro-video.mp4
```

### What ends up in MongoDB

```json
{
  "lesson_id": "699bee9cdd6f577f84b58eef",
  "title": "Welcome Video",
  "type": "video",
  "content": "https://smartcourse-uploads-bucket.s3.ap-south-1.amazonaws.com/course-content/videos/a3f9e1b2c4d5.mp4",
  "duration_minutes": 10,
  "order": 1,
  "is_preview": true,
  "is_active": true,
  "resources": [
    {
      "resource_id": "...",
      "name": "intro-video.mp4",
      "url": "https://smartcourse-uploads-bucket.s3.ap-south-1.amazonaws.com/...",
      "type": "video/mp4",
      "is_active": true
    }
  ]
}
```

---

## 8. Docker Compose Updates

### 8.1 — Add S3 env to course-service in `docker-compose.yml`

Find the `course-service` block and add the S3 environment variables:

```yaml
course-service:
  build: ./services/course-service
  environment:
    # ... existing vars ...
    AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID}
    AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY}
    AWS_REGION: ${AWS_REGION}
    S3_BUCKET_NAME: ${S3_BUCKET_NAME}
    S3_PRESIGNED_URL_EXPIRY: ${S3_PRESIGNED_URL_EXPIRY:-3600}
    S3_MAX_FILE_SIZE_MB: ${S3_MAX_FILE_SIZE_MB:-500}
```

### 8.2 — Root `.env` file (used by docker-compose)

Create or update the root `.env` at the project root (same level as `docker-compose.yml`). Docker Compose reads this automatically:

```dotenv
# Existing vars...

# S3
AWS_ACCESS_KEY_ID=AKIAxxxxxxxxxxxxxxxxx
AWS_SECRET_ACCESS_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
AWS_REGION=ap-south-1
S3_BUCKET_NAME=smartcourse-uploads-bucket
S3_PRESIGNED_URL_EXPIRY=3600
S3_MAX_FILE_SIZE_MB=500
```

### 8.3 — Rebuild and restart

```bash
# Rebuild shared + course-service (boto3 is new)
docker compose build shared course-service

# Restart course-service
docker compose up -d course-service
```

---

## 9. Testing with Postman

### 9.1 — Upload a file (Pattern A)

1. **New request** → `POST`
2. URL: `https://localhost/api/v1/uploads/lesson-file`
3. **Authorization** tab → Bearer Token → paste your instructor JWT
4. **Body** tab → `form-data`
   - Key: `file` | Type: **File** | Value: select a `.mp4` or `.pdf`
   - Key: `lesson_type` | Type: **Text** | Value: `video`
5. Send → 200 `{ "key": "...", "url": "..." }`

### 9.2 — Create lesson with that URL

1. Copy the `url` from the response above
2. `POST /api/v1/courses/2/content/modules/<module_id>/lessons`
3. Body JSON → paste the lesson JSON with `"content": "<url>"`

### 9.3 — Combined upload + lesson (Pattern B)

1. `POST https://localhost/api/v1/courses/2/modules/<module_id>/lessons/with-file`
2. Body → `form-data`
   - `title` = `Welcome Video`
   - `type` = `video`
   - `order` = `1`
   - `duration_minutes` = `10`
   - `is_preview` = `true`
   - `file` (File) = select your video

### 9.4 — Generated presigned URL (for playback/download)

1. `GET /api/v1/uploads/presigned-url?key=course-content/videos/a3f9e1b2c4d5.mp4`
2. Response → temporary URL valid for 1 hour
3. Open that URL in a browser to stream/download the file

---

## 10. How It All Fits Together

```
Instructor (Postman / Frontend)
        │
        │  multipart/form-data  (file + lesson metadata)
        ▼
   API Gateway (nginx)  ──────────────────────────────────────────────────┐
        │  forwards to course-service:8002                                 │
        ▼                                                                  │
   course-service                                                          │
   └── api/uploads.py                                                      │
        │                                                                  │
        │  1. Validates file type & size                                   │
        │  2. Calls shared.storage.s3.S3Uploader.upload_file()            │
        │        └── boto3.put_object()  ──────────────────► AWS S3       │
        │              Returns S3UploadResult { key, url }                 │
        │                                                                  │
        │  3. Stores url in MongoDB lesson.content                         │
        │     and in lesson.resources[]                                    │
        │        └── Motor (async MongoDB driver)  ────────► MongoDB       │
        │                                                                  │
        │  4. Returns CourseContentResponse (full doc)                     │
        └──────────────────────────────────────────────────────────────────┘
                                                                           │
                                                          response JSON  ◄─┘

Later — Student accesses lesson:
   GET /api/v1/uploads/presigned-url?key=course-content/videos/....mp4
        │
        └── S3Uploader.generate_presigned_url()
                └── Returns https://s3.amazonaws.com/...?X-Amz-Expires=3600
                        Student browser streams video directly from S3
```

### S3 Folder Structure

```
smartcourse-uploads-bucket/
├── course-content/
│   ├── videos/          ← lesson type "video"
│   │   └── a3f9e1b2c4d5.mp4
│   ├── documents/       ← lesson type "text" / "assignment"
│   │   └── 7b2c3d4e5f.pdf
│   └── images/          ← lesson type "quiz" (diagram/image attachments)
│       └── 9c1d2e3f.png
└── user-avatars/        ← future user-service uploads
    └── 42/profile.jpg
```

### Why store the permanent URL in MongoDB?

The permanent URL (`https://bucket.s3.region.amazonaws.com/key`) is stored in MongoDB as the canonical reference. It never expires and is not directly accessible (bucket is private). When a student needs to play a video:

1. Frontend calls `GET /uploads/presigned-url?key=<key>` (extract key from the stored URL or store key separately)
2. Backend generates a 1-hour presigned URL
3. Frontend uses that URL to stream from S3

> **Recommendation:** Store **both** `key` and `url` in MongoDB — `url` for display, `key` for generating presigned URLs without needing to parse the URL later. You can add a `s3_key` field to `ResourceSchema` and `LessonSchema`.

---

## Summary of Files to Create / Modify

| Action     | File                                                                           |
| ---------- | ------------------------------------------------------------------------------ |
| **CREATE** | `shared/src/shared/storage/__init__.py`                                        |
| **CREATE** | `shared/src/shared/storage/s3.py`                                              |
| **MODIFY** | `shared/src/shared/__init__.py` — add S3 exports                               |
| **MODIFY** | `shared/pyproject.toml` — add boto3                                            |
| **MODIFY** | `services/course-service/src/config.py` — add S3 settings                      |
| **CREATE** | `services/course-service/src/core/s3.py` — S3Uploader singleton                |
| **MODIFY** | `services/course-service/src/schemas/course_content.py` — add S3UploadResponse |
| **CREATE** | `services/course-service/src/api/uploads.py` — upload router                   |
| **MODIFY** | `services/course-service/src/main.py` — register router                        |
| **MODIFY** | `docker-compose.yml` — add S3 env vars                                         |
| **MODIFY** | `.env` (root) — add S3 secrets                                                 |
| **MODIFY** | `services/course-service/.env` — add S3 secrets                                |
