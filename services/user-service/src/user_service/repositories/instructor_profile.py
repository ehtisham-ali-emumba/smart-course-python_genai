import uuid as _uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from user_service.models.instructor import InstructorProfile
from user_service.repositories.base import BaseRepository


class InstructorProfileRepository(BaseRepository[InstructorProfile]):

    def __init__(self, db: AsyncSession):
        super().__init__(db, InstructorProfile)

    async def get_by_user_id(self, user_id: _uuid.UUID) -> InstructorProfile | None:
        result = await self.db.execute(
            select(InstructorProfile).where(InstructorProfile.user_id == user_id)
        )
        return result.scalars().first()
