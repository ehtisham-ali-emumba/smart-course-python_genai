# Product Requirements Document (PRD)

## SmartCourse — Intelligent Course Delivery Platform

| Field              | Detail                                      |
|--------------------|---------------------------------------------|
| **Product Name**   | SmartCourse                                 |
| **Version**        | 1.0                                         |
| **Date**           | April 1, 2026                               |
| **Author**         | Ehtisham — Backend Engineer                 |
| **Stakeholder**    | EduCorp                                     |
| **Status**         | In Progress                                 |

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Goals & Objectives](#3-goals--objectives)
4. [Target Users & Personas](#4-target-users--personas)
5. [Key Use Cases](#5-key-use-cases)
6. [Functional Requirements](#6-functional-requirements)
7. [Non-Functional Requirements](#7-non-functional-requirements)
8. [System Architecture Overview](#8-system-architecture-overview)
9. [Implementation Timeline & Milestones](#9-implementation-timeline--milestones)
10. [Traceability Matrix](#10-traceability-matrix)
11. [Risks & Mitigations](#11-risks--mitigations)
12. [Success Metrics](#12-success-metrics)
13. [Glossary](#13-glossary)
14. [References](#14-references)

---

## 1. Executive Summary

SmartCourse is an intelligent, large-scale learning platform commissioned by EduCorp to support digital education for universities, enterprises, and training academies. The platform addresses critical pain points in content publishing speed, intelligent search, data consistency, scalability under traffic spikes, and underutilization of interaction data. This PRD defines the scope, requirements, milestones, and traceability for the backend system that powers SmartCourse.

---

## 2. Problem Statement

EduCorp's current system faces five core challenges:

| #  | Problem                                  | Business Impact                                                        |
|----|------------------------------------------|------------------------------------------------------------------------|
| P1 | Content publishing is slow and manual    | Instructors cannot launch/update courses efficiently                   |
| P2 | Students lack intelligent search/support | Low engagement, students cannot find relevant content                   |
| P3 | Data is scattered and inconsistent       | Dashboards conflict with actual platform state                         |
| P4 | High traffic causes processing delays    | Enrollment spikes degrade UX                                           |
| P5 | Interaction data is underutilized        | No recommendations or adaptive learning despite rich usage data        |

---

## 3. Goals & Objectives

### Business Goals

| ID   | Goal                                         | Maps to Problem |
|------|----------------------------------------------|-----------------|
| BG-1 | Robust course management system              | P1              |
| BG-2 | Scalable and reliable operations backbone    | P4              |
| BG-3 | Consistent and accurate learner data         | P3              |
| BG-4 | Intelligent learning experiences             | P2, P5          |
| BG-5 | Smooth real-time interactions                | P4              |
| BG-6 | Long-term scalability foundation             | P4              |

### Product Objectives

- **O1:** Enable end-to-end course lifecycle management (create, publish, enroll, learn, certify).
- **O2:** Provide an AI-powered learning assistant for contextual Q&A and content generation.
- **O3:** Build event-driven, fault-tolerant background processing for publishing, enrollment, notifications, and analytics.
- **O4:** Deliver a consistent, queryable data layer across all services.
- **O5:** Achieve observability across all critical flows via structured logging, tracing, and metrics.

---

## 4. Target Users & Personas

### Persona 1: Instructor (Content Creator)

| Attribute        | Detail                                                                 |
|------------------|------------------------------------------------------------------------|
| **Role**         | Creates courses, modules, uploads materials, publishes updates         |
| **Pain Points**  | Slow publishing pipeline, manual content creation, no AI assistance    |
| **Needs**        | Fast publish workflow, auto-generated summaries/quizzes, analytics     |

### Persona 2: Student (Learner)

| Attribute        | Detail                                                                 |
|------------------|------------------------------------------------------------------------|
| **Role**         | Browses courses, enrolls, tracks progress, interacts with content      |
| **Pain Points**  | Cannot find relevant info, no contextual help, inconsistent progress   |
| **Needs**        | Smart search, AI Q&A on course material, reliable progress tracking    |

### Persona 3: Admin (Platform Manager)

| Attribute        | Detail                                                                 |
|------------------|------------------------------------------------------------------------|
| **Role**         | Manages platform operations, users, analytics dashboards               |
| **Pain Points**  | Inconsistent reporting, no visibility into system health               |
| **Needs**        | Accurate analytics, system observability, user management              |

---

## 5. Key Use Cases

### UC-1: Course Creation & Publishing

| Field           | Detail                                                                         |
|-----------------|--------------------------------------------------------------------------------|
| **Actor**       | Instructor                                                                     |
| **Precondition**| Instructor is authenticated and verified                                       |
| **Flow**        | 1. Instructor creates a course with title, description, category, thumbnail    |
|                 | 2. Instructor adds modules and uploads learning materials (PDF, video, text)   |
|                 | 3. Instructor clicks "Publish"                                                |
|                 | 4. System triggers background pipeline: content extraction, chunking, vector indexing |
|                 | 5. System marks course as "published" once all processing completes            |
| **Postcondition**| Course is searchable, browsable, and ready for enrollment                     |
| **Error Paths** | Partial processing failure triggers retry; course remains in "processing" state |

### UC-2: Student Enrollment

| Field           | Detail                                                                         |
|-----------------|--------------------------------------------------------------------------------|
| **Actor**       | Student                                                                        |
| **Precondition**| Student is authenticated; course is published and not at capacity              |
| **Flow**        | 1. Student browses/searches for a course                                       |
|                 | 2. Student clicks "Enroll"                                                     |
|                 | 3. System records enrollment (idempotent — no duplicates)                      |
|                 | 4. System initializes progress tracking for all modules                        |
|                 | 5. System updates analytics (enrollment count, popular courses)                |
|                 | 6. System sends "Welcome to the course" notification                           |
| **Postcondition**| Student can access course content; progress is at 0%                          |
| **Error Paths** | Duplicate enrollment returns existing enrollment; capacity exceeded returns 409 |

### UC-3: Learning Progress Tracking

| Field           | Detail                                                                         |
|-----------------|--------------------------------------------------------------------------------|
| **Actor**       | Student                                                                        |
| **Precondition**| Student is enrolled in the course                                              |
| **Flow**        | 1. Student completes a lesson/module                                           |
|                 | 2. System updates module-level and course-level progress                       |
|                 | 3. When all modules are complete, system marks course as "completed"           |
|                 | 4. System generates certificate upon completion                                |
| **Postcondition**| Progress is persisted; certificate is issued on 100% completion               |

### UC-4: AI Contextual Q&A (Student)

| Field           | Detail                                                                         |
|-----------------|--------------------------------------------------------------------------------|
| **Actor**       | Student                                                                        |
| **Precondition**| Student is enrolled; course content is indexed in vector DB                    |
| **Flow**        | 1. Student asks a question about course material                               |
|                 | 2. System retrieves relevant content chunks via RAG (vector similarity search) |
|                 | 3. LLM generates a contextually grounded answer                               |
|                 | 4. Response is streamed back to the student                                    |
| **Postcondition**| Student receives a relevant, course-specific answer                           |

### UC-5: AI Content Enhancement (Instructor)

| Field           | Detail                                                                         |
|-----------------|--------------------------------------------------------------------------------|
| **Actor**       | Instructor                                                                     |
| **Precondition**| Course content exists and is indexed                                           |
| **Flow**        | 1. Instructor requests a summary, quiz, or learning objectives for a module    |
|                 | 2. System retrieves module content                                             |
|                 | 3. LLM generates the requested content                                         |
|                 | 4. Response is streamed back to the instructor                                 |
| **Postcondition**| Instructor receives generated content for review/use                          |

### UC-6: Platform Analytics Dashboard

| Field           | Detail                                                                         |
|-----------------|--------------------------------------------------------------------------------|
| **Actor**       | Admin / Instructor                                                             |
| **Precondition**| User has admin or instructor role                                              |
| **Flow**        | 1. User navigates to analytics dashboard                                       |
|                 | 2. System queries aggregated metrics (enrollments, completions, popular courses)|
|                 | 3. System returns time-series and summary data                                 |
| **Postcondition**| Accurate, up-to-date analytics are displayed                                  |

### UC-7: User Registration & Authentication

| Field           | Detail                                                                         |
|-----------------|--------------------------------------------------------------------------------|
| **Actor**       | Student / Instructor / Admin                                                   |
| **Precondition**| None                                                                           |
| **Flow**        | 1. User registers with email, name, password, and role                         |
|                 | 2. System hashes password and stores user record                               |
|                 | 3. User logs in with credentials                                               |
|                 | 4. API Gateway issues JWT; all subsequent requests are authenticated           |
| **Postcondition**| User has a valid session; role-based access is enforced                        |

### UC-8: Notification Delivery

| Field           | Detail                                                                         |
|-----------------|--------------------------------------------------------------------------------|
| **Actor**       | System (event-driven)                                                          |
| **Precondition**| A triggering event occurs (enrollment, course published, etc.)                 |
| **Flow**        | 1. Event is published to message broker (Kafka/RabbitMQ)                       |
|                 | 2. Notification service consumes the event                                     |
|                 | 3. System delivers notification via appropriate channel (email, in-app, push)  |
| **Postcondition**| User is notified; delivery status is logged                                   |

---

## 6. Functional Requirements

### FR-1: Course & Content Management

| ID     | Requirement                                                                 | Priority | Use Case |
|--------|-----------------------------------------------------------------------------|----------|----------|
| FR-1.1 | Instructors can create courses with title, description, category, thumbnail | Must     | UC-1     |
| FR-1.2 | Instructors can add, update, and delete modules within a course             | Must     | UC-1     |
| FR-1.3 | Instructors can upload learning materials (PDF, video, text) to modules     | Must     | UC-1     |
| FR-1.4 | Courses have lifecycle states: draft, processing, published, archived       | Must     | UC-1     |
| FR-1.5 | Publishing triggers background pipeline (content extraction, chunking, vector indexing) | Must | UC-1 |
| FR-1.6 | Partial pipeline failures do not corrupt course state; retries are supported | Must    | UC-1     |
| FR-1.7 | Published courses are browsable and searchable by students                  | Must     | UC-2     |

### FR-2: User Management & Authentication

| ID     | Requirement                                                                 | Priority | Use Case |
|--------|-----------------------------------------------------------------------------|----------|----------|
| FR-2.1 | Users can register with email, name, password, and role (student/instructor/admin) | Must | UC-7 |
| FR-2.2 | Passwords are hashed using a secure algorithm (bcrypt)                      | Must     | UC-7     |
| FR-2.3 | Login returns a JWT; API Gateway validates JWT on every request             | Must     | UC-7     |
| FR-2.4 | Role-based access control (RBAC) enforced at the gateway level             | Must     | UC-7     |
| FR-2.5 | Student and Instructor profiles are maintained separately with role-specific fields | Must | UC-7 |
| FR-2.6 | Users can upload and update profile avatars                                 | Should   | UC-7     |

### FR-3: Enrollment & Progress

| ID     | Requirement                                                                 | Priority | Use Case |
|--------|-----------------------------------------------------------------------------|----------|----------|
| FR-3.1 | Students can enroll in published courses                                    | Must     | UC-2     |
| FR-3.2 | Duplicate enrollments are prevented (idempotent)                            | Must     | UC-2     |
| FR-3.3 | Enrollment initializes progress tracking for all modules in the course      | Must     | UC-2, UC-3 |
| FR-3.4 | Enrollment triggers analytics updates and welcome notification              | Must     | UC-2, UC-8 |
| FR-3.5 | Progress is updated at module-level and rolls up to course-level            | Must     | UC-3     |
| FR-3.6 | Course completion (100%) triggers certificate generation                    | Must     | UC-3     |
| FR-3.7 | Enrollment limits and prerequisites can be configured per course            | Should   | UC-2     |
| FR-3.8 | Enrollment history is maintained and queryable                              | Must     | UC-2     |

### FR-4: Intelligent Learning Assistant

| ID     | Requirement                                                                 | Priority | Use Case |
|--------|-----------------------------------------------------------------------------|----------|----------|
| FR-4.1 | Students can ask natural-language questions scoped to a course              | Must     | UC-4     |
| FR-4.2 | System performs RAG: retrieves relevant chunks from vector DB, sends to LLM | Must     | UC-4     |
| FR-4.3 | Responses are streamed incrementally to avoid blocking                      | Must     | UC-4, UC-5 |
| FR-4.4 | Instructors can request auto-generated summaries for modules                | Must     | UC-5     |
| FR-4.5 | Instructors can request auto-generated quiz questions for modules           | Must     | UC-5     |
| FR-4.6 | Instructors can request auto-generated learning objectives                  | Should   | UC-5     |
| FR-4.7 | Assistant handles ambiguous/incomplete questions gracefully                  | Must     | UC-4     |
| FR-4.8 | AI usage (questions asked, type of assistance) is tracked for analytics     | Should   | UC-6     |

### FR-5: Event-Driven Processing & Workflows

| ID     | Requirement                                                                 | Priority | Use Case |
|--------|-----------------------------------------------------------------------------|----------|----------|
| FR-5.1 | Course publishing triggers an asynchronous content processing pipeline      | Must     | UC-1     |
| FR-5.2 | Enrollment triggers asynchronous analytics update, progress init, notification | Must  | UC-2     |
| FR-5.3 | All background tasks are idempotent (no double-processing)                  | Must     | UC-1, UC-2 |
| FR-5.4 | Failed tasks are retried with backoff; dead-letter queues capture permanent failures | Must | UC-1, UC-2 |
| FR-5.5 | Workflows are orchestrated via Temporal for multi-step processes            | Must     | UC-1     |
| FR-5.6 | Celery workers handle independent background tasks (notifications, analytics) | Must  | UC-2, UC-8 |
| FR-5.7 | Kafka is used for event streaming between services                         | Must     | UC-2, UC-8 |
| FR-5.8 | System supports backpressure handling during traffic spikes                 | Should   | UC-2     |

### FR-6: Analytics & Reporting

| ID     | Requirement                                                                 | Priority | Use Case |
|--------|-----------------------------------------------------------------------------|----------|----------|
| FR-6.1 | Track total active students, instructors, and published courses             | Must     | UC-6     |
| FR-6.2 | Track new enrollments over time (daily, weekly, monthly)                    | Must     | UC-6     |
| FR-6.3 | Calculate course completion rate per course                                 | Must     | UC-6     |
| FR-6.4 | Calculate average time to complete a course                                 | Should   | UC-6     |
| FR-6.5 | Rank most popular courses by enrollment count and engagement                | Must     | UC-6     |
| FR-6.6 | Calculate average courses per student                                       | Should   | UC-6     |
| FR-6.7 | Track AI assistant usage metrics                                           | Should   | UC-6     |
| FR-6.8 | Track failed events and workflow issues                                     | Must     | UC-6     |

### FR-7: Notifications

| ID     | Requirement                                                                 | Priority | Use Case |
|--------|-----------------------------------------------------------------------------|----------|----------|
| FR-7.1 | Send enrollment confirmation notifications to students                      | Must     | UC-8     |
| FR-7.2 | Send course published notifications to enrolled/interested students         | Should   | UC-8     |
| FR-7.3 | Support multiple channels: email, in-app, push                             | Should   | UC-8     |
| FR-7.4 | Notification delivery status is logged and queryable                        | Must     | UC-8     |

---

## 7. Non-Functional Requirements

### NFR-1: Performance

| ID      | Requirement                                                              | Target                |
|---------|--------------------------------------------------------------------------|-----------------------|
| NFR-1.1 | API response time for CRUD operations                                    | p95 < 300ms           |
| NFR-1.2 | AI Q&A time-to-first-token                                               | < 2 seconds           |
| NFR-1.3 | Background task processing latency (enrollment pipeline)                 | < 5 seconds end-to-end|
| NFR-1.4 | Content publishing pipeline completion                                   | < 60 seconds per course|

### NFR-2: Scalability

| ID      | Requirement                                                              | Target                |
|---------|--------------------------------------------------------------------------|-----------------------|
| NFR-2.1 | Support 10,000+ concurrent learners                                      | Horizontal scaling    |
| NFR-2.2 | Handle enrollment spikes during course launches                          | Backpressure + queuing|
| NFR-2.3 | Background workers scale independently of API services                   | Docker + Celery       |

### NFR-3: Reliability & Fault Tolerance

| ID      | Requirement                                                              | Target                |
|---------|--------------------------------------------------------------------------|-----------------------|
| NFR-3.1 | No data loss on service failure                                          | Persistent queues     |
| NFR-3.2 | Idempotent event processing                                              | Deduplication at consumer |
| NFR-3.3 | Graceful degradation: AI service unavailability does not block core flows | Circuit breaker pattern |
| NFR-3.4 | Database consistency across services                                     | Transactional writes  |

### NFR-4: Observability

| ID      | Requirement                                                              | Target                |
|---------|--------------------------------------------------------------------------|-----------------------|
| NFR-4.1 | Structured logging for all services                                      | JSON format           |
| NFR-4.2 | Distributed tracing across service boundaries                            | OpenTelemetry + Jaeger|
| NFR-4.3 | Metrics dashboards for system health                                     | Prometheus + Grafana  |
| NFR-4.4 | Alerting on failed background tasks and error rate spikes                | Grafana alerting      |

### NFR-5: Security

| ID      | Requirement                                                              | Target                |
|---------|--------------------------------------------------------------------------|-----------------------|
| NFR-5.1 | All API endpoints authenticated via JWT                                  | HS256 at gateway      |
| NFR-5.2 | Passwords hashed with bcrypt                                             | Cost factor 12        |
| NFR-5.3 | Role-based access control on all endpoints                               | Gateway middleware     |
| NFR-5.4 | No secrets in source code or logs                                        | Environment variables  |

### NFR-6: Maintainability

| ID      | Requirement                                                              | Target                |
|---------|--------------------------------------------------------------------------|-----------------------|
| NFR-6.1 | Microservices architecture with clear boundaries                         | Service per domain    |
| NFR-6.2 | Database migrations managed via Alembic                                  | Version-controlled    |
| NFR-6.3 | Dockerized services with docker-compose for local development            | Single command startup|
| NFR-6.4 | API documentation auto-generated via FastAPI/OpenAPI                     | Swagger UI per service|

---

## 8. System Architecture Overview

### Services

| Service               | Port  | Responsibility                                                    |
|-----------------------|-------|-------------------------------------------------------------------|
| **API Gateway**       | 8000  | JWT auth, rate limiting, request routing, OpenTelemetry tracing   |
| **User Service**      | 8001  | Registration, login, JWT generation, user/profile CRUD            |
| **Course Service**    | 8002  | Course CRUD, modules, materials, enrollment, progress, certificates|
| **Notification Service** | 8005 | Email, push, in-app notifications via event consumption          |
| **Analytics Service** | 8008  | Aggregated metrics, dashboards, time-series enrollment data       |
| **AI Service**        | 8009  | RAG Q&A, quiz generation, summary generation, content indexing    |

### Infrastructure

| Component             | Purpose                                                           |
|-----------------------|-------------------------------------------------------------------|
| **PostgreSQL**        | Primary relational database (per-service schemas)                 |
| **MongoDB / NoSQL**   | Flexible storage for analytics, AI logs, notification history     |
| **Redis**             | Caching, rate limiting, session store                             |
| **RabbitMQ**          | Task queue broker for Celery workers                              |
| **Kafka**             | Event streaming between services (enrollment, publishing events)  |
| **Temporal**          | Workflow orchestration for multi-step pipelines                   |
| **Vector DB**         | Semantic search for RAG-based AI Q&A                              |
| **Prometheus**        | Metrics collection                                                |
| **Grafana**           | Metrics visualization and alerting                                |
| **Jaeger**            | Distributed tracing                                               |
| **Docker Compose**    | Local development orchestration                                   |

### Data Flow Diagram (High-Level)

```
Instructor publishes course
    │
    ▼
[API Gateway] ──▶ [Course Service] ──▶ Kafka Event: "course.published"
                                            │
                         ┌──────────────────┼──────────────────┐
                         ▼                  ▼                  ▼
                  [AI Service]      [Analytics Service]  [Notification Service]
                  Content indexing   Update metrics       Notify students
                  Vector embedding   Course count
                         │
                         ▼
                    [Vector DB]
                    Ready for RAG Q&A
```

```
Student enrolls in course
    │
    ▼
[API Gateway] ──▶ [Course Service] ──▶ Kafka Event: "student.enrolled"
                        │                     │
                        ▼              ┌──────┼──────────────────┐
                  Record enrollment    ▼      ▼                  ▼
                  Init progress   [Analytics] [Notification]  [AI Service]
                                  Update      Welcome email    (no action)
                                  metrics
```

---

## 9. Implementation Timeline & Milestones

### Phase 1: Foundation (Weeks 1–2)

| Milestone | Deliverable                                                         | Requirements Covered        |
|-----------|---------------------------------------------------------------------|-----------------------------|
| M1.1      | Project scaffolding: monorepo structure, Docker Compose, shared lib | NFR-6.1, NFR-6.3            |
| M1.2      | User Service: registration, login, JWT, profiles                    | FR-2.1–FR-2.6               |
| M1.3      | API Gateway: routing, JWT validation, rate limiting                 | FR-2.3, FR-2.4, NFR-5.1     |
| M1.4      | Database setup: PostgreSQL, Alembic migrations                      | NFR-6.2                     |

### Phase 2: Core Course Management (Weeks 3–4)

| Milestone | Deliverable                                                         | Requirements Covered        |
|-----------|---------------------------------------------------------------------|-----------------------------|
| M2.1      | Course CRUD: create, read, update, delete courses                   | FR-1.1, FR-1.4              |
| M2.2      | Module management: add/update/delete modules within courses         | FR-1.2                      |
| M2.3      | Material upload: support PDF, video, text uploads to modules        | FR-1.3                      |
| M2.4      | Course browsing and search for students                             | FR-1.7                      |

### Phase 3: Enrollment & Progress (Weeks 5–6)

| Milestone | Deliverable                                                         | Requirements Covered        |
|-----------|---------------------------------------------------------------------|-----------------------------|
| M3.1      | Enrollment endpoint with idempotency and duplicate prevention       | FR-3.1, FR-3.2              |
| M3.2      | Progress tracking: module-level and course-level                    | FR-3.3, FR-3.5              |
| M3.3      | Certificate generation on course completion                         | FR-3.6                      |
| M3.4      | Enrollment history and query APIs                                   | FR-3.8                      |

### Phase 4: Event-Driven Architecture (Weeks 7–8)

| Milestone | Deliverable                                                         | Requirements Covered        |
|-----------|---------------------------------------------------------------------|-----------------------------|
| M4.1      | Kafka setup with schema registry; event schemas defined             | FR-5.7                      |
| M4.2      | Publishing pipeline: content extraction + chunking via Temporal     | FR-5.1, FR-5.5              |
| M4.3      | Enrollment pipeline: analytics + progress + notification via events | FR-5.2, FR-5.6              |
| M4.4      | Idempotency, retry logic, dead-letter queues                       | FR-5.3, FR-5.4              |

### Phase 5: AI & Intelligent Assistant (Weeks 9–10)

| Milestone | Deliverable                                                         | Requirements Covered        |
|-----------|---------------------------------------------------------------------|-----------------------------|
| M5.1      | Vector DB setup; content indexing pipeline                          | FR-4.2                      |
| M5.2      | RAG-based contextual Q&A for students (streamed responses)          | FR-4.1, FR-4.3              |
| M5.3      | AI content generation: summaries, quizzes, objectives               | FR-4.4, FR-4.5, FR-4.6      |
| M5.4      | LangGraph agent integration                                        | FR-4.7                      |

### Phase 6: Analytics & Notifications (Weeks 11–12)

| Milestone | Deliverable                                                         | Requirements Covered        |
|-----------|---------------------------------------------------------------------|-----------------------------|
| M6.1      | Analytics service: aggregated metrics APIs                          | FR-6.1–FR-6.8               |
| M6.2      | Notification service: email, in-app, push channels                  | FR-7.1–FR-7.4               |
| M6.3      | Event consumption for both services from Kafka                      | FR-5.6, FR-5.7              |

### Phase 7: Observability & Hardening (Weeks 13–14)

| Milestone | Deliverable                                                         | Requirements Covered        |
|-----------|---------------------------------------------------------------------|-----------------------------|
| M7.1      | OpenTelemetry instrumentation across all services                   | NFR-4.1, NFR-4.2            |
| M7.2      | Prometheus metrics + Grafana dashboards                             | NFR-4.3                     |
| M7.3      | Jaeger distributed tracing                                          | NFR-4.2                     |
| M7.4      | Load testing and performance validation                             | NFR-1.1–NFR-1.4, NFR-2.1    |
| M7.5      | End-to-end integration testing                                      | All FR                      |

---

## 10. Traceability Matrix

This matrix maps **business goals** → **functional requirements** → **use cases** → **milestones**, ensuring every feature is traceable from business need to deliverable.

| Business Goal | Functional Requirements         | Use Cases          | Milestones          |
|---------------|---------------------------------|--------------------|---------------------|
| BG-1          | FR-1.1–FR-1.7                   | UC-1               | M2.1–M2.4           |
| BG-1          | FR-2.1–FR-2.6                   | UC-7               | M1.2–M1.3           |
| BG-2          | FR-5.1–FR-5.8                   | UC-1, UC-2, UC-8   | M4.1–M4.4           |
| BG-3          | FR-3.1–FR-3.8                   | UC-2, UC-3         | M3.1–M3.4           |
| BG-3          | FR-6.1–FR-6.8                   | UC-6               | M6.1                |
| BG-4          | FR-4.1–FR-4.8                   | UC-4, UC-5         | M5.1–M5.4           |
| BG-5          | FR-4.3, FR-5.1, FR-5.2         | UC-4, UC-5         | M5.2, M4.2–M4.3     |
| BG-6          | NFR-2.1–NFR-2.3, FR-5.5–FR-5.8 | All                | M4.1–M4.4, M7.4     |

### Requirement Coverage Summary

| Category                  | Total Requirements | Must Have | Should Have |
|---------------------------|--------------------|-----------|-------------|
| Course & Content (FR-1)   | 7                  | 7         | 0           |
| User Management (FR-2)    | 6                  | 5         | 1           |
| Enrollment & Progress (FR-3) | 8               | 6         | 2           |
| AI Assistant (FR-4)       | 8                  | 5         | 3           |
| Event Processing (FR-5)   | 8                  | 7         | 1           |
| Analytics (FR-6)          | 8                  | 5         | 3           |
| Notifications (FR-7)      | 4                  | 2         | 2           |
| **Total**                 | **49**             | **37**    | **12**      |

---

## 11. Risks & Mitigations

| #  | Risk                                                    | Probability | Impact | Mitigation                                                      |
|----|---------------------------------------------------------|-------------|--------|-----------------------------------------------------------------|
| R1 | Kafka/Temporal complexity delays event-driven milestones | High        | High   | Start with simpler Celery tasks; migrate to Kafka/Temporal incrementally |
| R2 | Vector DB performance degrades with large course corpus  | Medium      | Medium | Benchmark early; implement chunking strategy with size limits   |
| R3 | AI service latency impacts user experience               | Medium      | High   | Streaming responses (SSE); circuit breaker for fallback         |
| R4 | Data inconsistency between services                      | Medium      | High   | Event sourcing patterns; idempotent consumers; integration tests|
| R5 | Scope creep from "should have" features                  | High        | Medium | Strict milestone gating; defer "should have" to post-MVP        |
| R6 | Single developer bottleneck                              | High        | High   | Prioritize "must have" requirements; reuse shared libraries     |

---

## 12. Success Metrics

| Metric                                | Target                              | Measurement Method            |
|---------------------------------------|-------------------------------------|-------------------------------|
| All "Must Have" FRs implemented       | 37/37                               | Checklist review              |
| API p95 latency (CRUD)               | < 300ms                             | Prometheus/Grafana            |
| Content publishing pipeline success   | > 99%                               | Temporal workflow dashboard   |
| Enrollment pipeline end-to-end time   | < 5 seconds                         | Jaeger traces                 |
| AI Q&A time-to-first-token           | < 2 seconds                         | Application metrics           |
| Zero data loss on service restart     | 0 events lost                       | Integration test suite        |
| Test coverage                         | > 80% for critical paths            | pytest-cov                    |
| All services containerized            | 6/6 services in docker-compose      | docker-compose up succeeds    |

---

## 13. Glossary

| Term                | Definition                                                                    |
|---------------------|-------------------------------------------------------------------------------|
| **RAG**             | Retrieval-Augmented Generation — AI pattern combining search with LLM generation |
| **Idempotent**      | An operation that produces the same result regardless of how many times it is executed |
| **Backpressure**    | Mechanism to slow down producers when consumers cannot keep up                |
| **Dead-Letter Queue** | Queue for messages that cannot be processed after all retry attempts        |
| **Circuit Breaker** | Pattern that prevents cascading failures by stopping calls to a failing service |
| **SSE**             | Server-Sent Events — HTTP-based streaming for real-time updates               |
| **Vector DB**       | Database optimized for storing and querying high-dimensional embeddings       |
| **LangGraph**       | Framework for building stateful, multi-step AI agent workflows                |
| **Temporal**        | Workflow orchestration engine for reliable distributed task execution          |
| **JWT**             | JSON Web Token — compact, self-contained token for authentication             |
| **RBAC**            | Role-Based Access Control — restricting access based on user roles             |

---

## 14. References

| Document                          | Location                                        |
|-----------------------------------|-------------------------------------------------|
| Requirements PDF                  | `docs/SmartCourse — Intelligent Course Delivery Platform.pdf` |
| Entity Relationship Diagram       | `docs/SmartCourse-ERD-Simple.md`                |
| System Design Document            | `docs/SmartCourse-System-Design.md`             |
| Analytics Implementation Plan     | `docs/Analytics-Implementation-Plan.md`         |
| AI Service Plan                   | `docs/AgenticAI-Plan.md`                        |
| Monitoring Guide                  | `docs/Grafana-Prometheus-Monitoring-Guide.md`   |
| API Gateway Guide                 | `docs/API-Gateway-Nginx-Implementation-Guide.md`|
| Alembic Migration Guide           | `docs/Alembic-Usage-Guide.md`                   |
