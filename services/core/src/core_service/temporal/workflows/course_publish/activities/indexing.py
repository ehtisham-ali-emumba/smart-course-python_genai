"""AI-service activities for RAG indexing during course publish."""

import logging
from dataclasses import dataclass

from temporalio import activity

from core_service.config import core_settings
from core_service.temporal.common.http_client import get_json, post_json
from shared.temporal.constants import Activities

logger = logging.getLogger(__name__)

AI_SERVICE = core_settings.AI_SERVICE_URL


# ── Dataclasses ───────────────────────────────────────────────


@dataclass
class TriggerIndexingInput:
    course_id: str
    instructor_id: str


@dataclass
class TriggerIndexingOutput:
    success: bool
    status: str = ""  # "pending"
    error: str = ""


@dataclass
class PollIndexingStatusInput:
    course_id: str
    instructor_id: str


@dataclass
class PollIndexingStatusOutput:
    status: str  # "pending" | "indexing" | "indexed" | "failed"
    error_message: str | None = None
    total_chunks: int = 0


# ── Activities ────────────────────────────────────────────────


@activity.defn(name=Activities.TRIGGER_COURSE_INDEXING)
async def trigger_course_indexing(
    input: TriggerIndexingInput,
) -> TriggerIndexingOutput:
    """POST /api/v1/ai/index/courses/{course_id}/build to trigger RAG indexing.

    The ai-service requires instructor auth via X-User-ID / X-User-Role headers.
    Returns 202 Accepted with status "pending".
    """
    activity.logger.info("trigger_course_indexing course_id=%s", input.course_id)

    try:
        result = await post_json(
            f"{AI_SERVICE}/api/v1/ai/index/courses/{input.course_id}/build",
            payload={"force_rebuild": True},
            headers={
                "X-User-ID": str(input.instructor_id),
                "X-User-Role": "instructor",
            },
        )

        return TriggerIndexingOutput(
            success=True,
            status=result.get("status", "pending"),
        )

    except Exception as e:
        activity.logger.error("trigger_course_indexing failed: %s", e)
        return TriggerIndexingOutput(success=False, error=str(e))


@activity.defn(name=Activities.POLL_COURSE_INDEXING_STATUS)
async def poll_course_indexing_status(
    input: PollIndexingStatusInput,
) -> PollIndexingStatusOutput:
    """GET /api/v1/ai/index/courses/{course_id}/status to check indexing progress.

    Returns status: pending | indexing | indexed | failed
    """
    activity.logger.info("poll_course_indexing_status course_id=%s", input.course_id)

    try:
        result = await get_json(
            f"{AI_SERVICE}/api/v1/ai/index/courses/{input.course_id}/status",
            headers={
                "X-User-ID": str(input.instructor_id),
                "X-User-Role": "instructor",
            },
        )

        return PollIndexingStatusOutput(
            status=result.get("status", "pending"),
            error_message=result.get("error_message"),
            total_chunks=result.get("total_chunks", 0),
        )

    except Exception as e:
        activity.logger.error("poll_course_indexing_status failed: %s", e)
        raise  # Let Temporal retry — transient network error


INDEXING_ACTIVITIES = [
    trigger_course_indexing,
    poll_course_indexing_status,
]
