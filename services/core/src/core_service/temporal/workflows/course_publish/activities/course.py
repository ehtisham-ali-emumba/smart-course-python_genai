"""Course-service activities for course publish workflow."""

import logging
from dataclasses import dataclass

from temporalio import activity

from core_service.config import core_settings
from core_service.temporal.common.http_client import get_json, post_json, patch_json
from shared.temporal.constants import Activities

logger = logging.getLogger(__name__)

COURSE_SERVICE = core_settings.COURSE_SERVICE_URL


# ── Dataclasses ───────────────────────────────────────────────


@dataclass
class ValidateCourseInput:
    course_id: str
    instructor_id: str


@dataclass
class ValidateCourseOutput:
    is_valid: bool
    reason: str = ""
    course_status: str = ""


@dataclass
class MarkCoursePublishedInput:
    course_id: str


@dataclass
class MarkCoursePublishedOutput:
    success: bool
    error: str = ""


# ── Activities ────────────────────────────────────────────────


@activity.defn(name=Activities.VALIDATE_COURSE_FOR_PUBLISH)
async def validate_course_for_publish(
    input: ValidateCourseInput,
) -> ValidateCourseOutput:
    """Validate course exists, belongs to instructor, is not already published,
    and has content (at least 1 module).
    """
    activity.logger.info("validate_course_for_publish course_id=%s", input.course_id)

    try:
        # 1. Fetch course details (public endpoint)
        course = await get_json(f"{COURSE_SERVICE}/courses/{input.course_id}")

        # 2. Check ownership
        if str(course.get("instructor_id")) != input.instructor_id:
            return ValidateCourseOutput(
                is_valid=False,
                reason="Instructor does not own this course",
            )

        # 3. Check status — only draft/publish_requested can proceed
        status = course.get("status", "")
        if status not in ("draft", "publish_requested"):
            return ValidateCourseOutput(
                is_valid=False,
                reason=f"Course cannot be published from status '{status}'",
                course_status=status,
            )

        # 4. Check required fields
        if not course.get("title", "").strip():
            return ValidateCourseOutput(
                is_valid=False, reason="Course must have a title"
            )
        if not course.get("description", "").strip():
            return ValidateCourseOutput(
                is_valid=False, reason="Course must have a description"
            )

        # 5. Check course has content (modules)
        try:
            content = await get_json(
                f"{COURSE_SERVICE}/courses/{input.course_id}/content"
            )
            modules = (
                content if isinstance(content, list) else content.get("modules", [])
            )
            if not modules:
                return ValidateCourseOutput(
                    is_valid=False,
                    reason="Course must have at least one module with content",
                )
        except Exception as e:
            activity.logger.warning(
                "Could not fetch course content for validation: %s", e
            )
            # Non-blocking — allow publish even if content check fails

        return ValidateCourseOutput(
            is_valid=True,
            course_status=status,
        )

    except Exception as e:
        activity.logger.error("validate_course_for_publish failed: %s", e)
        raise  # Let Temporal retry


@activity.defn(name=Activities.MARK_COURSE_PUBLISHED)
async def mark_course_published(
    input: MarkCoursePublishedInput,
) -> MarkCoursePublishedOutput:
    """Call course-service internal endpoint to mark course as published in DB.

    This also fires the course.published Kafka event from course-service.
    """
    activity.logger.info("mark_course_published course_id=%s", input.course_id)

    try:
        # Internal endpoint — uses X-User-ID / X-User-Role headers
        result = await patch_json(
            f"{COURSE_SERVICE}/courses/{input.course_id}/internal/publish",
            payload={},
            headers={
                "X-User-ID": "0",  # system/internal call
                "X-User-Role": "system",
            },
        )
        return MarkCoursePublishedOutput(success=True)

    except Exception as e:
        activity.logger.error("mark_course_published failed: %s", e)
        return MarkCoursePublishedOutput(success=False, error=str(e))


COURSE_ACTIVITIES = [
    validate_course_for_publish,
    mark_course_published,
]
