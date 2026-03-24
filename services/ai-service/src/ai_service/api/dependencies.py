"""API dependencies for authentication and authorization."""

import uuid as _uuid

from fastapi import HTTPException, Request, status

from ai_service.services.index import IndexService
from ai_service.services.tutor import TutorService
from ai_service.services.instructor import InstructorService


def get_current_user_id(request: Request) -> _uuid.UUID:
    """Extract user ID from X-User-ID header."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return _uuid.UUID(user_id)


def get_current_user_role(request: Request) -> str:
    """Extract user role from X-User-Role header."""
    role = request.headers.get("X-User-Role")
    if not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return role


def get_current_profile_id(request: Request) -> _uuid.UUID:
    """Extract profile ID from X-Profile-ID header."""
    profile_id = request.headers.get("X-Profile-ID")
    if not profile_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Profile not found",
        )
    return _uuid.UUID(profile_id)


def require_instructor(request: Request) -> tuple[_uuid.UUID, _uuid.UUID]:
    """Require instructor or admin role. Returns (user_id, profile_id)."""
    user_id = get_current_user_id(request)
    role = get_current_user_role(request)
    if role not in ("instructor", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Instructor role required",
        )
    profile_id = get_current_profile_id(request)
    return user_id, profile_id


def require_student(request: Request) -> _uuid.UUID:
    """Require student or admin role."""
    user_id = get_current_user_id(request)
    role = get_current_user_role(request)
    if role not in ("student", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student role required",
        )
    return user_id


def get_authenticated_user(request: Request) -> tuple[_uuid.UUID, str]:
    """Get authenticated user ID and role."""
    user_id = get_current_user_id(request)
    role = get_current_user_role(request)
    return user_id, role


# Module-level reference for index service singleton
_index_service: IndexService | None = None


def set_index_service(svc: IndexService) -> None:
    """Called during app startup to set the index service singleton."""
    global _index_service
    _index_service = svc


def get_index_service() -> IndexService:
    """FastAPI dependency that returns the IndexService singleton."""
    if _index_service is None:
        raise RuntimeError("IndexService not initialized. Check app startup.")
    return _index_service


# Module-level reference for tutor service singleton
_tutor_service: TutorService | None = None


def set_tutor_service(ts: TutorService) -> None:
    """Called during app startup to set the tutor service singleton."""
    global _tutor_service
    _tutor_service = ts


def get_tutor_service() -> TutorService:
    """FastAPI dependency that returns the TutorService singleton."""
    if _tutor_service is None:
        raise RuntimeError("TutorService not initialized. Check app startup.")
    return _tutor_service


# Module-level reference for instructor service singleton
_instructor_service: InstructorService | None = None


def set_instructor_service(svc: InstructorService) -> None:
    """Called during app startup to set the instructor service singleton."""
    global _instructor_service
    _instructor_service = svc


def get_instructor_service() -> InstructorService:
    """FastAPI dependency that returns the InstructorService singleton."""
    if _instructor_service is None:
        raise RuntimeError("InstructorService not initialized. Check app startup.")
    return _instructor_service
