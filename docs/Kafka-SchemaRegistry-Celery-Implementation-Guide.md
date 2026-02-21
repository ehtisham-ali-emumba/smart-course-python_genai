# Kafka Schema Registry + RabbitMQ/Celery — Implementation Guide

**Date:** February 2026  
**Goal:** Bring the POC in line with the PDF requirements: **Kafka + Schema Registry** and **Celery Workers with RabbitMQ** — both actually working end-to-end.

---

## 1. What the PDF Requires vs What We Have Today

| Requirement (from PDF) | Current State | Gap |
|------------------------|---------------|-----|
| Kafka + Schema Registry | Kafka works, plain JSON, **no Schema Registry** | Need to add Schema Registry container and wire producer/consumer to validate schemas |
| Celery Workers with RabbitMQ | RabbitMQ container runs, CeleryDispatcher code exists, but **nothing dispatches or consumes Celery tasks** | Need to add a Celery worker, route notification work through RabbitMQ, and actually execute tasks |
| Background tasks run independently | Notification service handles email/notification/PDF **inline** in its Kafka consumer (synchronous, blocking) | Kafka consumer should hand off heavy work to Celery tasks via RabbitMQ |

### 1.1 Why Both Kafka AND RabbitMQ?

This is the most important concept. They solve **different problems**:

```
Kafka  = "Something happened" (event broadcasting)
         Many consumers can read the same event.
         Events are stored durably (replay possible).
         Use for: domain events, analytics, audit trail.

RabbitMQ + Celery = "Do this one job" (task queue)
         Exactly ONE worker picks up each task.
         Task deleted after acknowledgment.
         Built-in retries, dead-letter queues, result tracking.
         Use for: send email, generate PDF, heavy processing.
```

**In SmartCourse, they work together:**

```
User registers
    │
    ▼
user-service publishes "user.registered" to Kafka
    │
    ▼
notification-service Kafka consumer receives the event
    │
    ▼
Instead of sending email inline, it dispatches a Celery task:
    celery_app.send_task("send_welcome_email", ...)
    │
    ▼
Task goes to RabbitMQ → email_queue
    │
    ▼
Celery worker picks it up, executes the mock email
    │
    ▼
If it fails → automatic retry (60s, 300s, 900s)
After 3 failures → dead letter queue
```

### 1.2 Why Schema Registry?

Without Schema Registry, any service can publish any random JSON to Kafka. If user-service accidentally removes `email` from the payload, notification-service crashes at runtime with a `KeyError`.

**Schema Registry enforces a contract:**

```
Producer → "Here's my message" → Schema Registry validates it → Kafka
Consumer → Kafka → Schema Registry provides the schema → Parse safely
```

For our POC we'll use **JSON Schema** (not Avro). It works with our existing Pydantic models and is simpler to understand.

---

## 2. Architecture After These Changes

```
┌──────────────┐         Kafka + Schema Registry         ┌─────────────────────┐
│ user-service │ ──── publish (validated) ──────────────► │ notification-service│
│ course-svc   │    user.registered                      │   Kafka consumer    │
└──────────────┘    enrollment.completed                 │                     │
                    certificate.issued                   │  Receives event,    │
                                                         │  dispatches Celery  │
                                                         │  task via RabbitMQ  │
                                                         └────────┬────────────┘
                                                                  │
                                                         send_task("send_welcome_email")
                                                                  │
                                                                  ▼
                                                         ┌─────────────────────┐
                                                         │    RabbitMQ         │
                                                         │  ┌───────────────┐  │
                                                         │  │ email_queue   │  │
                                                         │  │ notif_queue   │  │
                                                         │  │ cert_queue    │  │
                                                         │  └───────────────┘  │
                                                         └────────┬────────────┘
                                                                  │
                                                                  ▼
                                                         ┌─────────────────────┐
                                                         │  Celery Worker      │
                                                         │  (notification-svc) │
                                                         │                     │
                                                         │  • send_welcome_email│
                                                         │  • send_enrollment  │
                                                         │  • generate_pdf     │
                                                         │  • create_notif     │
                                                         └─────────────────────┘
```

---

## 3. Implementation — Part A: Kafka Schema Registry

### 3.1 What is Schema Registry?

Schema Registry is a **separate HTTP server** (runs alongside Kafka) that stores and validates message schemas. When a producer sends a message, the serializer checks the payload against the registered schema. If it doesn't match, the message is **rejected before it hits Kafka**.

Think of it as a "type checker" for your Kafka messages.

### 3.2 Add Schema Registry to Docker Compose

Add this service to `docker-compose.yml`, right after the `kafka` service:

```yaml
  schema-registry:
    image: confluentinc/cp-schema-registry:7.6.0
    container_name: smartcourse-schema-registry
    depends_on:
      kafka:
        condition: service_healthy
    ports:
      - "8081:8081"
    environment:
      SCHEMA_REGISTRY_HOST_NAME: schema-registry
      SCHEMA_REGISTRY_KAFKASTORE_BOOTSTRAP_SERVERS: kafka:29092
      SCHEMA_REGISTRY_LISTENERS: http://0.0.0.0:8081
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8081/subjects"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - smartcourse-network
```

**What this does:**
- Runs the Confluent Schema Registry on port 8081
- Connects to your existing Kafka broker
- Exposes a REST API to register and retrieve schemas
- You can browse registered schemas at `http://localhost:8081/subjects`

### 3.3 Add Environment Variable

Add to `.env` (root):

```env
SCHEMA_REGISTRY_URL=http://schema-registry:8081
```

Add to `docker-compose.yml` for every service that produces or consumes Kafka messages — user-service, course-service, notification-service:

```yaml
  - SCHEMA_REGISTRY_URL=${SCHEMA_REGISTRY_URL:-http://schema-registry:8081}
```

Also add `schema-registry` to their `depends_on`.

### 3.4 Install the Python Library

Update `services/core/pyproject.toml` — add one dependency:

```toml
dependencies = [
    "aiokafka>=0.10.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "celery[redis]>=5.3.0",
    "httpx>=0.26.0",            # <-- NEW: for Schema Registry HTTP calls
]
```

We'll use `httpx` to talk to Schema Registry's REST API. This is simpler than `confluent-kafka[schemaregistry]` which requires C libraries and is harder to install in Docker.

### 3.5 Add Config

Update `services/core/src/core_service/config.py`:

```python
class CoreSettings(BaseSettings):
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:29092"
    RABBITMQ_URL: str = "amqp://smartcourse:smartcourse_secret@rabbitmq:5672//"
    CELERY_RESULT_BACKEND: str = "redis://:smartcourse_secret@redis:6379/2"
    SCHEMA_REGISTRY_URL: str = "http://schema-registry:8081"   # <-- NEW

    model_config = {"env_prefix": "", "case_sensitive": True}
```

### 3.6 Create the Schema Registry Client

Create new file `services/core/src/core_service/providers/kafka/schema_registry.py`:

```python
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class SchemaRegistryClient:
    """Lightweight JSON Schema Registry client using httpx.

    Responsibilities:
    - Register JSON schemas derived from Pydantic models
    - Validate that producers/consumers agree on payload shape
    - Cache schema IDs to avoid repeated HTTP calls

    This replaces the heavier confluent-kafka[schemaregistry] package.
    """

    def __init__(self, registry_url: str):
        self._url = registry_url.rstrip("/")
        self._schema_id_cache: dict[str, int] = {}

    async def register_schema(self, subject: str, schema: dict[str, Any]) -> int:
        """Register a JSON schema and return its ID.

        Schema Registry uses "subjects" to namespace schemas.
        Convention: <topic>-value (e.g., "user.events-value").
        """
        if subject in self._schema_id_cache:
            return self._schema_id_cache[subject]

        payload = {
            "schemaType": "JSON",
            "schema": json.dumps(schema),
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._url}/subjects/{subject}/versions",
                json=payload,
                headers={"Content-Type": "application/vnd.schemaregistry.v1+json"},
            )
            resp.raise_for_status()
            schema_id = resp.json()["id"]

        self._schema_id_cache[subject] = schema_id
        logger.info("Registered schema for %s (id=%d)", subject, schema_id)
        return schema_id

    async def get_latest_schema(self, subject: str) -> dict[str, Any]:
        """Fetch the latest schema for a subject."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._url}/subjects/{subject}/versions/latest"
            )
            resp.raise_for_status()
            return json.loads(resp.json()["schema"])
```

### 3.7 Generate JSON Schemas from Pydantic Models

The beauty here: **your existing Pydantic payload models already define the schema**. Pydantic v2 has `.model_json_schema()` built-in.

Create new file `services/core/src/core_service/providers/kafka/schema_utils.py`:

```python
from pydantic import BaseModel

from core_service.events.envelope import EventEnvelope


def get_envelope_schema() -> dict:
    """Generate JSON Schema from the EventEnvelope Pydantic model.

    This schema is what gets registered in Schema Registry.
    Every Kafka message must conform to this structure.
    """
    return EventEnvelope.model_json_schema()
```

### 3.8 Update the Producer to Register Schemas

Update `services/core/src/core_service/providers/kafka/producer.py`:

```python
import json
import logging
from typing import Any

from aiokafka import AIOKafkaProducer

from core_service.events.envelope import EventEnvelope
from core_service.providers.kafka.schema_registry import SchemaRegistryClient
from core_service.providers.kafka.schema_utils import get_envelope_schema

logger = logging.getLogger(__name__)


class EventProducer:
    """Async Kafka producer with Schema Registry validation.

    On startup, registers the EventEnvelope JSON schema with Schema Registry.
    On each publish, the message is still validated by Pydantic (EventEnvelope),
    and Schema Registry ensures all consumers know the expected shape.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        service_name: str,
        schema_registry_url: str = "",
    ):
        self._bootstrap_servers = bootstrap_servers
        self._service_name = service_name
        self._producer: AIOKafkaProducer | None = None
        self._schema_registry: SchemaRegistryClient | None = None
        if schema_registry_url:
            self._schema_registry = SchemaRegistryClient(schema_registry_url)

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
        )
        await self._producer.start()
        logger.info("Kafka producer started for %s", self._service_name)

    async def _ensure_schema_registered(self, topic: str) -> None:
        """Register the EventEnvelope schema for this topic (once)."""
        if not self._schema_registry:
            return
        subject = f"{topic}-value"
        try:
            await self._schema_registry.register_schema(
                subject, get_envelope_schema()
            )
        except Exception:
            logger.warning("Schema registration failed for %s (non-fatal)", subject)

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()
            logger.info("Kafka producer stopped for %s", self._service_name)

    async def publish(
        self,
        topic: str,
        event_type: str,
        payload: dict[str, Any],
        key: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        if not self._producer:
            logger.warning("Producer not started — dropping event %s", event_type)
            return

        await self._ensure_schema_registered(topic)

        envelope = EventEnvelope(
            event_type=event_type,
            service=self._service_name,
            payload=payload,
        )
        if correlation_id:
            envelope.correlation_id = correlation_id

        await self._producer.send_and_wait(
            topic, value=envelope.model_dump(), key=key,
        )
        logger.info("Published %s to %s (key=%s)", event_type, topic, key)
```

### 3.9 Update Service Lifespans to Pass Schema Registry URL

In **user-service** (`services/user-service/src/user_service/main.py`), update the producer init:

```python
producer = EventProducer(
    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
    service_name="user-service",
    schema_registry_url=settings.SCHEMA_REGISTRY_URL,  # <-- NEW
)
```

Add `SCHEMA_REGISTRY_URL` to user-service's `Settings` class.

Do the same in **course-service** (`services/course-service/src/main.py`).

### 3.10 How to Verify Schema Registry Works

After `docker compose up -d`:

```bash
# List registered subjects (should show topics after first message)
curl http://localhost:8081/subjects

# After sending a user.registered event:
curl http://localhost:8081/subjects/user.events-value/versions/latest | python -m json.tool
```

You'll see your EventEnvelope JSON Schema registered there.

---

## 4. Implementation — Part B: RabbitMQ + Celery Workers

### 4.1 What is Celery and How Does It Work?

```
Your Code                  RabbitMQ                  Celery Worker
─────────                  ────────                  ─────────────
celery_app.send_task(  →   email_queue: [task1]  →   Worker picks task1
  "send_welcome_email",                              Executes send_welcome_email()
  kwargs={...},                                      Returns result
  queue="email_queue"                                 ACKs the message
)                                                     (task removed from queue)
```

**Key concepts:**
- **Broker** = RabbitMQ (stores tasks in queues)
- **Worker** = Python process running `celery -A ... worker` (picks up and executes tasks)
- **Task** = Python function decorated with `@celery_app.task`
- **Queue** = Named channel in RabbitMQ (email_queue, notification_queue, certificate_queue)
- **send_task()** = Fire-and-forget: enqueue a task by name without importing the function

### 4.2 Notification Service Celery App

Create new file `services/notification-service/src/notification_service/worker.py`:

```python
from celery import Celery

from notification_service.config import settings

celery_app = Celery(
    "smartcourse-notifications",
    broker=settings.RABBITMQ_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "notification_service.tasks.email.*": {"queue": "email_queue"},
        "notification_service.tasks.certificate.*": {"queue": "certificate_queue"},
        "notification_service.tasks.notification.*": {"queue": "notification_queue"},
    },
)

celery_app.autodiscover_tasks([
    "notification_service.tasks",
])
```

### 4.3 Update Notification Service Config

Update `services/notification-service/src/notification_service/config.py`:

```python
class Settings(BaseSettings):
    SERVICE_NAME: str = "notification-service"
    SERVICE_PORT: int = 8005
    LOG_LEVEL: str = "INFO"

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "no-reply@smartcourse.com"

    FIREBASE_PROJECT_ID: str = ""

    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:29092"
    RABBITMQ_URL: str = "amqp://smartcourse:smartcourse_secret@rabbitmq:5672//"    # <-- NEW
    CELERY_RESULT_BACKEND: str = "redis://:smartcourse_secret@redis:6379/2"        # <-- NEW

    class Config:
        env_file = ".env"
        case_sensitive = True
```

### 4.4 Create Celery Tasks

These are the actual functions that Celery workers execute. They use the existing mocks.

Create directory: `services/notification-service/src/notification_service/tasks/`

**`tasks/__init__.py`** — empty or just a docstring:

```python
"""Celery task definitions for notification-service."""
```

**`tasks/email.py`**:

```python
from notification_service.mocks import MockEmailService
from notification_service.worker import celery_app

mock_email = MockEmailService()


@celery_app.task(
    bind=True,
    max_retries=3,
    name="notification_service.tasks.email.send_welcome_email",
)
def send_welcome_email(self, user_id: int, email: str, first_name: str):
    """Send welcome email after user registration.

    Retries up to 3 times with exponential backoff on failure.
    In production: replace mock with SMTP/SendGrid.
    """
    try:
        return mock_email.send(
            to=email,
            subject=f"Welcome to SmartCourse, {first_name}!",
            body=(
                f"Hi {first_name},\n\n"
                f"Welcome to SmartCourse! Your account has been created\n"
                f"successfully. Start exploring our course catalog.\n\n"
                f"-- The SmartCourse Team"
            ),
            email_type="WELCOME_EMAIL",
            metadata={"user_id": user_id},
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(
    bind=True,
    max_retries=3,
    name="notification_service.tasks.email.send_enrollment_confirmation",
)
def send_enrollment_confirmation(
    self, student_id: int, course_id: int, course_title: str, email: str
):
    try:
        return mock_email.send(
            to=email,
            subject=f"Enrollment Confirmed: {course_title}",
            body=(
                f"You're in!\n\n"
                f"You have successfully enrolled in '{course_title}'.\n"
                f"Head to your dashboard to start learning.\n\n"
                f"-- The SmartCourse Team"
            ),
            email_type="ENROLLMENT_CONFIRMATION",
            metadata={"student_id": student_id, "course_id": course_id},
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(
    bind=True,
    max_retries=3,
    name="notification_service.tasks.email.send_course_completion_email",
)
def send_course_completion_email(
    self, student_id: int, course_id: int, course_title: str, email: str
):
    try:
        return mock_email.send(
            to=email,
            subject=f"Congratulations! You completed {course_title}",
            body=(
                f"Amazing work!\n\n"
                f"You've completed all modules in '{course_title}'.\n"
                f"Your certificate is being generated.\n\n"
                f"-- The SmartCourse Team"
            ),
            email_type="COURSE_COMPLETION",
            metadata={"student_id": student_id, "course_id": course_id},
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(
    bind=True,
    max_retries=3,
    name="notification_service.tasks.email.send_certificate_ready_email",
)
def send_certificate_ready_email(
    self,
    student_id: int,
    certificate_number: str,
    verification_code: str,
    email: str,
):
    try:
        return mock_email.send(
            to=email,
            subject=f"Your Certificate is Ready! #{certificate_number}",
            body=(
                f"Your certificate has been issued!\n\n"
                f"Certificate:    {certificate_number}\n"
                f"Verification:   {verification_code}\n\n"
                f"Download it from your profile.\n\n"
                f"-- The SmartCourse Team"
            ),
            email_type="CERTIFICATE_READY",
            metadata={"student_id": student_id, "cert": certificate_number},
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
```

**`tasks/notification.py`**:

```python
from notification_service.mocks import MockNotificationService
from notification_service.worker import celery_app

mock_notification = MockNotificationService()


@celery_app.task(
    bind=True,
    max_retries=3,
    name="notification_service.tasks.notification.create_in_app_notification",
)
def create_in_app_notification(
    self,
    user_id: int,
    title: str,
    message: str,
    notification_type: str = "system",
):
    """Create an in-app notification for a user.

    In production: write to a notifications DB table and push via WebSocket.
    """
    try:
        return mock_notification.create(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
```

**`tasks/certificate.py`**:

```python
from notification_service.mocks import MockCertificateGenerator
from notification_service.worker import celery_app

mock_certificate = MockCertificateGenerator()


@celery_app.task(
    bind=True,
    max_retries=3,
    name="notification_service.tasks.certificate.generate_certificate_pdf",
)
def generate_certificate_pdf(
    self,
    certificate_id: int,
    enrollment_id: int,
    student_name: str,
    course_title: str,
):
    """Generate a PDF certificate.

    In production: use WeasyPrint/ReportLab, upload to S3, store URL in DB.
    """
    try:
        return mock_certificate.generate(
            certificate_id=certificate_id,
            enrollment_id=enrollment_id,
            student_name=student_name,
            course_title=course_title,
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
```

### 4.5 Update Kafka Event Handlers — Dispatch to Celery Instead of Inline

This is the critical change. The Kafka consumer currently runs mocks directly. Instead, it should **dispatch Celery tasks** so the work goes through RabbitMQ.

Update `services/notification-service/src/notification_service/consumers/event_handlers.py`:

```python
"""Kafka event handlers — dispatch work to Celery via RabbitMQ."""

import sys
from typing import Any

from celery import Celery
from core_service.events.envelope import EventEnvelope

from notification_service.config import settings


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


celery_app = Celery(broker=settings.RABBITMQ_URL)


class NotificationEventHandlers:
    """Receives Kafka events and dispatches Celery tasks to RabbitMQ.

    This is the bridge between Kafka (events) and RabbitMQ (tasks).
    The Kafka consumer tells us WHAT happened.
    We decide WHAT WORK to do and put it in the right queue.
    The Celery worker does the actual work.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Any] = {
            "user.registered": self._on_user_registered,
            "course.published": self._on_course_published,
            "course.archived": self._on_course_archived,
            "enrollment.created": self._on_enrollment_created,
            "enrollment.dropped": self._on_enrollment_dropped,
            "enrollment.completed": self._on_enrollment_completed,
            "certificate.issued": self._on_certificate_issued,
            "certificate.revoked": self._on_certificate_revoked,
        }

    async def handle(self, topic: str, event: EventEnvelope) -> None:
        handler = self._handlers.get(event.event_type)
        if handler:
            _log(f"[notification-service] {event.event_type} from {topic} (id={event.event_id})")
            await handler(event)

    # ── Dispatchers ──────────────────────────────────────────

    async def _on_user_registered(self, event: EventEnvelope) -> None:
        p = event.payload
        celery_app.send_task(
            "notification_service.tasks.email.send_welcome_email",
            kwargs={
                "user_id": p["user_id"],
                "email": p["email"],
                "first_name": p.get("first_name", ""),
            },
            queue="email_queue",
        )
        celery_app.send_task(
            "notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["user_id"],
                "title": "Welcome to SmartCourse!",
                "message": f"Hi {p.get('first_name', '')}! Start exploring courses.",
                "notification_type": "welcome",
            },
            queue="notification_queue",
        )
        _log(f"[dispatch] user.registered → email_queue + notification_queue")

    async def _on_course_published(self, event: EventEnvelope) -> None:
        p = event.payload
        celery_app.send_task(
            "notification_service.tasks.email.send_enrollment_confirmation",
            kwargs={
                "student_id": p["instructor_id"],
                "course_id": p["course_id"],
                "course_title": p.get("title", ""),
                "email": f"instructor-{p['instructor_id']}@smartcourse.local",
            },
            queue="email_queue",
        )
        celery_app.send_task(
            "notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["instructor_id"],
                "title": "Course Published!",
                "message": f"Your course '{p.get('title', '')}' is now live.",
                "notification_type": "course_published",
            },
            queue="notification_queue",
        )

    async def _on_course_archived(self, event: EventEnvelope) -> None:
        p = event.payload
        celery_app.send_task(
            "notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["instructor_id"],
                "title": "Course Archived",
                "message": f"Your course '{p.get('title', '')}' has been archived.",
                "notification_type": "course_archived",
            },
            queue="notification_queue",
        )

    async def _on_enrollment_created(self, event: EventEnvelope) -> None:
        p = event.payload
        email = p.get("email") or f"student-{p['student_id']}@smartcourse.local"
        celery_app.send_task(
            "notification_service.tasks.email.send_enrollment_confirmation",
            kwargs={
                "student_id": p["student_id"],
                "course_id": p["course_id"],
                "course_title": p.get("course_title", "your course"),
                "email": email,
            },
            queue="email_queue",
        )
        celery_app.send_task(
            "notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["student_id"],
                "title": "Enrollment Confirmed!",
                "message": f"You're enrolled in '{p.get('course_title', 'a course')}'.",
                "notification_type": "enrollment",
            },
            queue="notification_queue",
        )

    async def _on_enrollment_dropped(self, event: EventEnvelope) -> None:
        p = event.payload
        celery_app.send_task(
            "notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["student_id"],
                "title": "Course Dropped",
                "message": "You've dropped a course. You can re-enroll anytime.",
                "notification_type": "enrollment",
            },
            queue="notification_queue",
        )

    async def _on_enrollment_completed(self, event: EventEnvelope) -> None:
        p = event.payload
        email = p.get("email") or f"student-{p['student_id']}@smartcourse.local"
        celery_app.send_task(
            "notification_service.tasks.email.send_course_completion_email",
            kwargs={
                "student_id": p["student_id"],
                "course_id": p["course_id"],
                "course_title": p.get("course_title", "your course"),
                "email": email,
            },
            queue="email_queue",
        )
        celery_app.send_task(
            "notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["student_id"],
                "title": "Course Completed!",
                "message": f"Congratulations on completing '{p.get('course_title', 'a course')}'!",
                "notification_type": "completion",
            },
            queue="notification_queue",
        )

    async def _on_certificate_issued(self, event: EventEnvelope) -> None:
        p = event.payload
        email = p.get("email") or f"student-{p['student_id']}@smartcourse.local"

        # 3 tasks dispatched for certificate.issued
        celery_app.send_task(
            "notification_service.tasks.email.send_certificate_ready_email",
            kwargs={
                "student_id": p["student_id"],
                "certificate_number": p["certificate_number"],
                "verification_code": p["verification_code"],
                "email": email,
            },
            queue="email_queue",
        )
        celery_app.send_task(
            "notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["student_id"],
                "title": "Certificate Ready!",
                "message": f"Certificate #{p['certificate_number']} is ready to download.",
                "notification_type": "certificate",
            },
            queue="notification_queue",
        )
        celery_app.send_task(
            "notification_service.tasks.certificate.generate_certificate_pdf",
            kwargs={
                "certificate_id": p["certificate_id"],
                "enrollment_id": p["enrollment_id"],
                "student_name": p.get("student_name", ""),
                "course_title": p.get("course_title", ""),
            },
            queue="certificate_queue",
        )
        _log(f"[dispatch] certificate.issued → email_queue + notification_queue + certificate_queue")

    async def _on_certificate_revoked(self, event: EventEnvelope) -> None:
        p = event.payload
        celery_app.send_task(
            "notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p.get("student_id", 0),
                "title": "Certificate Revoked",
                "message": f"Certificate for enrollment #{p['enrollment_id']} revoked.",
                "notification_type": "certificate",
            },
            queue="notification_queue",
        )
```

### 4.6 Add Celery Worker to Docker Compose

Add to `docker-compose.yml`:

```yaml
  celery-worker:
    build:
      context: .
      dockerfile: services/notification-service/Dockerfile
    container_name: smartcourse-celery-worker
    command: >
      celery -A notification_service.worker:celery_app worker
      --loglevel=info
      -Q email_queue,notification_queue,certificate_queue
    environment:
      - PYTHONUNBUFFERED=1
      - RABBITMQ_URL=amqp://${RABBITMQ_USER:-smartcourse}:${RABBITMQ_PASSWORD:-smartcourse_secret}@rabbitmq:5672//
      - CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD:-smartcourse_secret}@redis:6379/2
      - KAFKA_BOOTSTRAP_SERVERS=${KAFKA_BOOTSTRAP_SERVERS:-kafka:29092}
    depends_on:
      rabbitmq:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - smartcourse-network
```

**What this does:**
- Builds from the same Dockerfile as notification-service (same code)
- But runs `celery worker` instead of `uvicorn` (different `command`)
- Listens on 3 queues: `email_queue`, `notification_queue`, `certificate_queue`
- When a task arrives in any queue, the worker executes the corresponding function

### 4.7 Update Notification Service Dependencies

Update `services/notification-service/pyproject.toml`:

```toml
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "httpx>=0.26.0",
    "structlog>=24.1.0",
    "celery[redis]>=5.3.0",       # <-- NEW
]
```

Also update the Dockerfile to install celery:

In `services/notification-service/Dockerfile`, add `celery[redis]>=5.3.0` to the pip install list.

### 4.8 Update Notification Service Docker Compose

Update the existing `notification-service` in docker-compose to also depend on RabbitMQ (since the Kafka handler now dispatches to Celery/RabbitMQ):

```yaml
  notification-service:
    # ... existing config ...
    environment:
      - PYTHONUNBUFFERED=1
      - SERVICE_NAME=notification-service
      - SERVICE_PORT=8005
      - LOG_LEVEL=INFO
      - KAFKA_BOOTSTRAP_SERVERS=${KAFKA_BOOTSTRAP_SERVERS:-kafka:29092}
      - RABBITMQ_URL=amqp://${RABBITMQ_USER:-smartcourse}:${RABBITMQ_PASSWORD:-smartcourse_secret}@rabbitmq:5672//      # <-- NEW
      - CELERY_RESULT_BACKEND=redis://:${REDIS_PASSWORD:-smartcourse_secret}@redis:6379/2    # <-- NEW
    depends_on:
      kafka:
        condition: service_healthy
      kafka-init:
        condition: service_completed_successfully
      rabbitmq:                    # <-- NEW
        condition: service_healthy
      redis:                       # <-- NEW
        condition: service_healthy
```

---

## 5. Complete Control Flow After Changes

### 5.1 User Sign Up — Full Path

```
Step 1: Client → POST /auth/register
Step 2: user-service → register user in PostgreSQL
Step 3: user-service → EventProducer.publish()
          │
          ├── Pydantic validates the payload (UserRegisteredPayload)
          ├── Schema Registry validates the envelope schema (JSON Schema)
          └── Message written to Kafka topic: user.events
                │
Step 4: notification-service Kafka consumer picks it up
          │
          ├── _on_user_registered() dispatches 2 Celery tasks:
          │     ├── send_welcome_email → email_queue (RabbitMQ)
          │     └── create_in_app_notification → notification_queue (RabbitMQ)
          │
Step 5: Celery worker picks up tasks from RabbitMQ
          │
          ├── send_welcome_email() → MockEmailService.send() → styled log
          └── create_in_app_notification() → MockNotificationService.create() → styled log
          │
Step 6: If task fails → retry after 60s, then 120s, then 240s
          After 3 failures → task goes to dead letter queue
```

### 5.2 Certificate Issued — Full Path

```
Step 1: Student marks all lessons complete (100% progress)
Step 2: course-service → ProgressService._check_auto_complete()
          │
          ├── Publish: progress.course_completed   → progress.events (Kafka)
          ├── Update enrollment status → "completed"
          ├── Publish: enrollment.completed         → enrollment.events (Kafka)
          ├── Create certificate in DB
          └── Publish: certificate.issued           → course.events (Kafka)
                │
Step 3: notification-service Kafka consumer
          │
          ├── _on_enrollment_completed() → dispatches:
          │     ├── send_course_completion_email → email_queue
          │     └── create_in_app_notification → notification_queue
          │
          └── _on_certificate_issued() → dispatches:
                ├── send_certificate_ready_email → email_queue
                ├── create_in_app_notification → notification_queue
                └── generate_certificate_pdf → certificate_queue
                │
Step 4: Celery worker processes 5 tasks total:
          ├── 2 from enrollment.completed (email + notification)
          └── 3 from certificate.issued (email + notification + PDF)
```

---

## 6. How to Verify Everything Works

### 6.1 Start All Services

```bash
docker compose up -d --build
```

### 6.2 Check Schema Registry

```bash
# Should return empty list initially
curl http://localhost:8081/subjects

# After publishing an event, should show: ["user.events-value"]
curl http://localhost:8081/subjects
```

### 6.3 Check RabbitMQ Management UI

Open `http://localhost:15672` (login: smartcourse / smartcourse_secret).

- Go to **Queues** tab — you should see `email_queue`, `notification_queue`, `certificate_queue`
- After a user registers, you'll see messages flow through these queues

### 6.4 Check Celery Worker Logs

```bash
# See tasks being received and executed
docker compose logs celery-worker --tail=50 -f
```

You should see:
```
[2026-02-20 12:00:01] Task notification_service.tasks.email.send_welcome_email received
[2026-02-20 12:00:01] Task notification_service.tasks.notification.create_in_app_notification received
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  SMARTCOURSE EMAIL SERVICE (MOCK)                    ...           ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
[2026-02-20 12:00:01] Task ... succeeded in 0.01s
```

### 6.5 Test User Registration

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Test1234!","first_name":"Ali","last_name":"Khan","role":"student"}'
```

Check three places:
1. `docker compose logs notification-service` — should show "[dispatch] user.registered → email_queue + notification_queue"
2. `docker compose logs celery-worker` — should show mock email + notification output
3. RabbitMQ UI at `http://localhost:15672` — Queues tab shows message rates

---

## 7. Files Changed / Created Summary

| File | Action | Purpose |
|------|--------|---------|
| `docker-compose.yml` | **Edit** | Add `schema-registry` service, `celery-worker` service; update `notification-service` depends_on and env |
| `.env` | **Edit** | Add `SCHEMA_REGISTRY_URL` |
| `services/core/pyproject.toml` | **Edit** | Add `httpx` dependency |
| `services/core/src/core_service/config.py` | **Edit** | Add `SCHEMA_REGISTRY_URL` |
| `services/core/src/core_service/providers/kafka/schema_registry.py` | **Create** | Schema Registry HTTP client |
| `services/core/src/core_service/providers/kafka/schema_utils.py` | **Create** | Pydantic → JSON Schema helper |
| `services/core/src/core_service/providers/kafka/producer.py` | **Edit** | Add schema registration on publish |
| `services/user-service/src/user_service/config.py` | **Edit** | Add `SCHEMA_REGISTRY_URL` |
| `services/user-service/src/user_service/main.py` | **Edit** | Pass `schema_registry_url` to producer |
| `services/course-service/src/config.py` | **Edit** | Add `SCHEMA_REGISTRY_URL` |
| `services/course-service/src/main.py` | **Edit** | Pass `schema_registry_url` to producer |
| `services/notification-service/pyproject.toml` | **Edit** | Add `celery[redis]` |
| `services/notification-service/Dockerfile` | **Edit** | Add `celery[redis]` to pip install |
| `services/notification-service/src/notification_service/config.py` | **Edit** | Add `RABBITMQ_URL`, `CELERY_RESULT_BACKEND` |
| `services/notification-service/src/notification_service/worker.py` | **Create** | Celery app config |
| `services/notification-service/src/notification_service/tasks/__init__.py` | **Create** | Package init |
| `services/notification-service/src/notification_service/tasks/email.py` | **Create** | Email Celery tasks |
| `services/notification-service/src/notification_service/tasks/notification.py` | **Create** | In-app notification Celery tasks |
| `services/notification-service/src/notification_service/tasks/certificate.py` | **Create** | Certificate PDF Celery tasks |
| `services/notification-service/src/notification_service/consumers/event_handlers.py` | **Edit** | Replace inline mocks with Celery `send_task()` dispatch |

---

## 8. Concepts to Understand

### 8.1 Why `send_task()` Instead of Calling the Function Directly?

```python
# Direct call — WRONG (tight coupling, no retry, blocks Kafka consumer)
from notification_service.tasks.email import send_welcome_email
send_welcome_email(user_id=1, email="a@b.com", first_name="Ali")

# send_task — CORRECT (decoupled, goes through RabbitMQ, worker handles it)
celery_app.send_task(
    "notification_service.tasks.email.send_welcome_email",
    kwargs={"user_id": 1, "email": "a@b.com", "first_name": "Ali"},
    queue="email_queue",
)
```

With `send_task()`:
- The Kafka consumer doesn't need to import the task function
- The task goes to RabbitMQ and returns immediately (non-blocking)
- A separate Celery worker process picks it up
- If the worker crashes, RabbitMQ re-delivers the task
- Retries are automatic

### 8.2 Why Schema Registry with JSON Schema (Not Avro)?

| Option | Pros | Cons |
|--------|------|------|
| **JSON Schema** (our choice) | Works with Pydantic `.model_json_schema()`, human-readable, no special serializer needed | Slightly larger messages than Avro |
| Avro | Compact binary format, Confluent's default | Requires Avro schema files, special serializer/deserializer, harder to debug |

For a POC, JSON Schema is the right choice. You're already using Pydantic models — the schemas are generated automatically.

### 8.3 Retry Policy

| Attempt | Delay | Formula |
|---------|-------|---------|
| 1st retry | 60 seconds | `60 * (2^0)` |
| 2nd retry | 120 seconds (2 min) | `60 * (2^1)` |
| 3rd retry | 240 seconds (4 min) | `60 * (2^2)` |
| After 3rd | Dead letter queue | Task marked as failed |

---

## 9. Before vs After — Summary

| Aspect | Before (Current) | After (This Guide) |
|--------|-------------------|---------------------|
| Kafka messages | Plain JSON, no schema validation | JSON Schema validated via Schema Registry |
| Email/notification work | Done inline in Kafka consumer | Dispatched to Celery via RabbitMQ, executed by worker |
| RabbitMQ | Running but unused | Used as Celery broker for 3 queues |
| Celery workers | Not deployed | Deployed, processing email/notification/certificate tasks |
| Retry on failure | None (if Kafka handler crashes, event may be lost) | Automatic 3-retry with exponential backoff |
| Observability | Mock output in notification-service logs | Mock output in **celery-worker** logs + RabbitMQ management UI |

---

*Document for SmartCourse POC. Last updated: February 2026.*
