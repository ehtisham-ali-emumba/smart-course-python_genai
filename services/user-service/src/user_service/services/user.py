from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from user_service.core.cache import cache_delete, cache_get, cache_set
from user_service.models.user import User
from user_service.repositories.user import UserRepository
from user_service.schemas.user import UserResponse, UserUpdate


# ── TTL Constants ─────────────────────────────────────────────────
USER_PROFILE_TTL = 900  # 15 minutes


class UserService:
    """User service for user operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)

    async def get_user(self, user_id: int) -> Optional[User] | Optional[dict]:
        """Get user by ID — with cache."""
        # 1. Try cache
        cache_key = f"user:profile:{user_id}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        # 2. Fallback to DB
        user = await self.user_repo.get_by_id(user_id)

        # 3. Store in cache
        if user:
            user_dict = UserResponse.model_validate(user).model_dump(mode="json")
            await cache_set(cache_key, user_dict, ttl=USER_PROFILE_TTL)

        return user

    async def update_user(
        self, user_id: int, user_data: UserUpdate
    ) -> Optional[User]:
        """Update user information — invalidate cache."""
        update_data = user_data.model_dump(exclude_unset=True)
        result = await self.user_repo.update(user_id, update_data)

        if result:
            await cache_delete(f"user:profile:{user_id}")

        return result

    async def list_users(self, skip: int = 0, limit: int = 100):
        """List all users with pagination."""
        return await self.user_repo.get_all(skip=skip, limit=limit)
