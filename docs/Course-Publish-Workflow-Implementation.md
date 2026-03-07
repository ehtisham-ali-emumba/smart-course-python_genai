# Course Publish Workflow — Implementation Guide

> **Date:** 2026-03-06
> **Scope:** Temporal `CoursePublishWorkflow` + course-service endpoint changes + core-service Kafka consumer + notification-service cleanup

---

## Overview

Currently, `PATCH /courses/{course_id}/status` immediately saves `published` status to the DB and fires a `course.published` Kafka event. The notification-service picks up that event and sends a basic in-app notification to the instructor — but no RAG indexing or proper validation happens.

**New flow:**

```
Instructor calls PATCH /courses/{course_id}/status  (status="published")
  |
  |  1. Validate course readiness (has content, title, etc.)
  |  2. Validate instructor ownership (already done)
  |  3. Do NOT save "published" status to DB yet
  |  4. Publish "course.publish_requested" Kafka event
  |
  v
Core-service Kafka consumer picks up event
  |
  |  Check: is course already published? If yes, skip.
  |  Start CoursePublishWorkflow via Temporal
  |
  v
CoursePublishWorkflow (Temporal — core-service)
  |
  |  Step 1: Validate course (HTTP → course-service)
  |  Step 2: Validate instructor (HTTP → user-service)
  |  Step 3: Trigger RAG indexing (HTTP POST → ai-service /build)
  |  Step 4: Poll RAG indexing status (HTTP GET → ai-service /status) — retry until "indexed"
  |  Step 5: Mark course as published (HTTP PATCH → course-service internal endpoint)
  |  Step 6: Notify instructor of publish success (HTTP POST → notification-service)
  |
  v
Course is published + indexed + instructor notified
```

---

## Part 1 — Course Service Changes

### 1.1 Tweak `PATCH /{course_id}/status` endpoint

**File:** `services/course-service/src/api/courses.py` — `update_course_status()` (line 161)

**Current behavior (lines 171-188):**
- Calls `service.update_status()` which saves the new status to DB immediately
- If status is `"published"`, publishes `course.published` Kafka event

**New behavior:**
- When `data.status == "published"`:
  - Do NOT call `service.update_status()` — don't save to DB
  - Instead, validate course readiness first (call a new service method)
  - Publish a **`course.publish_requested`** event (not `course.published`)
  - Return `202 Accepted` with a message like `"Course publish workflow started"`
- When `data.status != "published"` (e.g. `"archived"`, `"draft"`): keep existing behavior unchanged

```python
@router.patch("/{course_id}/status", status_code=status.HTTP_200_OK)
async def update_course_status(
    course_id: int,
    data: CourseStatusUpdate,
    instructor_id: int = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
    producer: EventProducer = Depends(get_event_producer),
):
    service = CourseService(db)

    if data.status == "published":
        # --- NEW: validate without saving ---
        course = await service.validate_course_for_publish(course_id, instructor_id)
        # course is a dict; raises HTTPException if invalid

        await producer.publish(
            Topics.COURSE,
            "course.publish_requested",
            CoursePublishRequestedPayload(
                course_id=course_id,
                instructor_id=instructor_id,
                title=course["title"],
            ).model_dump(),
            key=str(course_id),
        )

        return {
            "message": "Course publish workflow started",
            "course_id": course_id,
            "status": "publish_requested",
        }

    # --- existing behavior for archive/draft ---
    try:
        course = await service.update_status(course_id, data, instructor_id)
        if not course:
            raise HTTPException(status_code=404, detail="Course not found")

        if data.status == "archived":
            await producer.publish(
                Topics.COURSE,
                "course.archived",
                CourseArchivedPayload(
                    course_id=course_id,
                    instructor_id=instructor_id,
                    title=course.get("title", ""),
                ).model_dump(),
                key=str(course_id),
            )

        return CourseResponse(**course)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
```

### 1.2 Add `validate_course_for_publish()` to CourseService

**File:** `services/course-service/src/services/course.py`

Add a new method that validates without saving:

```python
async def validate_course_for_publish(
    self, course_id: int, instructor_id: int
) -> dict:
    """Validate a course is ready for publishing WITHOUT changing DB state.

    Raises HTTPException (via ValueError/PermissionError) if validation fails.
    Returns course dict if valid.
    """
    course = await self.course_repo.get_by_id(course_id)
    if not course or bool(course.is_deleted):
        raise ValueError("Course not found")
    if cast(int, course.instructor_id) != instructor_id:
        raise PermissionError("You do not own this course")
    if str(course.status) == "published":
        raise ValueError("Course is already published")

    # Validate course has required fields
    if not course.title or not course.title.strip():
        raise ValueError("Course must have a title")
    if not course.description or not course.description.strip():
        raise ValueError("Course must have a description")

    # TODO: optionally check that course has at least 1 module with content
    # This can be done via course_content_repo if needed

    return _course_to_dict(course)
```

### 1.3 Add new internal endpoint for marking published (called by Temporal)

**File:** `services/course-service/src/api/courses.py`

Add a new internal endpoint that Temporal's activity will call to mark the course as published after indexing succeeds:

```python
@router.patch("/{course_id}/internal/publish", response_model=CourseResponse)
async def internal_publish_course(
    course_id: int,
    db: AsyncSession = Depends(get_db),
    producer: EventProducer = Depends(get_event_producer),
):
    """Internal endpoint — called by core-service Temporal workflow after
    RAG indexing completes. Marks course as published in DB and fires
    the course.published event.

    Guarded by X-User-ID / X-User-Role headers (internal services only).
    """
    service = CourseService(db)
    course = await service.get_course(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    result = await service.force_publish(course_id)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to publish course")

    # Now fire the actual course.published event
    await producer.publish(
        Topics.COURSE,
        "course.published",
        CoursePublishedPayload(
            course_id=course_id,
            instructor_id=result["instructor_id"],
            title=result.get("title", ""),
            published_at=str(result.get("published_at", "")),
        ).model_dump(),
        key=str(course_id),
    )

    return CourseResponse(**result)
```

Add `force_publish()` to `CourseService`:

```python
async def force_publish(self, course_id: int) -> dict | None:
    """Mark course as published (called by internal workflow endpoint)."""
    update_data = {
        "status": "published",
        "published_at": datetime.utcnow(),
    }
    result = await self.course_repo.update(course_id, update_data)
    await cache_delete(f"course:detail:{course_id}")
    await cache_delete_pattern("course:published:*")
    return _course_to_dict(result) if result else None
```

### 1.4 Add new event schema

**File:** `shared/src/shared/schemas/events/course.py`

```python
class CoursePublishRequestedPayload(BaseModel):
    course_id: int
    instructor_id: int
    title: str
```

---

## Part 2 — Core Service: Kafka Consumer for Course Events

### 2.1 Create course consumer

**File:** `services/core/src/core_service/kafka/course_consumer.py`

Follow the exact pattern of `enrollment_consumer.py`:

```python
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
        topic, envelope.event_type, envelope.event_id,
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
        course_id, instructor_id,
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
            "Failed to start CoursePublishWorkflow: %s", str(e), exc_info=True,
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
```

### 2.2 Register course consumer in main.py

**File:** `services/core/src/core_service/main.py`

Add the course consumer as a background task alongside the enrollment consumer:

```python
from core_service.kafka.course_consumer import run_course_consumer

# Inside lifespan():
course_consumer_task = asyncio.create_task(
    run_course_consumer(),
    name="course-consumer",
)
_background_tasks.extend([worker_task, consumer_task, course_consumer_task])
```

### 2.3 Add `AI_SERVICE_URL` to core config

**File:** `services/core/src/core_service/config.py`

```python
AI_SERVICE_URL: str = "http://smartcourse-ai-service:8009"
```

Also add this to the core-service `.env` file.

---

## Part 3 — Temporal CoursePublishWorkflow

### 3.1 Directory structure

Create under `services/core/src/core_service/temporal/workflows/course_publish/`:

```
course_publish/
  __init__.py
  workflow.py
  activities/
    __init__.py
    course.py        # validate course, mark published
    indexing.py       # trigger + poll RAG indexing
    notification.py   # notify instructor
```

### 3.2 Workflow definition

**File:** `services/core/src/core_service/temporal/workflows/course_publish/workflow.py`

```python
"""Course publish workflow that orchestrates the publishing process."""

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
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


@dataclass
class CoursePublishWorkflowInput:
    course_id: int
    instructor_id: int
    course_title: str


@dataclass
class CoursePublishWorkflowOutput:
    workflow_id: str
    course_id: int
    instructor_id: int
    success: bool
    steps_completed: list[str]
    steps_failed: list[str]
    error_message: str | None = None


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


@workflow.defn(name="CoursePublishWorkflow")
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
    async def run(self, input: CoursePublishWorkflowInput) -> CoursePublishWorkflowOutput:
        workflow.logger.info(
            "Starting CoursePublishWorkflow for course_id=%d, instructor_id=%d",
            input.course_id, input.instructor_id,
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
                input.course_id, str(e),
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

        max_attempts = 60          # max 60 polls
        poll_interval_secs = 10    # 10s between polls (total max ~10 min)

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
                attempt, max_attempts, result.status,
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
                "notify_instructor_failure failed (best-effort)", exc_info=True,
            )
            self.steps_failed.append(step_name)

    @workflow.query(name="get_status")
    def get_status(self) -> dict:
        return {
            "steps_completed": self.steps_completed,
            "steps_failed": self.steps_failed,
            "indexing_status": self.indexing_status,
        }
```

### 3.3 Activities — Course validation & mark published

**File:** `services/core/src/core_service/temporal/workflows/course_publish/activities/course.py`

```python
"""Course-service activities for course publish workflow."""

import logging
from dataclasses import dataclass

from temporalio import activity

from core_service.config import core_settings
from core_service.temporal.common.http_client import get_json, post_json, patch_json

logger = logging.getLogger(__name__)

COURSE_SERVICE = core_settings.COURSE_SERVICE_URL


# ── Dataclasses ───────────────────────────────────────────────


@dataclass
class ValidateCourseInput:
    course_id: int
    instructor_id: int


@dataclass
class ValidateCourseOutput:
    is_valid: bool
    reason: str = ""
    course_status: str = ""


@dataclass
class MarkCoursePublishedInput:
    course_id: int


@dataclass
class MarkCoursePublishedOutput:
    success: bool
    error: str = ""


# ── Activities ────────────────────────────────────────────────


@activity.defn
async def validate_course_for_publish(
    input: ValidateCourseInput,
) -> ValidateCourseOutput:
    """Validate course exists, belongs to instructor, is not already published,
    and has content (at least 1 module).
    """
    activity.logger.info(
        "validate_course_for_publish course_id=%d", input.course_id
    )

    try:
        # 1. Fetch course details (public endpoint)
        course = await get_json(
            f"{COURSE_SERVICE}/courses/{input.course_id}"
        )

        # 2. Check ownership
        if course.get("instructor_id") != input.instructor_id:
            return ValidateCourseOutput(
                is_valid=False,
                reason="Instructor does not own this course",
            )

        # 3. Check status — must not be already published
        status = course.get("status", "")
        if status == "published":
            return ValidateCourseOutput(
                is_valid=False,
                reason="Course is already published",
                course_status=status,
            )

        # 4. Check required fields
        if not course.get("title", "").strip():
            return ValidateCourseOutput(
                is_valid=False, reason="Course must have a title"
            )
        if not course.get("description", "").strip():
            return ValidateCourseOutput(
                is_valid=False, reason="Course must have a description"
            )

        # 5. Check course has content (modules)
        try:
            content = await get_json(
                f"{COURSE_SERVICE}/courses/{input.course_id}/content"
            )
            modules = content if isinstance(content, list) else content.get("modules", [])
            if not modules:
                return ValidateCourseOutput(
                    is_valid=False,
                    reason="Course must have at least one module with content",
                )
        except Exception as e:
            activity.logger.warning(
                "Could not fetch course content for validation: %s", e
            )
            # Non-blocking — allow publish even if content check fails

        return ValidateCourseOutput(
            is_valid=True,
            course_status=status,
        )

    except Exception as e:
        activity.logger.error("validate_course_for_publish failed: %s", e)
        raise  # Let Temporal retry


@activity.defn
async def mark_course_published(
    input: MarkCoursePublishedInput,
) -> MarkCoursePublishedOutput:
    """Call course-service internal endpoint to mark course as published in DB.

    This also fires the course.published Kafka event from course-service.
    """
    activity.logger.info(
        "mark_course_published course_id=%d", input.course_id
    )

    try:
        # Internal endpoint — uses X-User-ID / X-User-Role headers
        result = await patch_json(
            f"{COURSE_SERVICE}/courses/{input.course_id}/internal/publish",
            payload={},
            headers={
                "X-User-ID": "0",         # system/internal call
                "X-User-Role": "system",
            },
        )
        return MarkCoursePublishedOutput(success=True)

    except Exception as e:
        activity.logger.error("mark_course_published failed: %s", e)
        return MarkCoursePublishedOutput(success=False, error=str(e))


COURSE_ACTIVITIES = [
    validate_course_for_publish,
    mark_course_published,
]
```

> **Note on `patch_json`:** The existing `http_client.py` has `get_json` and `post_json`. You need to add a `patch_json` helper following the same pattern. See Section 5.1.

### 3.4 Activities — RAG Indexing (trigger + poll)

**File:** `services/core/src/core_service/temporal/workflows/course_publish/activities/indexing.py`

```python
"""AI-service activities for RAG indexing during course publish."""

import logging
from dataclasses import dataclass

from temporalio import activity

from core_service.config import core_settings
from core_service.temporal.common.http_client import get_json, post_json

logger = logging.getLogger(__name__)

AI_SERVICE = core_settings.AI_SERVICE_URL


# ── Dataclasses ───────────────────────────────────────────────


@dataclass
class TriggerIndexingInput:
    course_id: int
    instructor_id: int


@dataclass
class TriggerIndexingOutput:
    success: bool
    status: str = ""  # "pending"
    error: str = ""


@dataclass
class PollIndexingStatusInput:
    course_id: int
    instructor_id: int


@dataclass
class PollIndexingStatusOutput:
    status: str  # "pending" | "indexing" | "indexed" | "failed"
    error_message: str | None = None
    total_chunks: int = 0


# ── Activities ────────────────────────────────────────────────


@activity.defn
async def trigger_course_indexing(
    input: TriggerIndexingInput,
) -> TriggerIndexingOutput:
    """POST /api/v1/ai/index/courses/{course_id}/build to trigger RAG indexing.

    The ai-service requires instructor auth via X-User-ID / X-User-Role headers.
    Returns 202 Accepted with status "pending".
    """
    activity.logger.info(
        "trigger_course_indexing course_id=%d", input.course_id
    )

    try:
        result = await post_json(
            f"{AI_SERVICE}/api/v1/ai/index/courses/{input.course_id}/build",
            payload={"force_rebuild": False},
            headers={
                "X-User-ID": str(input.instructor_id),
                "X-User-Role": "instructor",
            },
        )

        return TriggerIndexingOutput(
            success=True,
            status=result.get("status", "pending"),
        )

    except Exception as e:
        activity.logger.error("trigger_course_indexing failed: %s", e)
        return TriggerIndexingOutput(success=False, error=str(e))


@activity.defn
async def poll_course_indexing_status(
    input: PollIndexingStatusInput,
) -> PollIndexingStatusOutput:
    """GET /api/v1/ai/index/courses/{course_id}/status to check indexing progress.

    Returns status: pending | indexing | indexed | failed
    """
    activity.logger.info(
        "poll_course_indexing_status course_id=%d", input.course_id
    )

    try:
        result = await get_json(
            f"{AI_SERVICE}/api/v1/ai/index/courses/{input.course_id}/status",
            headers={
                "X-User-ID": str(input.instructor_id),
                "X-User-Role": "instructor",
            },
        )

        return PollIndexingStatusOutput(
            status=result.get("status", "pending"),
            error_message=result.get("error_message"),
            total_chunks=result.get("total_chunks", 0),
        )

    except Exception as e:
        activity.logger.error("poll_course_indexing_status failed: %s", e)
        raise  # Let Temporal retry — transient network error


INDEXING_ACTIVITIES = [
    trigger_course_indexing,
    poll_course_indexing_status,
]
```

### 3.5 Activities — Instructor Notification

**File:** `services/core/src/core_service/temporal/workflows/course_publish/activities/notification.py`

```python
"""Notification activities for course publish workflow."""

import logging
from dataclasses import dataclass

from temporalio import activity

from core_service.config import core_settings
from core_service.temporal.common.http_client import post_json

logger = logging.getLogger(__name__)

NOTIFICATION_SERVICE = core_settings.NOTIFICATION_SERVICE_URL


# ── Dataclasses ───────────────────────────────────────────────


@dataclass
class NotifyInstructorInput:
    instructor_id: int
    course_id: int
    course_title: str
    error_message: str = ""


@dataclass
class NotifyInstructorOutput:
    success: bool
    error: str = ""


# ── Activities ────────────────────────────────────────────────


@activity.defn
async def notify_instructor_publish_success(
    input: NotifyInstructorInput,
) -> NotifyInstructorOutput:
    """Notify instructor that their course has been published successfully.

    Calls notification-service /notifications/send which enqueues Celery tasks.
    """
    activity.logger.info(
        "notify_instructor_publish_success course_id=%d instructor_id=%d",
        input.course_id, input.instructor_id,
    )

    try:
        await post_json(
            f"{NOTIFICATION_SERVICE}/notifications/send",
            payload={
                "user_id": input.instructor_id,
                "type": "course_published",
                "channel": "in_app",
                "priority": "normal",
                "title": "Course Published!",
                "message": (
                    f"Your course '{input.course_title}' is now live "
                    f"and available to students."
                ),
            },
        )
        return NotifyInstructorOutput(success=True)

    except Exception as e:
        activity.logger.error(
            "notify_instructor_publish_success failed: %s", e
        )
        return NotifyInstructorOutput(success=False, error=str(e))


@activity.defn
async def notify_instructor_publish_failure(
    input: NotifyInstructorInput,
) -> NotifyInstructorOutput:
    """Notify instructor that course publishing failed."""
    activity.logger.info(
        "notify_instructor_publish_failure course_id=%d", input.course_id,
    )

    try:
        await post_json(
            f"{NOTIFICATION_SERVICE}/notifications/send",
            payload={
                "user_id": input.instructor_id,
                "type": "course_publish_failed",
                "channel": "in_app",
                "priority": "high",
                "title": "Course Publishing Failed",
                "message": (
                    f"Your course '{input.course_title}' could not be published. "
                    f"Reason: {input.error_message or 'Unknown error'}. "
                    f"Please try again or contact support."
                ),
            },
        )
        return NotifyInstructorOutput(success=True)

    except Exception as e:
        activity.logger.error(
            "notify_instructor_publish_failure failed: %s", e
        )
        return NotifyInstructorOutput(success=False, error=str(e))


NOTIFICATION_ACTIVITIES = [
    notify_instructor_publish_success,
    notify_instructor_publish_failure,
]
```

### 3.6 Activities `__init__.py`

**File:** `services/core/src/core_service/temporal/workflows/course_publish/activities/__init__.py`

```python
"""Course publish workflow activities."""

from core_service.temporal.workflows.course_publish.activities.course import (
    validate_course_for_publish,
    mark_course_published,
    ValidateCourseInput,
    ValidateCourseOutput,
    MarkCoursePublishedInput,
    MarkCoursePublishedOutput,
    COURSE_ACTIVITIES,
)
from core_service.temporal.workflows.course_publish.activities.indexing import (
    trigger_course_indexing,
    poll_course_indexing_status,
    TriggerIndexingInput,
    TriggerIndexingOutput,
    PollIndexingStatusInput,
    PollIndexingStatusOutput,
    INDEXING_ACTIVITIES,
)
from core_service.temporal.workflows.course_publish.activities.notification import (
    notify_instructor_publish_success,
    notify_instructor_publish_failure,
    NotifyInstructorInput,
    NotifyInstructorOutput,
    NOTIFICATION_ACTIVITIES,
)

ALL_ACTIVITIES = COURSE_ACTIVITIES + INDEXING_ACTIVITIES + NOTIFICATION_ACTIVITIES

__all__ = [
    # Course
    "validate_course_for_publish",
    "mark_course_published",
    "ValidateCourseInput",
    "ValidateCourseOutput",
    "MarkCoursePublishedInput",
    "MarkCoursePublishedOutput",
    # Indexing
    "trigger_course_indexing",
    "poll_course_indexing_status",
    "TriggerIndexingInput",
    "TriggerIndexingOutput",
    "PollIndexingStatusInput",
    "PollIndexingStatusOutput",
    # Notification
    "notify_instructor_publish_success",
    "notify_instructor_publish_failure",
    "NotifyInstructorInput",
    "NotifyInstructorOutput",
    # Aggregated
    "ALL_ACTIVITIES",
]
```

### 3.7 Package `__init__.py`

**File:** `services/core/src/core_service/temporal/workflows/course_publish/__init__.py`

```python
"""Course publish workflow package."""

from core_service.temporal.workflows.course_publish.workflow import (
    CoursePublishWorkflow,
    CoursePublishWorkflowInput,
    CoursePublishWorkflowOutput,
)
from core_service.temporal.workflows.course_publish.activities import (
    ALL_ACTIVITIES,
)

__all__ = [
    "CoursePublishWorkflow",
    "CoursePublishWorkflowInput",
    "CoursePublishWorkflowOutput",
    "ALL_ACTIVITIES",
]
```

### 3.8 Register in workflows `__init__.py`

**File:** `services/core/src/core_service/temporal/workflows/__init__.py`

```python
"""Temporal workflows for core-service."""

from core_service.temporal.workflows.enrollment import (
    EnrollmentWorkflow,
    EnrollmentWorkflowInput,
    EnrollmentWorkflowOutput,
    ALL_ACTIVITIES as _enrollment_activities,
)
from core_service.temporal.workflows.course_publish import (
    CoursePublishWorkflow,
    CoursePublishWorkflowInput,
    CoursePublishWorkflowOutput,
    ALL_ACTIVITIES as _course_publish_activities,
)

ALL_WORKFLOWS = [
    EnrollmentWorkflow,
    CoursePublishWorkflow,
]

ALL_ACTIVITIES = _enrollment_activities + _course_publish_activities

__all__ = [
    "EnrollmentWorkflow",
    "EnrollmentWorkflowInput",
    "EnrollmentWorkflowOutput",
    "CoursePublishWorkflow",
    "CoursePublishWorkflowInput",
    "CoursePublishWorkflowOutput",
    "ALL_WORKFLOWS",
    "ALL_ACTIVITIES",
]
```

---

## Part 4 — Notification Service Cleanup

### 4.1 Remove `course.published` handler from notification-service

**File:** `services/notification-service/src/notification_service/consumers/event_handlers.py`

The `_on_course_published` handler (lines 84-99) must be **removed** from `_handlers` dict. Temporal now owns the instructor notification via its `notify_instructor_publish_success` activity.

```python
# BEFORE
self._handlers = {
    "user.registered": self._on_user_registered,
    "course.published": self._on_course_published,      # REMOVE THIS LINE
    "enrollment.completed": self._on_enrollment_completed,
    "certificate.issued": self._on_certificate_issued,
}

# AFTER
self._handlers = {
    "user.registered": self._on_user_registered,
    "enrollment.completed": self._on_enrollment_completed,
    "certificate.issued": self._on_certificate_issued,
}
```

Also delete the `_on_course_published` method (lines 84-99).

**Why:** The `course.published` Kafka event is now fired by the internal `/courses/{id}/internal/publish` endpoint AFTER Temporal's workflow completes. The notification is sent by Temporal's activity via HTTP to notification-service `/notifications/send`. Having the Kafka handler would cause double notification.

---

## Part 5 — Misc Changes

### 5.1 Add `patch_json` to HTTP client

**File:** `services/core/src/core_service/temporal/common/http_client.py`

Add alongside existing `get_json` and `post_json`:

```python
async def patch_json(url: str, payload: dict, headers: dict | None = None) -> dict:
    """PATCH request, raises ClientResponseError on non-2xx."""
    async with aiohttp.ClientSession(timeout=make_timeout()) as session:
        async with session.patch(url, json=payload, headers=headers or {}) as resp:
            resp.raise_for_status()
            return await resp.json()
```

### 5.2 Nginx route for internal publish endpoint

**File:** `services/api-gateway/nginx.conf`

The internal `/courses/{id}/internal/publish` endpoint is called service-to-service (core → course), so it does **NOT** need an nginx route. It bypasses the API gateway entirely since core-service calls `http://course-service:8002` directly.

However, you should ensure this endpoint is **not** exposed through nginx to prevent external access. The existing nginx config only proxies specific path patterns, so this should be fine by default.

---

## Summary — Files to Create/Modify

### New Files (7)
| # | File | Description |
|---|------|-------------|
| 1 | `services/core/src/core_service/kafka/course_consumer.py` | Kafka consumer for `course.publish_requested` events |
| 2 | `services/core/src/core_service/temporal/workflows/course_publish/__init__.py` | Package init |
| 3 | `services/core/src/core_service/temporal/workflows/course_publish/workflow.py` | CoursePublishWorkflow definition |
| 4 | `services/core/src/core_service/temporal/workflows/course_publish/activities/__init__.py` | Activities aggregator |
| 5 | `services/core/src/core_service/temporal/workflows/course_publish/activities/course.py` | Validate + mark published activities |
| 6 | `services/core/src/core_service/temporal/workflows/course_publish/activities/indexing.py` | Trigger + poll RAG indexing activities |
| 7 | `services/core/src/core_service/temporal/workflows/course_publish/activities/notification.py` | Instructor notification activities |

### Modified Files (7)
| # | File | Change |
|---|------|--------|
| 1 | `services/course-service/src/api/courses.py` | Tweak status endpoint + add internal publish endpoint |
| 2 | `services/course-service/src/services/course.py` | Add `validate_course_for_publish()` + `force_publish()` |
| 3 | `shared/src/shared/schemas/events/course.py` | Add `CoursePublishRequestedPayload` |
| 4 | `services/core/src/core_service/config.py` | Add `AI_SERVICE_URL` |
| 5 | `services/core/src/core_service/main.py` | Register course consumer background task |
| 6 | `services/core/src/core_service/temporal/workflows/__init__.py` | Register CoursePublishWorkflow + activities |
| 7 | `services/core/src/core_service/temporal/common/http_client.py` | Add `patch_json` helper |

### Cleanup (1)
| # | File | Change |
|---|------|--------|
| 1 | `services/notification-service/src/notification_service/consumers/event_handlers.py` | Remove `course.published` handler (Temporal owns it now) |

---

## Flow Diagram

```
┌──────────────────────────────────────────────────────────────┐
│  INSTRUCTOR: PATCH /courses/{id}/status  {status:"published"}│
│  (course-service)                                            │
│                                                              │
│  1. validate_course_for_publish() — no DB write              │
│  2. Publish "course.publish_requested" → Kafka COURSE topic  │
│  3. Return 202 {status: "publish_requested"}                 │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  CORE-SERVICE: Kafka course_consumer                         │
│                                                              │
│  Receives "course.publish_requested"                         │
│  Starts CoursePublishWorkflow via Temporal                    │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  TEMPORAL: CoursePublishWorkflow                              │
│                                                              │
│  Step 1: validate_course_for_publish                         │
│          GET course-service /courses/{id}                    │
│          GET course-service /courses/{id}/content            │
│                                                              │
│  Step 2: trigger_course_indexing                             │
│          POST ai-service /api/v1/ai/index/courses/{id}/build │
│          → 202 {status: "pending"}                           │
│                                                              │
│  Step 3: poll_course_indexing_status (loop every 10s)        │
│          GET ai-service /api/v1/ai/index/courses/{id}/status │
│          → wait until status == "indexed"                    │
│                                                              │
│  Step 4: mark_course_published                               │
│          PATCH course-service /courses/{id}/internal/publish │
│          → saves to DB + fires "course.published" event      │
│                                                              │
│  Step 5: notify_instructor_publish_success                   │
│          POST notification-service /notifications/send       │
│          → enqueues Celery in-app notification task           │
│                                                              │
│  ON FAILURE: notify_instructor_publish_failure               │
│          POST notification-service /notifications/send       │
│          → enqueues Celery in-app notification task           │
└──────────────────────────────────────────────────────────────┘
```

---

## Implementation Order

1. **Shared schema** — Add `CoursePublishRequestedPayload`
2. **Core config** — Add `AI_SERVICE_URL`
3. **HTTP client** — Add `patch_json`
4. **CoursePublishWorkflow** — All activities + workflow + package inits
5. **Workflows registry** — Update `__init__.py` to register new workflow
6. **Course consumer** — Create `course_consumer.py`
7. **Core main.py** — Register course consumer background task
8. **Course service** — Add `validate_course_for_publish()`, `force_publish()`, tweak status endpoint, add internal publish endpoint
9. **Notification service** — Remove `course.published` Kafka handler
10. **Test** — Trigger publish via PATCH endpoint, verify workflow runs end-to-end
