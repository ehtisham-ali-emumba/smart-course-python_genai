import uuid as _uuid

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from shared.storage.s3 import S3Uploader
from user_service.core.cache import cache_delete, cache_get, cache_set
from user_service.core.s3 import get_s3_uploader
from user_service.models.user import User
from user_service.repositories.instructor_profile import InstructorProfileRepository
from user_service.repositories.student_profile import StudentProfileRepository
from user_service.repositories.user import UserRepository
from user_service.schemas.user import (
    InstructorProfileResponse,
    StudentProfileResponse,
    UserResponse,
    UserUpdate,
)


# ── TTL Constants ─────────────────────────────────────────────────
USER_PROFILE_TTL = 900  # 15 minutes


def _user_to_dict(user: User) -> dict:
    """Convert User ORM to dict for consistent API/response use."""
    return UserResponse.model_validate(user).model_dump(mode="json")


class UserService:
    """User service for user operations.

    All read methods return dict (not ORM) so the API layer can always use
    UserResponse(**data) with no isinstance checks. Cache logic is in the service.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)

    async def get_user(self, user_id: _uuid.UUID) -> dict | None:
        """Get user by ID — with cache. Always returns dict or None."""
        # 1. Try cache
        cache_key = f"user:profile:{user_id}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        # 2. Fallback to DB
        user = await self.user_repo.get_by_id(user_id)

        # 3. Store in cache and return normalized dict
        if user:
            user_dict = _user_to_dict(user)
            await cache_set(cache_key, user_dict, ttl=USER_PROFILE_TTL)
            return user_dict

        return None

    async def get_full_profile(self, user_id: _uuid.UUID) -> dict | None:
        user = await self.get_user(user_id)
        if not user:
            return None

        role = user.get("role")
        result = dict(user)

        if role == "student":
            repo = StudentProfileRepository(self.db)
            profile = await repo.get_by_user_id(user_id)
            result["student_profile"] = (
                StudentProfileResponse.model_validate(profile).model_dump(mode="json")
                if profile
                else None
            )
        elif role == "instructor":
            repo = InstructorProfileRepository(self.db)
            profile = await repo.get_by_user_id(user_id)
            result["instructor_profile"] = (
                InstructorProfileResponse.model_validate(profile).model_dump(mode="json")
                if profile
                else None
            )

        return result

    async def update_user(self, user_id: _uuid.UUID, user_data: UserUpdate) -> dict | None:
        """Update user information — invalidate cache. Returns dict or None."""
        update_data = user_data.model_dump(exclude_unset=True)
        result = await self.user_repo.update(user_id, update_data)

        if result:
            await cache_delete(f"user:profile:{user_id}")
            return _user_to_dict(result)

        return None

    async def list_users(self, skip: int = 0, limit: int = 100):
        """List all users with pagination."""
        return await self.user_repo.get_all(skip=skip, limit=limit)

    async def upload_avatar(
        self, user_id: _uuid.UUID, file: UploadFile, max_size_mb: float = 5.0
    ) -> str:
        """Upload avatar to S3, delete old one, persist URL. Returns new URL."""
        # 1. Get user to verify exists and determine role
        user = await self.get_user(user_id)
        if not user:
            raise ValueError(f"User not found: {user_id}")

        role = user.get("role")

        # 2. Get current avatar URL (to delete old one)
        old_url = None
        if role == "student":
            repo = StudentProfileRepository(self.db)
            profile = await repo.get_by_user_id(user_id)
            old_url = profile.profile_picture_url if profile else None
        elif role == "instructor":
            repo = InstructorProfileRepository(self.db)
            profile = await repo.get_by_user_id(user_id)
            old_url = profile.profile_picture_url if profile else None

        # 3. Upload new avatar to S3
        uploader = get_s3_uploader()
        result = await uploader.upload_file(
            file=file,
            folder=f"users/avatars/{user_id}",
            allowed_category="image",
            max_size_mb=max_size_mb,
        )

        # 4. Delete old avatar if it exists
        if old_url:
            try:
                old_key = S3Uploader.key_from_url(old_url)
                await uploader.delete_file(old_key)
            except Exception as e:
                # Log but don't fail the upload if deletion fails
                import structlog

                logger = structlog.get_logger(__name__)
                logger.warning("failed_to_delete_old_avatar", error=str(e), old_url=old_url)

        # 5. Update profile with new URL
        if role == "student":
            repo = StudentProfileRepository(self.db)
            await repo.update_avatar_url(user_id, result.url)
        elif role == "instructor":
            repo = InstructorProfileRepository(self.db)
            await repo.update_avatar_url(user_id, result.url)

        # 6. Invalidate user profile cache
        await cache_delete(f"user:profile:{user_id}")

        return result.url
