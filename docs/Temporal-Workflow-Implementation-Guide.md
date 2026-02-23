# Temporal Workflow Implementation Guide for SmartCourse Core Service

**Version:** 1.0  
**Date:** February 23, 2026  
**Service:** `core-service`  
**Scope:** Enrollment Workflow with Activity-Based Microservice Communication

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Infrastructure Setup](#3-infrastructure-setup)
4. [Python Dependencies](#4-python-dependencies)
5. [File Structure](#5-file-structure)
6. [Implementation Details](#6-implementation-details)
   - [Configuration](#61-configuration)
   - [Temporal Client](#62-temporal-client)
   - [Activities (Mock)](#63-activities)
   - [Workflows](#64-workflows)
   - [Kafka Consumer for Workflow Trigger](#65-kafka-consumer-for-workflow-trigger)
   - [Worker Process](#66-worker-process)
   - [Application Integration](#67-application-integration)
7. [Error Handling & Retry Policies](#7-error-handling--retry-policies)
8. [Testing](#8-testing)
9. [Complete Code Files](#9-complete-code-files)
10. [Switching from Mock to Real HTTP Activities](#10-switching-from-mock-to-real-http-activities)

---

## 1. Overview

### What is Temporal?

Temporal is a workflow orchestration platform that enables writing durable, reliable distributed applications. Unlike Kafka events (fire-and-forget), Temporal provides:

- **Durability**: Workflow state is persisted; workflows resume exactly where they left off after failures
- **Two-way communication**: Activities are request/response operations with proper error handling
- **Automatic retries**: Built-in retry policies with exponential backoff
- **Visibility**: Query workflow state at any time
- **Timeouts**: Activity, workflow, and schedule-to-start timeouts

### Why Temporal for Enrollment Workflow?

The current architecture uses Kafka for event publishing (fire-and-forget). This is great for decoupling and eventual consistency, but for complex multi-step business processes like student enrollment, we need:

1. **Guaranteed completion**: Each step must succeed or be properly handled
2. **State tracking**: Know exactly where a workflow is at any point
3. **Proper error handling**: If step 3 fails, know that steps 1-2 succeeded
4. **Two-way communication**: Activities call microservices via HTTP and wait for responses

### Flow Overview

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                           ENROLLMENT WORKFLOW FLOW                                    │
└──────────────────────────────────────────────────────────────────────────────────────┘

  ┌─────────────────┐         ┌─────────────────┐         ┌─────────────────────┐
  │  Course Service │  ──────▶│   Kafka        │  ──────▶│   Core Service       │
  │  (Enrollment)   │  Event  │   enrollment   │  Consume│   Kafka Consumer     │
  │                 │         │   .events      │         │                      │
  └─────────────────┘         └─────────────────┘         └──────────┬──────────┘
                                                                     │
                                                     Start Workflow  │
                                                                     ▼
                                                          ┌─────────────────────┐
                                                          │  Temporal Server    │
                                                          │  (Workflow Engine)  │
                                                          └──────────┬──────────┘
                                                                     │
                              ┌──────────────────────────────────────┼──────────────────────────────────────┐
                              │                                      │                                      │
                              ▼                                      ▼                                      ▼
                    ┌──────────────────┐               ┌──────────────────┐               ┌──────────────────┐
                    │   Activity 1     │               │   Activity 2     │               │   Activity 3     │
                    │   MOCK: delay +  │               │   MOCK: delay +  │               │   MOCK: delay +  │
                    │   logging        │               │   logging        │               │   logging        │
                    │                  │               │                  │               │                  │
                    │   ◄─── await ──▶ │               │   ◄─── await ──▶ │               │   ◄─── await ──▶ │
                    └──────────────────┘               └──────────────────┘               └──────────────────┘

                    (In production: Replace MOCK with actual HTTP calls to microservices)
```

---

## 2. Architecture

### Key Design Principles

1. **Kafka for Trigger Only**: Kafka event `enrollment.created` triggers the workflow start
2. **Activities for Communication**: Each activity simulates (or makes) an API call to a microservice
3. **Await Pattern**: Activities use async/await for proper request/response flow
4. **Core Service as Orchestrator**: The core-service hosts the Temporal worker and workflows
5. **Idempotency**: Activities should be idempotent (safe to retry)
6. **Mock First**: Start with mock activities, switch to real HTTP later

### Component Roles

| Component                                      | Role                                                            |
| ---------------------------------------------- | --------------------------------------------------------------- |
| **Course Service**                             | Publishes `enrollment.created` event to Kafka                   |
| **Core Service Kafka Consumer**                | Subscribes to `enrollment.events`, starts Temporal workflow     |
| **Core Service Temporal Worker**               | Executes workflow and activities (mock implementations for now) |
| **Temporal Server**                            | Persists workflow state, schedules activities                   |
| **Microservices (User, Course, Notification)** | REST APIs (not called in mock mode; called in production mode)  |

---

## 3. Infrastructure Setup

### 3.1 Docker Compose Additions

Add the following services to `docker-compose.yml`:

```yaml
# ═══════════════════════════════════════════════════════════════
#  TEMPORAL — Workflow Orchestration
# ═══════════════════════════════════════════════════════════════

temporal:
  image: temporalio/auto-setup:1.24.2
  container_name: smartcourse-temporal
  environment:
    - DB=postgresql
    - DB_PORT=5432
    - POSTGRES_USER=${POSTGRES_USER:-smartcourse}
    - POSTGRES_PWD=${POSTGRES_PASSWORD:-smartcourse_secret}
    - POSTGRES_SEEDS=postgres
    - DYNAMIC_CONFIG_FILE_PATH=config/dynamicconfig/development-sql.yaml
  ports:
    - "7233:7233"
  depends_on:
    postgres:
      condition: service_healthy
  volumes:
    - ./temporal-config:/etc/temporal/config/dynamicconfig
  healthcheck:
    test: ["CMD", "tctl", "--address", "temporal:7233", "cluster", "health"]
    interval: 15s
    timeout: 10s
    retries: 10
    start_period: 60s
  networks:
    - smartcourse-network

temporal-ui:
  image: temporalio/ui:2.26.2
  container_name: smartcourse-temporal-ui
  environment:
    - TEMPORAL_ADDRESS=temporal:7233
    - TEMPORAL_CORS_ORIGINS=http://localhost:3000
  ports:
    - "8080:8080"
  depends_on:
    temporal:
      condition: service_healthy
  networks:
    - smartcourse-network

temporal-admin-tools:
  image: temporalio/admin-tools:1.24.2
  container_name: smartcourse-temporal-admin
  environment:
    - TEMPORAL_ADDRESS=temporal:7233
  depends_on:
    temporal:
      condition: service_healthy
  networks:
    - smartcourse-network
  stdin_open: true
  tty: true
```

### 3.2 Temporal Dynamic Config

Create file `temporal-config/development-sql.yaml`:

```yaml
# Temporal Dynamic Configuration
system.forceSearchAttributesCacheRefreshOnRead:
  - value: true

limit.maxIDLength:
  - value: 1000

history.maximumSignalCountPerExecution:
  - value: 10000
```

### 3.3 Update Core Service in Docker Compose

Update the `core-service` definition:

```yaml
core-service:
  build:
    context: .
    dockerfile: services/core/Dockerfile
  container_name: smartcourse-core-service
  environment:
    - KAFKA_BOOTSTRAP_SERVERS=${KAFKA_BOOTSTRAP_SERVERS:-kafka:29092}
    - SCHEMA_REGISTRY_URL=${SCHEMA_REGISTRY_URL:-http://schema-registry:8081}
    - RABBITMQ_URL=amqp://${RABBITMQ_USER:-smartcourse}:${RABBITMQ_PASSWORD:-smartcourse_secret}@rabbitmq:5672//
    - CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD:-smartcourse_secret}@redis:6379/2
    - LOG_LEVEL=INFO
    # Temporal settings
    - TEMPORAL_HOST=${TEMPORAL_HOST:-temporal:7233}
    - TEMPORAL_NAMESPACE=${TEMPORAL_NAMESPACE:-default}
    - TEMPORAL_TASK_QUEUE=${TEMPORAL_TASK_QUEUE:-smartcourse-enrollment}
    # Mock activity settings (adjust for testing)
    - MOCK_ACTIVITY_DELAY_MIN=0.5
    - MOCK_ACTIVITY_DELAY_MAX=2.0
    - MOCK_ACTIVITY_FAIL_RATE=0.0
    # NOTE: Service URLs not needed in mock mode
    # Uncomment when switching to real HTTP activity calls:
    # - USER_SERVICE_URL=http://user-service:8001
    # - COURSE_SERVICE_URL=http://course-service:8002
    # - NOTIFICATION_SERVICE_URL=http://notification-service:8005
  depends_on:
    kafka:
      condition: service_healthy
    schema-registry:
      condition: service_healthy
    rabbitmq:
      condition: service_healthy
    redis:
      condition: service_healthy
    temporal:
      condition: service_healthy
  healthcheck:
    test:
      [
        "CMD",
        "python",
        "-c",
        "import urllib.request; urllib.request.urlopen('http://localhost:8006/health')",
      ]
    interval: 10s
    timeout: 5s
    retries: 3
  networks:
    - smartcourse-network
```

---

## 4. Python Dependencies

### 4.1 Update `services/core/pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "smartcourse-core"
version = "0.1.0"
description = "SmartCourse Core Service — workflow orchestration boundary"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "structlog>=24.1.0",
    # Temporal SDK
    "temporalio>=1.5.0",
    # Kafka consumer for workflow triggers
    "aiokafka>=0.10.0",
    # NOTE: httpx is NOT needed for mock implementation
    # Add "httpx>=0.27.0" later when switching to real HTTP calls
]

[tool.setuptools.packages.find]
where = ["src"]
include = ["core_service*"]
```

---

## 5. File Structure

The core service should have this structure after implementation:

```
services/core/
├── Dockerfile
├── pyproject.toml
└── src/
    └── core_service/
        ├── __init__.py
        ├── config.py                    # Settings with service URLs
        ├── main.py                      # FastAPI app with lifespan
        ├── api/
        │   ├── __init__.py
        │   └── router.py                # Health and workflow status endpoints
        ├── kafka/
        │   ├── __init__.py
        │   └── enrollment_consumer.py   # Kafka consumer that starts workflows
        ├── temporal/
        │   ├── __init__.py
        │   ├── client.py                # Temporal client singleton
        │   ├── worker.py                # Temporal worker runner
        │   ├── activities/
        │   │   ├── __init__.py
        │   │   ├── base.py              # Base HTTP activity client
        │   │   ├── user_activities.py   # Activities calling user-service
        │   │   ├── course_activities.py # Activities calling course-service
        │   │   └── notification_activities.py  # Activities calling notification-service
        │   └── workflows/
        │       ├── __init__.py
        │       └── enrollment_workflow.py  # The enrollment workflow
        └── schemas/
            ├── __init__.py
            └── workflow_inputs.py       # Pydantic models for workflow inputs
```

---

## 6. Implementation Details

### 6.1 Configuration

**File:** `services/core/src/core_service/config.py`

```python
"""Core service configuration."""

from pydantic_settings import BaseSettings


class CoreSettings(BaseSettings):
    """Core service settings."""

    # Kafka settings
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:29092"
    SCHEMA_REGISTRY_URL: str = "http://schema-registry:8081"

    # Legacy settings (keep for compatibility)
    RABBITMQ_URL: str = "amqp://smartcourse:smartcourse_secret@rabbitmq:5672//"
    CELERY_RESULT_BACKEND: str = "redis://:smartcourse_secret@redis:6379/2"

    # Logging
    LOG_LEVEL: str = "INFO"

    # Temporal settings
    TEMPORAL_HOST: str = "temporal:7233"
    TEMPORAL_NAMESPACE: str = "default"
    TEMPORAL_TASK_QUEUE: str = "smartcourse-enrollment"

    # Mock activity settings (for testing/development)
    MOCK_ACTIVITY_DELAY_MIN: float = 0.5  # Minimum simulated delay in seconds
    MOCK_ACTIVITY_DELAY_MAX: float = 2.0  # Maximum simulated delay in seconds
    MOCK_ACTIVITY_FAIL_RATE: float = 0.0  # Probability of simulated failure (0.0-1.0)

    # NOTE: Service URLs not needed in mock mode
    # Uncomment when switching to real HTTP activity calls:
    # USER_SERVICE_URL: str = "http://user-service:8001"
    # COURSE_SERVICE_URL: str = "http://course-service:8002"
    # NOTIFICATION_SERVICE_URL: str = "http://notification-service:8005"
    # HTTP_TIMEOUT_SECONDS: float = 30.0

    model_config = {"env_prefix": "", "case_sensitive": True}


core_settings = CoreSettings()
```

---

### 6.2 Temporal Client

**File:** `services/core/src/core_service/temporal/client.py`

```python
"""Temporal client singleton for starting workflows."""

import logging
from temporalio.client import Client

from core_service.config import core_settings

logger = logging.getLogger(__name__)

_temporal_client: Client | None = None


async def get_temporal_client() -> Client:
    """Get or create the Temporal client singleton."""
    global _temporal_client
    if _temporal_client is None:
        logger.info(
            "Connecting to Temporal at %s namespace=%s",
            core_settings.TEMPORAL_HOST,
            core_settings.TEMPORAL_NAMESPACE,
        )
        _temporal_client = await Client.connect(
            core_settings.TEMPORAL_HOST,
            namespace=core_settings.TEMPORAL_NAMESPACE,
        )
        logger.info("Temporal client connected successfully")
    return _temporal_client


async def close_temporal_client() -> None:
    """Close the Temporal client connection."""
    global _temporal_client
    if _temporal_client is not None:
        # Note: temporalio client doesn't have explicit close,
        # but we clear the reference for clean shutdown
        _temporal_client = None
        logger.info("Temporal client reference cleared")
```

---

### 6.3 Activities

Activities are the building blocks that perform actual work. **For initial setup and testing, we use MOCK implementations with simulated delays and logging.** Later, these can be replaced with actual HTTP calls to microservices.

> **Note:** All activities below are MOCK implementations. They simulate work with `asyncio.sleep()` delays and return mock data. This allows you to test the Temporal workflow infrastructure without requiring all microservices to be running.

#### 6.3.1 Mock Activity Utilities

**File:** `services/core/src/core_service/temporal/activities/base.py`

```python
"""Base utilities for mock activities."""

import asyncio
import logging
import random
import uuid
from dataclasses import dataclass
from typing import Any

from core_service.config import core_settings

logger = logging.getLogger(__name__)


@dataclass
class MockActivityResult:
    """Standard result from a mock activity."""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    simulated_latency_ms: int = 0


async def simulate_service_call(
    service_name: str,
    operation: str,
    input_data: dict[str, Any] | None = None,
    fail_probability: float | None = None,
) -> MockActivityResult:
    """
    Simulate an HTTP call to a microservice with realistic delays.

    Args:
        service_name: Name of the target service (for logging)
        operation: Description of the operation being performed
        input_data: Input data for logging purposes
        fail_probability: Probability of simulated failure (0.0 to 1.0)
                         If None, uses MOCK_ACTIVITY_FAIL_RATE from config

    Returns:
        MockActivityResult with simulated response
    """
    # Use config values for delay range
    delay_min = core_settings.MOCK_ACTIVITY_DELAY_MIN
    delay_max = core_settings.MOCK_ACTIVITY_DELAY_MAX

    # Use provided fail_probability or default from config
    if fail_probability is None:
        fail_probability = core_settings.MOCK_ACTIVITY_FAIL_RATE

    # Generate random delay to simulate network latency
    delay = random.uniform(delay_min, delay_max)
    latency_ms = int(delay * 1000)

    logger.info(
        "[MOCK] %s -> %s: Starting '%s' (simulated latency: %dms)",
        "core-service",
        service_name,
        operation,
        latency_ms,
    )

    if input_data:
        logger.debug(
            "[MOCK] %s -> %s: Input data: %s",
            "core-service",
            service_name,
            input_data,
        )

    # Simulate network delay
    await asyncio.sleep(delay)

    # Simulate random failures if configured
    if fail_probability > 0 and random.random() < fail_probability:
        logger.warning(
            "[MOCK] %s -> %s: '%s' FAILED (simulated failure)",
            "core-service",
            service_name,
            operation,
        )
        return MockActivityResult(
            success=False,
            error=f"Simulated failure for {operation}",
            simulated_latency_ms=latency_ms,
        )

    logger.info(
        "[MOCK] %s -> %s: '%s' completed successfully in %dms",
        "core-service",
        service_name,
        operation,
        latency_ms,
    )

    return MockActivityResult(
        success=True,
        simulated_latency_ms=latency_ms,
    )


def generate_mock_id() -> str:
    """Generate a mock UUID for simulated resources."""
    return f"mock-{uuid.uuid4().hex[:8]}"
```

#### 6.3.2 User Activities (Mock)

**File:** `services/core/src/core_service/temporal/activities/user_activities.py`

```python
"""Mock activities simulating user-service interactions."""

import logging
from dataclasses import dataclass
from temporalio import activity

from core_service.temporal.activities.base import (
    simulate_service_call,
    generate_mock_id,
)

logger = logging.getLogger(__name__)


@dataclass
class FetchUserInput:
    """Input for fetch_user_details activity."""

    user_id: int


@dataclass
class FetchUserOutput:
    """Output from fetch_user_details activity."""

    success: bool
    user_id: int
    email: str | None = None
    name: str | None = None
    role: str | None = None
    error: str | None = None


@activity.defn(name="fetch_user_details")
async def fetch_user_details(input: FetchUserInput) -> FetchUserOutput:
    """
    MOCK: Simulate fetching user details from user-service.

    In production, this would make an HTTP GET to user-service.
    For now, returns mock data after a simulated delay.
    """
    logger.info(
        "========================================\n"
        "[Activity] fetch_user_details STARTED\n"
        "  user_id: %d\n"
        "========================================",
        input.user_id,
    )

    # Simulate the service call with delay
    result = await simulate_service_call(
        service_name="user-service",
        operation=f"GET /users/{input.user_id}",
        input_data={"user_id": input.user_id},
    )

    if not result.success:
        logger.warning(
            "[Activity] fetch_user_details FAILED for user_id=%d: %s",
            input.user_id,
            result.error,
        )
        return FetchUserOutput(
            success=False,
            user_id=input.user_id,
            error=result.error,
        )

    # Return mock user data
    mock_email = f"student_{input.user_id}@example.com"
    mock_name = f"Student {input.user_id}"

    logger.info(
        "[Activity] fetch_user_details COMPLETED\n"
        "  user_id: %d\n"
        "  email: %s\n"
        "  name: %s\n"
        "  role: student\n"
        "  latency: %dms",
        input.user_id,
        mock_email,
        mock_name,
        result.simulated_latency_ms,
    )

    return FetchUserOutput(
        success=True,
        user_id=input.user_id,
        email=mock_email,
        name=mock_name,
        role="student",
    )


@dataclass
class ValidateUserEnrollmentInput:
    """Input for validate_user_for_enrollment activity."""

    user_id: int


@dataclass
class ValidateUserEnrollmentOutput:
    """Output from validate_user_for_enrollment activity."""

    is_valid: bool
    user_id: int
    reason: str | None = None


@activity.defn(name="validate_user_for_enrollment")
async def validate_user_for_enrollment(
    input: ValidateUserEnrollmentInput,
) -> ValidateUserEnrollmentOutput:
    """
    MOCK: Simulate validating user eligibility for enrollment.

    In production, this would check:
    - User exists and is active
    - User is not an instructor (students only)
    - Payment status, account standing, etc.
    """
    logger.info(
        "========================================\n"
        "[Activity] validate_user_for_enrollment STARTED\n"
        "  user_id: %d\n"
        "========================================",
        input.user_id,
    )

    # Simulate the validation call
    result = await simulate_service_call(
        service_name="user-service",
        operation=f"GET /users/{input.user_id}/enrollment-eligibility",
        input_data={"user_id": input.user_id},
    )

    if not result.success:
        logger.warning(
            "[Activity] validate_user_for_enrollment FAILED: %s",
            result.error,
        )
        return ValidateUserEnrollmentOutput(
            is_valid=False,
            user_id=input.user_id,
            reason=f"Validation failed: {result.error}",
        )

    # Mock validation logic - always valid for demo
    # In production, parse actual response from user-service
    logger.info(
        "[Activity] validate_user_for_enrollment COMPLETED\n"
        "  user_id: %d\n"
        "  is_valid: True\n"
        "  latency: %dms",
        input.user_id,
        result.simulated_latency_ms,
    )

    return ValidateUserEnrollmentOutput(
        is_valid=True,
        user_id=input.user_id,
        reason=None,
    )
```

#### 6.3.3 Course Activities (Mock)

**File:** `services/core/src/core_service/temporal/activities/course_activities.py`

```python
"""Mock activities simulating course-service interactions."""

import logging
import random
from dataclasses import dataclass
from temporalio import activity

from core_service.temporal.activities.base import (
    simulate_service_call,
    generate_mock_id,
)

logger = logging.getLogger(__name__)


@dataclass
class FetchCourseInput:
    """Input for fetch_course_details activity."""

    course_id: int


@dataclass
class FetchCourseOutput:
    """Output from fetch_course_details activity."""

    success: bool
    course_id: int
    title: str | None = None
    instructor_id: int | None = None
    status: str | None = None
    error: str | None = None


@activity.defn(name="fetch_course_details")
async def fetch_course_details(input: FetchCourseInput) -> FetchCourseOutput:
    """
    MOCK: Simulate fetching course details from course-service.

    In production, this would make an HTTP GET to course-service.
    For now, returns mock data after a simulated delay.
    """
    logger.info(
        "========================================\n"
        "[Activity] fetch_course_details STARTED\n"
        "  course_id: %d\n"
        "========================================",
        input.course_id,
    )

    # Simulate the service call with delay
    result = await simulate_service_call(
        service_name="course-service",
        operation=f"GET /courses/{input.course_id}",
        input_data={"course_id": input.course_id},
    )

    if not result.success:
        logger.warning(
            "[Activity] fetch_course_details FAILED for course_id=%d: %s",
            input.course_id,
            result.error,
        )
        return FetchCourseOutput(
            success=False,
            course_id=input.course_id,
            error=result.error,
        )

    # Return mock course data
    mock_title = f"Introduction to Course {input.course_id}"
    mock_instructor_id = random.randint(100, 999)

    logger.info(
        "[Activity] fetch_course_details COMPLETED\n"
        "  course_id: %d\n"
        "  title: %s\n"
        "  instructor_id: %d\n"
        "  status: published\n"
        "  latency: %dms",
        input.course_id,
        mock_title,
        mock_instructor_id,
        result.simulated_latency_ms,
    )

    return FetchCourseOutput(
        success=True,
        course_id=input.course_id,
        title=mock_title,
        instructor_id=mock_instructor_id,
        status="published",
    )


@dataclass
class InitializeProgressInput:
    """Input for initialize_course_progress activity."""

    student_id: int
    course_id: int
    enrollment_id: int | None = None


@dataclass
class InitializeProgressOutput:
    """Output from initialize_course_progress activity."""

    success: bool
    progress_id: int | None = None
    error: str | None = None


@activity.defn(name="initialize_course_progress")
async def initialize_course_progress(
    input: InitializeProgressInput,
) -> InitializeProgressOutput:
    """
    MOCK: Simulate initializing progress tracking for enrollment.

    In production, this would POST to course-service to create
    initial progress records for all course modules.
    """
    logger.info(
        "========================================\n"
        "[Activity] initialize_course_progress STARTED\n"
        "  student_id: %d\n"
        "  course_id: %d\n"
        "  enrollment_id: %s\n"
        "========================================",
        input.student_id,
        input.course_id,
        input.enrollment_id,
    )

    # Simulate the service call with delay
    result = await simulate_service_call(
        service_name="course-service",
        operation="POST /progress/initialize",
        input_data={
            "student_id": input.student_id,
            "course_id": input.course_id,
            "enrollment_id": input.enrollment_id,
        },
    )

    if not result.success:
        logger.warning(
            "[Activity] initialize_course_progress FAILED: %s",
            result.error,
        )
        return InitializeProgressOutput(
            success=False,
            error=result.error,
        )

    # Generate mock progress ID
    mock_progress_id = random.randint(10000, 99999)

    logger.info(
        "[Activity] initialize_course_progress COMPLETED\n"
        "  student_id: %d\n"
        "  course_id: %d\n"
        "  progress_id: %d (mock)\n"
        "  latency: %dms",
        input.student_id,
        input.course_id,
        mock_progress_id,
        result.simulated_latency_ms,
    )

    return InitializeProgressOutput(
        success=True,
        progress_id=mock_progress_id,
    )


@dataclass
class FetchCourseModulesInput:
    """Input for fetch_course_modules activity."""

    course_id: int


@dataclass
class ModuleInfo:
    """Basic module information."""

    module_id: int
    title: str
    order: int


@dataclass
class FetchCourseModulesOutput:
    """Output from fetch_course_modules activity."""

    success: bool
    course_id: int
    modules: list[dict] | None = None
    module_count: int = 0
    error: str | None = None


@activity.defn(name="fetch_course_modules")
async def fetch_course_modules(
    input: FetchCourseModulesInput,
) -> FetchCourseModulesOutput:
    """
    MOCK: Simulate fetching course modules from course-service.
    """
    logger.info(
        "========================================\n"
        "[Activity] fetch_course_modules STARTED\n"
        "  course_id: %d\n"
        "========================================",
        input.course_id,
    )

    # Simulate the service call with delay
    result = await simulate_service_call(
        service_name="course-service",
        operation=f"GET /courses/{input.course_id}/modules",
        input_data={"course_id": input.course_id},
    )

    if not result.success:
        logger.warning(
            "[Activity] fetch_course_modules FAILED: %s",
            result.error,
        )
        return FetchCourseModulesOutput(
            success=False,
            course_id=input.course_id,
            error=result.error,
        )

    # Generate mock modules
    mock_modules = [
        {"module_id": 1, "title": "Module 1: Getting Started", "order": 1},
        {"module_id": 2, "title": "Module 2: Core Concepts", "order": 2},
        {"module_id": 3, "title": "Module 3: Advanced Topics", "order": 3},
    ]

    logger.info(
        "[Activity] fetch_course_modules COMPLETED\n"
        "  course_id: %d\n"
        "  module_count: %d\n"
        "  modules: %s\n"
        "  latency: %dms",
        input.course_id,
        len(mock_modules),
        [m["title"] for m in mock_modules],
        result.simulated_latency_ms,
    )

    return FetchCourseModulesOutput(
        success=True,
        course_id=input.course_id,
        modules=mock_modules,
        module_count=len(mock_modules),
    )
```

#### 6.3.4 Notification Activities (Mock)

**File:** `services/core/src/core_service/temporal/activities/notification_activities.py`

```python
"""Mock activities simulating notification-service interactions."""

import logging
from dataclasses import dataclass
from temporalio import activity

from core_service.temporal.activities.base import (
    simulate_service_call,
    generate_mock_id,
)

logger = logging.getLogger(__name__)


@dataclass
class SendWelcomeEmailInput:
    """Input for send_enrollment_welcome_email activity."""

    student_id: int
    student_email: str
    student_name: str | None
    course_id: int
    course_title: str


@dataclass
class SendWelcomeEmailOutput:
    """Output from send_enrollment_welcome_email activity."""

    success: bool
    notification_id: str | None = None
    error: str | None = None


@activity.defn(name="send_enrollment_welcome_email")
async def send_enrollment_welcome_email(
    input: SendWelcomeEmailInput,
) -> SendWelcomeEmailOutput:
    """
    MOCK: Simulate sending welcome email via notification-service.

    In production, this would POST to notification-service to queue
    a welcome email via Celery.
    """
    logger.info(
        "========================================\n"
        "[Activity] send_enrollment_welcome_email STARTED\n"
        "  student_id: %d\n"
        "  student_email: %s\n"
        "  student_name: %s\n"
        "  course_id: %d\n"
        "  course_title: %s\n"
        "========================================",
        input.student_id,
        input.student_email,
        input.student_name or "(not provided)",
        input.course_id,
        input.course_title,
    )

    # Simulate the service call with delay (emails typically take longer)
    result = await simulate_service_call(
        service_name="notification-service",
        operation="POST /notifications/email",
        input_data={
            "recipient_id": input.student_id,
            "recipient_email": input.student_email,
            "template": "enrollment_welcome",
            "subject": f"Welcome to {input.course_title}!",
        },
    )

    if not result.success:
        logger.warning(
            "[Activity] send_enrollment_welcome_email FAILED: %s",
            result.error,
        )
        return SendWelcomeEmailOutput(
            success=False,
            error=result.error,
        )

    # Generate mock notification ID
    mock_notification_id = generate_mock_id()

    logger.info(
        "[Activity] send_enrollment_welcome_email COMPLETED\n"
        "  notification_id: %s (mock)\n"
        "  email_to: %s\n"
        "  subject: Welcome to %s!\n"
        "  latency: %dms\n"
        "  [MOCK] Email would be queued to Celery in production",
        mock_notification_id,
        input.student_email,
        input.course_title,
        result.simulated_latency_ms,
    )

    return SendWelcomeEmailOutput(
        success=True,
        notification_id=mock_notification_id,
    )


@dataclass
class SendInAppNotificationInput:
    """Input for send_in_app_notification activity."""

    user_id: int
    title: str
    message: str
    notification_type: str = "info"


@dataclass
class SendInAppNotificationOutput:
    """Output from send_in_app_notification activity."""

    success: bool
    notification_id: str | None = None
    error: str | None = None


@activity.defn(name="send_in_app_notification")
async def send_in_app_notification(
    input: SendInAppNotificationInput,
) -> SendInAppNotificationOutput:
    """
    MOCK: Simulate sending in-app notification via notification-service.

    In production, this would POST to notification-service to create
    an in-app notification stored in the database.
    """
    logger.info(
        "========================================\n"
        "[Activity] send_in_app_notification STARTED\n"
        "  user_id: %d\n"
        "  title: %s\n"
        "  message: %s\n"
        "  type: %s\n"
        "========================================",
        input.user_id,
        input.title,
        input.message,
        input.notification_type,
    )

    # Simulate the service call with delay
    result = await simulate_service_call(
        service_name="notification-service",
        operation="POST /notifications/in-app",
        input_data={
            "user_id": input.user_id,
            "title": input.title,
            "message": input.message,
            "type": input.notification_type,
        },
    )

    if not result.success:
        logger.warning(
            "[Activity] send_in_app_notification FAILED: %s",
            result.error,
        )
        return SendInAppNotificationOutput(
            success=False,
            error=result.error,
        )

    # Generate mock notification ID
    mock_notification_id = generate_mock_id()

    logger.info(
        "[Activity] send_in_app_notification COMPLETED\n"
        "  notification_id: %s (mock)\n"
        "  user_id: %d\n"
        "  title: %s\n"
        "  latency: %dms\n"
        "  [MOCK] Notification would be persisted in production",
        mock_notification_id,
        input.user_id,
        input.title,
        result.simulated_latency_ms,
    )

    return SendInAppNotificationOutput(
        success=True,
        notification_id=mock_notification_id,
    )
```

#### 6.3.5 Activities Package Init

**File:** `services/core/src/core_service/temporal/activities/__init__.py`

```python
"""
Temporal activities for core-service workflows.

NOTE: All activities in this package are MOCK implementations.
They simulate microservice calls with delays and return mock data.
Replace with real HTTP implementations when ready for production.
"""

from core_service.temporal.activities.user_activities import (
    fetch_user_details,
    validate_user_for_enrollment,
    FetchUserInput,
    FetchUserOutput,
    ValidateUserEnrollmentInput,
    ValidateUserEnrollmentOutput,
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
)
from core_service.temporal.activities.notification_activities import (
    send_enrollment_welcome_email,
    send_in_app_notification,
    SendWelcomeEmailInput,
    SendWelcomeEmailOutput,
    SendInAppNotificationInput,
    SendInAppNotificationOutput,
)

# All activities that need to be registered with the worker
# These are MOCK implementations with simulated delays
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
    # User activities (mock)
    "fetch_user_details",
    "validate_user_for_enrollment",
    "FetchUserInput",
    "FetchUserOutput",
    "ValidateUserEnrollmentInput",
    "ValidateUserEnrollmentOutput",
    # Course activities (mock)
    "fetch_course_details",
    "initialize_course_progress",
    "fetch_course_modules",
    "FetchCourseInput",
    "FetchCourseOutput",
    "InitializeProgressInput",
    "InitializeProgressOutput",
    "FetchCourseModulesInput",
    "FetchCourseModulesOutput",
    # Notification activities (mock)
    "send_enrollment_welcome_email",
    "send_in_app_notification",
    "SendWelcomeEmailInput",
    "SendWelcomeEmailOutput",
    "SendInAppNotificationInput",
    "SendInAppNotificationOutput",
    # All activities list
    "ALL_ACTIVITIES",
]
```

---

### 6.4 Workflows

#### 6.4.1 Workflow Input/Output Schemas

**File:** `services/core/src/core_service/schemas/workflow_inputs.py`

```python
"""Pydantic models for workflow inputs and outputs."""

from datetime import datetime
from pydantic import BaseModel


class EnrollmentWorkflowInput(BaseModel):
    """Input for the enrollment workflow."""

    student_id: int
    course_id: int
    course_title: str
    student_email: str
    enrollment_timestamp: str | None = None

    def model_post_init(self, __context) -> None:
        if self.enrollment_timestamp is None:
            self.enrollment_timestamp = datetime.utcnow().isoformat()


class EnrollmentWorkflowOutput(BaseModel):
    """Output from the enrollment workflow."""

    workflow_id: str
    student_id: int
    course_id: int
    success: bool
    steps_completed: list[str]
    steps_failed: list[str]
    error_message: str | None = None
```

#### 6.4.2 Enrollment Workflow

**File:** `services/core/src/core_service/temporal/workflows/enrollment_workflow.py`

```python
"""Enrollment workflow that orchestrates student enrollment process."""

import logging
from datetime import timedelta
from dataclasses import dataclass

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
            await self._initialize_progress(input.student_id, input.course_id)

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

    async def _initialize_progress(self, student_id: int, course_id: int) -> None:
        """Step 4: Initialize progress tracking."""
        step_name = "initialize_progress"
        workflow.logger.info("Step: %s", step_name)

        result = await workflow.execute_activity(
            initialize_course_progress,
            InitializeProgressInput(
                student_id=student_id,
                course_id=course_id,
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
```

#### 6.4.3 Workflows Package Init

**File:** `services/core/src/core_service/temporal/workflows/__init__.py`

```python
"""Temporal workflows for core-service."""

from core_service.temporal.workflows.enrollment_workflow import (
    EnrollmentWorkflow,
    EnrollmentWorkflowInput,
    EnrollmentWorkflowOutput,
)

# All workflows that need to be registered with the worker
ALL_WORKFLOWS = [
    EnrollmentWorkflow,
]

__all__ = [
    "EnrollmentWorkflow",
    "EnrollmentWorkflowInput",
    "EnrollmentWorkflowOutput",
    "ALL_WORKFLOWS",
]
```

---

### 6.5 Kafka Consumer for Workflow Trigger

**File:** `services/core/src/core_service/kafka/enrollment_consumer.py`

```python
"""Kafka consumer that triggers enrollment workflows."""

import asyncio
import logging
import sys
from typing import Any

from shared.kafka.consumer import EventConsumer
from shared.kafka.topics import Topics
from shared.schemas.envelope import EventEnvelope

from core_service.config import core_settings
from core_service.temporal.client import get_temporal_client
from core_service.temporal.workflows import (
    EnrollmentWorkflow,
    EnrollmentWorkflowInput,
)

logger = logging.getLogger(__name__)

MAX_RETRY_DELAY = 30


def _log(msg: str) -> None:
    """Log to stderr for visibility in Docker."""
    print(msg, file=sys.stderr, flush=True)


async def handle_enrollment_event(topic: str, envelope: EventEnvelope) -> None:
    """
    Handle enrollment events and start Temporal workflows.

    This is the bridge between Kafka events (fire-and-forget trigger)
    and Temporal workflows (orchestrated with activities).
    """
    logger.info(
        "Received event: topic=%s event_type=%s event_id=%s",
        topic,
        envelope.event_type,
        envelope.event_id,
    )

    if envelope.event_type != "enrollment.created":
        logger.debug("Ignoring event type: %s", envelope.event_type)
        return

    payload = envelope.payload
    student_id = payload.get("student_id")
    course_id = payload.get("course_id")
    course_title = payload.get("course_title", f"Course {course_id}")
    student_email = payload.get("email", "")

    if not student_id or not course_id:
        logger.error("Invalid enrollment event payload: %s", payload)
        return

    logger.info(
        "Starting EnrollmentWorkflow for student_id=%d, course_id=%d",
        student_id,
        course_id,
    )

    try:
        # Get Temporal client
        client = await get_temporal_client()

        # Create workflow input
        workflow_input = EnrollmentWorkflowInput(
            student_id=student_id,
            course_id=course_id,
            course_title=course_title,
            student_email=student_email,
        )

        # Start workflow (non-blocking - workflow runs asynchronously)
        # Using a deterministic workflow ID allows deduplication
        workflow_id = f"enrollment-{student_id}-{course_id}-{envelope.event_id}"

        handle = await client.start_workflow(
            EnrollmentWorkflow.run,
            workflow_input,
            id=workflow_id,
            task_queue=core_settings.TEMPORAL_TASK_QUEUE,
        )

        logger.info(
            "EnrollmentWorkflow started: workflow_id=%s",
            handle.id,
        )

    except Exception as e:
        logger.error(
            "Failed to start EnrollmentWorkflow: %s",
            str(e),
            exc_info=True,
        )


async def run_enrollment_consumer() -> None:
    """
    Run the Kafka consumer that listens for enrollment events
    and triggers Temporal workflows.
    """
    topics = [Topics.ENROLLMENT]
    attempt = 0

    _log(
        f"[core-service] Enrollment consumer starting | "
        f"topics={topics} broker={core_settings.KAFKA_BOOTSTRAP_SERVERS}"
    )

    while True:
        consumer = EventConsumer(
            topics=topics,
            bootstrap_servers=core_settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id="core-service-enrollment",
        )
        try:
            await consumer.start(handler=handle_enrollment_event)
        except asyncio.CancelledError:
            _log("[core-service] Enrollment consumer shutting down.")
            raise
        except Exception as e:
            attempt += 1
            delay = min(2**attempt, MAX_RETRY_DELAY)
            _log(
                f"[core-service] Consumer error (attempt {attempt}), "
                f"retry in {delay}s: {e!r}"
            )
            await asyncio.sleep(delay)
        else:
            break
```

**File:** `services/core/src/core_service/kafka/__init__.py`

```python
"""Kafka consumers for core-service."""

from core_service.kafka.enrollment_consumer import run_enrollment_consumer

__all__ = ["run_enrollment_consumer"]
```

---

### 6.6 Worker Process

**File:** `services/core/src/core_service/temporal/worker.py`

```python
"""Temporal worker that executes workflows and activities."""

import asyncio
import logging
import sys

from temporalio.client import Client
from temporalio.worker import Worker

from core_service.config import core_settings
from core_service.temporal.activities import ALL_ACTIVITIES
from core_service.temporal.workflows import ALL_WORKFLOWS

logger = logging.getLogger(__name__)


def _log(msg: str) -> None:
    """Log to stderr for visibility in Docker."""
    print(msg, file=sys.stderr, flush=True)


async def run_worker() -> None:
    """
    Run the Temporal worker that executes workflows and activities.

    The worker:
    1. Connects to Temporal server
    2. Polls the task queue for work
    3. Executes workflows and activities
    4. Reports results back to Temporal
    """
    _log(
        f"[core-service] Temporal worker starting | "
        f"host={core_settings.TEMPORAL_HOST} "
        f"namespace={core_settings.TEMPORAL_NAMESPACE} "
        f"task_queue={core_settings.TEMPORAL_TASK_QUEUE}"
    )

    # Connect to Temporal
    client = await Client.connect(
        core_settings.TEMPORAL_HOST,
        namespace=core_settings.TEMPORAL_NAMESPACE,
    )

    _log("[core-service] Connected to Temporal server")

    # Create and run worker
    worker = Worker(
        client,
        task_queue=core_settings.TEMPORAL_TASK_QUEUE,
        workflows=ALL_WORKFLOWS,
        activities=ALL_ACTIVITIES,
    )

    _log(
        f"[core-service] Worker registered | "
        f"workflows={[w.__name__ for w in ALL_WORKFLOWS]} "
        f"activities={[a.__name__ for a in ALL_ACTIVITIES]}"
    )

    # Run the worker (blocks until shutdown)
    await worker.run()


async def run_worker_with_retry(max_retries: int = 10) -> None:
    """Run worker with exponential backoff retry."""
    attempt = 0
    max_delay = 30

    while True:
        try:
            await run_worker()
            break
        except asyncio.CancelledError:
            _log("[core-service] Worker shutdown requested")
            raise
        except Exception as e:
            attempt += 1
            if attempt > max_retries:
                _log(f"[core-service] Worker failed after {max_retries} attempts")
                raise

            delay = min(2**attempt, max_delay)
            _log(
                f"[core-service] Worker error (attempt {attempt}/{max_retries}), "
                f"retry in {delay}s: {e!r}"
            )
            await asyncio.sleep(delay)
```

---

### 6.7 Application Integration

**File:** `services/core/src/core_service/main.py` (Updated)

```python
"""Core service application entrypoint."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core_service.api.router import router
from core_service.config import core_settings
from core_service.kafka.enrollment_consumer import run_enrollment_consumer
from core_service.temporal.worker import run_worker_with_retry
from core_service.temporal.client import close_temporal_client

logging.basicConfig(
    level=getattr(logging, core_settings.LOG_LEVEL.upper(), logging.INFO)
)
logger = logging.getLogger(__name__)

# Background tasks
_background_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Core service startup/shutdown hooks."""
    logger.info(
        "core_service_starting temporal=%s namespace=%s task_queue=%s",
        core_settings.TEMPORAL_HOST,
        core_settings.TEMPORAL_NAMESPACE,
        core_settings.TEMPORAL_TASK_QUEUE,
    )

    # Start background tasks
    worker_task = asyncio.create_task(
        run_worker_with_retry(),
        name="temporal-worker",
    )
    consumer_task = asyncio.create_task(
        run_enrollment_consumer(),
        name="enrollment-consumer",
    )
    _background_tasks.extend([worker_task, consumer_task])

    logger.info("Background tasks started: temporal-worker, enrollment-consumer")

    yield

    # Shutdown
    logger.info("core_service_shutting_down")

    # Cancel background tasks
    for task in _background_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Close Temporal client
    await close_temporal_client()

    logger.info("core_service_shutdown_complete")


app = FastAPI(
    title="SmartCourse Core Service",
    description="Workflow orchestration and cross-cutting platform workflows",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/health")
async def health_check() -> dict:
    """Container/local health endpoint."""
    return {
        "status": "ok",
        "service": "core-service",
    }
```

**File:** `services/core/src/core_service/api/router.py` (Updated)

```python
"""Core service API routes."""

from fastapi import APIRouter

from core_service.config import core_settings

router = APIRouter(prefix="/core", tags=["core"])


@router.get("/health")
async def core_health() -> dict:
    """Core service health endpoint (routed via API gateway)."""
    return {
        "status": "ok",
        "service": "core-service",
        "capabilities": ["workflow-orchestration", "event-bridge", "temporal"],
    }


@router.get("/workflows/temporal")
async def temporal_workflow_status() -> dict:
    """Temporal workflow configuration status."""
    return {
        "enabled": True,
        "status": "configured",
        "message": "Temporal workflow engine is active.",
        "temporal_host": core_settings.TEMPORAL_HOST,
        "temporal_namespace": core_settings.TEMPORAL_NAMESPACE,
        "task_queue": core_settings.TEMPORAL_TASK_QUEUE,
        "workflows": ["EnrollmentWorkflow"],
        "activities": [
            "fetch_user_details",
            "validate_user_for_enrollment",
            "fetch_course_details",
            "initialize_course_progress",
            "fetch_course_modules",
            "send_enrollment_welcome_email",
            "send_in_app_notification",
        ],
    }


@router.get("/workflows/enrollment/info")
async def enrollment_workflow_info() -> dict:
    """Information about the enrollment workflow."""
    return {
        "workflow_name": "EnrollmentWorkflow",
        "trigger": "Kafka event: enrollment.created",
        "steps": [
            {
                "order": 1,
                "name": "validate_user",
                "activity": "validate_user_for_enrollment",
                "service": "user-service",
                "critical": True,
            },
            {
                "order": 2,
                "name": "fetch_user_details",
                "activity": "fetch_user_details",
                "service": "user-service",
                "critical": False,
            },
            {
                "order": 3,
                "name": "fetch_course_details",
                "activity": "fetch_course_details",
                "service": "course-service",
                "critical": False,
            },
            {
                "order": 4,
                "name": "initialize_progress",
                "activity": "initialize_course_progress",
                "service": "course-service",
                "critical": False,
            },
            {
                "order": 5,
                "name": "send_welcome_email",
                "activity": "send_enrollment_welcome_email",
                "service": "notification-service",
                "critical": False,
            },
            {
                "order": 6,
                "name": "send_in_app_notification",
                "activity": "send_in_app_notification",
                "service": "notification-service",
                "critical": False,
            },
        ],
    }
```

---

### 6.8 Temporal Package Init

**File:** `services/core/src/core_service/temporal/__init__.py`

```python
"""Temporal workflow orchestration for core-service."""

from core_service.temporal.client import get_temporal_client, close_temporal_client
from core_service.temporal.worker import run_worker, run_worker_with_retry

__all__ = [
    "get_temporal_client",
    "close_temporal_client",
    "run_worker",
    "run_worker_with_retry",
]
```

---

## 7. Error Handling & Retry Policies

### 7.1 Activity Retry Policy

Activities use the following retry policy by default:

```python
DEFAULT_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),    # Start with 1s delay
    backoff_coefficient=2.0,                  # Double each time
    maximum_interval=timedelta(seconds=30),   # Cap at 30s
    maximum_attempts=3,                       # Try 3 times max
)
```

### 7.2 Activity Timeouts

Each activity has timeouts configured:

| Timeout Type                | Value      | Description                       |
| --------------------------- | ---------- | --------------------------------- |
| `start_to_close_timeout`    | 30-60s     | Max time for activity to complete |
| `schedule_to_start_timeout` | (default)  | Time waiting in queue             |
| `heartbeat_timeout`         | (not used) | For long-running activities       |

### 7.3 Workflow Error Handling

The workflow implements graceful degradation:

1. **Critical steps** (e.g., user validation): Workflow fails if these fail
2. **Non-critical steps** (e.g., notifications): Workflow continues even if these fail
3. **Fallback values**: If fetching details fails, use event payload values

### 7.4 Idempotency

Activities should be designed to be idempotent:

- Use workflow ID in external calls for deduplication
- Check if resource already exists before creating
- Temporal guarantees at-least-once execution

---

## 8. Testing

### 8.1 Running Locally

```bash
# Start infrastructure
docker-compose up -d postgres redis kafka zookeeper schema-registry temporal temporal-ui

# Wait for Temporal to be healthy
docker-compose logs -f temporal

# Start core service
cd services/core
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
uv pip install -e ../../shared
python -m uvicorn core_service.main:app --host 0.0.0.0 --port 8006 --reload
```

### 8.2 Testing the Workflow

```bash
# 1. Login and get token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/users/login \
  -H "Content-Type: application/json" \
  -d '{"email": "student@example.com", "password": "password123"}' \
  | jq -r '.access_token')

# 2. Enroll in a course (this triggers the workflow)
curl -X POST http://localhost:8000/api/v1/enrollments/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"course_id": 1}'

# 3. Check Temporal UI at http://localhost:8080
# Look for workflow: enrollment-{student_id}-{course_id}-{event_id}

# 4. Check workflow status via API
curl http://localhost:8000/api/v1/core/workflows/temporal
```

### 8.3 Viewing Workflow in Temporal UI

1. Open http://localhost:8080
2. Select namespace: `default`
3. Find workflows starting with `enrollment-`
4. View:
   - Workflow history (all events)
   - Activity results
   - Query workflow state

---

## 9. Complete Code Files Summary

### Files to Create

| File                                                                            | Purpose                          |
| ------------------------------------------------------------------------------- | -------------------------------- |
| `temporal-config/development-sql.yaml`                                          | Temporal dynamic config          |
| `services/core/src/core_service/config.py`                                      | Updated config with service URLs |
| `services/core/src/core_service/main.py`                                        | Updated main with lifespan       |
| `services/core/src/core_service/api/router.py`                                  | Updated router                   |
| `services/core/src/core_service/kafka/__init__.py`                              | Kafka package                    |
| `services/core/src/core_service/kafka/enrollment_consumer.py`                   | Kafka consumer                   |
| `services/core/src/core_service/temporal/__init__.py`                           | Temporal package                 |
| `services/core/src/core_service/temporal/client.py`                             | Temporal client                  |
| `services/core/src/core_service/temporal/worker.py`                             | Temporal worker                  |
| `services/core/src/core_service/temporal/activities/__init__.py`                | Activities package (mock)        |
| `services/core/src/core_service/temporal/activities/base.py`                    | Mock activity utilities          |
| `services/core/src/core_service/temporal/activities/user_activities.py`         | User activities (mock)           |
| `services/core/src/core_service/temporal/activities/course_activities.py`       | Course activities (mock)         |
| `services/core/src/core_service/temporal/activities/notification_activities.py` | Notification activities (mock)   |
| `services/core/src/core_service/temporal/workflows/__init__.py`                 | Workflows package                |
| `services/core/src/core_service/temporal/workflows/enrollment_workflow.py`      | Enrollment workflow              |
| `services/core/src/core_service/schemas/__init__.py`                            | Schemas package                  |
| `services/core/src/core_service/schemas/workflow_inputs.py`                     | Workflow input schemas           |

### Files to Update

| File                           | Change                                                   |
| ------------------------------ | -------------------------------------------------------- |
| `docker-compose.yml`           | Add temporal, temporal-ui, temporal-admin-tools services |
| `services/core/pyproject.toml` | Add temporalio, aiokafka dependencies                    |

---

## 10. Switching from Mock to Real HTTP Activities

When you're ready to switch from mock activities to real HTTP calls:

### 10.1 Update Dependencies

Add `httpx` to `pyproject.toml`:

```toml
dependencies = [
    # ... existing deps ...
    "httpx>=0.27.0",  # Add this for HTTP activity calls
]
```

### 10.2 Update Config

Uncomment the service URLs in `config.py`:

```python
# Enable these settings:
USER_SERVICE_URL: str = "http://user-service:8001"
COURSE_SERVICE_URL: str = "http://course-service:8002"
NOTIFICATION_SERVICE_URL: str = "http://notification-service:8005"
HTTP_TIMEOUT_SECONDS: float = 30.0
```

### 10.3 Replace base.py

Replace the mock utilities with the HTTP client:

```python
"""Base HTTP client for activities."""

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from core_service.config import core_settings

logger = logging.getLogger(__name__)


@dataclass
class ActivityResult:
    """Standard result from an activity."""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    status_code: int | None = None


class ActivityHttpClient:
    """HTTP client wrapper for activity calls to microservices."""

    def __init__(self, base_url: str, service_name: str):
        self.base_url = base_url.rstrip("/")
        self.service_name = service_name
        self.timeout = httpx.Timeout(core_settings.HTTP_TIMEOUT_SECONDS)

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> ActivityResult:
        """Make an HTTP request to the microservice."""
        url = f"{self.base_url}{path}"
        default_headers = {"Content-Type": "application/json"}
        if headers:
            default_headers.update(headers)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method=method, url=url, json=json,
                    params=params, headers=default_headers,
                )

                if response.status_code >= 400:
                    return ActivityResult(
                        success=False,
                        error=response.text,
                        status_code=response.status_code,
                    )

                return ActivityResult(
                    success=True,
                    data=response.json() if response.content else None,
                    status_code=response.status_code,
                )

        except httpx.RequestError as e:
            return ActivityResult(success=False, error=str(e))
```

### 10.4 Update Activity Implementations

Replace `simulate_service_call()` with actual HTTP client calls in each activity file.

---

## Key Takeaways

1. **Kafka = Trigger**: The `enrollment.created` Kafka event triggers the workflow start
2. **Temporal = Orchestration**: Temporal manages the workflow state and activity execution
3. **Activities = Mock (for now)**: Each activity simulates work with delays and logging
4. **Two-way Communication**: Activities use await pattern - workflow waits for completion
5. **Error Recovery**: Temporal knows exactly where failures occur and can retry
6. **Visibility**: Use Temporal UI at `http://localhost:8080` to monitor workflow execution
7. **Configurable**: Delay ranges and failure rates configurable via environment variables

### Mock Implementation Benefits

- **No service dependencies**: Test Temporal infrastructure without running all microservices
- **Realistic simulation**: Configurable delays simulate actual network latency
- **Easy debugging**: Detailed logging shows each activity step
- **Gradual transition**: Switch to real HTTP calls when ready (see Section 10)

This architecture provides the reliability of orchestrated workflows while keeping the decoupling benefits of event-driven architecture for the initial trigger.
