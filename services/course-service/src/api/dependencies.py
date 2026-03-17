import uuid as _uuid

from fastapi import HTTPException, Request, status
from temporalio.client import Client as TemporalClient

from shared.kafka.producer import EventProducer


def get_event_producer(request: Request) -> EventProducer:
    return request.app.state.event_producer


def get_temporal_client(request: Request) -> TemporalClient:
    client = getattr(request.app.state, "temporal_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="Temporal client not available")
    return client


def get_current_user_id(request: Request) -> _uuid.UUID:
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return _uuid.UUID(user_id)


def get_current_user_role(request: Request) -> str:
    role = request.headers.get("X-User-Role")
    if not role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return role


def get_current_profile_id(request: Request) -> _uuid.UUID:
    profile_id = request.headers.get("X-Profile-ID")
    if not profile_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Profile not found")
    return _uuid.UUID(profile_id)


def require_instructor(request: Request) -> _uuid.UUID:
    """Returns instructor profile_id (from X-Profile-ID header)."""
    role = get_current_user_role(request)
    if role not in ("instructor", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Instructor role required"
        )
    return get_current_profile_id(request)


def require_student(request: Request) -> _uuid.UUID:
    """Returns student profile_id (from X-Profile-ID header)."""
    role = get_current_user_role(request)
    if role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Student role required")
    return get_current_profile_id(request)


def get_authenticated_user(request: Request) -> tuple[_uuid.UUID, str, _uuid.UUID]:
    """Returns (user_id, role, profile_id)."""
    user_id = get_current_user_id(request)
    role = get_current_user_role(request)
    profile_id = get_current_profile_id(request)
    return user_id, role, profile_id
