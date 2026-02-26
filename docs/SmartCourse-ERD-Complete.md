# SmartCourse - Entity Relationship Diagram (ERD)

**Version:** 2.0  
**Date:** February 26, 2026  
**Author:** SmartCourse Architecture Team  
**Scope:** Complete Platform Entities (Including AI/LLM/Vector DB Components)

---

## Key Schema Decisions

| Decision                                      | Rationale                                                                    |
| --------------------------------------------- | ---------------------------------------------------------------------------- |
| **Separate Progress Table**                   | 1:N relationship - tracks per-lesson progress with percentage granularity    |
| **enrollment_id in Progress (not course_id)** | Correctly scopes progress per enrollment; allows user re-enrollment tracking |
| **progress_percentage + updated_at**          | Enables partial progress tracking (0-100%) and resume functionality          |
| **Auto-issue Certificates**                   | Triggered when course hits 100% completion; reduces manual overhead          |
| **Certificates → enrollment_id only**         | Student/course derived from enrollment, reduces redundancy                   |
| **AI-Generated Content in MongoDB**           | Flexible nested schema (quiz questions, summary), easy teacher edits, version tracking |
| **Conversation history in PostgreSQL**        | Structured, easy pagination by user/session, FK to ai_conversations          |
| **RAG_INDEX_STATUS separate from Qdrant**     | PG tracks indexing state per course; Qdrant only stores vectors — no overlap |
| **AI_GENERATION_HISTORY as audit log only**   | PG stores who/when/how; MongoDB stores the actual content — two sides of one event |
| **Cross-service refs via logical FK**         | AI service references user_id and course_id by value (no DB-level FK across services) |

---

## 1. ERD Visual Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     SMARTCOURSE - ENTITY RELATIONSHIP DIAGRAM                                    │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘


                                          ┌──────────────────────┐
                                          │        USERS         │
                                          ├──────────────────────┤
                                          │ PK id                │
                                          │    email (UNIQUE)    │
                                          │    first_name        │
                                          │    last_name         │
                                          │    password_hash     │
                                          │    role              │
                                          │    is_active         │
                                          │    is_verified       │
                                          │    phone_number      │
                                          │    created_at        │
                                          │    updated_at        │
                                          └──────────┬───────────┘
                                                     │
                         ┌───────────────────────────┴───────────────────────────┐
                         │                                                       │
                         │ 1:1 (becomes instructor)                              │ 1:N (as student)
                         ▼                                                       ▼
              ┌──────────────────────┐                                ┌─────────────────────────────────┐
              │  INSTRUCTOR_PROFILE  │                                │         ENROLLMENTS             │
              ├──────────────────────┤                                ├─────────────────────────────────┤
              │ PK id                │                                │ PK id                           │
              │ FK user_id (UNIQUE)  │                                │ FK student_id                   │◄── Users
              │    specialization    │                                │ FK course_id                    │◄── Courses
              │    bio               │                                │    status                       │
              │    total_students    │                                │    enrolled_at                  │
              │    rating            │                                │    started_at                   │
              │    verified_at       │                                │    completed_at                 │
              └──────────┬───────────┘                                │    dropped_at                   │
                         │                                            │    last_accessed_at             │
                         │ 1:N (creates courses)                      │    payment_status               │
                         ▼                                            │    payment_amount               │
              ┌──────────────────────┐                                │    enrollment_source            │
              │       COURSES        │───────────────────────────────►│    time_spent_minutes           │
              ├──────────────────────┤              1:N               └──────────┬──────────┬───────────┘
              │ PK id                │       (has many enrollments)              │          │
              │    title             │                                           │          │ 1:N (progress)
              │    slug (UNIQUE)     │                                           │          ▼
              │    description       │                                           │  ┌───────────────────┐
              │ FK instructor_id     │                                           │  │     PROGRESS      │
              │    category          │                                           │  ├───────────────────┤
              │    level             │                                           │  │ PK id             │
                                                                                │  │    user_id        │
                                                                                │  │ FK enrollment_id  │
                                                                                │  │    item_type      │
                                                                                │  │    item_id        │
                                                                                │  │    progress_pct   │
                                                                                │  │    completed_at   │
                                                                                │  └───────────────────┘
                                                                                │
                                                                                │ 1:1 (earns certificate)
              │    status            │                                                 ▼
              │    published_at      │                              ┌──────────────────────────────────┐
              │    max_students      │                              │         CERTIFICATES             │
              │    price             │                              ├──────────────────────────────────┤
              │    created_at        │                              │ PK id                            │
              └──────────┬───────────┘                              │ FK enrollment_id (UNIQUE)        │
                         │                                          │    (student_id derived)          │
                         │ 1:1 (has content)                        │    (course_id derived)           │
                         ▼                                          │    certificate_number (UNIQUE)   │
              ┌──────────────────────┐                              │    issue_date                    │
              │    COURSE_CONTENT    │                              │    verification_code (UNIQUE)    │
              │     (MongoDB)        │                              │    grade                         │
              ├──────────────────────┤                              │    is_revoked                    │
              │ _id (ObjectId)       │                              └──────────────────────────────────┘
              │ course_id            │
              │ modules: [           │
              │   { module_id,       │
              │     title,           │
              │     order,           │
              │     lessons: [...] } │
              │ ]                    │
              │ metadata             │
              │ total_duration       │
              └──────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                              SUPPORTING ENTITIES                                                  │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────┐    ┌──────────────────────┐    ┌──────────────────────┐    ┌──────────────────────┐
│     NOTIFICATION     │    │       EVENTS         │    │  ANALYTICS_METRICS   │    │ WORKFLOW_EXECUTIONS  │
├──────────────────────┤    ├──────────────────────┤    ├──────────────────────┤    ├──────────────────────┤
│ PK id                │    │ PK id                │    │ PK id                │    │ PK id                │
│ FK user_id           │    │ FK user_id           │    │    metric_name       │    │    workflow_id       │
│    type              │    │    event_type        │    │    metric_value      │    │    workflow_type     │
│    title             │    │    entity_type       │    │    metric_type       │    │    run_id            │
│    message           │    │    entity_id         │    │    dimension (JSONB) │    │ FK user_id           │
│    priority          │    │    payload (JSONB)   │    │    recorded_at       │    │    status            │
│    is_read           │    │    status            │    │    created_at        │    │    started_at        │
│    created_at        │    │    kafka_offset      │    └──────────────────────┘    │    completed_at      │
└──────────────────────┘    │    created_at        │                                │    result (JSONB)    │
                            └──────────────────────┘                                └──────────────────────┘

                            ┌──────────────────────┐
                            │   COURSE_MATERIALS   │
                            │      (MongoDB)       │
                            ├──────────────────────┤
                            │ _id (ObjectId)       │
                            │ course_id            │
                            │ module_id            │
                            │ lesson_id            │
                            │ file_name            │
                            │ file_type            │
                            │ file_url             │
                            │ created_at           │
                            └──────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                          AI SERVICE ENTITIES                                                      │
│                  Feature 1: AI Tutor (RAG)  │  Feature 2: Quiz & Summary Generation                              │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

  External references (cross-service, logical FK — no DB-level constraint):
  ┌─────────────┐          ┌──────────────────────┐
  │    USERS    │          │       COURSES         │
  │ (user-svc)  │          │  (course-service PG)  │
  └──────┬──────┘          └───────────┬───────────┘
         │ user_id                     │ course_id
         │                             │
─────────┼─────────────────────────────┼───────────────────────────────────────────────────
         │                             │
         │         ╔═══════════════════╩══════════════════════════════════════╗
         │         ║          FEATURE 1: AI TUTOR (RAG)                      ║
         │         ╚══════════════════════════════════════════════════════════╝
         │                             │
         │  ┌──────────────────────────┴──────────────────────────────┐
         │  │                                                          │
         ▼  ▼                                                          ▼
┌──────────────────────────────┐  1:N  ┌───────────────────────────────────────┐
│   AI_CONVERSATIONS (PG)      │──────►│          AI_MESSAGES (PG)             │
├──────────────────────────────┤       ├───────────────────────────────────────┤
│ PK id                        │       │ PK id                                 │
│    session_id (UUID, UNIQUE)  │       │ FK conversation_id ──────────────────►│(CASCADE DEL)
│ FK user_id  (→ users)        │       │    role  ('user' | 'assistant')       │
│    course_id (→ courses)     │       │    content (TEXT)                     │
│    is_active                  │       │    retrieved_context (JSONB) ─────────┼──► Qdrant chunk IDs
│    created_at                 │       │    tokens_used                        │
│    updated_at                 │       │    model / latency_ms                 │
└──────────────────────────────┘       │    created_at                         │
                                       └───────────────────────────────────────┘

┌──────────────────────────────┐  tracks  ┌──────────────────────────────────────┐
│   RAG_INDEX_STATUS (PG)      │─────────►│      COURSE_EMBEDDINGS (Qdrant)      │
├──────────────────────────────┤          ├──────────────────────────────────────┤
│ PK id                        │          │ id (UUID)                            │
│    course_id (UNIQUE)        │◄─────────│ payload.course_id  (same course)     │
│    status                    │          │ payload.module_id                    │
│    indexed_at                │          │ payload.lesson_id  (→ MongoDB lesson)│
│    total_chunks              │          │ payload.chunk_index                  │
│    total_lessons             │          │ payload.text  (chunk content)        │
│    embedding_model           │          │ payload.metadata { titles }          │
│    last_content_hash (MD5)   │          │ vector [1536 dims, Cosine]           │
│    created_at / updated_at   │          └──────────────────────────────────────┘
└──────────────────────────────┘

─────────────────────────────────────────────────────────────────────────────────────────────
         │                             │
         │         ╔═══════════════════╩══════════════════════════════════════╗
         │         ║       FEATURE 2: QUIZ & SUMMARY GENERATION               ║
         │         ╚══════════════════════════════════════════════════════════╝
         │                             │
         ▼                             ▼
┌──────────────────────────────┐              ┌──────────────────────────────────┐
│  AI_GENERATION_HISTORY (PG)  │──soft link──►│    AI_GENERATED_CONTENT (Mongo)  │
│    (the audit log)           │ (course_id + │    (the actual output)           │
├──────────────────────────────┤  module_id)  ├──────────────────────────────────┤
│ PK id                        │              │ _id (ObjectId)                   │
│    course_id  (→ courses)    │◄─────────────│ course_id   (same course)        │
│    module_id                 │◄─────────────│ module_id   (same module)        │
│    generation_type           │              │ summary: {                       │
│      ('quiz' | 'summary')    │              │   content, version, model,       │
│    version                   │              │   is_edited, original_content }  │
│ FK triggered_by (→ users)    │              │ quiz: {                          │
│    input_lesson_count        │              │   questions[], version,          │
│    tokens_used               │              │   settings, is_edited }          │
│    status                    │              │ source_lesson_ids[]              │
│    error_message             │              │ created_at / updated_at          │
│    created_at                │              └──────────────────────────────────┘
└──────────────────────────────┘

  NOTE: AI_GENERATION_HISTORY and AI_GENERATED_CONTENT share (course_id, module_id) as a
  soft link. PG stores WHO generated it + metrics; MongoDB stores WHAT was generated.
  No hard FK across stores — referential integrity enforced at the application layer.
```

---

## 2. Entity Definitions

### 2.1 Core Entities (PostgreSQL)

#### **USERS**

Central entity storing all platform users with role-based access.

| Column        | Type                                 | Constraints      | Description                  |
| ------------- | ------------------------------------ | ---------------- | ---------------------------- |
| id            | SERIAL                               | PRIMARY KEY      | Auto-incrementing identifier |
| email         | VARCHAR(255)                         | UNIQUE, NOT NULL | User email address           |
| first_name    | VARCHAR(100)                         | NOT NULL         | User's first name            |
| last_name     | VARCHAR(100)                         | NOT NULL         | User's last name             |
| password_hash | VARCHAR(255)                         | NOT NULL         | Bcrypt hashed password       |
| role          | VARCHAR(50)                          | NOT NULL         | student, instructor, admin   |
| is_active     | BOOLEAN                              | DEFAULT TRUE     | Account status               |
| is_verified   | BOOLEAN                              | DEFAULT FALSE    | Email verification           |
| phone_number  | VARCHAR(20)                          |                  | Phone number                 |
| created_at    | TIMESTAMP                            | DEFAULT NOW()    | Creation timestamp           |
| updated_at    | TIMESTAMP                            | ON UPDATE NOW()  | Last update                  |

---

#### **COURSES**

Main entity for course metadata and status tracking.

| Column              | Type                                       | Constraints                            | Description                  |
| ------------------- | ------------------------------------------ | -------------------------------------- | ---------------------------- |
| id                  | SERIAL                                     | PRIMARY KEY                            | Auto-incrementing identifier |
| title               | VARCHAR(255)                               | NOT NULL                               | Course title                 |
| slug                | VARCHAR(255)                               | UNIQUE, NOT NULL                       | URL-friendly identifier      |
| description         | TEXT                                       |                                        | Short description            |
| long_description    | TEXT                                       |                                        | Detailed description         |
| instructor_id       | INTEGER                                    | FK → instructor_profiles(id), NOT NULL | Course instructor            |
| category            | VARCHAR(100)                               | INDEX                                  | Course category              |
| level               | ENUM('beginner','intermediate','advanced') |                                        | Difficulty level             |
| language            | VARCHAR(50)                                | DEFAULT 'en'                           | Course language              |
| duration_hours      | DECIMAL(5,2)                               |                                        | Estimated duration           |
| price               | DECIMAL(10,2)                              | DEFAULT 0.00                           | Course price                 |
| currency            | VARCHAR(3)                                 | DEFAULT 'USD'                          | Price currency               |
| thumbnail_url       | VARCHAR(500)                               |                                        | Thumbnail image              |
| status              | ENUM('draft','published','archived')       | NOT NULL, INDEX                        | Course status                |
| published_at        | TIMESTAMP                                  |                                        | Publication time             |
| max_students        | INTEGER                                    |                                        | Enrollment limit             |
| prerequisites       | TEXT                                       |                                        | Required prerequisites       |
| learning_objectives | TEXT                                       |                                        | What students will learn     |
| created_at          | TIMESTAMP                                  | DEFAULT NOW()                          | Creation time                |
| updated_at          | TIMESTAMP                                  | ON UPDATE NOW()                        | Last update                  |
| is_deleted          | BOOLEAN                                    | DEFAULT FALSE                          | Soft delete flag             |

---

#### **ENROLLMENTS**

Tracks student enrollments in courses.

| Column            | Type          | Constraints                | Description                  |
| ----------------- | ------------- | -------------------------- | ---------------------------- |
| id                | SERIAL        | PRIMARY KEY                | Auto-incrementing identifier |
| student_id        | INTEGER       | NOT NULL, INDEX            | Enrolled student             |
| course_id         | INTEGER       | NOT NULL, INDEX            | Target course                |
| status            | VARCHAR(50)   | NOT NULL, INDEX            | active, completed, dropped, suspended |
| enrolled_at       | TIMESTAMP     | DEFAULT NOW()              | Enrollment time              |
| started_at        | TIMESTAMP     |                            | First access                 |
| completed_at      | TIMESTAMP     |                            | Completion time              |
| dropped_at        | TIMESTAMP     |                            | Drop time                    |
| last_accessed_at  | TIMESTAMP     |                            | Last course access           |
| payment_status    | VARCHAR(50)   |                            | pending, completed, refunded |
| payment_amount    | DECIMAL(10,2) |                            | Amount paid                  |
| enrollment_source | VARCHAR(100)  |                            | web, mobile, api             |
| time_spent_minutes| INTEGER       | DEFAULT 0                  | Total time spent             |
| created_at        | TIMESTAMP     | DEFAULT NOW()              | Record creation              |
| updated_at        | TIMESTAMP     | ON UPDATE NOW()            | Last update                  |

**Unique Constraint:** `(student_id, course_id)`

**Note:** Progress tracking is handled by the separate PROGRESS table (1:N relationship per enrollment). Each lesson/quiz/summary gets its own progress row.

---

#### **PROGRESS**

Tracks per-lesson progress for each enrollment. One row per (user, enrollment, item).

| Column              | Type         | Constraints                           | Description                                      |
| ------------------- | ------------ | ------------------------------------- | ------------------------------------------------ |
| id                  | SERIAL       | PRIMARY KEY                           | Auto-incrementing identifier                     |
| user_id             | INTEGER      | NOT NULL, INDEX                       | User who owns this progress                      |
| enrollment_id       | INTEGER      | FK → enrollments(id), NOT NULL, INDEX | The enrollment this progress belongs to          |
| item_type           | VARCHAR(20)  | NOT NULL                              | 'lesson', 'quiz', or 'summary'                   |
| item_id             | VARCHAR(50)  | NOT NULL                              | MongoDB ID of the lesson/quiz/summary            |
| progress_percentage | DECIMAL(5,2) | NOT NULL, DEFAULT 0.00                | 0.00 to 100.00 — how far the user has progressed |
| completed_at        | TIMESTAMP    | NULLABLE                              | Set only when progress_percentage reaches 100    |
| created_at          | TIMESTAMP    | NOT NULL, DEFAULT NOW()               | Row creation timestamp                           |
| updated_at          | TIMESTAMP    | NOT NULL, DEFAULT NOW()               | Last progress update timestamp                   |

**Unique Constraint:** `(user_id, enrollment_id, item_type, item_id)`

**How Progress Aggregation Works:**

- **Lesson progress**: Stored directly as `progress_percentage` (0–100) in each row
- **Module progress**: Average of all lesson percentages within the module (lessons with no row = 0%)
- **Course progress**: Average of ALL lesson percentages across ALL modules
- **Completion**: An item is "completed" when `progress_percentage = 100` and `completed_at IS NOT NULL`
- **Course completion**: When ALL items reach 100%, enrollment status → 'completed', certificate auto-issued

---

#### **CERTIFICATES**

Generated certificates for course completion. **Only references enrollment_id** - student and course info are derived from the enrollment relationship.

| Column             | Type         | Constraints                  | Description                  |
| ------------------ | ------------ | ---------------------------- | ---------------------------- |
| id                 | SERIAL       | PRIMARY KEY                  | Auto-incrementing identifier |
| enrollment_id      | INTEGER      | FK → enrollments(id), UNIQUE | Related enrollment           |
| certificate_number | VARCHAR(100) | UNIQUE, NOT NULL             | Unique cert number           |
| issue_date         | DATE         | NOT NULL                     | Issue date                   |
| certificate_url    | VARCHAR(500) |                              | PDF URL                      |
| verification_code  | VARCHAR(50)  | UNIQUE, NOT NULL             | Public verification          |
| grade              | VARCHAR(10)  |                              | Final grade (A,B,C)          |
| score_percentage   | DECIMAL(5,2) |                              | Final score %                |
| issued_by_id       | INTEGER      | FK → users(id)               | Issuing instructor           |
| is_revoked         | BOOLEAN      | DEFAULT FALSE                | Revocation status            |
| revoked_at         | TIMESTAMP    |                              | Revocation time              |
| revoked_reason     | TEXT         |                              | Revocation reason            |
| created_at         | TIMESTAMP    | DEFAULT NOW()                | Creation time                |

**Note:** student_id and course_id are NOT stored directly. They are derived via the enrollment relationship:

- `certificate.enrollment.student_id` → get student
- `certificate.enrollment.course_id` → get course

This reduces data redundancy and ensures consistency.

---

#### **NOTIFICATIONS**

User notifications for system events.

| Column              | Type                                                               | Constraints              | Description                  |
| ------------------- | ------------------------------------------------------------------ | ------------------------ | ---------------------------- |
| id                  | SERIAL                                                             | PRIMARY KEY              | Auto-incrementing identifier |
| user_id             | INTEGER                                                            | FK → users(id), NOT NULL | Recipient                    |
| type                | ENUM('enrollment','completion','announcement','reminder','system') | NOT NULL                 | Notification type            |
| title               | VARCHAR(255)                                                       | NOT NULL                 | Title                        |
| message             | TEXT                                                               | NOT NULL                 | Message content              |
| action_url          | VARCHAR(500)                                                       |                          | Action link                  |
| priority            | ENUM('low','normal','high','urgent')                               | DEFAULT 'normal'         | Priority level               |
| is_read             | BOOLEAN                                                            | DEFAULT FALSE            | Read status                  |
| read_at             | TIMESTAMP                                                          |                          | Read timestamp               |
| related_entity_type | VARCHAR(50)                                                        |                          | Related entity               |
| related_entity_id   | INTEGER                                                            |                          | Entity ID                    |
| metadata            | JSONB                                                              |                          | Additional data              |
| created_at          | TIMESTAMP                                                          | DEFAULT NOW()            | Creation time                |
| expires_at          | TIMESTAMP                                                          |                          | Auto-delete time             |

---

#### **INSTRUCTOR_PROFILES**

Extended profile for instructors.

| Column         | Type         | Constraints                      | Description                  |
| -------------- | ------------ | -------------------------------- | ---------------------------- |
| id             | SERIAL       | PRIMARY KEY                      | Auto-incrementing identifier |
| user_id        | INTEGER      | FK → users(id), UNIQUE, NOT NULL | Related user                 |
| specialization | VARCHAR(255) |                                  | Areas of expertise           |
| bio            | TEXT         |                                  | Detailed biography           |
| website_url    | VARCHAR(500) |                                  | Personal website             |
| linkedin_url   | VARCHAR(500) |                                  | LinkedIn profile             |
| total_students | INTEGER      | DEFAULT 0                        | Total enrolled students      |
| total_courses  | INTEGER      | DEFAULT 0                        | Published courses            |
| average_rating | DECIMAL(3,2) | DEFAULT 0.00                     | Average rating 0-5           |
| total_reviews  | INTEGER      | DEFAULT 0                        | Review count                 |
| is_verified    | BOOLEAN      | DEFAULT FALSE                    | Verified instructor          |
| verified_at    | TIMESTAMP    |                                  | Verification date            |
| payout_info    | JSONB        |                                  | Payment details              |
| created_at     | TIMESTAMP    | DEFAULT NOW()                    | Creation time                |
| updated_at     | TIMESTAMP    | ON UPDATE NOW()                  | Last update                  |

---

#### **ANALYTICS_METRICS**

Aggregated metrics for dashboards.

| Column             | Type                                | Constraints     | Description                  |
| ------------------ | ----------------------------------- | --------------- | ---------------------------- |
| id                 | SERIAL                              | PRIMARY KEY     | Auto-incrementing identifier |
| metric_name        | VARCHAR(100)                        | NOT NULL, INDEX | Metric identifier            |
| metric_value       | DECIMAL(10,2)                       | NOT NULL        | Metric value                 |
| metric_type        | ENUM('counter','gauge','histogram') | NOT NULL        | Metric type                  |
| dimension          | JSONB                               |                 | Labels/dimensions            |
| aggregation_period | VARCHAR(20)                         |                 | 'hourly','daily','weekly'    |
| recorded_at        | TIMESTAMP                           | NOT NULL, INDEX | Metric timestamp             |
| created_at         | TIMESTAMP                           | DEFAULT NOW()   | Record creation              |

---

#### **EVENTS**

Event log for Kafka tracking and audit.

| Column          | Type                                              | Constraints       | Description                  |
| --------------- | ------------------------------------------------- | ----------------- | ---------------------------- |
| id              | SERIAL                                            | PRIMARY KEY       | Auto-incrementing identifier |
| event_type      | VARCHAR(100)                                      | NOT NULL, INDEX   | Event type                   |
| event_name      | VARCHAR(255)                                      | NOT NULL          | Human-readable name          |
| entity_type     | VARCHAR(50)                                       |                   | Related entity type          |
| entity_id       | INTEGER                                           |                   | Related entity ID            |
| user_id         | INTEGER                                           | FK → users(id)    | Triggering user              |
| payload         | JSONB                                             | NOT NULL          | Event data                   |
| status          | ENUM('pending','processing','completed','failed') | DEFAULT 'pending' | Processing status            |
| kafka_offset    | BIGINT                                            |                   | Kafka offset                 |
| kafka_partition | INTEGER                                           |                   | Kafka partition              |
| processed_at    | TIMESTAMP                                         |                   | Completion time              |
| error_message   | TEXT                                              |                   | Error details                |
| retry_count     | INTEGER                                           | DEFAULT 0         | Retry count                  |
| created_at      | TIMESTAMP                                         | DEFAULT NOW()     | Creation time                |

---

#### **WORKFLOW_EXECUTIONS**

Temporal workflow tracking.

| Column           | Type                                             | Constraints      | Description                  |
| ---------------- | ------------------------------------------------ | ---------------- | ---------------------------- |
| id               | SERIAL                                           | PRIMARY KEY      | Auto-incrementing identifier |
| workflow_id      | VARCHAR(255)                                     | UNIQUE, NOT NULL | Temporal workflow ID         |
| workflow_type    | VARCHAR(100)                                     | NOT NULL, INDEX  | Workflow type                |
| run_id           | VARCHAR(255)                                     | NOT NULL         | Temporal run ID              |
| entity_type      | VARCHAR(50)                                      |                  | Related entity               |
| entity_id        | INTEGER                                          |                  | Entity ID                    |
| user_id          | INTEGER                                          | FK → users(id)   | Triggering user              |
| input_data       | JSONB                                            |                  | Workflow inputs              |
| status           | ENUM('running','completed','failed','cancelled') | NOT NULL, INDEX  | Execution status             |
| started_at       | TIMESTAMP                                        | DEFAULT NOW()    | Start time                   |
| completed_at     | TIMESTAMP                                        |                  | Completion time              |
| duration_ms      | INTEGER                                          |                  | Duration in ms               |
| current_activity | VARCHAR(100)                                     |                  | Current activity             |
| error_message    | TEXT                                             |                  | Error details                |
| result           | JSONB                                            |                  | Workflow result              |
| created_at       | TIMESTAMP                                        | DEFAULT NOW()    | Creation time                |

---

### 2.2 Document Entities (MongoDB)

#### **COURSE_CONTENT**

Flexible course content storage.

```json
{
  "_id": "ObjectId",
  "course_id": 123,
  "modules": [
    {
      "module_id": 1,
      "title": "Introduction",
      "description": "Getting started",
      "order": 1,
      "is_published": true,
      "lessons": [
        {
          "lesson_id": 1,
          "title": "Welcome",
          "type": "video|text|quiz|assignment",
          "content": "Lesson content here",
          "duration_minutes": 15,
          "order": 1,
          "is_preview": false,
          "resources": [
            {
              "name": "slides.pdf",
              "url": "s3://...",
              "type": "pdf"
            }
          ]
        }
      ]
    }
  ],
  "metadata": {
    "total_modules": 10,
    "total_lessons": 50,
    "total_duration_hours": 40,
    "tags": ["python", "programming"]
  },
  "created_at": "2026-02-10T00:00:00Z",
  "updated_at": "2026-02-10T00:00:00Z"
}
```

#### **COURSE_MATERIALS**

Course learning materials.

```json
{
  "_id": "ObjectId",
  "course_id": 123,
  "module_id": 1,
  "lesson_id": 1,
  "file_name": "lecture-notes.pdf",
  "file_type": "application/pdf",
  "file_size_bytes": 1048576,
  "file_url": "s3://bucket/materials/lecture-notes.pdf",
  "storage_provider": "s3",
  "is_downloadable": true,
  "metadata": {
    "pages": 25,
    "author": "John Doe"
  },
  "created_at": "2026-02-10T00:00:00Z",
  "uploaded_by": 1
}
```

---

### 2.3 AI Service Entities

#### **AI_CONVERSATIONS** (PostgreSQL)

Chat sessions between students and AI Tutor.

| Column     | Type      | Constraints               | Description                  |
| ---------- | --------- | ------------------------- | ---------------------------- |
| id         | SERIAL    | PRIMARY KEY               | Auto-incrementing identifier |
| session_id | UUID      | UNIQUE, NOT NULL, DEFAULT | Unique session identifier    |
| user_id    | INTEGER   | NOT NULL, INDEX           | Student user ID              |
| course_id  | INTEGER   | NOT NULL                  | Course context for chat      |
| created_at | TIMESTAMP | DEFAULT NOW()             | Session start time           |
| updated_at | TIMESTAMP | ON UPDATE NOW()           | Last activity time           |
| is_active  | BOOLEAN   | DEFAULT TRUE              | Session active status        |

---

#### **AI_MESSAGES** (PostgreSQL)

Individual messages within AI Tutor conversations.

| Column            | Type        | Constraints                         | Description                   |
| ----------------- | ----------- | ----------------------------------- | ----------------------------- |
| id                | SERIAL      | PRIMARY KEY                         | Auto-incrementing identifier  |
| conversation_id   | INTEGER     | FK → ai_conversations(id), NOT NULL | Parent conversation           |
| role              | VARCHAR(20) | NOT NULL                            | 'user', 'assistant', 'system' |
| content           | TEXT        | NOT NULL                            | Message content               |
| retrieved_context | JSONB       |                                     | RAG context chunks            |
| tokens_used       | INTEGER     |                                     | LLM tokens consumed           |
| model             | VARCHAR(50) |                                     | Model used (gpt-4o-mini)      |
| latency_ms        | INTEGER     |                                     | Response latency              |
| created_at        | TIMESTAMP   | DEFAULT NOW()                       | Message timestamp             |

---

#### **AI_GENERATION_HISTORY** (PostgreSQL)

Audit trail for quiz/summary generation by teachers.

| Column             | Type         | Constraints         | Description                         |
| ------------------ | ------------ | ------------------- | ----------------------------------- |
| id                 | SERIAL       | PRIMARY KEY         | Auto-incrementing identifier        |
| course_id          | INTEGER      | NOT NULL            | Course ID                           |
| module_id          | VARCHAR(100) | NOT NULL            | Module ID (MongoDB ObjectId string) |
| generation_type    | VARCHAR(20)  | NOT NULL            | 'quiz' or 'summary'                 |
| version            | INTEGER      | NOT NULL            | Generation version (1, 2, 3...)     |
| triggered_by       | INTEGER      | NOT NULL            | Teacher user ID                     |
| input_lesson_count | INTEGER      |                     | Number of lessons processed         |
| model              | VARCHAR(50)  |                     | LLM model used                      |
| tokens_used        | INTEGER      |                     | Total tokens consumed               |
| latency_ms         | INTEGER      |                     | Generation time                     |
| status             | VARCHAR(20)  | DEFAULT 'completed' | 'pending', 'completed', 'failed'    |
| error_message      | TEXT         |                     | Error details if failed             |
| created_at         | TIMESTAMP    | DEFAULT NOW()       | Generation timestamp                |

---

#### **RAG_INDEX_STATUS** (PostgreSQL)

Tracks RAG indexing status for each course.

| Column            | Type        | Constraints       | Description                                |
| ----------------- | ----------- | ----------------- | ------------------------------------------ |
| id                | SERIAL      | PRIMARY KEY       | Auto-incrementing identifier               |
| course_id         | INTEGER     | UNIQUE, NOT NULL  | Course ID                                  |
| status            | VARCHAR(20) | DEFAULT 'pending' | 'pending', 'indexing', 'indexed', 'failed' |
| indexed_at        | TIMESTAMP   |                   | Last successful index time                 |
| total_chunks      | INTEGER     |                   | Number of text chunks indexed              |
| total_lessons     | INTEGER     |                   | Number of lessons processed                |
| embedding_model   | VARCHAR(50) |                   | Model used (text-embedding-3-small)        |
| last_content_hash | VARCHAR(64) |                   | MD5 hash for change detection              |
| created_at        | TIMESTAMP   | DEFAULT NOW()     | Record creation time                       |
| updated_at        | TIMESTAMP   | ON UPDATE NOW()   | Last update time                           |

---

#### **AI_GENERATED_CONTENT** (MongoDB)

AI-generated quizzes and summaries for course modules.

```json
{
  "_id": "ObjectId",
  "course_id": 123,
  "module_id": "mod_abc123",

  "summary": {
    "content": "This module covers the fundamentals of...",
    "version": 3,
    "generated_at": "2026-02-26T10:00:00Z",
    "model": "gpt-4o-mini",
    "is_edited": true,
    "edited_at": "2026-02-26T12:00:00Z",
    "original_content": "Original AI-generated text..."
  },

  "quiz": {
    "questions": [
      {
        "question_id": "q1",
        "question": "What is the main purpose of...",
        "type": "multiple_choice",
        "options": ["Option A", "Option B", "Option C", "Option D"],
        "correct_answer": "B",
        "explanation": "Because...",
        "difficulty": "medium"
      }
    ],
    "version": 2,
    "generated_at": "2026-02-26T10:30:00Z",
    "model": "gpt-4o-mini",
    "is_edited": false,
    "settings": {
      "num_questions": 10,
      "difficulty_distribution": { "easy": 3, "medium": 5, "hard": 2 }
    }
  },

  "source_lesson_ids": ["lesson_1", "lesson_2", "lesson_3"],
  "created_at": "2026-02-26T10:00:00Z",
  "updated_at": "2026-02-26T12:00:00Z"
}
```

---

#### **COURSE_EMBEDDINGS** (Qdrant Vector DB)

Vector embeddings for RAG-based AI Tutor.

```python
# Collection Configuration
{
    "collection_name": "course_embeddings",
    "vectors": {
        "size": 1536,           # text-embedding-3-small dimensions
        "distance": "Cosine"
    }
}

# Point Structure
{
    "id": "uuid-string",
    "vector": [0.123, 0.456, ...],  # 1536 dimensions
    "payload": {
        "course_id": 123,
        "module_id": "mod_abc123",
        "lesson_id": "lesson_xyz",
        "chunk_index": 0,
        "content_type": "text",       # text, pdf, transcript
        "text": "The actual chunk content...",
        "metadata": {
            "lesson_title": "Introduction to...",
            "module_title": "Fundamentals",
            "course_title": "Python Programming"
        }
    }
}
```

---

## 3. Relationship Summary

| Relationship                                 | Cardinality | Description                                               |
| -------------------------------------------- | ----------- | --------------------------------------------------------- |
| Users → Instructor_Profiles                  | 1:1         | Instructors have one profile                              |
| Instructor_Profiles → Courses                | 1:N         | One instructor creates many courses                       |
| Users → Enrollments                          | 1:N         | One student has many enrollments                          |
| Courses → Enrollments                        | 1:N         | One course has many enrollments                           |
| Enrollments → Progress                       | 1:N         | One enrollment has many progress records (per item)       |
| Enrollments → Certificates                   | 1:1         | Each completion has one certificate                       |
| Users → Notifications                        | 1:N         | One user receives many notifications                      |
| Users → Events                               | 1:N         | One user triggers many events                             |
| Users → Workflow_Executions                  | 1:N         | One user triggers many workflows                          |
| Courses → Course_Content (MongoDB)           | 1:1         | Each course has content document                          |
| Courses → Course_Materials (MongoDB)         | 1:N         | Each course has many materials                            |
| Enrollments ↔ Course_Content (MongoDB)       | Reference   | Enrollments store MongoDB module/lesson IDs               |
| **Users → AI_Conversations**                           | **1:N**        | **One student has many AI tutor sessions (logical FK)**             |
| **AI_Conversations → AI_Messages**                     | **1:N**        | **One session has many messages (CASCADE DELETE)**                  |
| **AI_Messages.retrieved_context → Course_Embeddings**  | **ref (JSONB)**| **Each assistant message stores Qdrant chunk IDs + scores used**    |
| **Courses → AI_Conversations**                         | **1:N**        | **One course has many tutor sessions (logical FK)**                 |
| **Courses → RAG_Index_Status**                         | **1:1**        | **Each course has one RAG index status row (UNIQUE course_id)**     |
| **RAG_Index_Status → Course_Embeddings (Qdrant)**      | **tracks**     | **Status row reflects what is indexed in Qdrant for that course**   |
| **Users → AI_Generation_History**                      | **1:N**        | **One teacher triggers many generations (triggered_by FK)**         |
| **Courses → AI_Generation_History**                    | **1:N**        | **One course can have many quiz/summary generations (logical FK)**  |
| **AI_Generation_History ↔ AI_Generated_Content**       | **soft link**  | **(course_id, module_id) ties audit log in PG to output in MongoDB**|
| **Courses → AI_Generated_Content (MongoDB)**           | **1:N**        | **One course has one AI content doc per module**                    |
| **Courses → Course_Embeddings (Qdrant)**               | **1:N**        | **One course has many vector chunks (one per text chunk)**          |
| **Course_Content (MongoDB) → Course_Embeddings**       | **source**     | **Lesson text is chunked, embedded, and stored in Qdrant**          |

---

## 4. Key Indexes

### PostgreSQL Indexes

```sql
-- Users
CREATE UNIQUE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_is_active ON users(is_active);

-- Courses
CREATE UNIQUE INDEX idx_courses_slug ON courses(slug);
CREATE INDEX idx_courses_instructor ON courses(instructor_id);
CREATE INDEX idx_courses_status ON courses(status);
CREATE INDEX idx_courses_category ON courses(category);
CREATE INDEX idx_courses_published_at ON courses(published_at);

-- Enrollments (includes merged Progress fields)
CREATE UNIQUE INDEX idx_enrollments_student_course ON enrollments(student_id, course_id);
CREATE INDEX idx_enrollments_student ON enrollments(student_id);
CREATE INDEX idx_enrollments_course ON enrollments(course_id);
CREATE INDEX idx_enrollments_status ON enrollments(status);
CREATE INDEX idx_enrollments_enrolled_at ON enrollments(enrolled_at);
CREATE INDEX idx_enrollments_last_accessed ON enrollments(last_accessed_at);

-- Progress
CREATE INDEX ix_progress_user_id ON progress(user_id);
CREATE INDEX ix_progress_enrollment_id ON progress(enrollment_id);
CREATE INDEX ix_progress_user_enrollment ON progress(user_id, enrollment_id);
CREATE UNIQUE INDEX uq_progress_user_enrollment_item ON progress(user_id, enrollment_id, item_type, item_id);

-- Certificates (only enrollment_id reference now)
CREATE UNIQUE INDEX idx_certificates_number ON certificates(certificate_number);
CREATE UNIQUE INDEX idx_certificates_verification ON certificates(verification_code);
CREATE INDEX idx_certificates_enrollment ON certificates(enrollment_id);
-- NOTE: idx_certificates_student and idx_certificates_course REMOVED
-- Student/course derived from enrollment relationship

-- Notifications
CREATE INDEX idx_notifications_user_read ON notifications(user_id, is_read, created_at);
CREATE INDEX idx_notifications_type ON notifications(type);

-- Events
CREATE INDEX idx_events_type_status ON events(event_type, status, created_at);
CREATE INDEX idx_events_entity ON events(entity_type, entity_id);

-- Analytics Metrics
CREATE INDEX idx_analytics_name_recorded ON analytics_metrics(metric_name, recorded_at);

-- Workflow Executions
CREATE UNIQUE INDEX idx_workflows_workflow_id ON workflow_executions(workflow_id);
CREATE INDEX idx_workflows_type_status ON workflow_executions(workflow_type, status);
CREATE INDEX idx_workflows_entity ON workflow_executions(entity_type, entity_id);

-- AI Conversations
CREATE UNIQUE INDEX idx_ai_conversations_session ON ai_conversations(session_id);
CREATE INDEX idx_ai_conversations_user ON ai_conversations(user_id);
CREATE INDEX idx_ai_conversations_course ON ai_conversations(course_id);
CREATE INDEX idx_ai_conversations_user_course ON ai_conversations(user_id, course_id);

-- AI Messages
CREATE INDEX idx_ai_messages_conversation ON ai_messages(conversation_id);
CREATE INDEX idx_ai_messages_created ON ai_messages(created_at);

-- AI Generation History
CREATE INDEX idx_ai_gen_history_course_module ON ai_generation_history(course_id, module_id);
CREATE INDEX idx_ai_gen_history_type ON ai_generation_history(generation_type);
CREATE INDEX idx_ai_gen_history_triggered_by ON ai_generation_history(triggered_by);

-- RAG Index Status
CREATE UNIQUE INDEX idx_rag_status_course ON rag_index_status(course_id);
CREATE INDEX idx_rag_status_status ON rag_index_status(status);
```

### MongoDB Indexes

```javascript
// course_content collection
db.course_content.createIndex({ course_id: 1 }, { unique: true });
db.course_content.createIndex({ "modules.module_id": 1 });
db.course_content.createIndex({ updated_at: -1 });

// course_materials collection
db.course_materials.createIndex({ course_id: 1, module_id: 1, lesson_id: 1 });
db.course_materials.createIndex({ file_type: 1 });
db.course_materials.createIndex({ created_at: -1 });

// ai_generated_content collection
db.ai_generated_content.createIndex(
  { course_id: 1, module_id: 1 },
  { unique: true },
);
db.ai_generated_content.createIndex({ course_id: 1 });
db.ai_generated_content.createIndex({ updated_at: -1 });
```

### Qdrant Indexes

```python
# Qdrant creates indexes automatically on payload fields for filtering
# Key filterable fields:
# - course_id (exact match filtering)
# - module_id (exact match filtering)
# - lesson_id (exact match filtering)
# - content_type (categorical filtering)
```

---

## 5. Data Integrity Constraints

### Foreign Key Constraints

```sql
-- Courses
ALTER TABLE courses
ADD CONSTRAINT fk_courses_instructor
FOREIGN KEY (instructor_id) REFERENCES instructor_profiles(id) ON DELETE RESTRICT;

-- Enrollments
-- Note: student_id and course_id are logical FKs (cross-service reference)
-- No DB-level FK constraint since users table is in user-service DB
-- Referential integrity enforced at application level via API validation

-- Progress
ALTER TABLE progress
ADD CONSTRAINT fk_progress_enrollment
FOREIGN KEY (enrollment_id) REFERENCES enrollments(id) ON DELETE CASCADE;

-- Certificates (only enrollment_id FK now)
ALTER TABLE certificates
ADD CONSTRAINT fk_certificates_enrollment
FOREIGN KEY (enrollment_id) REFERENCES enrollments(id) ON DELETE CASCADE;

-- NOTE: fk_certificates_student and fk_certificates_course REMOVED
-- Student/course info derived from enrollment relationship

-- Notifications
ALTER TABLE notifications
ADD CONSTRAINT fk_notifications_user
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- Instructor Profiles
ALTER TABLE instructor_profiles
ADD CONSTRAINT fk_instructor_profiles_user
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

-- Events
ALTER TABLE events
ADD CONSTRAINT fk_events_user
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL;

-- Workflow Executions
ALTER TABLE workflow_executions
ADD CONSTRAINT fk_workflows_user
FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL;

-- AI Conversations
-- Note: user_id is a logical FK (cross-service reference to user-service)
-- No DB-level FK since users table is in a different database

-- AI Messages
ALTER TABLE ai_messages
ADD CONSTRAINT fk_ai_messages_conversation
FOREIGN KEY (conversation_id) REFERENCES ai_conversations(id) ON DELETE CASCADE;

-- AI Generation History
ALTER TABLE ai_generation_history
ADD CONSTRAINT fk_ai_gen_history_user
FOREIGN KEY (triggered_by) REFERENCES users(id) ON DELETE SET NULL;
```

### Check Constraints

```sql
-- Users role check
ALTER TABLE users
ADD CONSTRAINT chk_users_role
CHECK (role IN ('student', 'instructor', 'admin'));

-- Courses status check
ALTER TABLE courses
ADD CONSTRAINT chk_courses_status
CHECK (status IN ('draft', 'published', 'archived'));

-- Enrollments status check
ALTER TABLE enrollments
ADD CONSTRAINT chk_enrollments_status
CHECK (status IN ('active', 'completed', 'dropped', 'suspended'));

-- Progress completion percentage
ALTER TABLE progress
ADD CONSTRAINT chk_progress_percentage
CHECK (progress_percentage >= 0 AND progress_percentage <= 100);

-- Courses price non-negative
ALTER TABLE courses
ADD CONSTRAINT chk_courses_price
CHECK (price >= 0);

-- Instructor rating range
ALTER TABLE instructor_profiles
ADD CONSTRAINT chk_instructor_rating
CHECK (average_rating >= 0 AND average_rating <= 5);
```

---

## 6. Event Types Reference

| Event Type                  | Trigger          | Consumers                                 |
| --------------------------- | ---------------- | ----------------------------------------- |
| `user.registered`           | User signs up    | Analytics, Notification                   |
| `user.verified`             | Email verified   | Analytics                                 |
| `course.created`            | Course created   | Analytics                                 |
| `course.published`          | Course published | Analytics, Content Processing, AI Service |
| `course.updated`            | Course modified  | Content Processing                        |
| `course.archived`           | Course archived  | Notification, Analytics, AI Service       |
| `content.updated`           | Content changed  | AI Service                                |
| `enrollment.created`        | Student enrolls  | Analytics, Progress, Notification         |
| `enrollment.completed`      | Course completed | Analytics, Certificate, Notification      |
| `enrollment.dropped`        | Student drops    | Analytics                                 |
| `progress.updated`          | Lesson completed | Analytics                                 |
| `progress.module_completed` | Module done      | Analytics, Notification                   |
| `certificate.issued`        | Cert generated   | Notification                              |
| `certificate.revoked`       | Cert revoked     | Notification                              |
| `quiz.generated`            | AI quiz created  | Notification                              |
| `summary.generated`         | AI summary done  | Notification                              |
| `rag.indexed`               | RAG index done   | Notification, Analytics                   |
| `rag.failed`                | RAG index failed | Notification                              |

---

## 7. Metrics Tracked

| Metric Name               | Type    | Description             |
| ------------------------- | ------- | ----------------------- |
| `total_students`          | Gauge   | Active learners         |
| `total_instructors`       | Gauge   | Active instructors      |
| `total_courses_published` | Gauge   | Published courses       |
| `new_enrollments_daily`   | Counter | Daily enrollments       |
| `new_enrollments_weekly`  | Counter | Weekly enrollments      |
| `new_enrollments_monthly` | Counter | Monthly enrollments     |
| `course_completion_rate`  | Gauge   | % completing courses    |
| `avg_time_to_complete`    | Gauge   | Avg days to complete    |
| `popular_courses`         | List    | Top enrolled courses    |
| `avg_courses_per_student` | Gauge   | Courses per student     |
| `failed_workflows`        | Counter | Failed background tasks |
| `failed_events`           | Counter | Failed event processing |

---

## 8. Database Technology Summary

| Data Store       | Technology    | Purpose                                                                          | Access Pattern               |
| ---------------- | ------------- | -------------------------------------------------------------------------------- | ---------------------------- |
| Relational Data  | PostgreSQL 15 | Users, Courses, Enrollments, Progress, Certificates, Analytics, AI Conversations | ACID transactions, OLTP      |
| Flexible Content | MongoDB 7     | Course modules, lessons, materials, AI-generated content (quiz/summary)          | Document reads, nested data  |
| Vector Database  | Qdrant        | Course embeddings for RAG-based AI Tutor                                         | Similarity search, filtering |
| Session/Cache    | Redis 7       | Sessions, rate limits, progress cache                                            | Low-latency reads            |
| Event Stream     | Kafka         | Event sourcing, service communication                                            | Pub/Sub, replay              |

---

_Document Version: 2.0 | Last Updated: February 26, 2026_
