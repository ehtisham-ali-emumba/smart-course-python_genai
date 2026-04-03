from datetime import datetime
import uuid as _uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from models.enrollment import Enrollment
from repositories.course import CourseRepository
from repositories.enrollment import EnrollmentRepository
from schemas.enrollment import EnrollmentCreate


class EnrollmentService:
    """Business logic for enrollment operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.enrollment_repo = EnrollmentRepository(db)
        self.course_repo = CourseRepository(db)

    async def enroll_student(self, student_id: _uuid.UUID, data: EnrollmentCreate) -> Enrollment:
        """Enroll a student in a course.

        Uses pessimistic locking (SELECT ... FOR UPDATE) to serialize concurrent
        enrollment attempts for the same course. This prevents race conditions
        around the max_students check.

        Wraps check and insert in a single atomic transaction. If the max_students
        limit is reached or the student is already enrolled, the transaction rolls
        back and no enrollment is created.
        """
        async with self.db.begin_nested():
            # Acquire row-level lock on the course within the transaction
            course = await self.course_repo.get_by_id_for_update(data.course_id)
            if not course or course.is_deleted:
                raise ValueError("Course not found")
            if course.status != "published":
                raise ValueError("Course is not available for enrollment")

            # Check max_students limit within the locked transaction
            if course.max_students:
                current_count = await self.enrollment_repo.count_by_course(data.course_id)
                if current_count >= course.max_students:
                    raise ValueError("Course enrollment limit reached")

            # Check if already enrolled within the locked transaction
            if await self.enrollment_repo.is_enrolled(student_id, data.course_id):
                raise ValueError("Already enrolled in this course")

            enrollment_data = {
                "student_id": student_id,
                "course_id": data.course_id,
                "status": "active",
                "payment_amount": data.payment_amount,
                "payment_status": "completed" if data.payment_amount else None,
                "enrollment_source": data.enrollment_source,
            }

            try:
                # Flush (insert) without committing - transaction scope owns the commit
                enrollment = await self.enrollment_repo.create_in_tx(enrollment_data)
            except IntegrityError:
                # Unique constraint violation on (student_id, course_id)
                # Rollback happens automatically; re-raise as ValueError
                raise ValueError("Already enrolled in this course")

        # Commit the outer transaction to persist changes
        await self.db.commit()
        return enrollment

    async def get_enrollment(self, enrollment_id: _uuid.UUID) -> Enrollment | None:
        """Get a single enrollment by ID. No cache — low frequency, user-specific."""
        return await self.enrollment_repo.get_by_id(enrollment_id)

    async def get_student_enrollments(
        self, student_id: _uuid.UUID, skip: int = 0, limit: int = 100
    ):
        """List all enrollments for a student. No cache — user-specific."""
        enrollments = await self.enrollment_repo.get_by_student(student_id, skip=skip, limit=limit)
        total = await self.enrollment_repo.count_by_student(student_id)
        return enrollments, total

    async def get_course_enrollments(self, course_id: _uuid.UUID, skip: int = 0, limit: int = 100):
        """List all enrollments for a course (instructor view). No cache."""
        enrollments = await self.enrollment_repo.get_by_course(course_id, skip=skip, limit=limit)
        total = await self.enrollment_repo.count_by_course(course_id)
        return enrollments, total

    async def drop_enrollment(
        self, enrollment_id: _uuid.UUID, student_id: _uuid.UUID
    ) -> Enrollment | None:
        """Student drops a course."""
        enrollment = await self.enrollment_repo.get_by_id(enrollment_id)
        if not enrollment:
            return None
        if enrollment.student_id != student_id:
            raise PermissionError("This is not your enrollment")

        return await self.enrollment_repo.update(
            enrollment_id,
            {
                "status": "dropped",
                "dropped_at": datetime.utcnow(),
            },
        )

    async def undrop_enrollment(
        self, enrollment_id: _uuid.UUID, student_id: _uuid.UUID
    ) -> Enrollment | None:
        """Student re-enrolls after dropping (reactivates enrollment).

        Uses pessimistic locking (SELECT ... FOR UPDATE) on the course to serialize
        concurrent re-enrollment attempts and prevent exceeding max_students limit.

        All validation and the status update happen within a single atomic transaction.
        """
        enrollment = await self.enrollment_repo.get_by_id(enrollment_id)
        if not enrollment:
            return None
        if enrollment.student_id != student_id:
            raise PermissionError("This is not your enrollment")
        if enrollment.status != "dropped":
            raise ValueError("Enrollment is not dropped")

        async with self.db.begin_nested():
            # Acquire row-level lock on the course within the transaction
            course = await self.course_repo.get_by_id_for_update(enrollment.course_id)
            if not course or course.is_deleted:
                raise ValueError("Course not found")
            if course.status != "published":
                raise ValueError("Course is not available for enrollment")

            # Check max_students limit within the locked transaction
            if course.max_students:
                current_count = await self.enrollment_repo.count_by_course(enrollment.course_id)
                if current_count >= course.max_students:
                    raise ValueError("Course enrollment limit reached")

            # Update enrollment status within the locked transaction
            result = await self.enrollment_repo.update_in_tx(
                enrollment_id,
                {"status": "active", "dropped_at": None},
            )

        # Commit the outer transaction to persist changes
        await self.db.commit()
        return result
