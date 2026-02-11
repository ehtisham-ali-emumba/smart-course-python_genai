from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from user_service.models.user import User
from user_service.repositories.user import UserRepository
from user_service.schemas.user import UserUpdate


class UserService:
    """User service for user operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)

    async def get_user(self, user_id: int) -> Optional[User]:
        """Get user by ID."""
        return await self.user_repo.get_by_id(user_id)

    async def update_user(self, user_id: int, user_data: UserUpdate) -> Optional[User]:
        """Update user information."""
        update_data = user_data.model_dump(exclude_unset=True)
        return await self.user_repo.update(user_id, update_data)

    async def list_users(self, skip: int = 0, limit: int = 100):
        """List all users with pagination."""
        return await self.user_repo.get_all(skip=skip, limit=limit)
