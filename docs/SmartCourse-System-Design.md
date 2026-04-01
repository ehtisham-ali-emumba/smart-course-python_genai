# SmartCourse — System Design Document

**Version:** 3.0
**Last Updated:** April 1, 2026
**Author:** SmartCourse Architecture Team
**Status:** Living Document
**Scope:** Complete System Architecture — Microservices, Event-Driven, AI/ML

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Decisions Record](#2-architecture-decisions-record)
3. [High-Level Architecture](#3-high-level-architecture)
4. [Service Specifications](#4-service-specifications)
5. [Communication Patterns](#5-communication-patterns)
6. [Data Architecture](#6-data-architecture)
7. [Workflow Orchestration](#7-workflow-orchestration)
8. [AI / ML Architecture](#8-ai--ml-architecture)
9. [Infrastructure Components](#9-infrastructure-components)
10. [Security Architecture](#10-security-architecture)
11. [Observability](#11-observability)
12. [Failure Handling & Resilience](#12-failure-handling--resilience)
13. [Deployment Architecture](#13-deployment-architecture)

---

## 1. System Overview

SmartCourse is a distributed, event-driven microservices platform for intelligent course delivery. The system combines traditional CRUD services with AI-powered content generation, RAG-based tutoring, and workflow orchestration to provide a comprehensive e-learning experience.

### 1.1 Design Principles

| Principle | Application |
|-----------|-------------|
| **Single Responsibility** | Each service owns one bounded context (users, courses, AI, etc.) |
| **Event-Driven** | Services communicate asynchronously via Kafka; synchronous calls only where latency-critical |
| **Workflow as Code** | Multi-step business processes orchestrated through Temporal, not ad-hoc service chains |
| **Polyglot Persistence** | PostgreSQL for relational data, MongoDB for documents, Qdrant for vectors, Redis for cache |
| **Gateway Pattern** | Single entry point (Nginx) handles auth, rate limiting, and routing |
| **Shared Nothing** | Each service owns its database; no shared DB access across services |

### 1.2 Service Inventory

| Service | Port | Technology | Database | Purpose |
|---------|------|------------|----------|---------|
| **API Gateway** | 8000 | Nginx + Python Sidecar | — | Reverse proxy, JWT auth, rate limiting |
| **User Service** | 8001 | FastAPI | PostgreSQL, Redis | Auth, profiles, JWT generation |
| **Course Service** | 8002 | FastAPI | PostgreSQL, MongoDB, Redis | Courses, enrollments, progress, certificates, quizzes |
| **Notification Service** | 8005 | FastAPI + Celery | RabbitMQ, Redis | Email, in-app notifications, certificate PDF generation |
| **Core Service** | 8006 | FastAPI + Temporal Worker | — (stateless) | Workflow execution engine (enrollment, publish, RAG indexing) |
| **AI Service** | 8009 | FastAPI + LangGraph | MongoDB, Qdrant, Redis | RAG indexing, AI tutor, quiz/summary generation |

> **Note:** Enrollment, Progress, and Certificate are **not** separate services — they are modules within the Course Service (single deployable unit).

---

## 2. Architecture Decisions Record

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| ADR-01 | **API Gateway** | Nginx reverse proxy + Python auth sidecar | Nginx handles high-throughput proxying; sidecar handles JWT verification via `auth_request` directive |
| ADR-02 | **JWT Algorithm** | HS256 (symmetric) | Simpler key management; sufficient for internal services behind a single gateway |
| ADR-03 | **JWT Verification** | API Gateway only | Single point of authentication; downstream services trust `X-Auth-*` headers set by gateway |
| ADR-04 | **Event Streaming** | Apache Kafka + Schema Registry | Durable, ordered, replayable event log for cross-service communication |
| ADR-05 | **Task Queue** | RabbitMQ + Celery | Background job execution for emails, notifications, certificate PDF generation |
| ADR-06 | **Workflow Engine** | Temporal | Durable, retryable, observable orchestration of multi-step business processes |
| ADR-07 | **AI Framework** | LangGraph + LangChain | State-machine-based agent orchestration for RAG, quiz generation, tutoring |
| ADR-08 | **Vector Database** | Qdrant | Purpose-built for similarity search; supports filtered vector queries with metadata |
| ADR-09 | **File Storage** | AWS S3 | Managed object storage for course materials, thumbnails, certificate PDFs |
| ADR-10 | **Dependencies** | pyproject.toml per service | Modern Python packaging standard; no requirements.txt |
| ADR-11 | **Shared Code** | `shared/` editable package | Reusable Kafka, Temporal, S3, schema, and exception modules installed in all services |
| ADR-12 | **Containerization** | Dockerfile per service + root docker-compose | Each service independently buildable; single-command full-stack orchestration |
| ADR-13 | **File Naming** | No folder prefix | e.g., `repositories/user.py` NOT `repositories/user_repository.py` |

---

## 3. High-Level Architecture

```
                        ╔══════════════════════════════════════════════════╗
                        ║       SMARTCOURSE — SYSTEM ARCHITECTURE          ║
                        ╚══════════════════════════════════════════════════╝


                               ┌───────────────────────┐
                               │       CLIENTS          │
                               │    Web  ·  Mobile      │
                               └───────────┬───────────┘
                                           │ HTTPS
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│  GATEWAY LAYER                                                                   │
│                                                                                  │
│   ┌────────────────────────────────────────────────────────────────────────┐     │
│   │              NGINX REVERSE PROXY  (:8000 — only public port)          │     │
│   │                                                                        │     │
│   │   Rate         CORS          Routing        Static       Health       │     │
│   │   Limiting     Headers       Rules          Assets       Check        │     │
│   │                                                                        │     │
│   │         ┌──────────────────────────────────┐                           │     │
│   │         │  AUTH SIDECAR (FastAPI :8010)     │                           │     │
│   │         │  JWT verify via auth_request      │                           │     │
│   │         │  Sets: X-Auth-User-ID             │                           │     │
│   │         │        X-Auth-User-Role            │                           │     │
│   │         │        X-Auth-Profile-ID           │                           │     │
│   │         └──────────────────────────────────┘                           │     │
│   └────────────────────────────────────────────────────────────────────────┘     │
│                                                                                  │
└──────────────────────────┬───────────────────────────────────────────────────────┘
                           │  Internal REST (trusted, no JWT re-verification)
          ┌────────────────┼────────────────────────────────┐
          ▼                ▼                                ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│  SERVICES LAYER                                                                  │
│                                                                                  │
│   ┌─────────────────────┐    ┌───────────────────────────────────────────┐       │
│   │   USER SERVICE      │    │           COURSE SERVICE                   │       │
│   │      :8001          │    │              :8002                         │       │
│   │                     │    │                                            │       │
│   │  · Registration     │    │  · Course CRUD       · Enrollments        │       │
│   │  · Login / Auth     │    │  · Content (MongoDB)  · Progress          │       │
│   │  · JWT Generation   │    │  · Publishing         · Certificates      │       │
│   │  · Profile CRUD     │    │  · Quiz Attempts      · File Uploads (S3) │       │
│   │  · Roles (student/  │    │                                            │       │
│   │    instructor)      │    │  (Course + Enrollment + Progress +        │       │
│   │                     │    │   Certificate + Quiz — single deployable)  │       │
│   └─────────────────────┘    └───────────────────────────────────────────┘       │
│                                                                                  │
│   ┌─────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐   │
│   │ NOTIFICATION SVC    │  │   CORE SERVICE       │  │     AI SERVICE       │   │
│   │      :8005          │  │      :8006           │  │        :8009         │   │
│   │                     │  │                      │  │                      │   │
│   │  · Email (Celery)   │  │  · Temporal Worker   │  │  · RAG Indexing      │   │
│   │  · In-App Notifs    │  │  · EnrollmentWF      │  │  · AI Tutor (Q&A)    │   │
│   │  · Cert PDF Gen     │  │  · CoursePublishWF   │  │  · Quiz Generation   │   │
│   │  · Kafka Consumer   │  │  · RAG Indexing      │  │  · Summary Gen       │   │
│   │                     │  │    Child WF          │  │  · Content Pipeline  │   │
│   │                     │  │                      │  │  · LangGraph Agents  │   │
│   └─────────────────────┘  └──────────────────────┘  └──────────────────────┘   │
│                                                                                  │
└──────────────────────────┬───────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│  EVENT & WORKFLOW LAYER                                                          │
│                                                                                  │
│   ┌───────────────────────────┐    ┌─────────────────────────────────────────┐   │
│   │   KAFKA  (Event Bus)      │    │   TEMPORAL  (Workflow Orchestrator)      │   │
│   │   + Schema Registry       │    │                                          │   │
│   │                           │    │   Workflows:                             │   │
│   │   Topics (3 partitions):  │    │    · EnrollmentWorkflow                 │   │
│   │    · user.events          │    │    · CoursePublishWorkflow              │   │
│   │    · course.events        │    │    · CourseRagIndexingChildWorkflow     │   │
│   │    · enrollment.events    │    │                                          │   │
│   │    · progress.events      │    │   Task Queue: "core-service"            │   │
│   │    · notification.events  │    │   Namespace:  "default"                 │   │
│   │    · ai.events            │    │   Persistence: PostgreSQL               │   │
│   │                           │    │   UI: :8080                              │   │
│   └───────────────────────────┘    └─────────────────────────────────────────┘   │
│                                                                                  │
│   ┌───────────────────────────┐                                                  │
│   │   CELERY + RABBITMQ       │                                                  │
│   │   (Background Tasks)      │                                                  │
│   │                           │                                                  │
│   │   Queues:                 │                                                  │
│   │    · email_queue          │                                                  │
│   │    · notification_queue   │                                                  │
│   │    · certificate_queue    │                                                  │
│   │                           │                                                  │
│   │   Backend: Redis          │                                                  │
│   │   Serialization: JSON     │                                                  │
│   └───────────────────────────┘                                                  │
│                                                                                  │
└──────────────────────────┬───────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│  DATA LAYER                                                                      │
│                                                                                  │
│   ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────┐ ┌────────────┐ │
│   │ POSTGRESQL   │ │   MONGODB    │ │    REDIS     │ │AWS S3  │ │   QDRANT   │ │
│   │   :5432      │ │   :27017     │ │    :6379     │ │        │ │ :6333/:6334│ │
│   │              │ │              │ │              │ │        │ │            │ │
│   │ User Svc DB: │ │ · course_    │ │ · Cache      │ │ · Thumb│ │ · course_  │ │
│   │  · users     │ │   content    │ │ · Celery     │ │   nails│ │   embeddings│
│   │  · student_  │ │ · module_    │ │   backend    │ │ · PDFs │ │            │ │
│   │   profiles   │ │   quizzes    │ │ · Rate       │ │ · Video│ │ · 1536-dim │ │
│   │  · instructor│ │ · module_    │ │   limits     │ │ · Certs│ │ · Cosine   │ │
│   │   _profiles  │ │   summaries  │ │ · Gen status │ │ · Imgs │ │ · Filtered │ │
│   │              │ │              │ │              │ │        │ │   search   │ │
│   │ Course Svc:  │ │              │ │              │ │        │ │            │ │
│   │  · courses   │ │              │ │              │ │        │ │            │ │
│   │  · enroll-   │ │              │ │              │ │        │ │            │ │
│   │    ments     │ │              │ │              │ │        │ │            │ │
│   │  · progress  │ │              │ │              │ │        │ │            │ │
│   │  · certifi-  │ │              │ │              │ │        │ │            │ │
│   │    cates     │ │              │ │              │ │        │ │            │ │
│   │  · quiz_     │ │              │ │              │ │        │ │            │ │
│   │    attempts  │ │              │ │              │ │        │ │            │ │
│   │  · user_     │ │              │ │              │ │        │ │            │ │
│   │    answers   │ │              │ │              │ │        │ │            │ │
│   └──────────────┘ └──────────────┘ └──────────────┘ └────────┘ └────────────┘ │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘


┌──────────────────────────────────────────────────────────────────────────────────┐
│  OBSERVABILITY  (Cross-cutting — monitors all layers)                            │
│                                                                                  │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐   │
│   │  PROMETHEUS  │  │   GRAFANA    │  │   JAEGER     │  │  OPENTELEMETRY    │   │
│   │    :9090     │  │    :3000     │  │              │  │                   │   │
│   │              │  │              │  │              │  │                   │   │
│   │  · Scrape    │  │  · Dashboards│  │  · Traces    │  │ · Auto-instrument │   │
│   │    /metrics  │  │  · Alerting  │  │  · Spans     │  │   FastAPI, SQLAlch│   │
│   │  · 15s       │  │  · Visualize │  │  · Deps      │  │   emy, Redis      │   │
│   │    interval  │  │              │  │              │  │ · Export to Jaeger│   │
│   └──────────────┘  └──────────────┘  └──────────────┘  └───────────────────┘   │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Service Specifications

### 4.1 API Gateway

| Property | Value |
|----------|-------|
| **Port** | 8000 (public), 8010 (auth sidecar — internal only) |
| **Technology** | Nginx reverse proxy + FastAPI auth sidecar |
| **Dockerfiles** | `services/api-gateway/Dockerfile.nginx`, `services/api-gateway/Dockerfile.sidecar` |
| **Config** | `services/api-gateway/nginx.conf`, `services/api-gateway/protected.conf` |
| **Connects To** | All microservices (upstream), Redis (sidecar) |

**Authentication Flow:**

```
Client                    Nginx (:8000)              Auth Sidecar (:8010)         Upstream Service
  │                           │                              │                          │
  │  Authorization: Bearer {JWT}                             │                          │
  │──────────────────────────►│                              │                          │
  │                           │                              │                          │
  │                           │  GET /internal/auth-verify   │                          │
  │                           │  (auth_request directive)    │                          │
  │                           │─────────────────────────────►│                          │
  │                           │                              │                          │
  │                           │                              │ Decode JWT (HS256)       │
  │                           │                              │ Validate expiry          │
  │                           │                              │ Extract claims           │
  │                           │                              │                          │
  │                           │  200 OK                      │                          │
  │                           │  X-Auth-User-ID: {uuid}      │                          │
  │                           │  X-Auth-User-Role: {role}    │                          │
  │                           │  X-Auth-Profile-ID: {uuid}   │                          │
  │                           │◄─────────────────────────────│                          │
  │                           │                              │                          │
  │                           │  Forward request + auth headers                        │
  │                           │────────────────────────────────────────────────────────►│
  │                           │                              │                          │
  │  Response                 │◄───────────────────────────────────────────────────────│
  │◄──────────────────────────│                              │                          │
```

**Rate Limiting (Nginx):**

| Zone | Rate | Burst | Scope |
|------|------|-------|-------|
| `api_general` | 30 req/s | 20 | All protected endpoints |
| `api_auth` | 5 req/s | 10 | `/auth/login`, `/auth/register` |
| `api_refresh` | 2 req/s | — | `/auth/refresh` |

**Routing Table:**

| Route Pattern | Upstream | Auth Required |
|---------------|----------|---------------|
| `POST /auth/register` | user-service:8001 | No |
| `POST /auth/login` | user-service:8001 | No |
| `POST /auth/refresh` | user-service:8001 | No |
| `GET /auth/me`, `/auth/*` | user-service:8001 | Yes |
| `/profile/*`, `/users/*` | user-service:8001 | Yes |
| `/courses/*` | course-service:8002 | Yes |
| `/course/enrollments/*` | course-service:8002 | Yes |
| `/course/certificates/*` | course-service:8002 | Yes |
| `/course/progress/*` | course-service:8002 | Yes |
| `/notifications/*` | notification-service:8005 | Yes |
| `/core/*` | core-service:8006 | Yes |
| `/api/v1/ai/*` | ai-service:8009 | Yes |

---

### 4.2 User Service

| Property | Value |
|----------|-------|
| **Port** | 8001 |
| **Technology** | FastAPI, SQLAlchemy (async), asyncpg |
| **Database** | PostgreSQL (`users`, `student_profiles`, `instructor_profiles`) |
| **Cache** | Redis |
| **Events Published** | `user.registered`, `user.login` on `user.events` topic |
| **Dockerfile** | `services/user-service/Dockerfile` |

**Responsibilities:**
- User registration with password hashing (bcrypt)
- JWT token generation (access + refresh tokens, HS256)
- Token refresh mechanism
- Profile management (role-based: student vs instructor)
- Kafka event publishing on user state changes

**Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | Register new user |
| POST | `/auth/login` | Login, returns access + refresh JWT |
| POST | `/auth/refresh` | Refresh access token |
| GET | `/auth/me` | Get current user from `X-Auth-User-ID` header |
| GET | `/profile/{id}` | Get user profile |
| GET | `/users/{id}` | Get user details |

**Event Payloads Published:**

| Event Type | Topic | Payload |
|------------|-------|---------|
| `user.registered` | `user.events` | `UserRegisteredPayload` (user_id, email, role) |
| `user.login` | `user.events` | `UserLoginPayload` (user_id, timestamp) |

---

### 4.3 Course Service

| Property | Value |
|----------|-------|
| **Port** | 8002 |
| **Technology** | FastAPI, SQLAlchemy (async), Motor (MongoDB), asyncpg |
| **Databases** | PostgreSQL (courses, enrollments, progress, certificates, quiz_attempts, user_answers), MongoDB (course_content, module_quizzes, module_summaries) |
| **Cache** | Redis |
| **Events Published** | `course.*`, `enrollment.*`, `progress.*`, `certificate.*` |
| **Workflows Triggered** | `EnrollmentWorkflow`, `CoursePublishWorkflow` (via Temporal client) |
| **Dockerfile** | `services/course-service/Dockerfile` |

> **Note:** This service merges what were previously separate Course, Enrollment, Progress, and Certificate services into a single deployable unit.

**Responsibilities:**
- Course CRUD with draft/published lifecycle
- Course content management (modules, lessons, resources via MongoDB)
- Student enrollment (triggers Temporal workflow)
- Progress tracking per enrollment
- Certificate issuance with unique verification codes
- Quiz attempt recording and scoring
- File uploads to AWS S3 (thumbnails, materials)

**Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/courses` | Create course (instructor) |
| GET | `/courses` | List courses (paginated, filtered) |
| GET | `/courses/{id}` | Get course details |
| PUT | `/courses/{id}` | Update course (instructor) |
| POST | `/courses/{id}/publish` | Publish course → triggers `CoursePublishWorkflow` |
| GET | `/courses/{id}/content` | Get course content structure (MongoDB) |
| POST | `/course/enrollments` | Enroll in course → triggers `EnrollmentWorkflow` |
| GET | `/course/enrollments` | List enrollments |
| GET | `/course/enrollments/{id}` | Get enrollment details |
| PATCH | `/course/enrollments/{id}` | Update enrollment status (drop/reactivate) |
| GET | `/course/progress/{enrollment_id}` | Get progress |
| POST | `/course/certificates` | Issue certificate |
| GET | `/course/certificates/my` | Get my certificates |
| GET | `/course/certificates/verify/{code}` | Verify certificate by code |
| POST | `/uploads` | Upload course content to S3 |

---

### 4.4 Notification Service

| Property | Value |
|----------|-------|
| **Port** | 8005 |
| **Technology** | FastAPI + Celery workers |
| **Message Queue** | RabbitMQ (broker) + Redis (result backend) |
| **Events Consumed** | `user.events`, `course.events`, `enrollment.events` (via Kafka) |
| **Dockerfile** | `services/notification-service/Dockerfile` |

**Architecture:**

```
                    Kafka Topics
                         │
                         ▼
              ┌─────────────────────┐
              │   Kafka Consumer    │
              │  (background task   │
              │   in FastAPI app)   │
              └──────────┬──────────┘
                         │ event_type dispatch
                         ▼
              ┌─────────────────────┐
              │   Event Handlers    │
              │  (maps events to   │
              │   Celery tasks)     │
              └──────────┬──────────┘
                         │ enqueue
                         ▼
              ┌─────────────────────┐
              │     RabbitMQ        │
              │  ┌───────────────┐  │
              │  │ email_queue   │  │
              │  │ notif_queue   │  │
              │  │ cert_queue    │  │
              │  └───────────────┘  │
              └──────────┬──────────┘
                         │ consume
                         ▼
              ┌─────────────────────┐
              │   Celery Workers    │
              │                     │
              │ · send_welcome_email│
              │ · send_enrollment_  │
              │   confirmation      │
              │ · send_course_      │
              │   completion_email  │
              │ · send_certificate_ │
              │   ready_email       │
              │ · create_in_app_    │
              │   notification      │
              │ · generate_         │
              │   certificate_pdf   │
              └─────────────────────┘
```

**Event → Task Mapping:**

| Kafka Event | Celery Tasks Enqueued | Queue |
|-------------|----------------------|-------|
| `user.registered` | `send_welcome_email`, `create_in_app_notification` | email_queue, notification_queue |
| `enrollment.completed` | `send_course_completion_email`, `create_in_app_notification` | email_queue, notification_queue |
| `certificate.issued` | `send_certificate_ready_email`, `create_in_app_notification`, `generate_certificate_pdf` | email_queue, notification_queue, certificate_queue |

---

### 4.5 Core Service (Temporal Workflow Executor)

| Property | Value |
|----------|-------|
| **Port** | 8006 |
| **Technology** | FastAPI + Temporal SDK (Python) |
| **Type** | Stateless workflow worker — no database |
| **Task Queue** | `core-service` |
| **Temporal Server** | `temporal:7233`, namespace: `default` |
| **Dockerfile** | `services/core/Dockerfile` |

**Responsibilities:**
- Registers and executes Temporal workflow and activity implementations
- Activities make HTTP calls to other services (user-service, course-service, notification-service, ai-service)
- Handles retries, compensation, and step tracking

**Workflows Implemented:**

| Workflow | Trigger | Activities | Details |
|----------|---------|------------|---------|
| `EnrollmentWorkflow` | `POST /course/enrollments` (course-service) | validate_user → fetch_user_details → fetch_course_details → enroll_in_course → trigger_enrollment_notifications | Returns `EnrollmentWorkflowOutput` with step tracking |
| `CoursePublishWorkflow` | `POST /courses/{id}/publish` (course-service) | validate_course → mark_course_published → notify_instructor → start RAG indexing child | Parent close policy: ABANDON on child |
| `CourseRagIndexingChildWorkflow` | Child of `CoursePublishWorkflow` | Calls AI Service `POST /api/v1/ai/index/build` | Runs independently after parent completes |

**Retry Policy:**

```
initial_interval:    1 second
backoff_coefficient: 2.0
maximum_interval:    30 seconds
maximum_attempts:    3
activity_timeout:    60 seconds
```

---

### 4.6 AI Service

| Property | Value |
|----------|-------|
| **Port** | 8009 |
| **Technology** | FastAPI, LangGraph, LangChain, OpenAI SDK |
| **Databases** | MongoDB (read course_content), Qdrant (vector store), Redis (generation status cache) |
| **LLM Provider** | OpenAI — `gpt-4o-mini` (chat), `text-embedding-3-small` (embeddings, 1536-dim) |
| **Dockerfile** | `services/ai-service/Dockerfile` |

**Three Subsystems:**

#### A. RAG Indexing Pipeline

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌──────────┐
│  MongoDB    │    │  Content    │    │   Text      │    │  OpenAI     │    │  Qdrant  │
│  (course_   │───►│  Extractor  │───►│  Chunker    │───►│  Embeddings │───►│  Store   │
│   content)  │    │  (PDF,Video │    │  (semantic) │    │  (1536-dim) │    │          │
│             │    │   Audio,Txt)│    │             │    │             │    │          │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └──────────┘
```

- **ContentExtractor:** Fetches course/module/lessons from MongoDB
- **ContentPipeline:** Processes PDFs (PyMuPDF), video (ffmpeg), audio (pydub), text
- **TextChunker:** Semantic chunking of extracted text
- **Embedding:** OpenAI `text-embedding-3-small` → 1536-dimensional vectors
- **VectorStoreRepository:** Stores in Qdrant `course_embeddings` collection with metadata filters (course_id, module_id, lesson_id)
- **Status Tracking:** Redis cache with TTL for generation status

#### B. AI Tutor (RAG-based Q&A)

```
                    LangGraph State Machine

                    ┌─────────┐
                    │  START  │
                    └────┬────┘
                         │
                         ▼
                    ┌─────────┐     Qdrant vector search
                    │RETRIEVE │────► TOP_K=5, SCORE_THRESHOLD=0.3
                    │         │     Filter by course_id, module_id
                    └────┬────┘
                         │ context_text (joined chunks)
                         ▼
                    ┌─────────┐     ChatOpenAI (gpt-4o-mini)
                    │GENERATE │────► System prompt + context +
                    │         │     conversation_history
                    └────┬────┘
                         │ response + sources
                         ▼
                    ┌─────────┐
                    │   END   │
                    └─────────┘
```

#### C. Instructor Content Generation

- **Quiz Generation:** LangGraph pipeline → structured output → stored in MongoDB `module_quizzes`
- **Summary Generation:** LangGraph pipeline → structured output → stored in MongoDB `module_summaries`

**Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/ai/index/build` | Build vector index for module/course |
| GET | `/api/v1/ai/index/status/{course_id}` | Check indexing status |
| POST | `/api/v1/ai/tutor/ask` | Ask AI tutor a question (RAG) |
| GET | `/api/v1/ai/tutor/history` | Get conversation history |
| POST | `/api/v1/ai/instructor/generate-quiz` | Generate quiz for module |
| POST | `/api/v1/ai/instructor/generate-summary` | Generate module summary |

---

## 5. Communication Patterns

### 5.1 Synchronous Communication (REST)

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                           SYNCHRONOUS CALL MAP                                   │
│                                                                                  │
│                              ┌──────────────┐                                   │
│                              │  API Gateway │                                   │
│                              │    (Nginx)   │                                   │
│                              └──────┬───────┘                                   │
│                    ┌────────────────┼────────────────┬──────────┐               │
│                    ▼                ▼                ▼          ▼               │
│             ┌────────────┐  ┌────────────┐  ┌──────────┐ ┌──────────┐          │
│             │    User    │  │   Course   │  │ Notif.   │ │    AI    │          │
│             │   :8001    │  │   :8002    │  │  :8005   │ │  :8009   │          │
│             └────────────┘  └─────┬──────┘  └──────────┘ └────┬─────┘          │
│                                   │                            │                │
│                          Temporal │                            │ HTTP           │
│                          Client   │                            │ to Course Svc  │
│                                   ▼                            │                │
│                            ┌────────────┐                     │                │
│                            │    Core    │◄────────────────────┘                │
│                            │   :8006    │  (RAG indexing child WF              │
│                            │ (Temporal) │   calls AI service)                  │
│                            └────────────┘                                       │
│                                                                                  │
│  Core Service activities make HTTP calls to:                                    │
│    · User Service    — validate_user, fetch_user_details                        │
│    · Course Service  — fetch_course_details, enroll_in_course,                  │
│                        validate_course, mark_course_published                   │
│    · Notification Svc — trigger_enrollment_notifications                        │
│    · AI Service      — trigger RAG indexing                                     │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

| From | To | Protocol | Endpoint | Purpose |
|------|-----|----------|----------|---------|
| API Gateway | User Service | REST | `/auth/*`, `/users/*`, `/profile/*` | Auth, User CRUD |
| API Gateway | Course Service | REST | `/courses/*`, `/course/*`, `/uploads` | Courses, Enrollments, Progress, Certs |
| API Gateway | Notification Service | REST | `/notifications/*` | Notification management |
| API Gateway | AI Service | REST | `/api/v1/ai/*` | RAG, Tutor, Generation |
| Core Service | User Service | REST | `/users/{id}` | Validate/fetch user (Temporal activity) |
| Core Service | Course Service | REST | `/courses/{id}`, `/course/enrollments` | Validate/fetch course, create enrollment (Temporal activity) |
| Core Service | Notification Service | REST | `/notifications` | Trigger notifications (Temporal activity) |
| Core Service | AI Service | REST | `/api/v1/ai/index/build` | Trigger RAG indexing (child workflow activity) |
| AI Service | Course Service | REST | `/courses/{id}/content` | Fetch course content for indexing |

### 5.2 Asynchronous Communication (Kafka Events)

| Producer | Event Type | Topic | Consumers |
|----------|-----------|-------|-----------|
| User Service | `user.registered` | `user.events` | Notification |
| User Service | `user.login` | `user.events` | — (logging) |
| Course Service | `course.published` | `course.events` | Notification |
| Course Service | `enrollment.created` | `enrollment.events` | Notification |
| Course Service | `enrollment.completed` | `enrollment.events` | Notification |
| Course Service | `enrollment.dropped` | `enrollment.events` | Notification |
| Course Service | `progress.updated` | `progress.events` | — |
| Course Service | `certificate.issued` | `course.events` | Notification |

**Event Envelope Schema (shared library):**

```python
class EventEnvelope(BaseModel):
    event_id: str        # UUID, auto-generated
    event_type: str      # e.g., "user.registered"
    timestamp: datetime  # auto-set
    payload: dict        # service-specific payload
```

### 5.3 Task Queue Communication (Celery)

```
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│  Kafka Event │────────►│   Event      │────────►│  RabbitMQ    │
│  Handler     │         │   Handler    │  enqueue│              │
│ (Notif Svc)  │         │  (dispatch)  │         │ email_queue  │
│              │         │              │         │ notif_queue  │
└──────────────┘         └──────────────┘         │ cert_queue   │
                                                   └──────┬───────┘
                                                          │ consume
                                                          ▼
                                                   ┌──────────────┐
                                                   │ Celery Worker│
                                                   │ (execute)    │
                                                   └──────────────┘
```

---

## 6. Data Architecture

### 6.1 Database Distribution

| Store | Service | Entities | Purpose |
|-------|---------|----------|---------|
| **PostgreSQL** | User Service | `users`, `student_profiles`, `instructor_profiles` | Relational user data with FK constraints |
| **PostgreSQL** | Course Service | `courses`, `enrollments`, `progress`, `certificates`, `quiz_attempts`, `user_answers` | Relational course/enrollment data with FK constraints |
| **PostgreSQL** | Temporal Server | Workflow execution state | Durable workflow persistence |
| **MongoDB** | Course Service | `course_content` (modules/lessons/resources) | Flexible document structure for nested course content |
| **MongoDB** | AI Service | `module_quizzes`, `module_summaries` (read: `course_content`) | AI-generated content storage |
| **Qdrant** | AI Service | `course_embeddings` (1536-dim, cosine) | Vector similarity search for RAG |
| **Redis** | All Services | Cache, rate limits, generation status, Celery results | Low-latency key-value store |

### 6.2 PostgreSQL Schema (User Service)

```
┌───────────────────────────────┐
│            users              │
├───────────────────────────────┤
│ id            UUID PK         │
│ email         VARCHAR UK      │
│ first_name    VARCHAR         │
│ last_name     VARCHAR         │
│ password_hash VARCHAR         │
│ role          VARCHAR         │
│ is_active     BOOLEAN         │
│ is_verified   BOOLEAN         │
│ phone_number  VARCHAR         │
│ created_at    TIMESTAMP       │
│ updated_at    TIMESTAMP       │
└───────────┬───────────────────┘
            │ 1:1 (user_id FK, CASCADE, UNIQUE)
    ┌───────┴───────┐
    ▼               ▼
┌─────────────┐ ┌──────────────────┐
│ student_    │ │ instructor_      │
│ profiles    │ │ profiles         │
├─────────────┤ ├──────────────────┤
│ id       PK │ │ id            PK │
│ user_id  FK │ │ user_id       FK │
│ bio         │ │ bio              │
│ education_  │ │ profile_picture_ │
│  level      │ │  url             │
│ profile_    │ │ phone_number     │
│  picture_url│ │ total_students   │
│ total_      │ │ total_courses    │
│  enrollments│ │ average_rating   │
│ total_      │ │ is_verified_     │
│  completed  │ │  instructor      │
│ created_at  │ │ verification_date│
│ updated_at  │ │ created_at       │
└─────────────┘ │ updated_at       │
                └──────────────────┘
```

### 6.3 PostgreSQL Schema (Course Service)

```
┌─────────────────────────┐
│        courses          │
├─────────────────────────┤      ┌─────────────────────────┐
│ id             UUID PK  │      │      enrollments        │
│ title          VARCHAR  │      ├─────────────────────────┤
│ slug           VARCHAR UK│      │ id            UUID PK   │
│ description    TEXT     │      │ student_id    UUID      │──── logical FK (cross-svc)
│ long_description TEXT   │      │ course_id     UUID FK   │
│ instructor_id  UUID    │──┐   │ status        VARCHAR   │
│ category       VARCHAR  │  │   │ enrolled_at   TIMESTAMP │
│ level          VARCHAR  │  │   │ started_at    TIMESTAMP │
│ language       VARCHAR  │  │   │ completed_at  TIMESTAMP │
│ duration_hours DECIMAL  │  │   │ dropped_at    TIMESTAMP │
│ price          DECIMAL  │  │   │ last_accessed TIMESTAMP │
│ currency       VARCHAR  │  │   │ payment_status VARCHAR  │
│ thumbnail_url  VARCHAR  │  │   │ payment_amount DECIMAL  │
│ status         VARCHAR  │  │   │ enrollment_source VARCHAR│
│ published_at   TIMESTAMP│  │   │ created_at    TIMESTAMP │
│ max_students   INT      │  │   │ updated_at    TIMESTAMP │
│ prerequisites  TEXT     │  │   └──────────┬──────────────┘
│ learning_obj   TEXT     │  │              │ 1:N (enrollment_id FK, CASCADE)
│ is_deleted     BOOLEAN  │  │       ┌──────┼──────────┐
│ created_at     TIMESTAMP│  │       ▼      ▼          ▼
│ updated_at     TIMESTAMP│  │ ┌──────────┐┌────────┐┌─────────────┐
└─────────────────────────┘  │ │ progress ││certifi-││quiz_attempts│
   logical FK (instructor)◄──┘ │          ││ cates  ││             │
                               │ enroll_  ││enroll_ ││ enrollment_ │
                               │  ment_id ││ment_id ││  id FK      │
                               │ item_type││cert_no ││ module_id   │
                               │ item_id  ││issue_  ││ attempt_no  │
                               │ progress_││ date   ││ status      │
                               │  pct     ││verif_  ││ score       │
                               │ completed││ code   ││ passed      │
                               │  _at     ││grade   ││ time_spent  │
                               └──────────┘└────────┘└──────┬──────┘
                                                            │ 1:N
                                                            ▼
                                                     ┌─────────────┐
                                                     │user_answers │
                                                     │             │
                                                     │ quiz_attempt│
                                                     │  _id FK     │
                                                     │ question_id │
                                                     │ user_resp   │
                                                     │ is_correct  │
                                                     │ time_spent  │
                                                     └─────────────┘
```

### 6.4 MongoDB Document Structure

**`course_content` Collection (one document per course):**

```json
{
  "_id": ObjectId,
  "course_id": "uuid",             // unique index → courses.id
  "modules": [
    {
      "module_id": "string",
      "title": "Module 1: Introduction",
      "description": "...",
      "order": 1,
      "is_published": true,
      "is_active": true,
      "lessons": [
        {
          "lesson_id": "string",
          "title": "What is Python?",
          "type": "video|text|pdf",
          "content": "...",
          "duration_minutes": 15,
          "order": 1,
          "is_preview": false,
          "is_active": true,
          "resources": [
            {
              "resource_id": "string",
              "name": "Slides",
              "url": "s3://...",
              "type": "pdf",
              "is_active": true
            }
          ]
        }
      ]
    }
  ],
  "metadata": {},
  "created_at": ISODate,
  "updated_at": ISODate
}
```

**`module_quizzes` Collection (one document per module quiz):**

```json
{
  "_id": ObjectId,
  "course_id": "uuid",
  "module_id": "string",            // unique index (course_id, module_id)
  "title": "Module 1 Quiz",
  "description": "...",
  "settings": { "time_limit": 30, "passing_score": 70 },
  "questions": [
    {
      "question_id": "string",
      "order": 1,
      "question_text": "What is a variable?",
      "question_type": "multiple_choice|true_false|short_answer",
      "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
      "correct_answers": ["B"],
      "case_sensitive": false,
      "explanation": "...",
      "hint": "..."
    }
  ],
  "authorship": { "generated_by": "ai", "model": "gpt-4o-mini" },
  "is_published": false,
  "is_active": true,
  "created_at": ISODate,
  "updated_at": ISODate
}
```

### 6.5 Qdrant Vector Store

| Property | Value |
|----------|-------|
| **Collection** | `course_embeddings` |
| **Vector Dimension** | 1536 |
| **Distance Metric** | Cosine |
| **Embedding Model** | OpenAI `text-embedding-3-small` |

**Point Structure:**

```json
{
  "id": "uuid",
  "vector": [0.012, -0.034, ...],     // 1536 floats
  "payload": {
    "course_id": "uuid",
    "module_id": "string",
    "lesson_id": "string",
    "chunk_index": 0,
    "text": "chunk content...",
    "lesson_title": "What is Python?",
    "module_title": "Introduction",
    "preview": "first 200 chars..."
  }
}
```

**Query Filters:** `course_id`, `module_id`, `lesson_id` for scoped retrieval.

### 6.6 Unique Constraints

| Table/Collection | Unique On |
|-----------------|-----------|
| `users` | `(email)` |
| `courses` | `(slug)` |
| `enrollments` | `(student_id, course_id)` |
| `progress` | `(enrollment_id, item_type, item_id)` |
| `certificates` | `(enrollment_id)`, `(certificate_number)`, `(verification_code)` |
| `quiz_attempts` | `(enrollment_id, module_id, attempt_number)` |
| `module_quizzes` | `(course_id, module_id)` |
| `module_summaries` | `(course_id, module_id)` |

### 6.7 Caching Strategy (Redis)

| Cache Key Pattern | TTL | Invalidation | Usage |
|-------------------|-----|--------------|-------|
| `courses:category:{cat}:page:{p}` | 5m | Course publish/update | Course catalog |
| `course:{id}` | 10m | Course update | Course details |
| `progress:{enrollment_id}` | 5m | Progress update | Progress cache |
| `user:{id}` | 15m | Profile update | User profile |
| `rate_limit:{ip}:{zone}` | 1s | Auto-expire | Nginx rate limiting |
| `gen_status:{course_id}` | 1h | Indexing complete | RAG indexing status |
| `celery-task-meta-{id}` | — | Auto | Celery result backend |

---

## 7. Workflow Orchestration

All multi-step business processes are orchestrated through **Temporal**, executed by the **Core Service** worker.

### 7.1 Enrollment Workflow

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                          ENROLLMENT WORKFLOW (Temporal)                                    │
└──────────────────────────────────────────────────────────────────────────────────────────┘

    STUDENT           API GATEWAY      COURSE SERVICE       TEMPORAL (Core Svc Worker)
       │                    │                │                         │
       │ POST /course/      │                │                         │
       │ enrollments        │                │                         │
       │ {course_id}        │                │                         │
       │───────────────────►│                │                         │
       │                    │  Forward       │                         │
       │                    │───────────────►│                         │
       │                    │                │                         │
       │                    │                │  Start EnrollmentWorkflow
       │                    │                │  (user_id, course_id)   │
       │                    │                │───────────────────────►│
       │                    │                │                         │
       │                    │                │  workflow_id            │
       │  {status: 202,     │◄───────────────│◄────────────────────────│
       │   workflow_id}     │                │                         │
       │◄───────────────────│                │                         │
       │                    │                │                         │
       │                    │     ┌──────────────────────────────────────────────────┐
       │                    │     │          TEMPORAL WORKFLOW EXECUTION             │
       │                    │     ├──────────────────────────────────────────────────┤
       │                    │     │                                                  │
       │                    │     │  Activity 1: validate_user_for_enrollment       │
       │                    │     │  ├─ HTTP GET user-service /users/{id}           │
       │                    │     │  └─ Check user is_active = true                 │
       │                    │     │                                                  │
       │                    │     │  Activity 2: fetch_user_details                 │
       │                    │     │  ├─ HTTP GET user-service /users/{id}           │
       │                    │     │  └─ Non-critical: fallback to defaults on fail  │
       │                    │     │                                                  │
       │                    │     │  Activity 3: fetch_course_details               │
       │                    │     │  ├─ HTTP GET course-service /courses/{id}       │
       │                    │     │  └─ Validate course is published                │
       │                    │     │                                                  │
       │                    │     │  Activity 4: enroll_in_course                   │
       │                    │     │  ├─ HTTP POST course-service /course/enrollments│
       │                    │     │  └─ Idempotent: returns existing if duplicate   │
       │                    │     │                                                  │
       │                    │     │  Activity 5: trigger_enrollment_notifications   │
       │                    │     │  ├─ HTTP POST notification-service              │
       │                    │     │  └─ Non-critical: workflow completes on failure │
       │                    │     │                                                  │
       │                    │     │  Returns: EnrollmentWorkflowOutput              │
       │                    │     │  {success, enrollment_id, steps_completed}      │
       │                    │     └──────────────────────────────────────────────────┘
```

### 7.2 Course Publishing Workflow

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                       COURSE PUBLISH WORKFLOW (Temporal)                                   │
└──────────────────────────────────────────────────────────────────────────────────────────┘

   INSTRUCTOR          API GATEWAY      COURSE SERVICE       TEMPORAL (Core Svc)    AI SERVICE
       │                    │                │                      │                    │
       │ POST /courses/     │                │                      │                    │
       │ {id}/publish       │                │                      │                    │
       │───────────────────►│                │                      │                    │
       │                    │  Forward       │                      │                    │
       │                    │───────────────►│                      │                    │
       │                    │                │                      │                    │
       │                    │                │ Start CoursePublishWF │                    │
       │                    │                │─────────────────────►│                    │
       │                    │                │                      │                    │
       │  {status: 202,     │◄───────────────│◄─────────────────────│                    │
       │   workflow_id}     │                │                      │                    │
       │◄───────────────────│                │                      │                    │
       │                    │                │                      │                    │
       │                    │         ┌──────────────────────────────────────────────────┤
       │                    │         │       TEMPORAL WORKFLOW EXECUTION                │
       │                    │         ├──────────────────────────────────────────────────┤
       │                    │         │                                                  │
       │                    │         │  Activity 1: validate_course_for_publish        │
       │                    │         │  ├─ Course exists, has content, status = draft  │
       │                    │         │  └─ HTTP GET course-service /courses/{id}       │
       │                    │         │                                                  │
       │                    │         │  Activity 2: mark_course_published              │
       │                    │         │  ├─ HTTP PUT course-service /courses/{id}       │
       │                    │         │  └─ Set status = "published", published_at      │
       │                    │         │                                                  │
       │                    │         │  Activity 3: notify_instructor_publish_success  │
       │                    │         │  └─ HTTP POST notification-service              │
       │                    │         │                                                  │
       │                    │         │  Activity 4: start_rag_indexing_child           │
       │                    │         │  ├─ Start CourseRagIndexingChildWorkflow        │
       │                    │         │  ├─ parent_close_policy = ABANDON               │
       │                    │         │  └─ Child continues independently               │
       │                    │         │                                                  │
       │                    │         │  ═══ PARENT WORKFLOW COMPLETE ═══               │
       │                    │         └──────────────────────────────────────────────────┘
       │                    │                                                  │
       │                    │         ┌────────────────────────────────────────┤
       │                    │         │  CHILD: CourseRagIndexingChildWorkflow │
       │                    │         ├────────────────────────────────────────┤
       │                    │         │                                        │
       │                    │         │  HTTP POST ai-service                 │
       │                    │         │  /api/v1/ai/index/build               │
       │                    │         │  {course_id}  ────────────────────────►│
       │                    │         │                                        │
       │                    │         │  AI Service:                           │
       │                    │         │   · Fetch content from MongoDB        │
       │                    │         │   · Extract text (PDF, video, audio)  │
       │                    │         │   · Chunk text semantically           │
       │                    │         │   · Generate embeddings (OpenAI)      │
       │                    │         │   · Store in Qdrant                   │
       │                    │         │                                        │
       │                    │         └────────────────────────────────────────┘
```

### 7.3 AI Tutor Q&A Flow

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                               AI TUTOR Q&A FLOW                                           │
└──────────────────────────────────────────────────────────────────────────────────────────┘

    STUDENT           API GATEWAY        AI SERVICE             QDRANT           OPENAI
       │                    │                │                      │                │
       │ POST /api/v1/ai/   │                │                      │                │
       │ tutor/ask          │                │                      │                │
       │ {query, course_id, │                │                      │                │
       │  module_id,        │                │                      │                │
       │  conversation_     │                │                      │                │
       │  history}          │                │                      │                │
       │───────────────────►│                │                      │                │
       │                    │  Forward       │                      │                │
       │                    │───────────────►│                      │                │
       │                    │                │                      │                │
       │                    │                │  ┌──────────────────────────────────────┐
       │                    │                │  │  LANGGRAPH STATE MACHINE            │
       │                    │                │  ├──────────────────────────────────────┤
       │                    │                │  │                                      │
       │                    │                │  │  NODE 1: RETRIEVE                   │
       │                    │                │  │  ├─ Embed query ─────────────────────────────►│
       │                    │                │  │  │                                   │        │
       │                    │                │  │  │  Vector search ───────────────────►│        │
       │                    │                │  │  │  (TOP_K=5, threshold=0.3,         │        │
       │                    │                │  │  │   filter: course_id, module_id)   │        │
       │                    │                │  │  │                                   │        │
       │                    │                │  │  │  Retrieved chunks ◄───────────────│        │
       │                    │                │  │  │  (text + metadata)                │        │
       │                    │                │  │  └─ Build context_text              │        │
       │                    │                │  │                                      │        │
       │                    │                │  │  NODE 2: GENERATE                   │        │
       │                    │                │  │  ├─ System prompt + context +        │        │
       │                    │                │  │  │  conversation_history             │        │
       │                    │                │  │  │                                   │        │
       │                    │                │  │  ├─ ChatOpenAI (gpt-4o-mini) ────────────────►│
       │                    │                │  │  │  (streaming tokens)               │        │
       │                    │                │  │  │                                   │        │
       │                    │                │  │  │  Response ◄────────────────────────────────│
       │                    │                │  │  └─ Return response + sources       │        │
       │                    │                │  │                                      │        │
       │                    │                │  └──────────────────────────────────────┘
       │                    │                │                      │                │
       │  {response: "...", │◄───────────────│◄─────────────────────│                │
       │   sources: [...]}  │                │                      │                │
       │◄───────────────────│                │                      │                │
```

---

## 8. AI / ML Architecture

### 8.1 Component Overview

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                              AI SERVICE ARCHITECTURE                                      │
│                                                                                           │
│  ┌──────────────────────────────────────────────────────────────────────────────────────┐ │
│  │                           LangGraph Pipelines                                        │ │
│  │                                                                                      │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────────────────────┐     │ │
│  │  │  RAG Indexing    │  │  AI Tutor       │  │  Instructor Content Generation   │     │ │
│  │  │  Pipeline        │  │  Agent          │  │                                  │     │ │
│  │  │                  │  │                  │  │  ┌─────────────┐ ┌────────────┐ │     │ │
│  │  │ Extract → Chunk  │  │ Retrieve →      │  │  │ Quiz Gen    │ │ Summary Gen│ │     │ │
│  │  │ → Embed → Store  │  │ Generate        │  │  │ (structured │ │ (structured│ │     │ │
│  │  │                  │  │ (RAG Q&A)       │  │  │  output)    │ │  output)   │ │     │ │
│  │  └────────┬─────────┘  └───────┬─────────┘  │  └─────────────┘ └────────────┘ │     │ │
│  │           │                    │             │                                  │     │ │
│  └───────────┼────────────────────┼─────────────┼──────────────────────────────────┘     │ │
│              │                    │             │                                         │ │
│  ┌───────────┼────────────────────┼─────────────┼──────────────────────────────────────┐ │ │
│  │           ▼                    ▼             ▼         EXTERNAL DEPENDENCIES         │ │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │ │ │
│  │  │   Qdrant     │  │   OpenAI     │  │   MongoDB    │  │    Redis     │            │ │ │
│  │  │  (vectors)   │  │  (LLM+Embed) │  │  (content)   │  │  (status)    │            │ │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘            │ │ │
│  └────────────────────────────────────────────────────────────────────────────────────┘ │ │
│                                                                                           │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

### 8.2 Content Processing Pipeline

| Stage | Component | Input | Output |
|-------|-----------|-------|--------|
| 1. Fetch | `ContentExtractor` | course_id from MongoDB | Raw course content (modules, lessons) |
| 2. Process | `ContentPipeline` | Raw content (PDF, video, audio, text) | Extracted plain text |
| 3. Chunk | `TextChunker` | Plain text | Semantically chunked text segments |
| 4. Embed | `OpenAIClient` | Text chunks | 1536-dim float vectors |
| 5. Store | `VectorStoreRepository` | Vectors + metadata | Qdrant points with payload filters |

**Supported Content Types:**

| Type | Processor | Library |
|------|-----------|---------|
| PDF | PDF text + image extraction | PyMuPDF (`fitz`) |
| Video | Metadata + audio track extraction | `ffmpeg-python` |
| Audio | Format conversion + transcription markers | `pydub` |
| Text | Direct pass-through | — |

### 8.3 LLM Configuration

| Parameter | Value |
|-----------|-------|
| Chat Model | `gpt-4o-mini` |
| Embedding Model | `text-embedding-3-small` |
| Embedding Dimensions | 1536 |
| RAG Top-K | 5 |
| RAG Score Threshold | 0.3 |
| Vector Distance | Cosine |

---

## 9. Infrastructure Components

### 9.1 Message Queue Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                           KAFKA EVENT STREAMING                                           │
│                                                                                           │
│  ┌───────────────┐  ┌───────────────┐  ┌─────────────────┐  ┌───────────────┐           │
│  │ user.events   │  │ course.events │  │enrollment.events│  │progress.events│           │
│  │ partitions: 3 │  │ partitions: 3 │  │ partitions: 3   │  │ partitions: 3 │           │
│  └───────────────┘  └───────────────┘  └─────────────────┘  └───────────────┘           │
│                                                                                           │
│  ┌────────────────────┐  ┌───────────────┐                                               │
│  │notification.events │  │  ai.events    │                                               │
│  │ partitions: 1      │  │ partitions: 3 │                                               │
│  └────────────────────┘  └───────────────┘                                               │
│                                                                                           │
│  Schema Registry: http://schema-registry:8081                                            │
│  Bootstrap: kafka:29092 (internal), localhost:9092 (external)                            │
│  Depends on: Zookeeper :2181                                                             │
└──────────────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                           RABBITMQ + CELERY (Task Queue)                                  │
│                                                                                           │
│  Broker:  amqp://smartcourse:***@rabbitmq:5672                                           │
│  Backend: redis://:***@redis:6379/2                                                      │
│  Management UI: http://rabbitmq:15672                                                    │
│                                                                                           │
│  ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐                    │
│  │   email_queue     │  │ notification_queue │  │ certificate_queue │                    │
│  │                   │  │                    │  │                   │                    │
│  │ send_welcome_     │  │ create_in_app_     │  │ generate_         │                    │
│  │  email            │  │  notification      │  │  certificate_pdf  │                    │
│  │ send_enrollment_  │  │                    │  │                   │                    │
│  │  confirmation     │  │                    │  │                   │                    │
│  │ send_course_      │  │                    │  │                   │                    │
│  │  completion_email │  │                    │  │                   │                    │
│  │ send_certificate_ │  │                    │  │                   │                    │
│  │  ready_email      │  │                    │  │                   │                    │
│  └───────────────────┘  └───────────────────┘  └───────────────────┘                    │
│                                                                                           │
│  Retry Policy: 3 attempts, exponential backoff                                           │
│  Serialization: JSON                                                                     │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

### 9.2 Infrastructure Port Map

| Component | Internal Port | External Port | Protocol |
|-----------|---------------|---------------|----------|
| Nginx API Gateway | 8000 | 8000 | HTTP |
| Auth Sidecar | 8010 | — | HTTP (internal) |
| User Service | 8001 | — | HTTP (internal) |
| Course Service | 8002 | — | HTTP (internal) |
| Notification Service | 8005 | — | HTTP (internal) |
| Core Service | 8006 | — | HTTP (internal) |
| AI Service | 8009 | — | HTTP (internal) |
| PostgreSQL | 5432 | 5432 | TCP |
| MongoDB | 27017 | 27017 | TCP |
| Redis | 6379 | 6379 | TCP |
| Kafka (internal) | 29092 | — | TCP |
| Kafka (external) | — | 9092 | TCP |
| Zookeeper | 2181 | 2181 | TCP |
| Schema Registry | 8081 | 8081 | HTTP |
| RabbitMQ | 5672 | 5672 | AMQP |
| RabbitMQ Management | 15672 | 15672 | HTTP |
| Qdrant REST | 6333 | 6333 | HTTP |
| Qdrant gRPC | 6334 | 6334 | gRPC |
| Temporal Server | 7233 | 7233 | gRPC |
| Temporal UI | 8080 | 8080 | HTTP |
| Prometheus | 9090 | 9090 | HTTP |
| Grafana | 3000 | 3000 | HTTP |

---

## 10. Security Architecture

### 10.1 Authentication & Authorization

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                          AUTHENTICATION ARCHITECTURE                                      │
│                                                                                           │
│                                                                                           │
│   Client ──── HTTPS ────► Nginx ──── auth_request ────► Auth Sidecar                    │
│                             │                              │                              │
│                             │                              │ JWT Verification:            │
│                             │                              │  · Algorithm: HS256          │
│                             │                              │  · Library: python-jose      │
│                             │                              │  · Secret: shared env var    │
│                             │                              │                              │
│                             │         200 + Headers ◄──────┘                              │
│                             │         401 Unauthorized                                    │
│                             │                                                             │
│                             │  On 200: sets proxy headers                                │
│                             │   · X-Auth-User-ID                                         │
│                             │   · X-Auth-User-Role                                       │
│                             │   · X-Auth-Profile-ID                                      │
│                             │                                                             │
│                             ▼                                                             │
│                        Upstream Service                                                   │
│                        (reads headers, trusts gateway)                                   │
│                                                                                           │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

| Layer | Mechanism |
|-------|-----------|
| **Client → Gateway** | JWT Bearer token in `Authorization` header |
| **Gateway → Services** | Trusted `X-Auth-*` headers (no re-verification) |
| **JWT Access Token** | HS256, configurable expiry (default: 1440 min / 24h) |
| **JWT Refresh Token** | HS256, configurable expiry (default: 7 days) |
| **Password Storage** | bcrypt hashing |
| **Inter-service** | Internal Docker network (no auth, services not exposed publicly) |

### 10.2 Network Security

| Control | Implementation |
|---------|----------------|
| **Single Public Port** | Only port 8000 (Nginx) is exposed to clients |
| **CORS** | Configured in Nginx (currently permissive for development) |
| **Rate Limiting** | Nginx `limit_req` zones (see §4.1) |
| **Input Validation** | Pydantic schemas on all request bodies |
| **SQL Injection** | Parameterized queries via SQLAlchemy ORM |
| **Secrets Management** | Environment variables via `.env` files (Docker) |

### 10.3 Data Protection

| Data Type | Protection |
|-----------|------------|
| Passwords | bcrypt hash (never stored in plaintext) |
| JWT Tokens | HS256-signed, short-lived access + long-lived refresh |
| Database Credentials | Environment variables, not in code |
| S3 Access | IAM credentials via environment |
| API Keys (OpenAI) | Environment variables |

---

## 11. Observability

### 11.1 Metrics (Prometheus)

All FastAPI services expose a `/metrics` endpoint via `prometheus-fastapi-instrumentator`.

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "user-service"
    static_configs:
      - targets: ["user-service:8001"]
    metrics_path: "/metrics"

  - job_name: "course-service"
    static_configs:
      - targets: ["course-service:8002"]

  - job_name: "notification-service"
    static_configs:
      - targets: ["notification-service:8005"]

  - job_name: "core-service"
    static_configs:
      - targets: ["core-service:8006"]

  - job_name: "ai-service"
    static_configs:
      - targets: ["ai-service:8009"]
```

**Auto-instrumented Metrics:**

| Metric | Type | Description |
|--------|------|-------------|
| `http_requests_total` | Counter | Total requests per endpoint, method, status |
| `http_request_duration_seconds` | Histogram | Request latency distribution |
| `http_requests_in_progress` | Gauge | Currently processing requests |

### 11.2 Dashboards (Grafana)

| Dashboard | Key Panels |
|-----------|------------|
| **API Overview** | Request rate, error rate, latency percentiles, top endpoints |
| **Business Metrics** | Enrollments, completions, active users |
| **Kafka Metrics** | Consumer lag, throughput, partition distribution |
| **Temporal Workflows** | Active workflows, failure rate, duration histograms |
| **Infrastructure** | CPU, memory, disk, network per container |

### 11.3 Distributed Tracing (OpenTelemetry + Jaeger)

```python
# Auto-instrumentation in services
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

FastAPIInstrumentor.instrument_app(app)
SQLAlchemyInstrumentor().instrument(engine=engine)
RedisInstrumentor().instrument()
```

**Trace Flow Example:**

```
[nginx:8000] → [user-service:8001] → [postgresql:5432]
                                   → [redis:6379]
                                   → [kafka:29092]

[nginx:8000] → [course-service:8002] → [temporal:7233]
               ↳ [core-service:8006] → [user-service:8001]
                                     → [course-service:8002] → [postgresql:5432]
                                     → [notification-service:8005] → [rabbitmq:5672]
                                     → [ai-service:8009] → [qdrant:6333]
                                                          → [openai-api]
```

### 11.4 Structured Logging

All services use `structlog` for structured JSON logging with correlation IDs.

---

## 12. Failure Handling & Resilience

### 12.1 Retry Strategies

| Component | Strategy | Max Retries | Backoff |
|-----------|----------|-------------|---------|
| Temporal Activities | Exponential | 3 | 1s → 30s (coefficient: 2.0) |
| Celery Tasks | Exponential | 3 | Configurable |
| Kafka Consumer | Auto (aiokafka) | ∞ (reconnect) | Built-in |
| Database Connections | Pool with retry | 5 | Linear 1s |

### 12.2 Idempotency

| Operation | Mechanism |
|-----------|-----------|
| Enrollment creation | Unique constraint `(student_id, course_id)` — returns existing on duplicate |
| Temporal workflows | Workflow ID deduplication (Temporal built-in) |
| Kafka events | `event_id` (UUID) in `EventEnvelope` for consumer-side dedup |
| Celery tasks | Task ID tracking |

### 12.3 Graceful Degradation

| Failure | Impact | Fallback |
|---------|--------|----------|
| Kafka down | Events not published | Service continues; events lost (no outbox pattern yet) |
| Temporal down | Workflows can't start | HTTP 503; enrollment not created |
| Redis down | Cache misses, rate limiting disabled | Services hit DB directly; higher latency |
| Qdrant down | AI Tutor unavailable | RAG queries fail; tutor returns error |
| OpenAI API down | AI generation unavailable | Quiz/summary/tutor endpoints return 503 |
| MongoDB down | Course content unavailable | Content endpoints fail; PG-based endpoints unaffected |

### 12.4 Temporal Compensation Patterns

- **Non-critical failures use fallback values**: e.g., `fetch_user_details` fails → workflow continues with default values
- **Step tracking**: Each workflow tracks completed steps for debugging and observability
- **Query support**: Workflow state can be queried via Temporal API to check progress
- **Parent close policy ABANDON**: RAG indexing child workflow continues even if parent completes

---

## 13. Deployment Architecture

### 13.1 Docker Compose Stack

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                           DOCKER COMPOSE DEPLOYMENT                                       │
└──────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              INFRASTRUCTURE LAYER                                        │
│                                                                                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────────┐ │
│  │PostgreSQL│ │ MongoDB  │ │  Redis   │ │  Qdrant  │ │ RabbitMQ │ │    Kafka        │ │
│  │  :5432   │ │  :27017  │ │  :6379   │ │:6333/6334│ │:5672/    │ │  :9092/:29092   │ │
│  │  v15     │ │  v7      │ │  v7      │ │  v1.12   │ │  15672   │ │  + Zookeeper    │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ │  v3.13   │ │  + Schema Reg   │ │
│                                                       └──────────┘ └─────────────────┘ │
│                                                                                          │
│  ┌──────────────────────────────────────────────────────────────┐                        │
│  │              TEMPORAL CLUSTER                                │                        │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │                        │
│  │  │Temporal Server│  │  Temporal UI │  │ Temporal PG  │       │                        │
│  │  │    :7233     │  │    :8080     │  │  (dedicated) │       │                        │
│  │  │    v1.24     │  │              │  │              │       │                        │
│  │  └──────────────┘  └──────────────┘  └──────────────┘       │                        │
│  └──────────────────────────────────────────────────────────────┘                        │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              SERVICES LAYER                                              │
│                                                                                          │
│  ┌──────────────────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐ │
│  │ API Gateway          │  │   User    │  │  Course   │  │  Notif.   │  │    AI     │ │
│  │ ┌────────┐┌────────┐ │  │  Service  │  │  Service  │  │  Service  │  │  Service  │ │
│  │ │ Nginx  ││Sidecar │ │  │   :8001   │  │   :8002   │  │   :8005   │  │   :8009   │ │
│  │ │ :8000  ││ :8010  │ │  └───────────┘  └───────────┘  └───────────┘  └───────────┘ │
│  │ └────────┘└────────┘ │                                                              │
│  └──────────────────────┘                                                              │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              WORKERS LAYER                                               │
│                                                                                          │
│  ┌──────────────────────────────────┐  ┌──────────────────────────────────┐             │
│  │    CELERY WORKER                 │  │    TEMPORAL WORKER (Core Svc)    │             │
│  │    (Notification Service)        │  │                                  │             │
│  │                                  │  │  Workflows:                      │             │
│  │  Queues:                         │  │   · EnrollmentWorkflow          │             │
│  │   · email_queue                  │  │   · CoursePublishWorkflow       │             │
│  │   · notification_queue           │  │   · CourseRagIndexingChildWF    │             │
│  │   · certificate_queue            │  │                                  │             │
│  │                                  │  │  Task Queue: "core-service"     │             │
│  └──────────────────────────────────┘  └──────────────────────────────────┘             │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           OBSERVABILITY LAYER                                            │
│                                                                                          │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐                                           │
│  │Prometheus │  │  Grafana  │  │ Temporal  │                                           │
│  │   :9090   │  │   :3000   │  │  UI :8080 │                                           │
│  └───────────┘  └───────────┘  └───────────┘                                           │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### 13.2 Service Health Checks

Each service exposes a `GET /health` endpoint. Docker Compose uses these for startup ordering and dependency readiness.

### 13.3 Shared Library Distribution

```
shared/
├── pyproject.toml                  # Package metadata
└── src/shared/
    ├── kafka/                      # EventProducer, EventConsumer, Topics enum
    ├── schemas/events/             # Pydantic event payloads (user, course, enrollment, etc.)
    ├── temporal/                   # Client singleton, constants (TaskQueues, Workflows), I/O dataclasses
    ├── storage/                    # S3Uploader (async upload/download/delete)
    ├── exceptions/                 # NotFoundError, BadRequestError
    └── utils/                      # Datetime utilities
```

Installed as **editable package** (`pip install -e shared/`) in all service containers via their respective Dockerfiles.

### 13.4 Project File Structure

```
smart-course/
├── docker-compose.yml
├── .env
├── shared/                              # Shared library
│   ├── pyproject.toml
│   └── src/shared/
│       ├── kafka/
│       ├── schemas/events/
│       ├── temporal/
│       ├── storage/
│       ├── exceptions/
│       └── utils/
│
├── services/
│   ├── api-gateway/
│   │   ├── nginx.conf
│   │   ├── protected.conf
│   │   ├── auth-sidecar.py
│   │   ├── Dockerfile.nginx
│   │   └── Dockerfile.sidecar
│   │
│   ├── user-service/
│   │   ├── pyproject.toml
│   │   └── src/user_service/
│   │       ├── main.py
│   │       ├── config.py
│   │       ├── models/
│   │       ├── schemas/
│   │       ├── api/              # auth, profile routers
│   │       ├── services/         # AuthService, UserService
│   │       ├── repositories/
│   │       ├── core/             # database, redis, security, s3
│   │       └── alembic/
│   │
│   ├── course-service/
│   │   ├── pyproject.toml
│   │   └── src/
│   │       ├── main.py
│   │       ├── config.py
│   │       ├── models/           # Course, Enrollment, Certificate, Progress, QuizAttempt, UserAnswer
│   │       ├── schemas/
│   │       ├── api/              # courses, enrollments, certificates, progress, quiz_attempt
│   │       ├── services/         # EnrollmentService, CertificateService, ProgressService
│   │       ├── repositories/
│   │       ├── temporal/         # start_enrollment_workflow, start_course_publish_workflow
│   │       ├── core/             # database, mongodb, redis, s3
│   │       └── alembic/
│   │
│   ├── notification-service/
│   │   ├── pyproject.toml
│   │   └── src/notification_service/
│   │       ├── main.py
│   │       ├── config.py
│   │       ├── worker.py         # Celery app
│   │       ├── consumers/        # kafka_consumer, event_handlers
│   │       ├── tasks/            # email, notification, certificate
│   │       ├── mocks/            # MockEmailService, MockNotificationService
│   │       ├── api/
│   │       └── core/
│   │
│   ├── core/
│   │   ├── pyproject.toml
│   │   └── src/core_service/
│   │       ├── main.py
│   │       ├── config.py
│   │       └── temporal/
│   │           ├── worker.py
│   │           ├── workflows/
│   │           │   ├── enrollment/
│   │           │   │   ├── workflow.py
│   │           │   │   └── activities/
│   │           │   └── course_publish/
│   │           │       ├── workflow.py
│   │           │       ├── rag_indexing_child_workflow.py
│   │           │       └── activities/
│   │           └── common/
│   │
│   └── ai-service/
│       ├── pyproject.toml
│       └── src/ai_service/
│           ├── main.py
│           ├── config.py
│           ├── api/              # index, tutor, instructor routers
│           ├── services/
│           │   ├── index.py
│           │   ├── tutor_agent.py
│           │   ├── instructor_graphs.py
│           │   ├── generation_status.py
│           │   └── content_pipeline/
│           ├── repositories/     # vector_store (Qdrant), course_content (MongoDB)
│           ├── schemas/
│           ├── clients/          # OpenAIClient, CourseServiceClient
│           └── core/             # mongodb, redis
│
├── temporal-config/
│   └── development-sql.yaml
│
└── docs/
    ├── PRD-SmartCourse.md
    ├── SmartCourse-ERD-Simple.md
    └── SmartCourse-System-Design.md   # (this document)
```

---

## Non-Functional Requirements

### Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| API Response Time (P50) | < 100ms | Prometheus histogram |
| API Response Time (P95) | < 200ms | Prometheus histogram |
| API Response Time (P99) | < 500ms | Prometheus histogram |
| Enrollment Workflow Duration | < 5s | Temporal metrics |
| Publishing Workflow Duration | < 2m | Temporal metrics |
| Kafka Event Processing Lag | < 10s | Consumer lag |
| Cache Hit Rate | > 80% | Redis stats |
| RAG Query Latency | < 3s | Application metrics |

### Availability Targets

| Component | Target SLA | Recovery |
|-----------|------------|----------|
| API Gateway (Nginx) | 99.9% | Auto-restart, health checks |
| PostgreSQL | 99.95% | Docker restart policy |
| Redis | 99.9% | Docker restart policy |
| Kafka | 99.95% | Multi-partition, replication |
| Temporal | 99.9% | PostgreSQL persistence, auto-restart |

---

_Document Version: 3.0 | Last Updated: April 1, 2026_
_Previous Version: 2.0 (February 26, 2026)_
