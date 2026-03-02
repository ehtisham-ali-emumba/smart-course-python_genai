"""Kafka consumer that triggers enrollment workflows."""

import asyncio
import logging
import sys
from typing import Any

from shared.kafka.consumer import EventConsumer
from shared.kafka.topics import Topics
from shared.schemas.envelope import EventEnvelope

from core_service.config import core_settings
from core_service.temporal.client import get_temporal_client
from core_service.temporal.workflows import (
    EnrollmentWorkflow,
    EnrollmentWorkflowInput,
)

logger = logging.getLogger(__name__)

MAX_RETRY_DELAY = 30


def _log(msg: str) -> None:
    """Log to stderr for visibility in Docker."""
    print(msg, file=sys.stderr, flush=True)


async def handle_enrollment_event(topic: str, envelope: EventEnvelope) -> None:
    """
    Handle enrollment events and start Temporal workflows.

    This is the bridge between Kafka events (fire-and-forget trigger)
    and Temporal workflows (orchestrated with activities).
    """
    logger.info(
        "Received event: topic=%s event_type=%s event_id=%s",
        topic,
        envelope.event_type,
        envelope.event_id,
    )

    if envelope.event_type != "enrollment.created":
        logger.debug("Ignoring event type: %s", envelope.event_type)
        return

    payload = envelope.payload
    student_id = payload.get("student_id")
    course_id = payload.get("course_id")
    enrollment_id = payload.get("enrollment_id")  # ← ADD
    course_title = payload.get("course_title", f"Course {course_id}")
    student_email = payload.get("email", "")

    if not student_id or not course_id:
        logger.error("Invalid enrollment event payload: %s", payload)
        return

    logger.info(
        "Starting EnrollmentWorkflow for student_id=%d, course_id=%d",
        student_id,
        course_id,
    )

    try:
        # Get Temporal client
        client = await get_temporal_client()

        # Create workflow input
        workflow_input = EnrollmentWorkflowInput(
            student_id=student_id,
            course_id=course_id,
            course_title=course_title,
            student_email=student_email,
            enrollment_id=enrollment_id,  # ← ADD
        )

        # Start workflow (non-blocking - workflow runs asynchronously)
        # Using a deterministic workflow ID allows deduplication
        workflow_id = f"enrollment-{student_id}-{course_id}-{envelope.event_id}"

        handle = await client.start_workflow(
            EnrollmentWorkflow.run,
            workflow_input,
            id=workflow_id,
            task_queue=core_settings.TEMPORAL_TASK_QUEUE,
        )

        logger.info(
            "EnrollmentWorkflow started: workflow_id=%s",
            handle.id,
        )

    except Exception as e:
        logger.error(
            "Failed to start EnrollmentWorkflow: %s",
            str(e),
            exc_info=True,
        )


async def run_enrollment_consumer() -> None:
    """
    Run the Kafka consumer that listens for enrollment events
    and triggers Temporal workflows.
    """
    topics = [Topics.ENROLLMENT]
    attempt = 0

    _log(
        f"[core-service] Enrollment consumer starting | "
        f"topics={topics} broker={core_settings.KAFKA_BOOTSTRAP_SERVERS}"
    )

    while True:
        consumer = EventConsumer(
            topics=topics,
            bootstrap_servers=core_settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id="core-service-enrollment",
        )
        try:
            await consumer.start(handler=handle_enrollment_event)
        except asyncio.CancelledError:
            _log("[core-service] Enrollment consumer shutting down.")
            raise
        except Exception as e:
            attempt += 1
            delay = min(2**attempt, MAX_RETRY_DELAY)
            _log(
                f"[core-service] Consumer error (attempt {attempt}), "
                f"retry in {delay}s: {e!r}"
            )
            await asyncio.sleep(delay)
        else:
            break
