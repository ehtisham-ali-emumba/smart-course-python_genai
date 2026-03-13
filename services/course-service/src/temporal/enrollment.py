"""Start enrollment workflow on Temporal."""

import logging
import uuid
from decimal import Decimal

from temporalio.client import Client

from shared.temporal.constants import Workflows, TaskQueues
from shared.temporal.inputs import EnrollmentWorkflowInput

logger = logging.getLogger(__name__)


async def start_enrollment_workflow(
    client: Client,
    *,
    student_id: int,
    course_id: int,
    course_title: str,
    student_email: str = "",
    payment_amount: Decimal = Decimal(0),
    enrollment_source: str = "web",
) -> str:
    """Start the EnrollmentWorkflow on Temporal and return the workflow ID."""
    event_id = str(uuid.uuid4())
    workflow_id = f"enrollment-std{student_id}-crs{course_id}-{event_id}"

    workflow_input = EnrollmentWorkflowInput(
        student_id=student_id,
        course_id=course_id,
        course_title=course_title,
        student_email=student_email,
        payment_amount=float(payment_amount),
        enrollment_source=enrollment_source,
    )

    handle = await client.start_workflow(
        Workflows.ENROLLMENT,
        workflow_input,
        id=workflow_id,
        task_queue=TaskQueues.CORE,
    )

    logger.info("EnrollmentWorkflow started: workflow_id=%s", handle.id)
    return handle.id
