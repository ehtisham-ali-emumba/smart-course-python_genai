# SmartCourse - Entity Relationship Diagram (ERD)

**Version:** 1.0  
**Date:** February 10, 2026  
**Author:** SmartCourse Architecture Team  
**Scope:** Core Platform Entities (Excluding AI/LLM/Vector DB Components)

---

## 1. ERD Visual Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                     SMARTCOURSE - ENTITY RELATIONSHIP DIAGRAM                                    │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

                                            ┌──────────────────────┐
                                            │   INSTRUCTOR_PROFILE │
                                            ├──────────────────────┤
                                            │ PK id                │
                                            │ FK user_id (UNIQUE)  │
                                            │    specialization    │
                                            │    bio               │
                                            │    total_students    │
                                            │    rating            │
                                            │    verified_at       │
                                            └──────────┬───────────┘
                                                       │
                                                       │ 1:1
                                                       │
┌──────────────────────┐                    ┌──────────▼───────────┐                    ┌──────────────────────┐
│     NOTIFICATION     │                    │        USERS         │                    │   REFRESH_TOKENS     │
├──────────────────────┤                    ├──────────────────────┤                    ├──────────────────────┤
│ PK id                │                    │ PK id                │                    │ PK id                │
│ FK user_id           │◄───────────────────┤    email (UNIQUE)    ├───────────────────►│ FK user_id           │
│    type              │        1:N         │    username (UNIQUE) │        1:N         │    token             │
│    title             │                    │    hashed_password   │                    │    expires_at        │
│    message           │                    │    first_name        │                    │    is_revoked        │
│    priority          │                    │    last_name         │                    │    created_at        │
│    is_read           │                    │    role              │                    └──────────────────────┘
│    created_at        │                    │    is_active         │
└──────────────────────┘                    │    is_verified       │
                                            │    created_at        │
                                            │    updated_at        │
                                            └──────────┬───────────┘
                                                       │
                        ┌──────────────────────────────┼──────────────────────────────┐
                        │                              │                              │
                        │ 1:N (as instructor)          │ 1:N (as student)             │
                        │                              │                              │
             ┌──────────▼───────────┐       ┌──────────▼───────────┐       ┌──────────▼───────────┐
             │       COURSES        │       │     ENROLLMENTS      │       │       EVENTS         │
             ├──────────────────────┤       ├──────────────────────┤       ├──────────────────────┤
             │ PK id                │       │ PK id                │       │ PK id                │
             │    title             │       │ FK student_id        │       │ FK user_id           │
             │    slug (UNIQUE)     │       │ FK course_id         │       │    event_type        │
             │    description       │  1:N  │    status            │       │    entity_type       │
             │ FK instructor_id     │──────►│    enrolled_at       │       │    entity_id         │
             │    category          │       │    completed_at      │       │    payload (JSONB)   │
             │    level             │       │    completion_%      │       │    status            │
             │    status            │       │    last_accessed_at  │       │    kafka_offset      │
             │    published_at      │       │    payment_status    │       │    created_at        │
             │    max_students      │       └──────────┬───────────┘       └──────────────────────┘
             │    price             │                  │
             │    created_at        │                  │
             └──────────┬───────────┘                  │
                        │                              │
                        │                   ┌──────────┼───────────┐
                        │                   │          │           │
                        │                   │ 1:1      │ 1:1       │ 1:N
                        │                   │          │           │
             ┌──────────▼───────────┐      ┌▼──────────▼──┐  ┌─────▼────────────────┐
             │    COURSE_MODULES    │      │   PROGRESS   │  │ ENROLLMENT_HISTORY   │
             │     (MongoDB)        │      ├──────────────┤  ├──────────────────────┤
             ├──────────────────────┤      │ PK id        │  │ PK id                │
             │ _id (ObjectId)       │      │FK enrollment │  │ FK enrollment_id     │
             │ course_id            │      │   completed  │  │    action            │
             │ modules: [           │      │   _modules[] │  │    previous_status   │
             │   { module_id,       │      │   completed  │  │    new_status        │
             │     title,           │      │   _lessons[] │  │    reason            │
             │     description,     │      │   total_%    │  │    performed_by      │
             │     order,           │      │   time_spent │  │    created_at        │
             │     lessons: [       │      │   updated_at │  └──────────────────────┘
             │       { lesson_id,   │      └──────────────┘
             │         title,       │                │
             │         type,        │                │ 1:1
             │         content,     │                │
             │         duration }   │      ┌─────────▼────────────┐
             │     ]                │      │    CERTIFICATES      │
             │   }                  │      ├──────────────────────┤
             │ ]                    │      │ PK id                │
             │ metadata             │      │ FK enrollment_id     │
             │ total_duration       │      │ FK student_id        │
             │ created_at           │      │ FK course_id         │
             └──────────────────────┘      │    certificate_number│
                                           │    issue_date        │
                                           │    verification_code │
                                           │    certificate_url   │
                                           │    grade             │
                                           │    is_revoked        │
                                           └──────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                              SUPPORTING ENTITIES                                                  │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────┐      ┌──────────────────────┐      ┌──────────────────────┐      ┌──────────────────────┐
│  ANALYTICS_METRICS   │      │ WORKFLOW_EXECUTIONS  │      │   COURSE_MATERIALS   │      │    ANNOUNCEMENTS     │
├──────────────────────┤      ├──────────────────────┤      │      (MongoDB)       │      ├──────────────────────┤
│ PK id                │      │ PK id                │      ├──────────────────────┤      │ PK id                │
│    metric_name       │      │    workflow_id       │      │ _id (ObjectId)       │      │ FK course_id         │
│    metric_value      │      │    workflow_type     │      │ course_id            │      │ FK instructor_id     │
│    metric_type       │      │    run_id            │      │ module_id            │      │    title             │
│    dimension (JSONB) │      │    entity_type       │      │ lesson_id            │      │    content           │
│    aggregation_period│      │    entity_id         │      │ file_name            │      │    priority          │
│    recorded_at       │      │ FK user_id           │      │ file_type            │      │    is_pinned         │
│    created_at        │      │    status            │      │ file_size            │      │    published_at      │
└──────────────────────┘      │    started_at        │      │ file_url             │      │    expires_at        │
                              │    completed_at      │      │ metadata             │      │    created_at        │
                              │    error_message     │      │ created_at           │      └──────────────────────┘
                              │    result (JSONB)    │      └──────────────────────┘
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

| Column              | Type                                       | Constraints              | Description                  |
| ------------------- | ------------------------------------------ | ------------------------ | ---------------------------- |
| id                  | SERIAL                                     | PRIMARY KEY              | Auto-incrementing identifier |
| title               | VARCHAR(255)                               | NOT NULL                 | Course title                 |
| slug                | VARCHAR(255)                               | UNIQUE, NOT NULL         | URL-friendly identifier      |
| description         | TEXT                                       |                          | Short description            |
| long_description    | TEXT                                       |                          | Detailed description         |
| instructor_id       | INTEGER                                    | FK → users(id), NOT NULL | Course instructor            |
| category            | VARCHAR(100)                               | INDEX                    | Course category              |
| level               | ENUM('beginner','intermediate','advanced') |                          | Difficulty level             |
| language            | VARCHAR(50)                                | DEFAULT 'en'             | Course language              |
| duration_hours      | DECIMAL(5,2)                               |                          | Estimated duration           |
| price               | DECIMAL(10,2)                              | DEFAULT 0.00             | Course price                 |
| currency            | VARCHAR(3)                                 | DEFAULT 'USD'            | Price currency               |
| thumbnail_url       | VARCHAR(500)                               |                          | Thumbnail image              |
| status              | ENUM('draft','published','archived')       | NOT NULL, INDEX          | Course status                |
| published_at        | TIMESTAMP                                  |                          | Publication time             |
| max_students        | INTEGER                                    |                          | Enrollment limit             |
| prerequisites       | TEXT                                       |                          | Required prerequisites       |
| learning_objectives | TEXT                                       |                          | What students will learn     |
| created_at          | TIMESTAMP                                  | DEFAULT NOW()            | Creation time                |
| updated_at          | TIMESTAMP                                  | ON UPDATE NOW()          | Last update                  |
| is_deleted          | BOOLEAN                                    | DEFAULT FALSE            | Soft delete flag             |

---

#### **ENROLLMENTS**

Tracks student enrollments in courses.

| Column                | Type                                             | Constraints                | Description                  |
| --------------------- | ------------------------------------------------ | -------------------------- | ---------------------------- |
| id                    | SERIAL                                           | PRIMARY KEY                | Auto-incrementing identifier |
| student_id            | INTEGER                                          | FK → users(id), NOT NULL   | Enrolled student             |
| course_id             | INTEGER                                          | FK → courses(id), NOT NULL | Target course                |
| status                | ENUM('active','completed','dropped','suspended') | NOT NULL, INDEX            | Enrollment status            |
| enrolled_at           | TIMESTAMP                                        | DEFAULT NOW()              | Enrollment time              |
| started_at            | TIMESTAMP                                        |                            | First access                 |
| completed_at          | TIMESTAMP                                        |                            | Completion time              |
| dropped_at            | TIMESTAMP                                        |                            | Drop time                    |
| completion_percentage | DECIMAL(5,2)                                     | DEFAULT 0.00               | Progress 0-100%              |
| last_accessed_at      | TIMESTAMP                                        |                            | Last course access           |
| payment_status        | ENUM('pending','completed','refunded')           |                            | Payment state                |
| payment_amount        | DECIMAL(10,2)                                    |                            | Amount paid                  |
| enrollment_source     | VARCHAR(100)                                     |                            | 'web','mobile','api'         |
| created_at            | TIMESTAMP                                        | DEFAULT NOW()              | Record creation              |
| updated_at            | TIMESTAMP                                        | ON UPDATE NOW()            | Last update                  |

**Unique Constraint:** `(student_id, course_id)`

---

#### **PROGRESS**

Detailed progress tracking per enrollment.

| Column             | Type      | Constraints                  | Description                  |
| ------------------ | --------- | ---------------------------- | ---------------------------- |
| id                 | SERIAL    | PRIMARY KEY                  | Auto-incrementing identifier |
| enrollment_id      | INTEGER   | FK → enrollments(id), UNIQUE | Related enrollment           |
| completed_modules  | INTEGER[] | DEFAULT '{}'                 | Completed module IDs         |
| completed_lessons  | INTEGER[] | DEFAULT '{}'                 | Completed lesson IDs         |
| total_modules      | INTEGER   | NOT NULL                     | Total modules count          |
| total_lessons      | INTEGER   | NOT NULL                     | Total lessons count          |
| completed_quizzes  | INTEGER[] | DEFAULT '{}'                 | Completed quiz IDs           |
| quiz_scores        | JSONB     |                              | Scores: {quiz_id: score}     |
| time_spent_minutes | INTEGER   | DEFAULT 0                    | Total time spent             |
| current_module_id  | INTEGER   |                              | Current module               |
| current_lesson_id  | INTEGER   |                              | Current lesson               |
| last_accessed_at   | TIMESTAMP | DEFAULT NOW()                | Last access                  |
| created_at         | TIMESTAMP | DEFAULT NOW()                | Creation time                |
| updated_at         | TIMESTAMP | ON UPDATE NOW()              | Last update                  |

---

#### **CERTIFICATES**

Generated certificates for course completion.

| Column             | Type         | Constraints                  | Description                  |
| ------------------ | ------------ | ---------------------------- | ---------------------------- |
| id                 | SERIAL       | PRIMARY KEY                  | Auto-incrementing identifier |
| enrollment_id      | INTEGER      | FK → enrollments(id), UNIQUE | Related enrollment           |
| student_id         | INTEGER      | FK → users(id), NOT NULL     | Certificate holder           |
| course_id          | INTEGER      | FK → courses(id), NOT NULL   | Completed course             |
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

| Relationship                         | Cardinality | Description                             |
| ------------------------------------ | ----------- | --------------------------------------- |
| Users → Courses                      | 1:N         | One instructor creates many courses     |
| Users → Enrollments                  | 1:N         | One student has many enrollments        |
| Courses → Enrollments                | 1:N         | One course has many enrollments         |
| Enrollments → Progress               | 1:1         | Each enrollment has one progress record |
| Enrollments → Certificates           | 1:1         | Each completion has one certificate     |
| Users → Notifications                | 1:N         | One user receives many notifications    |
| Users → Events                       | 1:N         | One user triggers many events           |
| Users → Instructor_Profiles          | 1:1         | Instructors have one profile            |
| Users → Workflow_Executions          | 1:N         | One user triggers many workflows        |
| Courses → Course_Content (MongoDB)   | 1:1         | Each course has content document        |
| Courses → Course_Materials (MongoDB) | 1:N         | Each course has many materials          |

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

-- Enrollments
CREATE UNIQUE INDEX idx_enrollments_student_course ON enrollments(student_id, course_id);
CREATE INDEX idx_enrollments_student ON enrollments(student_id);
CREATE INDEX idx_enrollments_course ON enrollments(course_id);
CREATE INDEX idx_enrollments_status ON enrollments(status);
CREATE INDEX idx_enrollments_enrolled_at ON enrollments(enrolled_at);

-- Progress
CREATE UNIQUE INDEX idx_progress_enrollment ON progress(enrollment_id);
CREATE INDEX idx_progress_last_accessed ON progress(last_accessed_at);

-- Certificates
CREATE UNIQUE INDEX idx_certificates_number ON certificates(certificate_number);
CREATE UNIQUE INDEX idx_certificates_verification ON certificates(verification_code);
CREATE INDEX idx_certificates_student ON certificates(student_id);
CREATE INDEX idx_certificates_course ON certificates(course_id);

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
FOREIGN KEY (instructor_id) REFERENCES users(id) ON DELETE RESTRICT;

-- Enrollments
ALTER TABLE enrollments
ADD CONSTRAINT fk_enrollments_student
FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE enrollments
ADD CONSTRAINT fk_enrollments_course
FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE;

-- Progress
ALTER TABLE progress
ADD CONSTRAINT fk_progress_enrollment
FOREIGN KEY (enrollment_id) REFERENCES enrollments(id) ON DELETE CASCADE;

-- Certificates
ALTER TABLE certificates
ADD CONSTRAINT fk_certificates_enrollment
FOREIGN KEY (enrollment_id) REFERENCES enrollments(id) ON DELETE CASCADE;

ALTER TABLE certificates
ADD CONSTRAINT fk_certificates_student
FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE certificates
ADD CONSTRAINT fk_certificates_course
FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE;

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

_Document Version: 1.0 | Last Updated: February 10, 2026_
