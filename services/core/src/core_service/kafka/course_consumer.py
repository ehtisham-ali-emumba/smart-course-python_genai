"""Kafka consumer that triggers course publish workflows."""

import asyncio
import logging
import sys
from typing import Any

from shared.kafka.consumer import EventConsumer
from shared.kafka.topics import Topics
from shared.schemas.envelope import EventEnvelope

from core_service.config import core_settings
from core_service.temporal.common.temporal_client import get_temporal_client
from core_service.temporal.workflows import (
    CoursePublishWorkflow,
    CoursePublishWorkflowInput,
)

logger = logging.getLogger(__name__)
MAX_RETRY_DELAY = 30


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


async def handle_course_event(topic: str, envelope: EventEnvelope) -> None:
    """Handle course events and start Temporal workflows."""
    logger.info(
        "Received event: topic=%s event_type=%s event_id=%s",
        topic,
        envelope.event_type,
        envelope.event_id,
    )

    if envelope.event_type != "course.publish_requested":
        logger.debug("Ignoring event type: %s", envelope.event_type)
        return

    payload = envelope.payload
    course_id = payload.get("course_id")
    instructor_id = payload.get("instructor_id")
    title = payload.get("title", f"Course {course_id}")

    if not course_id or not instructor_id:
        logger.error("Invalid course publish event payload: %s", payload)
        return

    logger.info(
        "Starting CoursePublishWorkflow for course_id=%d, instructor_id=%d",
        course_id,
        instructor_id,
    )

    try:
        client = await get_temporal_client()

        workflow_input = CoursePublishWorkflowInput(
            course_id=course_id,
            instructor_id=instructor_id,
            course_title=title,
        )

        # Deterministic workflow ID — prevents duplicate workflows for same course
        workflow_id = f"course-publish-crs{course_id}-{envelope.event_id}"

        handle = await client.start_workflow(
            CoursePublishWorkflow.run,
            workflow_input,
            id=workflow_id,
            task_queue=core_settings.TEMPORAL_TASK_QUEUE,
        )

        logger.info("CoursePublishWorkflow started: workflow_id=%s", handle.id)

    except Exception as e:
        logger.error(
            "Failed to start CoursePublishWorkflow: %s",
            str(e),
            exc_info=True,
        )


async def run_course_consumer() -> None:
    """Run the Kafka consumer that listens for course events."""
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
            group_id="core-service-course",
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
