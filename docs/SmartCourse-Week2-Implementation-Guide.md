# SmartCourse - Week 2 Implementation Guide: Event-Driven Infrastructure

**Version:** 1.0  
**Date:** February 18, 2026  
**Prerequisites Completed (Week 1):** User Service, Course Service, Notification Service, API Gateway (FastAPI, Docker, PostgreSQL, MongoDB, Redis)

---

## 1. Overview

### Revised 4-Week Roadmap

| Week | Focus | Deliverables |
|------|-------|-------------|
| **Week 1** (Done) | Core LMS CRUD | User Service, Course Service, Notification Service, API Gateway |
| **Week 2** (This Guide) | Event-Driven Infrastructure | Kafka, RabbitMQ + Celery, Temporal integrated into existing services |
| **Week 3** | Agentic AI Service | AI Tutor agent with RAG, LangGraph, tool-use |
| **Week 4** | Analytics Service | Kafka consumer, metrics aggregation, dashboard endpoints |

### What Changed

The original Week 2 plan combined analytics service + agentic AI research into one week. This revised plan focuses entirely on integrating the event-driven backbone (Kafka, RabbitMQ/Celery, Temporal) into the existing services. This foundation must be in place before both the AI service (Week 3) and analytics service (Week 4) can function properly.

### Week 2 Goal

By the end of this week, every write operation in SmartCourse will produce a Kafka event, background tasks will be processed through Celery workers, and multi-step workflows (enrollment, course publishing) will be orchestrated through Temporal -- all visible in their respective management UIs.

---

## 2. Architecture

### Event & Workflow Layer

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              EXISTING SERVICES                                       │
│                                                                                      │
│   ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐                │
│   │  User Service    │   │  Course Service   │   │ Notification Svc │                │
│   │     :8001        │   │     :8002         │   │     :8005        │                │
│   └────────┬─────────┘   └────────┬──────────┘   └──────────────────┘                │
│            │                      │                        ▲                          │
└────────────┼──────────────────────┼────────────────────────┼──────────────────────────┘
             │                      │                        │
             │  publish events      │  publish events        │  execute tasks
             │                      │  start workflows       │
             ▼                      ▼                        │
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         NEW: EVENT & WORKFLOW LAYER                                   │
│                                                                                      │
│   ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐                │
│   │      KAFKA       │   │    TEMPORAL       │   │    RABBITMQ      │                │
│   │    :9092/:29092  │   │     :7233         │   │   :5672/:15672   │                │
│   │                  │   │                   │   │                  │                │
│   │  Topics:         │   │  Workflows:       │   │  Queues:         │                │
│   │  - user.events   │   │  - Enrollment     │   │  - email_queue   │                │
│   │  - course.events │   │  - Publishing     │   │  - cert_queue    │                │
│   │  - enrollment.*  │   │                   │   │  - notif_queue   │                │
│   │  - progress.*    │   │  Activities ──────┼───┼──► Celery Worker │                │
│   │  - notification.*│   │                   │   │                  │                │
│   └──────────────────┘   └──────────────────┘   └──────────────────┘                │
│            │                                                                         │
│            │ (Week 4)                                                                │
│            ▼                                                                         │
│   ┌──────────────────┐                                                               │
│   │ Analytics Service│  (future)                                                     │
│   │     :8008        │                                                               │
│   └──────────────────┘                                                               │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### When to Use What

| Technology | Pattern | Use Case in SmartCourse | Message Lifecycle |
|-----------|---------|------------------------|-------------------|
| **Kafka** | Event streaming (pub/sub) | Broadcasting events to multiple consumers (analytics, notifications, search) | Persisted (7-30 days), replayable |
| **RabbitMQ + Celery** | Task queue (work distribution) | One-time background jobs: send email, generate PDF certificate, create report | Deleted after acknowledgment |
| **Temporal** | Workflow orchestration | Multi-step durable processes: enrollment flow, course publishing, with retries and compensation | Managed by Temporal server |

**Rule of thumb:**
- "Something happened" → **Kafka** (event notification, many listeners)
- "Do this one thing" → **RabbitMQ/Celery** (task execution, one worker picks it up)
- "Do these 5 things in order, and roll back if step 3 fails" → **Temporal** (workflow orchestration)

---

## 3. Phase 1: Docker Infrastructure Setup

### 3.1 New Environment Variables

Add to `.env`:

```env
# Kafka Configuration
KAFKA_BOOTSTRAP_SERVERS=kafka:29092

# RabbitMQ Configuration
RABBITMQ_USER=smartcourse
RABBITMQ_PASSWORD=smartcourse_secret

# Temporal Configuration
TEMPORAL_HOST=temporal:7233
TEMPORAL_DB_USER=temporal
TEMPORAL_DB_PASSWORD=temporal_secret
```

### 3.2 Kafka + Zookeeper (docker-compose additions)

```yaml
zookeeper:
  image: confluentinc/cp-zookeeper:7.6.0
  container_name: smartcourse-zookeeper
  environment:
    ZOOKEEPER_CLIENT_PORT: 2181
    ZOOKEEPER_TICK_TIME: 2000
  healthcheck:
    test: ["CMD-SHELL", "echo ruok | nc localhost 2181 | grep imok"]
    interval: 10s
    timeout: 5s
    retries: 5
  networks:
    - smartcourse-network

kafka:
  image: confluentinc/cp-kafka:7.6.0
  container_name: smartcourse-kafka
  depends_on:
    zookeeper:
      condition: service_healthy
  ports:
    - "9092:9092"
  environment:
    KAFKA_BROKER_ID: 1
    KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
    KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:29092,PLAINTEXT_HOST://localhost:9092
    KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT
    KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
    KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
    KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"
  healthcheck:
    test: ["CMD-SHELL", "kafka-broker-api-versions --bootstrap-server localhost:9092"]
    interval: 15s
    timeout: 10s
    retries: 10
    start_period: 30s
  networks:
    - smartcourse-network
```

**Topic initialization (one-shot container):**

```yaml
kafka-init:
  image: confluentinc/cp-kafka:7.6.0
  container_name: smartcourse-kafka-init
  depends_on:
    kafka:
      condition: service_healthy
  entrypoint: ["/bin/sh", "-c"]
  command: |
    "
    kafka-topics --bootstrap-server kafka:29092 --create --if-not-exists --topic user.events --partitions 3 --replication-factor 1
    kafka-topics --bootstrap-server kafka:29092 --create --if-not-exists --topic course.events --partitions 3 --replication-factor 1
    kafka-topics --bootstrap-server kafka:29092 --create --if-not-exists --topic enrollment.events --partitions 3 --replication-factor 1
    kafka-topics --bootstrap-server kafka:29092 --create --if-not-exists --topic progress.events --partitions 3 --replication-factor 1
    kafka-topics --bootstrap-server kafka:29092 --create --if-not-exists --topic notification.events --partitions 1 --replication-factor 1
    echo 'All topics created.'
    "
  networks:
    - smartcourse-network
```

> **Note:** In production the partition counts should match the system design (user.events=3, course.events=6, enrollment.events=6, progress.events=12). For local dev, 3 partitions each is fine.

### 3.3 RabbitMQ

```yaml
rabbitmq:
  image: rabbitmq:3.13-management
  container_name: smartcourse-rabbitmq
  ports:
    - "5672:5672"     # AMQP protocol
    - "15672:15672"   # Management UI
  environment:
    RABBITMQ_DEFAULT_USER: ${RABBITMQ_USER:-smartcourse}
    RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASSWORD:-smartcourse_secret}
  volumes:
    - rabbitmq_data:/var/lib/rabbitmq
  healthcheck:
    test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
    interval: 10s
    timeout: 5s
    retries: 5
  networks:
    - smartcourse-network
```

### 3.4 Temporal + Temporal UI + Temporal DB

```yaml
temporal-db:
  image: postgres:16-alpine
  container_name: smartcourse-temporal-db
  environment:
    POSTGRES_USER: ${TEMPORAL_DB_USER:-temporal}
    POSTGRES_PASSWORD: ${TEMPORAL_DB_PASSWORD:-temporal_secret}
  volumes:
    - temporal_db_data:/var/lib/postgresql/data
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U temporal"]
    interval: 10s
    timeout: 5s
    retries: 5
  networks:
    - smartcourse-network

temporal:
  image: temporalio/auto-setup:1.24.2
  container_name: smartcourse-temporal
  ports:
    - "7233:7233"
  environment:
    - DB=postgres12
    - DB_PORT=5432
    - POSTGRES_USER=${TEMPORAL_DB_USER:-temporal}
    - POSTGRES_PWD=${TEMPORAL_DB_PASSWORD:-temporal_secret}
    - POSTGRES_SEEDS=temporal-db
  depends_on:
    temporal-db:
      condition: service_healthy
  healthcheck:
    test: ["CMD", "temporal", "operator", "cluster", "health"]
    interval: 15s
    timeout: 10s
    retries: 10
    start_period: 30s
  networks:
    - smartcourse-network

temporal-ui:
  image: temporalio/ui:2.26.2
  container_name: smartcourse-temporal-ui
  ports:
    - "8233:8080"
  environment:
    - TEMPORAL_ADDRESS=temporal:7233
  depends_on:
    - temporal
  networks:
    - smartcourse-network
```

### 3.5 New Volumes

```yaml
volumes:
  postgres_data:
  redis_data:
  mongodb_data:
  rabbitmq_data:       # NEW
  temporal_db_data:    # NEW
```

### 3.6 Update Existing Service Dependencies

Add to `user-service` environment and depends_on:

```yaml
user-service:
  environment:
    # ... existing vars ...
    - KAFKA_BOOTSTRAP_SERVERS=${KAFKA_BOOTSTRAP_SERVERS:-kafka:29092}
  depends_on:
    # ... existing deps ...
    kafka:
      condition: service_healthy
```

Add to `course-service` environment and depends_on:

```yaml
course-service:
  environment:
    # ... existing vars ...
    - KAFKA_BOOTSTRAP_SERVERS=${KAFKA_BOOTSTRAP_SERVERS:-kafka:29092}
    - TEMPORAL_HOST=${TEMPORAL_HOST:-temporal:7233}
  depends_on:
    # ... existing deps ...
    kafka:
      condition: service_healthy
    temporal:
      condition: service_healthy
```

Add to `notification-service` environment and depends_on:

```yaml
notification-service:
  environment:
    # ... existing vars ...
    - RABBITMQ_URL=amqp://${RABBITMQ_USER:-smartcourse}:${RABBITMQ_PASSWORD:-smartcourse_secret}@rabbitmq:5672//
    - REDIS_URL=redis://:${REDIS_PASSWORD:-smartcourse_secret}@redis:6379/2
  depends_on:
    rabbitmq:
      condition: service_healthy
    redis:
      condition: service_healthy
```

### 3.7 Verification

After running `docker compose up -d`, confirm:

```bash
# Kafka — list topics
docker compose exec kafka kafka-topics --list --bootstrap-server localhost:29092

# RabbitMQ — open management UI
open http://localhost:15672  # login: smartcourse / smartcourse_secret

# Temporal — open workflow UI
open http://localhost:8233

# Check all containers healthy
docker compose ps
```

---

## 4. Phase 2: Shared Event Library

### 4.1 Package Structure

```
shared/
├── pyproject.toml
└── shared/
    ├── __init__.py
    └── events/
        ├── __init__.py
        ├── topics.py       # Topic name constants
        ├── schemas.py       # Pydantic event envelope model
        ├── producer.py      # Async Kafka producer wrapper
        └── consumer.py      # Async Kafka consumer base class
```

### 4.2 `shared/pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "smartcourse-shared"
version = "0.1.0"
description = "SmartCourse shared utilities — event producer, consumer, schemas"
requires-python = ">=3.11"
dependencies = [
    "aiokafka>=0.10.0",
    "pydantic>=2.5.0",
]

[tool.setuptools.packages.find]
include = ["shared*"]
```

### 4.3 Topic Constants — `shared/shared/events/topics.py`

```python
class Topics:
    """Kafka topic name constants used across all services."""

    USER = "user.events"
    COURSE = "course.events"
    ENROLLMENT = "enrollment.events"
    PROGRESS = "progress.events"
    NOTIFICATION = "notification.events"

    ALL = [USER, COURSE, ENROLLMENT, PROGRESS, NOTIFICATION]
```

### 4.4 Event Envelope — `shared/shared/events/schemas.py`

Every Kafka message follows this standard structure:

```python
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    """Standard event envelope used by all SmartCourse services."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str                          # e.g. "user.registered"
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    service: str                             # e.g. "user-service"
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    payload: dict[str, Any] = Field(default_factory=dict)
```

Example serialized message on Kafka:

```json
{
  "event_id": "a1b2c3d4-...",
  "event_type": "enrollment.created",
  "timestamp": "2026-02-18T10:30:00+00:00",
  "service": "course-service",
  "correlation_id": "e5f6g7h8-...",
  "payload": {
    "enrollment_id": 42,
    "student_id": 7,
    "course_id": 101,
    "status": "active"
  }
}
```

### 4.5 Async Producer — `shared/shared/events/producer.py`

```python
import json
import logging
from typing import Any

from aiokafka import AIOKafkaProducer
from shared.events.schemas import EventEnvelope

logger = logging.getLogger(__name__)


class EventProducer:
    """Async Kafka producer that wraps every message in a standard EventEnvelope.

    Usage:
        producer = EventProducer(bootstrap_servers="kafka:29092", service_name="user-service")
        await producer.start()
        await producer.publish("user.events", "user.registered", {"user_id": 1})
        await producer.stop()
    """

    def __init__(self, bootstrap_servers: str, service_name: str):
        self._bootstrap_servers = bootstrap_servers
        self._service_name = service_name
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
        )
        await self._producer.start()
        logger.info("Kafka producer started for %s", self._service_name)

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
        logger.info("Published %s to %s", event_type, topic)
```

### 4.6 Async Consumer Base — `shared/shared/events/consumer.py`

```python
import json
import logging
from typing import Any, Callable, Coroutine

from aiokafka import AIOKafkaConsumer
from shared.events.schemas import EventEnvelope

logger = logging.getLogger(__name__)

EventHandler = Callable[[str, EventEnvelope], Coroutine[Any, Any, None]]


class EventConsumer:
    """Async Kafka consumer that deserializes EventEnvelope messages.

    Usage:
        consumer = EventConsumer(
            topics=["user.events", "course.events"],
            bootstrap_servers="kafka:29092",
            group_id="analytics-consumer-group",
        )
        await consumer.start(handler=my_handler)
        await consumer.stop()
    """

    def __init__(self, topics: list[str], bootstrap_servers: str, group_id: str):
        self._topics = topics
        self._bootstrap_servers = bootstrap_servers
        self._group_id = group_id
        self._consumer: AIOKafkaConsumer | None = None
        self._running = False

    async def start(self, handler: EventHandler) -> None:
        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="earliest",
        )
        await self._consumer.start()
        self._running = True
        logger.info("Consumer started [group=%s, topics=%s]", self._group_id, self._topics)

        try:
            async for msg in self._consumer:
                if not self._running:
                    break
                try:
                    envelope = EventEnvelope(**msg.value)
                    await handler(msg.topic, envelope)
                except Exception:
                    logger.exception("Error processing message from %s offset %s", msg.topic, msg.offset)
        finally:
            await self._consumer.stop()

    async def stop(self) -> None:
        self._running = False
```

### 4.7 Dockerfile Changes

Since the shared library lives outside service directories, change the docker-compose build context to the repo root for each service:

```yaml
# Before
user-service:
  build:
    context: ./services/user-service
    dockerfile: Dockerfile

# After
user-service:
  build:
    context: .
    dockerfile: services/user-service/Dockerfile
```

Then update each Dockerfile to copy and install the shared library:

```dockerfile
# Add these lines before COPY src/ ...
COPY shared/ /shared/
RUN pip install --no-cache-dir -e /shared
```

And update COPY paths to use the repo-root context:

```dockerfile
# Before:  COPY pyproject.toml .
# After:
COPY services/user-service/pyproject.toml ./pyproject.toml

# Before:  COPY src/ ./src/
# After:
COPY services/user-service/src/ ./src/
```

### 4.8 New Dependencies per Service

| Service | New Dependency | Why |
|---------|---------------|-----|
| user-service | `aiokafka>=0.10.0` | Kafka event producer |
| course-service | `aiokafka>=0.10.0`, `temporalio>=1.7.0`, `celery[redis]>=5.3.0` | Kafka, Temporal workflows, Celery task dispatch |
| notification-service | `celery[redis]>=5.3.0` | Celery worker and task definitions |
| shared | `aiokafka>=0.10.0`, `pydantic>=2.5.0` | Event library core |

---

## 5. Phase 3: Kafka Event Producers

### 5.1 Config Changes

Add `KAFKA_BOOTSTRAP_SERVERS` to each service's `config.py` Settings class:

**user-service** — `services/user-service/src/user_service/config.py`:

```python
class Settings(BaseSettings):
    # ... existing fields ...
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:29092"
```

**course-service** — `services/course-service/src/config.py`:

```python
class Settings(BaseSettings):
    # ... existing fields ...
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:29092"
    TEMPORAL_HOST: str = "temporal:7233"
```

### 5.2 FastAPI Lifespan Integration

Start the Kafka producer on app startup, stop on shutdown. Store it on `app.state` so services can access it.

**user-service** — `services/user-service/src/user_service/main.py`:

```python
from shared.events import EventProducer

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_redis(settings.REDIS_URL)

    # Start Kafka producer
    producer = EventProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        service_name="user-service",
    )
    await producer.start()
    app.state.event_producer = producer

    yield

    await producer.stop()
    await close_redis()
    await engine.dispose()
```

**course-service** — `services/course-service/src/main.py`:

```python
from shared.events import EventProducer

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_mongodb()
    await connect_redis(settings.REDIS_URL)

    producer = EventProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        service_name="course-service",
    )
    await producer.start()
    app.state.event_producer = producer

    yield

    await producer.stop()
    await close_redis()
    await close_mongodb()
    await engine.dispose()
```

### 5.3 Dependency Injection

Create a FastAPI dependency to get the producer from request state:

```python
from fastapi import Request
from shared.events import EventProducer

def get_event_producer(request: Request) -> EventProducer:
    return request.app.state.event_producer
```

### 5.4 Events to Emit

#### User Service Events (4 events)

| Event Type | Topic | Trigger | Key Fields in Payload |
|-----------|-------|---------|----------------------|
| `user.registered` | `user.events` | After `AuthService.register()` | `user_id`, `email`, `role` |
| `user.verified` | `user.events` | After email verification | `user_id` |
| `user.login` | `user.events` | After `AuthService.authenticate()` | `user_id`, `email` |
| `user.profile_updated` | `user.events` | After `UserService.update_user()` | `user_id`, `fields_changed` |

Example integration in `services/user-service/src/user_service/api/auth.py`:

```python
@router.post("/register", ...)
async def register(
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db),
    producer: EventProducer = Depends(get_event_producer),
):
    auth_service = AuthService(db)
    user = await auth_service.register(user_data)

    await producer.publish(
        Topics.USER,
        "user.registered",
        {"user_id": user.id, "email": user.email, "role": user.role},
        key=str(user.id),
    )

    return UserResponse.model_validate(user)
```

#### Course Service Events (9 events)

| Event Type | Topic | Trigger | Key Fields in Payload |
|-----------|-------|---------|----------------------|
| `course.created` | `course.events` | After `CourseService.create_course()` | `course_id`, `instructor_id`, `title` |
| `course.published` | `course.events` | After status change to `published` | `course_id`, `instructor_id` |
| `course.updated` | `course.events` | After `CourseService.update_course()` | `course_id`, `fields_changed` |
| `course.archived` | `course.events` | After status change to `archived` | `course_id` |
| `enrollment.created` | `enrollment.events` | After `EnrollmentService.enroll_student()` | `enrollment_id`, `student_id`, `course_id` |
| `enrollment.completed` | `enrollment.events` | After auto-complete in `ProgressService` | `enrollment_id`, `student_id`, `course_id` |
| `progress.updated` | `progress.events` | After `ProgressService.mark_completed()` | `user_id`, `course_id`, `item_type`, `item_id`, `completion_percentage` |
| `progress.module_completed` | `progress.events` | After all lessons in a module are done | `user_id`, `course_id`, `module_id` |
| `certificate.issued` | `course.events` | After `CertificateService.issue_certificate()` | `certificate_id`, `enrollment_id`, `certificate_number` |

**Pattern:** Add `producer: EventProducer = Depends(get_event_producer)` to the API endpoint, then call `await producer.publish(...)` after the successful service method call. The event is published outside the DB transaction so that only committed data triggers events.

### 5.5 Event Logger Script

Create `scripts/event_logger.py` — a standalone consumer that prints all events to stdout for development and debugging:

```python
import asyncio
from shared.events import EventConsumer, EventEnvelope, Topics

async def handle_event(topic: str, event: EventEnvelope) -> None:
    print(f"[{topic}] {event.event_type} | service={event.service} | payload={event.payload}")

async def main():
    consumer = EventConsumer(
        topics=Topics.ALL,
        bootstrap_servers="localhost:9092",
        group_id="event-logger",
    )
    print("Listening for events on all topics... (Ctrl+C to stop)")
    await consumer.start(handler=handle_event)

if __name__ == "__main__":
    asyncio.run(main())
```

Run with: `python scripts/event_logger.py`

---

## 6. Phase 4: RabbitMQ + Celery Background Tasks

### 6.1 Notification Service Updates

#### Config — `services/notification-service/src/notification_service/config.py`

Add RabbitMQ and Redis settings:

```python
class Settings(BaseSettings):
    # ... existing fields ...
    RABBITMQ_URL: str = "amqp://smartcourse:smartcourse_secret@rabbitmq:5672//"
    REDIS_URL: str = "redis://:smartcourse_secret@redis:6379/2"
```

#### Celery App — `services/notification-service/src/notification_service/worker.py`

```python
from celery import Celery
from notification_service.config import settings

celery_app = Celery(
    "smartcourse",
    broker=settings.RABBITMQ_URL,
    backend=settings.REDIS_URL,
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
    task_default_retry_delay=60,
    task_max_retries=3,
)

celery_app.autodiscover_tasks([
    "notification_service.tasks",
])
```

### 6.2 Task Definitions

#### New directory structure:

```
services/notification-service/src/notification_service/tasks/
├── __init__.py
├── email.py
├── certificate.py
└── notification.py
```

#### Email Tasks — `tasks/email.py`

```python
from notification_service.worker import celery_app

@celery_app.task(bind=True, max_retries=3, name="notification_service.tasks.email.send_welcome_email")
def send_welcome_email(self, user_id: int, email: str, first_name: str):
    """Send welcome email after registration."""
    try:
        # In production: use SMTP, SendGrid, etc.
        print(f"[EMAIL] Welcome email sent to {email} (user_id={user_id})")
        return {"status": "sent", "user_id": user_id}
    except Exception as exc:
        self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

@celery_app.task(bind=True, max_retries=3, name="notification_service.tasks.email.send_enrollment_confirmation")
def send_enrollment_confirmation(self, student_id: int, course_id: int, course_title: str):
    """Send enrollment confirmation email."""
    try:
        print(f"[EMAIL] Enrollment confirmation: student={student_id}, course={course_title}")
        return {"status": "sent", "student_id": student_id, "course_id": course_id}
    except Exception as exc:
        self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

@celery_app.task(bind=True, max_retries=3, name="notification_service.tasks.email.send_completion_congratulations")
def send_completion_congratulations(self, student_id: int, course_id: int, course_title: str):
    """Send congratulations email on course completion."""
    try:
        print(f"[EMAIL] Congratulations: student={student_id} completed {course_title}")
        return {"status": "sent", "student_id": student_id}
    except Exception as exc:
        self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
```

#### Certificate Tasks — `tasks/certificate.py`

```python
from notification_service.worker import celery_app

@celery_app.task(bind=True, max_retries=3, name="notification_service.tasks.certificate.generate_certificate_pdf")
def generate_certificate_pdf(self, certificate_id: int, enrollment_id: int, student_name: str, course_title: str):
    """Generate a PDF certificate for a completed course."""
    try:
        # In production: use reportlab, weasyprint, etc.
        print(f"[CERT] Generated PDF for certificate_id={certificate_id}")
        return {"status": "generated", "certificate_id": certificate_id}
    except Exception as exc:
        self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
```

#### In-App Notification Tasks — `tasks/notification.py`

```python
from notification_service.worker import celery_app

@celery_app.task(bind=True, max_retries=3, name="notification_service.tasks.notification.create_in_app_notification")
def create_in_app_notification(self, user_id: int, title: str, message: str, notification_type: str = "system"):
    """Create an in-app notification record."""
    try:
        # In production: write to notifications table in PostgreSQL
        print(f"[NOTIF] In-app notification for user_id={user_id}: {title}")
        return {"status": "created", "user_id": user_id}
    except Exception as exc:
        self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
```

### 6.3 Celery Worker Docker Service

```yaml
celery-worker:
  build:
    context: .
    dockerfile: services/notification-service/Dockerfile
  container_name: smartcourse-celery-worker
  command: >
    celery -A notification_service.worker:celery_app worker
    --loglevel=info
    -Q email_queue,certificate_queue,notification_queue
  environment:
    - RABBITMQ_URL=amqp://${RABBITMQ_USER}:${RABBITMQ_PASSWORD}@rabbitmq:5672//
    - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/2
  depends_on:
    rabbitmq:
      condition: service_healthy
    redis:
      condition: service_healthy
  networks:
    - smartcourse-network
```

### 6.4 Dispatching Celery Tasks from Other Services

Since user-service and course-service need to dispatch Celery tasks (e.g., during a Temporal workflow activity), they send tasks via the Celery `send_task` API rather than importing task functions directly. This keeps services decoupled.

```python
from celery import Celery

celery_app = Celery(broker="amqp://smartcourse:smartcourse_secret@rabbitmq:5672//")

# Send a task by name — no need to import the task function
celery_app.send_task(
    "notification_service.tasks.email.send_welcome_email",
    args=[user_id, email, first_name],
    queue="email_queue",
)
```

### 6.5 Retry Policy

Per the system design:

| Attempt | Delay | Notes |
|---------|-------|-------|
| 1st retry | 60 seconds | First failure |
| 2nd retry | 300 seconds (5 min) | Second failure |
| 3rd retry | 900 seconds (15 min) | Final attempt |
| After 3rd | Dead letter queue | Manual inspection required |

This is implemented via `self.retry(countdown=60 * (2 ** self.request.retries))` in each task.

---

## 7. Phase 5: Temporal Workflows

### 7.1 New Files in course-service

```
services/course-service/src/workflows/
├── __init__.py
├── enrollment.py       # EnrollmentWorkflow definition
├── publishing.py       # CoursePublishingWorkflow definition
├── activities.py       # Shared activity implementations
└── worker.py           # Temporal worker entry point
```

### 7.2 Enrollment Workflow

From the system design, the enrollment workflow has 4 activities:

```
                    EnrollmentWorkflow
                          │
          ┌───────────────┼───────────────┐
          │               │               │
          ▼               ▼               ▼
   1. initialize     2. update       3. activate
      progress          analytics       enrollment
                                            │
                                            ▼
                                   4. send_welcome
                                      notification
```

#### Workflow Definition — `workflows/enrollment.py`

```python
from datetime import timedelta
from dataclasses import dataclass

from temporalio import workflow
from temporalio.common import RetryPolicy

@dataclass
class EnrollmentInput:
    enrollment_id: int
    student_id: int
    course_id: int
    course_title: str

@workflow.defn
class EnrollmentWorkflow:
    @workflow.run
    async def run(self, input: EnrollmentInput) -> dict:
        retry = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=5))
        timeout = timedelta(seconds=30)

        # Step 1: Initialize progress tracking
        progress = await workflow.execute_activity(
            "initialize_progress",
            input,
            start_to_close_timeout=timeout,
            retry_policy=retry,
        )

        # Step 2: Update analytics counters
        await workflow.execute_activity(
            "update_enrollment_analytics",
            input,
            start_to_close_timeout=timeout,
            retry_policy=retry,
        )

        # Step 3: Activate the enrollment (PENDING → ACTIVE)
        await workflow.execute_activity(
            "activate_enrollment",
            input,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=retry,
        )

        # Step 4: Send welcome notification via Celery
        await workflow.execute_activity(
            "send_welcome_notification",
            input,
            start_to_close_timeout=timeout,
            retry_policy=retry,
        )

        return {"enrollment_id": input.enrollment_id, "status": "completed"}
```

#### Activity Implementations — `workflows/activities.py`

```python
from temporalio import activity
from celery import Celery

@activity.defn(name="initialize_progress")
async def initialize_progress(input) -> dict:
    # Create initial progress record for the student in this course
    # In practice: call the DB, create progress entries
    activity.logger.info("Initializing progress for enrollment %s", input.enrollment_id)
    return {"progress_initialized": True}

@activity.defn(name="update_enrollment_analytics")
async def update_enrollment_analytics(input) -> dict:
    # Publish enrollment.created event to Kafka
    # Update course enrollment count, instructor total_students
    activity.logger.info("Publishing analytics for enrollment %s", input.enrollment_id)
    return {"analytics_updated": True}

@activity.defn(name="activate_enrollment")
async def activate_enrollment(input) -> dict:
    # Update enrollment status from PENDING to ACTIVE
    activity.logger.info("Activating enrollment %s", input.enrollment_id)
    return {"status": "active"}

@activity.defn(name="send_welcome_notification")
async def send_welcome_notification(input) -> dict:
    # Dispatch Celery task for welcome email
    celery = Celery(broker="amqp://smartcourse:smartcourse_secret@rabbitmq:5672//")
    celery.send_task(
        "notification_service.tasks.email.send_enrollment_confirmation",
        args=[input.student_id, input.course_id, input.course_title],
        queue="email_queue",
    )
    activity.logger.info("Queued welcome notification for student %s", input.student_id)
    return {"notified": True}
```

### 7.3 Course Publishing Workflow

From the system design (5 activities):

```
                 CoursePublishingWorkflow
                          │
     ┌────────────────────┼────────────────────┐
     │                    │                    │
     ▼                    ▼                    ▼
  1. validate          2. process          3. update_search
     course               content              index
                                                  │
                          ┌───────────────────────┘
                          ▼                    ▼
                    4. mark_published     5. publish_event
```

#### Workflow Definition — `workflows/publishing.py`

```python
from datetime import timedelta
from dataclasses import dataclass

from temporalio import workflow
from temporalio.common import RetryPolicy

@dataclass
class PublishingInput:
    course_id: int
    instructor_id: int

@workflow.defn
class CoursePublishingWorkflow:
    @workflow.run
    async def run(self, input: PublishingInput) -> dict:
        retry = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=5))

        # Step 1: Validate course has modules/lessons
        await workflow.execute_activity(
            "validate_course_for_publishing",
            input,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry,
        )

        # Step 2: Process content (chunk text, prepare for search)
        await workflow.execute_activity(
            "process_course_content",
            input,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry,
        )

        # Step 3: Mark course as published
        await workflow.execute_activity(
            "mark_course_published",
            input,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=retry,
        )

        # Step 4: Publish Kafka event + notify instructor
        await workflow.execute_activity(
            "publish_course_event",
            input,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry,
        )

        return {"course_id": input.course_id, "status": "published"}
```

**Compensation on failure:** If any activity fails after max retries, the workflow should roll back:
1. Reset course status to `draft`
2. Clean up partial data
3. Notify instructor of failure

This is implemented by wrapping the workflow in a try/except and calling compensation activities.

### 7.4 Temporal Worker — `workflows/worker.py`

```python
import asyncio
from temporalio.client import Client
from temporalio.worker import Worker

from workflows.enrollment import EnrollmentWorkflow
from workflows.publishing import CoursePublishingWorkflow
from workflows.activities import (
    initialize_progress,
    update_enrollment_analytics,
    activate_enrollment,
    send_welcome_notification,
    validate_course_for_publishing,
    process_course_content,
    mark_course_published,
    publish_course_event,
)
from config import settings

TASK_QUEUE = "smartcourse-workflows"

async def main():
    client = await Client.connect(settings.TEMPORAL_HOST)

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[EnrollmentWorkflow, CoursePublishingWorkflow],
        activities=[
            initialize_progress,
            update_enrollment_analytics,
            activate_enrollment,
            send_welcome_notification,
            validate_course_for_publishing,
            process_course_content,
            mark_course_published,
            publish_course_event,
        ],
    )

    print(f"Temporal worker started on queue: {TASK_QUEUE}")
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())
```

### 7.5 Temporal Worker Docker Service

```yaml
temporal-worker:
  build:
    context: .
    dockerfile: services/course-service/Dockerfile
  container_name: smartcourse-temporal-worker
  command: python -m workflows.worker
  environment:
    - DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
    - MONGODB_URL=mongodb://${MONGO_USER}:${MONGO_PASSWORD}@mongodb:27017/${MONGO_DB}?authSource=admin
    - KAFKA_BOOTSTRAP_SERVERS=${KAFKA_BOOTSTRAP_SERVERS:-kafka:29092}
    - TEMPORAL_HOST=${TEMPORAL_HOST:-temporal:7233}
    - RABBITMQ_URL=amqp://${RABBITMQ_USER}:${RABBITMQ_PASSWORD}@rabbitmq:5672//
  depends_on:
    temporal:
      condition: service_healthy
    kafka:
      condition: service_healthy
    rabbitmq:
      condition: service_healthy
  networks:
    - smartcourse-network
```

### 7.6 Integrating Workflows into API Endpoints

In the course-service enrollment endpoint, start a Temporal workflow instead of doing everything inline.

**Before (current):** The `POST /enrollments/` endpoint calls `EnrollmentService.enroll_student()` which does everything synchronously.

**After:** The endpoint creates the enrollment in PENDING state, starts the Temporal workflow, and returns immediately. The workflow handles progress initialization, analytics, activation, and notification asynchronously.

```python
from temporalio.client import Client

# In the FastAPI lifespan, connect the Temporal client:
temporal_client = await Client.connect(settings.TEMPORAL_HOST)
app.state.temporal_client = temporal_client

# In the enrollment endpoint:
@router.post("/", ...)
async def enroll(data: EnrollmentCreate, ...):
    # 1. Validate + create enrollment (PENDING status)
    enrollment = await service.enroll_student(user_id, data)

    # 2. Start Temporal workflow (async, non-blocking)
    await temporal_client.start_workflow(
        EnrollmentWorkflow.run,
        EnrollmentInput(
            enrollment_id=enrollment.id,
            student_id=user_id,
            course_id=data.course_id,
            course_title="...",
        ),
        id=f"enrollment-{enrollment.id}",
        task_queue="smartcourse-workflows",
    )

    return EnrollmentResponse.model_validate(enrollment)
```

---

## 8. Phase 6: Integration Wiring + Verification

### 8.1 End-to-End Enrollment Flow

```
Student
  │
  │ POST /enrollments/ {course_id: 101}
  ▼
API Gateway (:8000)
  │
  ▼
Course Service (:8002)
  │
  ├─ 1. Validate (course exists, published, not already enrolled, under limit)
  ├─ 2. INSERT enrollment (status: PENDING) into PostgreSQL
  ├─ 3. Publish "enrollment.created" to Kafka (enrollment.events topic)
  ├─ 4. Start EnrollmentWorkflow in Temporal
  └─ 5. Return {enrollment_id, status: PENDING} to client
         │
         ▼ (async, via Temporal)
  ┌──────────────────────────────────────────────────────┐
  │              TEMPORAL: EnrollmentWorkflow             │
  │                                                      │
  │  Activity 1: initialize_progress                     │
  │    → Create progress record in PostgreSQL            │
  │                                                      │
  │  Activity 2: update_enrollment_analytics             │
  │    → Publish event to Kafka analytics topic          │
  │    → Update course enrollment_count                  │
  │                                                      │
  │  Activity 3: activate_enrollment                     │
  │    → UPDATE enrollment SET status = 'active'         │
  │                                                      │
  │  Activity 4: send_welcome_notification               │
  │    → Dispatch Celery task to RabbitMQ email_queue    │
  │                                                      │
  └──────────────────────────────────────────────────────┘
         │
         ▼ (via RabbitMQ → Celery Worker)
  ┌──────────────────────────────────────────────────────┐
  │           CELERY WORKER: send_enrollment_confirmation│
  │                                                      │
  │  → Send welcome email (stubbed for now)              │
  │  → Create in-app notification                        │
  └──────────────────────────────────────────────────────┘
```

### 8.2 Verification Checklist

| Check | How to Verify |
|-------|--------------|
| All containers running | `docker compose ps` — all services showing "healthy" or "running" |
| Kafka topics created | `docker compose exec kafka kafka-topics --list --bootstrap-server localhost:29092` |
| Kafka events flowing | Run `python scripts/event_logger.py`, register a user, see `user.registered` event |
| RabbitMQ accessible | Open `http://localhost:15672`, login with smartcourse/smartcourse_secret |
| RabbitMQ queues exist | Check Queues tab for email_queue, certificate_queue, notification_queue |
| Celery worker processing | Check celery-worker logs: `docker compose logs celery-worker` |
| Temporal UI accessible | Open `http://localhost:8233` |
| Temporal workflow runs | Enroll a student, see EnrollmentWorkflow in Temporal UI |
| Enrollment end-to-end | POST enrollment → see workflow in Temporal UI → see email task in Celery logs → see event in event logger |

---

## 9. Files Summary

### New Files (~20)

| File | Purpose |
|------|---------|
| `shared/pyproject.toml` | Shared library package config |
| `shared/shared/__init__.py` | Package init |
| `shared/shared/events/__init__.py` | Events subpackage |
| `shared/shared/events/topics.py` | Topic name constants |
| `shared/shared/events/schemas.py` | EventEnvelope Pydantic model |
| `shared/shared/events/producer.py` | Async Kafka producer |
| `shared/shared/events/consumer.py` | Async Kafka consumer base |
| `services/notification-service/src/notification_service/worker.py` | Celery app configuration |
| `services/notification-service/src/notification_service/tasks/__init__.py` | Tasks package |
| `services/notification-service/src/notification_service/tasks/email.py` | Email tasks |
| `services/notification-service/src/notification_service/tasks/certificate.py` | Certificate PDF task |
| `services/notification-service/src/notification_service/tasks/notification.py` | In-app notification task |
| `services/course-service/src/workflows/__init__.py` | Workflows package |
| `services/course-service/src/workflows/enrollment.py` | EnrollmentWorkflow |
| `services/course-service/src/workflows/publishing.py` | CoursePublishingWorkflow |
| `services/course-service/src/workflows/activities.py` | Workflow activity implementations |
| `services/course-service/src/workflows/worker.py` | Temporal worker entry point |
| `scripts/event_logger.py` | Development event consumer |

### Modified Files (~10)

| File | Change |
|------|--------|
| `docker-compose.yml` | Add Kafka, Zookeeper, kafka-init, RabbitMQ, Temporal, Temporal UI, Temporal DB, celery-worker, temporal-worker; update build contexts |
| `.env` | Add KAFKA, RABBITMQ, TEMPORAL env vars |
| `services/user-service/Dockerfile` | Repo-root context paths, install shared lib, add aiokafka |
| `services/user-service/pyproject.toml` | Add `aiokafka` dependency |
| `services/user-service/src/user_service/config.py` | Add `KAFKA_BOOTSTRAP_SERVERS` |
| `services/user-service/src/user_service/main.py` | Start/stop Kafka producer in lifespan |
| `services/user-service/src/user_service/api/auth.py` | Emit user.registered, user.login events |
| `services/user-service/src/user_service/api/profile.py` | Emit user.profile_updated event |
| `services/course-service/Dockerfile` | Repo-root context paths, install shared lib, add aiokafka + temporalio + celery |
| `services/course-service/pyproject.toml` | Add `aiokafka`, `temporalio`, `celery[redis]` dependencies |
| `services/course-service/src/config.py` | Add `KAFKA_BOOTSTRAP_SERVERS`, `TEMPORAL_HOST` |
| `services/course-service/src/main.py` | Start/stop Kafka producer + Temporal client in lifespan |
| `services/course-service/src/api/enrollments.py` | Start EnrollmentWorkflow after enrollment creation |
| `services/course-service/src/api/courses.py` | Start CoursePublishingWorkflow on publish, emit course events |
| `services/course-service/src/services/*.py` | Emit enrollment, progress, certificate events |
| `services/notification-service/Dockerfile` | Repo-root context paths, install shared lib, add celery |
| `services/notification-service/pyproject.toml` | Add `celery[redis]` dependency |
| `services/notification-service/src/notification_service/config.py` | Add `RABBITMQ_URL`, `REDIS_URL` |

---

## 10. Updated Port Reference

| Service | Internal Port | Host Port | Access |
|---------|--------------|-----------|--------|
| API Gateway (Nginx) | 8000 | 8000 | Public entry point |
| User Service | 8001 | -- | Via Gateway |
| Course Service | 8002 | -- | Via Gateway |
| Notification Service | 8005 | -- | Via Gateway |
| Auth Sidecar | 8010 | -- | Internal (Nginx only) |
| PostgreSQL | 5432 | 5432 | Direct |
| Redis | 6379 | 6379 | Direct |
| MongoDB | 27017 | 27017 | Direct |
| **Kafka** | 29092 | 9092 | Event streaming |
| **Zookeeper** | 2181 | -- | Kafka coordination |
| **RabbitMQ (AMQP)** | 5672 | 5672 | Task queue |
| **RabbitMQ (UI)** | 15672 | 15672 | Management UI |
| **Temporal** | 7233 | 7233 | Workflow server |
| **Temporal UI** | 8080 | 8233 | Workflow dashboard |
| **Temporal DB** | 5432 | -- | Temporal state (separate PG) |
| **Celery Worker** | -- | -- | Background task processor |
| **Temporal Worker** | -- | -- | Workflow activity executor |

---

## 11. Event Types Quick Reference

From the ERD:

| Event Type | Kafka Topic | Trigger | Consumers |
|-----------|-------------|---------|-----------|
| `user.registered` | `user.events` | User signs up | Analytics, Notification |
| `user.verified` | `user.events` | Email verified | Analytics |
| `user.login` | `user.events` | Successful login | Analytics |
| `user.profile_updated` | `user.events` | Profile update | Analytics |
| `course.created` | `course.events` | Course created | Analytics |
| `course.published` | `course.events` | Course published | Analytics, Content Processing |
| `course.updated` | `course.events` | Course modified | Content Processing |
| `course.archived` | `course.events` | Course archived | Notification, Analytics |
| `enrollment.created` | `enrollment.events` | Student enrolls | Analytics, Progress, Notification |
| `enrollment.completed` | `enrollment.events` | Course completed | Analytics, Certificate, Notification |
| `enrollment.dropped` | `enrollment.events` | Student drops | Analytics |
| `progress.updated` | `progress.events` | Lesson completed | Analytics |
| `progress.module_completed` | `progress.events` | Module done | Analytics, Notification |
| `certificate.issued` | `course.events` | Cert generated | Notification |
| `certificate.revoked` | `course.events` | Cert revoked | Notification |

---

*Document Version: 1.0 | Created: February 18, 2026*
