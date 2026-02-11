from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from user_service.models.user import User
from user_service.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """User repository for database operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(db, User)

    async def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalars().first()

    async def email_exists(self, email: str) -> bool:
        """Check if email exists."""
        user = await self.get_by_email(email)
        return user is not None
