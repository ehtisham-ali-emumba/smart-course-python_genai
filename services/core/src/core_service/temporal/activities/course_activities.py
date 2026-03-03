"""Real HTTP activities that call course-service."""

import logging
from dataclasses import dataclass, field

import aiohttp
from temporalio import activity

from core_service.config import core_settings
from core_service.temporal.activities.http_client import get_json, post_json

logger = logging.getLogger(__name__)

COURSE_SERVICE = core_settings.COURSE_SERVICE_URL


# ── Data classes ───────────────────────────────────────────────────────────────


@dataclass
class FetchCourseInput:
    course_id: int


@dataclass
class FetchCourseOutput:
    success: bool
    course_id: int
    title: str | None = None
    instructor_id: int | None = None
    status: str | None = None
    error: str | None = None


@dataclass
class EnrollInCourseInput:
    student_id: int
    course_id: int
    payment_amount: float = 0
    enrollment_source: str = "web"


@dataclass
class EnrollInCourseOutput:
    success: bool
    enrollment_id: int | None = None
    enrollment_status: str | None = None
    error: str | None = None


@dataclass
class FetchCourseModulesInput:
    course_id: int
    instructor_id: int = 0  # used as X-User-ID for content endpoint


@dataclass
class FetchCourseModulesOutput:
    success: bool
    course_id: int
    modules: list[dict] | None = None
    module_count: int = 0
    error: str | None = None


# ── Activities ─────────────────────────────────────────────────────────────────


@activity.defn(name="fetch_course_details")
async def fetch_course_details(input: FetchCourseInput) -> FetchCourseOutput:
    """
    GET http://course-service:8002/api/v1/courses/{course_id}
    Public endpoint — no auth header required.
    """
    url = f"{COURSE_SERVICE}/courses/{input.course_id}"

    try:
        data = await get_json(url)
        return FetchCourseOutput(
            success=True,
            course_id=input.course_id,
            title=data.get("title"),
            instructor_id=data.get("instructor_id"),
            status=data.get("status"),
        )
    except Exception as e:
        logger.warning(
            "fetch_course_details failed for course_id=%d: %s", input.course_id, e
        )
        return FetchCourseOutput(success=False, course_id=input.course_id, error=str(e))


@activity.defn(name="enroll_in_course")
async def enroll_in_course(
    input: EnrollInCourseInput,
) -> EnrollInCourseOutput:
    """
    POST /course/enrollments/internal/create to enroll a student.

    Uses the internal endpoint which:
    - Creates enrollment directly in DB (no Kafka event)
    - Is idempotent (returns existing enrollment if already enrolled)
    """
    logger.info(
        "enroll_in_course: student_id=%d, course_id=%d",
        input.student_id,
        input.course_id,
    )

    url = f"{COURSE_SERVICE}/course/enrollments/internal/create"
    headers = {"X-User-ID": str(input.student_id), "X-User-Role": "student"}
    payload = {
        "course_id": input.course_id,
        "payment_amount": input.payment_amount,
        "enrollment_source": input.enrollment_source,
    }

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                body = await resp.json(content_type=None)

                if resp.status in (200, 201):
                    logger.info(
                        "Enrollment created/confirmed: enrollment_id=%s, status=%s",
                        body.get("id"),
                        body.get("status"),
                    )
                    return EnrollInCourseOutput(
                        success=True,
                        enrollment_id=body.get("id"),
                        enrollment_status=body.get("status"),
                    )

                # Any non-2xx error
                logger.error(
                    "enroll_in_course failed %d for student=%d course=%d: %s",
                    resp.status,
                    input.student_id,
                    input.course_id,
                    body,
                )
                return EnrollInCourseOutput(
                    success=False,
                    error=f"HTTP {resp.status}: {body.get('detail', body)}",
                )

    except Exception as e:
        logger.error(
            "enroll_in_course failed for student=%d course=%d: %s",
            input.student_id,
            input.course_id,
            e,
            exc_info=True,
        )
        return EnrollInCourseOutput(success=False, error=str(e))


@activity.defn(name="fetch_course_modules")
async def fetch_course_modules(
    input: FetchCourseModulesInput,
) -> FetchCourseModulesOutput:
    """
    GET http://course-service:8002/api/v1/courses/{course_id}/content
    Requires X-User-ID header (uses instructor_id if provided, else student-style).
    """
    url = f"{COURSE_SERVICE}/courses/{input.course_id}/content"
    uid = input.instructor_id if input.instructor_id else 1
    headers = {
        "X-User-ID": str(uid),
        "X-User-Role": "instructor" if input.instructor_id else "student",
    }

    try:
        data = await get_json(url, headers=headers)
        modules = data.get("modules", [])
        return FetchCourseModulesOutput(
            success=True,
            course_id=input.course_id,
            modules=modules,
            module_count=len(modules),
        )
    except Exception as e:
        logger.warning(
            "fetch_course_modules failed for course_id=%d: %s", input.course_id, e
        )
        return FetchCourseModulesOutput(
            success=False, course_id=input.course_id, error=str(e)
        )


COURSE_ACTIVITIES = [
    fetch_course_details,
    enroll_in_course,
    fetch_course_modules,
]

__all__ = [
    "fetch_course_details",
    "enroll_in_course",
    "fetch_course_modules",
    "FetchCourseInput",
    "FetchCourseOutput",
    "EnrollInCourseInput",
    "EnrollInCourseOutput",
    "FetchCourseModulesInput",
    "FetchCourseModulesOutput",
    "COURSE_ACTIVITIES",
]
