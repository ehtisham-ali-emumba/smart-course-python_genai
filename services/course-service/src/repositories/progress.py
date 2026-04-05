import uuid as _uuid
from datetime import datetime
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.progress import Progress
from repositories.base import BaseRepository


class ProgressRepository(BaseRepository[Progress]):
    """Progress repository for PostgreSQL operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(db, Progress)

    async def upsert_progress(
        self,
        enrollment_id: _uuid.UUID,
        item_type: str,
        item_id: str,
        progress_percentage: float,
    ) -> Progress:
        """
        Create or update a progress record (upsert).

        - If no row exists: INSERT with the given percentage.
        - If row exists: UPDATE percentage (and completed_at if 100%).
        """
        completed_at = datetime.utcnow() if progress_percentage >= 100 else None

        stmt = (
            insert(Progress.__table__)
            .values(
                enrollment_id=enrollment_id,
                item_type=item_type,
                item_id=item_id,
                progress_percentage=progress_percentage,
                completed_at=completed_at,
                updated_at=datetime.utcnow(),
            )
            .on_conflict_do_update(
                constraint="uq_progress_enrollment_item",
                set_={
                    "progress_percentage": progress_percentage,
                    "completed_at": sa.func.coalesce(
                        Progress.__table__.c.completed_at,
                        completed_at,
                    ),
                    "updated_at": datetime.utcnow(),
                },
            )
            .returning(Progress.__table__.c.id)
        )

        result = await self.db.execute(stmt)
        await self.db.commit()

        row = result.one()
        return await self.get_by_id(row[0])

    async def get_by_enrollment_and_item(
        self,
        enrollment_id: _uuid.UUID,
        item_type: str,
        item_id: str,
    ) -> Optional[Progress]:
        """Get a specific progress record by enrollment + item."""
        result = await self.db.execute(
            select(Progress).where(
                Progress.enrollment_id == enrollment_id,
                Progress.item_type == item_type,
                Progress.item_id == item_id,
            )
        )
        return result.scalars().first()

    async def get_enrollment_progress(
        self,
        enrollment_id: _uuid.UUID,
    ) -> List[Progress]:
        """Get all progress records for an enrollment."""
        result = await self.db.execute(
            select(Progress)
            .where(Progress.enrollment_id == enrollment_id)
            .order_by(Progress.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_completed_items(
        self,
        enrollment_id: _uuid.UUID,
        item_type: Optional[str] = None,
    ) -> List[Progress]:
        """Get all completed items (progress_percentage = 100) for an enrollment."""
        query = select(Progress).where(
            Progress.enrollment_id == enrollment_id,
            Progress.completed_at.isnot(None),
        )
        if item_type:
            query = query.where(Progress.item_type == item_type)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_completed(
        self,
        enrollment_id: _uuid.UUID,
        item_type: Optional[str] = None,
    ) -> int:
        """Count completed items for an enrollment."""
        query = (
            select(func.count())
            .select_from(Progress)
            .where(
                Progress.enrollment_id == enrollment_id,
                Progress.completed_at.isnot(None),
            )
        )
        if item_type:
            query = query.where(Progress.item_type == item_type)
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def delete_enrollment_progress(
        self,
        enrollment_id: _uuid.UUID,
    ) -> int:
        """Delete all progress for an enrollment."""
        result = await self.db.execute(
            Progress.__table__.delete().where(
                Progress.enrollment_id == enrollment_id,
            )
        )
        await self.db.commit()
        return result.rowcount
