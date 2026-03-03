"""Real HTTP activities that call user-service."""

import logging
from dataclasses import dataclass

from temporalio import activity

from core_service.config import core_settings
from core_service.temporal.common.http_client import get_json

logger = logging.getLogger(__name__)

USER_SERVICE = core_settings.USER_SERVICE_URL


# ── Data classes ───────────────────────────────────────────────────────────────


@dataclass
class FetchUserInput:
    user_id: int


@dataclass
class FetchUserOutput:
    success: bool
    user_id: int
    email: str | None = None
    name: str | None = None
    role: str | None = None
    error: str | None = None


@dataclass
class ValidateUserEnrollmentInput:
    user_id: int


@dataclass
class ValidateUserEnrollmentOutput:
    is_valid: bool
    user_id: int
    reason: str | None = None


# ── Activities ─────────────────────────────────────────────────────────────────


@activity.defn(name="fetch_user_details")
async def fetch_user_details(input: FetchUserInput) -> FetchUserOutput:
    """
    GET http://user-service:8001/api/v1/auth/me
    Pass X-User-ID header — user-service reads it directly (set by gateway in prod).
    """
    url = f"{USER_SERVICE}/auth/me"
    headers = {"X-User-ID": str(input.user_id), "X-User-Role": "student"}

    try:
        data = await get_json(url, headers=headers)
        full_name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
        return FetchUserOutput(
            success=True,
            user_id=input.user_id,
            email=data.get("email"),
            name=full_name or None,
            role=data.get("role", "student"),
        )
    except Exception as e:
        logger.warning("fetch_user_details failed for user_id=%d: %s", input.user_id, e)
        return FetchUserOutput(success=False, user_id=input.user_id, error=str(e))


@activity.defn(name="validate_user_for_enrollment")
async def validate_user_for_enrollment(
    input: ValidateUserEnrollmentInput,
) -> ValidateUserEnrollmentOutput:
    """
    Verify user exists and is an active student.
    Calls the same /me endpoint — if the call succeeds, user is valid.
    """
    url = f"{USER_SERVICE}/auth/me"
    headers = {"X-User-ID": str(input.user_id), "X-User-Role": "student"}

    try:
        data = await get_json(url, headers=headers)

        if not data.get("is_active", True):
            return ValidateUserEnrollmentOutput(
                is_valid=False,
                user_id=input.user_id,
                reason="User account is not active",
            )

        role = data.get("role", "student")
        if role == "instructor":
            return ValidateUserEnrollmentOutput(
                is_valid=False,
                user_id=input.user_id,
                reason="Instructors cannot enroll as students",
            )

        return ValidateUserEnrollmentOutput(is_valid=True, user_id=input.user_id)

    except Exception as e:
        logger.error(
            "validate_user_for_enrollment failed for user_id=%d: %s", input.user_id, e
        )
        # Let Temporal retry via RetryPolicy
        raise


USER_ACTIVITIES = [fetch_user_details, validate_user_for_enrollment]

__all__ = [
    "fetch_user_details",
    "validate_user_for_enrollment",
    "FetchUserInput",
    "FetchUserOutput",
    "ValidateUserEnrollmentInput",
    "ValidateUserEnrollmentOutput",
    "USER_ACTIVITIES",
]
