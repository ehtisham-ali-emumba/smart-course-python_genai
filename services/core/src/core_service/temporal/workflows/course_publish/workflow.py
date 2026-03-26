"""Course publish workflow that orchestrates the publishing process."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.workflow import ParentClosePolicy

# All non-stdlib imports must go through imports_passed_through() because
# importing `shared.*` triggers shared/__init__.py which pulls in boto3/S3,
# and boto3 → urllib3 → http.client which is restricted by the Temporal sandbox.
with workflow.unsafe.imports_passed_through():
    from shared.temporal.constants import Workflows
    from shared.temporal.inputs import (
        CoursePublishWorkflowInput,
        CoursePublishWorkflowOutput,
        CourseRagIndexingChildWorkflowInput,
    )
    from core_service.temporal.workflows.course_publish.activities import (
        # Course activities
        validate_course_for_publish,
        mark_course_published,
        ValidateCourseInput,
        MarkCoursePublishedInput,
        # Notification activities
        notify_instructor_publish_success,
        notify_instructor_publish_failure,
        NotifyInstructorInput,
    )
    from core_service.temporal.workflows.course_publish.rag_indexing_child_workflow import (
        CourseRagIndexingChildWorkflow,
    )


DEFAULT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
)


@workflow.defn(name=Workflows.COURSE_PUBLISH)
class CoursePublishWorkflow:
    """
    Workflow that orchestrates course publishing:

    1. Validate course is ready (has content, correct status)
    2. Mark course as published in course-service DB
    3. Notify instructor of success
    4. Start child workflow for RAG indexing (fire-and-forget)
    """

    def __init__(self):
        self.steps_completed: list[str] = []
        self.steps_failed: list[str] = []

    @workflow.run
    async def run(
        self, input: CoursePublishWorkflowInput
    ) -> CoursePublishWorkflowOutput:
        workflow.logger.info(
            "Starting CoursePublishWorkflow for course_id=%s, instructor_id=%s",
            input.course_id,
            input.instructor_id,
        )
        workflow_id = workflow.info().workflow_id

        try:
            # Step 1: Validate course is ready for publishing
            await self._validate_course(input)

            # Step 2: Mark course as published in DB (moved UP - no longer blocked by indexing)
            await self._mark_published(input)

            # Step 3: Notify instructor of success
            await self._notify_instructor_success(input)

            # Step 4: Start RAG indexing as a child workflow (fire-and-forget)
            await self._start_rag_indexing_child(input)

            workflow.logger.info(
                "CoursePublishWorkflow completed for course_id=%s",
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
                "CoursePublishWorkflow failed for course_id=%s: %s",
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

    async def _mark_published(self, input: CoursePublishWorkflowInput) -> None:
        """Step 2: Mark course as published in course-service DB."""
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
        """Step 3: Notify instructor that course is published."""
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

    async def _start_rag_indexing_child(
        self, input: CoursePublishWorkflowInput
    ) -> None:
        """Step 4: Start RAG indexing as a fire-and-forget child workflow.

        Uses ParentClosePolicy.ABANDON so the child continues running
        even after this parent workflow completes.
        """
        step_name = "start_rag_indexing_child"
        workflow.logger.info("Step: %s", step_name)

        try:
            await workflow.start_child_workflow(
                CourseRagIndexingChildWorkflow.run,
                CourseRagIndexingChildWorkflowInput(
                    course_id=input.course_id,
                    instructor_id=input.instructor_id,
                    user_id=input.user_id,
                    course_title=input.course_title,
                ),
                id=f"rag-indexing-crs{input.course_id}-{workflow.info().workflow_id}",
                parent_close_policy=ParentClosePolicy.ABANDON,
            )
            self.steps_completed.append(step_name)
            workflow.logger.info(
                "RAG indexing child workflow started for course_id=%s",
                input.course_id,
            )
        except Exception as e:
            # Non-critical — course is already published
            workflow.logger.warning(
                "Failed to start RAG indexing child workflow (non-critical): %s",
                str(e),
            )
            self.steps_failed.append(step_name)

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
        }
