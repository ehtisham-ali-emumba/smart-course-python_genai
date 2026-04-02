# Analytics Service — How to Run & Use

## 1. Running the Service

### Prerequisites

Before starting the analytics service, the following must be running:
- PostgreSQL (with `analytics_db` created — handled by `postgres-init-analytics` in docker-compose)
- Redis
- Kafka + Schema Registry
- `kafka-init` job (creates Kafka topics)

### Start Everything with Docker Compose

```bash
# From project root
docker compose up -d

# Start only analytics service (and its deps)
docker compose up -d analytics-service

# View logs
docker compose logs -f analytics-service

# Rebuild after code changes
docker compose up -d --build analytics-service
```

### Service Port

The analytics service runs on **port 8007** inside Docker.

Via the Nginx API gateway (if running): requests go through `/analytics/` prefix.

### Health Check

```bash
curl http://localhost:8007/health
```

Expected response:
```json
{"status": "ok", "redis": "ok"}
```

### Prometheus Metrics

```bash
curl http://localhost:8007/metrics
```

---

## 2. Environment Variables

The service reads from two `.env` files (loaded automatically by docker-compose):
- `./.env` (root-level, shared secrets like REDIS_PASSWORD)
- `./services/analytics-service/.env`

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL connection string for `analytics_db` | `postgresql://smartcourse:smartcourse_secret@postgres:5432/analytics_db` |
| `REDIS_URL` | Redis connection string (DB index 3) | `redis://:smartcourse_secret@redis:6379/3` |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka broker address | `kafka:29092` |
| `SCHEMA_REGISTRY_URL` | Confluent Schema Registry | `http://schema-registry:8081` |

---

## 3. Authentication Headers

All endpoints require these headers (injected by Nginx auth sidecar in production, set manually when testing directly):

| Header | Required | Description |
|---|---|---|
| `X-User-ID` | Yes | UUID of the authenticated user |
| `X-User-Role` | Yes | `admin`, `instructor`, or `student` |
| `X-Profile-ID` | Sometimes | UUID of the user's profile (needed for self-access checks) |

---

## 4. API Endpoints

Base URL (direct): `http://localhost:8007`  
Base URL (via gateway): `http://localhost/analytics`

### 4.1 Platform Endpoints — Admin Only

---

#### GET `/analytics/platform/overview`

Returns current platform-wide totals.

**Who can call:** Admin only

**Headers required:**
```
X-User-ID: <uuid>
X-User-Role: admin
```

**Example:**
```bash
curl http://localhost:8007/analytics/platform/overview \
  -H "X-User-ID: 00000000-0000-0000-0000-000000000001" \
  -H "X-User-Role: admin"
```

**Response:**
```json
{
  "total_students": 120,
  "total_instructors": 15,
  "total_courses_published": 42,
  "total_enrollments": 980,
  "total_completions": 310,
  "avg_completion_rate": 31.63,
  "avg_courses_per_student": 8.17,
  "total_certificates_issued": 295
}
```

**Cache:** 5 minutes (`analytics:platform:overview`)

---

#### GET `/analytics/platform/trends`

Returns daily enrollment trend data over a date range.

**Who can call:** Admin only

**Query Params:**
| Param | Type | Default | Description |
|---|---|---|---|
| `period` | string | `daily` | (not yet used — always returns daily data) |
| `from_date` | date (YYYY-MM-DD) | 30 days before `to_date` | Start of range |
| `to_date` | date (YYYY-MM-DD) | today | End of range |

**Example:**
```bash
curl "http://localhost:8007/analytics/platform/trends?from_date=2026-03-01&to_date=2026-04-01" \
  -H "X-User-ID: 00000000-0000-0000-0000-000000000001" \
  -H "X-User-Role: admin"
```

**Response:**
```json
[
  {"date": "2026-03-01", "new_enrollments": 14, "new_completions": 3, "new_drops": 1},
  {"date": "2026-03-02", "new_enrollments": 22, "new_completions": 5, "new_drops": 0}
]
```

---

#### GET `/analytics/platform/ai-usage`

Returns daily AI assistant usage across the platform.

**Who can call:** Admin only

**Query Params:**
| Param | Type | Default | Description |
|---|---|---|---|
| `from_date` | date | 30 days ago | Start of range |
| `to_date` | date | today | End of range |

**Example:**
```bash
curl "http://localhost:8007/analytics/platform/ai-usage?from_date=2026-03-01&to_date=2026-04-01" \
  -H "X-User-ID: 00000000-0000-0000-0000-000000000001" \
  -H "X-User-Role: admin"
```

**Response:**
```json
[
  {"date": "2026-03-01", "tutor_questions": 47, "instructor_requests": 12, "total": 59},
  {"date": "2026-03-02", "tutor_questions": 63, "instructor_requests": 8, "total": 71}
]
```

---

### 4.2 Course Endpoints — Admin or Instructor

---

#### GET `/analytics/courses/popular`

Returns top courses sorted by enrollment count or completion rate.

**Who can call:** Admin, Instructor

**Query Params:**
| Param | Type | Default | Options |
|---|---|---|---|
| `limit` | int | `10` | Any positive int |
| `sort_by` | string | `enrollments` | `enrollments`, `completion_rate` |

**Example:**
```bash
curl "http://localhost:8007/analytics/courses/popular?limit=5&sort_by=completion_rate" \
  -H "X-User-ID: 00000000-0000-0000-0000-000000000001" \
  -H "X-User-Role: admin"
```

**Response:**
```json
[
  {
    "course_id": "aaa-bbb-ccc",
    "title": "Python Fundamentals",
    "total_enrollments": 320,
    "completion_rate": 78.5,
    "avg_progress": 91.2
  }
]
```

**Cache:** 5 minutes (`analytics:courses:popular:{sort_by}:{limit}`)

---

#### GET `/analytics/courses/{course_id}`

Returns full analytics for a specific course.

**Who can call:** Admin, Instructor (any instructor can view any course — no ownership check implemented yet)

**Path Params:**
| Param | Type | Description |
|---|---|---|
| `course_id` | UUID | Course identifier |

**Example:**
```bash
curl "http://localhost:8007/analytics/courses/aaa-bbb-ccc-ddd" \
  -H "X-User-ID: 00000000-0000-0000-0000-000000000001" \
  -H "X-User-Role: instructor" \
  -H "X-Profile-ID: 11111111-0000-0000-0000-000000000001"
```

**Response:**
```json
{
  "course_id": "aaa-bbb-ccc-ddd",
  "title": "Python Fundamentals",
  "total_enrollments": 320,
  "active_enrollments": 210,
  "completed_enrollments": 95,
  "dropped_enrollments": 15,
  "completion_rate": 29.69,
  "avg_progress_percentage": 67.4,
  "avg_time_to_complete_hours": 12.5,
  "avg_quiz_score": 82.3,
  "total_quiz_attempts": 440,
  "ai_questions_asked": 1230,
  "enrollment_trend": [
    {"date": "2026-03-01", "new_enrollments": 14, "new_completions": 3}
  ]
}
```

**Error:** 404 if course not found

**Cache:** 2 minutes (`analytics:course:{course_id}`)

---

#### GET `/analytics/courses/{course_id}/trends`

Returns enrollment trend for a specific course over a date range.

**Who can call:** Admin, Instructor

**Path Params:** `course_id` (UUID)

**Query Params:**
| Param | Type | Default | Description |
|---|---|---|---|
| `period` | string | `daily` | (not yet used) |
| `from_date` | date | 30 days before `to_date` | Start |
| `to_date` | date | today | End |

**Example:**
```bash
curl "http://localhost:8007/analytics/courses/aaa-bbb-ccc/trends?from_date=2026-03-01&to_date=2026-04-01" \
  -H "X-User-ID: 00000000-0000-0000-0000-000000000001" \
  -H "X-User-Role: admin"
```

**Response:**
```json
[
  {"date": "2026-03-01", "new_enrollments": 5, "new_completions": 1},
  {"date": "2026-03-02", "new_enrollments": 9, "new_completions": 2}
]
```

---

### 4.3 Instructor Endpoints

---

#### GET `/analytics/instructors/{instructor_id}`

Returns analytics for a specific instructor.

**Who can call:**
- **Admin:** Any instructor ID
- **Instructor:** Only own ID (X-Profile-ID must match instructor_id)

**Path Params:** `instructor_id` (UUID)

**Example (admin):**
```bash
curl "http://localhost:8007/analytics/instructors/11111111-0000-0000-0000-000000000001" \
  -H "X-User-ID: 00000000-0000-0000-0000-000000000001" \
  -H "X-User-Role: admin"
```

**Example (instructor viewing self):**
```bash
curl "http://localhost:8007/analytics/instructors/11111111-0000-0000-0000-000000000001" \
  -H "X-User-ID: 00000000-0000-0000-0000-000000000002" \
  -H "X-User-Role: instructor" \
  -H "X-Profile-ID: 11111111-0000-0000-0000-000000000001"
```

**Response:**
```json
{
  "instructor_id": "11111111-0000-0000-0000-000000000001",
  "total_courses": 8,
  "published_courses": 6,
  "total_students": 540,
  "total_enrollments": 620,
  "total_completions": 210,
  "avg_completion_rate": 33.87,
  "avg_quiz_score": 79.4,
  "courses": [
    {
      "course_id": "aaa-bbb-ccc",
      "title": "Python Fundamentals",
      "enrollments": 320,
      "completion_rate": 29.69
    }
  ]
}
```

**Error:** 404 if instructor not found, 403 if instructor tries to view another instructor

**Cache:** 2 minutes (`analytics:instructor:{instructor_id}`)

---

#### GET `/analytics/instructors/leaderboard`

Returns top instructors ranked by student count or completion rate.

**Who can call:** Admin, Instructor

**Query Params:**
| Param | Type | Default | Options |
|---|---|---|---|
| `limit` | int | `10` | Any positive int |
| `sort_by` | string | `students` | `students`, `completion_rate` |

**Example:**
```bash
curl "http://localhost:8007/analytics/instructors/leaderboard?limit=5&sort_by=students" \
  -H "X-User-ID: 00000000-0000-0000-0000-000000000001" \
  -H "X-User-Role: admin"
```

**Response:**
```json
[
  {
    "instructor_id": "11111111-0000-0000-0000-000000000001",
    "total_students": 540,
    "avg_completion_rate": 33.87
  }
]
```

---

### 4.4 Student Endpoints

---

#### GET `/analytics/students/{student_id}`

Returns analytics for a specific student.

**Who can call:**
- **Admin:** Any student ID
- **Student:** Only own ID (X-Profile-ID must match student_id)

**Path Params:** `student_id` (UUID)

**Example (admin):**
```bash
curl "http://localhost:8007/analytics/students/22222222-0000-0000-0000-000000000001" \
  -H "X-User-ID: 00000000-0000-0000-0000-000000000001" \
  -H "X-User-Role: admin"
```

**Example (student viewing self):**
```bash
curl "http://localhost:8007/analytics/students/22222222-0000-0000-0000-000000000001" \
  -H "X-User-ID: 00000000-0000-0000-0000-000000000003" \
  -H "X-User-Role: student" \
  -H "X-Profile-ID: 22222222-0000-0000-0000-000000000001"
```

**Response:**
```json
{
  "student_id": "22222222-0000-0000-0000-000000000001",
  "total_enrollments": 5,
  "active_enrollments": 3,
  "completed_courses": 2,
  "dropped_courses": 0,
  "avg_progress": 61.4,
  "avg_quiz_score": 85.2,
  "total_certificates": 2,
  "last_active_at": "2026-04-01T15:30:00Z"
}
```

**Error:** 404 if student not found, 403 if student tries to view another student

**Cache:** 2 minutes (`analytics:student:{student_id}`)

---

#### GET `/analytics/students/{student_id}/courses`

Returns per-course analytics for a student.

**Who can call:** Admin, or the student themselves

**Note:** Currently returns an empty list `[]` — not yet fully implemented.

**Example:**
```bash
curl "http://localhost:8007/analytics/students/22222222-0000-0000-0000-000000000001/courses" \
  -H "X-User-ID: 00000000-0000-0000-0000-000000000003" \
  -H "X-User-Role: student" \
  -H "X-Profile-ID: 22222222-0000-0000-0000-000000000001"
```

---

## 5. Role × Endpoint Access Matrix

| Endpoint | Admin | Instructor | Student |
|---|---|---|---|
| `GET /platform/overview` | ✅ | ❌ | ❌ |
| `GET /platform/trends` | ✅ | ❌ | ❌ |
| `GET /platform/ai-usage` | ✅ | ❌ | ❌ |
| `GET /courses/popular` | ✅ | ✅ | ❌ |
| `GET /courses/{course_id}` | ✅ | ✅ | ❌ |
| `GET /courses/{course_id}/trends` | ✅ | ✅ | ❌ |
| `GET /instructors/leaderboard` | ✅ | ✅ | ❌ |
| `GET /instructors/{instructor_id}` | ✅ (any) | ✅ (own only) | ❌ |
| `GET /students/{student_id}` | ✅ (any) | ❌ | ✅ (own only) |
| `GET /students/{student_id}/courses` | ✅ (any) | ❌ | ✅ (own only) |

---

## 6. Kafka Events the Service Listens To

Data in the analytics service is populated entirely from Kafka events. The service starts empty and fills up as events flow in from other services.

| Topic | Event Type | What Gets Updated |
|---|---|---|
| `user.events` | `user.registered` | student_metrics or instructor_metrics row created |
| `course.events` | `course.published` | course_metrics row created, instructor published_courses++ |
| `enrollment.events` | `enrollment.created` | enrollment counters on course, student, instructor, daily table |
| `enrollment.events` | `enrollment.completed` | completion counters and rates updated |
| `enrollment.events` | `enrollment.dropped` | drop counters updated |
| `progress.events` | `progress.updated` | avg_progress updated for course and student |
| `ai.events` | `ai.question.asked` | ai_usage_daily tutor_questions++ |
| `ai.events` | `ai.content.generated` | ai_usage_daily instructor_requests++ |
| `certificate.events` | `certificate.issued` | student total_certificates++ |

**If data looks empty:** Check that other services are running and publishing events. You can verify by checking Kafka topics.

---

## 7. Daily Snapshot

Every day at 00:05 UTC, the service automatically builds a `platform_snapshots` row that aggregates current state from all metric tables. This powers historical trend data for the platform overview.

No manual action needed — it runs automatically in the background as part of the app lifespan.

---

## 8. Database Migrations

Migrations run automatically on container startup (`alembic upgrade head`). To run manually:

```bash
docker compose exec analytics-service alembic upgrade head
```

To check current migration state:

```bash
docker compose exec analytics-service alembic current
```

---

## 9. Useful Docker Commands

```bash
# View running containers
docker compose ps

# Restart just analytics service
docker compose restart analytics-service

# Shell into the container
docker compose exec analytics-service bash

# Check DB tables exist
docker compose exec postgres psql -U smartcourse -d analytics_db -c "\dt"

# View Redis cached keys
docker compose exec redis redis-cli -a smartcourse_secret -n 3 keys "analytics:*"

# Clear all analytics cache
docker compose exec redis redis-cli -a smartcourse_secret -n 3 flushdb
```

---

## 10. Interactive API Docs

When the service is running, FastAPI's built-in docs are available:

- Swagger UI: `http://localhost:8007/docs`
- ReDoc: `http://localhost:8007/redoc`

Note: You'll need to manually add the auth headers (`X-User-ID`, `X-User-Role`, `X-Profile-ID`) via the "Authorize" button or per-request header fields in Swagger.
