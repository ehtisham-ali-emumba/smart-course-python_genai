# Temporal Real Workflows — Implementation Plan

**Date:** March 2, 2026
**Service:** `core-service`
**Scope:** Wire EnrollmentWorkflow + add CoursePublishWorkflow (with dummy AI RAG)

---

## Table of Contents

1. [Current State](#1-current-state)
2. [What Changes — File Map](#2-what-changes--file-map)
3. [Part 1: Enrollment Workflow — Real HTTP Activities](#3-part-1-enrollment-workflow--real-http-activities)
   - 3.1 Add `enrollment_id` to shared Kafka schema
   - 3.2 Update course-service enrollments API
   - 3.3 Update core-service config
   - 3.4 HTTP client utility
   - 3.5 Real user activities
   - 3.6 Real course activities
   - 3.7 Real notification activities
   - 3.8 Update activities `__init__.py`
4. [Part 2: Course Publish Workflow](#4-part-2-course-publish-workflow)
   - 4.1 Dummy AI service + AI activities
   - 4.2 `CoursePublishWorkflow`
   - 4.3 Kafka consumer for `course.published`
   - 4.4 Update `main.py` + `worker.py` + workflows `__init__`
5. [End-to-End Flow Diagrams](#5-end-to-end-flow-diagrams)
6. [Internal HTTP Auth Pattern](#6-internal-http-auth-pattern)
7. [Implementation Order & Checklist](#7-implementation-order--checklist)

---

## 1. Current State

### What exists in `core-service`

| File | Status | Notes |
|------|--------|-------|
| `temporal/workflows/enrollment_workflow.py` | ✅ Done | 6 steps, well structured, no changes needed |
| `temporal/activities/__init__.py` | 🔴 Mock | All activities sleep + return fake data |
| `temporal/client.py` | ✅ Done | Singleton client, no changes |
| `temporal/worker.py` | ✅ Done | Reads `ALL_WORKFLOWS`/`ALL_ACTIVITIES`, no changes |
| `kafka/enrollment_consumer.py` | ✅ Done | Listens for `enrollment.created`, starts workflow |
| `config.py` | 🔴 Incomplete | Service URLs commented out |
| `main.py` | 🟡 Partial | Only starts enrollment consumer + worker |

### Enrollment workflow — 6 steps (already defined, just mocked)

```
Step 1: validate_user_for_enrollment   → user-service
Step 2: fetch_user_details             → user-service
Step 3: fetch_course_details           → course-service
Step 4: initialize_course_progress     → course-service (verify enrollment active)
Step 5: send_enrollment_welcome_email  → notification-service
Step 6: send_in_app_notification       → notification-service
```

### Service URLs (Docker internal network)

```
user-service:          http://user-service:8001
course-service:        http://course-service:8002
notification-service:  http://notification-service:8005
```

### Internal auth pattern (no JWT needed)

All services trust `X-User-ID` and `X-User-Role` headers — set by the API Gateway in normal flow.
For internal service-to-service calls from core-service, just set these headers directly:

```python
headers = {"X-User-ID": str(user_id), "X-User-Role": "student"}
```

---

## 2. What Changes — File Map

### Files to MODIFY

| Service | File | Change |
|---------|------|--------|
| `shared` | `schemas/events/enrollment.py` | Add `enrollment_id` field to `EnrollmentCreatedPayload` |
| `course-service` | `api/enrollments.py` | Add `enrollment_id` to Kafka event; add `GET /course/{course_id}/active-students` |
| `core-service` | `config.py` | Uncomment service URLs |
| `core-service` | `main.py` | Add course publish consumer task |
| `core-service` | `temporal/activities/__init__.py` | Point to real activity modules |
| `core-service` | `temporal/workflows/__init__.py` | Register `CoursePublishWorkflow` |
| `core-service` | `temporal/workflows/enrollment_workflow.py` | Add `enrollment_id` to `EnrollmentWorkflowInput` |
| `core-service` | `kafka/enrollment_consumer.py` | Parse `enrollment_id` from payload |

### Files to CREATE

| Service | File | Purpose |
|---------|------|---------|
| `core-service` | `temporal/activities/http_client.py` | Shared aiohttp session factory |
| `core-service` | `temporal/activities/user_activities.py` | Real HTTP → user-service |
| `core-service` | `temporal/activities/course_activities.py` | Real HTTP → course-service |
| `core-service` | `temporal/activities/notification_activities.py` | Real HTTP → notification-service |
| `core-service` | `temporal/activities/ai_activities.py` | Dummy AI service + RAG activities |
| `core-service` | `temporal/workflows/course_publish_workflow.py` | CoursePublishWorkflow (7 steps) |
| `core-service` | `kafka/course_consumer.py` | Listen for `course.published`, start workflow |

---

## 3. Part 1: Enrollment Workflow — Real HTTP Activities

### 3.1 Add `enrollment_id` to shared Kafka schema

**File:** `shared/src/shared/schemas/events/enrollment.py`

Find the `EnrollmentCreatedPayload` class and add `enrollment_id`:

```python
class EnrollmentCreatedPayload(BaseModel):
    enrollment_id: int        # ← ADD THIS
    student_id: int
    course_id: int
    course_title: str
    email: str = ""
```

---

### 3.2 Update course-service enrollments API

**File:** `services/course-service/src/api/enrollments.py`

**Change 1 — include `enrollment_id` in the Kafka event** (in the `enroll` endpoint):

```python
await producer.publish(
    Topics.ENROLLMENT,
    "enrollment.created",
    EnrollmentCreatedPayload(
        enrollment_id=enrollment.id,       # ← ADD THIS
        student_id=enrollment.student_id,
        course_id=enrollment.course_id,
        course_title=course_title,
        email=student_email,
    ).model_dump(),
    key=str(enrollment.student_id),
)
```

**Change 2 — add internal endpoint** for course publish workflow to fetch enrolled student IDs.
Add this new route at the bottom of `enrollments.py`:

```python
@router.get("/course/{course_id}/active-students")
async def list_active_students_for_course(
    course_id: int,
    instructor_id: int = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """
    Internal endpoint: return active student_ids enrolled in a course.
    Used by core-service CoursePublishWorkflow to notify enrolled students.
    """
    service = EnrollmentService(db)
    # EnrollmentRepository.get_by_course() already exists
    enrollments = await service.enrollment_repo.get_by_course(course_id)
    active_ids = [
        e.student_id for e in enrollments if e.status == "active"
    ]
    return {"course_id": course_id, "student_ids": active_ids, "count": len(active_ids)}
```

> **Note:** `EnrollmentRepository.get_by_course()` already exists in the repo.
> `EnrollmentService` will need `enrollment_repo` exposed — check if already accessible or add a property.

---

### 3.3 Update core-service config

**File:** `services/core/src/core_service/config.py`

Uncomment (and add) the service URL settings:

```python
class CoreSettings(BaseSettings):
    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str
    SCHEMA_REGISTRY_URL: str

    # Legacy (keep)
    RABBITMQ_URL: str
    CELERY_RESULT_BACKEND: str

    # Logging
    LOG_LEVEL: str

    # Temporal
    TEMPORAL_HOST: str
    TEMPORAL_NAMESPACE: str
    TEMPORAL_TASK_QUEUE: str

    # Internal service URLs
    USER_SERVICE_URL: str = "http://user-service:8001"
    COURSE_SERVICE_URL: str = "http://course-service:8002"
    NOTIFICATION_SERVICE_URL: str = "http://notification-service:8005"
    HTTP_TIMEOUT_SECONDS: float = 30.0

    # Keep mock settings (used for local testing without Docker)
    MOCK_ACTIVITY_DELAY_MIN: float = 0.0
    MOCK_ACTIVITY_DELAY_MAX: float = 0.0
    MOCK_ACTIVITY_FAIL_RATE: float = 0.0

    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="", case_sensitive=True
    )
```

Also add to `services/core/.env`:

```env
USER_SERVICE_URL=http://user-service:8001
COURSE_SERVICE_URL=http://course-service:8002
NOTIFICATION_SERVICE_URL=http://notification-service:8005
HTTP_TIMEOUT_SECONDS=30.0
```

---

### 3.4 HTTP client utility

**File:** `services/core/src/core_service/temporal/activities/http_client.py` *(NEW)*

This shared utility creates a per-activity aiohttp session.
Activities are not async context managers themselves, so we create/close the session inside each activity call.

```python
"""Shared HTTP client utility for Temporal activities."""

import logging
from typing import Any

import aiohttp
from aiohttp import ClientResponseError, ClientTimeout

from core_service.config import core_settings

logger = logging.getLogger(__name__)


def make_timeout() -> ClientTimeout:
    return ClientTimeout(total=core_settings.HTTP_TIMEOUT_SECONDS)


async def get_json(
    url: str,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Perform a GET request and return parsed JSON.
    Raises aiohttp.ClientResponseError on non-2xx.
    """
    async with aiohttp.ClientSession(timeout=make_timeout()) as session:
        async with session.get(url, headers=headers or {}) as resp:
            resp.raise_for_status()
            return await resp.json()


async def post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Perform a POST request with JSON body and return parsed JSON.
    Raises aiohttp.ClientResponseError on non-2xx.
    """
    async with aiohttp.ClientSession(timeout=make_timeout()) as session:
        async with session.post(url, json=payload, headers=headers or {}) as resp:
            resp.raise_for_status()
            return await resp.json()
```

> **Dependency to add:** `aiohttp` in `services/core/pyproject.toml` under `[project] dependencies`.

---

### 3.5 Real user activities

**File:** `services/core/src/core_service/temporal/activities/user_activities.py` *(NEW)*

Replaces the mock `fetch_user_details` and `validate_user_for_enrollment` activities.

```python
"""Real HTTP activities that call user-service."""

import logging
from dataclasses import dataclass

from temporalio import activity

from core_service.config import core_settings
from core_service.temporal.activities.http_client import get_json

logger = logging.getLogger(__name__)

USER_SERVICE = core_settings.USER_SERVICE_URL


# ── Data classes (same shape as mock, so workflow code needs no changes) ──────

@dataclass
class FetchUserInput:
    user_id: int


@dataclass
class FetchUserOutput:
    success: bool
    user_id: int
    email: str | None = None
    name: str | None = None
    role: str | None = None
    error: str | None = None


@dataclass
class ValidateUserEnrollmentInput:
    user_id: int


@dataclass
class ValidateUserEnrollmentOutput:
    is_valid: bool
    user_id: int
    reason: str | None = None


# ── Activities ─────────────────────────────────────────────────────────────────

@activity.defn(name="fetch_user_details")
async def fetch_user_details(input: FetchUserInput) -> FetchUserOutput:
    """
    GET http://user-service:8001/api/v1/auth/me
    Pass X-User-ID header — user-service reads it directly (set by gateway in prod).
    """
    url = f"{USER_SERVICE}/api/v1/auth/me"
    headers = {"X-User-ID": str(input.user_id), "X-User-Role": "student"}

    try:
        data = await get_json(url, headers=headers)
        full_name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
        return FetchUserOutput(
            success=True,
            user_id=data["id"],
            email=data.get("email"),
            name=full_name or None,
            role=data.get("role", "student"),
        )
    except Exception as e:
        logger.warning("fetch_user_details failed for user_id=%d: %s", input.user_id, e)
        return FetchUserOutput(success=False, user_id=input.user_id, error=str(e))


@activity.defn(name="validate_user_for_enrollment")
async def validate_user_for_enrollment(
    input: ValidateUserEnrollmentInput,
) -> ValidateUserEnrollmentOutput:
    """
    Verify user exists and is an active student.
    Calls the same /me endpoint — if the call succeeds, user is valid.
    """
    url = f"{USER_SERVICE}/api/v1/auth/me"
    headers = {"X-User-ID": str(input.user_id), "X-User-Role": "student"}

    try:
        data = await get_json(url, headers=headers)

        if not data.get("is_active", True):
            return ValidateUserEnrollmentOutput(
                is_valid=False,
                user_id=input.user_id,
                reason="User account is inactive",
            )

        role = data.get("role", "student")
        if role == "instructor":
            return ValidateUserEnrollmentOutput(
                is_valid=False,
                user_id=input.user_id,
                reason="Instructors cannot enroll as students",
            )

        return ValidateUserEnrollmentOutput(is_valid=True, user_id=input.user_id)

    except Exception as e:
        logger.error("validate_user_for_enrollment failed for user_id=%d: %s", input.user_id, e)
        # Let Temporal retry via RetryPolicy
        raise


USER_ACTIVITIES = [fetch_user_details, validate_user_for_enrollment]

__all__ = [
    "fetch_user_details",
    "validate_user_for_enrollment",
    "FetchUserInput",
    "FetchUserOutput",
    "ValidateUserEnrollmentInput",
    "ValidateUserEnrollmentOutput",
    "USER_ACTIVITIES",
]
```

---

### 3.6 Real course activities

**File:** `services/core/src/core_service/temporal/activities/course_activities.py` *(NEW)*

```python
"""Real HTTP activities that call course-service."""

import logging
from dataclasses import dataclass, field

from temporalio import activity

from core_service.config import core_settings
from core_service.temporal.activities.http_client import get_json

logger = logging.getLogger(__name__)

COURSE_SERVICE = core_settings.COURSE_SERVICE_URL


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class FetchCourseInput:
    course_id: int


@dataclass
class FetchCourseOutput:
    success: bool
    course_id: int
    title: str | None = None
    instructor_id: int | None = None
    status: str | None = None
    error: str | None = None


@dataclass
class InitializeProgressInput:
    student_id: int
    course_id: int
    enrollment_id: int | None = None


@dataclass
class InitializeProgressOutput:
    success: bool
    enrollment_id: int | None = None
    enrollment_status: str | None = None
    error: str | None = None


@dataclass
class FetchCourseModulesInput:
    course_id: int
    instructor_id: int = 0  # used as X-User-ID for content endpoint


@dataclass
class FetchCourseModulesOutput:
    success: bool
    course_id: int
    modules: list[dict] | None = None
    module_count: int = 0
    error: str | None = None


# ── Activities ─────────────────────────────────────────────────────────────────

@activity.defn(name="fetch_course_details")
async def fetch_course_details(input: FetchCourseInput) -> FetchCourseOutput:
    """
    GET http://course-service:8002/api/v1/courses/{course_id}
    Public endpoint — no auth header required.
    """
    url = f"{COURSE_SERVICE}/api/v1/courses/{input.course_id}"

    try:
        data = await get_json(url)
        return FetchCourseOutput(
            success=True,
            course_id=data["id"],
            title=data.get("title"),
            instructor_id=data.get("instructor_id"),
            status=data.get("status"),
        )
    except Exception as e:
        logger.warning("fetch_course_details failed for course_id=%d: %s", input.course_id, e)
        return FetchCourseOutput(success=False, course_id=input.course_id, error=str(e))


@activity.defn(name="initialize_course_progress")
async def initialize_course_progress(
    input: InitializeProgressInput,
) -> InitializeProgressOutput:
    """
    Verify the enrollment is active in course-service.

    The enrollment record is already created BEFORE this workflow runs
    (the Kafka event fires after the DB insert). This activity simply
    confirms the enrollment exists and is active — progress rows are
    created on-demand when the student first interacts with content.

    If enrollment_id is provided, uses GET /enrollments/{enrollment_id}.
    Otherwise looks up via GET /enrollments/course/{course_id}/active-students.
    """
    headers = {"X-User-ID": str(input.student_id), "X-User-Role": "student"}

    try:
        if input.enrollment_id:
            url = f"{COURSE_SERVICE}/api/v1/enrollments/{input.enrollment_id}"
            data = await get_json(url, headers=headers)
            return InitializeProgressOutput(
                success=True,
                enrollment_id=data.get("id"),
                enrollment_status=data.get("status"),
            )
        else:
            # Fallback: just confirm course exists
            url = f"{COURSE_SERVICE}/api/v1/courses/{input.course_id}"
            await get_json(url)
            return InitializeProgressOutput(success=True)

    except Exception as e:
        logger.warning(
            "initialize_course_progress warning for student=%d course=%d: %s",
            input.student_id, input.course_id, e,
        )
        # Non-critical — return success so workflow continues
        return InitializeProgressOutput(success=False, error=str(e))


@activity.defn(name="fetch_course_modules")
async def fetch_course_modules(input: FetchCourseModulesInput) -> FetchCourseModulesOutput:
    """
    GET http://course-service:8002/api/v1/courses/{course_id}/content
    Requires X-User-ID header (uses instructor_id if provided, else student-style).
    """
    url = f"{COURSE_SERVICE}/api/v1/courses/{input.course_id}/content"
    uid = input.instructor_id if input.instructor_id else 1
    headers = {
        "X-User-ID": str(uid),
        "X-User-Role": "instructor" if input.instructor_id else "student",
    }

    try:
        data = await get_json(url, headers=headers)
        modules = data.get("modules", [])
        return FetchCourseModulesOutput(
            success=True,
            course_id=input.course_id,
            modules=modules,
            module_count=len(modules),
        )
    except Exception as e:
        logger.warning("fetch_course_modules failed for course_id=%d: %s", input.course_id, e)
        return FetchCourseModulesOutput(success=False, course_id=input.course_id, error=str(e))


COURSE_ACTIVITIES = [fetch_course_details, initialize_course_progress, fetch_course_modules]

__all__ = [
    "fetch_course_details",
    "initialize_course_progress",
    "fetch_course_modules",
    "FetchCourseInput",
    "FetchCourseOutput",
    "InitializeProgressInput",
    "InitializeProgressOutput",
    "FetchCourseModulesInput",
    "FetchCourseModulesOutput",
    "COURSE_ACTIVITIES",
]
```

---

### 3.7 Real notification activities

**File:** `services/core/src/core_service/temporal/activities/notification_activities.py` *(NEW)*

```python
"""Real HTTP activities that call notification-service."""

import logging
from dataclasses import dataclass

from temporalio import activity

from core_service.config import core_settings
from core_service.temporal.activities.http_client import post_json

logger = logging.getLogger(__name__)

NOTIFICATION_SERVICE = core_settings.NOTIFICATION_SERVICE_URL


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class SendWelcomeEmailInput:
    student_id: int
    student_email: str
    student_name: str | None
    course_id: int
    course_title: str
    enrollment_id: int = 0


@dataclass
class SendWelcomeEmailOutput:
    success: bool
    notification_id: str | None = None
    error: str | None = None


@dataclass
class SendInAppNotificationInput:
    user_id: int
    title: str
    message: str
    notification_type: str = "info"


@dataclass
class SendInAppNotificationOutput:
    success: bool
    notification_id: str | None = None
    error: str | None = None


@dataclass
class SendCoursePublishedNotificationInput:
    course_id: int
    course_title: str
    instructor_id: int
    affected_student_ids: list[int]
    event: str = "published"


@dataclass
class SendCoursePublishedNotificationOutput:
    success: bool
    students_notified: int = 0
    error: str | None = None


@dataclass
class SendInstructorNotificationInput:
    instructor_id: int
    course_id: int
    course_title: str
    rag_indexed: bool = True


@dataclass
class SendInstructorNotificationOutput:
    success: bool
    error: str | None = None


# ── Activities ─────────────────────────────────────────────────────────────────

@activity.defn(name="send_enrollment_welcome_email")
async def send_enrollment_welcome_email(
    input: SendWelcomeEmailInput,
) -> SendWelcomeEmailOutput:
    """
    POST http://notification-service:8005/api/v1/notifications/enrollment
    Uses EnrollmentNotificationRequest schema.
    """
    url = f"{NOTIFICATION_SERVICE}/api/v1/notifications/enrollment"
    headers = {"X-User-ID": str(input.student_id)}

    payload = {
        "user_id": input.student_id,
        "course_id": input.course_id,
        "course_title": input.course_title,
        "enrollment_id": input.enrollment_id,
        "instructor_name": "",  # Not available at this step
    }

    try:
        resp = await post_json(url, payload, headers=headers)
        return SendWelcomeEmailOutput(
            success=resp.get("success", True),
            notification_id=str(resp.get("timestamp", "")),
        )
    except Exception as e:
        logger.warning("send_enrollment_welcome_email failed: %s", e)
        # Non-critical — don't raise, let workflow continue
        return SendWelcomeEmailOutput(success=False, error=str(e))


@activity.defn(name="send_in_app_notification")
async def send_in_app_notification(
    input: SendInAppNotificationInput,
) -> SendInAppNotificationOutput:
    """
    POST http://notification-service:8005/api/v1/notifications/send
    Uses SendNotificationRequest schema.
    """
    url = f"{NOTIFICATION_SERVICE}/api/v1/notifications/send"
    headers = {"X-User-ID": str(input.user_id)}

    payload = {
        "user_id": input.user_id,
        "type": "enrollment_welcome",
        "channel": "in_app",
        "priority": "normal",
        "title": input.title,
        "message": input.message,
    }

    try:
        resp = await post_json(url, payload, headers=headers)
        return SendInAppNotificationOutput(
            success=resp.get("success", True),
            notification_id=str(resp.get("timestamp", "")),
        )
    except Exception as e:
        logger.warning("send_in_app_notification failed: %s", e)
        return SendInAppNotificationOutput(success=False, error=str(e))


@activity.defn(name="send_course_published_notification")
async def send_course_published_notification(
    input: SendCoursePublishedNotificationInput,
) -> SendCoursePublishedNotificationOutput:
    """
    POST http://notification-service:8005/api/v1/notifications/course
    Notifies all enrolled students that the course is now published.
    Uses CourseNotificationRequest schema with affected_user_ids.
    """
    url = f"{NOTIFICATION_SERVICE}/api/v1/notifications/course"
    headers = {"X-User-ID": str(input.instructor_id)}

    payload = {
        "course_id": input.course_id,
        "course_title": input.course_title,
        "instructor_id": input.instructor_id,
        "event": input.event,
        "affected_user_ids": input.affected_student_ids,
    }

    try:
        resp = await post_json(url, payload, headers=headers)
        return SendCoursePublishedNotificationOutput(
            success=resp.get("success", True),
            students_notified=len(input.affected_student_ids),
        )
    except Exception as e:
        logger.warning("send_course_published_notification failed: %s", e)
        return SendCoursePublishedNotificationOutput(success=False, error=str(e))


@activity.defn(name="send_instructor_course_published_notification")
async def send_instructor_course_published_notification(
    input: SendInstructorNotificationInput,
) -> SendInstructorNotificationOutput:
    """
    POST http://notification-service:8005/api/v1/notifications/course
    Notifies the instructor their course is live (and whether RAG was indexed).
    """
    url = f"{NOTIFICATION_SERVICE}/api/v1/notifications/course"
    headers = {"X-User-ID": str(input.instructor_id)}

    rag_note = " Course content has been indexed for AI Tutor." if input.rag_indexed else ""
    payload = {
        "course_id": input.course_id,
        "course_title": input.course_title,
        "instructor_id": input.instructor_id,
        "event": "published",
        "affected_user_ids": [input.instructor_id],
    }

    try:
        resp = await post_json(url, payload, headers=headers)
        logger.info(
            "Instructor %d notified: course %d published.%s",
            input.instructor_id, input.course_id, rag_note,
        )
        return SendInstructorNotificationOutput(success=resp.get("success", True))
    except Exception as e:
        logger.warning("send_instructor_course_published_notification failed: %s", e)
        return SendInstructorNotificationOutput(success=False, error=str(e))


NOTIFICATION_ACTIVITIES = [
    send_enrollment_welcome_email,
    send_in_app_notification,
    send_course_published_notification,
    send_instructor_course_published_notification,
]

__all__ = [
    "send_enrollment_welcome_email",
    "send_in_app_notification",
    "send_course_published_notification",
    "send_instructor_course_published_notification",
    "SendWelcomeEmailInput",
    "SendWelcomeEmailOutput",
    "SendInAppNotificationInput",
    "SendInAppNotificationOutput",
    "SendCoursePublishedNotificationInput",
    "SendCoursePublishedNotificationOutput",
    "SendInstructorNotificationInput",
    "SendInstructorNotificationOutput",
    "NOTIFICATION_ACTIVITIES",
]
```

---

### 3.8 Update activities `__init__.py`

**File:** `services/core/src/core_service/temporal/activities/__init__.py`

Replace the entire file. It now re-exports from the real modules and builds `ALL_ACTIVITIES`.

```python
"""
Temporal activities for core-service.

All imports are re-exported here so workflows and the worker
only import from this single package — the real vs mock switch
happens in one place.
"""

from core_service.temporal.activities.user_activities import (
    fetch_user_details,
    validate_user_for_enrollment,
    FetchUserInput,
    FetchUserOutput,
    ValidateUserEnrollmentInput,
    ValidateUserEnrollmentOutput,
    USER_ACTIVITIES,
)
from core_service.temporal.activities.course_activities import (
    fetch_course_details,
    initialize_course_progress,
    fetch_course_modules,
    FetchCourseInput,
    FetchCourseOutput,
    InitializeProgressInput,
    InitializeProgressOutput,
    FetchCourseModulesInput,
    FetchCourseModulesOutput,
    COURSE_ACTIVITIES,
)
from core_service.temporal.activities.notification_activities import (
    send_enrollment_welcome_email,
    send_in_app_notification,
    send_course_published_notification,
    send_instructor_course_published_notification,
    SendWelcomeEmailInput,
    SendWelcomeEmailOutput,
    SendInAppNotificationInput,
    SendInAppNotificationOutput,
    SendCoursePublishedNotificationInput,
    SendCoursePublishedNotificationOutput,
    SendInstructorNotificationInput,
    SendInstructorNotificationOutput,
    NOTIFICATION_ACTIVITIES,
)
from core_service.temporal.activities.ai_activities import (
    validate_course_for_publishing,
    fetch_course_content_for_rag,
    generate_rag_embeddings,
    store_rag_index,
    fetch_enrolled_students,
    ValidateCoursePublishInput,
    ValidateCoursePublishOutput,
    FetchCourseContentForRagInput,
    FetchCourseContentForRagOutput,
    GenerateRagEmbeddingsInput,
    GenerateRagEmbeddingsOutput,
    StoreRagIndexInput,
    StoreRagIndexOutput,
    FetchEnrolledStudentsInput,
    FetchEnrolledStudentsOutput,
    AI_ACTIVITIES,
)

# All activities registered with the Temporal worker
ALL_ACTIVITIES = USER_ACTIVITIES + COURSE_ACTIVITIES + NOTIFICATION_ACTIVITIES + AI_ACTIVITIES

__all__ = [
    # User
    "fetch_user_details",
    "validate_user_for_enrollment",
    "FetchUserInput",
    "FetchUserOutput",
    "ValidateUserEnrollmentInput",
    "ValidateUserEnrollmentOutput",
    # Course
    "fetch_course_details",
    "initialize_course_progress",
    "fetch_course_modules",
    "FetchCourseInput",
    "FetchCourseOutput",
    "InitializeProgressInput",
    "InitializeProgressOutput",
    "FetchCourseModulesInput",
    "FetchCourseModulesOutput",
    # Notification
    "send_enrollment_welcome_email",
    "send_in_app_notification",
    "send_course_published_notification",
    "send_instructor_course_published_notification",
    "SendWelcomeEmailInput",
    "SendWelcomeEmailOutput",
    "SendInAppNotificationInput",
    "SendInAppNotificationOutput",
    "SendCoursePublishedNotificationInput",
    "SendCoursePublishedNotificationOutput",
    "SendInstructorNotificationInput",
    "SendInstructorNotificationOutput",
    # AI
    "validate_course_for_publishing",
    "fetch_course_content_for_rag",
    "generate_rag_embeddings",
    "store_rag_index",
    "fetch_enrolled_students",
    "ValidateCoursePublishInput",
    "ValidateCoursePublishOutput",
    "FetchCourseContentForRagInput",
    "FetchCourseContentForRagOutput",
    "GenerateRagEmbeddingsInput",
    "GenerateRagEmbeddingsOutput",
    "StoreRagIndexInput",
    "StoreRagIndexOutput",
    "FetchEnrolledStudentsInput",
    "FetchEnrolledStudentsOutput",
    # Combined list
    "ALL_ACTIVITIES",
]
```

---

### Also update `EnrollmentWorkflowInput` to include `enrollment_id`

**File:** `services/core/src/core_service/temporal/workflows/enrollment_workflow.py`

Add `enrollment_id` field to the input dataclass:

```python
@dataclass
class EnrollmentWorkflowInput:
    student_id: int
    course_id: int
    course_title: str
    student_email: str
    enrollment_id: int | None = None      # ← ADD THIS
    enrollment_timestamp: str | None = None
```

And in `_initialize_progress`, pass it through:

```python
async def _initialize_progress(self, student_id: int, course_id: int, enrollment_id: int | None) -> None:
    result = await workflow.execute_activity(
        initialize_course_progress,
        InitializeProgressInput(
            student_id=student_id,
            course_id=course_id,
            enrollment_id=enrollment_id,    # ← pass it
        ),
        ...
    )
```

Update the call site in `run()`:

```python
await self._initialize_progress(input.student_id, input.course_id, input.enrollment_id)
```

---

### Also update `enrollment_consumer.py` to parse `enrollment_id`

**File:** `services/core/src/core_service/kafka/enrollment_consumer.py`

```python
payload = envelope.payload
student_id = payload.get("student_id")
course_id = payload.get("course_id")
enrollment_id = payload.get("enrollment_id")       # ← ADD
course_title = payload.get("course_title", f"Course {course_id}")
student_email = payload.get("email", "")

workflow_input = EnrollmentWorkflowInput(
    student_id=student_id,
    course_id=course_id,
    course_title=course_title,
    student_email=student_email,
    enrollment_id=enrollment_id,                   # ← ADD
)
```

---

## 4. Part 2: Course Publish Workflow

### Overview of steps

```
Trigger: course.published Kafka event
         ↓
Step 1: validate_course_for_publishing   → course-service (verify course + has content)
Step 2: fetch_course_content_for_rag     → course-service (get full MongoDB content)
Step 3: generate_rag_embeddings          → DummyAIService (chunk text → fake embeddings)
Step 4: store_rag_index                  → DummyAIService (store index in memory dict)
Step 5: fetch_enrolled_students          → course-service (get active student IDs)
Step 6: send_course_published_notif      → notification-service (notify students)
Step 7: send_instructor_notif            → notification-service (notify instructor)
```

Steps 3–4 are the AI RAG steps (dummy now, real in Week 3).
Steps 3 and 4 have compensation: if RAG fails, log it and continue — publishing already happened.

---

### 4.1 Dummy AI Service + AI activities

**File:** `services/core/src/core_service/temporal/activities/ai_activities.py` *(NEW)*

```python
"""
AI activities for the CoursePublishWorkflow.

DummyAIService is a placeholder for the real AI service (Week 3).
It demonstrates the interface that the real AI service must implement.

Real implementation will:
  - Use OpenAI text-embedding-3-small (or Ollama) for embeddings
  - Store vectors in Qdrant or pgvector
  - Expose a proper AI microservice on port 8009
"""

import logging
import random
from dataclasses import dataclass, field

from temporalio import activity

from core_service.config import core_settings
from core_service.temporal.activities.http_client import get_json

logger = logging.getLogger(__name__)

COURSE_SERVICE = core_settings.COURSE_SERVICE_URL


# ─────────────────────────────────────────────────────────────────────────────
# Dummy AI Service
# Replace this entire class in Week 3 with a real HTTP call to ai-service:8009
# ─────────────────────────────────────────────────────────────────────────────

class DummyAIService:
    """
    Mock AI service for RAG generation.

    In Week 3, this becomes real:
      - Embeddings: POST http://ai-service:8009/api/v1/rag/embed
      - Store:      POST http://ai-service:8009/api/v1/rag/index
      - Status:     GET  http://ai-service:8009/api/v1/rag/{course_id}/status

    The in-memory _rag_store is module-level so it persists for the worker process lifetime.
    It is NOT durable — only for demo purposes.
    """

    _rag_store: dict[int, dict] = {}

    def chunk_text(self, content: dict) -> list[str]:
        """
        Extract text chunks from course content structure (MongoDB format).
        Each module title + lesson title/description becomes a chunk.
        """
        chunks: list[str] = []
        course_id = content.get("course_id", "?")
        chunks.append(f"Course {course_id} overview")

        for module in content.get("modules", []):
            if not module.get("is_active", True):
                continue
            module_title = module.get("title", "")
            chunks.append(f"Module: {module_title}")

            for lesson in module.get("lessons", []):
                if not lesson.get("is_active", True):
                    continue
                lesson_title = lesson.get("title", "")
                chunks.append(f"Lesson in '{module_title}': {lesson_title}")

            for quiz in module.get("quizzes", []):
                if not quiz.get("is_active", True):
                    continue
                chunks.append(f"Quiz in '{module_title}': {quiz.get('title', '')}")

            for summary in module.get("summaries", []):
                if not summary.get("is_active", True):
                    continue
                chunks.append(f"Summary in '{module_title}': {summary.get('title', '')}")

        logger.info("[DummyAI] Chunked %d text segments for course %s", len(chunks), course_id)
        return chunks

    def generate_embeddings(self, chunks: list[str]) -> list[list[float]]:
        """
        Generate fake 384-dimensional embeddings.
        Real impl: call OpenAI text-embedding-3-small or sentence-transformers.
        Dimension 384 matches sentence-transformers/all-MiniLM-L6-v2.
        """
        embeddings = [[random.uniform(-1.0, 1.0) for _ in range(384)] for _ in chunks]
        logger.info("[DummyAI] Generated %d fake embeddings (dim=384)", len(embeddings))
        return embeddings

    def store_index(self, course_id: int, chunks: list[str], embeddings: list[list[float]]) -> dict:
        """
        Store the index in memory.
        Real impl: upsert into Qdrant collection or pgvector table.
        Returns index metadata dict.
        """
        index_id = f"course-{course_id}-rag-index"
        self._rag_store[course_id] = {
            "index_id": index_id,
            "chunk_count": len(chunks),
            "embedding_dim": 384,
            "status": "ready",
        }
        logger.info(
            "[DummyAI] Stored RAG index for course %d | chunks=%d index_id=%s",
            course_id, len(chunks), index_id,
        )
        return self._rag_store[course_id]

    def get_index_status(self, course_id: int) -> str:
        """Check if a course is already indexed."""
        entry = self._rag_store.get(course_id)
        return entry["status"] if entry else "not_indexed"


# Module-level singleton — shared across all activity executions in this worker
_ai_service = DummyAIService()


# ─────────────────────────────────────────────────────────────────────────────
# Data classes for Course Publish Workflow activities
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ValidateCoursePublishInput:
    course_id: int
    instructor_id: int


@dataclass
class ValidateCoursePublishOutput:
    is_valid: bool
    course_id: int
    title: str = ""
    has_content: bool = False
    module_count: int = 0
    reason: str | None = None


@dataclass
class FetchCourseContentForRagInput:
    course_id: int
    instructor_id: int


@dataclass
class FetchCourseContentForRagOutput:
    success: bool
    course_id: int
    content: dict | None = None
    module_count: int = 0
    error: str | None = None


@dataclass
class GenerateRagEmbeddingsInput:
    course_id: int
    content: dict


@dataclass
class GenerateRagEmbeddingsOutput:
    success: bool
    course_id: int
    chunks: list[str] = field(default_factory=list)
    embeddings: list[list[float]] = field(default_factory=list)
    chunks_processed: int = 0
    error: str | None = None


@dataclass
class StoreRagIndexInput:
    course_id: int
    chunks: list[str]
    embeddings: list[list[float]]


@dataclass
class StoreRagIndexOutput:
    success: bool
    index_id: str | None = None
    chunk_count: int = 0
    error: str | None = None


@dataclass
class FetchEnrolledStudentsInput:
    course_id: int
    instructor_id: int


@dataclass
class FetchEnrolledStudentsOutput:
    success: bool
    course_id: int
    student_ids: list[int] = field(default_factory=list)
    count: int = 0
    error: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Activities
# ─────────────────────────────────────────────────────────────────────────────

@activity.defn(name="validate_course_for_publishing")
async def validate_course_for_publishing(
    input: ValidateCoursePublishInput,
) -> ValidateCoursePublishOutput:
    """
    Verify the course exists, is published, and has at least one module of content.
    Calls:
      - GET http://course-service:8002/api/v1/courses/{course_id}
      - GET http://course-service:8002/api/v1/courses/{course_id}/content
    """
    try:
        # Step A: verify course record
        course_url = f"{COURSE_SERVICE}/api/v1/courses/{input.course_id}"
        course_data = await get_json(course_url)
        title = course_data.get("title", "")

        if course_data.get("status") != "published":
            return ValidateCoursePublishOutput(
                is_valid=False,
                course_id=input.course_id,
                title=title,
                reason=f"Course status is '{course_data.get('status')}', not 'published'",
            )

        # Step B: verify content exists
        content_url = f"{COURSE_SERVICE}/api/v1/courses/{input.course_id}/content"
        headers = {"X-User-ID": str(input.instructor_id), "X-User-Role": "instructor"}
        try:
            content_data = await get_json(content_url, headers=headers)
            modules = content_data.get("modules", [])
            active_modules = [m for m in modules if m.get("is_active", True)]
        except Exception:
            # Content may not exist yet — not a blocker for workflow
            active_modules = []

        return ValidateCoursePublishOutput(
            is_valid=True,
            course_id=input.course_id,
            title=title,
            has_content=len(active_modules) > 0,
            module_count=len(active_modules),
        )

    except Exception as e:
        logger.error("validate_course_for_publishing failed: %s", e)
        raise  # Let Temporal retry


@activity.defn(name="fetch_course_content_for_rag")
async def fetch_course_content_for_rag(
    input: FetchCourseContentForRagInput,
) -> FetchCourseContentForRagOutput:
    """
    Fetch full course content from course-service for RAG chunking.
    GET http://course-service:8002/api/v1/courses/{course_id}/content
    """
    url = f"{COURSE_SERVICE}/api/v1/courses/{input.course_id}/content"
    headers = {"X-User-ID": str(input.instructor_id), "X-User-Role": "instructor"}

    try:
        data = await get_json(url, headers=headers)
        modules = [m for m in data.get("modules", []) if m.get("is_active", True)]
        return FetchCourseContentForRagOutput(
            success=True,
            course_id=input.course_id,
            content=data,
            module_count=len(modules),
        )
    except Exception as e:
        logger.warning("fetch_course_content_for_rag failed for course %d: %s", input.course_id, e)
        # Return empty content — RAG step will be skipped gracefully
        return FetchCourseContentForRagOutput(success=False, course_id=input.course_id, error=str(e))


@activity.defn(name="generate_rag_embeddings")
async def generate_rag_embeddings(
    input: GenerateRagEmbeddingsInput,
) -> GenerateRagEmbeddingsOutput:
    """
    Chunk course content and generate embeddings using DummyAIService.

    WEEK 3 UPGRADE PATH:
      Replace DummyAIService call with HTTP POST to ai-service:8009/api/v1/rag/embed
      Request:  { course_id, chunks: [str] }
      Response: { embeddings: [[float]] }
    """
    if not input.content:
        return GenerateRagEmbeddingsOutput(
            success=False, course_id=input.course_id, error="No content to embed"
        )

    try:
        chunks = _ai_service.chunk_text(input.content)
        embeddings = _ai_service.generate_embeddings(chunks)
        return GenerateRagEmbeddingsOutput(
            success=True,
            course_id=input.course_id,
            chunks=chunks,
            embeddings=embeddings,
            chunks_processed=len(chunks),
        )
    except Exception as e:
        logger.error("generate_rag_embeddings failed for course %d: %s", input.course_id, e)
        return GenerateRagEmbeddingsOutput(success=False, course_id=input.course_id, error=str(e))


@activity.defn(name="store_rag_index")
async def store_rag_index(input: StoreRagIndexInput) -> StoreRagIndexOutput:
    """
    Store the embeddings/index using DummyAIService.

    WEEK 3 UPGRADE PATH:
      Replace with HTTP POST to ai-service:8009/api/v1/rag/index
      Request:  { course_id, chunks: [str], embeddings: [[float]] }
      Response: { index_id, chunk_count, status }
    """
    try:
        result = _ai_service.store_index(input.course_id, input.chunks, input.embeddings)
        return StoreRagIndexOutput(
            success=True,
            index_id=result["index_id"],
            chunk_count=result["chunk_count"],
        )
    except Exception as e:
        logger.error("store_rag_index failed for course %d: %s", input.course_id, e)
        return StoreRagIndexOutput(success=False, error=str(e))


@activity.defn(name="fetch_enrolled_students")
async def fetch_enrolled_students(
    input: FetchEnrolledStudentsInput,
) -> FetchEnrolledStudentsOutput:
    """
    GET http://course-service:8002/api/v1/enrollments/course/{course_id}/active-students
    Returns the list of active student IDs to notify.
    (This endpoint is added to course-service in Section 3.2)
    """
    url = f"{COURSE_SERVICE}/api/v1/enrollments/course/{input.course_id}/active-students"
    headers = {"X-User-ID": str(input.instructor_id), "X-User-Role": "instructor"}

    try:
        data = await get_json(url, headers=headers)
        student_ids = data.get("student_ids", [])
        return FetchEnrolledStudentsOutput(
            success=True,
            course_id=input.course_id,
            student_ids=student_ids,
            count=len(student_ids),
        )
    except Exception as e:
        logger.warning("fetch_enrolled_students failed for course %d: %s", input.course_id, e)
        return FetchEnrolledStudentsOutput(success=False, course_id=input.course_id, error=str(e))


AI_ACTIVITIES = [
    validate_course_for_publishing,
    fetch_course_content_for_rag,
    generate_rag_embeddings,
    store_rag_index,
    fetch_enrolled_students,
]

__all__ = [
    "validate_course_for_publishing",
    "fetch_course_content_for_rag",
    "generate_rag_embeddings",
    "store_rag_index",
    "fetch_enrolled_students",
    "DummyAIService",
    "ValidateCoursePublishInput",
    "ValidateCoursePublishOutput",
    "FetchCourseContentForRagInput",
    "FetchCourseContentForRagOutput",
    "GenerateRagEmbeddingsInput",
    "GenerateRagEmbeddingsOutput",
    "StoreRagIndexInput",
    "StoreRagIndexOutput",
    "FetchEnrolledStudentsInput",
    "FetchEnrolledStudentsOutput",
    "AI_ACTIVITIES",
]
```

---

### 4.2 `CoursePublishWorkflow`

**File:** `services/core/src/core_service/temporal/workflows/course_publish_workflow.py` *(NEW)*

```python
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
        ValidateCoursePublishInput,
        FetchCourseContentForRagInput,
        GenerateRagEmbeddingsInput,
        StoreRagIndexInput,
        FetchEnrolledStudentsInput,
        # Notification activities
        send_course_published_notification,
        send_instructor_course_published_notification,
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
    async def run(self, input: CoursePublishWorkflowInput) -> CoursePublishWorkflowOutput:
        workflow.logger.info(
            "CoursePublishWorkflow starting | course_id=%d instructor_id=%d",
            input.course_id, input.instructor_id,
        )
        workflow_id = workflow.info().workflow_id

        try:
            # ── CRITICAL STEPS ─────────────────────────────────────────────────
            # Step 1: Validate course
            await self._validate_course(input)

            # Step 2: Fetch content for RAG
            content = await self._fetch_content(input)

            # ── RAG STEPS (non-critical — RAG failure does not block notifications) ─
            # Step 3: Generate embeddings
            chunks, embeddings = await self._generate_embeddings(input, content)

            # Step 4: Store RAG index
            await self._store_index(input, chunks, embeddings)

            # ── NOTIFICATION STEPS (non-critical) ──────────────────────────────
            # Step 5: Fetch enrolled students
            student_ids = await self._fetch_students(input)

            # Step 6: Notify students
            await self._notify_students(input, student_ids)

            # Step 7: Notify instructor
            await self._notify_instructor(input)

            workflow.logger.info(
                "CoursePublishWorkflow completed | course_id=%d rag=%s students=%d",
                input.course_id, self.rag_indexed, self.students_notified,
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
            workflow.logger.error("CoursePublishWorkflow failed: %s", str(e))
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
        self.steps_completed.append(step)
        workflow.logger.info("Step %s: passed | title='%s' modules=%d", step, result.title, result.module_count)

    async def _fetch_content(self, input: CoursePublishWorkflowInput) -> dict:
        step = "fetch_course_content"
        result = await workflow.execute_activity(
            fetch_course_content_for_rag,
            FetchCourseContentForRagInput(
                course_id=input.course_id,
                instructor_id=input.instructor_id,
            ),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=DEFAULT_RETRY,
        )
        if result.success and result.content:
            self.steps_completed.append(step)
            return result.content
        # No content yet — RAG steps will be skipped
        self.steps_completed.append(f"{step}_no_content")
        return {}

    async def _generate_embeddings(
        self,
        input: CoursePublishWorkflowInput,
        content: dict,
    ) -> tuple[list[str], list[list[float]]]:
        step = "generate_rag_embeddings"
        if not content:
            self.steps_completed.append(f"{step}_skipped")
            return [], []
        try:
            result = await workflow.execute_activity(
                generate_rag_embeddings,
                GenerateRagEmbeddingsInput(
                    course_id=input.course_id,
                    content=content,
                ),
                start_to_close_timeout=timedelta(seconds=120),
                retry_policy=LENIENT_RETRY,
            )
            if result.success:
                self.steps_completed.append(step)
                return result.chunks, result.embeddings
            self.steps_failed.append(step)
            return [], []
        except Exception as e:
            workflow.logger.warning("RAG embedding step failed (non-critical): %s", e)
            self.steps_failed.append(step)
            return [], []

    async def _store_index(
        self,
        input: CoursePublishWorkflowInput,
        chunks: list[str],
        embeddings: list[list[float]],
    ) -> None:
        step = "store_rag_index"
        if not chunks:
            self.steps_completed.append(f"{step}_skipped")
            return
        try:
            result = await workflow.execute_activity(
                store_rag_index,
                StoreRagIndexInput(
                    course_id=input.course_id,
                    chunks=chunks,
                    embeddings=embeddings,
                ),
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=LENIENT_RETRY,
            )
            if result.success:
                self.rag_indexed = True
                self.steps_completed.append(step)
                workflow.logger.info("RAG index stored: %s (%d chunks)", result.index_id, result.chunk_count)
            else:
                self.steps_failed.append(step)
        except Exception as e:
            workflow.logger.warning("RAG store step failed (non-critical): %s", e)
            self.steps_failed.append(step)

    async def _fetch_students(self, input: CoursePublishWorkflowInput) -> list[int]:
        step = "fetch_enrolled_students"
        try:
            result = await workflow.execute_activity(
                fetch_enrolled_students,
                FetchEnrolledStudentsInput(
                    course_id=input.course_id,
                    instructor_id=input.instructor_id,
                ),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=LENIENT_RETRY,
            )
            if result.success:
                self.steps_completed.append(step)
                return result.student_ids
            self.steps_failed.append(step)
            return []
        except Exception as e:
            workflow.logger.warning("fetch_enrolled_students failed (non-critical): %s", e)
            self.steps_failed.append(step)
            return []

    async def _notify_students(
        self,
        input: CoursePublishWorkflowInput,
        student_ids: list[int],
    ) -> None:
        step = "notify_enrolled_students"
        if not student_ids:
            self.steps_completed.append(f"{step}_skipped_no_students")
            return
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
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=LENIENT_RETRY,
            )
            if result.success:
                self.students_notified = result.students_notified
                self.steps_completed.append(step)
            else:
                self.steps_failed.append(step)
        except Exception as e:
            workflow.logger.warning("notify_enrolled_students failed (non-critical): %s", e)
            self.steps_failed.append(step)

    async def _notify_instructor(self, input: CoursePublishWorkflowInput) -> None:
        step = "notify_instructor"
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
                self.steps_completed.append(step)
            else:
                self.steps_failed.append(step)
        except Exception as e:
            workflow.logger.warning("notify_instructor failed (non-critical): %s", e)
            self.steps_failed.append(step)

    @workflow.query(name="get_status")
    def get_status(self) -> dict:
        return {
            "steps_completed": self.steps_completed,
            "steps_failed": self.steps_failed,
            "rag_indexed": self.rag_indexed,
            "students_notified": self.students_notified,
        }
```

---

### 4.3 Kafka consumer for `course.published`

**File:** `services/core/src/core_service/kafka/course_consumer.py` *(NEW)*

```python
"""Kafka consumer that triggers CoursePublishWorkflow on course.published events."""

import asyncio
import logging
import sys

from shared.kafka.consumer import EventConsumer
from shared.kafka.topics import Topics
from shared.schemas.envelope import EventEnvelope

from core_service.config import core_settings
from core_service.temporal.client import get_temporal_client
from core_service.temporal.workflows import (
    CoursePublishWorkflow,
    CoursePublishWorkflowInput,
)

logger = logging.getLogger(__name__)
MAX_RETRY_DELAY = 30


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


async def handle_course_event(topic: str, envelope: EventEnvelope) -> None:
    """
    Handle course.published events and start CoursePublishWorkflow.
    Ignores all other course event types (course.created, course.archived, etc.)
    """
    if envelope.event_type != "course.published":
        logger.debug("Ignoring course event type: %s", envelope.event_type)
        return

    payload = envelope.payload
    course_id = payload.get("course_id")
    instructor_id = payload.get("instructor_id")
    course_title = payload.get("title", f"Course {course_id}")
    published_at = payload.get("published_at", "")

    if not course_id or not instructor_id:
        logger.error("Invalid course.published payload: %s", payload)
        return

    logger.info(
        "Starting CoursePublishWorkflow | course_id=%d instructor_id=%d",
        course_id, instructor_id,
    )

    try:
        client = await get_temporal_client()

        workflow_input = CoursePublishWorkflowInput(
            course_id=course_id,
            instructor_id=instructor_id,
            course_title=course_title,
            published_at=published_at,
        )

        # Deterministic workflow ID — prevents duplicate processing if event is replayed
        workflow_id = f"course-publish-{course_id}-{envelope.event_id}"

        handle = await client.start_workflow(
            CoursePublishWorkflow.run,
            workflow_input,
            id=workflow_id,
            task_queue=core_settings.TEMPORAL_TASK_QUEUE,
        )

        logger.info("CoursePublishWorkflow started: workflow_id=%s", handle.id)

    except Exception as e:
        logger.error("Failed to start CoursePublishWorkflow: %s", str(e), exc_info=True)


async def run_course_consumer() -> None:
    """
    Run the Kafka consumer that listens for course events
    and triggers CoursePublishWorkflow on course.published.
    """
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
            group_id="core-service-course-publish",
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

---

### 4.4 Update `main.py`, `worker.py`, and workflows `__init__`

**File:** `services/core/src/core_service/main.py` — add course consumer task:

```python
from core_service.kafka.course_consumer import run_course_consumer   # ← ADD

@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = asyncio.create_task(run_worker_with_retry(), name="temporal-worker")
    consumer_task = asyncio.create_task(run_enrollment_consumer(), name="enrollment-consumer")
    course_task = asyncio.create_task(run_course_consumer(), name="course-consumer")   # ← ADD
    _background_tasks.extend([worker_task, consumer_task, course_task])                # ← ADD course_task

    logger.info("Background tasks started: temporal-worker, enrollment-consumer, course-consumer")
    yield
    # ... rest unchanged
```

---

**File:** `services/core/src/core_service/temporal/workflows/__init__.py` — register new workflow:

```python
from core_service.temporal.workflows.enrollment_workflow import (
    EnrollmentWorkflow,
    EnrollmentWorkflowInput,
    EnrollmentWorkflowOutput,
)
from core_service.temporal.workflows.course_publish_workflow import (   # ← ADD
    CoursePublishWorkflow,
    CoursePublishWorkflowInput,
    CoursePublishWorkflowOutput,
)

ALL_WORKFLOWS = [
    EnrollmentWorkflow,
    CoursePublishWorkflow,    # ← ADD
]

__all__ = [
    "EnrollmentWorkflow",
    "EnrollmentWorkflowInput",
    "EnrollmentWorkflowOutput",
    "CoursePublishWorkflow",          # ← ADD
    "CoursePublishWorkflowInput",     # ← ADD
    "CoursePublishWorkflowOutput",    # ← ADD
    "ALL_WORKFLOWS",
]
```

> **`worker.py` needs no changes** — it reads `ALL_WORKFLOWS` and `ALL_ACTIVITIES` from `__init__` files.

---

## 5. End-to-End Flow Diagrams

### Enrollment Workflow

```
Student POST /enrollments
        │
        ▼
course-service
  ├── Creates Enrollment record in PostgreSQL (enrollment.id = 42)
  └── Publishes Kafka event
        │
        ▼ enrollment.events topic
        │  { event_type: "enrollment.created",
        │    payload: { enrollment_id: 42, student_id: 5,
        │               course_id: 7, course_title: "...", email: "..." } }
        ▼
core-service (Kafka Consumer)
  └── Parses event → starts EnrollmentWorkflow(enrollment_id=42, student_id=5, course_id=7)
        │
        ▼ Temporal Worker executes workflow steps:
        │
        ├─ Step 1: validate_user_for_enrollment
        │     → GET user-service:8001/api/v1/auth/me (X-User-ID: 5)
        │     → Verify user is active student
        │
        ├─ Step 2: fetch_user_details
        │     → GET user-service:8001/api/v1/auth/me (X-User-ID: 5)
        │     → Extract name, email, role
        │
        ├─ Step 3: fetch_course_details
        │     → GET course-service:8002/api/v1/courses/7
        │     → Extract title, instructor_id, status
        │
        ├─ Step 4: initialize_course_progress
        │     → GET course-service:8002/api/v1/enrollments/42 (X-User-ID: 5)
        │     → Verify enrollment is "active"
        │
        ├─ Step 5: send_enrollment_welcome_email
        │     → POST notification-service:8005/api/v1/notifications/enrollment
        │     → Triggers Celery email task (existing Celery worker)
        │
        └─ Step 6: send_in_app_notification
              → POST notification-service:8005/api/v1/notifications/send
              → Creates in-app notification record
```

### Course Publish Workflow

```
Instructor PATCH /courses/7/status { status: "published" }
        │
        ▼
course-service
  ├── Updates course status to "published" in PostgreSQL
  └── Publishes Kafka event
        │
        ▼ course.events topic
        │  { event_type: "course.published",
        │    payload: { course_id: 7, instructor_id: 3,
        │               title: "Python 101", published_at: "..." } }
        ▼
core-service (Kafka Consumer)
  └── Parses event → starts CoursePublishWorkflow(course_id=7, instructor_id=3)
        │
        ▼ Temporal Worker executes workflow steps:
        │
        ├─ Step 1: validate_course_for_publishing    [CRITICAL]
        │     → GET course-service:8002/api/v1/courses/7
        │     → GET course-service:8002/api/v1/courses/7/content
        │     → Verify published + has modules
        │
        ├─ Step 2: fetch_course_content_for_rag      [CRITICAL]
        │     → GET course-service:8002/api/v1/courses/7/content
        │     → Returns full MongoDB content structure
        │
        ├─ Step 3: generate_rag_embeddings           [NON-CRITICAL / AI]
        │     → DummyAIService.chunk_text(content)   → ["Module 1", "Lesson A", ...]
        │     → DummyAIService.generate_embeddings() → [[0.1, -0.3, ...], ...]
        │     (Week 3: → POST ai-service:8009/api/v1/rag/embed)
        │
        ├─ Step 4: store_rag_index                   [NON-CRITICAL / AI]
        │     → DummyAIService.store_index(course_id, chunks, embeddings)
        │     → Stored in-memory for demo (module-level dict)
        │     (Week 3: → POST ai-service:8009/api/v1/rag/index → Qdrant/pgvector)
        │
        ├─ Step 5: fetch_enrolled_students           [NON-CRITICAL]
        │     → GET course-service:8002/api/v1/enrollments/course/7/active-students
        │     → Returns [5, 12, 99, ...]
        │
        ├─ Step 6: send_course_published_notification [NON-CRITICAL]
        │     → POST notification-service:8005/api/v1/notifications/course
        │     → { course_id:7, affected_user_ids:[5,12,99], event:"published" }
        │
        └─ Step 7: send_instructor_notification      [NON-CRITICAL]
              → POST notification-service:8005/api/v1/notifications/course
              → { course_id:7, affected_user_ids:[3], event:"published" }
              → Includes RAG indexing status in message
```

---

## 6. Internal HTTP Auth Pattern

Because all services share the same simple header-based auth (set by the API Gateway in production), internal service-to-service calls from core-service work by passing the headers directly:

| Call target | Headers to pass |
|-------------|----------------|
| `user-service /api/v1/auth/me` | `X-User-ID: {student_id}` + `X-User-Role: student` |
| `course-service /api/v1/courses/{id}` | None (public endpoint) |
| `course-service /api/v1/courses/{id}/content` | `X-User-ID: {instructor_id}` + `X-User-Role: instructor` |
| `course-service /api/v1/enrollments/{id}` | `X-User-ID: {student_id}` + `X-User-Role: student` |
| `course-service /api/v1/enrollments/course/{id}/active-students` | `X-User-ID: {instructor_id}` + `X-User-Role: instructor` |
| `notification-service /api/v1/notifications/*` | `X-User-ID: {user_id}` (any) |

No JWT tokens are needed — this is safe because all services are on an internal Docker network not reachable from outside.

---

## 7. Implementation Order & Checklist

Work in this order to avoid broken imports:

### Phase 1 — Shared + course-service changes (no Temporal yet)

- [ ] `shared/schemas/events/enrollment.py` — add `enrollment_id` to `EnrollmentCreatedPayload`
- [ ] `course-service/api/enrollments.py` — add `enrollment_id` to Kafka publish call
- [ ] `course-service/api/enrollments.py` — add `GET /course/{course_id}/active-students` endpoint
- [ ] Restart course-service container, verify enrollment still works via Postman

### Phase 2 — core-service config + HTTP client

- [ ] `core-service/config.py` — uncomment service URLs, add `HTTP_TIMEOUT_SECONDS`
- [ ] `core-service/.env` — add service URL env vars
- [ ] `core-service/temporal/activities/http_client.py` — create the file
- [ ] Add `aiohttp` to `services/core/pyproject.toml` dependencies

### Phase 3 — Real enrollment workflow activities

- [ ] `core-service/temporal/activities/user_activities.py` — create
- [ ] `core-service/temporal/activities/course_activities.py` — create
- [ ] `core-service/temporal/activities/notification_activities.py` — create
- [ ] `core-service/temporal/workflows/enrollment_workflow.py` — add `enrollment_id` to input + pass to `_initialize_progress`
- [ ] `core-service/kafka/enrollment_consumer.py` — parse `enrollment_id` from payload

### Phase 4 — Course publish workflow + AI

- [ ] `core-service/temporal/activities/ai_activities.py` — create (DummyAIService + 5 activities)
- [ ] `core-service/temporal/activities/__init__.py` — replace with real imports + ALL_ACTIVITIES
- [ ] `core-service/temporal/workflows/course_publish_workflow.py` — create
- [ ] `core-service/temporal/workflows/__init__.py` — register `CoursePublishWorkflow`
- [ ] `core-service/kafka/course_consumer.py` — create
- [ ] `core-service/main.py` — add `run_course_consumer` background task

### Phase 5 — Test end-to-end

- [ ] Restart core-service container
- [ ] Open Temporal UI at `localhost:8233`
- [ ] Enroll a student via Postman → watch `EnrollmentWorkflow` in Temporal UI
  - Confirm each step calls real service (check logs of user-service, course-service, notification-service)
- [ ] Publish a course via Postman → watch `CoursePublishWorkflow` in Temporal UI
  - Confirm RAG steps complete with dummy data
  - Confirm students + instructor are notified
- [ ] Check core-service logs for `[DummyAI]` lines confirming RAG chunking ran

### Week 3 upgrade path (AI service)

When the real AI service is built:
1. Replace `DummyAIService` with HTTP calls to `http://ai-service:8009`
2. Only `ai_activities.py` changes — workflow and other activities are untouched
3. The `store_rag_index` activity stores to Qdrant/pgvector instead of in-memory dict

---

## Notes

- **Activity communication is through Temporal — NOT Kafka, NOT fire-and-forget** — Kafka is used exclusively to *trigger* a workflow (enrollment consumer, course consumer). Once the workflow is running, all activity-to-workflow communication happens through Temporal's own task queue mechanism. `await workflow.execute_activity(...)` blocks the workflow until the activity returns its result. No Kafka event is published by an activity, and no fire-and-forget (start-and-ignore) pattern is used — every activity result is awaited and inspected before the next step runs. This is the fundamental Temporal model: the workflow is the orchestrator; activities are just units of work that report back synchronously to it.

- **`worker.py` never needs changes** — it pulls `ALL_WORKFLOWS` and `ALL_ACTIVITIES` dynamically from the `__init__` files.
- **Enrollment workflow code is unchanged** — only the activities behind the interface change from mock to real.
- **Compensation for RAG failure** — the workflow intentionally does not compensate by un-publishing the course. Publishing has already happened. RAG failure is treated as "index not available yet" — it can be re-run manually if needed.
- **Deduplication** — both consumers use deterministic `workflow_id` (e.g., `enrollment-{student_id}-{course_id}-{event_id}`), so replayed Kafka messages don't re-run completed workflows.
- **aiohttp sessions** — a new `ClientSession` is created per activity call (not per worker). This is correct for Temporal activities because each activity is a standalone execution unit.
