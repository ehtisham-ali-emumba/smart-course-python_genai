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
from urllib.parse import urlparse
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

    key: str  # full S3 object key, e.g. "course-content/abc123.mp4"
    bucket: str  # bucket name
    region: str  # AWS region
    filename: str  # original file name supplied by client
    content_type: str  # detected MIME type
    size_bytes: int  # uploaded file size

    @property
    def url(self) -> str:
        """Permanent S3 URL. Objects are private."""
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

    async def download_file(self, key: str) -> bytes:
        """
        Download an object from S3 by its key.

        Args:
            key: S3 object key, e.g. "course-content/abc123.mp3"

        Returns:
            Raw bytes of the downloaded object.

        Raises:
            RuntimeError: S3 download failures.
        """
        try:
            data = await asyncio.to_thread(self._sync_download, key=key)
            logger.info("s3_download_success", key=key, size_bytes=len(data))
            return data
        except (BotoCoreError, ClientError) as exc:
            logger.error("s3_download_failed", key=key, error=str(exc))
            raise RuntimeError(f"S3 download failed for key '{key}': {exc}") from exc

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

    def _sync_download(self, *, key: str) -> bytes:
        """Blocking S3 get_object — always call inside asyncio.to_thread."""
        resp = self._client.get_object(Bucket=self._bucket, Key=key)
        return resp["Body"].read()

    @staticmethod
    def key_from_url(url: str) -> str:
        """Extract S3 object key from a virtual-hosted S3 URL.

        https://{bucket}.s3.{region}.amazonaws.com/{key}  →  {key}
        """
        return urlparse(url).path.lstrip("/")

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
