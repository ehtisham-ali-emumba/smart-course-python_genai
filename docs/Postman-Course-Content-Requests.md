# Postman Requests: Course & Content Creation

**Base URL:** `http://localhost:8000`  
**Auth:** All requests require `Authorization: Bearer <your_jwt_token>`. Instructor routes require role `instructor` or `admin`.

**Note:** Do **not** send `module_id` or `lesson_id` in any POST or PUT request body. They are always auto-generated.

---

## 1. Create New Course

**Method:** `POST`  
**URL:** `http://localhost:8000/courses/`

**Headers:**
| Key | Value |
|-----|-------|
| Authorization | Bearer \<your_jwt_token\> |
| Content-Type | application/json |

**Body (raw JSON):**
```json
{
  "title": "Advanced Python Programming",
  "slug": "advanced-python",
  "description": "Master Python for production applications",
  "category": "Programming",
  "level": "intermediate",
  "language": "en",
  "duration_hours": 15.5,
  "price": 99.99,
  "currency": "USD",
  "max_students": 50
}
```

**Required:** `title`, `slug`  
**Slug format:** lowercase, numbers, hyphens only (e.g. `my-course-101`)

---

## 2. Create/Replace Full Course Content

**Method:** `PUT`  
**URL:** `http://localhost:8000/courses/{course_id}/content`

Replace `{course_id}` with the course ID from step 1 (e.g. `5`).

**Body (raw JSON) — no `module_id` or `lesson_id`:**
```json
{
  "modules": [
    {
      "title": "Getting Started",
      "description": "Introduction to the course",
      "order": 1,
      "is_published": true,
      "lessons": [
        {
          "title": "Welcome Video",
          "type": "video",
          "content": "Introduction video content",
          "duration_minutes": 10,
          "order": 1,
          "is_preview": true,
          "resources": []
        },
        {
          "title": "Course Overview",
          "type": "text",
          "content": "Detailed syllabus",
          "duration_minutes": 5,
          "order": 2,
          "is_preview": false,
          "resources": []
        }
      ]
    }
  ]
}
```

**Lesson `type`:** Must be one of `video`, `text`, `quiz`, `assignment`

---

## 3. Add Module One-by-One

**Method:** `POST`  
**URL:** `http://localhost:8000/courses/{course_id}/content/modules`

**Body — no `module_id`:**
```json
{
  "title": "Module 2: Advanced Topics",
  "description": "Dive deeper",
  "order": 2,
  "is_published": true,
  "lessons": []
}
```

The response returns the auto-generated `module_id` (use it in the URL for adding lessons).

---

## 4. Add Lesson to Module

**Method:** `POST`  
**URL:** `http://localhost:8000/courses/{course_id}/content/modules/{module_id}/lessons`

Use `module_id` from the response of step 3 in the URL path.

**Body — no `lesson_id`:**
```json
{
  "title": "New Lesson",
  "type": "text",
  "content": "Lesson content here",
  "duration_minutes": 15,
  "order": 1,
  "is_preview": false
}
```

---

## 5. Add Media Resource to Lesson

**Method:** `POST`  
**URL:** `http://localhost:8000/courses/{course_id}/content/modules/{module_id}/lessons/{lesson_id}/resources`

**Body — no `resource_id`:**
```json
{
  "name": "Python Cheat Sheet",
  "url": "https://example.com/cheatsheet.pdf",
  "type": "pdf"
}
```

**Resource `type`:** One of `video`, `pdf`, `audio`, `image`, `link`

---

## Summary: IDs in POST/PUT

| Request | IDs in body? | IDs in URL? |
|---------|--------------|-------------|
| PUT content | Never — omit `module_id`, `lesson_id`, `resource_id` | `course_id` only |
| POST module | Never | `course_id` only |
| POST lesson | Never | `course_id`, `module_id` |
| POST resource | Never | `course_id`, `module_id`, `lesson_id` |

IDs are always auto-generated and returned in responses. Use them only in the URL for subsequent requests (e.g. add lesson) or for PATCH/DELETE.
