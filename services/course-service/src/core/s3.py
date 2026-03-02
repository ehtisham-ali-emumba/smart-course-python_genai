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
