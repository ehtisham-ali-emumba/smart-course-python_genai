# SmartCourse - Entity Relationship Diagram (ERD)

**Version:** 1.2  
**Date:** February 11, 2026  
**Author:** SmartCourse Architecture Team  
**Scope:** Core Platform Entities (Excluding AI/LLM/Vector DB Components)

---

## Key Schema Decisions

| Decision                              | Rationale                                                      |
| ------------------------------------- | -------------------------------------------------------------- |
| **Merged Enrollments + Progress**     | 1:1 relationship - combining eliminates unnecessary join       |
| **Certificates → enrollment_id only** | Student/course derived from enrollment, reduces redundancy     |
| **Progress arrays in Enrollments**    | completed_modules, completed_lessons stored as Postgres arrays |

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
                                          │    username (UNIQUE) │
                                          │    hashed_password   │
                                          │    first_name        │
                                          │    last_name         │
                                          │    role              │
                                          │    is_active         │
                                          │    is_verified       │
                                          │    created_at        │
                                          │    updated_at        │
                                          └──────────┬───────────┘
                                                     │
                         ┌───────────────────────────┴───────────────────────────┐
                         │                                                       │
                         │ 1:1 (becomes instructor)                              │ 1:N (as student)
                         ▼                                                       ▼
              ┌──────────────────────┐                                ┌─────────────────────────────────┐
              │  INSTRUCTOR_PROFILE  │                                │  ENROLLMENTS (includes Progress)│
              ├──────────────────────┤                                ├─────────────────────────────────┤
              │ PK id                │                                │ PK id                           │
              │ FK user_id (UNIQUE)  │                                │ FK student_id                   │◄── Users
              │    specialization    │                                │ FK course_id                    │◄── Courses
              │    bio               │                                │    status                       │
              │    total_students    │                                │    enrolled_at                  │
              │    rating            │                                │    completed_at                 │
              │    verified_at       │                                │    completion_percentage        │
              └──────────┬───────────┘                                │    last_accessed_at             │
                         │                                            │── Progress Fields (merged) ──── │
                         │ 1:N (creates courses)                      │    completed_modules[]          │
                         ▼                                            │    completed_lessons[]          │
              ┌──────────────────────┐                                │    total_modules                │
              │       COURSES        │───────────────────────────────►│    total_lessons                │
              ├──────────────────────┤              1:N               │    quiz_scores (JSONB)          │
              │ PK id                │       (has many enrollments)   │    time_spent_minutes           │
              │    title             │                                │    current_module_id            │
              │    slug (UNIQUE)     │                                │    current_lesson_id            │
              │    description       │                                └────────────────┬────────────────┘
              │ FK instructor_id     │                                                 │
              │    category          │                                                 │ 1:1
              │    level             │                                                 │ (earns certificate)
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
```

---

## 2. Entity Definitions

### 2.1 Core Entities (PostgreSQL)

#### **USERS**

Central entity storing all platform users with role-based access.

| Column            | Type                                 | Constraints      | Description                  |
| ----------------- | ------------------------------------ | ---------------- | ---------------------------- |
| id                | SERIAL                               | PRIMARY KEY      | Auto-incrementing identifier |
| email             | VARCHAR(255)                         | UNIQUE, NOT NULL | User email address           |
| username          | VARCHAR(100)                         | UNIQUE, NOT NULL | Unique username              |
| hashed_password   | VARCHAR(255)                         | NOT NULL         | Bcrypt hashed password       |
| first_name        | VARCHAR(100)                         |                  | User's first name            |
| last_name         | VARCHAR(100)                         |                  | User's last name             |
| role              | ENUM('student','instructor','admin') | NOT NULL         | User role                    |
| is_active         | BOOLEAN                              | DEFAULT TRUE     | Account status               |
| is_verified       | BOOLEAN                              | DEFAULT FALSE    | Email verification           |
| profile_image_url | VARCHAR(500)                         |                  | Avatar URL                   |
| created_at        | TIMESTAMP                            | DEFAULT NOW()    | Creation timestamp           |
| updated_at        | TIMESTAMP                            | ON UPDATE NOW()  | Last update                  |
| last_login_at     | TIMESTAMP                            |                  | Last login time              |
| is_deleted        | BOOLEAN                              | DEFAULT FALSE    | Soft delete flag             |

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

#### **ENROLLMENTS (Merged with Progress)**

Tracks student enrollments in courses AND their progress (merged 1:1 relationship).

| Column                    | Type                                             | Constraints                | Description                              |
| ------------------------- | ------------------------------------------------ | -------------------------- | ---------------------------------------- |
| id                        | SERIAL                                           | PRIMARY KEY                | Auto-incrementing identifier             |
| student_id                | INTEGER                                          | FK → users(id), NOT NULL   | Enrolled student                         |
| course_id                 | INTEGER                                          | FK → courses(id), NOT NULL | Target course                            |
| status                    | ENUM('active','completed','dropped','suspended') | NOT NULL, INDEX            | Enrollment status                        |
| enrolled_at               | TIMESTAMP                                        | DEFAULT NOW()              | Enrollment time                          |
| started_at                | TIMESTAMP                                        |                            | First access                             |
| completed_at              | TIMESTAMP                                        |                            | Completion time                          |
| dropped_at                | TIMESTAMP                                        |                            | Drop time                                |
| last_accessed_at          | TIMESTAMP                                        |                            | Last course access                       |
| payment_status            | ENUM('pending','completed','refunded')           |                            | Payment state                            |
| payment_amount            | DECIMAL(10,2)                                    |                            | Amount paid                              |
| enrollment_source         | VARCHAR(100)                                     |                            | 'web','mobile','api'                     |
| **completed_modules**     | INTEGER[]                                        | DEFAULT '{}'               | Completed module IDs (from Progress)     |
| **completed_lessons**     | INTEGER[]                                        | DEFAULT '{}'               | Completed lesson IDs (from Progress)     |
| **total_modules**         | INTEGER                                          | NOT NULL, DEFAULT 0        | Total modules count (from Progress)      |
| **total_lessons**         | INTEGER                                          | NOT NULL, DEFAULT 0        | Total lessons count (from Progress)      |
| **completion_percentage** | DECIMAL(5,2)                                     | DEFAULT 0.00               | Progress 0-100% (from Progress)          |
| **completed_quizzes**     | INTEGER[]                                        | DEFAULT '{}'               | Completed quiz IDs (from Progress)       |
| **quiz_scores**           | JSONB                                            |                            | Scores: {quiz_id: score} (from Progress) |
| **time_spent_minutes**    | INTEGER                                          | DEFAULT 0                  | Total time spent (from Progress)         |
| **current_module_id**     | INTEGER                                          |                            | Current module (from Progress)           |
| **current_lesson_id**     | INTEGER                                          |                            | Current lesson (from Progress)           |
| created_at                | TIMESTAMP                                        | DEFAULT NOW()              | Record creation                          |
| updated_at                | TIMESTAMP                                        | ON UPDATE NOW()            | Last update                              |

**Unique Constraint:** `(student_id, course_id)`

**Note:** Fields marked in bold were previously in a separate PROGRESS table. They are now merged into ENROLLMENTS since there was a 1:1 relationship between the two tables.

---

#### **~~PROGRESS~~ (REMOVED - Merged into ENROLLMENTS)**

**This table has been removed.** All progress fields are now part of the ENROLLMENTS table since there was a 1:1 relationship.

See ENROLLMENTS table above for the merged schema.

**How Progress Works with MongoDB Modules/Lessons:**

The Enrollment table (PostgreSQL) stores **references** to MongoDB module/lesson IDs, not the actual content:

1. **ID Matching**: MongoDB's `COURSE_CONTENT` assigns each module a `module_id` (integer) and each lesson a `lesson_id` (integer). These are simple sequential IDs within each course.

2. **Array Storage**: Enrollment stores completed IDs in PostgreSQL arrays:
   - `completed_modules = [1, 2, 3]` → modules 1, 2, 3 are done
   - `completed_lessons = [1, 2, 3, 4, 5, 6]` → lessons 1-6 are done

3. **Calculation Flow**:

   ```
   Student completes lesson 5 in module 2
   ↓
   Course Service adds 5 to completed_lessons array in Enrollment
   ↓
   Service fetches course metadata from MongoDB (total_modules, total_lessons)
   ↓
   Calculates: completion_% = (completed_lessons.length / total_lessons) × 100
   ↓
   Updates enrollment.completion_percentage
   ```

4. **Current Position**: `current_module_id` and `current_lesson_id` track where the student left off for resume functionality.

5. **Why This Works**: MongoDB stores the content structure (what's IN module 2), PostgreSQL stores progress state (IS module 2 complete?). The IDs are the bridge between them.

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

## 3. Relationship Summary

| Relationship                           | Cardinality | Description                                    |
| -------------------------------------- | ----------- | ---------------------------------------------- |
| Users → Instructor_Profiles            | 1:1         | Instructors have one profile                   |
| Instructor_Profiles → Courses          | 1:N         | One instructor creates many courses            |
| Users → Enrollments                    | 1:N         | One student has many enrollments               |
| Courses → Enrollments                  | 1:N         | One course has many enrollments                |
| ~~Enrollments → Progress~~             | ~~1:1~~     | **REMOVED** - Progress merged into Enrollments |
| Enrollments → Certificates             | 1:1         | Each completion has one certificate            |
| Users → Notifications                  | 1:N         | One user receives many notifications           |
| Users → Events                         | 1:N         | One user triggers many events                  |
| Users → Workflow_Executions            | 1:N         | One user triggers many workflows               |
| Courses → Course_Content (MongoDB)     | 1:1         | Each course has content document               |
| Courses → Course_Materials (MongoDB)   | 1:N         | Each course has many materials                 |
| Enrollments ↔ Course_Content (MongoDB) | Reference   | Enrollments store MongoDB module/lesson IDs    |

---

## 4. Key Indexes

### PostgreSQL Indexes

```sql
-- Users
CREATE UNIQUE INDEX idx_users_email ON users(email);
CREATE UNIQUE INDEX idx_users_username ON users(username);
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

-- Progress table REMOVED - fields merged into Enrollments

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
ALTER TABLE enrollments
ADD CONSTRAINT fk_enrollments_student
FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE enrollments
ADD CONSTRAINT fk_enrollments_course
FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE;

-- Progress table REMOVED - no foreign keys needed

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
CHECK (completion_percentage >= 0 AND completion_percentage <= 100);

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

| Event Type                  | Trigger          | Consumers                            |
| --------------------------- | ---------------- | ------------------------------------ |
| `user.registered`           | User signs up    | Analytics, Notification              |
| `user.verified`             | Email verified   | Analytics                            |
| `course.created`            | Course created   | Analytics                            |
| `course.published`          | Course published | Analytics, Content Processing        |
| `course.updated`            | Course modified  | Content Processing                   |
| `course.archived`           | Course archived  | Notification, Analytics              |
| `enrollment.created`        | Student enrolls  | Analytics, Progress, Notification    |
| `enrollment.completed`      | Course completed | Analytics, Certificate, Notification |
| `enrollment.dropped`        | Student drops    | Analytics                            |
| `progress.updated`          | Lesson completed | Analytics                            |
| `progress.module_completed` | Module done      | Analytics, Notification              |
| `certificate.issued`        | Cert generated   | Notification                         |
| `certificate.revoked`       | Cert revoked     | Notification                         |

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

| Data Store       | Technology    | Purpose                                                        | Access Pattern              |
| ---------------- | ------------- | -------------------------------------------------------------- | --------------------------- |
| Relational Data  | PostgreSQL 15 | Users, Courses, Enrollments, Progress, Certificates, Analytics | ACID transactions, OLTP     |
| Flexible Content | MongoDB 7     | Course modules, lessons, materials                             | Document reads, nested data |
| Session/Cache    | Redis 7       | Sessions, rate limits, progress cache                          | Low-latency reads           |
| Event Stream     | Kafka         | Event sourcing, service communication                          | Pub/Sub, replay             |

---

_Document Version: 1.2 | Last Updated: February 11, 2026_
