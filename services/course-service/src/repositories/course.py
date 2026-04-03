import uuid as _uuid
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.course import Course
from repositories.base import BaseRepository


class CourseRepository(BaseRepository[Course]):
    """Course repository for PostgreSQL operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(db, Course)

    async def get_by_slug(self, slug: str) -> Optional[Course]:
        """Get course by URL slug."""
        result = await self.db.execute(
            select(Course).where(Course.slug == slug, Course.is_deleted == False)
        )
        return result.scalars().first()

    async def get_by_id_for_update(self, id: _uuid.UUID) -> Optional[Course]:
        """Get course by ID with a row-level exclusive lock (SELECT ... FOR UPDATE).

        Acquires a pessimistic lock on the course row within the current transaction.
        This serializes concurrent access to the same course. Used in enrollment
        operations to prevent race conditions around max_students check.

        Must be called within an explicit transaction (e.g., async with self.db.begin()).
        """
        result = await self.db.execute(select(Course).where(Course.id == id).with_for_update())
        return result.scalars().first()

    async def slug_exists(self, slug: str) -> bool:
        """Check if a slug already exists."""
        course = await self.get_by_slug(slug)
        return course is not None

    async def get_by_instructor(
        self, instructor_id: _uuid.UUID, skip: int = 0, limit: int = 100
    ) -> List[Course]:
        """Get all courses by an instructor."""
        result = await self.db.execute(
            select(Course)
            .where(Course.instructor_id == instructor_id, Course.is_deleted == False)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_published(self, skip: int = 0, limit: int = 100) -> List[Course]:
        """Get all published courses (for students browsing)."""
        result = await self.db.execute(
            select(Course)
            .where(Course.status == "published", Course.is_deleted == False)
            .order_by(Course.published_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_published(self) -> int:
        """Count total published courses."""
        result = await self.db.execute(
            select(func.count())
            .select_from(Course)
            .where(Course.status == "published", Course.is_deleted == False)
        )
        return result.scalar() or 0

    async def count_by_instructor(self, instructor_id: _uuid.UUID) -> int:
        """Count courses by instructor."""
        result = await self.db.execute(
            select(func.count())
            .select_from(Course)
            .where(Course.instructor_id == instructor_id, Course.is_deleted == False)
        )
        return result.scalar() or 0

    async def soft_delete(self, id: _uuid.UUID) -> Optional[Course]:
        """Soft delete a course."""
        return await self.update(id, {"is_deleted": True})
