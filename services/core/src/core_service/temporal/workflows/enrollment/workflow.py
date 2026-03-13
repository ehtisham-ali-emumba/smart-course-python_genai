"""Enrollment workflow that orchestrates student enrollment process."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

# All non-stdlib imports must go through imports_passed_through() because
# importing `shared.*` triggers shared/__init__.py which pulls in boto3/S3,
# and boto3 → urllib3 → http.client which is restricted by the Temporal sandbox.
with workflow.unsafe.imports_passed_through():
    from shared.temporal.constants import Workflows
    from shared.temporal.inputs import (
        EnrollmentWorkflowInput,
        EnrollmentWorkflowOutput,
    )
    from core_service.temporal.workflows.enrollment.activities import (
        # User activities
        fetch_user_details,
        validate_user_for_enrollment,
        FetchUserInput,
        ValidateUserEnrollmentInput,
        # Course activities
        fetch_course_details,
        enroll_in_course,
        fetch_course_modules,
        FetchCourseInput,
        EnrollInCourseInput,
        FetchCourseModulesInput,
        # Notification activities
        trigger_enrollment_notifications,
        TriggerEnrollmentNotificationsInput,
    )


# Retry policy for activities
DEFAULT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
)


@workflow.defn(name=Workflows.ENROLLMENT)
class EnrollmentWorkflow:
    """
    Workflow that orchestrates the student enrollment process.

    This workflow is triggered when a student enrolls in a course.
    It performs the following steps:
    1. Validate user can enroll
    2. Fetch user details
    3. Fetch course details
    4. Enroll in course (verifies existing enrollment or creates new one)
    5. Trigger enrollment notifications (email + in-app via notification-service)
    """

    def __init__(self):
        self.steps_completed: list[str] = []
        self.steps_failed: list[str] = []
        self.user_details: dict | None = None
        self.course_details: dict | None = None

    @workflow.run
    async def run(self, input: EnrollmentWorkflowInput) -> EnrollmentWorkflowOutput:
        """Execute the enrollment workflow."""
        workflow.logger.info(
            "Starting EnrollmentWorkflow for student_id=%d, course_id=%d",
            input.student_id,
            input.course_id,
        )

        workflow_id = workflow.info().workflow_id

        try:
            # Step 1: Validate user for enrollment
            await self._validate_user(input.student_id)

            # Step 2: Fetch user details
            await self._fetch_user_details(input.student_id, input.student_email)

            # Step 3: Fetch course details
            await self._fetch_course_details(input.course_id, input.course_title)

            # Step 4: Create enrollment in course-service
            await self._enroll_in_course(input)

            # Step 5: Trigger enrollment notifications (email + in-app)
            # The notifications/enrollment endpoint handles both via Celery tasks
            await self._send_enrollment_notifications(input)

            workflow.logger.info(
                "EnrollmentWorkflow completed successfully for student_id=%d, course_id=%d",
                input.student_id,
                input.course_id,
            )

            return EnrollmentWorkflowOutput(
                workflow_id=workflow_id,
                student_id=input.student_id,
                course_id=input.course_id,
                success=True,
                steps_completed=self.steps_completed,
                steps_failed=self.steps_failed,
            )

        except Exception as e:
            workflow.logger.error(
                "EnrollmentWorkflow failed for student_id=%d, course_id=%d: %s",
                input.student_id,
                input.course_id,
                str(e),
            )

            return EnrollmentWorkflowOutput(
                workflow_id=workflow_id,
                student_id=input.student_id,
                course_id=input.course_id,
                success=False,
                steps_completed=self.steps_completed,
                steps_failed=self.steps_failed,
                error_message=str(e),
            )

    async def _validate_user(self, student_id: int) -> None:
        """Step 1: Validate user can enroll."""
        step_name = "validate_user"
        workflow.logger.info("Step: %s", step_name)

        result = await workflow.execute_activity(
            validate_user_for_enrollment,
            ValidateUserEnrollmentInput(user_id=student_id),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        if not result.is_valid:
            self.steps_failed.append(step_name)
            raise ValueError(f"User validation failed: {result.reason}")

        self.steps_completed.append(step_name)

    async def _fetch_user_details(self, student_id: int, fallback_email: str) -> None:
        """Step 2: Fetch user details."""
        step_name = "fetch_user_details"
        workflow.logger.info("Step: %s", step_name)

        result = await workflow.execute_activity(
            fetch_user_details,
            FetchUserInput(user_id=student_id),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        if result.success:
            self.user_details = {
                "user_id": result.user_id,
                "email": result.email or fallback_email,
                "name": result.name,
                "role": result.role,
            }
            self.steps_completed.append(step_name)
        else:
            # Non-critical - use fallback values
            self.user_details = {
                "user_id": student_id,
                "email": fallback_email,
                "name": None,
                "role": "student",
            }
            workflow.logger.warning(
                "fetch_user_details failed, using fallback: %s",
                result.error,
            )
            self.steps_completed.append(f"{step_name}_fallback")

    async def _fetch_course_details(self, course_id: int, fallback_title: str) -> None:
        """Step 3: Fetch course details."""
        step_name = "fetch_course_details"
        workflow.logger.info("Step: %s", step_name)

        result = await workflow.execute_activity(
            fetch_course_details,
            FetchCourseInput(course_id=course_id),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        if result.success:
            self.course_details = {
                "course_id": result.course_id,
                "title": result.title or fallback_title,
                "instructor_id": result.instructor_id,
                "status": result.status,
            }
            self.steps_completed.append(step_name)
        else:
            # Non-critical - use fallback values
            self.course_details = {
                "course_id": course_id,
                "title": fallback_title,
                "instructor_id": None,
                "status": "published",
            }
            workflow.logger.warning(
                "fetch_course_details failed, using fallback: %s",
                result.error,
            )
            self.steps_completed.append(f"{step_name}_fallback")

    async def _enroll_in_course(self, input: EnrollmentWorkflowInput) -> None:
        """Step 4: Create enrollment in course-service (idempotent — 400 already-enrolled treated as success)."""
        step_name = "enroll_in_course"
        workflow.logger.info("Step: %s", step_name)

        result = await workflow.execute_activity(
            enroll_in_course,
            EnrollInCourseInput(
                student_id=input.student_id,
                course_id=input.course_id,
                payment_amount=input.payment_amount,
                enrollment_source=input.enrollment_source,
            ),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        if result.success:
            self.steps_completed.append(step_name)
        else:
            # Non-critical — enrollment may already exist outside this flow
            workflow.logger.warning(
                "enroll_in_course failed (non-critical): %s",
                result.error,
            )
            self.steps_completed.append(f"{step_name}_failed")

    async def _send_enrollment_notifications(
        self, input: EnrollmentWorkflowInput
    ) -> None:
        """Step 5: Trigger enrollment notifications (email + in-app).

        Calls notifications/enrollment endpoint which handles both:
        - Welcome email via Celery task
        - In-app notification via Celery task
        """
        step_name = "trigger_enrollment_notifications"
        workflow.logger.info("Step: %s", step_name)

        user_name = None
        if self.user_details:
            user_name = self.user_details.get("name")

        course_title = input.course_title
        if self.course_details:
            course_title = self.course_details.get("title", course_title)

        result = await workflow.execute_activity(
            trigger_enrollment_notifications,
            TriggerEnrollmentNotificationsInput(
                student_id=input.student_id,
                student_email=input.student_email,
                student_name=user_name,
                course_id=input.course_id,
                course_title=course_title,
            ),
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        if result.success:
            self.steps_completed.append(step_name)
        else:
            # Notifications are non-critical
            workflow.logger.warning(
                "trigger_enrollment_notifications failed (non-critical): %s",
                result.error,
            )
            self.steps_completed.append(f"{step_name}_failed")

    @workflow.query(name="get_status")
    def get_status(self) -> dict:
        """Query to get current workflow status."""
        return {
            "steps_completed": self.steps_completed,
            "steps_failed": self.steps_failed,
            "user_details": self.user_details,
            "course_details": self.course_details,
        }
