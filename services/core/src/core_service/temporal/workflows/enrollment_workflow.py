"""Enrollment workflow that orchestrates student enrollment process."""

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

# Import activity stubs - these are executed by the worker
with workflow.unsafe.imports_passed_through():
    from core_service.temporal.activities import (
        # User activities
        fetch_user_details,
        validate_user_for_enrollment,
        FetchUserInput,
        ValidateUserEnrollmentInput,
        # Course activities
        fetch_course_details,
        initialize_course_progress,
        fetch_course_modules,
        FetchCourseInput,
        InitializeProgressInput,
        FetchCourseModulesInput,
        # Notification activities
        send_enrollment_welcome_email,
        send_in_app_notification,
        SendWelcomeEmailInput,
        SendInAppNotificationInput,
    )


@dataclass
class EnrollmentWorkflowInput:
    """Input for the enrollment workflow."""

    student_id: int
    course_id: int
    course_title: str
    student_email: str
    enrollment_id: int | None = None  # ← ADD THIS
    enrollment_timestamp: str | None = None


@dataclass
class EnrollmentWorkflowOutput:
    """Output from the enrollment workflow."""

    workflow_id: str
    student_id: int
    course_id: int
    success: bool
    steps_completed: list[str]
    steps_failed: list[str]
    error_message: str | None = None


# Retry policy for activities
DEFAULT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
)


@workflow.defn(name="EnrollmentWorkflow")
class EnrollmentWorkflow:
    """
    Workflow that orchestrates the student enrollment process.

    This workflow is triggered when a student enrolls in a course.
    It performs the following steps:
    1. Validate user can enroll
    2. Fetch user details
    3. Fetch course details
    4. Initialize progress tracking
    5. Send welcome email
    6. Send in-app notification

    Each step is an activity that makes an HTTP call to a microservice.
    If any step fails, the workflow knows exactly which step failed
    and can be retried or handled appropriately.
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

            # Step 4: Initialize progress tracking
            await self._initialize_progress(
                input.student_id, input.course_id, input.enrollment_id
            )

            # Step 5: Send welcome email
            await self._send_welcome_email(input)

            # Step 6: Send in-app notification
            await self._send_in_app_notification(input)

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

    async def _initialize_progress(
        self, student_id: int, course_id: int, enrollment_id: int | None
    ) -> None:
        """Step 4: Initialize progress tracking."""
        step_name = "initialize_progress"
        workflow.logger.info("Step: %s", step_name)

        result = await workflow.execute_activity(
            initialize_course_progress,
            InitializeProgressInput(
                student_id=student_id,
                course_id=course_id,
                enrollment_id=enrollment_id,
            ),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        if result.success:
            self.steps_completed.append(step_name)
        else:
            # Progress initialization is non-critical for workflow completion
            workflow.logger.warning(
                "initialize_progress failed (non-critical): %s",
                result.error,
            )
            self.steps_completed.append(f"{step_name}_skipped")

    async def _send_welcome_email(self, input: EnrollmentWorkflowInput) -> None:
        """Step 5: Send welcome email."""
        step_name = "send_welcome_email"
        workflow.logger.info("Step: %s", step_name)

        user_name = None
        if self.user_details:
            user_name = self.user_details.get("name")

        course_title = input.course_title
        if self.course_details:
            course_title = self.course_details.get("title", course_title)

        result = await workflow.execute_activity(
            send_enrollment_welcome_email,
            SendWelcomeEmailInput(
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
            # Email is non-critical
            workflow.logger.warning(
                "send_welcome_email failed (non-critical): %s",
                result.error,
            )
            self.steps_completed.append(f"{step_name}_failed")

    async def _send_in_app_notification(self, input: EnrollmentWorkflowInput) -> None:
        """Step 6: Send in-app notification."""
        step_name = "send_in_app_notification"
        workflow.logger.info("Step: %s", step_name)

        course_title = input.course_title
        if self.course_details:
            course_title = self.course_details.get("title", course_title)

        result = await workflow.execute_activity(
            send_in_app_notification,
            SendInAppNotificationInput(
                user_id=input.student_id,
                title="Enrollment Successful!",
                message=f"You have been enrolled in {course_title}. Start learning now!",
                notification_type="success",
            ),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY_POLICY,
        )

        if result.success:
            self.steps_completed.append(step_name)
        else:
            workflow.logger.warning(
                "send_in_app_notification failed (non-critical): %s",
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
