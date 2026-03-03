# AI Service - Sample Postman Requests

Use this guide to manually verify all AI endpoints.

## Option A (Recommended for debugging): call ai-service directly

**Base URL:** `http://localhost:8009`  
**Headers (required on all protected routes):**

- `Content-Type: application/json`
- `X-User-ID: 1`
- `X-User-Role: instructor` (for instructor/index routes)
- `X-User-Role: student` (for tutor routes)

## Option B: call through API Gateway

If gateway routing for AI is enabled, use:

- **Base URL:** `http://localhost:8000`
- Add `Authorization: Bearer <your_jwt_token>`

---

## 0. Health Check

**Method:** `GET`  
**URL:** `http://localhost:8009/health`

Expected: `200 OK`

---

## 1. Instructor Endpoints

Use header: `X-User-Role: instructor`

### 1.1 Generate Summary

**Method:** `POST`  
**URL:** `http://localhost:8009/api/v1/ai/instructor/modules/{module_id}/generate-summary?course_id={course_id}`

Example URL:
`http://localhost:8009/api/v1/ai/instructor/modules/65f1a2b3c4d5e6f7890abcde/generate-summary?course_id=1`

```json
{
  "source_lesson_ids": ["65f1a2b3c4d5e6f7890ab111"],
  "include_glossary": true,
  "include_key_points": true,
  "include_learning_objectives": true,
  "language": "en",
  "tone": "formal",
  "max_length_words": 500
}
```

Expected: `200 OK`, `status: "not_implemented"`

### 1.2 Generate Quiz

**Method:** `POST`  
**URL:** `http://localhost:8009/api/v1/ai/instructor/modules/{module_id}/generate-quiz?course_id={course_id}`

```json
{
  "source_lesson_ids": ["65f1a2b3c4d5e6f7890ab111"],
  "num_questions": 5,
  "difficulty": "medium",
  "question_types": ["multiple_choice", "true_false"],
  "passing_score": 70,
  "max_attempts": 3,
  "time_limit_minutes": 15,
  "language": "en"
}
```

Expected: `200 OK`, `status: "not_implemented"`

### 1.3 Generate All (Summary + Quiz)

**Method:** `POST`  
**URL:** `http://localhost:8009/api/v1/ai/instructor/modules/{module_id}/generate-all?course_id={course_id}`

```json
{
  "source_lesson_ids": ["65f1a2b3c4d5e6f7890ab111"],
  "include_glossary": true,
  "include_key_points": true,
  "include_learning_objectives": true,
  "summary_language": "en",
  "num_questions": 5,
  "difficulty": "easy",
  "question_types": ["multiple_choice", "true_false"],
  "quiz_language": "en"
}
```

Expected: `200 OK`, both nested statuses as `"not_implemented"`

### 1.4 Generation Status

**Method:** `GET`  
**URL:** `http://localhost:8009/api/v1/ai/instructor/modules/{module_id}/generation-status?course_id={course_id}`

Expected: `200 OK`, `summary_status` and `quiz_status` present

---

## 2. Tutor Endpoints

Use header: `X-User-Role: student`

### 2.1 Create Session

**Method:** `POST`  
**URL:** `http://localhost:8009/api/v1/ai/tutor/sessions`

```json
{
  "course_id": 1,
  "module_id": "65f1a2b3c4d5e6f7890abcde",
  "lesson_id": "65f1a2b3c4d5e6f7890ab111",
  "initial_message": "Can you explain this lesson in simple terms?"
}
```

Expected: `201 Created`, returns `session_id`

### 2.2 Send Message

**Method:** `POST`  
**URL:** `http://localhost:8009/api/v1/ai/tutor/sessions/{session_id}/messages`

```json
{
  "message": "What are the key takeaways?",
  "module_id": "65f1a2b3c4d5e6f7890abcde",
  "lesson_id": "65f1a2b3c4d5e6f7890ab111"
}
```

Expected: `200 OK`, `assistant_message.content` should be placeholder text

---

## 3. Index Endpoints

Use header: `X-User-Role: instructor`

### 3.1 Build Course Index

**Method:** `POST`  
**URL:** `http://localhost:8009/api/v1/ai/index/courses/{course_id}/build`

```json
{
  "force_rebuild": false
}
```

Expected: `202 Accepted`, `status: "pending"`

### 3.2 Build Module Index

**Method:** `POST`  
**URL:** `http://localhost:8009/api/v1/ai/index/modules/{module_id}/build?course_id={course_id}`

```json
{
  "force_rebuild": false
}
```

Expected: `202 Accepted`, `status: "pending"`

### 3.3 Course Index Status

**Method:** `GET`  
**URL:** `http://localhost:8009/api/v1/ai/index/courses/{course_id}/status`

Expected: `200 OK`, `status` field present

### 3.4 Module Index Status

**Method:** `GET`  
**URL:** `http://localhost:8009/api/v1/ai/index/modules/{module_id}/status?course_id={course_id}`

Expected: `200 OK`, `status` field present

---

## 4. Quick Negative Tests

### 4.1 Missing Auth Header

Call any protected route without `X-User-ID` and expect: `401`

### 4.2 Wrong Role (student on instructor route)

Use `X-User-Role: student` on an instructor/index endpoint and expect: `403`

### 4.3 Invalid Body

Send `num_questions: 0` to generate-quiz and expect: `422`

---

## 5. Suggested Postman Environment Variables

Create a Postman environment with:

- `base_url = http://localhost:8009`
- `course_id = 1`
- `module_id = 65f1a2b3c4d5e6f7890abcde`
- `lesson_id = 65f1a2b3c4d5e6f7890ab111`
- `session_id = <set from create session response>`
- `x_user_id = 1`
- `x_user_role = instructor`

Then replace URLs with variables, for example:
`{{base_url}}/api/v1/ai/index/courses/{{course_id}}/build`
