"""Lean mock activities for enrollment workflow testing."""

import asyncio
import logging
import random
import uuid
from dataclasses import dataclass

from temporalio import activity

logger = logging.getLogger(__name__)

# Each activity sleeps exactly this long (seconds) for workflow visibility/testing.
ACTIVITY_DELAY_SECONDS = 5.0


def _mock_id() -> str:
    """Generate a stable-looking mock ID."""
    return f"mock-{uuid.uuid4().hex[:8]}"


async def _simulate(service: str, operation: str) -> int:
    """Sleep and log to mimic a service request. Always sleeps ACTIVITY_DELAY_SECONDS."""
    delay = ACTIVITY_DELAY_SECONDS
    latency_ms = int(delay * 1000)
    logger.info("[MOCK] %s %s start latency=%dms", service, operation, latency_ms)
    await asyncio.sleep(delay)
    logger.info("[MOCK] %s %s done", service, operation)
    return latency_ms


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


@activity.defn(name="fetch_user_details")
async def fetch_user_details(input: FetchUserInput) -> FetchUserOutput:
    await _simulate("user-service", f"GET /users/{input.user_id}")
    return FetchUserOutput(
        success=True,
        user_id=input.user_id,
        email=f"student_{input.user_id}@example.com",
        name=f"Student {input.user_id}",
        role="student",
    )


@dataclass
class ValidateUserEnrollmentInput:
    user_id: int


@dataclass
class ValidateUserEnrollmentOutput:
    is_valid: bool
    user_id: int
    reason: str | None = None


@activity.defn(name="validate_user_for_enrollment")
async def validate_user_for_enrollment(
    input: ValidateUserEnrollmentInput,
) -> ValidateUserEnrollmentOutput:
    await _simulate(
        "user-service",
        f"GET /users/{input.user_id}/enrollment-eligibility",
    )
    return ValidateUserEnrollmentOutput(
        is_valid=True, user_id=input.user_id, reason=None
    )


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


@activity.defn(name="fetch_course_details")
async def fetch_course_details(input: FetchCourseInput) -> FetchCourseOutput:
    await _simulate("course-service", f"GET /courses/{input.course_id}")
    return FetchCourseOutput(
        success=True,
        course_id=input.course_id,
        title=f"Introduction to Course {input.course_id}",
        instructor_id=random.randint(100, 999),
        status="published",
    )


@dataclass
class InitializeProgressInput:
    student_id: int
    course_id: int
    enrollment_id: int | None = None


@dataclass
class InitializeProgressOutput:
    success: bool
    progress_id: int | None = None
    error: str | None = None


@activity.defn(name="initialize_course_progress")
async def initialize_course_progress(
    input: InitializeProgressInput,
) -> InitializeProgressOutput:
    await _simulate("course-service", "POST /progress/initialize")
    return InitializeProgressOutput(
        success=True, progress_id=random.randint(10000, 99999)
    )


@dataclass
class FetchCourseModulesInput:
    course_id: int


@dataclass
class FetchCourseModulesOutput:
    success: bool
    course_id: int
    modules: list[dict] | None = None
    module_count: int = 0
    error: str | None = None


@activity.defn(name="fetch_course_modules")
async def fetch_course_modules(
    input: FetchCourseModulesInput,
) -> FetchCourseModulesOutput:
    await _simulate("course-service", f"GET /courses/{input.course_id}/modules")
    modules = [
        {"module_id": 1, "title": "Module 1: Getting Started", "order": 1},
        {"module_id": 2, "title": "Module 2: Core Concepts", "order": 2},
        {"module_id": 3, "title": "Module 3: Advanced Topics", "order": 3},
    ]
    return FetchCourseModulesOutput(
        success=True,
        course_id=input.course_id,
        modules=modules,
        module_count=len(modules),
    )


@dataclass
class SendWelcomeEmailInput:
    student_id: int
    student_email: str
    student_name: str | None
    course_id: int
    course_title: str


@dataclass
class SendWelcomeEmailOutput:
    success: bool
    notification_id: str | None = None
    error: str | None = None


@activity.defn(name="send_enrollment_welcome_email")
async def send_enrollment_welcome_email(
    input: SendWelcomeEmailInput,
) -> SendWelcomeEmailOutput:
    await _simulate("notification-service", "POST /notifications/email")
    logger.info(
        "[MOCK] welcome email queued to=%s course=%s",
        input.student_email,
        input.course_title,
    )
    return SendWelcomeEmailOutput(success=True, notification_id=_mock_id())


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


@activity.defn(name="send_in_app_notification")
async def send_in_app_notification(
    input: SendInAppNotificationInput,
) -> SendInAppNotificationOutput:
    await _simulate("notification-service", "POST /notifications/in-app")
    logger.info("[MOCK] in-app notification user_id=%d", input.user_id)
    return SendInAppNotificationOutput(success=True, notification_id=_mock_id())


ALL_ACTIVITIES = [
    fetch_user_details,
    validate_user_for_enrollment,
    fetch_course_details,
    initialize_course_progress,
    fetch_course_modules,
    send_enrollment_welcome_email,
    send_in_app_notification,
]

__all__ = [
    "fetch_user_details",
    "validate_user_for_enrollment",
    "FetchUserInput",
    "FetchUserOutput",
    "ValidateUserEnrollmentInput",
    "ValidateUserEnrollmentOutput",
    "fetch_course_details",
    "initialize_course_progress",
    "fetch_course_modules",
    "FetchCourseInput",
    "FetchCourseOutput",
    "InitializeProgressInput",
    "InitializeProgressOutput",
    "FetchCourseModulesInput",
    "FetchCourseModulesOutput",
    "send_enrollment_welcome_email",
    "send_in_app_notification",
    "SendWelcomeEmailInput",
    "SendWelcomeEmailOutput",
    "SendInAppNotificationInput",
    "SendInAppNotificationOutput",
    "ALL_ACTIVITIES",
]
