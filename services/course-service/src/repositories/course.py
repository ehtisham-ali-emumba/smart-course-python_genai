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

    async def slug_exists(self, slug: str) -> bool:
        """Check if a slug already exists."""
        course = await self.get_by_slug(slug)
        return course is not None

    async def get_by_instructor(
        self, instructor_id: int, skip: int = 0, limit: int = 100
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
            select(func.count()).select_from(Course).where(
                Course.status == "published", Course.is_deleted == False
            )
        )
        return result.scalar() or 0

    async def count_by_instructor(self, instructor_id: int) -> int:
        """Count courses by instructor."""
        result = await self.db.execute(
            select(func.count()).select_from(Course).where(
                Course.instructor_id == instructor_id, Course.is_deleted == False
            )
        )
        return result.scalar() or 0

    async def soft_delete(self, id: int) -> Optional[Course]:
        """Soft delete a course."""
        return await self.update(id, {"is_deleted": True})
