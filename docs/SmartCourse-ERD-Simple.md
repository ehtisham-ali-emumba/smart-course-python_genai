# SmartCourse - Entity Relationship Diagram

```mermaid
erDiagram
    %% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    %% PG: User Service
    %% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    users {
        int id PK
        varchar email
        varchar first_name
        varchar last_name
        varchar password_hash
        varchar role
        boolean is_active
        boolean is_verified
        varchar phone_number
        timestamp created_at
        timestamp updated_at
    }

    instructor_profiles {
        int id PK
        int user_id FK
        text bio
        varchar expertise
        varchar profile_picture_url
        varchar phone_number
        int total_students
        int total_courses
        float average_rating
        int is_verified_instructor
        timestamp verification_date
        timestamp created_at
        timestamp updated_at
    }

    %% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    %% PG: Course Service
    %% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    courses {
        int id PK
        varchar title
        varchar slug
        text description
        text long_description
        int instructor_id FK
        varchar category
        varchar level
        varchar language
        decimal duration_hours
        decimal price
        varchar currency
        varchar thumbnail_url
        varchar status
        timestamp published_at
        int max_students
        text prerequisites
        text learning_objectives
        boolean is_deleted
        timestamp created_at
        timestamp updated_at
    }

    enrollments {
        int id PK
        int student_id FK
        int course_id FK
        varchar status
        timestamp enrolled_at
        timestamp started_at
        timestamp completed_at
        timestamp dropped_at
        timestamp last_accessed_at
        varchar payment_status
        decimal payment_amount
        varchar enrollment_source
        int time_spent_minutes
        timestamp created_at
        timestamp updated_at
    }

    progress {
        int id PK
        int user_id FK
        int enrollment_id FK
        varchar item_type
        varchar item_id
        decimal progress_percentage
        timestamp completed_at
        timestamp created_at
        timestamp updated_at
    }

    certificates {
        int id PK
        int enrollment_id FK
        varchar certificate_number
        date issue_date
        varchar certificate_url
        varchar verification_code
        varchar grade
        decimal score_percentage
        int issued_by_id FK
        boolean is_revoked
        timestamp revoked_at
        text revoked_reason
        timestamp created_at
    }

    quiz_attempts {
        int id PK
        int user_id FK
        int enrollment_id FK
        varchar module_id
        int attempt_number
        varchar status
        decimal score
        boolean passed
        int time_spent_seconds
        timestamp started_at
        timestamp submitted_at
        timestamp graded_at
        timestamp created_at
        timestamp updated_at
    }

    user_answers {
        int id PK
        int quiz_attempt_id FK
        int user_id FK
        varchar question_id
        varchar question_type
        jsonb user_response
        boolean is_correct
        int time_spent_seconds
        timestamp answered_at
        timestamp created_at
        timestamp updated_at
    }

    %% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    %% MongoDB Collections
    %% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    course_content {
        string _id PK
        int course_id FK
        array modules
        object metadata
        timestamp created_at
        timestamp updated_at
    }

    module_quizzes {
        string _id PK
        int course_id FK
        string module_id
        boolean is_active
        array questions
        int version
        string model
        timestamp created_at
        timestamp updated_at
    }

    module_summaries {
        string _id PK
        int course_id FK
        string module_id
        boolean is_active
        text content
        int version
        string model
        boolean is_edited
        text original_content
        timestamp created_at
        timestamp updated_at
    }

    %% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    %% Qdrant Vector DB
    %% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    course_embeddings {
        uuid id PK
        vector embedding
        string course_id
        string module_id
        string lesson_id
        int chunk_index
        string text
        string lesson_title
        string module_title
    }

    %% ═══════════════════════════════════
    %% RELATIONSHIPS
    %% ═══════════════════════════════════

    %% User Service - DB FK
    users ||--o| instructor_profiles : "1-to-1 has profile"

    %% Cross-service logical FKs
    instructor_profiles ||--o{ courses : "1-to-N creates"
    users ||--o{ enrollments : "1-to-N enrolls"
    courses ||--o{ enrollments : "1-to-N has"

    %% Course Service - DB FKs
    enrollments ||--o{ progress : "1-to-N tracks"
    enrollments ||--o| certificates : "1-to-1 earns"
    enrollments ||--o{ quiz_attempts : "1-to-N attempts"
    quiz_attempts ||--o{ user_answers : "1-to-N answers"

    %% PG to MongoDB cross-store
    courses ||--|| course_content : "1-to-1 has content"
    courses ||--o{ module_quizzes : "1-to-N has quizzes"
    courses ||--o{ module_summaries : "1-to-N has summaries"

    %% MongoDB to Qdrant cross-store
    course_content ||--o{ course_embeddings : "1-to-N embedded"
```

---

## Relationship Types

| From | To | Cardinality | Type | FK Column |
|---|---|---|---|---|
| users | instructor_profiles | 1:1 | DB FK | instructor_profiles.user_id → users.id (CASCADE, UNIQUE) |
| instructor_profiles | courses | 1:N | logical | courses.instructor_id → instructor_profiles.id (cross-service) |
| users | enrollments | 1:N | logical | enrollments.student_id → users.id (cross-service) |
| courses | enrollments | 1:N | logical | enrollments.course_id → courses.id |
| enrollments | progress | 1:N | DB FK | progress.enrollment_id → enrollments.id (CASCADE) |
| enrollments | certificates | 1:1 | DB FK | certificates.enrollment_id → enrollments.id (CASCADE, UNIQUE) |
| enrollments | quiz_attempts | 1:N | DB FK | quiz_attempts.enrollment_id → enrollments.id (CASCADE) |
| quiz_attempts | user_answers | 1:N | DB FK | user_answers.quiz_attempt_id → quiz_attempts.id (CASCADE) |
| courses | course_content | 1:1 | cross-store | course_content.course_id → courses.id (unique index) |
| courses | module_quizzes | 1:N | cross-store | module_quizzes.course_id → courses.id |
| courses | module_summaries | 1:N | cross-store | module_summaries.course_id → courses.id |
| course_content | course_embeddings | 1:N | cross-store | Lesson text chunked and embedded into Qdrant |

---

## Database Distribution

| Store | Entities |
|---|---|
| **PostgreSQL (User Service)** | users, instructor_profiles |
| **PostgreSQL (Course Service)** | courses, enrollments, progress, certificates, quiz_attempts, user_answers |
| **MongoDB** | course_content, module_quizzes, module_summaries |
| **Qdrant** | course_embeddings |
