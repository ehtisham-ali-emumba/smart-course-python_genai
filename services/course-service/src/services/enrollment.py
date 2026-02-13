from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import cache_delete, cache_get, cache_set
from models.enrollment import Enrollment
from repositories.course import CourseRepository
from repositories.enrollment import EnrollmentRepository
from schemas.enrollment import EnrollmentCreate


# ── TTL Constants ─────────────────────────────────────────────────
ENROLLMENT_FLAG_TTL = 1800  # 30 minutes — enrollment status rarely changes
ENROLLMENT_COUNT_TTL = 300  # 5 minutes


class EnrollmentService:
    """Business logic for enrollment and progress operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.enrollment_repo = EnrollmentRepository(db)
        self.course_repo = CourseRepository(db)

    # ── CACHED HELPERS ────────────────────────────────────────────

    async def _is_enrolled_cached(self, student_id: int, course_id: int) -> bool:
        """Check enrollment with cache. Used internally."""
        cache_key = f"course:enrolled:{student_id}:{course_id}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached  # True or False

        is_enrolled = await self.enrollment_repo.is_enrolled(student_id, course_id)
        await cache_set(cache_key, is_enrolled, ttl=ENROLLMENT_FLAG_TTL)
        return is_enrolled

    async def _get_enrollment_count_cached(self, course_id: int) -> int:
        """Get enrollment count with cache. Used for limit checks and display."""
        cache_key = f"course:enrollment_count:{course_id}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        count = await self.enrollment_repo.count_by_course(course_id)
        await cache_set(cache_key, count, ttl=ENROLLMENT_COUNT_TTL)
        return count

    # ── READS ─────────────────────────────────────────────────────

    async def enroll_student(self, student_id: int, data: EnrollmentCreate) -> Enrollment:
        """Enroll a student in a course."""
        # Check course exists and is published
        course = await self.course_repo.get_by_id(data.course_id)
        if not course or course.is_deleted:
            raise ValueError("Course not found")
        if course.status != "published":
            raise ValueError("Course is not available for enrollment")

        # Check max_students limit (uses cached count)
        if course.max_students:
            current_count = await self._get_enrollment_count_cached(data.course_id)
            if current_count >= course.max_students:
                raise ValueError("Course enrollment limit reached")

        # Check not already enrolled (uses cached flag)
        if await self._is_enrolled_cached(student_id, data.course_id):
            raise ValueError("Already enrolled in this course")

        enrollment_data = {
            "student_id": student_id,
            "course_id": data.course_id,
            "status": "active",
            "payment_amount": data.payment_amount,
            "payment_status": "completed" if data.payment_amount else None,
            "enrollment_source": data.enrollment_source,
        }
        enrollment = await self.enrollment_repo.create(enrollment_data)

        # Invalidate enrollment caches
        await cache_set(
            f"course:enrolled:{student_id}:{data.course_id}", True, ttl=ENROLLMENT_FLAG_TTL
        )
        await cache_delete(f"course:enrollment_count:{data.course_id}")

        return enrollment

    async def get_enrollment(self, enrollment_id: int) -> Enrollment | None:
        """Get a single enrollment by ID. No cache — low frequency, user-specific."""
        return await self.enrollment_repo.get_by_id(enrollment_id)

    async def get_student_enrollments(
        self, student_id: int, skip: int = 0, limit: int = 100
    ):
        """List all enrollments for a student. No cache — user-specific."""
        enrollments = await self.enrollment_repo.get_by_student(
            student_id, skip=skip, limit=limit
        )
        total = await self.enrollment_repo.count_by_student(student_id)
        return enrollments, total

    async def get_course_enrollments(
        self, course_id: int, skip: int = 0, limit: int = 100
    ):
        """List all enrollments for a course (instructor view). No cache."""
        enrollments = await self.enrollment_repo.get_by_course(
            course_id, skip=skip, limit=limit
        )
        total = await self.enrollment_repo.count_by_course(course_id)
        return enrollments, total

    async def drop_enrollment(
        self, enrollment_id: int, student_id: int
    ) -> Enrollment | None:
        """Student drops a course."""
        enrollment = await self.enrollment_repo.get_by_id(enrollment_id)
        if not enrollment:
            return None
        if enrollment.student_id != student_id:
            raise PermissionError("This is not your enrollment")

        result = await self.enrollment_repo.update(
            enrollment_id,
            {
                "status": "dropped",
                "dropped_at": datetime.utcnow(),
            },
        )

        # Invalidate enrollment caches
        await cache_delete(f"course:enrolled:{student_id}:{enrollment.course_id}")
        await cache_delete(f"course:enrollment_count:{enrollment.course_id}")

        return result

    async def undrop_enrollment(
        self, enrollment_id: int, student_id: int
    ) -> Enrollment | None:
        """Student re-enrolls after dropping (reactivates enrollment)."""
        enrollment = await self.enrollment_repo.get_by_id(enrollment_id)
        if not enrollment:
            return None
        if enrollment.student_id != student_id:
            raise PermissionError("This is not your enrollment")
        if enrollment.status != "dropped":
            raise ValueError("Enrollment is not dropped")

        course = await self.course_repo.get_by_id(enrollment.course_id)
        if not course or course.is_deleted:
            raise ValueError("Course not found")
        if course.status != "published":
            raise ValueError("Course is not available for enrollment")
        if course.max_students:
            current_count = await self._get_enrollment_count_cached(enrollment.course_id)
            if current_count >= course.max_students:
                raise ValueError("Course enrollment limit reached")

        result = await self.enrollment_repo.update(
            enrollment_id,
            {"status": "active", "dropped_at": None},
        )

        await cache_set(
            f"course:enrolled:{student_id}:{enrollment.course_id}",
            True,
            ttl=ENROLLMENT_FLAG_TTL,
        )
        await cache_delete(f"course:enrollment_count:{enrollment.course_id}")

        return result
