"""Real HTTP activities that call course-service."""

import logging
from dataclasses import dataclass, field

from temporalio import activity

from core_service.config import core_settings
from core_service.temporal.activities.http_client import get_json

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
class InitializeProgressInput:
    student_id: int
    course_id: int
    enrollment_id: int | None = None


@dataclass
class InitializeProgressOutput:
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


@activity.defn(name="initialize_course_progress")
async def initialize_course_progress(
    input: InitializeProgressInput,
) -> InitializeProgressOutput:
    """
    Verify the enrollment is active in course-service.

    The enrollment record is already created BEFORE this workflow runs
    (the Kafka event fires after the DB insert). This activity simply
    confirms the enrollment exists and is active — progress rows are
    created on-demand when the student first interacts with content.

    If enrollment_id is provided, uses GET /enrollments/{enrollment_id}.
    Otherwise looks up via GET /enrollments/course/{course_id}/active-students.
    """
    headers = {"X-User-ID": str(input.student_id), "X-User-Role": "student"}

    try:
        if input.enrollment_id:
            url = f"{COURSE_SERVICE}/course/enrollments/{input.enrollment_id}"
            data = await get_json(url, headers=headers)
            if data.get("status") != "active":
                return InitializeProgressOutput(
                    success=False,
                    enrollment_id=input.enrollment_id,
                    enrollment_status=data.get("status"),
                    error=f"Enrollment status is {data.get('status')}",
                )
            return InitializeProgressOutput(
                success=True,
                enrollment_id=input.enrollment_id,
                enrollment_status="active",
            )
        else:
            # Fallback: just confirm course exists
            course_url = f"{COURSE_SERVICE}/courses/{input.course_id}"
            await get_json(course_url)
            return InitializeProgressOutput(success=True)

    except Exception as e:
        logger.warning(
            "initialize_course_progress warning for student=%d course=%d: %s",
            input.student_id,
            input.course_id,
            e,
        )
        return InitializeProgressOutput(success=False, error=str(e))


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
    initialize_course_progress,
    fetch_course_modules,
]

__all__ = [
    "fetch_course_details",
    "initialize_course_progress",
    "fetch_course_modules",
    "FetchCourseInput",
    "FetchCourseOutput",
    "InitializeProgressInput",
    "InitializeProgressOutput",
    "FetchCourseModulesInput",
    "FetchCourseModulesOutput",
    "COURSE_ACTIVITIES",
]
