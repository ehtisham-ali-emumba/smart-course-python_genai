import uuid as _uuid

from sqlalchemy import select, insert, update
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

    async def update_avatar_url(self, user_id: _uuid.UUID, url: str) -> None:
        """Update or insert profile_picture_url for an instructor."""
        # Check if profile exists
        existing = await self.get_by_user_id(user_id)

        if existing:
            # Update existing profile
            await self.db.execute(
                update(InstructorProfile)
                .where(InstructorProfile.user_id == user_id)
                .values(profile_picture_url=url)
            )
        else:
            # Insert new profile with avatar
            await self.db.execute(
                insert(InstructorProfile).values(
                    user_id=user_id,
                    profile_picture_url=url,
                )
            )

        await self.db.commit()
