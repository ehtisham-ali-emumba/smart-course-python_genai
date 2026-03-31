import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from shared.kafka.producer import EventProducer
from shared.kafka.topics import Topics
from shared.schemas.events.user import UserProfileUpdatedPayload
from user_service.config import settings
from user_service.core.database import get_db
from user_service.schemas.user import (
    AvatarUploadResponse,
    ProfileResponse,
    UserResponse,
    UserUpdate,
)
from user_service.services.user import UserService

router = APIRouter()


def get_event_producer(request: Request) -> EventProducer:
    return request.app.state.event_producer


@router.get("/", response_model=ProfileResponse)
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
    user = await user_service.get_full_profile(_uuid.UUID(user_id))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return ProfileResponse(**user)


@router.put("/", response_model=UserResponse)
async def update_profile(
    user_data: UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    producer: EventProducer = Depends(get_event_producer),
):
    """Update user profile."""
    user_id = request.headers.get("X-User-ID")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    user_uuid = _uuid.UUID(user_id)
    user_service = UserService(db)
    user = await user_service.update_user(user_uuid, user_data)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    fields_changed = list(user_data.model_dump(exclude_unset=True).keys())
    if fields_changed:
        await producer.publish(
            Topics.USER,
            "user.profile_updated",
            UserProfileUpdatedPayload(
                user_id=user_uuid,
                fields_changed=fields_changed,
            ).model_dump(),
            key=str(user_uuid),
        )

    return UserResponse(**user)


@router.post("/avatar", response_model=AvatarUploadResponse)
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload user avatar. Returns the URL of the uploaded avatar."""
    user_id = request.headers.get("X-User-ID")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    # Validate content type early
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image",
        )

    try:
        user_uuid = _uuid.UUID(user_id)
        user_service = UserService(db)
        url = await user_service.upload_avatar(
            user_uuid,
            file,
            max_size_mb=settings.S3_AVATAR_MAX_SIZE_MB,
        )
        return AvatarUploadResponse(profile_picture_url=url)
    except ValueError as e:
        if "User not found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
