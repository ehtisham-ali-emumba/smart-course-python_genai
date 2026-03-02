# Data Structure Design: MongoDB + PostgreSQL

## Overview

This document outlines the hybrid data architecture for SmartCourse, leveraging:

- **MongoDB**: Flexible, content-rich documents (course content, quizzes, summaries)
- **PostgreSQL**: Structured, relational data (user responses, progress, attempts)

---

## MongoDB Collections

### 1. `course_content` Collection (Existing)

Stores the hierarchical course structure with modules and lessons.

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
          "title": "Variables Quiz",
          "type": "quiz",
          "content": "quiz_6b8c9d1e2f3a",  // Reference to quiz_id in quizzes collection
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
  "created_at": ISODate("2026-01-15T10:00:00Z"),
  "updated_at": ISODate("2026-02-20T14:30:00Z")
}
```

**Indexes:**

- `course_id` (unique)
- `updated_at`

---

### 2. `quizzes` Collection (NEW)

Stores detailed quiz structure with questions, options, and correct answers.

```json
{
  "_id": ObjectId("6b8c9d1e2f3a4567890abcde"),
  "quiz_id": "quiz_6b8c9d1e2f3a",
  "course_id": 1,
  "lesson_id": "les_9k1m2n",  // Links back to lesson in course_content
  "title": "Python Variables Quiz",
  "description": "Test your understanding of Python variables and data types",
  "type": "graded",  // graded, practice, self-assessment
  "passing_score": 70,
  "time_limit_minutes": 15,
  "max_attempts": 3,
  "shuffle_questions": true,
  "shuffle_options": true,
  "show_correct_answers_after": "completion",  // completion, all_attempts_exhausted, never
  "questions": [
    {
      "question_id": "q_1a2b3c",
      "order": 1,
      "question_text": "What is the correct way to declare a variable in Python?",
      "question_type": "multiple_choice",  // multiple_choice, multiple_select, true_false, short_answer
      "points": 10,
      "options": [
        {
          "option_id": "opt_x1y2z3",
          "text": "x = 5",
          "is_correct": true
        },
        {
          "option_id": "opt_a4b5c6",
          "text": "int x = 5",
          "is_correct": false
        },
        {
          "option_id": "opt_d7e8f9",
          "text": "var x = 5",
          "is_correct": false
        },
        {
          "option_id": "opt_g0h1i2",
          "text": "declare x = 5",
          "is_correct": false
        }
      ],
      "explanation": "Python uses dynamic typing, so you don't need to declare the variable type.",
      "hint": "Python doesn't require type declarations"
    },
    {
      "question_id": "q_2d3e4f",
      "order": 2,
      "question_text": "Which of the following are valid Python data types? (Select all that apply)",
      "question_type": "multiple_select",
      "points": 15,
      "options": [
        {
          "option_id": "opt_j3k4l5",
          "text": "int",
          "is_correct": true
        },
        {
          "option_id": "opt_m6n7o8",
          "text": "float",
          "is_correct": true
        },
        {
          "option_id": "opt_p9q0r1",
          "text": "string",
          "is_correct": false
        },
        {
          "option_id": "opt_s2t3u4",
          "text": "str",
          "is_correct": true
        }
      ],
      "explanation": "The correct types are int, float, and str (not 'string').",
      "hint": "Python uses abbreviated names for some types"
    },
    {
      "question_id": "q_3g4h5i",
      "order": 3,
      "question_text": "What will be the output of: print(type(5.0))?",
      "question_type": "short_answer",
      "points": 10,
      "correct_answers": [
        "<class 'float'>",
        "float",
        "<type 'float'>"
      ],
      "case_sensitive": false,
      "explanation": "5.0 is a floating-point number, so type() returns <class 'float'>",
      "hint": "Consider the decimal point"
    }
  ],
  "total_points": 35,
  "metadata": {
    "created_by": 123,  // instructor_id
    "difficulty": "beginner",
    "estimated_time_minutes": 10,
    "tags": ["python", "variables", "data-types"]
  },
  "created_at": ISODate("2026-01-20T09:00:00Z"),
  "updated_at": ISODate("2026-02-15T11:20:00Z"),
  "is_active": true
}
```

**Indexes:**

- `quiz_id` (unique)
- `course_id`
- `lesson_id`
- `created_at`

---

### 3. `summaries` Collection (NEW)

Stores AI-generated summaries for modules, lessons, or entire courses.

```json
{
  "_id": ObjectId("507f1f77bcf86cd799439099"),
  "summary_id": "sum_4g5h6i7j8k",
  "course_id": 1,
  "content_type": "module",  // course, module, lesson
  "content_id": "mod_6a8b9c",  // Reference to module_id, lesson_id, or course_id
  "summary_text": "This module introduces the fundamental concepts of Python programming...",
  "summary_html": "<h2>Key Concepts</h2><p>This module introduces...</p>",
  "key_points": [
    "Variables don't require type declaration",
    "Python supports multiple numeric types: int, float, complex",
    "Strings can use single or double quotes",
    "Type conversion functions: int(), float(), str()"
  ],
  "learning_objectives": [
    "Understand how to declare and use variables",
    "Identify different Python data types",
    "Perform type conversion operations"
  ],
  "glossary": [
    {
      "term": "Variable",
      "definition": "A named storage location in memory that holds a value"
    },
    {
      "term": "Data Type",
      "definition": "The classification of data that tells the compiler or interpreter how the data should be used"
    }
  ],
  "difficulty_assessment": {
    "level": "beginner",
    "estimated_hours": 2.5,
    "prerequisites": []
  },
  "generated_by": "ai-service",
  "model_version": "gpt-4-turbo",
  "metadata": {
    "word_count": 450,
    "reading_time_minutes": 5,
    "tags": ["python", "fundamentals", "variables"]
  },
  "created_at": ISODate("2026-01-21T10:00:00Z"),
  "updated_at": ISODate("2026-02-10T14:00:00Z"),
  "is_active": true
}
```

**Indexes:**

- `summary_id` (unique)
- `course_id`
- `content_type, content_id` (compound)
- `created_at`

---

## PostgreSQL Tables

### 1. `courses` Table (Existing)

Stores course metadata.

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
CREATE INDEX idx_courses_published_at ON courses(published_at);
```

**Example Data:**

```sql
id  | title             | instructor_id | status    | price
----|-------------------|---------------|-----------|-------
1   | Python Mastery    | 123           | published | 99.99
2   | Web Development   | 456           | published | 149.99
```

---

### 2. `enrollments` Table (Existing)

Tracks which users are enrolled in which courses.

```sql
CREATE TABLE enrollments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    status VARCHAR(50) DEFAULT 'active' NOT NULL,
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

**Example Data:**

```sql
id  | user_id | course_id | status    | progress_percentage | enrolled_at
----|---------|-----------|-----------|---------------------|------------
1   | 789     | 1         | active    | 35.50               | 2026-02-01
2   | 789     | 2         | active    | 12.00               | 2026-02-15
3   | 890     | 1         | completed | 100.00              | 2026-01-10
```

---

### 3. `progress` Table (Existing - Enhanced)

Tracks granular progress for each content item (lessons, quizzes, etc.).

```sql
CREATE TABLE progress (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    enrollment_id INTEGER NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
    item_type VARCHAR(20) NOT NULL,  -- 'video', 'text', 'quiz', 'assignment'
    item_id VARCHAR(50) NOT NULL,    -- References MongoDB lesson_id or quiz_id
    progress_percentage NUMERIC(5,2) DEFAULT 0 NOT NULL,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL,
    CONSTRAINT uq_progress_user_enrollment_item UNIQUE(user_id, enrollment_id, item_type, item_id)
);

CREATE INDEX idx_progress_user_enrollment ON progress(user_id, enrollment_id);
CREATE INDEX idx_progress_item ON progress(item_type, item_id);
```

**Example Data:**

```sql
id  | user_id | enrollment_id | item_type | item_id         | progress_percentage | completed_at
----|---------|---------------|-----------|-----------------|---------------------|-------------
1   | 789     | 1             | video     | les_3d4e5f      | 100.00              | 2026-02-05
2   | 789     | 1             | quiz      | les_9k1m2n      | 100.00              | 2026-02-06
3   | 789     | 1             | video     | les_4f5g6h      | 45.00               | NULL
```

---

### 4. `quiz_attempts` Table (NEW)

Tracks each attempt a user makes on a quiz.

```sql
CREATE TABLE quiz_attempts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    enrollment_id INTEGER NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
    quiz_id VARCHAR(50) NOT NULL,  -- References MongoDB quiz_id
    lesson_id VARCHAR(50) NOT NULL,  -- References MongoDB lesson_id
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL,
    status VARCHAR(20) DEFAULT 'in_progress' NOT NULL,  -- in_progress, submitted, graded
    score NUMERIC(5,2),  -- Percentage score (0-100)
    points_earned NUMERIC(10,2),
    total_points NUMERIC(10,2),
    time_spent_seconds INTEGER,
    passed BOOLEAN,
    started_at TIMESTAMP DEFAULT NOW() NOT NULL,
    submitted_at TIMESTAMP,
    graded_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL,
    CONSTRAINT uq_quiz_attempts UNIQUE(user_id, quiz_id, attempt_number)
);

CREATE INDEX idx_quiz_attempts_user_id ON quiz_attempts(user_id);
CREATE INDEX idx_quiz_attempts_enrollment_id ON quiz_attempts(enrollment_id);
CREATE INDEX idx_quiz_attempts_quiz_id ON quiz_attempts(quiz_id);
CREATE INDEX idx_quiz_attempts_course_id ON quiz_attempts(course_id);
CREATE INDEX idx_quiz_attempts_status ON quiz_attempts(status);
```

**Example Data:**

```sql
id  | user_id | quiz_id              | attempt_number | status    | score | points_earned | total_points | passed | submitted_at
----|---------|----------------------|----------------|-----------|-------|---------------|--------------|--------|-------------
1   | 789     | quiz_6b8c9d1e2f3a    | 1              | graded    | 71.43 | 25.00         | 35.00        | true   | 2026-02-06
2   | 789     | quiz_6b8c9d1e2f3a    | 2              | graded    | 85.71 | 30.00         | 35.00        | true   | 2026-02-07
3   | 890     | quiz_6b8c9d1e2f3a    | 1              | graded    | 57.14 | 20.00         | 35.00        | false  | 2026-02-08
```

---

### 5. `user_answers` Table (NEW)

Stores individual answers for each question in a quiz attempt.

```sql
CREATE TABLE user_answers (
    id SERIAL PRIMARY KEY,
    quiz_attempt_id INTEGER NOT NULL REFERENCES quiz_attempts(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL,
    question_id VARCHAR(50) NOT NULL,  -- References MongoDB question_id
    question_type VARCHAR(20) NOT NULL,
    user_response JSONB NOT NULL,  -- Flexible storage for different answer types
    is_correct BOOLEAN,
    points_earned NUMERIC(10,2),
    points_possible NUMERIC(10,2),
    time_spent_seconds INTEGER,
    answered_at TIMESTAMP DEFAULT NOW() NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW() NOT NULL
);

CREATE INDEX idx_user_answers_attempt_id ON user_answers(quiz_attempt_id);
CREATE INDEX idx_user_answers_user_id ON user_answers(user_id);
CREATE INDEX idx_user_answers_question_id ON user_answers(question_id);
CREATE INDEX idx_user_answers_user_response ON user_answers USING gin(user_response);
```

**Example Data with Different Question Types:**

```sql
-- Multiple Choice Answer
id  | quiz_attempt_id | user_id | question_id | question_type    | user_response                           | is_correct | points_earned | points_possible
----|-----------------|---------|-------------|------------------|-----------------------------------------|------------|---------------|----------------
1   | 1               | 789     | q_1a2b3c    | multiple_choice  | {"selected_option": "opt_x1y2z3"}       | true       | 10.00         | 10.00

-- Multiple Select Answer
2   | 1               | 789     | q_2d3e4f    | multiple_select  | {"selected_options": ["opt_j3k4l5", "opt_m6n7o8", "opt_s2t3u4"]} | true | 15.00 | 15.00

-- Short Answer
3   | 1               | 789     | q_3g4h5i    | short_answer     | {"text": "float"}                       | true       | 10.00         | 10.00

-- Wrong Answer Example
4   | 3               | 890     | q_1a2b3c    | multiple_choice  | {"selected_option": "opt_a4b5c6"}       | false      | 0.00          | 10.00
```

**user_response JSONB Structure Examples:**

```json
// Multiple Choice
{
  "selected_option": "opt_x1y2z3"
}

// Multiple Select
{
  "selected_options": ["opt_j3k4l5", "opt_m6n7o8"]
}

// True/False
{
  "selected_option": "opt_true"
}

// Short Answer
{
  "text": "float"
}

// Essay/Long Answer
{
  "text": "Python is a high-level programming language...",
  "word_count": 150
}
```

---

## Data Relationships

### Content Flow

```
PostgreSQL: courses (id=1)
    ↓ (course_id reference)
MongoDB: course_content (course_id=1)
    ↓ (contains modules and lessons)
    lessons → lesson_id="les_9k1m2n" (type="quiz")
    ↓ (content field references quiz_id)
MongoDB: quizzes (quiz_id="quiz_6b8c9d1e2f3a")
```

### User Progress Flow

```
PostgreSQL: enrollments (user_id=789, course_id=1)
    ↓
PostgreSQL: progress (tracks each lesson/quiz completion)
    ↓ (for quiz items)
PostgreSQL: quiz_attempts (tracks each quiz attempt)
    ↓
PostgreSQL: user_answers (stores individual question responses)
```

---

## Key Design Decisions

### Why MongoDB for Content?

- **Flexible schema**: Course content structure can evolve without migrations
- **Nested documents**: Modules → Lessons → Resources naturally nest
- **Rich content**: Quizzes with complex question types fit well in documents
- **Version control**: Easy to version entire course content as documents

### Why PostgreSQL for User Data?

- **ACID compliance**: Critical for enrollment and scoring transactions
- **Strong consistency**: User progress must be accurate
- **Relational integrity**: Foreign keys ensure data consistency
- **Analytics**: Easier to query aggregated user performance data
- **Indexing**: Efficient queries for user progress dashboards

---

## Usage Examples

### 1. Student Takes a Quiz

**Step 1:** Fetch quiz from MongoDB

```python
quiz = await mongodb.quizzes.find_one({"quiz_id": "quiz_6b8c9d1e2f3a"})
```

**Step 2:** Create quiz attempt in PostgreSQL

```python
attempt = QuizAttempt(
    user_id=789,
    enrollment_id=1,
    quiz_id="quiz_6b8c9d1e2f3a",
    lesson_id="les_9k1m2n",
    course_id=1,
    attempt_number=1,
    total_points=35.00
)
db.add(attempt)
await db.commit()
```

**Step 3:** Save each answer

```python
for question in user_submitted_answers:
    answer = UserAnswer(
        quiz_attempt_id=attempt.id,
        user_id=789,
        question_id=question["question_id"],
        question_type=question["type"],
        user_response={"selected_option": question["answer"]},
        is_correct=check_answer(question),
        points_earned=calculate_points(question),
        points_possible=question["points"]
    )
    db.add(answer)
```

**Step 4:** Update quiz attempt with final score

```python
attempt.status = "graded"
attempt.score = (total_earned / total_possible) * 100
attempt.points_earned = total_earned
attempt.passed = attempt.score >= quiz["passing_score"]
attempt.submitted_at = datetime.utcnow()
await db.commit()
```

**Step 5:** Update progress table

```python
progress = Progress(
    user_id=789,
    enrollment_id=1,
    item_type="quiz",
    item_id="les_9k1m2n",
    progress_percentage=100.00,
    completed_at=datetime.utcnow()
)
db.merge(progress)
await db.commit()
```

### 2. Display Student Dashboard

**Fetch enrollment and progress:**

```python
enrollment = await db.query(Enrollment).filter(
    Enrollment.user_id == 789,
    Enrollment.course_id == 1
).first()

progress_items = await db.query(Progress).filter(
    Progress.enrollment_id == enrollment.id
).all()

quiz_attempts = await db.query(QuizAttempt).filter(
    QuizAttempt.enrollment_id == enrollment.id
).order_by(QuizAttempt.started_at.desc()).all()
```

**Fetch course content from MongoDB:**

```python
course_content = await mongodb.course_content.find_one({"course_id": 1})
```

**Combine data for display:**

```python
dashboard = {
    "course": course_content,
    "enrollment": enrollment,
    "completed_lessons": [p for p in progress_items if p.completed_at],
    "quiz_scores": [
        {
            "quiz_id": a.quiz_id,
            "best_score": max(attempts for same quiz),
            "attempts": a.attempt_number
        }
        for a in quiz_attempts
    ]
}
```

### 3. Generate Analytics Report

**Top performers query:**

```sql
SELECT
    u.username,
    AVG(qa.score) as avg_quiz_score,
    COUNT(DISTINCT qa.quiz_id) as quizzes_completed,
    SUM(qa.time_spent_seconds) as total_time_seconds
FROM quiz_attempts qa
JOIN users u ON qa.user_id = u.id
WHERE qa.course_id = 1
  AND qa.status = 'graded'
GROUP BY u.username
ORDER BY avg_quiz_score DESC
LIMIT 10;
```

**Quiz difficulty analysis:**

```sql
SELECT
    quiz_id,
    COUNT(*) as total_attempts,
    AVG(score) as avg_score,
    COUNT(CASE WHEN passed THEN 1 END) as pass_count,
    COUNT(CASE WHEN passed THEN 1 END)::float / COUNT(*) * 100 as pass_rate
FROM quiz_attempts
WHERE status = 'graded'
GROUP BY quiz_id
ORDER BY pass_rate ASC;
```

---

## Migration Considerations

### Adding Quizzes and Summaries to MongoDB

1. **Create indexes:**

```python
await mongodb.quizzes.create_index("quiz_id", unique=True)
await mongodb.quizzes.create_index("course_id")
await mongodb.quizzes.create_index("lesson_id")

await mongodb.summaries.create_index("summary_id", unique=True)
await mongodb.summaries.create_index("course_id")
await mongodb.summaries.create_index([("content_type", 1), ("content_id", 1)])
```

2. **Create tables in PostgreSQL:**

```bash
# Create migration
alembic revision -m "add_quiz_attempts_and_user_answers"

# Apply migration
alembic upgrade head
```

---

## Best Practices

1. **Always reference MongoDB IDs as strings** in PostgreSQL (quiz_id, lesson_id)
2. **Use JSONB for flexible user_response** to handle different question types
3. **Index foreign keys** for efficient joins
4. **Denormalize sparingly**: Keep course_id in quiz_attempts for easier analytics
5. **Validate MongoDB references** before creating PostgreSQL records
6. **Use transactions** when updating related tables (quiz_attempts + user_answers)
7. **Cache frequently accessed MongoDB documents** (Redis layer)
8. **Archive old attempts** after a retention period to keep tables lean

---

## Summary

This hybrid architecture gives you:

- **Flexibility**: MongoDB for evolving content structures
- **Consistency**: PostgreSQL for transactional user data
- **Performance**: Proper indexing on both sides
- **Analytics**: Rich querying capabilities for insights
- **Scalability**: Separate read/write patterns for content vs. user data
