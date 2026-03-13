"""Course publish workflow that orchestrates the publishing process."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

# All non-stdlib imports must go through imports_passed_through() because
# importing `shared.*` triggers shared/__init__.py which pulls in boto3/S3,
# and boto3 → urllib3 → http.client which is restricted by the Temporal sandbox.
with workflow.unsafe.imports_passed_through():
    from shared.temporal.constants import Workflows
    from shared.temporal.inputs import (
        CoursePublishWorkflowInput,
        CoursePublishWorkflowOutput,
    )
    from core_service.temporal.workflows.course_publish.activities import (
        # Course activities
        validate_course_for_publish,
        mark_course_published,
        ValidateCourseInput,
        MarkCoursePublishedInput,
        # Indexing activities
        trigger_course_indexing,
        poll_course_indexing_status,
        TriggerIndexingInput,
        PollIndexingStatusInput,
        # Notification activities
        notify_instructor_publish_success,
        notify_instructor_publish_failure,
        NotifyInstructorInput,
    )


DEFAULT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
)

# Longer retry for indexing poll — it can take time
INDEXING_POLL_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    backoff_coefficient=1.5,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=1,  # We handle retries manually in the workflow
)


@workflow.defn(name=Workflows.COURSE_PUBLISH)
class CoursePublishWorkflow:
    """
    Workflow that orchestrates course publishing:

    1. Validate course is ready (has content, correct status)
    2. Validate instructor exists and is active
    3. Trigger RAG indexing via ai-service
    4. Poll RAG indexing status until complete
    5. Mark course as published in course-service DB
    6. Notify instructor of success/failure
    """

    def __init__(self):
        self.steps_completed: list[str] = []
        self.steps_failed: list[str] = []
        self.indexing_status: str = "not_started"

    @workflow.run
    async def run(
        self, input: CoursePublishWorkflowInput
    ) -> CoursePublishWorkflowOutput:
        workflow.logger.info(
            "Starting CoursePublishWorkflow for course_id=%d, instructor_id=%d",
            input.course_id,
            input.instructor_id,
        )
        workflow_id = workflow.info().workflow_id

        try:
            # Step 1: Validate course is ready for publishing
            await self._validate_course(input)

            # Step 2: Trigger RAG indexing
            await self._trigger_indexing(input)

            # Step 3: Poll RAG indexing until success
            await self._poll_indexing(input)

            # Step 4: Mark course as published in DB
            await self._mark_published(input)

            # Step 5: Notify instructor of success
            await self._notify_instructor_success(input)

            workflow.logger.info(
                "CoursePublishWorkflow completed for course_id=%d",
                input.course_id,
            )

            return CoursePublishWorkflowOutput(
                workflow_id=workflow_id,
                course_id=input.course_id,
                instructor_id=input.instructor_id,
                success=True,
                steps_completed=self.steps_completed,
                steps_failed=self.steps_failed,
            )

        except Exception as e:
            workflow.logger.error(
                "CoursePublishWorkflow failed for course_id=%d: %s",
                input.course_id,
                str(e),
            )

            # Best-effort: notify instructor of failure
            await self._notify_instructor_failure(input, str(e))

            return CoursePublishWorkflowOutput(
                workflow_id=workflow_id,
                course_id=input.course_id,
                instructor_id=input.instructor_id,
                success=False,
                steps_completed=self.steps_completed,
                steps_failed=self.steps_failed,
                error_message=str(e),
            )

    # ── Step implementations ──────────────────────────────────────

    async def _validate_course(self, input: CoursePublishWorkflowInput) -> None:
        """Step 1: Validate course exists, has content, is in draft status."""
        step_name = "validate_course"
        workflow.logger.info("Step: %s", step_name)

        result = await workflow.execute_activity(
            validate_course_for_publish,
            ValidateCourseInput(
                course_id=input.course_id,
                instructor_id=input.instructor_id,
            ),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        if not result.is_valid:
            self.steps_failed.append(step_name)
            raise ValueError(f"Course validation failed: {result.reason}")

        self.steps_completed.append(step_name)

    async def _trigger_indexing(self, input: CoursePublishWorkflowInput) -> None:
        """Step 2: Trigger RAG indexing via ai-service POST /build."""
        step_name = "trigger_indexing"
        workflow.logger.info("Step: %s", step_name)

        result = await workflow.execute_activity(
            trigger_course_indexing,
            TriggerIndexingInput(
                course_id=input.course_id,
                instructor_id=input.instructor_id,
            ),
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        if not result.success:
            self.steps_failed.append(step_name)
            raise RuntimeError(f"Failed to trigger indexing: {result.error}")

        self.indexing_status = result.status  # "pending"
        self.steps_completed.append(step_name)

    async def _poll_indexing(self, input: CoursePublishWorkflowInput) -> None:
        """Step 3: Poll ai-service GET /status until indexed or failed.

        Uses Temporal timer (workflow.sleep) between polls — this is durable
        and survives worker restarts.
        """
        step_name = "poll_indexing"
        workflow.logger.info("Step: %s", step_name)

        max_attempts = 60  # max 60 polls
        poll_interval_secs = 10  # 10s between polls (total max ~10 min)

        for attempt in range(1, max_attempts + 1):
            # Wait before polling (durable Temporal timer)
            await workflow.sleep(timedelta(seconds=poll_interval_secs))

            result = await workflow.execute_activity(
                poll_course_indexing_status,
                PollIndexingStatusInput(
                    course_id=input.course_id,
                    instructor_id=input.instructor_id,
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
                self.steps_completed.append(step_name)
                return

            if result.status == "failed":
                self.steps_failed.append(step_name)
                raise RuntimeError(
                    f"RAG indexing failed: {result.error_message or 'unknown error'}"
                )

            # "pending" or "indexing" — continue polling

        # Exhausted all attempts
        self.steps_failed.append(step_name)
        raise TimeoutError(
            f"RAG indexing did not complete after {max_attempts * poll_interval_secs}s"
        )

    async def _mark_published(self, input: CoursePublishWorkflowInput) -> None:
        """Step 4: Mark course as published in course-service DB."""
        step_name = "mark_published"
        workflow.logger.info("Step: %s", step_name)

        result = await workflow.execute_activity(
            mark_course_published,
            MarkCoursePublishedInput(course_id=input.course_id),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        if not result.success:
            self.steps_failed.append(step_name)
            raise RuntimeError(f"Failed to mark course published: {result.error}")

        self.steps_completed.append(step_name)

    async def _notify_instructor_success(
        self, input: CoursePublishWorkflowInput
    ) -> None:
        """Step 5: Notify instructor that course is published."""
        step_name = "notify_instructor_success"
        workflow.logger.info("Step: %s", step_name)

        result = await workflow.execute_activity(
            notify_instructor_publish_success,
            NotifyInstructorInput(
                instructor_id=input.instructor_id,
                course_id=input.course_id,
                course_title=input.course_title,
            ),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        if result.success:
            self.steps_completed.append(step_name)
        else:
            # Non-critical — course is already published
            workflow.logger.warning(
                "notify_instructor_success failed (non-critical): %s",
                result.error,
            )
            self.steps_completed.append(f"{step_name}_failed")

    async def _notify_instructor_failure(
        self, input: CoursePublishWorkflowInput, error_msg: str
    ) -> None:
        """Best-effort: Notify instructor that publishing failed."""
        step_name = "notify_instructor_failure"
        try:
            await workflow.execute_activity(
                notify_instructor_publish_failure,
                NotifyInstructorInput(
                    instructor_id=input.instructor_id,
                    course_id=input.course_id,
                    course_title=input.course_title,
                    error_message=error_msg,
                ),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=DEFAULT_RETRY_POLICY,
            )
            self.steps_completed.append(step_name)
        except Exception:
            workflow.logger.warning(
                "notify_instructor_failure failed (best-effort)",
                exc_info=True,
            )
            self.steps_failed.append(step_name)

    @workflow.query(name="get_status")
    def get_status(self) -> dict:
        return {
            "steps_completed": self.steps_completed,
            "steps_failed": self.steps_failed,
            "indexing_status": self.indexing_status,
        }
