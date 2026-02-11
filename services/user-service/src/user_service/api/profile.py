from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from user_service.core.database import get_db
from user_service.schemas.user import UserResponse, UserUpdate
from user_service.services.user import UserService

router = APIRouter()


@router.get("/", response_model=UserResponse)
async def get_profile(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get current user profile."""
    # User ID is set by API Gateway after JWT verification
    user_id = request.headers.get("X-User-ID")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    user_service = UserService(db)
    user = await user_service.get_user(int(user_id))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserResponse.model_validate(user)


@router.put("/", response_model=UserResponse)
async def update_profile(
    user_data: UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Update user profile."""
    user_id = request.headers.get("X-User-ID")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    user_service = UserService(db)
    user = await user_service.update_user(int(user_id), user_data)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserResponse.model_validate(user)
