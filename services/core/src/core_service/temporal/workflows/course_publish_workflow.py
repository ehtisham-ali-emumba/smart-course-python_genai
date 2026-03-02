"""
CoursePublishWorkflow — orchestrates post-publish processing for a course.

Triggered by: course.published Kafka event (via course_consumer.py)

Steps:
  1. validate_course_for_publishing   — confirm course is published and has content
  2. fetch_course_content_for_rag     — pull full content from MongoDB via course-service
  3. generate_rag_embeddings          — DummyAIService: chunk + embed (→ real AI in Week 3)
  4. store_rag_index                  — DummyAIService: persist index (→ Qdrant in Week 3)
  5. fetch_enrolled_students          — get active student IDs for this course
  6. send_course_published_notif      — notify enrolled students
  7. send_instructor_notif            — notify instructor (course live + RAG status)

Compensation strategy:
  - Steps 1–2: Critical. Raise on failure so Temporal retries.
  - Steps 3–4: RAG failure is non-critical. Log and continue — publishing already happened.
  - Steps 5–7: Notification failure is non-critical. Log and continue.

The workflow always returns a CoursePublishWorkflowOutput regardless of partial failures,
recording which steps succeeded and which did not.
"""

from dataclasses import dataclass, field
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from core_service.temporal.activities import (
        # Course + AI activities
        validate_course_for_publishing,
        fetch_course_content_for_rag,
        generate_rag_embeddings,
        store_rag_index,
        fetch_enrolled_students,
        send_course_published_notification,
        send_instructor_course_published_notification,
        ValidateCoursePublishInput,
        FetchCourseContentForRagInput,
        GenerateRagEmbeddingsInput,
        StoreRagIndexInput,
        FetchEnrolledStudentsInput,
        SendCoursePublishedNotificationInput,
        SendInstructorNotificationInput,
    )


@dataclass
class CoursePublishWorkflowInput:
    course_id: int
    instructor_id: int
    course_title: str
    published_at: str = ""


@dataclass
class CoursePublishWorkflowOutput:
    workflow_id: str
    course_id: int
    success: bool
    rag_indexed: bool
    students_notified: int
    steps_completed: list[str] = field(default_factory=list)
    steps_failed: list[str] = field(default_factory=list)
    error_message: str | None = None


DEFAULT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=60),
    maximum_attempts=3,
)

LENIENT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=1.5,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=2,
)


@workflow.defn(name="CoursePublishWorkflow")
class CoursePublishWorkflow:
    """Orchestrates post-publish processing: RAG indexing + student/instructor notifications."""

    def __init__(self):
        self.steps_completed: list[str] = []
        self.steps_failed: list[str] = []
        self.rag_indexed: bool = False
        self.students_notified: int = 0

    @workflow.run
    async def run(
        self, input: CoursePublishWorkflowInput
    ) -> CoursePublishWorkflowOutput:
        workflow_id = workflow.info().workflow_id

        workflow.logger.info(
            "CoursePublishWorkflow started | workflow_id=%s course_id=%d instructor_id=%d",
            workflow_id,
            input.course_id,
            input.instructor_id,
        )

        try:
            # Step 1: Validate course for publishing
            await self._validate_course(input)

            # Step 2: Fetch course content for RAG
            content = await self._fetch_content(input)

            # Step 3: Generate RAG embeddings (non-critical)
            chunks, embeddings = await self._generate_embeddings(input, content)

            # Step 4: Store RAG index (non-critical)
            await self._store_index(input, chunks, embeddings)

            # Step 5: Fetch enrolled students
            student_ids = await self._fetch_students(input)

            # Step 6: Notify enrolled students (non-critical)
            await self._notify_students(input, student_ids)

            # Step 7: Notify instructor (non-critical)
            await self._notify_instructor(input)

            workflow.logger.info(
                "CoursePublishWorkflow completed | course_id=%d rag_indexed=%s students_notified=%d",
                input.course_id,
                self.rag_indexed,
                self.students_notified,
            )

            return CoursePublishWorkflowOutput(
                workflow_id=workflow_id,
                course_id=input.course_id,
                success=True,
                rag_indexed=self.rag_indexed,
                students_notified=self.students_notified,
                steps_completed=self.steps_completed,
                steps_failed=self.steps_failed,
            )

        except Exception as e:
            workflow.logger.error(
                "CoursePublishWorkflow failed | course_id=%d: %s",
                input.course_id,
                str(e),
            )

            return CoursePublishWorkflowOutput(
                workflow_id=workflow_id,
                course_id=input.course_id,
                success=False,
                rag_indexed=self.rag_indexed,
                students_notified=self.students_notified,
                steps_completed=self.steps_completed,
                steps_failed=self.steps_failed,
                error_message=str(e),
            )

    # ── Step implementations ───────────────────────────────────────────────────

    async def _validate_course(self, input: CoursePublishWorkflowInput) -> None:
        step = "validate_course"
        workflow.logger.info("Step %s: validating course %d", step, input.course_id)

        result = await workflow.execute_activity(
            validate_course_for_publishing,
            ValidateCoursePublishInput(
                course_id=input.course_id,
                instructor_id=input.instructor_id,
            ),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY,
        )

        if not result.is_valid:
            self.steps_failed.append(step)
            raise ValueError(f"Course validation failed: {result.reason}")

        workflow.logger.info(
            "Step %s: passed | title='%s' modules=%d",
            step,
            result.title,
            result.module_count,
        )
        self.steps_completed.append(step)

    async def _fetch_content(self, input: CoursePublishWorkflowInput) -> dict:
        step = "fetch_course_content"
        workflow.logger.info(
            "Step %s: fetching content for course %d", step, input.course_id
        )

        result = await workflow.execute_activity(
            fetch_course_content_for_rag,
            FetchCourseContentForRagInput(
                course_id=input.course_id,
                instructor_id=input.instructor_id,
            ),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY,
        )

        if not result.success:
            self.steps_failed.append(step)
            raise ValueError(f"Content fetch failed: {result.error}")

        workflow.logger.info("Step %s: fetched %d modules", step, result.module_count)
        self.steps_completed.append(step)
        return result.content

    async def _generate_embeddings(
        self,
        input: CoursePublishWorkflowInput,
        content: dict,
    ) -> tuple[list[str], list[list[float]]]:
        step = "generate_rag_embeddings"
        workflow.logger.info(
            "Step %s: generating embeddings for course %d", step, input.course_id
        )

        try:
            result = await workflow.execute_activity(
                generate_rag_embeddings,
                GenerateRagEmbeddingsInput(
                    course_id=input.course_id,
                    content=content,
                ),
                start_to_close_timeout=timedelta(
                    seconds=60
                ),  # Allow more time for processing
                retry_policy=LENIENT_RETRY,
            )

            if result.success:
                workflow.logger.info(
                    "Step %s: generated %d chunks", step, result.chunks_processed
                )
                self.steps_completed.append(step)
                self.rag_indexed = True
                return result.chunks, result.embeddings
            else:
                workflow.logger.warning(
                    "Step %s: failed (non-critical): %s", step, result.error
                )
                self.steps_failed.append(step)
                return [], []

        except Exception as e:
            workflow.logger.warning(
                "Step %s: exception (non-critical): %s", step, str(e)
            )
            self.steps_failed.append(step)
            return [], []

    async def _store_index(
        self,
        input: CoursePublishWorkflowInput,
        chunks: list[str],
        embeddings: list[list[float]],
    ) -> None:
        if not chunks or not embeddings:
            workflow.logger.info("Step store_rag_index: skipped (no chunks to store)")
            self.steps_failed.append("store_rag_index")
            return

        step = "store_rag_index"
        workflow.logger.info(
            "Step %s: storing index for course %d", step, input.course_id
        )

        try:
            result = await workflow.execute_activity(
                store_rag_index,
                StoreRagIndexInput(
                    course_id=input.course_id,
                    chunks=chunks,
                    embeddings=embeddings,
                ),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=LENIENT_RETRY,
            )

            if result.success:
                workflow.logger.info(
                    "Step %s: stored %d chunks", step, result.chunk_count
                )
                self.steps_completed.append(step)
            else:
                workflow.logger.warning(
                    "Step %s: failed (non-critical): %s", step, result.error
                )
                self.steps_failed.append(step)
                self.rag_indexed = False  # Override if store failed

        except Exception as e:
            workflow.logger.warning(
                "Step %s: exception (non-critical): %s", step, str(e)
            )
            self.steps_failed.append(step)
            self.rag_indexed = False

    async def _fetch_students(self, input: CoursePublishWorkflowInput) -> list[int]:
        step = "fetch_enrolled_students"
        workflow.logger.info(
            "Step %s: fetching students for course %d", step, input.course_id
        )

        try:
            result = await workflow.execute_activity(
                fetch_enrolled_students,
                FetchEnrolledStudentsInput(
                    course_id=input.course_id,
                    instructor_id=input.instructor_id,
                ),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=DEFAULT_RETRY,
            )

            if result.success:
                workflow.logger.info("Step %s: found %d students", step, result.count)
                self.steps_completed.append(step)
                return result.student_ids
            else:
                workflow.logger.warning("Step %s: failed: %s", step, result.error)
                self.steps_failed.append(step)
                return []

        except Exception as e:
            workflow.logger.warning("Step %s: exception: %s", step, str(e))
            self.steps_failed.append(step)
            return []

    async def _notify_students(
        self,
        input: CoursePublishWorkflowInput,
        student_ids: list[int],
    ) -> None:
        if not student_ids:
            workflow.logger.info("Step notify_students: skipped (no students)")
            self.steps_failed.append("notify_enrolled_students")
            return

        step = "notify_enrolled_students"
        workflow.logger.info(
            "Step %s: notifying %d students for course %d",
            step,
            len(student_ids),
            input.course_id,
        )

        try:
            result = await workflow.execute_activity(
                send_course_published_notification,
                SendCoursePublishedNotificationInput(
                    course_id=input.course_id,
                    course_title=input.course_title,
                    instructor_id=input.instructor_id,
                    affected_student_ids=student_ids,
                    event="published",
                ),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=LENIENT_RETRY,
            )

            if result.success:
                workflow.logger.info(
                    "Step %s: notified %d students", step, result.students_notified
                )
                self.steps_completed.append(step)
                self.students_notified = result.students_notified
            else:
                workflow.logger.warning(
                    "Step %s: failed (non-critical): %s", step, result.error
                )
                self.steps_failed.append(step)

        except Exception as e:
            workflow.logger.warning(
                "Step %s: exception (non-critical): %s", step, str(e)
            )
            self.steps_failed.append(step)

    async def _notify_instructor(self, input: CoursePublishWorkflowInput) -> None:
        step = "notify_instructor"
        workflow.logger.info(
            "Step %s: notifying instructor %d for course %d",
            step,
            input.instructor_id,
            input.course_id,
        )

        try:
            result = await workflow.execute_activity(
                send_instructor_course_published_notification,
                SendInstructorNotificationInput(
                    instructor_id=input.instructor_id,
                    course_id=input.course_id,
                    course_title=input.course_title,
                    rag_indexed=self.rag_indexed,
                ),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=LENIENT_RETRY,
            )

            if result.success:
                workflow.logger.info("Step %s: instructor notified", step)
                self.steps_completed.append(step)
            else:
                workflow.logger.warning(
                    "Step %s: failed (non-critical): %s", step, result.error
                )
                self.steps_failed.append(step)

        except Exception as e:
            workflow.logger.warning(
                "Step %s: exception (non-critical): %s", step, str(e)
            )
            self.steps_failed.append(step)

    @workflow.query(name="get_status")
    def get_status(self) -> dict:
        return {
            "course_id": (
                workflow.info().workflow_id.split("-")[-1]
                if "-" in workflow.info().workflow_id
                else None
            ),
            "steps_completed": self.steps_completed,
            "steps_failed": self.steps_failed,
            "rag_indexed": self.rag_indexed,
            "students_notified": self.students_notified,
        }
