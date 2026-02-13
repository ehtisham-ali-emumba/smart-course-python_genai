# Notification Service - Implementation Instructions

**Version:** 1.1  
**Date:** February 13, 2026  
**Scope:** Skeleton implementation of the Notification Service with logging-only behavior (no DB, no real email/push yet)

---

## Overview

Create a new **Notification Service** (`services/notification-service/`) for the SmartCourse platform. This service is designed to eventually handle **email** and **mobile push notifications**, but for now it should be a **logging-only skeleton** — every notification action simply logs what _would_ happen (e.g., "Would send enrollment welcome email to user 42 for course 'Python Basics'").

**There is NO notification table in the database.** This service does not connect to PostgreSQL or MongoDB. It only uses Python's `structlog` logger to output structured JSON logs.

**CRITICAL: This service is NOT exposed to the public.** It runs behind the API Gateway (Nginx) on the internal Docker network only. No ports are mapped to the host. Clients access it exclusively through `http://localhost:8000/notifications/*` via the gateway. The gateway handles JWT verification and forwards `X-User-ID` / `X-User-Role` headers.

---

## Architecture Context

| Property            | Value                                      |
| ------------------- | ------------------------------------------ |
| **Port**            | 8005 (internal Docker network only)        |
| **Database**        | None (logging only, no DB connection)      |
| **Cache**           | None                                       |
| **Public Access**   | None — only reachable via API Gateway      |
| **Events Consumed** | Will eventually consume Kafka events (stubbed for now) |
| **Queue**           | Will eventually use Celery + RabbitMQ (stubbed for now) |

### Where This Service Fits

```
Client (browser/mobile)
   │
   │  HTTPS
   ▼
API Gateway (Nginx :8000)  ─── JWT verification via auth-sidecar ───►  auth-sidecar (:8010)
   │                                                                      │
   │  sets X-User-ID, X-User-Role headers                                │
   │  proxies to internal services                                        │
   ▼                                                                      │
Notification Service (:8005, internal only)                               │
   │                                                                      │
   ├── POST /notifications/send        (generic send — logs only)         │
   ├── POST /notifications/enrollment  (enrollment notification — logs)   │
   ├── POST /notifications/course      (course event notification — logs) │
   ├── POST /notifications/certificate (certificate notification — logs)  │
   ├── POST /notifications/progress    (progress notification — logs)     │
   └── GET  /health                    (health check)
```

All endpoints are **internal only** — not directly accessible from outside the Docker network. They are **protected behind the API Gateway** which handles JWT verification and sets `X-User-ID` / `X-User-Role` headers on forwarded requests.

---

## Required Directory Structure

Follow the exact same pattern as `services/user-service/`. Create this structure:

```
services/notification-service/
├── pyproject.toml
├── Dockerfile
├── .env.example
└── src/
    └── notification_service/
        ├── __init__.py
        ├── main.py
        ├── config.py
        ├── core/
        │   ├── __init__.py
        │   └── logging.py
        ├── schemas/
        │   ├── __init__.py
        │   └── notification.py
        ├── services/
        │   ├── __init__.py
        │   └── notification.py
        └── api/
            ├── __init__.py
            ├── router.py
            └── notification.py
```

**Note:** No `models/`, `repositories/`, `core/database.py`, `core/redis.py`, `core/cache.py`, `core/security.py`, or `alembic/` folders — this service has no database or cache.

---

## File-by-File Implementation

### 1. `pyproject.toml`

**Must follow the exact same format as user-service/course-service** (`setuptools.build_meta`, line-length 100, same ruff/black/mypy config).

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "smartcourse-notification-service"
version = "0.1.0"
description = "SmartCourse Notification Service"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "httpx>=0.26.0",
    "structlog>=24.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "httpx>=0.26.0",
    "ruff>=0.1.0",
    "black>=24.1.0",
    "mypy>=1.8.0",
]

[tool.setuptools.packages.find]
where = ["src"]
include = ["notification_service*"]

[tool.ruff]
line-length = 100
select = ["E", "F", "I", "N", "W"]

[tool.black]
line-length = 100

[tool.mypy]
python_version = "3.11"
strict = true
```

**Key difference from user-service:** No SQLAlchemy, Alembic, asyncpg, redis, python-jose, passlib, bcrypt, motor, opentelemetry, or prometheus-client. This is a lightweight logging-only service. Dependency **version ranges match the existing services exactly**.

---

### 2. `Dockerfile`

**Must follow the exact same build pattern as user-service Dockerfile** (explicit pip install of deps first for Docker layer caching, then copy src, then `pip install -e .`, set PYTHONPATH).

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy only pyproject.toml first for better caching
COPY pyproject.toml .

# Install dependencies first (without the package itself)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    fastapi>=0.109.0 \
    uvicorn[standard]>=0.27.0 \
    pydantic>=2.5.0 \
    pydantic-settings>=2.1.0 \
    httpx>=0.26.0 \
    structlog>=24.1.0

COPY src/ ./src/

# Install the package in editable mode
RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/src:/app
EXPOSE 8005

# No Alembic migration — this service has no database
CMD ["uvicorn", "notification_service.main:app", "--host", "0.0.0.0", "--port", "8005"]
```

**Key differences from user-service:**
- No `libpq-dev` system dependency (no PostgreSQL)
- No Alembic migration step in CMD (`sh -c "alembic upgrade head && ..."`)
- Fewer pip dependencies (no SQLAlchemy, redis, JWT, etc.)

---

### 3. `.env.example`

```env
# Service Configuration
SERVICE_NAME=notification-service
SERVICE_PORT=8005
LOG_LEVEL=INFO

# Future: Email Provider Configuration (not used yet)
# SMTP_HOST=smtp.example.com
# SMTP_PORT=587
# SMTP_USER=notifications@smartcourse.com
# SMTP_PASSWORD=secret
# SMTP_FROM_EMAIL=no-reply@smartcourse.com

# Future: Push Notification Configuration (not used yet)
# FIREBASE_PROJECT_ID=
# FIREBASE_CREDENTIALS_PATH=

# Future: Celery/RabbitMQ Configuration (not used yet)
# RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672//
# CELERY_BROKER_URL=amqp://guest:guest@rabbitmq:5672//
```

---

### 4. `src/notification_service/__init__.py`

```python
"""SmartCourse Notification Service."""
```

---

### 5. `src/notification_service/config.py`

Use `pydantic-settings` following the **exact same pattern as user-service `config.py`** (inner `class Config`, not `model_config` dict).

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Notification service configuration."""

    SERVICE_NAME: str = "notification-service"
    SERVICE_PORT: int = 8005
    LOG_LEVEL: str = "INFO"

    # Future: Email configuration (not used yet)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "no-reply@smartcourse.com"

    # Future: Push notification configuration (not used yet)
    FIREBASE_PROJECT_ID: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
```

---

### 6. `src/notification_service/core/__init__.py`

```python
"""Core utilities for notification service."""
```

---

### 7. `src/notification_service/core/logging.py`

Set up structured logging with `structlog`. This is the core of the service since everything is logging for now.

```python
import logging
import structlog
from notification_service.config import settings


def setup_logging() -> None:
    """Configure structured logging for the notification service."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structured logger instance."""
    logger = structlog.get_logger()
    if name:
        logger = logger.bind(component=name)
    return logger
```

---

### 8. `src/notification_service/schemas/__init__.py`

```python
"""Pydantic schemas for notification service."""
```

---

### 9. `src/notification_service/schemas/notification.py`

Define request/response schemas. These model the payloads that other services (or the gateway) will send.

```python
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


# --- Enums ---

class NotificationChannel(str, Enum):
    """Supported notification delivery channels."""
    EMAIL = "email"
    PUSH = "push"
    IN_APP = "in_app"
    SMS = "sms"


class NotificationPriority(str, Enum):
    """Notification priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationType(str, Enum):
    """Types of notifications the service handles."""
    ENROLLMENT_WELCOME = "enrollment_welcome"
    ENROLLMENT_COMPLETED = "enrollment_completed"
    COURSE_PUBLISHED = "course_published"
    COURSE_ARCHIVED = "course_archived"
    MODULE_COMPLETED = "module_completed"
    CERTIFICATE_ISSUED = "certificate_issued"
    COURSE_REMINDER = "course_reminder"
    USER_REGISTERED = "user_registered"
    GENERIC = "generic"


# --- Request Schemas ---

class SendNotificationRequest(BaseModel):
    """Generic notification send request."""
    user_id: int = Field(..., description="Target user ID")
    type: NotificationType = Field(default=NotificationType.GENERIC, description="Notification type")
    channel: NotificationChannel = Field(default=NotificationChannel.EMAIL, description="Delivery channel")
    priority: NotificationPriority = Field(default=NotificationPriority.NORMAL, description="Priority level")
    title: str = Field(..., min_length=1, max_length=255, description="Notification title")
    message: str = Field(..., min_length=1, description="Notification message body")
    metadata: dict | None = Field(default=None, description="Additional metadata (course_id, enrollment_id, etc.)")


class EnrollmentNotificationRequest(BaseModel):
    """Notification request for enrollment events."""
    user_id: int = Field(..., description="Student user ID")
    course_id: int = Field(..., description="Course ID")
    course_title: str = Field(..., description="Course title")
    enrollment_id: int = Field(..., description="Enrollment ID")
    instructor_name: str = Field(default="", description="Instructor name")


class CourseNotificationRequest(BaseModel):
    """Notification request for course events (published, archived, etc.)."""
    course_id: int = Field(..., description="Course ID")
    course_title: str = Field(..., description="Course title")
    instructor_id: int = Field(..., description="Instructor user ID")
    event: str = Field(..., description="Event type: 'published', 'archived', 'updated'")
    affected_user_ids: list[int] = Field(default_factory=list, description="List of user IDs to notify (e.g., enrolled students)")


class CertificateNotificationRequest(BaseModel):
    """Notification request when a certificate is issued."""
    user_id: int = Field(..., description="Student user ID")
    course_id: int = Field(..., description="Course ID")
    course_title: str = Field(..., description="Course title")
    certificate_id: int = Field(..., description="Certificate ID")
    certificate_number: str = Field(..., description="Certificate number")
    verification_code: str = Field(..., description="Verification code")


class ProgressNotificationRequest(BaseModel):
    """Notification request for progress milestones."""
    user_id: int = Field(..., description="Student user ID")
    course_id: int = Field(..., description="Course ID")
    course_title: str = Field(..., description="Course title")
    enrollment_id: int = Field(..., description="Enrollment ID")
    module_title: str = Field(default="", description="Completed module title")
    completion_percentage: float = Field(..., ge=0, le=100, description="Current completion percentage")


# --- Response Schemas ---

class NotificationResponse(BaseModel):
    """Standard response for notification requests."""
    success: bool = Field(..., description="Whether the notification was queued/logged successfully")
    message: str = Field(..., description="Human-readable status message")
    notification_type: NotificationType = Field(..., description="Type of notification processed")
    channel: NotificationChannel = Field(default=NotificationChannel.EMAIL, description="Delivery channel used")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Processing timestamp")


```

---

### 10. `src/notification_service/services/__init__.py`

```python
"""Business logic services for notification service."""
```

---

### 11. `src/notification_service/services/notification.py`

This is the **core business logic**. Every method logs what it _would_ do. Keep it generic so real implementations (email via SMTP, push via Firebase, etc.) can be plugged in later.

```python
from notification_service.core.logging import get_logger
from notification_service.schemas.notification import (
    CertificateNotificationRequest,
    CourseNotificationRequest,
    EnrollmentNotificationRequest,
    NotificationChannel,
    NotificationPriority,
    NotificationResponse,
    NotificationType,
    ProgressNotificationRequest,
    SendNotificationRequest,
)

logger = get_logger("notification_service")


class NotificationService:
    """
    Notification service handling all notification logic.

    Currently logs all notifications. Will be extended to:
    - Send emails via SMTP/SendGrid/SES
    - Send push notifications via Firebase/APNs
    - Queue tasks via Celery + RabbitMQ
    """

    # --- Generic Send ---

    async def send_notification(self, request: SendNotificationRequest) -> NotificationResponse:
        """
        Send a generic notification. Currently logs only.

        In the future, this will route to the appropriate channel handler
        (email, push, in-app, SMS) based on request.channel.
        """
        logger.info(
            "notification_send_requested",
            user_id=request.user_id,
            notification_type=request.type.value,
            channel=request.channel.value,
            priority=request.priority.value,
            title=request.title,
            message_preview=request.message[:100],
            metadata=request.metadata,
        )

        # Future: Route to appropriate channel handler
        # await self._send_email(request) / self._send_push(request) / etc.

        return NotificationResponse(
            success=True,
            message=f"[LOG] Notification '{request.title}' for user {request.user_id} logged via {request.channel.value}",
            notification_type=request.type,
            channel=request.channel,
        )

    # --- Enrollment Notifications ---

    async def notify_enrollment(self, request: EnrollmentNotificationRequest) -> NotificationResponse:
        """
        Handle enrollment welcome notification. Currently logs only.

        Triggered when: enrollment.created event occurs.
        Future behavior: Send welcome email + in-app notification.
        """
        logger.info(
            "enrollment_notification",
            event="enrollment_created",
            user_id=request.user_id,
            course_id=request.course_id,
            course_title=request.course_title,
            enrollment_id=request.enrollment_id,
            instructor_name=request.instructor_name,
            action="would_send_welcome_email",
        )
        logger.info(
            "enrollment_notification",
            event="enrollment_created",
            user_id=request.user_id,
            course_id=request.course_id,
            action="would_create_in_app_notification",
            message=f"You have been enrolled in '{request.course_title}'",
        )

        return NotificationResponse(
            success=True,
            message=f"[LOG] Enrollment notification for user {request.user_id} in course '{request.course_title}' (enrollment #{request.enrollment_id}) logged",
            notification_type=NotificationType.ENROLLMENT_WELCOME,
            channel=NotificationChannel.EMAIL,
        )

    # --- Course Event Notifications ---

    async def notify_course_event(self, request: CourseNotificationRequest) -> NotificationResponse:
        """
        Handle course lifecycle notifications. Currently logs only.

        Triggered when: course.published, course.archived events occur.
        Future behavior:
        - course.published → Email enrolled students, push notification
        - course.archived → Email enrolled students with info
        """
        logger.info(
            "course_notification",
            event=request.event,
            course_id=request.course_id,
            course_title=request.course_title,
            instructor_id=request.instructor_id,
            affected_users_count=len(request.affected_user_ids),
            affected_user_ids=request.affected_user_ids,
            action=f"would_notify_users_about_course_{request.event}",
        )

        notification_type = (
            NotificationType.COURSE_PUBLISHED if request.event == "published"
            else NotificationType.COURSE_ARCHIVED if request.event == "archived"
            else NotificationType.GENERIC
        )

        return NotificationResponse(
            success=True,
            message=f"[LOG] Course '{request.course_title}' {request.event} notification for {len(request.affected_user_ids)} users logged",
            notification_type=notification_type,
            channel=NotificationChannel.EMAIL,
        )

    # --- Certificate Notifications ---

    async def notify_certificate(self, request: CertificateNotificationRequest) -> NotificationResponse:
        """
        Handle certificate issuance notification. Currently logs only.

        Triggered when: certificate.issued event occurs.
        Future behavior: Send congratulatory email with certificate download link.
        """
        logger.info(
            "certificate_notification",
            event="certificate_issued",
            user_id=request.user_id,
            course_id=request.course_id,
            course_title=request.course_title,
            certificate_id=request.certificate_id,
            certificate_number=request.certificate_number,
            verification_code=request.verification_code,
            action="would_send_certificate_email",
            message=f"Congratulations! Your certificate for '{request.course_title}' is ready.",
        )

        return NotificationResponse(
            success=True,
            message=f"[LOG] Certificate notification for user {request.user_id} - cert #{request.certificate_number} for course '{request.course_title}' logged",
            notification_type=NotificationType.CERTIFICATE_ISSUED,
            channel=NotificationChannel.EMAIL,
        )

    # --- Progress Milestone Notifications ---

    async def notify_progress(self, request: ProgressNotificationRequest) -> NotificationResponse:
        """
        Handle progress milestone notification. Currently logs only.

        Triggered when: progress.module_completed event occurs.
        Future behavior: In-app notification for module completion.
        """
        logger.info(
            "progress_notification",
            event="module_completed",
            user_id=request.user_id,
            course_id=request.course_id,
            course_title=request.course_title,
            enrollment_id=request.enrollment_id,
            module_title=request.module_title,
            completion_percentage=request.completion_percentage,
            action="would_send_progress_in_app_notification",
            message=f"Module '{request.module_title}' completed! {request.completion_percentage}% done.",
        )

        return NotificationResponse(
            success=True,
            message=f"[LOG] Progress notification for user {request.user_id} - module '{request.module_title}' completed ({request.completion_percentage}%) in '{request.course_title}' logged",
            notification_type=NotificationType.MODULE_COMPLETED,
            channel=NotificationChannel.IN_APP,
        )

    # --- Private Channel Handlers (Stubs for Future) ---

    async def _send_email(self, to_user_id: int, subject: str, body: str) -> bool:
        """
        Stub: Send email notification.

        Future implementation:
        - Look up user email from User Service (via HTTP or cache)
        - Send via SMTP / SendGrid / AWS SES
        - Queue via Celery for reliability
        """
        logger.info(
            "email_stub",
            to_user_id=to_user_id,
            subject=subject,
            body_preview=body[:100],
            action="email_send_skipped_stub",
        )
        return True

    async def _send_push(self, to_user_id: int, title: str, body: str) -> bool:
        """
        Stub: Send push notification.

        Future implementation:
        - Look up user device tokens
        - Send via Firebase Cloud Messaging / APNs
        """
        logger.info(
            "push_stub",
            to_user_id=to_user_id,
            title=title,
            body_preview=body[:100],
            action="push_send_skipped_stub",
        )
        return True

    async def _send_sms(self, to_user_id: int, message: str) -> bool:
        """
        Stub: Send SMS notification.

        Future implementation:
        - Look up user phone number from User Service
        - Send via Twilio / AWS SNS
        """
        logger.info(
            "sms_stub",
            to_user_id=to_user_id,
            message_preview=message[:100],
            action="sms_send_skipped_stub",
        )
        return True
```

---

### 12. `src/notification_service/api/__init__.py`

```python
"""API route handlers for notification service."""
```

---

### 13. `src/notification_service/api/router.py`

Central router that includes all sub-routers, following the same pattern as user-service.

```python
from fastapi import APIRouter
from notification_service.api.notification import router as notification_router

router = APIRouter()
router.include_router(notification_router, prefix="/notifications", tags=["notifications"])
```

---

### 14. `src/notification_service/api/notification.py`

Route handlers. Each endpoint instantiates `NotificationService` and delegates.

Follow the same pattern as `user-service/api/auth.py` — read `X-User-ID` from the request headers (set by the API Gateway).

```python
from fastapi import APIRouter, Header, HTTPException

from notification_service.schemas.notification import (
    CertificateNotificationRequest,
    CourseNotificationRequest,
    EnrollmentNotificationRequest,
    NotificationResponse,
    ProgressNotificationRequest,
    SendNotificationRequest,
)
from notification_service.services.notification import NotificationService

router = APIRouter()
notification_service = NotificationService()


@router.post("/send", response_model=NotificationResponse)
async def send_notification(
    request: SendNotificationRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """Send a generic notification (logs only for now)."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID header")
    return await notification_service.send_notification(request)


@router.post("/enrollment", response_model=NotificationResponse)
async def notify_enrollment(
    request: EnrollmentNotificationRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """Handle enrollment notification (logs only for now)."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID header")
    return await notification_service.notify_enrollment(request)


@router.post("/course", response_model=NotificationResponse)
async def notify_course_event(
    request: CourseNotificationRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """Handle course event notification (logs only for now)."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID header")
    return await notification_service.notify_course_event(request)


@router.post("/certificate", response_model=NotificationResponse)
async def notify_certificate(
    request: CertificateNotificationRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """Handle certificate notification (logs only for now)."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID header")
    return await notification_service.notify_certificate(request)


@router.post("/progress", response_model=NotificationResponse)
async def notify_progress(
    request: ProgressNotificationRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """Handle progress milestone notification (logs only for now)."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID header")
    return await notification_service.notify_progress(request)
```

---

### 15. `src/notification_service/main.py`

FastAPI app entry point. **Follow the exact same pattern as user-service `main.py`**: lifespan context manager, include router, `/health` endpoint returning a dict.

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from notification_service.api.router import router
from notification_service.core.logging import get_logger, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    setup_logging()
    logger = get_logger("main")
    logger.info("notification_service_starting", port=8005)
    yield
    logger.info("notification_service_shutting_down")


app = FastAPI(
    title="SmartCourse Notification Service",
    description="Handles email, push, and in-app notifications for the SmartCourse platform",
    version="0.1.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "notification-service",
    }
```

**Note:** The health check returns a plain dict matching the user-service pattern (`{"status": "ok", "service": "notification-service"}`). No Pydantic response model needed — keep it simple.

---

## Docker Compose Integration

Add the following service block to the root `docker-compose.yml`, placed **after the `course-service` block and before the `auth-sidecar` block**. Follow the exact same structure as user-service/course-service.

```yaml
  notification-service:
    build:
      context: ./services/notification-service
      dockerfile: Dockerfile
    container_name: smartcourse-notification-service
    # No ports exposed to host — only accessible through API Gateway
    environment:
      - SERVICE_NAME=notification-service
      - SERVICE_PORT=8005
      - LOG_LEVEL=INFO
    networks:
      - smartcourse-network
```

**CRITICAL — follow existing patterns exactly:**
- **No `ports:` mapping** — the service is internal only, accessible ONLY through the API Gateway on the Docker network. This matches user-service and course-service which also have no port mappings.
- **No `depends_on`** for postgres, redis, or mongodb — this service has no DB/cache dependencies.
- **No `restart:` policy** — existing services (user-service, course-service) don't set one, so don't add one here either.
- **No `healthcheck:`** — existing services (user-service, course-service) don't define healthchecks in docker-compose (only infra services like postgres/redis do). The auth-sidecar is the exception because it's used by nginx `auth_request`.
- Container name follows the pattern: `smartcourse-notification-service` (prefix `smartcourse-`)
- Uses the same `smartcourse-network` network as all other services

Also update the `api-gateway` service to depend on notification-service:

```yaml
  api-gateway:
    build:
      context: ./services/api-gateway/nginx
      dockerfile: Dockerfile
    container_name: smartcourse-api-gateway
    ports:
      - "8000:8000"           # The ONLY port clients should access
    depends_on:
      - auth-sidecar
      - user-service
      - course-service
      - notification-service    # ← ADD THIS LINE
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:8000/health"]
      interval: 15s
      timeout: 5s
      retries: 3
    networks:
      - smartcourse-network
```

---

## API Gateway (Nginx) Integration

The API Gateway is the **ONLY** way to reach the notification service. Update the existing Nginx config files to route `/notifications/*` traffic.

### 1. Update `services/api-gateway/nginx/conf.d/upstreams.conf`

The notification-service upstream is **already commented out** in the existing file. Uncomment it and update to use the container name (matching the existing naming pattern where upstream servers use the `container_name` from docker-compose):

```nginx
# Notification service
upstream notification-service {
    server smartcourse-notification-service:8005;
    keepalive 32;
}
```

**Note:** The existing upstreams use `smartcourse-user-service:8001`, `smartcourse-course-service:8002`, etc. (container names, not docker-compose service names). Follow this exact pattern.

### 2. Update `services/api-gateway/nginx/nginx.conf` — Add location block

Add the notification service routes in the `server` block of `nginx.conf`, **after the course-service location blocks and before the `INTERNAL` auth-verify section**. Follow the exact same pattern as other protected routes:

```nginx
        # ==============================================================
        #  NOTIFICATION SERVICE — All routes protected by JWT
        # ==============================================================
        location /notifications/ {
            limit_req zone=api_general burst=20 nodelay;
            include /etc/nginx/conf.d/protected-snippet.conf;
            proxy_pass http://notification-service$request_uri;
            include /etc/nginx/conf.d/proxy-params.conf;
        }
```

**This ensures:**
- JWT is verified via `auth_request` to the auth-sidecar (from `protected-snippet.conf`)
- `X-User-ID` and `X-User-Role` headers are set on the forwarded request
- Rate limiting is applied (`api_general` zone, same as other protected routes)
- Standard proxy headers are included (`proxy-params.conf`)

---

## Event Mapping Reference

These are the events from other services that should eventually trigger notifications. For now, the HTTP endpoints serve as the trigger mechanism. In the future, these will be replaced/supplemented by Kafka consumers.

| Event                       | Source Service | Notification Action                           | Channel      |
| --------------------------- | -------------- | --------------------------------------------- | ------------ |
| `user.registered`           | User Service   | Welcome email                                 | Email        |
| `enrollment.created`        | Course Service | Enrollment confirmation + welcome              | Email, In-App |
| `enrollment.completed`      | Course Service | Course completion congratulations              | Email, In-App |
| `course.published`          | Course Service | Notify interested students                     | Email, Push  |
| `course.archived`           | Course Service | Notify enrolled students                       | Email        |
| `progress.module_completed` | Course Service | Module milestone notification                  | In-App       |
| `certificate.issued`        | Course Service | Certificate ready notification + download link | Email        |

---

## Key Conventions to Follow

These are **non-negotiable** — they match the existing codebase exactly.

### Code Conventions
1. **File naming:** No folder prefix — e.g., `services/notification.py` NOT `services/notification_service.py`
2. **Dependencies:** `pyproject.toml` only — **NO** `requirements.txt`. Use `setuptools.build_meta` as build backend.
3. **Package structure:** Source code under `src/notification_service/`
4. **Imports:** Use absolute imports (`from notification_service.schemas.notification import ...`)
5. **Schemas:** Pydantic v2 models for all request/response types
6. **Logging:** Use `structlog` with JSON output for all log entries
7. **No database:** This service does NOT connect to any database
8. **No authentication logic:** JWT is verified at the API Gateway; this service just reads `X-User-ID` header
9. **Async:** All service methods and route handlers should be `async`
10. **Error handling:** Return proper HTTP error codes (401 for missing auth, 422 for validation, 500 for internal errors)
11. **Line length:** 100 characters (matching ruff and black config of existing services)
12. **Config pattern:** Use `pydantic_settings.BaseSettings` with inner `class Config` (not `model_config` dict)

### Infrastructure Conventions
13. **NOT publicly accessible:** No port mapping in docker-compose. Service is only reachable within the `smartcourse-network` Docker network.
14. **Gateway is the ONLY entry point:** Clients access this service through `http://localhost:8000/notifications/*`. The gateway handles JWT verification.
15. **Container naming:** Use `smartcourse-notification-service` (matches `smartcourse-user-service`, `smartcourse-course-service` pattern)
16. **Dockerfile pattern:** Explicit `pip install` of each dependency for Docker layer caching, then `pip install -e .`, then set `PYTHONPATH=/app/src:/app`
17. **Nginx upstream naming:** Use container name `smartcourse-notification-service:8005` (not docker-compose service name)
18. **Protected routes:** All notification routes go through `protected-snippet.conf` which triggers JWT verification via auth-sidecar

---

## Testing the Service

Since the notification service is **NOT exposed to the public**, all testing goes through the **API Gateway on port 8000** with a valid JWT token.

### Step 1: Build and start the full stack

```bash
# Build and start everything (gateway + all services)
docker compose up --build -d

# Verify the notification service container is running
docker compose ps notification-service

# Check notification service logs
docker compose logs notification-service
```

### Step 2: Get a JWT token (required for all protected endpoints)

```bash
# Register a test user (public endpoint)
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "username": "testuser",
    "password": "TestPass123!",
    "first_name": "Test",
    "last_name": "User"
  }'

# Login to get a JWT token (public endpoint)
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "TestPass123!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

### Step 3: Test notification endpoints through the gateway

All requests go through `localhost:8000` (the gateway), which verifies JWT and sets `X-User-ID` automatically.

```bash
# Test generic notification
curl -X POST http://localhost:8000/notifications/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "user_id": 42,
    "type": "generic",
    "channel": "email",
    "priority": "normal",
    "title": "Test Notification",
    "message": "This is a test notification"
  }'

# Test enrollment notification
curl -X POST http://localhost:8000/notifications/enrollment \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "user_id": 42,
    "course_id": 1,
    "course_title": "Python Basics",
    "enrollment_id": 101,
    "instructor_name": "John Doe"
  }'

# Test certificate notification
curl -X POST http://localhost:8000/notifications/certificate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "user_id": 42,
    "course_id": 1,
    "course_title": "Python Basics",
    "certificate_id": 10,
    "certificate_number": "CERT-2026-001",
    "verification_code": "ABC123XYZ"
  }'

# Test progress notification
curl -X POST http://localhost:8000/notifications/progress \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "user_id": 42,
    "course_id": 1,
    "course_title": "Python Basics",
    "enrollment_id": 101,
    "module_title": "Variables & Data Types",
    "completion_percentage": 35.5
  }'

# Check structured JSON logs
docker compose logs notification-service
```

### Step 4: Verify gateway routing

```bash
# This should return 401 Unauthorized (no JWT)
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/notifications/send

# This should return 404 (direct access not possible — no ports exposed)
curl -s -o /dev/null -w "%{http_code}" http://localhost:8005/health
# ↑ Expected: connection refused (port not mapped to host)
```

All endpoints should return `200 OK` with a `NotificationResponse` JSON body when accessed through the gateway with a valid JWT. The service logs should show structured JSON entries describing what notification _would_ have been sent.

---

## Future Enhancements (Out of Scope for Now)

These are planned but **NOT** part of this implementation:

1. **Email sending** — SMTP/SendGrid/AWS SES integration in `_send_email()`
2. **Push notifications** — Firebase Cloud Messaging in `_send_push()`
3. **SMS notifications** — Twilio/AWS SNS in `_send_sms()`
4. **Kafka consumers** — Consume events directly from Kafka topics instead of HTTP endpoints
5. **Celery task queue** — Queue email/SMS sends via Celery + RabbitMQ for reliability and retry
6. **Template engine** — Jinja2 templates for email HTML bodies
7. **User preference lookup** — HTTP call to User Service to get email/phone for a user_id
8. **Notification preferences** — Allow users to opt-in/out of notification channels
9. **Rate limiting** — Prevent notification floods (e.g., max 5 emails/hour per user)
10. **Dead letter queue** — Handle failed notification deliveries

---

_Document Version: 1.1 | Updated: February 13, 2026_  
_v1.1: Aligned all patterns (Dockerfile, pyproject.toml, config, docker-compose, nginx) with existing infrastructure. Service is internal-only behind API Gateway._
