# Postman API Testing Guide: Module Quiz & Summary

## Prerequisites

- FastAPI server running (course-service)
- MongoDB running and indexes created
- PostgreSQL up and migrated
- Required headers: `X-User-ID`, `X-User-Role`

---

## 1. Module Quiz Endpoints

### Create Quiz (POST)

- **Method:** POST
- **URL:** `http://localhost:8000/courses/1/modules/mod_6a8b9c/quiz`
- **Headers:**
  - Content-Type: application/json
  - X-User-ID: 123
  - X-User-Role: instructor
- **Body (JSON):**

```
{
  "title": "Intro Quiz",
  "description": "Test your knowledge",
  "settings": {"passing_score": 70, "max_attempts": 3},
  "questions": [
    {
      "order": 1,
      "question_text": "What is Python?",
      "question_type": "multiple_choice",
      "options": [
        {"option_id": "opt1", "text": "A snake", "is_correct": false},
        {"option_id": "opt2", "text": "A programming language", "is_correct": true}
      ],
      "explanation": "Python is a programming language."
    }
  ],
  "is_published": false
}
```

### Get Quiz (GET)

- **Method:** GET
- **URL:** `http://localhost:8000/courses/1/modules/mod_6a8b9c/quiz`
- **Headers:**
  - X-User-ID: 123

### Update Quiz (PUT)

- **Method:** PUT
- **URL:** `http://localhost:8000/courses/1/modules/mod_6a8b9c/quiz`
- **Headers:**
  - Content-Type: application/json
  - X-User-ID: 123
  - X-User-Role: instructor
- **Body:** (same as create, all fields required)

### Patch Quiz (PATCH)

- **Method:** PATCH
- **URL:** `http://localhost:8000/courses/1/modules/mod_6a8b9c/quiz`
- **Headers:**
  - Content-Type: application/json
  - X-User-ID: 123
  - X-User-Role: instructor
- **Body:** (only fields to update)

### Delete Quiz (DELETE)

- **Method:** DELETE
- **URL:** `http://localhost:8000/courses/1/modules/mod_6a8b9c/quiz`
- **Headers:**
  - X-User-ID: 123
  - X-User-Role: instructor

### Publish/Unpublish Quiz (PATCH)

- **Method:** PATCH
- **URL:** `http://localhost:8000/courses/1/modules/mod_6a8b9c/quiz/publish`
- **Headers:**
  - Content-Type: application/json
  - X-User-ID: 123
  - X-User-Role: instructor
- **Body:**

```
{"is_published": true}
```

### AI Generate Quiz (POST)

- **Method:** POST
- **URL:** `http://localhost:8000/courses/1/modules/mod_6a8b9c/quiz/generate`
- **Headers:**
  - Content-Type: application/json
  - X-User-ID: 123
  - X-User-Role: instructor
- **Body:**

```
{
  "source_lesson_ids": ["les_1", "les_2"],
  "num_questions": 5,
  "passing_score": 70,
  "max_attempts": 3
}
```

---

## 2. Module Summary Endpoints

### Create Summary (POST)

- **Method:** POST
- **URL:** `http://localhost:8000/courses/1/modules/mod_6a8b9c/summary`
- **Headers:**
  - Content-Type: application/json
  - X-User-ID: 123
  - X-User-Role: instructor
- **Body:**

```
{
  "title": "Module Summary",
  "content": {
    "summary_text": "This module covers...",
    "key_points": ["Point 1", "Point 2"],
    "learning_objectives": ["Obj 1"],
    "glossary": [{"term": "Python", "definition": "A language"}]
  },
  "is_published": false
}
```

### Get Summary (GET)

- **Method:** GET
- **URL:** `http://localhost:8000/courses/1/modules/mod_6a8b9c/summary`
- **Headers:**
  - X-User-ID: 123

### Update Summary (PUT)

- **Method:** PUT
- **URL:** `http://localhost:8000/courses/1/modules/mod_6a8b9c/summary`
- **Headers:**
  - Content-Type: application/json
  - X-User-ID: 123
  - X-User-Role: instructor
- **Body:** (same as create, all fields required)

### Patch Summary (PATCH)

- **Method:** PATCH
- **URL:** `http://localhost:8000/courses/1/modules/mod_6a8b9c/summary`
- **Headers:**
  - Content-Type: application/json
  - X-User-ID: 123
  - X-User-Role: instructor
- **Body:** (only fields to update)

### Delete Summary (DELETE)

- **Method:** DELETE
- **URL:** `http://localhost:8000/courses/1/modules/mod_6a8b9c/summary`
- **Headers:**
  - X-User-ID: 123
  - X-User-Role: instructor

### Publish/Unpublish Summary (PATCH)

- **Method:** PATCH
- **URL:** `http://localhost:8000/courses/1/modules/mod_6a8b9c/summary/publish`
- **Headers:**
  - Content-Type: application/json
  - X-User-ID: 123
  - X-User-Role: instructor
- **Body:**

```
{"is_published": true}
```

### AI Generate Summary (POST)

- **Method:** POST
- **URL:** `http://localhost:8000/courses/1/modules/mod_6a8b9c/summary/generate`
- **Headers:**
  - Content-Type: application/json
  - X-User-ID: 123
  - X-User-Role: instructor
- **Body:**

```
{
  "source_lesson_ids": ["les_1", "les_2"],
  "include_glossary": true,
  "include_key_points": true,
  "include_learning_objectives": true
}
```

---

## Notes

- Replace IDs and payloads as needed.
- 201 = created, 200 = success, 204 = deleted, 404 = not found, 403 = forbidden.
- Use the same headers for all instructor actions.
- For PATCH, only include fields you want to update.
