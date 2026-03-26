"""Child workflow that handles RAG indexing for a course (fire-and-forget)."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from shared.temporal.constants import Workflows
    from shared.temporal.inputs import (
        CourseRagIndexingChildWorkflowInput,
        CourseRagIndexingChildWorkflowOutput,
    )
    from core_service.temporal.workflows.course_publish.activities import (
        trigger_course_indexing,
        poll_course_indexing_status,
        TriggerIndexingInput,
        PollIndexingStatusInput,
    )


DEFAULT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
)

INDEXING_POLL_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    backoff_coefficient=1.5,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=5,
)


@workflow.defn(name=Workflows.COURSE_RAG_INDEXING_CHILD)
class CourseRagIndexingChildWorkflow:
    """
    Child workflow that handles RAG indexing independently of course publishing.

    Steps:
    1. Trigger RAG indexing via ai-service
    2. Poll until indexing completes
    """

    def __init__(self):
        self.indexing_status: str = "not_started"

    @workflow.run
    async def run(
        self, input: CourseRagIndexingChildWorkflowInput
    ) -> CourseRagIndexingChildWorkflowOutput:
        workflow.logger.info(
            "Starting CourseRagIndexingChildWorkflow for course_id=%s",
            input.course_id,
        )
        workflow_id = workflow.info().workflow_id

        try:
            # Step 1: Trigger RAG indexing
            trigger_result = await workflow.execute_activity(
                trigger_course_indexing,
                TriggerIndexingInput(
                    course_id=input.course_id,
                    instructor_id=input.instructor_id,
                    user_id=input.user_id,
                ),
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=DEFAULT_RETRY_POLICY,
            )

            if not trigger_result.success:
                raise RuntimeError(
                    f"Failed to trigger indexing: {trigger_result.error}"
                )

            self.indexing_status = trigger_result.status

            # Step 2: Poll until indexed or failed
            max_attempts = 60
            poll_interval_secs = 10

            for attempt in range(1, max_attempts + 1):
                await workflow.sleep(timedelta(seconds=poll_interval_secs))

                result = await workflow.execute_activity(
                    poll_course_indexing_status,
                    PollIndexingStatusInput(
                        course_id=input.course_id,
                        instructor_id=input.instructor_id,
                        user_id=input.user_id,
                    ),
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=INDEXING_POLL_RETRY_POLICY,
                )

                self.indexing_status = result.status

                workflow.logger.info(
                    "Indexing poll attempt %d/%d: status=%s",
                    attempt,
                    max_attempts,
                    result.status,
                )

                if result.status == "indexed":
                    return CourseRagIndexingChildWorkflowOutput(
                        workflow_id=workflow_id,
                        course_id=input.course_id,
                        success=True,
                        indexing_status="indexed",
                    )

                if result.status == "failed":
                    raise RuntimeError(
                        f"RAG indexing failed: {result.error_message or 'unknown'}"
                    )

            raise TimeoutError(
                f"RAG indexing timed out after {max_attempts * poll_interval_secs}s"
            )

        except Exception as e:
            workflow.logger.error(
                "CourseRagIndexingChildWorkflow failed for course_id=%s: %s",
                input.course_id,
                str(e),
            )
            return CourseRagIndexingChildWorkflowOutput(
                workflow_id=workflow_id,
                course_id=input.course_id,
                success=False,
                indexing_status=self.indexing_status,
                error_message=str(e),
            )

    @workflow.query(name="get_indexing_status")
    def get_indexing_status(self) -> dict:
        return {"indexing_status": self.indexing_status}
