import uuid as _uuid

from sqlalchemy import select, insert, update
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

    async def update_avatar_url(self, user_id: _uuid.UUID, url: str) -> None:
        """Update or insert profile_picture_url for a student."""
        # Check if profile exists
        existing = await self.get_by_user_id(user_id)

        if existing:
            # Update existing profile
            await self.db.execute(
                update(StudentProfile)
                .where(StudentProfile.user_id == user_id)
                .values(profile_picture_url=url)
            )
        else:
            # Insert new profile with avatar
            await self.db.execute(
                insert(StudentProfile).values(
                    user_id=user_id,
                    profile_picture_url=url,
                )
            )

        await self.db.commit()
