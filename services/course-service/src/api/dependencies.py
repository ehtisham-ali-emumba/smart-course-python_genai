from fastapi import HTTPException, Request, status


def get_current_user_id(request: Request) -> int:
    """
    Extract current user ID from X-User-ID header.
    This header is set by the API Gateway after JWT verification.
    """
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return int(user_id)


def get_current_user_role(request: Request) -> str:
    """
    Extract current user role from X-User-Role header.
    This header is set by the API Gateway after JWT verification.
    """
    role = request.headers.get("X-User-Role")
    if not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return role


def require_instructor(request: Request) -> int:
    """
    Require that the current user is an instructor.
    Returns user_id if authorized.
    """
    user_id = get_current_user_id(request)
    role = get_current_user_role(request)
    if role not in ("instructor", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Instructor role required",
        )
    return user_id
