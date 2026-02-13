from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.progress import Progress
from repositories.base import BaseRepository


class ProgressRepository(BaseRepository[Progress]):
    """Progress repository for PostgreSQL operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(db, Progress)

    async def mark_completed(
        self,
        user_id: int,
        course_id: int,
        item_type: str,
        item_id: str,
    ) -> Optional[Progress]:
        """Mark an item as completed (upsert — idempotent)."""
        stmt = (
            insert(Progress.__table__)
            .values(
                user_id=user_id,
                course_id=course_id,
                item_type=item_type,
                item_id=item_id,
            )
            .on_conflict_do_nothing(
                index_elements=["user_id", "item_type", "item_id"]
            )
            .returning(Progress.__table__.c.id)
        )

        result = await self.db.execute(stmt)
        await self.db.commit()

        inserted_row = result.one_or_none()
        if inserted_row is not None:
            # Insert succeeded, fetch the full record (inserted_row is (id,))
            return await self.get_by_id(inserted_row[0])
        # Conflict - record already exists, fetch it
        return await self.get_by_user_and_item(user_id, item_type, item_id)

    async def get_by_user_and_item(
        self,
        user_id: int,
        item_type: str,
        item_id: str,
    ) -> Optional[Progress]:
        """Get a specific progress record."""
        result = await self.db.execute(
            select(Progress).where(
                Progress.user_id == user_id,
                Progress.item_type == item_type,
                Progress.item_id == item_id,
            )
        )
        return result.scalars().first()

    async def get_user_course_progress(
        self,
        user_id: int,
        course_id: int,
    ) -> List[Progress]:
        """Get all progress records for a user in a course."""
        result = await self.db.execute(
            select(Progress).where(
                Progress.user_id == user_id,
                Progress.course_id == course_id,
            )
        )
        return list(result.scalars().all())

    async def get_completed_item_ids(
        self,
        user_id: int,
        course_id: int,
        item_type: str,
    ) -> List[str]:
        """Get list of completed item IDs for a specific type."""
        result = await self.db.execute(
            select(Progress.item_id).where(
                Progress.user_id == user_id,
                Progress.course_id == course_id,
                Progress.item_type == item_type,
            )
        )
        return [row[0] for row in result.fetchall()]

    async def count_completed(
        self,
        user_id: int,
        course_id: int,
        item_type: Optional[str] = None,
    ) -> int:
        """Count completed items for a user in a course."""
        query = select(func.count()).select_from(Progress).where(
            Progress.user_id == user_id,
            Progress.course_id == course_id,
        )
        if item_type:
            query = query.where(Progress.item_type == item_type)

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def delete_progress(
        self,
        user_id: int,
        course_id: int,
    ) -> int:
        """Delete all progress for a user in a course."""
        result = await self.db.execute(
            Progress.__table__.delete().where(
                Progress.user_id == user_id,
                Progress.course_id == course_id,
            )
        )
        await self.db.commit()
        return result.rowcount
