import uuid as _uuid

from fastapi import HTTPException, Request, status


def get_current_user_id(request: Request) -> _uuid.UUID:
    value = request.headers.get("X-User-ID")
    if not value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return _uuid.UUID(value)


def get_current_user_role(request: Request) -> str:
    value = request.headers.get("X-User-Role")
    if not value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return value


def get_current_profile_id(request: Request) -> _uuid.UUID | None:
    value = request.headers.get("X-Profile-ID")
    if not value:
        return None
    return _uuid.UUID(value)


def require_instructor(request: Request) -> _uuid.UUID:
    role = get_current_user_role(request)
    if role != "instructor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Instructor role required"
        )
    return get_current_user_id(request)


def require_instructor_or_self(request: Request, instructor_id: _uuid.UUID) -> None:
    role = get_current_user_role(request)
    if role == "instructor":
        return
    if role != "instructor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Instructor role required"
        )

    profile_id = get_current_profile_id(request)
    if profile_id and profile_id != instructor_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def require_student_or_instructor(request: Request, student_id: _uuid.UUID) -> None:
    role = get_current_user_role(request)
    if role == "instructor":
        return
    if role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Student role required")

    profile_id = get_current_profile_id(request)
    if profile_id and profile_id != student_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
