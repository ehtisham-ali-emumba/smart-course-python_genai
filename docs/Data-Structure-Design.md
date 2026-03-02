# Data Structure Design: MongoDB + PostgreSQL

## Overview

This document outlines the hybrid data architecture for SmartCourse, leveraging:

- **MongoDB**: Flexible, content-rich documents (course content, module quizzes, module summaries)
- **PostgreSQL**: Structured, relational data (enrollments, lesson progress, quiz attempts, user answers)

---

## Core Hierarchy

```
Course (PostgreSQL: courses)
  └── Module (MongoDB: course_content → modules[])
        ├── Lessons (MongoDB: course_content → modules[].lessons[])
        ├── Quiz (MongoDB: module_quizzes) — one quiz per module
        └── Summary (MongoDB: module_summaries) — one summary per module
```

**Key rule:** Quizzes and summaries are scoped to **modules**, not individual lessons. Each module can have at most one quiz and one summary. Both can be AI-generated or instructor-authored.

---

## MongoDB Collections

### 1. `course_content` Collection (Existing)

Stores the hierarchical course structure: modules and their lessons. No changes to this collection.

```json
{
  "_id": ObjectId("507f1f77bcf86cd799439011"),
  "course_id": 1,
  "modules": [
    {
      "module_id": "mod_6a8b9c",
      "title": "Introduction to Python",
      "description": "Learn Python basics",
      "order": 1,
      "is_published": true,
      "is_active": true,
      "lessons": [
        {
          "lesson_id": "les_3d4e5f",
          "title": "Variables and Data Types",
          "type": "video",
          "content": "https://cdn.example.com/videos/python-variables.mp4",
          "duration_minutes": 15,
          "order": 1,
          "is_preview": false,
          "is_active": true,
          "resources": [
            {
              "resource_id": "res_7h8i9j",
              "name": "Python Cheat Sheet",
              "url": "https://cdn.example.com/resources/cheatsheet.pdf",
              "type": "pdf",
              "is_active": true
            }
          ]
        },
        {
          "lesson_id": "les_9k1m2n",
          "title": "Control Flow",
          "type": "text",
          "content": "...",
          "duration_minutes": 10,
          "order": 2,
          "is_preview": false,
          "is_active": true,
          "resources": []
        }
      ]
    }
  ],
  "metadata": {
    "total_modules": 5,
    "total_lessons": 42,
    "total_duration_hours": 12.5,
    "tags": ["python", "programming", "beginner"]
  },
  "created_at": "ISODate(2026-01-15T10:00:00Z)",
  "updated_at": "ISODate(2026-02-20T14:30:00Z)"
}
```

**Indexes:**
- `course_id` (unique)
- `updated_at`

---

### 2. `module_quizzes` Collection (NEW)

Stores quiz content per module. One document per module. Can be AI-generated or manually authored by the instructor.

```json
{
  "_id": ObjectId("6b8c9d1e2f3a4567890abcde"),
  "course_id": 1,
  "module_id": "mod_6a8b9c",

  "title": "Introduction to Python — Module Quiz",
  "description": "Test your understanding of Python fundamentals covered in this module",

  "settings": {
    "passing_score": 70,
    "time_limit_minutes": 20,
    "max_attempts": 3,
    "shuffle_questions": true,
    "shuffle_options": true,
    "show_correct_answers_after": "completion"
  },

  "questions": [
    {
      "question_id": "q_1a2b3c",
      "order": 1,
      "question_text": "What is the correct way to declare a variable in Python?",
      "question_type": "multiple_choice",
      "options": [
        { "option_id": "opt_x1y2z3", "text": "x = 5",          "is_correct": true  },
        { "option_id": "opt_a4b5c6", "text": "int x = 5",      "is_correct": false },
        { "option_id": "opt_d7e8f9", "text": "var x = 5",      "is_correct": false },
        { "option_id": "opt_g0h1i2", "text": "declare x = 5",  "is_correct": false }
      ],
      "explanation": "Python uses dynamic typing — no type declaration needed.",
      "hint": "Python doesn't require type declarations"
    },
    {
      "question_id": "q_2d3e4f",
      "order": 2,
      "question_text": "Which of the following are valid Python data types? (Select all that apply)",
      "question_type": "multiple_select",
      "options": [
        { "option_id": "opt_j3k4l5", "text": "int",    "is_correct": true  },
        { "option_id": "opt_m6n7o8", "text": "float",  "is_correct": true  },
        { "option_id": "opt_p9q0r1", "text": "string", "is_correct": false },
        { "option_id": "opt_s2t3u4", "text": "str",    "is_correct": true  }
      ],
      "explanation": "Correct types: int, float, and str (not 'string').",
      "hint": "Python uses abbreviated names for some types"
    },
    {
      "question_id": "q_3g4h5i",
      "order": 3,
      "question_text": "What will be the output of: print(type(5.0))?",
      "question_type": "short_answer",
      "correct_answers": ["<class 'float'>", "float"],
      "case_sensitive": false,
      "explanation": "5.0 is a float, so type() returns <class 'float'>",
      "hint": "Consider the decimal point"
    },
    {
      "question_id": "q_4j5k6l",
      "order": 4,
      "question_text": "Is Python a statically typed language?",
      "question_type": "true_false",
      "options": [
        { "option_id": "opt_true",  "text": "True",  "is_correct": false },
        { "option_id": "opt_false", "text": "False", "is_correct": true  }
      ],
      "explanation": "Python is dynamically typed — types are resolved at runtime.",
      "hint": "Think about type declarations"
    }
  ],

  "authorship": {
    "source": "ai_generated",        // "ai_generated" | "manual" | "ai_edited"
    "generated_by_user_id": 123,     // instructor who triggered generation
    "ai_model": "gpt-4o-mini",       // null if manual
    "source_lesson_ids": ["les_3d4e5f", "les_9k1m2n"],  // lessons used as input for AI
    "version": 2,
    "last_edited_by": 123,
    "last_edited_at": "ISODate(2026-02-15T11:20:00Z)"
  },

  "is_published": true,
  "is_active": true,
  "created_at": "ISODate(2026-01-20T09:00:00Z)",
  "updated_at": "ISODate(2026-02-15T11:20:00Z)"
}
```

**Indexes:**
- `(course_id, module_id)` (unique compound — one quiz per module)
- `course_id`
- `created_at`

**Question Types:**

| Type              | `options` field  | `correct_answers` field | Notes                              |
|-------------------|------------------|-------------------------|------------------------------------|
| `multiple_choice` | Required         | —                       | Single correct option (`is_correct: true`) |
| `multiple_select` | Required         | —                       | Multiple options can be correct    |
| `true_false`      | Required (2)     | —                       | `opt_true` / `opt_false` option IDs |
| `short_answer`    | —                | Required (array)        | Case-insensitive match by default  |

**Scoring:** Score is calculated as `(correct_answers / total_questions) * 100`. No per-question weighting.

---

### 3. `module_summaries` Collection (NEW)

Stores a module-level summary. One document per module. AI-generated or manually written by the instructor.

```json
{
  "_id": ObjectId("507f1f77bcf86cd799439099"),
  "course_id": 1,
  "module_id": "mod_6a8b9c",

  "title": "Introduction to Python — Module Summary",

  "content": {
    "summary_text": "This module introduces the fundamental concepts of Python programming, covering variables, data types, and control flow.",
    "summary_html": "<h2>Key Concepts</h2><p>This module introduces...</p>",
    "key_points": [
      "Variables don't require type declarations in Python",
      "Python supports multiple numeric types: int, float, complex",
      "Strings can use single or double quotes",
      "Type conversion functions: int(), float(), str()"
    ],
    "learning_objectives": [
      "Declare and use variables",
      "Identify different Python data types",
      "Perform basic type conversions"
    ],
    "glossary": [
      {
        "term": "Variable",
        "definition": "A named storage location in memory that holds a value"
      },
      {
        "term": "Dynamic Typing",
        "definition": "Type resolution at runtime — no type declarations needed"
      }
    ],
    "difficulty_assessment": {
      "level": "beginner",
      "estimated_read_minutes": 5
    }
  },

  "authorship": {
    "source": "ai_generated",        // "ai_generated" | "manual" | "ai_edited"
    "generated_by_user_id": 123,
    "ai_model": "gpt-4o-mini",       // null if manual
    "source_lesson_ids": ["les_3d4e5f", "les_9k1m2n"],
    "version": 1,
    "last_edited_by": null,
    "last_edited_at": null
  },

  "is_published": true,
  "is_active": true,
  "created_at": "ISODate(2026-01-21T10:00:00Z)",
  "updated_at": "ISODate(2026-02-10T14:00:00Z)"
}
```

**Indexes:**
- `(course_id, module_id)` (unique compound — one summary per module)
- `course_id`
- `created_at`

---

## PostgreSQL Tables

### 1. `courses` Table (Existing — No Changes)

```sql
CREATE TABLE courses (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    slug VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    long_description TEXT,
    instructor_id INTEGER NOT NULL,
    category VARCHAR(100),
    level VARCHAR(50),
    language VARCHAR(50) DEFAULT 'en' NOT NULL,
    duration_hours NUMERIC(5,2),
    price NUMERIC(10,2) DEFAULT 0.00 NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD' NOT NULL,
    thumbnail_url VARCHAR(500),
    status VARCHAR(50) DEFAULT 'draft' NOT NULL,
    published_at TIMESTAMP,
    max_students INTEGER,
    prerequisites TEXT,
    learning_objectives TEXT,
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_courses_slug ON courses(slug);
CREATE INDEX idx_courses_instructor_id ON courses(instructor_id);
CREATE INDEX idx_courses_status ON courses(status);
```

---

### 2. `enrollments` Table (Existing — No Changes)

```sql
CREATE TABLE enrollments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    status VARCHAR(50) DEFAULT 'active' NOT NULL,   -- active, completed, dropped
    progress_percentage NUMERIC(5,2) DEFAULT 0 NOT NULL,
    enrolled_at TIMESTAMP DEFAULT NOW() NOT NULL,
    completed_at TIMESTAMP,
    last_accessed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL,
    UNIQUE(user_id, course_id)
);

CREATE INDEX idx_enrollments_user_id ON enrollments(user_id);
CREATE INDEX idx_enrollments_course_id ON enrollments(course_id);
CREATE INDEX idx_enrollments_status ON enrollments(status);
```

---

### 3. `progress` Table (Existing — Scoped to Completion Tracking Only)

Tracks **completion state** of each content item per enrollment. This table is intentionally lightweight — it only records whether an item was completed and the percentage watched/read. Detailed quiz performance data lives in `quiz_attempts` and `user_answers`.

```sql
CREATE TABLE progress (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    enrollment_id INTEGER NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
    item_type VARCHAR(30) NOT NULL,   -- 'lesson', 'module_quiz', 'module_summary'
    item_id VARCHAR(50) NOT NULL,     -- lesson_id (MongoDB), module_id (for quiz/summary)
    progress_percentage NUMERIC(5,2) DEFAULT 0 NOT NULL,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL,
    CONSTRAINT uq_progress_user_enrollment_item UNIQUE(user_id, enrollment_id, item_type, item_id)
);

CREATE INDEX idx_progress_user_enrollment ON progress(user_id, enrollment_id);
CREATE INDEX idx_progress_item ON progress(item_type, item_id);
```

**item_type values:**

| `item_type`      | `item_id` references              | Completed when                          |
|------------------|-----------------------------------|-----------------------------------------|
| `lesson`         | MongoDB `lesson_id`               | Student finishes watching/reading       |
| `module_quiz`    | MongoDB `module_id`               | Student submits quiz attempt (pass/fail)|
| `module_summary` | MongoDB `module_id`               | Student marks summary as read           |

**Note:** `module_quiz` progress is marked complete once the student submits any attempt (regardless of pass/fail). Pass/fail status lives in `quiz_attempts`.

---

### 4. `quiz_attempts` Table (NEW)

One row per quiz attempt. Tracks outcome, score, and timing. References the module-level quiz in MongoDB.

```sql
CREATE TABLE quiz_attempts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    enrollment_id INTEGER NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
    module_id VARCHAR(50) NOT NULL,     -- References MongoDB module_id
    attempt_number INTEGER NOT NULL,
    status VARCHAR(20) DEFAULT 'in_progress' NOT NULL,  -- in_progress, submitted, graded
    score NUMERIC(5,2),                 -- Percentage 0–100 (correct / total questions * 100)
    passed BOOLEAN,
    time_spent_seconds INTEGER,
    started_at TIMESTAMP DEFAULT NOW() NOT NULL,
    submitted_at TIMESTAMP,
    graded_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL,
    CONSTRAINT uq_quiz_attempts UNIQUE(user_id, enrollment_id, module_id, attempt_number)
);

CREATE INDEX idx_quiz_attempts_user_id ON quiz_attempts(user_id);
CREATE INDEX idx_quiz_attempts_enrollment_id ON quiz_attempts(enrollment_id);
CREATE INDEX idx_quiz_attempts_module_id ON quiz_attempts(module_id);
CREATE INDEX idx_quiz_attempts_status ON quiz_attempts(status);
```

**Example Data:**

```
id | user_id | module_id  | attempt_number | status | score | passed
---|---------|------------|----------------|--------|-------|-------
1  | 789     | mod_6a8b9c | 1              | graded | 50.00 | false
2  | 789     | mod_6a8b9c | 2              | graded | 75.00 | true
3  | 890     | mod_6a8b9c | 1              | graded | 75.00 | true
```

---

### 5. `user_answers` Table (NEW)

Stores each individual answer within a quiz attempt. Keyed to a `quiz_attempt_id`.

```sql
CREATE TABLE user_answers (
    id SERIAL PRIMARY KEY,
    quiz_attempt_id INTEGER NOT NULL REFERENCES quiz_attempts(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    question_id VARCHAR(50) NOT NULL,   -- References MongoDB question_id
    question_type VARCHAR(20) NOT NULL, -- multiple_choice, multiple_select, true_false, short_answer
    user_response JSONB NOT NULL,       -- Flexible per question type (see below)
    is_correct BOOLEAN,
    time_spent_seconds INTEGER,
    answered_at TIMESTAMP DEFAULT NOW() NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_user_answers_attempt_id ON user_answers(quiz_attempt_id);
CREATE INDEX idx_user_answers_user_id ON user_answers(user_id);
CREATE INDEX idx_user_answers_question_id ON user_answers(question_id);
CREATE INDEX idx_user_answers_response ON user_answers USING gin(user_response);
```

**`user_response` JSONB structure by question type:**

```json
// multiple_choice
{ "selected_option": "opt_x1y2z3" }

// multiple_select
{ "selected_options": ["opt_j3k4l5", "opt_m6n7o8"] }

// true_false
{ "selected_option": "opt_false" }

// short_answer
{ "text": "float" }
```

---

## Data Relationships

### Content Hierarchy

```
PostgreSQL: courses (id=1)
    │
    └─► MongoDB: course_content (course_id=1)
              │
              └─► modules[module_id="mod_6a8b9c"]
                        │
                        ├─► lessons[] — video, text, pdf, etc.
                        │
                        ├─► MongoDB: module_quizzes (course_id=1, module_id="mod_6a8b9c")
                        │
                        └─► MongoDB: module_summaries (course_id=1, module_id="mod_6a8b9c")
```

### Student Progress Flow

```
PostgreSQL: enrollments (user_id=789, course_id=1)
    │
    ├─► PostgreSQL: progress
    │       item_type='lesson',        item_id='les_3d4e5f'  → lesson completion
    │       item_type='module_quiz',   item_id='mod_6a8b9c'  → quiz completion flag
    │       item_type='module_summary',item_id='mod_6a8b9c'  → summary read flag
    │
    └─► PostgreSQL: quiz_attempts (user_id=789, module_id="mod_6a8b9c")
              │
              └─► PostgreSQL: user_answers (per question, per attempt)
```

---

## Key Design Decisions

### Why Quiz and Summary per Module (not per Lesson)?

- A module represents a cohesive learning unit; testing or summarising at that level is more meaningful pedagogically.
- Instructors review multiple lessons together before generating content — a module-level scope matches that workflow.
- Simpler data model: one quiz document and one summary document per module instead of tracking multiple per-lesson items.

### Why MongoDB for Quiz and Summary Content?

- Quiz questions have varying structure (multiple choice vs. short answer vs. true/false) — a flexible document model is cleaner than wide nullable columns.
- Summary content includes rich fields (HTML, glossary, key points) that are easier to evolve without schema migrations.
- Content lives alongside `course_content`, keeping all instructional material in one store.

### Why PostgreSQL for Quiz Attempts and Answers?

- ACID compliance is critical: a submitted attempt with its answers must be written atomically.
- Relational integrity: `user_answers` always belongs to a valid `quiz_attempts` row.
- Analytics: aggregating scores, pass rates, and per-question difficulty is straightforward with SQL.

### No Per-Question Points Weighting

Score is a simple percentage: `(correct_answers / total_questions) * 100`. All questions count equally. This keeps the grading logic simple and the schema lean.

---

## Usage Examples

### Instructor Creates a Quiz

```python
# AI-generated path: fetch lessons, call LLM, upsert into MongoDB
quiz_doc = {
    "course_id": 1, "module_id": "mod_6a8b9c",
    "title": "...", "description": "...",
    "settings": {"passing_score": 70, "max_attempts": 3, ...},
    "questions": [...],  # built from LLM output or instructor input
    "authorship": {
        "source": "ai_generated", "generated_by_user_id": 123,
        "ai_model": "gpt-4o-mini", "source_lesson_ids": [...], "version": 1
    },
    "is_published": False, "is_active": True
}
await mongodb.module_quizzes.replace_one(
    {"course_id": 1, "module_id": "mod_6a8b9c"},
    quiz_doc, upsert=True
)
```

### Student Takes a Module Quiz

```python
# 1. Fetch quiz from MongoDB
quiz = await mongodb.module_quizzes.find_one({
    "course_id": 1, "module_id": "mod_6a8b9c", "is_active": True
})

# 2. Enforce max_attempts
attempt_count = await db.scalar(
    select(func.count()).where(
        QuizAttempt.user_id == 789,
        QuizAttempt.enrollment_id == 1,
        QuizAttempt.module_id == "mod_6a8b9c"
    )
)
if attempt_count >= quiz["settings"]["max_attempts"]:
    raise MaxAttemptsExceededError()

# 3. Create attempt row
attempt = QuizAttempt(
    user_id=789, enrollment_id=1,
    module_id="mod_6a8b9c",
    attempt_number=attempt_count + 1,
)
db.add(attempt)
await db.flush()  # get attempt.id

# 4. Save each answer
correct_count = 0
total_questions = len(user_submitted_answers)
for q in user_submitted_answers:
    correct = grade_answer(q, quiz)
    if correct:
        correct_count += 1
    answer = UserAnswer(
        quiz_attempt_id=attempt.id, user_id=789,
        question_id=q["question_id"], question_type=q["type"],
        user_response=q["response"],
        is_correct=correct,
    )
    db.add(answer)

# 5. Finalise attempt
attempt.status = "graded"
attempt.score = (correct_count / total_questions) * 100
attempt.passed = attempt.score >= quiz["settings"]["passing_score"]
attempt.submitted_at = datetime.utcnow()
attempt.graded_at = datetime.utcnow()
await db.commit()

# 6. Mark quiz as complete in progress table (regardless of pass/fail)
await upsert_progress(
    user_id=789, enrollment_id=1,
    item_type="module_quiz", item_id="mod_6a8b9c",
    progress_percentage=100.0,
    completed_at=datetime.utcnow()
)
```

### Student Reads a Module Summary

```python
# 1. Fetch summary from MongoDB
summary = await mongodb.module_summaries.find_one({
    "course_id": 1, "module_id": "mod_6a8b9c",
    "is_active": True, "is_published": True
})

# 2. Mark as read in progress table
await upsert_progress(
    user_id=789, enrollment_id=1,
    item_type="module_summary", item_id="mod_6a8b9c",
    progress_percentage=100.0,
    completed_at=datetime.utcnow()
)
```

### Analytics: Quiz Performance per Module

```sql
-- Pass rates per module quiz
SELECT
    qa.module_id,
    COUNT(*) AS total_attempts,
    COUNT(DISTINCT qa.user_id) AS unique_students,
    ROUND(AVG(qa.score), 2) AS avg_score,
    COUNT(CASE WHEN qa.passed THEN 1 END)::float / COUNT(*) * 100 AS pass_rate
FROM quiz_attempts qa
JOIN enrollments e ON qa.enrollment_id = e.id
WHERE e.course_id = 1 AND qa.status = 'graded'
GROUP BY qa.module_id
ORDER BY pass_rate ASC;

-- Per-question difficulty (which questions students got wrong most)
SELECT
    ua.question_id,
    COUNT(*) AS total_answers,
    COUNT(CASE WHEN ua.is_correct THEN 1 END) AS correct_count,
    ROUND(COUNT(CASE WHEN ua.is_correct THEN 1 END)::numeric / COUNT(*) * 100, 2) AS correct_rate
FROM user_answers ua
JOIN quiz_attempts qa ON ua.quiz_attempt_id = qa.id
JOIN enrollments e ON qa.enrollment_id = e.id
WHERE e.course_id = 1 AND qa.module_id = 'mod_6a8b9c'
GROUP BY ua.question_id
ORDER BY correct_rate ASC;
```

---

## Migration Steps

### MongoDB — Create Collections and Indexes

```python
# module_quizzes
await mongodb.module_quizzes.create_index(
    [("course_id", 1), ("module_id", 1)], unique=True
)
await mongodb.module_quizzes.create_index("course_id")

# module_summaries
await mongodb.module_summaries.create_index(
    [("course_id", 1), ("module_id", 1)], unique=True
)
await mongodb.module_summaries.create_index("course_id")
```

### PostgreSQL — Alembic Migration

```bash
alembic revision -m "add_quiz_attempts_and_user_answers"
alembic upgrade head
```

---

## Summary Table: What Lives Where

| Data                               | Store      | Collection / Table |
|------------------------------------|------------|--------------------|
| Course metadata                    | PostgreSQL | `courses`          |
| Module + Lesson structure          | MongoDB    | `course_content`   |
| Module quiz content                | MongoDB    | `module_quizzes`   |
| Module summary content             | MongoDB    | `module_summaries` |
| Enrollment                         | PostgreSQL | `enrollments`      |
| Lesson / quiz / summary completion | PostgreSQL | `progress`         |
| Quiz attempt outcome + score       | PostgreSQL | `quiz_attempts`    |
| Per-question answers               | PostgreSQL | `user_answers`     |

---

## API Endpoints: Quiz & Summary CRUD (Course Service)

These endpoints live in the `course-service` under the existing `/courses` prefix. Auth is resolved via gateway-injected headers (`X-User-ID`, `X-User-Role`). Instructor-only routes use `require_instructor`; read routes use `get_current_user_id`.

---

### Pydantic Schemas

#### Quiz Schemas

```python
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal, Optional
from datetime import datetime

# ── Options ──────────────────────────────────────────────────────────────────

class QuizOptionSchema(BaseModel):
    option_id: str
    text: str
    is_correct: bool

# ── Questions ─────────────────────────────────────────────────────────────────

class QuizQuestionCreate(BaseModel):
    order: int = Field(..., ge=1)
    question_text: str = Field(..., min_length=1)
    question_type: Literal["multiple_choice", "multiple_select", "true_false", "short_answer"]
    options: Optional[list[QuizOptionSchema]] = None          # required for all except short_answer
    correct_answers: Optional[list[str]] = None               # required for short_answer
    case_sensitive: Optional[bool] = False                    # short_answer only
    explanation: Optional[str] = None
    hint: Optional[str] = None

class QuizQuestionResponse(QuizQuestionCreate):
    question_id: str

# ── Settings ──────────────────────────────────────────────────────────────────

class QuizSettingsSchema(BaseModel):
    passing_score: int = Field(70, ge=0, le=100)
    time_limit_minutes: Optional[int] = Field(None, ge=1)
    max_attempts: int = Field(3, ge=1)
    shuffle_questions: bool = True
    shuffle_options: bool = True
    show_correct_answers_after: Literal["completion", "passing", "never"] = "completion"

# ── Authorship ────────────────────────────────────────────────────────────────

class AuthorshipResponse(BaseModel):
    source: Literal["ai_generated", "manual", "ai_edited"]
    generated_by_user_id: Optional[int]
    ai_model: Optional[str]
    source_lesson_ids: list[str]
    version: int
    last_edited_by: Optional[int]
    last_edited_at: Optional[datetime]

# ── Quiz Request/Response ─────────────────────────────────────────────────────

class QuizCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = None
    settings: QuizSettingsSchema = Field(default_factory=QuizSettingsSchema)
    questions: list[QuizQuestionCreate] = Field(..., min_length=1)
    is_published: bool = False

class QuizUpdate(BaseModel):
    """Full replacement — all fields required (PUT semantics)."""
    title: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = None
    settings: QuizSettingsSchema
    questions: list[QuizQuestionCreate] = Field(..., min_length=1)
    is_published: bool

class QuizPatch(BaseModel):
    """Partial update — all fields optional (PATCH semantics)."""
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    description: Optional[str] = None
    settings: Optional[QuizSettingsSchema] = None
    questions: Optional[list[QuizQuestionCreate]] = None
    is_published: Optional[bool] = None

class QuizPublishUpdate(BaseModel):
    is_published: bool

class QuizGenerateRequest(BaseModel):
    """Trigger AI generation from selected lessons in the module."""
    source_lesson_ids: list[str] = Field(..., min_length=1)
    num_questions: int = Field(5, ge=1, le=20)
    passing_score: int = Field(70, ge=0, le=100)
    max_attempts: int = Field(3, ge=1)
    time_limit_minutes: Optional[int] = Field(None, ge=1)

class QuizResponse(BaseModel):
    id: str                          # MongoDB _id as hex string
    course_id: int
    module_id: str
    title: str
    description: Optional[str]
    settings: QuizSettingsSchema
    questions: list[QuizQuestionResponse]
    authorship: AuthorshipResponse
    is_published: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
```

---

#### Summary Schemas

```python
# ── Content ───────────────────────────────────────────────────────────────────

class GlossaryTermSchema(BaseModel):
    term: str
    definition: str

class DifficultyAssessmentSchema(BaseModel):
    level: Literal["beginner", "intermediate", "advanced"]
    estimated_read_minutes: int = Field(..., ge=1)

class SummaryContentCreate(BaseModel):
    summary_text: str = Field(..., min_length=1)
    summary_html: Optional[str] = None
    key_points: list[str] = Field(default_factory=list)
    learning_objectives: list[str] = Field(default_factory=list)
    glossary: list[GlossaryTermSchema] = Field(default_factory=list)
    difficulty_assessment: Optional[DifficultyAssessmentSchema] = None

# ── Summary Request/Response ──────────────────────────────────────────────────

class SummaryCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    content: SummaryContentCreate
    is_published: bool = False

class SummaryUpdate(BaseModel):
    """Full replacement — all fields required (PUT semantics)."""
    title: str = Field(..., min_length=1, max_length=300)
    content: SummaryContentCreate
    is_published: bool

class SummaryPatch(BaseModel):
    """Partial update — all fields optional (PATCH semantics)."""
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    content: Optional[SummaryContentCreate] = None
    is_published: Optional[bool] = None

class SummaryPublishUpdate(BaseModel):
    is_published: bool

class SummaryGenerateRequest(BaseModel):
    """Trigger AI generation from selected lessons in the module."""
    source_lesson_ids: list[str] = Field(..., min_length=1)
    include_glossary: bool = True
    include_key_points: bool = True
    include_learning_objectives: bool = True

class SummaryResponse(BaseModel):
    id: str                          # MongoDB _id as hex string
    course_id: int
    module_id: str
    title: str
    content: SummaryContentCreate
    authorship: AuthorshipResponse
    is_published: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
```

---

### Quiz Endpoints

**Router prefix:** `courses/{course_id}/modules/{module_id}/quiz`
**Tag:** `Module Quiz`
**File:** `src/api/module_quiz.py`

All quiz content lives in MongoDB (`module_quizzes`). The `course_id` is validated against PostgreSQL `courses` table to confirm the course exists and the instructor owns it.

| Method   | Path                                                              | Auth       | Description                                        | Status   |
|----------|-------------------------------------------------------------------|------------|----------------------------------------------------|----------|
| `GET`    | `/courses/{course_id}/modules/{module_id}/quiz`                   | Any user   | Get the published quiz for a module                | 200 / 404|
| `POST`   | `/courses/{course_id}/modules/{module_id}/quiz`                   | Instructor | Create a quiz manually (fails if one exists)       | 201 / 409|
| `PUT`    | `/courses/{course_id}/modules/{module_id}/quiz`                   | Instructor | Replace the entire quiz document                   | 200 / 404|
| `PATCH`  | `/courses/{course_id}/modules/{module_id}/quiz`                   | Instructor | Partial update (title, settings, questions, etc.)  | 200 / 404|
| `DELETE` | `/courses/{course_id}/modules/{module_id}/quiz`                   | Instructor | Soft-delete quiz (`is_active = false`)             | 204 / 404|
| `PATCH`  | `/courses/{course_id}/modules/{module_id}/quiz/publish`           | Instructor | Toggle `is_published`                              | 200 / 404|
| `POST`   | `/courses/{course_id}/modules/{module_id}/quiz/generate`          | Instructor | AI-generate quiz from lesson content               | 201 / 409|

#### Endpoint Details

```python
router = APIRouter(prefix="/courses/{course_id}/modules/{module_id}/quiz", tags=["Module Quiz"])

@router.get("", response_model=QuizResponse)
async def get_module_quiz(
    course_id: int,
    module_id: str,
    user_id: int = Depends(get_current_user_id),
):
    """
    Returns the active, published quiz for a module.
    Students see it before attempting; instructors see it for preview.
    Raises 404 if no quiz exists or it is inactive.
    """

@router.post("", response_model=QuizResponse, status_code=201)
async def create_module_quiz(
    course_id: int,
    module_id: str,
    payload: QuizCreate,
    instructor_id: int = Depends(require_instructor),
):
    """
    Manually create a quiz for a module.
    Raises 404 if course/module not found.
    Raises 403 if instructor does not own the course.
    Raises 409 if a quiz already exists for this module (use PUT to replace).
    """

@router.put("", response_model=QuizResponse)
async def replace_module_quiz(
    course_id: int,
    module_id: str,
    payload: QuizUpdate,
    instructor_id: int = Depends(require_instructor),
):
    """
    Full replacement of the quiz document (upserts if none exists).
    Increments authorship.version. Sets source to 'manual'.
    Raises 403 if instructor does not own the course.
    """

@router.patch("", response_model=QuizResponse)
async def patch_module_quiz(
    course_id: int,
    module_id: str,
    payload: QuizPatch,
    instructor_id: int = Depends(require_instructor),
):
    """
    Partial update — only provided fields are merged.
    Raises 404 if quiz not found. Raises 403 if not owner.
    """

@router.delete("", status_code=204)
async def delete_module_quiz(
    course_id: int,
    module_id: str,
    instructor_id: int = Depends(require_instructor),
):
    """
    Soft-delete: sets is_active = false on the quiz document.
    Raises 404 if quiz not found. Raises 403 if not owner.
    """

@router.patch("/publish", response_model=QuizResponse)
async def publish_module_quiz(
    course_id: int,
    module_id: str,
    payload: QuizPublishUpdate,
    instructor_id: int = Depends(require_instructor),
):
    """
    Toggle is_published. Unpublishing hides the quiz from students
    but preserves existing quiz_attempts records.
    Raises 404 if quiz not found. Raises 403 if not owner.
    """

@router.post("/generate", response_model=QuizResponse, status_code=201)
async def generate_module_quiz(
    course_id: int,
    module_id: str,
    payload: QuizGenerateRequest,
    instructor_id: int = Depends(require_instructor),
):
    """
    AI-generate a quiz from the specified lessons (source_lesson_ids must
    belong to this module). Calls the AI service internally. Upserts the
    result into MongoDB with authorship.source = 'ai_generated'.
    Raises 404 if course/module/lessons not found.
    Raises 403 if not owner.
    """
```

#### Error Responses

| Code | Trigger                                                              |
|------|----------------------------------------------------------------------|
| 401  | Missing `X-User-ID` header                                           |
| 403  | Instructor does not own the course                                   |
| 404  | Course, module, or quiz not found / inactive                         |
| 409  | `POST /quiz` called when quiz already exists for this module         |
| 422  | Pydantic validation failure (e.g., `short_answer` without `correct_answers`) |

---

### Summary Endpoints

**Router prefix:** `courses/{course_id}/modules/{module_id}/summary`
**Tag:** `Module Summary`
**File:** `src/api/module_summary.py`

All summary content lives in MongoDB (`module_summaries`). Same ownership and course-validation rules as quiz endpoints.

| Method   | Path                                                                 | Auth       | Description                                         | Status    |
|----------|----------------------------------------------------------------------|------------|-----------------------------------------------------|-----------|
| `GET`    | `/courses/{course_id}/modules/{module_id}/summary`                   | Any user   | Get the published summary for a module              | 200 / 404 |
| `POST`   | `/courses/{course_id}/modules/{module_id}/summary`                   | Instructor | Create a summary manually (fails if one exists)     | 201 / 409 |
| `PUT`    | `/courses/{course_id}/modules/{module_id}/summary`                   | Instructor | Replace the entire summary document                 | 200 / 404 |
| `PATCH`  | `/courses/{course_id}/modules/{module_id}/summary`                   | Instructor | Partial update (title, content fields)              | 200 / 404 |
| `DELETE` | `/courses/{course_id}/modules/{module_id}/summary`                   | Instructor | Soft-delete summary (`is_active = false`)           | 204 / 404 |
| `PATCH`  | `/courses/{course_id}/modules/{module_id}/summary/publish`           | Instructor | Toggle `is_published`                               | 200 / 404 |
| `POST`   | `/courses/{course_id}/modules/{module_id}/summary/generate`          | Instructor | AI-generate summary from lesson content             | 201 / 409 |

#### Endpoint Details

```python
router = APIRouter(prefix="/courses/{course_id}/modules/{module_id}/summary", tags=["Module Summary"])

@router.get("", response_model=SummaryResponse)
async def get_module_summary(
    course_id: int,
    module_id: str,
    user_id: int = Depends(get_current_user_id),
):
    """
    Returns the active, published summary for a module.
    Raises 404 if no summary exists or it is inactive/unpublished.
    """

@router.post("", response_model=SummaryResponse, status_code=201)
async def create_module_summary(
    course_id: int,
    module_id: str,
    payload: SummaryCreate,
    instructor_id: int = Depends(require_instructor),
):
    """
    Manually create a summary for a module.
    Raises 404 if course/module not found.
    Raises 403 if instructor does not own the course.
    Raises 409 if a summary already exists for this module (use PUT to replace).
    """

@router.put("", response_model=SummaryResponse)
async def replace_module_summary(
    course_id: int,
    module_id: str,
    payload: SummaryUpdate,
    instructor_id: int = Depends(require_instructor),
):
    """
    Full replacement of the summary document (upserts if none exists).
    Increments authorship.version. Sets source to 'manual' or 'ai_edited'
    if the previous version was AI-generated.
    Raises 403 if instructor does not own the course.
    """

@router.patch("", response_model=SummaryResponse)
async def patch_module_summary(
    course_id: int,
    module_id: str,
    payload: SummaryPatch,
    instructor_id: int = Depends(require_instructor),
):
    """
    Partial update — only provided fields are merged into the existing document.
    Raises 404 if summary not found. Raises 403 if not owner.
    """

@router.delete("", status_code=204)
async def delete_module_summary(
    course_id: int,
    module_id: str,
    instructor_id: int = Depends(require_instructor),
):
    """
    Soft-delete: sets is_active = false on the summary document.
    Raises 404 if summary not found. Raises 403 if not owner.
    """

@router.patch("/publish", response_model=SummaryResponse)
async def publish_module_summary(
    course_id: int,
    module_id: str,
    payload: SummaryPublishUpdate,
    instructor_id: int = Depends(require_instructor),
):
    """
    Toggle is_published. Unpublishing hides the summary from students
    but does not affect existing progress records.
    Raises 404 if summary not found. Raises 403 if not owner.
    """

@router.post("/generate", response_model=SummaryResponse, status_code=201)
async def generate_module_summary(
    course_id: int,
    module_id: str,
    payload: SummaryGenerateRequest,
    instructor_id: int = Depends(require_instructor),
):
    """
    AI-generate a summary from the specified lessons. Calls the AI service
    internally. Upserts the result with authorship.source = 'ai_generated'.
    Raises 404 if course/module/lessons not found.
    Raises 403 if not owner.
    """
```

#### Error Responses

| Code | Trigger                                                               |
|------|-----------------------------------------------------------------------|
| 401  | Missing `X-User-ID` header                                            |
| 403  | Instructor does not own the course                                    |
| 404  | Course, module, or summary not found / inactive                       |
| 409  | `POST /summary` called when summary already exists for this module    |
| 422  | Pydantic validation failure                                           |

---

### Router Registration

Add both routers to `src/api/router.py`:

```python
from src.api import module_quiz, module_summary

router.include_router(module_quiz.router,    prefix="/courses", tags=["Module Quiz"])
router.include_router(module_summary.router, prefix="/courses", tags=["Module Summary"])
```

---

### Authorship Version Logic

Both quiz and summary services apply the same versioning rule on every write:

| Previous source  | Operation        | New source   | Version    |
|------------------|------------------|--------------|------------|
| *(none)*         | manual create    | `manual`     | 1          |
| *(none)*         | AI generate      | `ai_generated` | 1        |
| `ai_generated`   | PUT / PATCH      | `ai_edited`  | prev + 1   |
| `manual`         | PUT / PATCH      | `manual`     | prev + 1   |
| `ai_edited`      | PUT / PATCH      | `ai_edited`  | prev + 1   |
| any              | AI generate      | `ai_generated` | prev + 1 |

`last_edited_by` and `last_edited_at` are always updated on any write.

---

### Complete Endpoint Summary

| Method   | Path                                                                    | Auth       | Description                          |
|----------|-------------------------------------------------------------------------|------------|--------------------------------------|
| `GET`    | `/courses/{id}/modules/{mid}/quiz`                                      | Any user   | Fetch module quiz                    |
| `POST`   | `/courses/{id}/modules/{mid}/quiz`                                      | Instructor | Create quiz manually                 |
| `PUT`    | `/courses/{id}/modules/{mid}/quiz`                                      | Instructor | Replace quiz                         |
| `PATCH`  | `/courses/{id}/modules/{mid}/quiz`                                      | Instructor | Partial update quiz                  |
| `DELETE` | `/courses/{id}/modules/{mid}/quiz`                                      | Instructor | Soft-delete quiz                     |
| `PATCH`  | `/courses/{id}/modules/{mid}/quiz/publish`                              | Instructor | Toggle published state               |
| `POST`   | `/courses/{id}/modules/{mid}/quiz/generate`                             | Instructor | AI-generate quiz                     |
| `GET`    | `/courses/{id}/modules/{mid}/summary`                                   | Any user   | Fetch module summary                 |
| `POST`   | `/courses/{id}/modules/{mid}/summary`                                   | Instructor | Create summary manually              |
| `PUT`    | `/courses/{id}/modules/{mid}/summary`                                   | Instructor | Replace summary                      |
| `PATCH`  | `/courses/{id}/modules/{mid}/summary`                                   | Instructor | Partial update summary               |
| `DELETE` | `/courses/{id}/modules/{mid}/summary`                                   | Instructor | Soft-delete summary                  |
| `PATCH`  | `/courses/{id}/modules/{mid}/summary/publish`                           | Instructor | Toggle published state               |
| `POST`   | `/courses/{id}/modules/{mid}/summary/generate`                          | Instructor | AI-generate summary                  |
