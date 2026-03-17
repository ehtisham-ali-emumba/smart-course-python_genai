"""Start course publish workflow on Temporal."""

import logging
import uuid
import uuid as _uuid

from temporalio.client import Client

from shared.temporal.constants import Workflows, TaskQueues
from shared.temporal.inputs import CoursePublishWorkflowInput

logger = logging.getLogger(__name__)


async def start_course_publish_workflow(
    client: Client,
    *,
    course_id: _uuid.UUID,
    instructor_id: _uuid.UUID,
    course_title: str,
) -> str:
    """Start the CoursePublishWorkflow on Temporal and return the workflow ID."""
    event_id = str(uuid.uuid4())
    workflow_id = f"course-publish-crs{course_id}-{event_id}"

    workflow_input = CoursePublishWorkflowInput(
        course_id=str(course_id),
        instructor_id=str(instructor_id),
        course_title=course_title,
    )

    handle = await client.start_workflow(
        Workflows.COURSE_PUBLISH,
        workflow_input,
        id=workflow_id,
        task_queue=TaskQueues.CORE,
    )

    logger.info("CoursePublishWorkflow started: workflow_id=%s", handle.id)
    return handle.id
