# Quiz Attempt & Student Answers — Implementation Plan

## Context

- **Quizzes** live in MongoDB (`module_quizzes` collection), keyed by `(course_id, module_id)`.
- **Student progress data** lives in PostgreSQL — tables `quiz_attempts` and `user_answers` already exist.
- **Enrollment** table links `student_id ↔ course_id` and provides the `enrollment_id` used as FK in `quiz_attempts`.
- Each course module can have **1 quiz**; a student has **1 attempt** per quiz (no multiple attempts).

---

## Decision: Batch Submit vs Question-by-Question

### Recommendation: **Batch Submit (all answers at once)**

| Factor | Batch Submit | One-by-One |
|--------|-------------|------------|
| Network calls | 1 request | N requests (1 per question) |
| Atomicity | All-or-nothing in a single transaction | Partial state if student disconnects |
| Grading | Instant — score computed server-side in one pass | Must track partial state, grade at end anyway |
| Frontend complexity | Simple — collect answers in local state, POST once | Must manage per-question API calls + retry |
| Time tracking | `time_spent_seconds` per question can be tracked on frontend and sent in payload | Same, but sent incrementally |
| DB writes | 1 INSERT for attempt + N INSERTs for answers (batch) | N+1 separate transactions |
| Resume support | Not needed for typical quizzes (<30 min) | Adds complexity for marginal benefit |

**Verdict**: Batch submit is simpler, faster, and more reliable. The frontend tracks per-question time locally and sends everything in one payload. The server creates the `quiz_attempt` + all `user_answers` in a single DB transaction, grades immediately, and returns the result.

---

## Database Flow

```
Student clicks "Start Quiz"
  → POST /start  →  INSERT quiz_attempts (status=in_progress)
  → Returns: attempt_id, quiz questions (no answers), time_limit

Student answers questions on frontend (local state)

Student clicks "Submit"
  → POST /submit  →  INSERT user_answers (bulk)
                   →  Auto-grade each answer
                   →  UPDATE quiz_attempts (score, passed, status=graded, submitted_at, quiz_version)
                   →  Upsert progress table (item_type=module_quiz)
  → Returns: score, passed, per-question results
```

---

## Endpoints

All endpoints are prefixed under: `/courses/{course_id}/modules/{module_id}/quiz/attempts`

### 1. Start a Quiz Attempt

```
POST /courses/{course_id}/modules/{module_id}/quiz/attempts/start
```

**Auth**: `require_student` → returns `student_profile_id`

**Logic**:
1. Verify student has an **active enrollment** for `course_id` → get `enrollment_id`
2. Fetch quiz from MongoDB → check `is_published` and `is_active`
3. Check if an existing attempt with `status=in_progress` exists for `(enrollment_id, module_id)` — if yes, return it instead of creating a new one
4. Check if a `status=graded` attempt exists — if yes, return `409` (already submitted, use retake endpoint if quiz is outdated)
5. INSERT into `quiz_attempts`:
   ```python
   {
       "enrollment_id": enrollment_id,
       "module_id": module_id,
       "status": "in_progress",
       "started_at": now()
   }
   ```
6. Return the quiz questions **without correct answers** (strip `is_correct` from options, strip `correct_answers`, strip `explanation`)

**Request Body**: None (or optional `{}`)

**Response** (`201 Created` or `200 OK` if resuming):
```json
{
    "attempt_id": "uuid",
    "started_at": "2026-03-17T10:00:00Z",
    "time_limit_minutes": 30,
    "questions": [
        {
            "question_id": "abc123",
            "order": 1,
            "question_text": "What is X?",
            "question_type": "multiple_choice",
            "options": [
                { "option_id": "opt_a", "text": "Option A" },
                { "option_id": "opt_b", "text": "Option B" }
            ],
            "hint": "Think about..."
        }
    ]
}
```

**Error cases**:
- `404` — enrollment not found or quiz not found
- `403` — not enrolled / enrollment not active
- `409` — already submitted (quiz already attempted)

---

### 2. Submit Quiz Answers (Batch)

```
POST /courses/{course_id}/modules/{module_id}/quiz/attempts/{attempt_id}/submit
```

**Auth**: `require_student` → returns `student_profile_id`

**Request Body**:
```json
{
    "answers": [
        {
            "question_id": "abc123",
            "response": { "selected_option_id": "opt_a" },
            "time_spent_seconds": 45
        },
        {
            "question_id": "def456",
            "response": { "selected_option_ids": ["opt_a", "opt_c"] },
            "time_spent_seconds": 30
        },
        {
            "question_id": "ghi789",
            "response": { "selected_option_id": "opt_true" },
            "time_spent_seconds": 10
        },
        {
            "question_id": "jkl012",
            "response": { "text": "my short answer" },
            "time_spent_seconds": 60
        }
    ],
    "total_time_spent_seconds": 145
}
```

**`user_response` JSONB format by question type**:

| Question Type | `response` format |
|--------------|-------------------|
| `multiple_choice` | `{ "selected_option_id": "opt_a" }` |
| `multiple_select` | `{ "selected_option_ids": ["opt_a", "opt_c"] }` |
| `true_false` | `{ "selected_option_id": "opt_true" }` |
| `short_answer` | `{ "text": "student answer" }` |

**Logic**:
1. Verify the `attempt_id` belongs to the student's enrollment
2. Verify `status == "in_progress"` (can't re-submit)
3. If `time_limit_minutes` is set, check `now() - started_at <= time_limit + grace_period`
4. Fetch quiz from MongoDB (need correct answers for grading)
5. **In a single DB transaction**:
   - For each answer, determine `question_type` from the quiz, grade it:
     - `multiple_choice` / `true_false`: compare `selected_option_id` against the option with `is_correct=True`
     - `multiple_select`: compare `selected_option_ids` set against all options with `is_correct=True` (exact match)
     - `short_answer`: compare `text` against `correct_answers` list (respect `case_sensitive` flag)
   - Bulk INSERT into `user_answers`
   - Compute `score = (correct_count / total_questions) * 100`
   - Determine `passed = score >= settings.passing_score`
   - UPDATE `quiz_attempts`: `status=graded`, `score`, `passed`, `submitted_at=now()`, `graded_at=now()`, `time_spent_seconds`, `quiz_version=quiz_doc["authorship"]["version"]`
6. Upsert `progress` table: `item_type=module_quiz`, `item_id=module_id`, `progress_percentage=100` (attempted)
7. Return results

**Response** (`200 OK`):
```json
{
    "attempt_id": "uuid",
    "status": "graded",
    "score": 80.00,
    "passed": true,
    "total_questions": 5,
    "correct_answers": 4,
    "time_spent_seconds": 145,
    "submitted_at": "2026-03-17T10:05:00Z",
    "results": [
        {
            "question_id": "abc123",
            "is_correct": true,
            "user_response": { "selected_option_id": "opt_a" },
            "correct_answer": { "option_id": "opt_a", "text": "Option A" },
            "explanation": "A is correct because..."
        }
    ]
}
```

> **Note on `show_correct_answers_after`**: The `results` array should respect the quiz setting:
> - `"completion"` — always show correct answers after submission
> - `"passing"` — only show if `passed == True`
> - `"never"` — omit `correct_answer` and `explanation` from response

**Error cases**:
- `404` — attempt not found
- `403` — attempt doesn't belong to this student
- `409` — attempt already submitted
- `400` — time limit exceeded / missing questions

---

### 3. Get Quiz Attempt Result

```
GET /courses/{course_id}/modules/{module_id}/quiz/attempts/{attempt_id}
```

**Auth**: `require_student`

**Logic**:
1. Fetch the `quiz_attempt` by ID, verify ownership
2. Fetch associated `user_answers`
3. If `status == graded`, fetch quiz from MongoDB for explanations (respecting `show_correct_answers_after`)

**Response** (`200 OK`):
```json
{
    "attempt_id": "uuid",
    "status": "graded",
    "score": 80.00,
    "passed": true,
    "total_questions": 5,
    "correct_answers": 4,
    "time_spent_seconds": 145,
    "started_at": "2026-03-17T10:00:00Z",
    "submitted_at": "2026-03-17T10:05:00Z",
    "answers": [
        {
            "question_id": "abc123",
            "question_type": "multiple_choice",
            "user_response": { "selected_option_id": "opt_a" },
            "is_correct": true,
            "time_spent_seconds": 45
        }
    ]
}
```

---

## quiz_attempts — What Gets Stored

| Column | When Set | Value |
|--------|----------|-------|
| `id` | On start | UUID auto-generated |
| `enrollment_id` | On start | Looked up from student's enrollment for this course |
| `module_id` | On start | From URL path |
| `status` | On start → On submit | `"in_progress"` → `"graded"` |
| `score` | On submit | `(correct / total) * 100`, stored as `Numeric(5,2)` |
| `passed` | On submit | `score >= passing_score` |
| `time_spent_seconds` | On submit | From request payload or `submitted_at - started_at` |
| `quiz_version` | On submit | `quiz_doc["authorship"]["version"]` from MongoDB |
| `started_at` | On start | `now()` |
| `submitted_at` | On submit | `now()` |
| `graded_at` | On submit | `now()` (auto-graded = instant) |

---

## Files to Create / Modify

### New Files

| File | Purpose |
|------|---------|
| `src/schemas/quiz_attempt.py` | Pydantic models for request/response |
| `src/repositories/quiz_attempt.py` | DB operations for quiz_attempts + user_answers |
| `src/services/quiz_attempt.py` | Business logic (start, submit, grade, fetch) |
| `src/api/quiz_attempt.py` | FastAPI route handlers |

### Modified Files

| File | Change |
|------|--------|
| `src/api/router.py` | Register `quiz_attempt.router` |
| `models/quiz_attempt.py` | Add `quiz_version` column |

---

## Schemas (`src/schemas/quiz_attempt.py`)

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID
from decimal import Decimal


# ── Request Schemas ──────────────────────────────────────────────────────────


class AnswerSubmission(BaseModel):
    question_id: str
    response: dict  # JSONB — format varies by question_type
    time_spent_seconds: Optional[int] = None


class QuizSubmitRequest(BaseModel):
    answers: list[AnswerSubmission] = Field(..., min_length=1)
    total_time_spent_seconds: Optional[int] = None


# ── Response Schemas ─────────────────────────────────────────────────────────


class StartQuizQuestion(BaseModel):
    question_id: str
    order: int
    question_text: str
    question_type: str
    options: Optional[list[dict]] = None  # option_id + text only, no is_correct
    hint: Optional[str] = None


class StartQuizResponse(BaseModel):
    attempt_id: UUID
    started_at: datetime
    time_limit_minutes: Optional[int] = None
    questions: list[StartQuizQuestion]


class AnswerResult(BaseModel):
    question_id: str
    is_correct: bool
    user_response: dict
    correct_answer: Optional[dict] = None  # hidden based on show_correct_answers_after
    explanation: Optional[str] = None


class SubmitQuizResponse(BaseModel):
    attempt_id: UUID
    status: str
    score: Decimal
    passed: bool
    total_questions: int
    correct_answers: int
    time_spent_seconds: Optional[int]
    submitted_at: datetime
    results: list[AnswerResult]


class AttemptDetailResponse(BaseModel):
    attempt_id: UUID
    status: str
    score: Optional[Decimal] = None
    passed: Optional[bool] = None
    total_questions: Optional[int] = None
    correct_answers_count: Optional[int] = None
    time_spent_seconds: Optional[int] = None
    started_at: datetime
    submitted_at: Optional[datetime] = None
    answers: list[AnswerResult]
```

---

## Grading Logic (in service layer)

```python
def grade_answer(question: dict, user_response: dict) -> bool:
    qtype = question["question_type"]

    if qtype in ("multiple_choice", "true_false"):
        correct_option = next(o for o in question["options"] if o["is_correct"])
        return user_response.get("selected_option_id") == correct_option["option_id"]

    if qtype == "multiple_select":
        correct_ids = {o["option_id"] for o in question["options"] if o["is_correct"]}
        selected_ids = set(user_response.get("selected_option_ids", []))
        return correct_ids == selected_ids

    if qtype == "short_answer":
        user_text = user_response.get("text", "")
        case_sensitive = question.get("case_sensitive", False)
        for answer in question.get("correct_answers", []):
            if case_sensitive and user_text == answer:
                return True
            if not case_sensitive and user_text.lower() == answer.lower():
                return True
        return False

    return False
```

---

## Router Registration (`src/api/router.py`)

Add this line:

```python
from api import quiz_attempt

router.include_router(
    quiz_attempt.router,
    prefix="/courses",
    tags=["Quiz Attempts"]
)
```

---

## Postman Collection — Sample Requests

### Prerequisites

Set these headers on all requests:
```
X-User-ID: <user-uuid>
X-User-Role: student
X-Profile-ID: <student-profile-uuid>
```

Assume:
- `course_id` = `a1b2c3d4-1234-5678-9abc-def012345678`
- `module_id` = `mod_1`
- Student is enrolled in the course

---

### Request 1: Start Quiz Attempt

```
POST http://localhost:8000/api/v1/courses/a1b2c3d4-1234-5678-9abc-def012345678/modules/mod_1/quiz/attempts/start

Headers:
  X-User-ID: 11111111-1111-1111-1111-111111111111
  X-User-Role: student
  X-Profile-ID: 22222222-2222-2222-2222-222222222222

Body: (none)
```

**Expected Response** (`201`):
```json
{
    "attempt_id": "99999999-9999-9999-9999-999999999999",
    "started_at": "2026-03-17T10:00:00Z",
    "time_limit_minutes": 30,
    "questions": [
        {
            "question_id": "q1hex",
            "order": 1,
            "question_text": "What is Python?",
            "question_type": "multiple_choice",
            "options": [
                { "option_id": "opt_a", "text": "A programming language" },
                { "option_id": "opt_b", "text": "A snake" },
                { "option_id": "opt_c", "text": "A framework" }
            ],
            "hint": "It's used for software development"
        },
        {
            "question_id": "q2hex",
            "order": 2,
            "question_text": "Python is dynamically typed.",
            "question_type": "true_false",
            "options": [
                { "option_id": "opt_true", "text": "True" },
                { "option_id": "opt_false", "text": "False" }
            ],
            "hint": null
        },
        {
            "question_id": "q3hex",
            "order": 3,
            "question_text": "Select all valid Python data types:",
            "question_type": "multiple_select",
            "options": [
                { "option_id": "opt_a", "text": "int" },
                { "option_id": "opt_b", "text": "str" },
                { "option_id": "opt_c", "text": "char" },
                { "option_id": "opt_d", "text": "list" }
            ],
            "hint": null
        },
        {
            "question_id": "q4hex",
            "order": 4,
            "question_text": "What keyword is used to define a function in Python?",
            "question_type": "short_answer",
            "options": null,
            "hint": "It's a 3-letter word"
        }
    ]
}
```

---

### Request 2: Submit Quiz Answers

```
POST http://localhost:8000/api/v1/courses/a1b2c3d4-1234-5678-9abc-def012345678/modules/mod_1/quiz/attempts/99999999-9999-9999-9999-999999999999/submit

Headers:
  X-User-ID: 11111111-1111-1111-1111-111111111111
  X-User-Role: student
  X-Profile-ID: 22222222-2222-2222-2222-222222222222
  Content-Type: application/json

Body:
{
    "answers": [
        {
            "question_id": "q1hex",
            "response": { "selected_option_id": "opt_a" },
            "time_spent_seconds": 15
        },
        {
            "question_id": "q2hex",
            "response": { "selected_option_id": "opt_true" },
            "time_spent_seconds": 8
        },
        {
            "question_id": "q3hex",
            "response": { "selected_option_ids": ["opt_a", "opt_b", "opt_d"] },
            "time_spent_seconds": 25
        },
        {
            "question_id": "q4hex",
            "response": { "text": "def" },
            "time_spent_seconds": 12
        }
    ],
    "total_time_spent_seconds": 60
}
```

**Expected Response** (`200`):
```json
{
    "attempt_id": "99999999-9999-9999-9999-999999999999",
    "status": "graded",
    "score": 100.00,
    "passed": true,
    "total_questions": 4,
    "correct_answers": 4,
    "time_spent_seconds": 60,
    "submitted_at": "2026-03-17T10:01:00Z",
    "results": [
        {
            "question_id": "q1hex",
            "is_correct": true,
            "user_response": { "selected_option_id": "opt_a" },
            "correct_answer": { "option_id": "opt_a", "text": "A programming language" },
            "explanation": "Python is a high-level programming language."
        },
        {
            "question_id": "q2hex",
            "is_correct": true,
            "user_response": { "selected_option_id": "opt_true" },
            "correct_answer": { "option_id": "opt_true", "text": "True" },
            "explanation": "Python uses dynamic typing."
        },
        {
            "question_id": "q3hex",
            "is_correct": true,
            "user_response": { "selected_option_ids": ["opt_a", "opt_b", "opt_d"] },
            "correct_answer": { "option_ids": ["opt_a", "opt_b", "opt_d"] },
            "explanation": "char is not a Python built-in type."
        },
        {
            "question_id": "q4hex",
            "is_correct": true,
            "user_response": { "text": "def" },
            "correct_answer": { "text": "def" },
            "explanation": "The 'def' keyword defines functions in Python."
        }
    ]
}
```

---

### Request 3: Get Attempt Detail

```
GET http://localhost:8000/api/v1/courses/a1b2c3d4-1234-5678-9abc-def012345678/modules/mod_1/quiz/attempts/99999999-9999-9999-9999-999999999999

Headers:
  X-User-ID: 11111111-1111-1111-1111-111111111111
  X-User-Role: student
  X-Profile-ID: 22222222-2222-2222-2222-222222222222
```

---

## Implementation Order

1. **Migration** — add `quiz_version` column to `quiz_attempts`
2. **Schemas** — `src/schemas/quiz_attempt.py` (Pydantic models)
3. **Repository** — `src/repositories/quiz_attempt.py` (DB queries for quiz_attempts + user_answers)
4. **Service** — `src/services/quiz_attempt.py` (business logic + grading)
5. **API** — `src/api/quiz_attempt.py` (route handlers)
6. **Router** — register in `src/api/router.py`
7. **Test** — hit the Postman samples above

---

## Handling Quiz Changes After Students Have Attempted

### The Problem

Teacher changes quiz questions after a student already submitted. Old `user_answers` rows in Postgres have `question_id`s pointing to questions that no longer exist in MongoDB.

### The Solution: `quiz_version` Flag on `quiz_attempts`

MongoDB quiz already has `authorship.version` (increments on every edit). We store it on `quiz_attempts` at submit time and use it as a simple comparison flag.

#### Step 1: Add `quiz_version` to `quiz_attempts`

Migration:

```python
"""add quiz_version to quiz_attempts"""

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column("quiz_attempts", sa.Column("quiz_version", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("quiz_attempts", "quiz_version")
```

Model update (`models/quiz_attempt.py`):

```python
quiz_version: Mapped[int | None] = mapped_column(default=None)
```

#### Step 2: Save version when student submits

```python
quiz_doc = await self.quiz_repo.get_published_by_course_module(course_id, module_id)

# after grading...
attempt.quiz_version = quiz_doc["authorship"]["version"]
attempt.score = score
attempt.status = "graded"
```

#### Step 3: Return `quiz_outdated` flag when student fetches quiz module info

When the student lands on the course page and we return the module quiz info along with their last attempt, we compare versions:

```python
quiz_doc = await self.quiz_repo.get_published_by_course_module(course_id, module_id)
last_attempt = await self.attempt_repo.get_latest_attempt(enrollment_id, module_id)

quiz_outdated = False
if last_attempt and last_attempt.quiz_version:
    quiz_outdated = last_attempt.quiz_version != quiz_doc["authorship"]["version"]
```

Response:

```json
{
    "module_id": "mod_1",
    "quiz_title": "Module 1 Quiz",
    "last_attempt": {
        "attempt_id": "uuid",
        "score": 80.00,
        "passed": true,
        "submitted_at": "2026-03-17T10:05:00Z"
    },
    "quiz_outdated": true
}
```

#### Step 4: How it works end-to-end

```
Course Page (student lands here)
│
├─ quiz_outdated = false
│   └─ Show: "Score: 80% - Passed ✓"
│   └─ Student opens quiz details → show attempt answers (from user_answers)
│
├─ quiz_outdated = true
│   └─ Show: "Score: 80% (quiz updated) - Resubmit required"
│   └─ Student opens quiz details → show old answers as read-only
│   └─ Student clicks "Retake Quiz" → hits POST /start
│       └─ Server deletes old quiz_attempt (CASCADE deletes user_answers)
│       └─ Creates fresh attempt with new questions
│       └─ quiz_outdated becomes false after resubmit
```

#### Step 5: Cleanup outdated attempt when student retakes

When the student clicks "Retake Quiz" and hits `POST /start`, the service checks if the existing attempt is outdated. If yes, delete it before creating a new one:

```python
async def start_attempt(self, enrollment_id, module_id, course_id):
    quiz_doc = await self.quiz_repo.get_published_by_course_module(course_id, module_id)
    current_version = quiz_doc["authorship"]["version"]

    existing = await self.attempt_repo.get_attempt(enrollment_id, module_id)

    if existing:
        if existing.status == "in_progress":
            return existing  # resume

        if existing.quiz_version == current_version:
            raise AlreadySubmitted()  # 409 — quiz hasn't changed, can't retake

        # Quiz is outdated — delete old attempt (CASCADE deletes user_answers)
        await self.db.delete(existing)
        await self.db.flush()

    # Create fresh attempt
    new_attempt = QuizAttempt(
        enrollment_id=enrollment_id,
        module_id=module_id,
        status="in_progress",
    )
    # ...
```

#### Summary

| What | Where | When |
|------|-------|------|
| `quiz_version` saved | `quiz_attempts` table | On submit |
| Version compared | Service layer | When returning module quiz info to student |
| `quiz_outdated` flag | API response | Sent to frontend |
| Old attempt deleted | Service layer | When student starts retake (`POST /start`) on outdated quiz |
| `user_answers` deleted | Automatic (CASCADE) | When parent `quiz_attempt` is deleted |
| Frontend action | Show "resubmit" prompt | When `quiz_outdated = true` |

**Total changes: 1 column, 1 migration, 1 version comparison, 1 boolean flag, 1 cleanup on retake.**

### Changes to Files for This Feature

| File | Change |
|------|--------|
| `models/quiz_attempt.py` | Add `quiz_version: Mapped[int \| None]` column |
| `alembic/versions/xxx_add_quiz_version.py` | New migration |
| `services/quiz_attempt.py` | Save version on submit, compare on fetch, delete outdated on retake |
| `schemas/quiz_attempt.py` | Add `quiz_outdated: bool` to module quiz info response |

---

## Note on `attempt_number` Column

The `quiz_attempts` table has an `attempt_number` column and a unique constraint on `(enrollment_id, module_id, attempt_number)`. Since we're using a single-attempt model (one attempt per student per module, replaced on quiz change), always set `attempt_number = 1`. The column stays for now but is not actively used for tracking multiple attempts.

---

## Analytics Note

The `enrollment_id` in `quiz_attempts` already links to `student_id` and `course_id` via the `enrollments` table. For future analytics:

```sql
-- Get all quiz scores for a student across all courses
SELECT e.student_id, e.course_id, qa.module_id, qa.score, qa.passed
FROM quiz_attempts qa
JOIN enrollments e ON qa.enrollment_id = e.id
WHERE e.student_id = '<student-uuid>';

-- Get average score per module across all students
SELECT qa.module_id, AVG(qa.score), COUNT(*) as total_attempts
FROM quiz_attempts qa
WHERE qa.status = 'graded'
GROUP BY qa.module_id;
```

This is sufficient for analytics — no extra columns needed in the current schema.
