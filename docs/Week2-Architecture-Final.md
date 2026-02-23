# SmartCourse Week 2: Final Event-Driven Architecture

**Date:** February 22, 2026  
**Status:** Approved Architecture  
**Purpose:** Definitive guide for implementing event-driven microservices

---

## Table of Contents

1. [The Problem We Solved](#1-the-problem-we-solved)
2. [Final Architecture](#2-final-architecture)
3. [What Goes Where](#3-what-goes-where)
4. [Celery Tasks Deep Dive](#4-celery-tasks-deep-dive)
5. [Complete Event Flow Examples](#5-complete-event-flow-examples)
6. [Folder Structure](#6-folder-structure)

---

## 1. The Problem We Solved

### Original Issue: `core` as a Shared Library Breaks Microservices

```
❌ ANTI-PATTERN (What we had):
user-service ──imports──► core_service (library)
course-service ──imports──► core_service (library)
notification-service ──imports──► core_service (library)

Problem: Change EventProducer in core → Rebuild ALL services
         This is tight coupling disguised as code reuse.
```

### Resolution: Proper Separation

```
✓ CORRECT PATTERN (What we're doing):

shared/              ← Library: Stable, minimal code (Kafka, schemas, utils)
core-service/        ← Real microservice: Temporal workflows (future)
notification-service ← Real microservice: Celery tasks + event handling
user-service         ← Real microservice: Just publishes events
course-service       ← Real microservice: Just publishes events
```

**Key Insight:** `shared/` contains **infrastructure glue code** that:

- Is very stable (changes maybe once a year)
- Is not business logic
- Needs to be consistent across services (message formats, topic names)

---

## 2. Final Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              SMARTCOURSE ARCHITECTURE                                    │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           shared/ (Python Library)                                       │
│                     Dependency of ALL microservices                                      │
│                                                                                          │
│   kafka/                          schemas/                    utils/                     │
│   ├── producer.py                 ├── envelope.py             ├── datetime.py           │
│   ├── consumer.py                 ├── pagination.py           └── ...                   │
│   ├── topics.py                   └── events/                                           │
│   └── schema_registry.py              ├── user.py             exceptions/               │
│                                       ├── course.py           └── common.py             │
│                                       └── enrollment.py                                 │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                    │                    │                      │
        ┌───────────┴───────┐   ┌────────┴────────┐   ┌────────┴─────────┐
        ▼                   ▼   ▼                 ▼   ▼                  ▼
┌───────────────────┐  ┌───────────────────┐  ┌───────────────────────────────┐
│   user-service    │  │  course-service   │  │    notification-service       │
│                   │  │                   │  │                               │
│ Publishes events: │  │ Publishes events: │  │ Consumes events from Kafka    │
│ • user.registered │  │ • course.published│  │ Dispatches to Celery/RabbitMQ │
│ • user.login      │  │ • enrollment.*    │  │ Runs Celery worker            │
│ • user.updated    │  │ • certificate.*   │  │                               │
│                   │  │ • progress.*      │  │ tasks/                        │
│ NO Celery code    │  │                   │  │ ├── email.py                  │
│ NO RabbitMQ code  │  │ NO Celery code    │  │ ├── notification.py           │
│                   │  │ NO RabbitMQ code  │  │ └── certificate.py            │
└───────────────────┘  └───────────────────┘  └───────────────────────────────┘
         │                      │                           │
         │ publish              │ publish                   │ consume
         └──────────┬───────────┘                           │
                    │                                       │
                    ▼                                       ▼
             ┌─────────────┐                    ┌───────────────────┐
             │    KAFKA    │───────────────────►│ Event Handlers    │
             │             │                    │ (what task to run)│
             │ Topics:     │                    └─────────┬─────────┘
             │ • user.*    │                              │
             │ • course.*  │                              │ send_task()
             │ • enroll.*  │                              ▼
             └─────────────┘                    ┌─────────────────────┐
                                               │     RABBITMQ        │
                                               │                     │
                                               │ Queues:             │
                                               │ • email_queue       │
                                               │ • notification_queue│
                                               │ • certificate_queue │
                                               └─────────┬───────────┘
                                                         │
                                                         ▼
                                               ┌─────────────────────┐
                                               │   CELERY WORKER     │
                                               │                     │
                                               │ Executes tasks from │
                                               │ notification-service│
                                               └─────────────────────┘


┌───────────────────┐
│   core-service    │  ← Future: Temporal workflows for multi-step processes
│   (Real Service)  │     • EnrollmentWorkflow
│                   │     • CoursePublishingWorkflow
│   NOT a library!  │     • CertificateGenerationWorkflow
└───────────────────┘
```

---

## 3. What Goes Where

### Summary Table

| What                   | Where                             | Why                                    |
| ---------------------- | --------------------------------- | -------------------------------------- |
| `EventProducer`        | `shared/kafka/producer.py`        | Single source of truth, stable code    |
| `EventConsumer`        | `shared/kafka/consumer.py`        | Single source of truth, stable code    |
| `Topics`               | `shared/kafka/topics.py`          | Consistent topic names across services |
| `EventEnvelope`        | `shared/schemas/envelope.py`      | Contract all services must follow      |
| Event payloads         | `shared/schemas/events/*.py`      | Type-safe event data                   |
| Pagination             | `shared/schemas/pagination.py`    | Common utility                         |
| Exceptions             | `shared/exceptions/common.py`     | Consistent error handling              |
| **Celery tasks**       | `notification-service/tasks/`     | Business logic for background work     |
| **Celery worker**      | `notification-service/worker.py`  | Service-specific configuration         |
| **Event handlers**     | `notification-service/consumers/` | Event → Task mapping                   |
| **Temporal workflows** | `core-service/temporal/`          | Future: multi-step orchestration       |

### Why user-service & course-service Don't Need Celery

They just **publish events** and return immediately. They don't care what happens after:

```python
# course-service publishes event, doesn't wait for PDF generation
await producer.publish(
    topic=Topics.ENROLLMENT,
    event_type="certificate.issued",
    payload={...}
)
return certificate  # Returns immediately
```

**notification-service decides** what tasks to trigger based on events.

---

## 4. Celery Tasks Deep Dive

### What is a Celery Task?

A Celery task is a Python function decorated with `@celery_app.task` that:

- Runs **asynchronously** in a worker process
- Is triggered via a **message queue** (RabbitMQ)
- Has **automatic retry** on failure
- Can be **monitored** and **tracked**

### Task Queues in SmartCourse

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              RABBITMQ QUEUES                                             │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│   email_queue                                                                            │
│   ├── send_welcome_email          (user.registered → welcome email)                     │
│   ├── send_enrollment_confirmation (enrollment.created → confirmation email)            │
│   ├── send_course_completion_email (enrollment.completed → congrats email)              │
│   └── send_certificate_ready_email (certificate.issued → certificate email)             │
│                                                                                          │
│   notification_queue                                                                     │
│   ├── create_in_app_notification  (any event → in-app notification)                     │
│   └── send_push_notification      (future: mobile push)                                 │
│                                                                                          │
│   certificate_queue                                                                      │
│   └── generate_certificate_pdf    (certificate.issued → PDF generation)                 │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### All Celery Tasks (Current + Planned)

#### Email Tasks (`notification-service/tasks/email.py`)

```python
@celery_app.task(bind=True, max_retries=3, name="notification_service.tasks.email.send_welcome_email")
def send_welcome_email(self, user_id: int, email: str, first_name: str):
    """
    Triggered by: user.registered event
    Purpose: Send welcome email to new user
    Retry: 3 times with exponential backoff (60s, 120s, 240s)
    """
    try:
        email_service.send(
            to=email,
            subject=f"Welcome to SmartCourse, {first_name}!",
            template="welcome",
            context={"first_name": first_name}
        )
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(bind=True, max_retries=3, name="notification_service.tasks.email.send_enrollment_confirmation")
def send_enrollment_confirmation(self, student_id: int, course_id: int, course_title: str, email: str):
    """
    Triggered by: enrollment.created event
    Purpose: Confirm student's enrollment in a course
    """
    email_service.send(
        to=email,
        subject=f"Enrollment Confirmed: {course_title}",
        template="enrollment_confirmation",
        context={"course_title": course_title}
    )


@celery_app.task(bind=True, max_retries=3, name="notification_service.tasks.email.send_course_completion_email")
def send_course_completion_email(self, student_id: int, course_id: int, course_title: str, email: str):
    """
    Triggered by: enrollment.completed event
    Purpose: Congratulate student on completing a course
    """
    email_service.send(
        to=email,
        subject=f"Congratulations! You completed {course_title}",
        template="course_completion",
        context={"course_title": course_title}
    )


@celery_app.task(bind=True, max_retries=3, name="notification_service.tasks.email.send_certificate_ready_email")
def send_certificate_ready_email(self, student_id: int, certificate_number: str, verification_code: str, email: str):
    """
    Triggered by: certificate.issued event
    Purpose: Notify student their certificate is ready for download
    """
    email_service.send(
        to=email,
        subject=f"Your Certificate is Ready! #{certificate_number}",
        template="certificate_ready",
        context={
            "certificate_number": certificate_number,
            "verification_code": verification_code
        }
    )
```

#### Notification Tasks (`notification-service/tasks/notification.py`)

```python
@celery_app.task(bind=True, max_retries=3, name="notification_service.tasks.notification.create_in_app_notification")
def create_in_app_notification(self, user_id: int, title: str, message: str, notification_type: str = "system"):
    """
    Triggered by: Any event that needs in-app notification
    Purpose: Create a notification visible in user's dashboard

    Types:
    - welcome: New user welcome
    - enrollment: Enrollment status changes
    - progress: Course progress milestones
    - certificate: Certificate issued
    - course_published: Instructor's course went live
    - system: System announcements
    """
    notification_service.create(
        user_id=user_id,
        title=title,
        message=message,
        type=notification_type,
        read=False
    )


@celery_app.task(bind=True, max_retries=3, name="notification_service.tasks.notification.send_push_notification")
def send_push_notification(self, user_id: int, title: str, body: str, data: dict = None):
    """
    Future: Send push notification to mobile device
    Requires: FCM/APNs integration
    """
    push_service.send(
        user_id=user_id,
        title=title,
        body=body,
        data=data or {}
    )
```

#### Certificate Tasks (`notification-service/tasks/certificate.py`)

```python
@celery_app.task(bind=True, max_retries=3, name="notification_service.tasks.certificate.generate_certificate_pdf")
def generate_certificate_pdf(
    self,
    certificate_id: int,
    student_name: str,
    course_title: str,
    certificate_number: str,
    issued_date: str,
    instructor_name: str
):
    """
    Triggered by: certificate.issued event
    Purpose: Generate a downloadable PDF certificate

    Steps:
    1. Load certificate template (HTML/Jinja2)
    2. Render with student/course data
    3. Convert to PDF (weasyprint/reportlab)
    4. Upload to S3/MinIO
    5. Update certificate record with PDF URL
    """
    try:
        # Render HTML template
        html = render_template("certificate.html", {
            "student_name": student_name,
            "course_title": course_title,
            "certificate_number": certificate_number,
            "issued_date": issued_date,
            "instructor_name": instructor_name
        })

        # Convert to PDF
        pdf_bytes = html_to_pdf(html)

        # Upload to storage
        pdf_url = storage.upload(
            bucket="certificates",
            key=f"{certificate_number}.pdf",
            data=pdf_bytes,
            content_type="application/pdf"
        )

        # Update certificate record
        certificate_service.update_pdf_url(certificate_id, pdf_url)

        return {"pdf_url": pdf_url}

    except Exception as exc:
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
```

### Task Retry Strategy

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                            RETRY STRATEGY (Exponential Backoff)                          │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│   Attempt 1: Execute immediately                                                         │
│              ↓ FAIL                                                                       │
│   Wait 60 seconds                                                                        │
│              ↓                                                                            │
│   Attempt 2: Retry                                                                       │
│              ↓ FAIL                                                                       │
│   Wait 120 seconds (60 * 2^1)                                                            │
│              ↓                                                                            │
│   Attempt 3: Retry                                                                       │
│              ↓ FAIL                                                                       │
│   Wait 240 seconds (60 * 2^2)                                                            │
│              ↓                                                                            │
│   Attempt 4: Final retry                                                                 │
│              ↓ FAIL                                                                       │
│   → Move to Dead Letter Queue (DLQ) for manual inspection                                │
│                                                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### Event → Task Mapping

This is where the magic happens. The event handlers in notification-service decide what tasks to trigger for each event:

```python
# notification-service/consumers/event_handlers.py

class NotificationEventHandlers:
    """Maps Kafka events to Celery tasks."""

    def __init__(self):
        self._handlers = {
            "user.registered": self._on_user_registered,
            "course.published": self._on_course_published,
            "enrollment.created": self._on_enrollment_created,
            "enrollment.completed": self._on_enrollment_completed,
            "certificate.issued": self._on_certificate_issued,
        }

    async def handle(self, topic: str, event: EventEnvelope):
        handler = self._handlers.get(event.event_type)
        if handler:
            await handler(event)

    # ─────────────────────────────────────────────────────────────
    #  EVENT HANDLERS
    # ─────────────────────────────────────────────────────────────

    async def _on_user_registered(self, event: EventEnvelope):
        """User registered → 2 tasks"""
        p = event.payload

        # Task 1: Welcome email
        celery_app.send_task(
            "notification_service.tasks.email.send_welcome_email",
            kwargs={"user_id": p["user_id"], "email": p["email"], "first_name": p["first_name"]},
            queue="email_queue"
        )

        # Task 2: In-app welcome notification
        celery_app.send_task(
            "notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["user_id"],
                "title": "Welcome to SmartCourse!",
                "message": f"Hi {p['first_name']}! Start exploring courses.",
                "notification_type": "welcome"
            },
            queue="notification_queue"
        )

    async def _on_enrollment_created(self, event: EventEnvelope):
        """Enrollment created → 2 tasks"""
        p = event.payload

        # Task 1: Confirmation email
        celery_app.send_task(
            "notification_service.tasks.email.send_enrollment_confirmation",
            kwargs={
                "student_id": p["student_id"],
                "course_id": p["course_id"],
                "course_title": p["course_title"],
                "email": p["email"]
            },
            queue="email_queue"
        )

        # Task 2: In-app notification
        celery_app.send_task(
            "notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["student_id"],
                "title": "Enrollment Confirmed!",
                "message": f"You're enrolled in '{p['course_title']}'.",
                "notification_type": "enrollment"
            },
            queue="notification_queue"
        )

    async def _on_certificate_issued(self, event: EventEnvelope):
        """Certificate issued → 3 tasks"""
        p = event.payload

        # Task 1: Certificate ready email
        celery_app.send_task(
            "notification_service.tasks.email.send_certificate_ready_email",
            kwargs={
                "student_id": p["student_id"],
                "certificate_number": p["certificate_number"],
                "verification_code": p["verification_code"],
                "email": p["email"]
            },
            queue="email_queue"
        )

        # Task 2: In-app notification
        celery_app.send_task(
            "notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": p["student_id"],
                "title": "Certificate Ready!",
                "message": f"Your certificate #{p['certificate_number']} is ready.",
                "notification_type": "certificate"
            },
            queue="notification_queue"
        )

        # Task 3: Generate PDF
        celery_app.send_task(
            "notification_service.tasks.certificate.generate_certificate_pdf",
            kwargs={
                "certificate_id": p["certificate_id"],
                "student_name": p["student_name"],
                "course_title": p["course_title"],
                "certificate_number": p["certificate_number"],
                "issued_date": p["issued_date"],
                "instructor_name": p["instructor_name"]
            },
            queue="certificate_queue"
        )
```

---

## 5. Complete Event Flow Examples

### Example 1: User Registration

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              USER REGISTRATION FLOW                                      │
└─────────────────────────────────────────────────────────────────────────────────────────┘

     ① POST /register                ② Create user in DB
              │                                │
              ▼                                ▼
        ┌──────────┐                  ┌──────────────────┐
        │  Client  │─────────────────►│   user-service   │
        └──────────┘                  │                  │
                                      │ 1. Hash password │
                                      │ 2. Save to DB    │
                                      │ 3. Publish event │
                                      └────────┬─────────┘
                                               │
                        ③ Kafka event          │
                           published           │
                                               ▼
                                      ┌──────────────────┐
                                      │      KAFKA       │
                                      │  topic: user.*   │
                                      │                  │
                                      │ {                │
                                      │   "event_type":  │
                                      │   "user.registered",
                                      │   "payload": {   │
                                      │     "user_id": 1,│
                                      │     "email": ... │
                                      │   }              │
                                      │ }                │
                                      └────────┬─────────┘
                                               │
                        ④ Consumer             │
                           receives            │
                                               ▼
                                      ┌──────────────────┐
                                      │notification-svc  │
                                      │ (Kafka consumer) │
                                      │                  │
                                      │ Event handler:   │
                                      │ _on_user_registered
                                      └────────┬─────────┘
                                               │
                        ⑤ Dispatch             │
                           2 tasks             │
                                               ▼
                                      ┌──────────────────┐
                                      │    RABBITMQ      │
                                      │                  │
                                      │ email_queue:     │
                                      │  [send_welcome]  │
                                      │                  │
                                      │ notification_q:  │
                                      │  [create_notif]  │
                                      └────────┬─────────┘
                                               │
                        ⑥ Worker               │
                           executes            │
                                               ▼
                                      ┌──────────────────┐
                                      │  Celery Worker   │
                                      │                  │
                                      │ ✓ Send email     │
                                      │ ✓ Create notif   │
                                      └──────────────────┘
```

### Example 2: Certificate Issuance

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                            CERTIFICATE ISSUANCE FLOW                                     │
└─────────────────────────────────────────────────────────────────────────────────────────┘

Student completes final module
              │
              ▼
┌──────────────────────┐
│   course-service     │
│                      │
│ 1. Mark enrollment   │
│    completed         │
│ 2. Create cert       │
│    record in DB      │
│ 3. Publish event     │────────► Kafka: certificate.issued
│                      │                     │
│ Returns immediately  │                     │
│ (no wait for PDF)    │                     │
└──────────────────────┘                     │
                                             ▼
                                    ┌──────────────────┐
                                    │notification-svc  │
                                    │                  │
                                    │ _on_certificate_ │
                                    │ issued()         │
                                    │                  │
                                    │ Dispatches 3     │
                                    │ tasks:           │
                                    └────────┬─────────┘
                                             │
                    ┌────────────────────────┼────────────────────────┐
                    │                        │                        │
                    ▼                        ▼                        ▼
           ┌──────────────┐         ┌──────────────┐         ┌──────────────┐
           │ email_queue  │         │ notif_queue  │         │ cert_queue   │
           │              │         │              │         │              │
           │send_cert_    │         │create_notif  │         │generate_pdf  │
           │ready_email   │         │              │         │              │
           └──────┬───────┘         └──────┬───────┘         └──────┬───────┘
                  │                        │                        │
                  ▼                        ▼                        ▼
         ┌──────────────────────────────────────────────────────────────────┐
         │                      Celery Worker                                │
         │                                                                   │
         │  Task 1: Send email               (fast, ~1 second)              │
         │  Task 2: Create notification      (fast, ~100ms)                 │
         │  Task 3: Generate PDF + Upload    (slow, ~5-10 seconds)          │
         │                                                                   │
         │  All tasks run in PARALLEL (independent)                         │
         └──────────────────────────────────────────────────────────────────┘
```

---

## 6. Folder Structure

### Final Project Structure

```
smart-course/
├── docker-compose.yml
├── .env
│
├── shared/                              # ← LIBRARY (dependency)
│   ├── pyproject.toml
│   └── src/
│       └── shared/
│           ├── __init__.py
│           ├── kafka/
│           │   ├── __init__.py
│           │   ├── producer.py          # EventProducer
│           │   ├── consumer.py          # EventConsumer
│           │   ├── topics.py            # Topic constants
│           │   └── schema_registry.py
│           ├── schemas/
│           │   ├── __init__.py
│           │   ├── envelope.py          # EventEnvelope
│           │   ├── pagination.py        # PaginationParams
│           │   └── events/
│           │       ├── __init__.py
│           │       ├── user.py          # UserRegisteredPayload
│           │       ├── course.py        # CoursePublishedPayload
│           │       └── enrollment.py    # EnrollmentCreatedPayload
│           ├── exceptions/
│           │   └── common.py            # NotFoundError, etc.
│           └── utils/
│               └── datetime.py
│
├── services/
│   │
│   ├── user-service/                    # ← MICROSERVICE
│   │   ├── Dockerfile
│   │   ├── pyproject.toml               # depends on shared
│   │   └── src/user_service/
│   │       ├── main.py                  # FastAPI app + EventProducer
│   │       └── api/
│   │           └── auth.py              # Publishes user.registered
│   │
│   ├── course-service/                  # ← MICROSERVICE
│   │   ├── Dockerfile
│   │   ├── pyproject.toml               # depends on shared
│   │   └── src/
│   │       └── api/
│   │           ├── enrollments.py       # Publishes enrollment.*
│   │           └── certificates.py      # Publishes certificate.*
│   │
│   ├── notification-service/            # ← MICROSERVICE (Kafka + Celery)
│   │   ├── Dockerfile
│   │   ├── pyproject.toml               # depends on shared
│   │   └── src/notification_service/
│   │       ├── main.py                  # FastAPI + Kafka consumer
│   │       ├── worker.py                # Celery app config
│   │       ├── consumers/
│   │       │   ├── kafka_consumer.py    # Runs EventConsumer
│   │       │   └── event_handlers.py    # Event → Task mapping
│   │       ├── tasks/
│   │       │   ├── email.py             # Email tasks
│   │       │   ├── notification.py      # In-app notification tasks
│   │       │   └── certificate.py       # PDF generation task
│   │       └── mocks/                   # Mock services (logs only)
│   │
│   └── core-service/                    # ← MICROSERVICE (Future: Temporal)
│       ├── Dockerfile
│       ├── pyproject.toml
│       └── src/core_service/
│           ├── main.py                  # FastAPI health check
│           └── temporal/                # Future
│               ├── client.py
│               ├── workflows/
│               └── activities/
│
└── docs/
```

---

## Summary

| Component              | Type         | Responsibility                                 |
| ---------------------- | ------------ | ---------------------------------------------- |
| `shared/`              | Library      | Kafka code, event schemas, common utils        |
| `user-service`         | Microservice | User CRUD, publishes user events               |
| `course-service`       | Microservice | Course/enrollment CRUD, publishes events       |
| `notification-service` | Microservice | Kafka consumer + Celery task dispatch + worker |
| `core-service`         | Microservice | Future: Temporal workflows                     |

### Key Principles

1. **Services publish events, don't execute tasks** — user-service and course-service just publish to Kafka
2. **notification-service is the task orchestrator** — it decides what tasks to run for each event
3. **Celery tasks are isolated, retriable units of work** — email, notification, PDF generation
4. **shared/ contains stable infrastructure code** — acceptable coupling for Kafka/schema consistency
5. **core-service is for Temporal (future)** — multi-step workflows with compensation

### The Flow

```
Service Action → Kafka Event → Event Handler → Celery Task → Worker Execution
```

This architecture gives you:

- **Independent deployability** (services don't import business logic from each other)
- **Fault tolerance** (Celery retries failed tasks)
- **Scalability** (scale workers independently)
- **Auditability** (Kafka stores events for replay)
