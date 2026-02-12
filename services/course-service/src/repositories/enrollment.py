from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.enrollment import Enrollment
from repositories.base import BaseRepository


class EnrollmentRepository(BaseRepository[Enrollment]):
    """Enrollment repository for PostgreSQL operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(db, Enrollment)

    async def get_by_student_and_course(
        self, student_id: int, course_id: int
    ) -> Optional[Enrollment]:
        """Get enrollment by student + course (unique pair)."""
        result = await self.db.execute(
            select(Enrollment).where(
                Enrollment.student_id == student_id,
                Enrollment.course_id == course_id,
            )
        )
        return result.scalars().first()

    async def get_by_student(
        self, student_id: int, skip: int = 0, limit: int = 100
    ) -> List[Enrollment]:
        """Get all enrollments for a student."""
        result = await self.db.execute(
            select(Enrollment)
            .where(Enrollment.student_id == student_id)
            .order_by(Enrollment.enrolled_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_course(
        self, course_id: int, skip: int = 0, limit: int = 100
    ) -> List[Enrollment]:
        """Get all enrollments for a course."""
        result = await self.db.execute(
            select(Enrollment)
            .where(Enrollment.course_id == course_id)
            .order_by(Enrollment.enrolled_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_course(self, course_id: int) -> int:
        """Count enrollments for a course."""
        result = await self.db.execute(
            select(func.count()).select_from(Enrollment).where(
                Enrollment.course_id == course_id
            )
        )
        return result.scalar() or 0

    async def count_by_student(self, student_id: int) -> int:
        """Count enrollments for a student."""
        result = await self.db.execute(
            select(func.count()).select_from(Enrollment).where(
                Enrollment.student_id == student_id
            )
        )
        return result.scalar() or 0

    async def is_enrolled(self, student_id: int, course_id: int) -> bool:
        """Check if a student is enrolled in a course."""
        enrollment = await self.get_by_student_and_course(student_id, course_id)
        return enrollment is not None
