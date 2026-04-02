import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from shared.kafka.producer import EventProducer
from shared.kafka.topics import Topics
from shared.schemas.events.user import UserLoginPayload, UserRegisteredPayload
from user_service.core.database import get_db
from user_service.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from user_service.schemas.auth import (
    UserRegister,
    UserLogin,
    TokenResponse,
    RefreshTokenRequest,
)
from user_service.schemas.user import UserResponse
from user_service.services.auth import AuthService

router = APIRouter()


def get_event_producer(request: Request) -> EventProducer:
    return request.app.state.event_producer


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db),
    producer: EventProducer = Depends(get_event_producer),
):
    """
    Register a new user.

    - Creates user in database with encrypted password
    - Returns created user
    """
    auth_service = AuthService(db)
    try:
        user = await auth_service.register(user_data)

        await producer.publish(
            Topics.USER,
            "user.registered",
            UserRegisteredPayload(
                user_id=user.id,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
            ).model_dump(),
            key=str(user.id),
        )

        return UserResponse.model_validate(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db),
    producer: EventProducer = Depends(get_event_producer),
):
    """
    Authenticate user and return JWT tokens.

    Returns:
        - access_token: Short-lived token (15 min) for API access
        - refresh_token: Long-lived token (7 days) for refreshing
        - token_type: "bearer"
    """
    auth_service = AuthService(db)
    user = await auth_service.authenticate(
        credentials.email,
        credentials.password,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    await producer.publish(
        Topics.USER,
        "user.login",
        UserLoginPayload(user_id=user.id, email=user.email).model_dump(),
        key=str(user.id),
    )

    profile_id = await auth_service.get_profile_id(user.id, user.role)
    access_token = create_access_token(user.id, user.role, profile_id)
    refresh_token = create_refresh_token(user.id, user.role, profile_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Refresh access token using refresh token.
    """
    try:
        payload = decode_token(request.refresh_token)

        if payload.type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        auth_service = AuthService(db)
        user = await auth_service.get_user_by_id(_uuid.UUID(payload.sub))

        if not user or not user.get("is_active", False):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )

        user_id_val = _uuid.UUID(user["id"])
        user_role = user["role"]
        profile_id = _uuid.UUID(payload.profile_id)
        access_token = create_access_token(user_id_val, user_role, profile_id)
        refresh_token = create_refresh_token(user_id_val, user_role, profile_id)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
        )

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Get current authenticated user profile.

    Note: User info is passed from API Gateway via headers.
    """
    # User ID is set by API Gateway after JWT verification
    user_id = request.headers.get("X-User-ID")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    auth_service = AuthService(db)
    user = await auth_service.get_user_by_id(_uuid.UUID(user_id))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserResponse(**user)
