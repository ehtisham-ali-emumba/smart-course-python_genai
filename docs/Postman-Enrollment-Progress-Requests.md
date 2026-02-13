# Postman Requests: Enrollment & Progress

**Base URL:** `http://localhost:8000`  
**Auth:** All requests require `Authorization: Bearer <your_jwt_token>`.

---

## Enrollment

### 1. Enroll in a Course

**Method:** `POST`  
**URL:** `http://localhost:8000/course/enrollments/`

**Headers:**
| Key | Value |
|-----|-------|
| Authorization | Bearer \<your_jwt_token\> |
| Content-Type | application/json |

**Body (raw JSON):**
```json
{
  "course_id": 4,
  "payment_amount": 49.99,
  "enrollment_source": "web"
}
```

**Required:** `course_id`  
**Optional:** `payment_amount`, `enrollment_source` (e.g. `"web"`, `"mobile"`, `"api"`)

---

### 2. List My Enrollments

**Method:** `GET`  
**URL:** `http://localhost:8000/course/enrollments/my-enrollments?skip=0&limit=20`

**Headers:**
| Key | Value |
|-----|-------|
| Authorization | Bearer \<your_jwt_token\> |

**Query params (optional):** `skip`, `limit`

---

### 3. Get Single Enrollment

**Method:** `GET`  
**URL:** `http://localhost:8000/course/enrollments/{enrollment_id}`

**Headers:**
| Key | Value |
|-----|-------|
| Authorization | Bearer \<your_jwt_token\> |

Must be the enrolled student (matches `X-User-ID` from JWT).

---

### 4. Drop Enrollment (withdraw from course)

**Method:** `PATCH`  
**URL:** `http://localhost:8000/course/enrollments/{enrollment_id}/drop`

**Headers:**
| Key | Value |
|-----|-------|
| Authorization | Bearer \<your_jwt_token\> |

No body required.

**What it does:** Withdraws you from the course. Sets enrollment status to `dropped` and records `dropped_at`. Your progress records stay in the database (for analytics), but you're no longer considered enrolled. This is **not** "drop progress" — there is no endpoint to delete or reset progress.

---

### 5. Undrop Enrollment (re-enroll after dropping)

**Method:** `PATCH`  
**URL:** `http://localhost:8000/course/enrollments/{enrollment_id}/undrop`

**Headers:**
| Key | Value |
|-----|-------|
| Authorization | Bearer \<your_jwt_token\> |

No body required.

**What it does:** Reactivates a dropped enrollment. Sets status back to `active` and clears `dropped_at`. Only works when enrollment is `dropped`. Fails if course is no longer published or enrollment limit reached.

---

## Progress

Progress is tracked per lesson/quiz/summary. You must be enrolled in the course to record progress.

**`item_id`:** Use the ObjectId string from the course content (e.g. from `GET /courses/{course_id}/content` — each lesson has a `lesson_id`).

### 1. Mark Lesson as Completed

**Method:** `POST`  
**URL:** `http://localhost:8000/course/progress`

**Headers:**
| Key | Value |
|-----|-------|
| Authorization | Bearer \<your_jwt_token\> |
| Content-Type | application/json |

**Body (raw JSON):**
```json
{
  "course_id": 4,
  "item_type": "lesson",
  "item_id": "674a1b2c3d4e5f6a7b8c9d0e"
}
```

**Required:** `course_id`, `item_type`, `item_id`  
**`item_type`:** One of `lesson`, `quiz`, `summary`  
**`item_id`:** The ObjectId string of the lesson/quiz/summary (from course content response)

---

### 2. Get Course Progress Summary

**Method:** `GET`  
**URL:** `http://localhost:8000/course/progress/{course_id}`

**Headers:**
| Key | Value |
|-----|-------|
| Authorization | Bearer \<your_jwt_token\> |

**Example:** `http://localhost:8000/course/progress/4`

**Requires:** You must be enrolled in the course. Returns **404** with message "User is not enrolled in this course" or "Enrollment is not active (dropped or suspended)" if not enrolled or enrollment is dropped.

**Response includes:**
- `total_items` — count of active lessons/quizzes/summaries in the course
- `completed_items` — count you've completed
- `completion_percentage`
- `completed_lessons` — array of lesson IDs you've finished
- `completed_quizzes`, `completed_summaries`
- `has_certificate`, `is_complete`

---

## Flow Example

1. **Enroll:** `POST /course/enrollments/` with `{"course_id": 4}`
2. **Get content:** `GET /courses/4/content` → copy `lesson_id` from each lesson in the response
3. **Mark complete:** `POST /course/progress` with `{"course_id": 4, "item_type": "lesson", "item_id": "<lesson_id>"}`
4. **Check progress:** `GET /course/progress/4`
