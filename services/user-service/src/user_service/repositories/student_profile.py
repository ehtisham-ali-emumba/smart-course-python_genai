import uuid as _uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from user_service.models.student import StudentProfile
from user_service.repositories.base import BaseRepository


class StudentProfileRepository(BaseRepository[StudentProfile]):

    def __init__(self, db: AsyncSession):
        super().__init__(db, StudentProfile)

    async def get_by_user_id(self, user_id: _uuid.UUID) -> StudentProfile | None:
        result = await self.db.execute(
            select(StudentProfile).where(StudentProfile.user_id == user_id)
        )
        return result.scalars().first()
