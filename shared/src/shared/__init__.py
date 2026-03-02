"""Shared library for SmartCourse microservices."""

# Keep package init lightweight and side-effect free.
# Subpackages are imported directly by services as needed.
__all__ = ["kafka", "schemas", "exceptions", "utils"]

# S3
from shared.storage.s3 import S3Uploader, S3UploadResult  # noqa: F401
