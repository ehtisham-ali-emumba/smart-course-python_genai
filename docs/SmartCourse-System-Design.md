# SmartCourse - System Design Document

**Version:** 1.1  
**Date:** February 11, 2026  
**Author:** SmartCourse Architecture Team  
**Scope:** Complete System Architecture (Excluding AI/LLM/Vector DB Components)

---

## Key Architecture Decisions

| Decision              | Choice                                       | Rationale                                                          |
| --------------------- | -------------------------------------------- | ------------------------------------------------------------------ |
| **JWT Algorithm**     | HS256 (symmetric)                            | Simpler key management, sufficient for internal services           |
| **JWT Verification**  | API Gateway only                             | Single point of authentication, services trust gateway             |
| **Dependencies**      | pyproject.toml                               | Modern Python packaging standard, no requirements.txt              |
| **Containerization**  | Dockerfile per service + root docker-compose | Each service is independently deployable                           |
| **Local Development** | venv per service                             | Can run services without Docker if needed                          |
| **Shared Code**       | shared/ folder                               | Reusable utilities, schemas, middleware across services            |
| **File Naming**       | No folder prefix                             | e.g., `repositories/user.py` NOT `repositories/user_repository.py` |

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     SMARTCOURSE - SYSTEM ARCHITECTURE                                            │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

                                         ┌─────────────────┐
                                         │   CLIENTS       │
                                         │ Web | Mobile    │
                                         └────────┬────────┘
                                                  │
                                                  │ HTTPS
                                                  ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                           GATEWAY LAYER                                                          │
│  ┌───────────────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                                      API GATEWAY (FastAPI)                                                 │  │
│  │                                         Port: 8000                                                         │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────┐ │  │
│  │  │ Auth         │  │ Rate         │  │ Request      │  │ Response     │  │ OpenTelemetry                │ │  │
│  │  │ Middleware   │  │ Limiter      │  │ Validation   │  │ Aggregation  │  │ Tracing                      │ │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                  │
                    ┌─────────────────────────────┼─────────────────────────────┐
                    │                             │                             │
                    ▼                             ▼                             ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                          SERVICES LAYER                                                          │
│                                                                                                                  │
│  ┌──────────────────────────┐  ┌────────────────────────────────────────────────────────┐                        │
│  │      USER SERVICE        │  │                  COURSE SERVICE (MERGED)               │                        │
│  │       Port: 8001         │  │                     Port: 8002                         │                        │
│  │                          │  │                                                        │                        │
│  │  • Register              │  │  • CRUD Courses        • Enrollments                   │                        │
│  │  • Login                 │  │  • Modules             • Progress Tracking             │                        │
│  │  • JWT Token Generation  │  │  • Materials           • Certificates                  │                        │
│  │  • User CRUD             │  │  • Publishing          • Quiz Scoring                  │                        │
│  │  • Instructor Profiles   │  │                                                        │                        │
│  │  • Password Management   │  │  (Combines: Course + Enrollment + Progress +           │                        │
│  │                          │  │   Certificate functionality)                           │                        │
│  └────────────┬─────────────┘  └──────────────────────────┬─────────────────────────────┘                        │
│               │                                           │                                                      │
│  ┌──────────────────────────┐  ┌──────────────────────────┐                                                      │
│  │   NOTIFICATION SERVICE   │  │    ANALYTICS SERVICE     │                                                      │
│  │       Port: 8005         │  │       Port: 8008         │                                                      │
│  │                          │  │                          │                                                      │
│  │  • Email Notifications   │  │  • Metrics Collection    │                                                      │
│  │  • Push Notifications    │  │  • Reports               │                                                      │
│  │  • In-App Notifications  │  │  • Dashboards            │                                                      │
│  └────────────┬─────────────┘  └────────────┬─────────────┘                                                      │
└───────────────┼─────────────────────────────┼────────────────────────────────────────────────────────────────────┘
            │                    │                    │
            └────────────────────┼────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       EVENT & WORKFLOW LAYER                                                     │
│                                                                                                                  │
│  ┌─────────────────────────────────────────────────┐  ┌────────────────────────────────────────────────────────┐│
│  │              KAFKA EVENT BUS                     │  │              TEMPORAL ORCHESTRATOR                    ││
│  │                                                  │  │                                                        ││
│  │  Topics:                                         │  │  Workflows:                                            ││
│  │  ├─ user.events                                  │  │  ├─ CoursePublishingWorkflow                          ││
│  │  ├─ course.events                                │  │  ├─ EnrollmentWorkflow                                ││
│  │  ├─ enrollment.events                            │  │  ├─ CertificateGenerationWorkflow                     ││
│  │  ├─ progress.events                              │  │  └─ CourseArchiveWorkflow                             ││
│  │  ├─ notification.events                          │  │                                                        ││
│  │  └─ analytics.events                             │  │  Activities:                                           ││
│  │                                                  │  │  ├─ validate_course                                   ││
│  │  Consumer Groups:                                │  │  ├─ process_content                                   ││
│  │  ├─ analytics-consumer                           │  │  ├─ initialize_progress                               ││
│  │  ├─ notification-consumer                        │  │  ├─ update_analytics                                  ││
│  │  └─ content-consumer                             │  │  ├─ send_notification                                 ││
│  └─────────────────────────────────────────────────┘  │  └─ generate_certificate                               ││
│                                                        └────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────┐                                                             │
│  │              CELERY + RABBITMQ                   │                                                            │
│  │                                                  │                                                            │
│  │  Queues:                                         │                                                            │
│  │  ├─ email_queue                                  │                                                            │
│  │  ├─ sms_queue                                    │                                                            │
│  │  ├─ report_queue                                 │                                                            │
│  │  └─ certificate_queue                            │                                                            │
│  │                                                  │                                                            │
│  │  Workers: 3-5 concurrent workers                 │                                                            │
│  └─────────────────────────────────────────────────┘                                                             │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                  │
                                                  ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                           DATA LAYER                                                             │
│                                                                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                             │
│  │   POSTGRESQL    │  │    MONGODB      │  │     REDIS       │  │  OBJECT STORE   │                             │
│  │                 │  │                 │  │                 │  │    (S3/MinIO)   │                             │
│  │ • Users         │  │ • CourseContent │  │ • Sessions      │  │                 │                             │
│  │ • Courses       │  │ • Materials     │  │ • Cache         │  │ • Videos        │                             │
│  │ • Enrollments   │  │ • Assignments   │  │ • Rate Limits   │  │ • PDFs          │                             │
│  │ • Progress      │  │ • Flexible Data │  │ • Progress      │  │ • Images        │                             │
│  │ • Certificates  │  │                 │  │   Snapshots     │  │ • Certificates  │                             │
│  │ • Analytics     │  │                 │  │ • Queues        │  │                 │                             │
│  │ • Events        │  │                 │  │                 │  │                 │                             │
│  │ • Workflows     │  │                 │  │                 │  │                 │                             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                  │
                                                  ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       OBSERVABILITY LAYER                                                        │
│                                                                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                             │
│  │   PROMETHEUS    │  │    GRAFANA      │  │     JAEGER      │  │ OPENTELEMETRY   │                             │
│  │                 │  │                 │  │                 │  │                 │                             │
│  │ • Metrics       │  │ • Dashboards    │  │ • Traces        │  │ • Instrumentation│                            │
│  │ • Alerts        │  │ • Visualization │  │ • Spans         │  │ • Export        │                             │
│  │ • Scraping      │  │ • Alerting      │  │ • Dependencies  │  │ • Context       │                             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Service Communication Matrix

### 2.1 Synchronous Communication (REST/gRPC)

| From           | To                   | Protocol | Endpoint                                                         | Purpose                                    |
| -------------- | -------------------- | -------- | ---------------------------------------------------------------- | ------------------------------------------ |
| API Gateway    | User Service         | REST     | `/auth/*`, `/users/*`                                            | Authentication, User CRUD                  |
| API Gateway    | Course Service       | REST     | `/courses/*`, `/enrollments/*`, `/progress/*`, `/certificates/*` | Course, Enrollment, Progress, Certificates |
| API Gateway    | Analytics Service    | REST     | `/analytics/*`                                                   | Dashboard data                             |
| API Gateway    | Notification Service | REST     | `/notifications/*`                                               | Notification management                    |
| Course Service | User Service         | REST     | `/users/{id}`                                                    | Validate student exists                    |

**Note:** API Gateway is the ONLY interface for frontend. It handles:

- JWT verification (HS256 algorithm)
- Rate limiting
- Request routing to appropriate services
- Response aggregation

### 2.2 Asynchronous Communication (Events)

| Producer       | Event                       | Topic         | Consumers               |
| -------------- | --------------------------- | ------------- | ----------------------- |
| User Service   | `user.registered`           | user.events   | Analytics, Notification |
| User Service   | `user.verified`             | user.events   | Analytics               |
| Course Service | `course.created`            | course.events | Analytics               |
| Course Service | `course.published`          | course.events | Analytics, Notification |
| Course Service | `course.updated`            | course.events | Analytics               |
| Course Service | `course.archived`           | course.events | Notification, Analytics |
| Course Service | `enrollment.created`        | course.events | Analytics, Notification |
| Course Service | `enrollment.completed`      | course.events | Analytics, Notification |
| Course Service | `enrollment.dropped`        | course.events | Analytics               |
| Course Service | `progress.updated`          | course.events | Analytics               |
| Course Service | `progress.module_completed` | course.events | Analytics, Notification |
| Course Service | `certificate.issued`        | course.events | Notification            |

**Note:** Course Service now publishes all course-related events (including enrollment, progress, certificate) since these functionalities are merged.

---

## 3. Core Workflow Diagrams

### 3.1 Course Publishing Workflow

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     COURSE PUBLISHING WORKFLOW (Temporal)                                         │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

   INSTRUCTOR                API GATEWAY           COURSE SERVICE         TEMPORAL              CONTENT SERVICE
       │                          │                      │                   │                        │
       │  POST /courses/{id}/     │                      │                   │                        │
       │  publish                 │                      │                   │                        │
       │─────────────────────────►│                      │                   │                        │
       │                          │  Forward request     │                   │                        │
       │                          │─────────────────────►│                   │                        │
       │                          │                      │                   │                        │
       │                          │                      │ StartWorkflow     │                        │
       │                          │                      │ (course_id)       │                        │
       │                          │                      │──────────────────►│                        │
       │                          │                      │                   │                        │
       │                          │                      │ workflow_id       │                        │
       │                          │                      │◄──────────────────│                        │
       │                          │                      │                   │                        │
       │                          │  {workflow_id,       │                   │                        │
       │  {workflow_id}           │   status: QUEUED}    │                   │                        │
       │◄─────────────────────────│◄─────────────────────│                   │                        │
       │                          │                      │                   │                        │
       │                          │                      │                   │                        │
       │                          │            ┌─────────────────────────────┴────────────────────────┤
       │                          │            │              TEMPORAL WORKFLOW EXECUTION             │
       │                          │            ├──────────────────────────────────────────────────────┤
       │                          │            │                                                       │
       │                          │            │  Activity 1: validate_course(course_id)              │
       │                          │            │  ├─ Check course has modules                         │
       │                          │            │  ├─ Check course has content                         │
       │                          │            │  └─ Return: {valid: true}                            │
       │                          │            │                       │                               │
       │                          │            │  Activity 2: process_content(course_id)              │
       │                          │            │  ├─ Extract text from materials ─────────────────────┼──────────────►│
       │                          │            │  ├─ Chunk content                                    │               │
       │                          │            │  ├─ Store in MongoDB                                 │               │
       │                          │            │  └─ Return: {chunks_count: 50}                       │◄──────────────┤
       │                          │            │                       │                               │
       │                          │            │  Activity 3: update_search_index(course_id)          │
       │                          │            │  ├─ Index course in search engine                    │
       │                          │            │  └─ Return: {indexed: true}                          │
       │                          │            │                       │                               │
       │                          │            │  Activity 4: mark_published(course_id)               │
       │                          │            │  ├─ Update course status = 'published'               │
       │                          │            │  ├─ Set published_at = NOW()                         │
       │                          │            │  └─ Return: {success: true}                          │
       │                          │            │                       │                               │
       │                          │            │  Activity 5: publish_event(course.published)         │
       │                          │            │  ├─ Send to Kafka                                    │
       │                          │            │  └─ Notify Analytics & Notification services         │
       │                          │            │                       │                               │
       │                          │            │  ═══════ WORKFLOW COMPLETE ═══════                   │
       │                          │            └──────────────────────────────────────────────────────┘
       │                          │
       │                          │
   ┌───┴───────────────────────────┴─────────────────────────────────────────────────────────────────────────────┐
   │                                         COMPENSATION (ON FAILURE)                                            │
   ├──────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
   │  If any activity fails:                                                                                       │
   │  1. rollback_status(course_id) → Set status back to 'draft'                                                  │
   │  2. cleanup_partial_data(course_id) → Remove partial chunks/indexes                                          │
   │  3. log_failure(workflow_id, error) → Record error for debugging                                             │
   │  4. send_alert(instructor_id, error) → Notify instructor of failure                                          │
   └──────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### 3.2 Student Enrollment Workflow

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     STUDENT ENROLLMENT WORKFLOW (Temporal)                                        │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

    STUDENT            API GATEWAY       ENROLLMENT SVC        TEMPORAL        PROGRESS SVC     NOTIFICATION SVC
       │                    │                  │                   │                 │                  │
       │ POST /enroll       │                  │                   │                 │                  │
       │ {course_id}        │                  │                   │                 │                  │
       │───────────────────►│                  │                   │                 │                  │
       │                    │  Forward         │                   │                 │                  │
       │                    │─────────────────►│                   │                 │                  │
       │                    │                  │                   │                 │                  │
       │                    │                  │ ┌────────────────────────────────────────────────────────────┐
       │                    │                  │ │           VALIDATION (Synchronous)                        │
       │                    │                  │ ├────────────────────────────────────────────────────────────┤
       │                    │                  │ │ 1. Check if course exists and is published                │
       │                    │                  │ │ 2. Check if student not already enrolled                  │
       │                    │                  │ │ 3. Check enrollment limit not exceeded                    │
       │                    │                  │ │ 4. Check prerequisites completed                          │
       │                    │                  │ └────────────────────────────────────────────────────────────┘
       │                    │                  │                   │                 │                  │
       │                    │                  │ Create enrollment │                 │                  │
       │                    │                  │ (PENDING status)  │                 │                  │
       │                    │                  │───────────────────┤                 │                  │
       │                    │                  │                   │                 │                  │
       │                    │                  │ StartWorkflow     │                 │                  │
       │                    │                  │ (enrollment_id)   │                 │                  │
       │                    │                  │──────────────────►│                 │                  │
       │                    │                  │                   │                 │                  │
       │                    │                  │ workflow_id       │                 │                  │
       │                    │                  │◄──────────────────│                 │                  │
       │                    │                  │                   │                 │                  │
       │                    │  enrollment_id   │                   │                 │                  │
       │  {enrollment_id,   │◄─────────────────│                   │                 │                  │
       │   status: PENDING} │                  │                   │                 │                  │
       │◄───────────────────│                  │                   │                 │                  │
       │                    │                  │                   │                 │                  │
       │                    │                  │         ┌─────────┴─────────────────┴──────────────────┤
       │                    │                  │         │         TEMPORAL WORKFLOW EXECUTION          │
       │                    │                  │         ├──────────────────────────────────────────────┤
       │                    │                  │         │                                               │
       │                    │                  │         │  Activity 1: initialize_progress             │
       │                    │                  │         │  ├─ Create progress record ─────────────────►│
       │                    │                  │         │  ├─ Get course modules/lessons count         │
       │                    │                  │         │  ├─ Set all to NOT_STARTED                   │
       │                    │                  │         │  └─ Return: {progress_id}              ◄─────┤
       │                    │                  │         │                       │                       │
       │                    │                  │         │  Activity 2: update_analytics                │
       │                    │                  │         │  ├─ Increment enrollment counter              │
       │                    │                  │         │  ├─ Update course enrollment_count           │
       │                    │                  │         │  ├─ Update instructor total_students         │
       │                    │                  │         │  └─ Publish to Kafka analytics topic         │
       │                    │                  │         │                       │                       │
       │                    │                  │         │  Activity 3: activate_enrollment             │
       │                    │                  │         │  ├─ Update status = 'active'                 │
       │                    │                  │         │  ├─ Set started_at = NOW()                   │
       │                    │                  │         │  └─ Return: {success: true}                  │
       │                    │                  │         │                       │                       │
       │                    │                  │         │  Activity 4: send_welcome_notification       │
       │                    │                  │         │  ├─ Queue email via Celery ─────────────────────────────►│
       │                    │                  │         │  ├─ Create in-app notification               │          │
       │                    │                  │         │  └─ Return: {notified: true}           ◄─────────────────┤
       │                    │                  │         │                       │                       │
       │                    │                  │         │  ═══════ WORKFLOW COMPLETE ═══════           │
       │                    │                  │         └──────────────────────────────────────────────┘
       │                    │                  │
       │  ┌────────────────────────────────────┴────────────────────────────────────────────────────────────────────┐
       │  │                                   IDEMPOTENCY HANDLING                                                   │
       │  ├─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
       │  │  Idempotency Key: SHA256(student_id + course_id + date)                                                 │
       │  │  • Stored in Redis with 24h TTL                                                                         │
       │  │  • If key exists, return existing enrollment_id                                                         │
       │  │  • Prevents duplicate enrollments from retry requests                                                   │
       │  └─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### 3.3 Progress Update & Course Completion Flow

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     PROGRESS UPDATE & COMPLETION FLOW                                             │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

    STUDENT            API GATEWAY       PROGRESS SVC         KAFKA           ANALYTICS      CERTIFICATE SVC
       │                    │                  │                 │                 │                  │
       │ POST /lessons/     │                  │                 │                 │                  │
       │ {lesson_id}/       │                  │                 │                 │                  │
       │ complete           │                  │                 │                 │                  │
       │───────────────────►│                  │                 │                 │                  │
       │                    │  Forward         │                 │                 │                  │
       │                    │─────────────────►│                 │                 │                  │
       │                    │                  │                 │                 │                  │
       │                    │                  │ ┌──────────────────────────────────────────────────────────┐
       │                    │                  │ │                PROGRESS UPDATE LOGIC                     │
       │                    │                  │ ├──────────────────────────────────────────────────────────┤
       │                    │                  │ │ 1. Add lesson_id to completed_lessons[]                  │
       │                    │                  │ │ 2. Recalculate completion_percentage                     │
       │                    │                  │ │ 3. Check if module completed                             │
       │                    │                  │ │ 4. Update last_accessed_at                               │
       │                    │                  │ │ 5. Cache in Redis for fast reads                         │
       │                    │                  │ └──────────────────────────────────────────────────────────┘
       │                    │                  │                 │                 │                  │
       │                    │                  │ Publish Event   │                 │                  │
       │                    │                  │ progress.updated│                 │                  │
       │                    │                  │────────────────►│                 │                  │
       │                    │                  │                 │                 │                  │
       │                    │                  │                 │ Consume         │                  │
       │                    │                  │                 │────────────────►│                  │
       │                    │                  │                 │                 │ Update metrics   │
       │                    │                  │                 │                 │                  │
       │                    │  {progress}      │                 │                 │                  │
       │  {updated progress}│◄─────────────────│                 │                 │                  │
       │◄───────────────────│                  │                 │                 │                  │
       │                    │                  │                 │                 │                  │
       │                    │                  │                 │                 │                  │
   ════╪════════════════════╪══════════════════╪═════════════════╪═════════════════╪══════════════════╪═══════════
       │                    │                  │ IF completion = 100%              │                  │
       │                    │                  │                 │                 │                  │
       │                    │                  │ Publish Event   │                 │                  │
       │                    │                  │ enrollment.     │                 │                  │
       │                    │                  │ completed       │                 │                  │
       │                    │                  │────────────────►│                 │                  │
       │                    │                  │                 │                 │                  │
       │                    │                  │                 │ Consume         │                  │
       │                    │                  │                 │────────────────────────────────────►│
       │                    │                  │                 │                 │                  │
       │                    │                  │                 │                 │    Generate      │
       │                    │                  │                 │                 │    Certificate   │
       │                    │                  │                 │                 │    (Temporal)    │
       │                    │                  │                 │                 │                  │
       │                    │                  │                 │                 │    Store cert    │
       │                    │                  │                 │                 │    Send email    │
       │                    │                  │                 │                 │                  │
       │                    │                  │                 │                 │                  │
       │◄─────────────────────────────────────────────────────────────────────────────────────────────┤
       │  Email: "Congratulations! Your certificate is ready"                                         │
       │                    │                  │                 │                 │                  │
```

---

## 4. Data Flow Diagrams

### 4.1 Read Path (Course Catalog)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                         READ PATH - COURSE CATALOG                                                │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

                        ┌───────────────────┐
                        │      CLIENT       │
                        └─────────┬─────────┘
                                  │ GET /courses?category=python&page=1
                                  ▼
                        ┌───────────────────┐
                        │   API GATEWAY     │
                        └─────────┬─────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    │             │             │
                    ▼             ▼             ▼
              ┌──────────┐ ┌──────────┐ ┌──────────────┐
              │  Redis   │ │  Cache   │ │  Course      │
              │  Check   │ │  HIT?    │ │  Service     │
              └────┬─────┘ └────┬─────┘ └──────┬───────┘
                   │            │              │
                   │ Yes        │ No           │
                   ▼            ▼              ▼
            ┌──────────────────────────────────────────┐
            │            CACHE STRATEGY                 │
            ├──────────────────────────────────────────┤
            │ Key: courses:category:{cat}:page:{p}     │
            │ TTL: 5 minutes                           │
            │ Invalidation: On course publish/update   │
            └──────────────────────────────────────────┘
                                  │
                                  │ Cache Miss
                                  ▼
                        ┌───────────────────┐
                        │   PostgreSQL      │
                        │   (Read Replica)  │
                        └─────────┬─────────┘
                                  │
                                  │ Join with instructor profile
                                  │ Filter by status='published'
                                  │ Order by published_at DESC
                                  │ LIMIT 20 OFFSET (page-1)*20
                                  ▼
                        ┌───────────────────┐
                        │   Enrich Data     │
                        │   • Enrollment    │
                        │     count         │
                        │   • Average       │
                        │     rating        │
                        └─────────┬─────────┘
                                  │
                                  │ Store in Redis
                                  ▼
                        ┌───────────────────┐
                        │   Return to       │
                        │   Client          │
                        └───────────────────┘
```

### 4.2 Write Path (Enrollment)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                         WRITE PATH - ENROLLMENT                                                   │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

         CLIENT                                      ENROLLMENT SERVICE                            DATA STORES
            │                                              │                                            │
            │  POST /enrollments                           │                                            │
            │  {course_id: 123}                            │                                            │
            │─────────────────────────────────────────────►│                                            │
            │                                              │                                            │
            │                                              │  ┌─────────────────────────────────────────┤
            │                                              │  │         WRITE-AHEAD PATTERN             │
            │                                              │  ├─────────────────────────────────────────┤
            │                                              │  │                                         │
            │                                              │  │  1. BEGIN TRANSACTION                   │
            │                                              │  │     │                                   │
            │                                              │  │     ├─► INSERT enrollment ────────────────────────► PostgreSQL
            │                                              │  │     │   (status: PENDING)               │
            │                                              │  │     │                                   │
            │                                              │  │     ├─► INSERT event ──────────────────────────────► Events Table
            │                                              │  │     │   (enrollment.created)            │
            │                                              │  │     │                                   │
            │                                              │  │  2. COMMIT TRANSACTION                  │
            │                                              │  │                                         │
            │                                              │  │  3. Publish to Kafka ──────────────────────────────► Kafka
            │                                              │  │     (enrollment.events topic)           │
            │                                              │  │                                         │
            │                                              │  │  4. Set idempotency key ─────────────────────────► Redis
            │                                              │  │     (TTL: 24h)                          │
            │                                              │  │                                         │
            │                                              │  │  5. Start Temporal workflow             │
            │                                              │  │                                         │
            │                                              │  └─────────────────────────────────────────┤
            │                                              │                                            │
            │◄─────────────────────────────────────────────│                                            │
            │  {enrollment_id, status: PENDING}            │                                            │
            │                                              │                                            │
```

---

## 5. Service Specifications

### 5.1 API Gateway

| Property             | Value                                                                          |
| -------------------- | ------------------------------------------------------------------------------ |
| **Port**             | 8000                                                                           |
| **Technology**       | FastAPI + Uvicorn                                                              |
| **Responsibilities** | JWT Verification (HS256), Rate Limiting, Request Routing, Response Aggregation |
| **Connects To**      | All microservices, Redis                                                       |
| **Dockerfile**       | services/api-gateway/Dockerfile                                                |
| **Dependencies**     | pyproject.toml (NO requirements.txt)                                           |

**Key Middleware:**

- JWT Verification using HS256 (python-jose) - **Only point where JWT is verified**
- Rate Limiting (redis-based, 100 req/min per user)
- Request Validation (Pydantic)
- OpenTelemetry Tracing

**Important:** The API Gateway is the ONLY interface for frontend clients. All JWT verification happens here. Backend services trust requests forwarded from the gateway.

---

### 5.2 User Service

| Property             | Value                                   |
| -------------------- | --------------------------------------- |
| **Port**             | 8001                                    |
| **Database**         | PostgreSQL (users, instructor_profiles) |
| **Cache**            | Redis (sessions, tokens)                |
| **Events Published** | user.registered, user.verified          |
| **Dockerfile**       | services/user-service/Dockerfile        |
| **Dependencies**     | pyproject.toml (NO requirements.txt)    |
| **Local Dev**        | venv per service                        |

**Responsibilities:**

- User registration, login, profile management
- JWT token generation (HS256 algorithm)
- Password management (bcrypt hashing)
- Instructor profile management
- All authentication-related functionality

**Endpoints:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /auth/register | User registration |
| POST | /auth/login | User login, returns JWT (HS256) |
| POST | /auth/refresh | Refresh access token |
| GET | /auth/me | Current user profile |
| GET | /users/{id} | Get user by ID |
| PUT | /users/{id} | Update user profile |
| GET | /instructors/{id} | Get instructor profile |

---

### 5.3 Course Service (MERGED)

| Property                | Value                                                                     |
| ----------------------- | ------------------------------------------------------------------------- |
| **Port**                | 8002                                                                      |
| **Database**            | PostgreSQL (courses, enrollments, certificates), MongoDB (course_content) |
| **Events Published**    | course._, enrollment._, progress._, certificate._                         |
| **Workflows Triggered** | CoursePublishingWorkflow, CertificateGenerationWorkflow                   |
| **Dockerfile**          | services/course-service/Dockerfile                                        |
| **Dependencies**        | pyproject.toml (NO requirements.txt)                                      |
| **Local Dev**           | venv per service                                                          |

**Note:** This service combines the functionality of the previously separate Course, Enrollment, Progress, and Certificate services.

**Responsibilities:**

- Course CRUD, modules, lessons, materials
- Student enrollments (merged with progress tracking)
- Progress tracking (merged into enrollments table)
- Certificate generation and verification

**Endpoints:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /courses | List courses (paginated, filtered) |
| POST | /courses | Create new course |
| GET | /courses/{id} | Get course details |
| PUT | /courses/{id} | Update course |
| DELETE | /courses/{id} | Archive course |
| POST | /courses/{id}/publish | Publish course |
| POST | /courses/{id}/modules | Add module |
| PUT | /courses/{id}/modules/{mid} | Update module |
| POST | /courses/{id}/materials | Upload material |
| POST | /enrollments | Enroll in course |
| GET | /enrollments/my-courses | Student's enrollments |
| GET | /enrollments/{id} | Get enrollment details (includes progress) |
| DELETE | /enrollments/{id} | Drop course |
| GET | /enrollments/{id}/progress | Get progress summary |
| POST | /lessons/{id}/complete | Mark lesson complete |
| POST | /quizzes/{id}/submit | Submit quiz |
| POST | /enrollments/{id}/certificate | Generate certificate |
| GET | /certificates/{id} | Get certificate |
| GET | /certificates/verify/{code} | Verify certificate |

---

### 5.4 Enrollment Service

| Property                | Value                                                        |
| ----------------------- | ------------------------------------------------------------ |
| **Port**                | 8003                                                         |
| **Database**            | PostgreSQL (enrollments, enrollment_history)                 |
| **Cache**               | Redis (idempotency keys)                                     |
| **Events Published**    | enrollment.created, enrollment.completed, enrollment.dropped |
| **Workflows Triggered** | EnrollmentWorkflow                                           |

**Endpoints:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /enrollments | Enroll in course |
| GET | /enrollments/my-courses | Student's enrollments |
| GET | /enrollments/{id} | Get enrollment details |
| DELETE | /enrollments/{id} | Drop course |

---

### 5.5 Progress Service

| Property             | Value                                       |
| -------------------- | ------------------------------------------- |
| **Port**             | 8004                                        |
| **Database**         | PostgreSQL (progress)                       |
| **Cache**            | Redis (progress snapshots)                  |
| **Events Published** | progress.updated, progress.module_completed |

**Endpoints:**
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /progress/{enrollment_id} | Get progress |
| POST | /lessons/{id}/complete | Mark lesson complete |
| POST | /quizzes/{id}/submit | Submit quiz |
| GET | /progress/{enrollment_id}/summary | Progress summary |

---

### 5.6 Notification Service

| Property            | Value                      |
| ------------------- | -------------------------- |
| **Port**            | 8005                       |
| **Database**        | PostgreSQL (notifications) |
| **Queue**           | RabbitMQ (via Celery)      |
| **Events Consumed** | All service events         |

**Notification Types:**
| Type | Trigger | Channel |
|------|---------|---------|
| Welcome Email | enrollment.created | Email |
| Course Published | course.published | Email, Push |
| Module Completed | progress.module_completed | In-App |
| Certificate Ready | certificate.issued | Email |
| Course Reminder | Scheduled | Email, Push |

---

### 5.7 Analytics Service

| Property            | Value                          |
| ------------------- | ------------------------------ |
| **Port**            | 8008                           |
| **Database**        | PostgreSQL (analytics_metrics) |
| **Events Consumed** | All service events             |

**Metrics Tracked:**
| Metric | Type | Aggregation |
|--------|------|-------------|
| total_students | Gauge | Real-time |
| total_instructors | Gauge | Real-time |
| total_courses_published | Gauge | Real-time |
| new_enrollments | Counter | Daily/Weekly/Monthly |
| course_completion_rate | Gauge | Daily |
| avg_time_to_complete | Gauge | Daily |
| popular_courses | List | Daily |
| failed_workflows | Counter | Hourly |

---

## 6. Infrastructure Components

### 6.1 Message Queue Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                         MESSAGE QUEUE ARCHITECTURE                                                │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                              KAFKA (Event Streaming)                                             │
│                                                                                                                  │
│  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐   │
│  │  user.events    │   │ course.events   │   │enrollment.events│   │ progress.events │   │analytics.events │   │
│  │                 │   │                 │   │                 │   │                 │   │                 │   │
│  │ Partitions: 3   │   │ Partitions: 6   │   │ Partitions: 6   │   │ Partitions: 12  │   │ Partitions: 3   │   │
│  │ Retention: 7d   │   │ Retention: 7d   │   │ Retention: 7d   │   │ Retention: 3d   │   │ Retention: 30d  │   │
│  └─────────────────┘   └─────────────────┘   └─────────────────┘   └─────────────────┘   └─────────────────┘   │
│                                                                                                                  │
│  Consumer Groups:                                                                                                │
│  • analytics-consumer-group (reads from all topics)                                                             │
│  • notification-consumer-group (reads from enrollment, progress, course)                                        │
│  • content-consumer-group (reads from course.events)                                                            │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                           RABBITMQ (Task Queue)                                                  │
│                                                                                                                  │
│  ┌───────────────────────┐    ┌───────────────────────┐    ┌───────────────────────┐                           │
│  │     email_queue       │    │      sms_queue        │    │   certificate_queue   │                           │
│  │                       │    │                       │    │                       │                           │
│  │  • send_welcome_email │    │  • send_sms_alert    │    │  • generate_pdf       │                           │
│  │  • send_completion    │    │  • send_reminder     │    │  • upload_to_s3       │                           │
│  │  • send_reminder      │    │                       │    │  • send_certificate   │                           │
│  └───────────────────────┘    └───────────────────────┘    └───────────────────────┘                           │
│                                                                                                                  │
│  Workers: Celery (3-5 concurrent, auto-scaling)                                                                 │
│  Retry Policy: 3 attempts, exponential backoff (60s, 300s, 900s)                                                │
│  Dead Letter Queue: failed_tasks (for manual inspection)                                                        │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### 6.2 Caching Strategy

| Cache Key Pattern                 | TTL | Invalidation            | Usage                |
| --------------------------------- | --- | ----------------------- | -------------------- |
| `session:{user_id}`               | 24h | Logout, Password change | User sessions        |
| `rate_limit:{user_id}:{endpoint}` | 1m  | Auto-expire             | Rate limiting        |
| `courses:category:{cat}:page:{p}` | 5m  | Course publish/update   | Course listing       |
| `course:{id}`                     | 10m | Course update           | Course details       |
| `progress:{enrollment_id}`        | 5m  | Progress update         | Progress cache       |
| `user:{id}`                       | 15m | Profile update          | User profile         |
| `idempotency:{key}`               | 24h | Auto-expire             | Duplicate prevention |

---

### 6.3 Database Partitioning

```sql
-- Progress table partitioning by enrollment_id range
CREATE TABLE progress (
    id SERIAL,
    enrollment_id INTEGER NOT NULL,
    -- other columns
    PRIMARY KEY (id, enrollment_id)
) PARTITION BY RANGE (enrollment_id);

CREATE TABLE progress_0_10000 PARTITION OF progress
    FOR VALUES FROM (0) TO (10000);

CREATE TABLE progress_10000_20000 PARTITION OF progress
    FOR VALUES FROM (10000) TO (20000);

-- Analytics metrics partitioning by date
CREATE TABLE analytics_metrics (
    id SERIAL,
    recorded_at TIMESTAMP NOT NULL,
    -- other columns
    PRIMARY KEY (id, recorded_at)
) PARTITION BY RANGE (recorded_at);

CREATE TABLE analytics_metrics_2026_01 PARTITION OF analytics_metrics
    FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');

CREATE TABLE analytics_metrics_2026_02 PARTITION OF analytics_metrics
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
```

---

## 7. Non-Functional Requirements

### 7.1 Performance Targets

| Metric                       | Target  | Measurement          |
| ---------------------------- | ------- | -------------------- |
| API Response Time (P50)      | < 100ms | Prometheus histogram |
| API Response Time (P95)      | < 200ms | Prometheus histogram |
| API Response Time (P99)      | < 500ms | Prometheus histogram |
| Enrollment Workflow Duration | < 5s    | Temporal metrics     |
| Publishing Workflow Duration | < 2m    | Temporal metrics     |
| Event Processing Lag         | < 10s   | Kafka consumer lag   |
| Cache Hit Rate               | > 80%   | Redis stats          |

### 7.2 Availability Targets

| Component   | Target SLA | Recovery                           |
| ----------- | ---------- | ---------------------------------- |
| API Gateway | 99.9%      | Auto-restart, health checks        |
| PostgreSQL  | 99.95%     | Streaming replication, failover    |
| Redis       | 99.9%      | Sentinel/Cluster mode              |
| Kafka       | 99.95%     | Multi-broker, replication factor 3 |
| Temporal    | 99.9%      | Multi-worker, persistence          |

### 7.3 Scalability

| Component        | Horizontal Scaling                | Vertical Scaling |
| ---------------- | --------------------------------- | ---------------- |
| API Gateway      | Load balancer, multiple instances | CPU/Memory       |
| Services         | Kubernetes HPA, 2-10 replicas     | CPU/Memory       |
| PostgreSQL       | Read replicas (up to 5)           | Instance size    |
| MongoDB          | Sharding                          | Instance size    |
| Redis            | Cluster mode (6 nodes)            | Memory           |
| Kafka            | Partition count increase          | Broker count     |
| Celery Workers   | 3-20 workers                      | Concurrency      |
| Temporal Workers | 2-10 workers                      | Activity slots   |

---

## 8. Observability

### 8.1 Metrics (Prometheus)

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "api-gateway"
    static_configs:
      - targets: ["api-gateway:8000"]
    metrics_path: "/metrics"

  - job_name: "user-service"
    static_configs:
      - targets: ["user-service:8001"]

  - job_name: "course-service"
    static_configs:
      - targets: ["course-service:8002"]

  # ... other services

  - job_name: "redis"
    static_configs:
      - targets: ["redis-exporter:9121"]

  - job_name: "postgres"
    static_configs:
      - targets: ["postgres-exporter:9187"]

  - job_name: "kafka"
    static_configs:
      - targets: ["kafka-exporter:9308"]
```

### 8.2 Key Dashboards (Grafana)

| Dashboard              | Panels                                                       |
| ---------------------- | ------------------------------------------------------------ |
| **API Overview**       | Request rate, Error rate, Latency percentiles, Top endpoints |
| **Business Metrics**   | Enrollments, Completions, Active users, Popular courses      |
| **Database Health**    | Connection pool, Query duration, Replication lag             |
| **Kafka Metrics**      | Consumer lag, Throughput, Partition distribution             |
| **Temporal Workflows** | Active workflows, Failure rate, Duration histograms          |
| **Infrastructure**     | CPU, Memory, Disk, Network across all services               |

### 8.3 Distributed Tracing (Jaeger)

```python
# OpenTelemetry instrumentation
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter

# Auto-instrument
FastAPIInstrumentor.instrument_app(app)
SQLAlchemyInstrumentor().instrument(engine=engine)
RedisInstrumentor().instrument()
```

**Trace Flow Example:**

```
[api-gateway] → [enrollment-service] → [postgresql]
                                     → [redis]
                                     → [temporal] → [progress-service] → [postgresql]
                                                  → [notification-service] → [rabbitmq]
                                                  → [analytics-service] → [kafka]
```

---

## 9. Deployment Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                         DOCKER COMPOSE DEPLOYMENT                                                 │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                           INFRASTRUCTURE LAYER                                                   │
│                                                                                                                  │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐       │
│  │PostgreSQL │  │  MongoDB  │  │   Redis   │  │   Kafka   │  │ RabbitMQ  │  │ Temporal  │  │  Zookeeper│       │
│  │   :5432   │  │  :27017   │  │   :6379   │  │   :9092   │  │   :5672   │  │   :7233   │  │   :2181   │       │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘  └───────────┘  └───────────┘  └───────────┘       │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                            SERVICES LAYER                                                        │
│                                                                                                                  │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐       │
│  │API Gateway│  │   User    │  │  Course   │  │Enrollment │  │ Progress  │  │Notification│ │ Analytics │       │
│  │   :8000   │  │   :8001   │  │   :8002   │  │   :8003   │  │   :8004   │  │   :8005   │  │   :8008   │       │
│  │ replicas:2│  │ replicas:2│  │ replicas:2│  │ replicas:2│  │ replicas:2│  │ replicas:1│  │ replicas:1│       │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘  └───────────┘  └───────────┘  └───────────┘       │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                             WORKERS LAYER                                                        │
│                                                                                                                  │
│  ┌──────────────────────────────────────┐  ┌──────────────────────────────────────┐                             │
│  │         CELERY WORKERS               │  │         TEMPORAL WORKERS             │                             │
│  │                                      │  │                                      │                             │
│  │  • worker-1 (concurrency: 4)         │  │  • worker-1 (workflows + activities) │                             │
│  │  • worker-2 (concurrency: 4)         │  │  • worker-2 (workflows + activities) │                             │
│  │  • worker-3 (concurrency: 4)         │  │                                      │                             │
│  └──────────────────────────────────────┘  └──────────────────────────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                          OBSERVABILITY LAYER                                                     │
│                                                                                                                  │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐                                                     │
│  │Prometheus │  │  Grafana  │  │   Jaeger  │  │ Temporal  │                                                     │
│  │   :9090   │  │   :3000   │  │  :16686   │  │  UI:8233  │                                                     │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘                                                     │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Security Considerations

### 10.1 Authentication & Authorization

| Layer         | Mechanism                                 |
| ------------- | ----------------------------------------- |
| API Gateway   | JWT validation, Token refresh             |
| Inter-service | Service mesh / Internal JWT               |
| Database      | Connection pooling, Encrypted credentials |
| Cache         | Password-protected Redis                  |

### 10.2 Data Protection

| Data Type    | Protection                      |
| ------------ | ------------------------------- |
| Passwords    | Bcrypt hashing (cost factor 12) |
| JWT Tokens   | HS256 signing, 15min expiry     |
| PII          | Encrypted at rest (AES-256)     |
| Certificates | Signed, verification codes      |
| API Keys     | Hashed storage, rate limited    |

### 10.3 Network Security

| Control          | Implementation                     |
| ---------------- | ---------------------------------- |
| TLS              | All external traffic               |
| CORS             | Whitelist allowed origins          |
| Rate Limiting    | Per-user, per-endpoint             |
| Input Validation | Pydantic schemas                   |
| SQL Injection    | Parameterized queries (SQLAlchemy) |

---

## 11. Failure Handling

### 11.1 Retry Strategies

| Component            | Strategy    | Max Retries | Backoff         |
| -------------------- | ----------- | ----------- | --------------- |
| HTTP Requests        | Exponential | 3           | 1s, 2s, 4s      |
| Kafka Consumer       | Exponential | 5           | 1s → 60s        |
| Celery Tasks         | Exponential | 3           | 60s, 300s, 900s |
| Temporal Activities  | Exponential | 3           | 10s → 300s      |
| Database Connections | Linear      | 5           | 1s              |

### 11.2 Circuit Breakers

| Service        | Threshold      | Timeout | Recovery            |
| -------------- | -------------- | ------- | ------------------- |
| Course Service | 5 failures/10s | 30s     | Half-open after 30s |
| User Service   | 5 failures/10s | 30s     | Half-open after 30s |
| External APIs  | 3 failures/5s  | 60s     | Half-open after 60s |

### 11.3 Dead Letter Queues

| Queue             | DLQ            | Handling                   |
| ----------------- | -------------- | -------------------------- |
| email_queue       | email_dlq      | Manual review, re-queue    |
| enrollment.events | enrollment_dlq | Alert, manual intervention |
| progress.events   | progress_dlq   | Batch reprocessing         |

---

_Document Version: 1.1 | Last Updated: February 11, 2026_
