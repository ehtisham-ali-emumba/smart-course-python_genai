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

Progress is tracked per lesson/quiz/summary with partial progress (0–100%). You must be enrolled and have an active enrollment to record progress.

**`enrollment_id`:** From `POST /course/enrollments/` response (`id`) or `GET /course/enrollments/my-enrollments` (each item has `id`).

**`item_id`:** MongoDB ObjectId from course content (e.g. from `GET /courses/{course_id}/content` — each lesson has `lesson_id`, quiz has `quiz_id`, summary has `summary_id`).

When `progress_percentage` reaches 100, the item is marked completed. When ALL items reach 100%, the enrollment is auto-completed and a certificate is auto-issued.

---

### 1. Update Progress (Mark Lesson/Quiz/Summary)

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
  "enrollment_id": 12,
  "item_type": "lesson",
  "item_id": "674a1b2c3d4e5f6a7b8c9d0e",
  "progress_percentage": 100
}
```

**Required:** `enrollment_id`, `item_type`, `item_id`, `progress_percentage`  
**`item_type`:** One of `lesson`, `quiz`, `summary`  
**`item_id`:** MongoDB ObjectId string of the lesson/quiz/summary (from course content)  
**`progress_percentage`:** 0–100 (Decimal). At 100, item is marked completed (`completed_at` set).

**Partial progress example** (e.g. watched 50% of a video):
```json
{
  "enrollment_id": 12,
  "item_type": "lesson",
  "item_id": "674a1b2c3d4e5f6a7b8c9d0e",
  "progress_percentage": 50
}
```

---

### 2. Get Progress by Enrollment ID

**Method:** `GET`  
**URL:** `http://localhost:8000/course/progress/enrollment/{enrollment_id}`

**Headers:**
| Key | Value |
|-----|-------|
| Authorization | Bearer \<your_jwt_token\> |

**Example:** `http://localhost:8000/course/progress/enrollment/12`

**Requires:** Enrollment must belong to you and be active/completed. Returns **404** if not found or not yours.

**Response includes:**
- `course_id`, `user_id`, `enrollment_id`
- `total_lessons`, `completed_lessons`, `progress_percentage`
- `module_progress` — per-module breakdown with lesson details
- `has_certificate`, `is_complete`

---

### 3. Get Progress by Course ID

**Method:** `GET`  
**URL:** `http://localhost:8000/course/progress/course/{course_id}`

**Headers:**
| Key | Value |
|-----|-------|
| Authorization | Bearer \<your_jwt_token\> |

**Example:** `http://localhost:8000/course/progress/course/4`

**Requires:** You must be enrolled in the course with an active/completed enrollment. Returns **404** with "User is not enrolled in this course" or "Enrollment is not active (dropped or suspended)" if not eligible.

**Response:** Same structure as "Get Progress by Enrollment ID".

---

## Flow Example

1. **Enroll:** `POST /course/enrollments/` with `{"course_id": 4}` → response includes `id` (enrollment_id)
2. **Get content:** `GET /courses/4/content` → copy `lesson_id`, `quiz_id`, `summary_id` for each item
3. **Update progress:** `POST /course/progress` with:
   ```json
   {
     "enrollment_id": 12,
     "item_type": "lesson",
     "item_id": "<lesson_id>",
     "progress_percentage": 100
   }
   ```
4. **Check progress:** `GET /course/progress/enrollment/12` or `GET /course/progress/course/4`
