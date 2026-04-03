"""
Enrollment workflow state management using Redis.

Thin wrapper around core.cache primitives.
Keys use format: enrollment:wf:{student_id}:{course_id}
TTL: 5 minutes (300 seconds) — enough for typical workflow execution.
"""

import uuid
from typing import Optional

import structlog

from core.cache import cache_delete, cache_delete_pattern, cache_exists, cache_set_nx

logger = structlog.get_logger(__name__)


class EnrollmentWorkflowCache:
    """Enrollment workflow lock management, built on shared cache primitives."""

    _KEY_PREFIX = "enrollment:wf"
    _DEFAULT_TTL = 300  # 5 minutes

    @staticmethod
    def _make_key(student_id: uuid.UUID, course_id: uuid.UUID) -> str:
        return f"{EnrollmentWorkflowCache._KEY_PREFIX}:{student_id}:{course_id}"

    @classmethod
    async def acquire_lock(
        cls,
        student_id: uuid.UUID,
        course_id: uuid.UUID,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Atomically acquire an enrollment lock (SET NX).

        Returns True if acquired, False if already held.
        Returns True if Redis is unavailable (graceful degradation).
        """
        key = cls._make_key(student_id, course_id)
        acquired = await cache_set_nx(key, "1", ttl or cls._DEFAULT_TTL)
        if acquired:
            logger.info(
                "enrollment_lock_acquired", student_id=str(student_id), course_id=str(course_id)
            )
        else:
            logger.debug(
                "enrollment_lock_exists", student_id=str(student_id), course_id=str(course_id)
            )
        return acquired

    @classmethod
    async def is_in_progress(cls, student_id: uuid.UUID, course_id: uuid.UUID) -> bool:
        """Return True if an enrollment workflow lock exists for (student, course)."""
        key = cls._make_key(student_id, course_id)
        in_progress = await cache_exists(key)
        if in_progress:
            logger.debug(
                "enrollment_in_progress", student_id=str(student_id), course_id=str(course_id)
            )
        return in_progress

    @classmethod
    async def release_lock(cls, student_id: uuid.UUID, course_id: uuid.UUID) -> bool:
        """Release the enrollment lock after workflow completes (success or failure)."""
        key = cls._make_key(student_id, course_id)
        deleted = await cache_delete(key)
        if deleted:
            logger.info(
                "enrollment_lock_released", student_id=str(student_id), course_id=str(course_id)
            )
        return deleted

    @classmethod
    async def cleanup_all_for_student(cls, student_id: uuid.UUID) -> int:
        """Delete all enrollment locks for a student (e.g. on account deletion)."""
        pattern = f"{cls._KEY_PREFIX}:{student_id}:*"
        deleted = await cache_delete_pattern(pattern)
        if deleted > 0:
            logger.info("enrollment_locks_cleaned_up", student_id=str(student_id), deleted=deleted)
        return deleted
