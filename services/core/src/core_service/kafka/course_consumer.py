"""Kafka consumer that triggers CoursePublishWorkflow on course.published events."""

import asyncio
import logging
import sys

from shared.kafka.consumer import EventConsumer
from shared.kafka.topics import Topics
from shared.schemas.envelope import EventEnvelope

from core_service.config import core_settings
from core_service.temporal.client import get_temporal_client
from core_service.temporal.workflows import (
    CoursePublishWorkflow,
    CoursePublishWorkflowInput,
)

logger = logging.getLogger(__name__)
MAX_RETRY_DELAY = 30


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


async def handle_course_event(topic: str, envelope: EventEnvelope) -> None:
    """
    Handle course.published events and start CoursePublishWorkflow.
    Ignores all other course event types (course.created, course.archived, etc.)
    """
    if envelope.event_type != "course.published":
        logger.debug("Ignoring course event type: %s", envelope.event_type)
        return

    payload = envelope.payload
    course_id = payload.get("course_id")
    instructor_id = payload.get("instructor_id")
    course_title = payload.get("title", f"Course {course_id}")
    published_at = payload.get("published_at", "")

    if not course_id or not instructor_id:
        logger.error("Invalid course.published payload: %s", payload)
        return

    logger.info(
        "Starting CoursePublishWorkflow | course_id=%d instructor_id=%d",
        course_id,
        instructor_id,
    )

    try:
        client = await get_temporal_client()

        # Create workflow input
        workflow_input = CoursePublishWorkflowInput(
            course_id=course_id,
            instructor_id=instructor_id,
            course_title=course_title,
            published_at=published_at,
        )

        # Start workflow (non-blocking - workflow runs asynchronously)
        # Using a deterministic workflow ID allows deduplication
        workflow_id = f"course-publish-{course_id}-{envelope.event_id}"

        handle = await client.start_workflow(
            CoursePublishWorkflow.run,
            workflow_input,
            id=workflow_id,
            task_queue=core_settings.TEMPORAL_TASK_QUEUE,
        )

        logger.info("CoursePublishWorkflow started: workflow_id=%s", handle.id)

    except Exception as e:
        logger.error("Failed to start CoursePublishWorkflow: %s", str(e), exc_info=True)


async def run_course_consumer() -> None:
    """
    Run the Kafka consumer that listens for course events
    and triggers CoursePublishWorkflow on course.published.
    """
    topics = [Topics.COURSE]
    attempt = 0

    _log(
        f"[core-service] Course consumer starting | "
        f"topics={topics} broker={core_settings.KAFKA_BOOTSTRAP_SERVERS}"
    )

    while True:
        consumer = EventConsumer(
            topics=topics,
            bootstrap_servers=core_settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id="core-service-course-consumer",
        )
        try:
            await consumer.start(handler=handle_course_event)
        except asyncio.CancelledError:
            _log("[core-service] Course consumer shutting down.")
            raise
        except Exception as e:
            attempt += 1
            delay = min(2**attempt, MAX_RETRY_DELAY)
            _log(
                f"[core-service] Course consumer error (attempt {attempt}), "
                f"retry in {delay}s: {e!r}"
            )
            await asyncio.sleep(delay)
        else:
            break
