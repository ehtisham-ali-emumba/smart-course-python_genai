# SmartCourse — Event-Driven Architecture: A Complete Learning Guide

**Your teacher's note:** This guide walks you through every piece of the event flow we built. Read it top-to-bottom for a full picture, or jump to sections that interest you.

---

## 1. The Big Picture: What Problem Are We Solving?

In a microservices app, services need to talk to each other. Two common patterns:

| Pattern | Use case | Example |
|---------|----------|---------|
| **Request–Response** | Client needs an immediate answer | "Give me my profile" |
| **Event-Driven** | Something happened; others might care | "A user just signed up" |

**Event-driven** means: instead of user-service calling notification-service directly (tight coupling), user-service **announces** "user.registered" and any service that cares can react. Loose coupling, easy to add new consumers.

We use **two different tools** for two different jobs:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  KAFKA           = "What happened?" (events)                                 │
│  - Many consumers can read the same event                                   │
│  - Events are stored (replay, audit)                                        │
│  - Example: user.registered, enrollment.completed, certificate.issued       │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  RABBITMQ + CELERY  = "Do this job" (tasks)                                 │
│  - Exactly one worker does each task                                        │
│  - Task is removed when done                                                │
│  - Retries, dead-letter queues, result tracking                             │
│  - Example: send_welcome_email, generate_certificate_pdf                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

**How they work together:** Kafka tells us *what happened*. RabbitMQ/Celery does the *actual work* (email, PDF, etc.) in the background.

---

## 2. End-to-End Flow: User Signup Example

Follow a single user registration through the whole system:

```
  YOU                    user-service              Kafka            notification-service        RabbitMQ          Celery Worker
   │                          │                      │                       │                      │                    │
   │  POST /auth/register     │                      │                       │                      │                    │
   │ ───────────────────────> │                      │                       │                      │                    │
   │                          │                      │                       │                      │                    │
   │                          │  1. Save user in DB  │                       │                      │                    │
   │                          │  2. Publish event    │                       │                      │                    │
   │                          │ ─────────────────────>                       │                      │                    │
   │                          │     user.registered  │                       │                      │                    │
   │                          │     (Schema Registry │                       │                      │                    │
   │                          │      validates)     │                       │                      │                    │
   │                          │                      │                       │                      │                    │
   │  {"id": 14, ...}         │                      │  3. Consumer receives  │                      │                    │
   │ <─────────────────────── │                      │ <──────────────────────│                      │                    │
   │                          │                      │     user.registered    │                      │                    │
   │                          │                      │                       │                      │                    │
   │                          │                      │                       │  4. Dispatch tasks   │                    │
   │                          │                      │                       │ ─────────────────────>                    │
   │                          │                      │                       │  send_welcome_email  │                    │
   │                          │                      │                       │  create_notification │                    │
   │                          │                      │                       │                      │                    │
   │                          │                      │                       │                      │  5. Worker executes  │
   │                          │                      │                       │                      │ <───────────────── │
   │                          │                      │                       │                      │  Mock email log    │
   │                          │                      │                       │                      │  Mock notif log    │
```

**Key insight:** The user gets an immediate HTTP response. Emails and notifications run asynchronously in the background.

---

## 3. Where Things Live: The Code Map

### 3.1 Kafka Producers

**Who produces?** user-service and course-service (they *create* events).

**Shared producer code:**
```
services/core/src/core_service/providers/kafka/producer.py
```
- `EventProducer` class – used by all producing services
- Wraps messages in `EventEnvelope`
- Registers schemas with Schema Registry before first publish per topic

**Where it’s created (lifespan):**
- `services/user-service/src/user_service/main.py` — `EventProducer(..., schema_registry_url=...)`
- `services/course-service/src/main.py` — same

**Where it’s used (HTTP endpoints):**

| Service       | File                          | Event(s)                |
|---------------|-------------------------------|-------------------------|
| user-service  | `api/auth.py`                 | user.registered, user.login |
| course-service| `api/courses.py`              | course.published, course.archived |
| course-service| `api/enrollments.py`          | enrollment.created, enrollment.dropped, enrollment.completed |
| course-service| `services/progress.py`        | progress.course_completed |
| course-service| `services/certificate.py`     | certificate.issued, certificate.revoked |

**Example — user registration:**
```python
# services/user-service/src/user_service/api/auth.py

await producer.publish(
    Topics.USER,              # topic: "user.events"
    "user.registered",       # event_type
    UserRegisteredPayload(
        user_id=user.id,
        email=user.email,
        first_name=user.first_name,
        ...
    ).model_dump(),
    key=str(user.id),        # Kafka key for partitioning
)
```

---

### 3.2 Kafka Consumers

**Who consumes?** notification-service.

**Shared consumer code:**
```
services/core/src/core_service/providers/kafka/consumer.py
```
- `EventConsumer` class — generic async consumer
- Deserializes JSON → `EventEnvelope`
- Invokes a handler for each message

**Where it’s used:**
```
services/notification-service/src/notification_service/consumers/kafka_consumer.py
```
- `run_notification_consumer()` creates `EventConsumer` for `user.events`, `course.events`, `enrollment.events`
- Handler: `NotificationEventHandlers`

**Event → Handler mapping:**
```
services/notification-service/src/notification_service/consumers/event_handlers.py
```
- `NotificationEventHandlers` – maps event types to methods
- Each handler receives the event, then dispatches Celery tasks (does **not** do heavy work inline)

---

## 4. Schema Registry: What and Where

### 4.1 What Is It?

**Problem:** Without a shared contract, any service can publish arbitrary JSON. If `user-service` drops `email` from the payload, `notification-service` may crash with `KeyError`.

**Solution:** Schema Registry is an HTTP service that:
1. Stores JSON schemas per topic
2. Producers register their schema before publishing
3. Consumers can fetch the schema to validate/parse messages

Think of it as a shared type checker for Kafka messages.

### 4.2 Where Is It?

**Infrastructure:**
```
docker-compose.yml → schema-registry service
```
- Image: `confluentinc/cp-schema-registry:7.6.0`
- Port: 8081
- HTTP API: e.g. `http://localhost:8081/subjects`

**Client code:**
```
services/core/src/core_service/providers/kafka/schema_registry.py
```
- `SchemaRegistryClient` – HTTP client for Schema Registry
- `register_schema(subject, schema)` – register a schema
- `get_latest_schema(subject)` – fetch latest schema for a subject

**Schema source:**
```
services/core/src/core_service/providers/kafka/schema_utils.py
```
- `get_envelope_schema()` – generates JSON schema from `EventEnvelope` Pydantic model
- We use one schema for all events (the envelope shape)

**Usage in producer:**
```
services/core/src/core_service/providers/kafka/producer.py
```
- On first publish to a topic:
  - Subject: `{topic}-value` (e.g. `user.events-value`)
  - Registers via Schema Registry
  - Caches schema ID to avoid repeated calls

**Flow:**
```
Producer.publish("user.events", ...)
    → _ensure_schema_registered("user.events")
    → SchemaRegistryClient.register_schema("user.events-value", get_envelope_schema())
    → POST http://schema-registry:8081/subjects/user.events-value/versions
    → Then send message to Kafka
```

---

## 5. The EventEnvelope: Your Message Format

All Kafka messages use this wrapper:

```
services/core/src/core_service/events/envelope.py
```

```python
class EventEnvelope(BaseModel):
    event_id: str          # UUID
    event_type: str       # "user.registered", "enrollment.completed", etc.
    timestamp: str         # ISO 8601
    service: str          # "user-service", "course-service"
    correlation_id: str    # For tracing
    payload: dict          # The actual event data (varies by event_type)
```

**Example JSON on wire:**
```json
{
  "event_id": "a2461f4e-d2ab-465c-bc17-d5d832d17734",
  "event_type": "user.registered",
  "timestamp": "2026-02-21T08:06:14.123Z",
  "service": "user-service",
  "correlation_id": "abc-123",
  "payload": {
    "user_id": 14,
    "email": "final@example.com",
    "first_name": "Final",
    "last_name": "Test",
    "role": "student"
  }
}
```

Consumers branch on `event_type` and then interpret `payload`.

---

## 6. RabbitMQ + Celery: How Tasks Run

### 6.1 Why Two Systems?

- **Kafka:** "Something happened." Multiple consumers, durable, replayable.
- **RabbitMQ/Celery:** "Do this job once." One worker, retries, DLQ, results.

**Pattern:** Kafka consumer receives event → enqueues Celery tasks → worker executes them.

### 6.2 Where Each Piece Lives

**RabbitMQ (broker):**
```
docker-compose.yml → rabbitmq service
```
- Ports: 5672 (AMQP), 15672 (management UI)
- Login: smartcourse / smartcourse_secret

**Celery app (config):**
```
services/notification-service/src/notification_service/worker.py
```
- Creates Celery app with broker and backend
- Configures task routes (email → email_queue, etc.)
- Autodiscovers tasks in `notification_service.tasks`

**Task definitions:**
```
services/notification-service/src/notification_service/tasks/
├── __init__.py
├── email.py          # send_welcome_email, send_enrollment_confirmation, etc.
├── notification.py   # create_in_app_notification
└── certificate.py    # generate_certificate_pdf
```

**Dispatcher (from Kafka to RabbitMQ):**
```
services/notification-service/src/notification_service/consumers/event_handlers.py
```
- Event handlers call `celery_app.send_task("task.name", kwargs={...}, queue="email_queue")`
- They **do not** import and call task functions directly

**Worker process:**
```
docker-compose.yml → celery-worker service
```
- Command: `celery -A notification_service.worker:celery_app worker -Q email_queue,notification_queue,certificate_queue`

### 6.3 Task Flow

```
event_handlers._on_user_registered(event)
    │
    ├── celery_app.send_task("notification_service.tasks.email.send_welcome_email", kwargs={...}, queue="email_queue")
    └── celery_app.send_task("notification_service.tasks.notification.create_in_app_notification", kwargs={...}, queue="notification_queue")
            │
            ▼
    RabbitMQ stores tasks in queues
            │
            ▼
    Celery worker consumes from queues, runs the Python functions
            │
            ▼
    email.py: send_welcome_email() → MockEmailService.send()
    notification.py: create_in_app_notification() → MockNotificationService.create()
```

---

## 7. Dependency Overview

```
                    ┌─────────────────┐
                    │   Schema        │
                    │   Registry      │  ← Producers register schemas here
                    │   :8081         │
                    └────────▲────────┘
                             │
    ┌────────────────────────┼────────────────────────┐
    │                        │                        │
    │  user-service          │        course-service  │
    │  (producer)            │        (producer)      │
    │                        │                        │
    └────────────┬───────────┴───────────┬────────────┘
                 │                       │
                 │    Publish events     │
                 ▼                       ▼
            ┌─────────────────────────────────────┐
            │              KAFKA                   │
            │  user.events, course.events,         │
            │  enrollment.events, progress.events  │
            └───────────────────┬───────────────────┘
                                │
                                │  Consume
                                ▼
            ┌─────────────────────────────────────┐
            │     notification-service            │
            │     (Kafka consumer)                │
            │                                    │
            │  EventConsumer → EventHandlers      │
            └───────────────────┬─────────────────┘
                                │
                                │  send_task(...)
                                ▼
            ┌─────────────────────────────────────┐
            │            RABBITMQ                 │
            │  email_queue, notification_queue,   │
            │  certificate_queue                  │
            └───────────────────┬─────────────────┘
                                │
                                │  Worker consumes
                                ▼
            ┌─────────────────────────────────────┐
            │        celery-worker                │
            │  Executes: email, notification,     │
            │  certificate tasks                  │
            └─────────────────────────────────────┘
                                │
                                │  Result storage
                                ▼
            ┌─────────────────────────────────────┐
            │              REDIS                  │
            │  CELERY_RESULT_BACKEND              │
            └─────────────────────────────────────┘
```

---

## 8. Event Filtering: Who Listens to What

This answers: *Does every consumer read every event? Where is filtering?*

### Two Levels of Filtering

| Level | Where | How |
|-------|-------|-----|
| **Topic** | When the consumer subscribes | Each consumer passes a `topics=[...]` list — only those topics are delivered |
| **Event type** | In the handler | Handler has a dict of `event_type → function`; unknown types are ignored |

### Who Subscribes to What (Today)

| Consumer | Topics subscribed | Location |
|----------|-------------------|----------|
| **notification-service** | `user.events`, `course.events`, `enrollment.events` | `kafka_consumer.py` line 21 |

**Code — notification-service (filtered):**
```python
# services/notification-service/src/notification_service/consumers/kafka_consumer.py

topics = [Topics.USER, Topics.COURSE, Topics.ENROLLMENT]  # NOT progress, NOT notification
consumer = EventConsumer(
    topics=topics,
    group_id="notification-service",
)
```

So notification-service **does not** subscribe to `progress.events` or `notification.events`. It only gets user, course, and enrollment events.

### Event-Type Filtering Within a Topic

A single topic can contain multiple event types. For example, `user.events` has:
- `user.registered`
- `user.login`
- `user.profile_updated`

The handler decides what to do per `event_type`:

```python
# services/notification-service/src/notification_service/consumers/event_handlers.py

self._handlers = {
    "user.registered": self._on_user_registered,
    "course.published": self._on_course_published,
    # ... only events we care about
}

async def handle(self, topic: str, event: EventEnvelope) -> None:
    handler = self._handlers.get(event.event_type)
    if handler:                    # ← filtering: only process if we have a handler
        await handler(event)
    # If no handler → event is silently ignored (we don't care)
```

So if `user.login` arrives, notification-service receives it (because it subscribes to `user.events`) but does nothing — no handler for it.

### Consumer Groups: Copy vs Load Balance

| Same `group_id` | Each instance shares the partition; Kafka load-balances messages across the group |
| Different `group_id` | Each group gets its own copy of every message |

- `notification-service` uses `group_id="notification-service"` and gets its own copy of messages from user, course, and enrollment topics.

### Future: Analytics or Other Services

To add an **analytics service** that only cares about user and progress events:

```python
# Hypothetical: services/analytics-service/consumer.py

topics = [Topics.USER, Topics.PROGRESS]  # Only these
consumer = EventConsumer(
    topics=topics,
    group_id="analytics-service",
)
```

Or a **course-recommendation service** that only cares about enrollments:

```python
topics = [Topics.ENROLLMENT]
consumer = EventConsumer(topics=topics, group_id="course-recommendations")
```

Filtering happens at **subscription** (topics) and in the **handler** (event_type). No extra Kafka config needed.

### Summary

| Question | Answer |
|----------|--------|
| Does every consumer read every event? | **No.** Each consumer subscribes to specific topics. |
| Where is topic filtering? | In `EventConsumer(topics=[...])` when the consumer starts. |
| Where is event-type filtering? | In the handler dict — `handlers.get(event_type)`; no match = ignore. |
| Can we add analytics / course-service consumers? | **Yes.** Create a new consumer with its own `topics` and `group_id`. |

---

## 9. Event Types and Handlers Cheat Sheet (Reference)

| Event Type           | Published By     | Topic            | Celery Tasks Dispatched |
|----------------------|------------------|------------------|--------------------------|
| user.registered      | user-service     | user.events      | send_welcome_email, create_in_app_notification |
| course.published      | course-service   | course.events    | send_enrollment_confirmation, create_in_app_notification |
| course.archived      | course-service   | course.events    | create_in_app_notification |
| enrollment.created   | course-service   | enrollment.events| send_enrollment_confirmation, create_in_app_notification |
| enrollment.dropped   | course-service   | enrollment.events| create_in_app_notification |
| enrollment.completed | course-service   | enrollment.events| send_course_completion_email, create_in_app_notification |
| certificate.issued   | course-service   | course.events    | send_certificate_ready_email, create_in_app_notification, generate_certificate_pdf |
| certificate.revoked  | course-service   | course.events    | create_in_app_notification |

---

## 10. Quick Reference: File Locations

| What | Path |
|------|------|
| Kafka producer | `core_service/providers/kafka/producer.py` |
| Kafka consumer | `core_service/providers/kafka/consumer.py` |
| Schema Registry client | `core_service/providers/kafka/schema_registry.py` |
| Event envelope | `core_service/events/envelope.py` |
| Topics | `core_service/providers/kafka/topics.py` |
| Celery app | `notification_service/worker.py` |
| Celery tasks | `notification_service/tasks/{email,notification,certificate}.py` |
| Event handlers | `notification_service/consumers/event_handlers.py` |
| Kafka consumer entry | `notification_service/consumers/kafka_consumer.py` |
| User registration + publish | `user_service/api/auth.py` |
| Course enrollment + publish | `course_service/api/enrollments.py` |

---

## 11. Concepts to Remember

1. **Kafka = events, RabbitMQ = tasks.** Use Kafka to broadcast “what happened,” RabbitMQ/Celery to run “do this job.”
2. **Schema Registry** stores the message schema (we use one for `EventEnvelope`) so producers and consumers stay in sync.
3. **EventEnvelope** is the shared wrapper; `event_type` and `payload` define what happened.
4. **Notification service** is the bridge: consume from Kafka, enqueue Celery tasks, let workers do the work.
5. **send_task()** is fire-and-forget; the HTTP/Kafka path returns quickly while tasks run in the background.
6. **Retries:** Celery tasks use `max_retries=3` and exponential backoff (`60 * 2^retries` seconds).

---

*Guide created for SmartCourse. Last updated: February 2026.*
