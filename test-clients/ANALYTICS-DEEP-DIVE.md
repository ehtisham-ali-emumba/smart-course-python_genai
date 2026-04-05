# SmartCourse Analytics — Complete Deep Dive

Everything you need to understand the analytics service and the dashboard HTML file.

---

## Table of Contents

1. [Big Picture — How the Analytics Service Works](#1-big-picture)
2. [Kafka Events — What Triggers Analytics](#2-kafka-events)
3. [PostgreSQL Database — What Gets Stored](#3-postgresql-database)
4. [Redis Cache — How Caching Works](#4-redis-cache)
5. [API Endpoints — What You Can Query](#5-api-endpoints)
6. [Auth & Gateway — How Requests Are Secured](#6-auth--gateway)
7. [Dashboard HTML File — How It Works](#7-dashboard-html-file)
8. [Full Data Flow — End to End](#8-full-data-flow-end-to-end)

---

## 1. Big Picture

The analytics service is a **passive observer**. It never receives HTTP requests from other services. Instead it sits and listens to Kafka and builds up aggregated metrics in its own PostgreSQL database.

```
Other Services → Kafka Topics → Analytics Consumers → PostgreSQL
                                                     ↓
                                               HTTP Clients ← FastAPI API
```

There are **two halves** to this service:

| Half | What it does |
|---|---|
| **Consumers** (background) | Listen to Kafka, update DB counters when events arrive |
| **API** (HTTP) | Read from DB/Redis and return analytics to dashboards/clients |

These two halves run in the **same process** (started by `main.py`) but work independently.

---

## 2. Kafka Events

The service subscribes to **6 Kafka topics** and handles specific event types from each.

### Topic: USER

| Event | What analytics does |
|---|---|
| `user.registered` | Creates a new row in `student_metrics` or `instructor_metrics` depending on `role` |

### Topic: COURSE

| Event | What analytics does |
|---|---|
| `course.published` | Creates a row in `course_metrics`, sets `published_at` timestamp |
| `course.updated` | Updates `title`, `category` on the `course_metrics` row |

### Topic: ENROLLMENT

| Event | What analytics does |
|---|---|
| `enrollment.created` | +1 `total_enrollments` and `active_enrollments` on course, student, instructor; +1 `new_enrollments` on today's `enrollment_daily` row |
| `enrollment.completed` | active→completed counters; recalculates `completion_rate`; +1 `new_completions` daily |
| `enrollment.dropped` | active→dropped counters; +1 `new_drops` daily |

### Topic: PROGRESS

| Event | What analytics does |
|---|---|
| `progress.updated` | Updates `avg_progress_percentage` on course and student |
| `quiz.graded` | Running average of `avg_quiz_score`; increments `total_quiz_attempts` |

### Topic: AI

| Event | What analytics does |
|---|---|
| `ai.question.asked` | +1 `tutor_questions` + `total_questions` on `ai_usage_daily`; +1 `ai_questions_asked` on course |
| `ai.content.generated` | +1 `instructor_requests` + `total_questions` on `ai_usage_daily` |

### Topic: CERTIFICATE

| Event | What analytics does |
|---|---|
| `certificate.issued` | +1 `total_certificates` on student |

### Key Design Pattern — Idempotency

Every event is first checked against the `processed_events` table using its `event_id`. If it was already processed, it is silently skipped. This means the same Kafka message can be replayed safely without double-counting.

```python
# base_consumer.py — this runs on every single event before anything else
marked = await processed_repo.mark_processed(event_id, topic, event_type)
if not marked:
    return  # already seen this event — skip it
```

After processing, the consumer **invalidates Redis cache** for the affected patterns so the next API read gets fresh data.

---

## 3. PostgreSQL Database

The analytics DB has **5 core tables** plus the idempotency table. These are **pre-aggregated metrics** — not raw event logs.

### `course_metrics` — One row per course

| Column | Type | What it tracks |
|---|---|---|
| `course_id` | UUID | Foreign key to the courses service |
| `instructor_id` | UUID | Which instructor owns this course |
| `title` | string | Course name (synced from events) |
| `category` | string | Course category |
| `total_enrollments` | int | All-time enrollments |
| `active_enrollments` | int | Currently enrolled (not completed/dropped) |
| `completed_enrollments` | int | How many finished |
| `dropped_enrollments` | int | How many dropped out |
| `completion_rate` | decimal | `completed / total × 100` |
| `avg_progress_percentage` | decimal | Average student progress % |
| `avg_quiz_score` | decimal | Running average quiz score |
| `total_quiz_attempts` | int | Total quiz submissions |
| `ai_questions_asked` | int | AI tutor questions asked in this course |
| `published_at` | datetime | When the course was published |
| `last_enrollment_at` | datetime | When someone last enrolled |

### `student_metrics` — One row per student

| Column | Type | What it tracks |
|---|---|---|
| `student_id` | UUID | The student |
| `total_enrollments` | int | All courses ever enrolled in |
| `active_enrollments` | int | Currently active enrollments |
| `completed_courses` | int | Finished courses |
| `dropped_courses` | int | Dropped courses |
| `avg_progress` | decimal | Average progress across all courses |
| `avg_quiz_score` | decimal | Average quiz performance |
| `total_certificates` | int | Certificates earned |
| `last_active_at` | datetime | Last time student had any activity |

### `instructor_metrics` — One row per instructor

| Column | Type | What it tracks |
|---|---|---|
| `instructor_id` | UUID | The instructor |
| `total_courses` | int | All courses created |
| `published_courses` | int | Currently published courses |
| `total_students` | int | Total unique students across all courses |
| `total_enrollments` | int | All enrollments across their courses |
| `total_completions` | int | All completions across their courses |
| `avg_completion_rate` | decimal | Average completion rate |
| `avg_quiz_score` | decimal | Average quiz score across their courses |

### `enrollment_daily` — One row per day (+ per day per course)

This table stores **time-series data** — it's how the trend charts work.

| Column | What it tracks |
|---|---|
| `date` | The calendar date |
| `course_id` | NULL = platform-wide; UUID = specific course |
| `new_enrollments` | Enrollments that day |
| `new_completions` | Completions that day |
| `new_drops` | Drops that day |

When `course_id` is NULL, the row is a **platform-wide** daily total.
When `course_id` is a UUID, the row is for that specific course only.

### `ai_usage_daily` — One row per day (+ per day per course)

Same pattern as `enrollment_daily` but for AI usage.

| Column | What it tracks |
|---|---|
| `date` | Calendar date |
| `course_id` | NULL = platform-wide; UUID = specific course |
| `tutor_questions` | Student → AI tutor questions that day |
| `instructor_requests` | Instructor → AI content generation requests that day |
| `total_questions` | Sum of both |

### `processed_events` — Idempotency table

Stores `(event_id, topic, event_type)` for every event that has been handled. Prevents double-processing if Kafka delivers a message twice.

---

## 4. Redis Cache

Redis is used to avoid hitting PostgreSQL on every API request.

### How it works

```python
# get_or_set_json in core/cache.py
cached = await redis.get(key)
if cached:
    return json.loads(cached)   # Cache HIT — instant response

data = await db_query()         # Cache MISS — hit the database
await redis.setex(key, ttl, json.dumps(data))  # Store it
return data
```

### Cache keys and TTLs

| Key pattern | TTL | Used by |
|---|---|---|
| `analytics:platform:overview` | 5 min | Platform overview endpoint |
| `analytics:courses:popular:{sort_by}:{limit}` | 5 min | Popular courses |
| `analytics:course:{course_id}` | 2 min | Course details |
| `analytics:instructor:{instructor_id}` | 2 min | Instructor details |
| `analytics:student:{student_id}` | 2 min | Student details |

### Cache invalidation

When any Kafka event is processed, the consumer **deletes all analytics cache keys** using pattern-based deletion. This ensures that after a new enrollment, the next request gets fresh counts — not 5-minute-old data.

```python
# These patterns are deleted after every event
CACHE_PATTERNS = [
    "analytics:courses:popular:*",
    "analytics:course:*",
    "analytics:instructor:*",
    "analytics:student:*",
]
```

Note: `analytics:platform:overview` is NOT invalidated on every event — it's a 5-minute TTL cache only, so it may be slightly stale.

---

## 5. API Endpoints

All endpoints sit behind the Nginx gateway at `http://localhost:8000`. The analytics service itself runs on port `8007` internally.

### Platform Endpoints

#### `GET /analytics/platform/overview`
**Auth:** Instructor only

Returns a single snapshot of the entire platform.

```json
{
  "total_students": 150,
  "total_instructors": 12,
  "total_courses_published": 35,
  "total_enrollments": 820,
  "total_completions": 340,
  "avg_completion_rate": "41.46",
  "avg_courses_per_student": "0.23",
  "total_certificates_issued": 0
}
```

#### `GET /analytics/platform/trends?from_date=2026-03-01&to_date=2026-04-05`
**Auth:** Instructor only | **Default range:** last 30 days

Returns daily enrollment activity as an array. Used to draw the trend line chart.

```json
[
  { "date": "2026-04-01", "new_enrollments": 12, "new_completions": 3, "new_drops": 1 },
  { "date": "2026-04-02", "new_enrollments": 8, "new_completions": 5, "new_drops": 0 }
]
```

#### `GET /analytics/platform/ai-usage?from_date=2026-03-01&to_date=2026-04-05`
**Auth:** Instructor only | **Default range:** last 30 days

Returns daily AI usage totals. Used for the AI Usage tab charts.

```json
[
  { "date": "2026-04-01", "tutor_questions": 45, "instructor_requests": 12, "total": 57 },
  { "date": "2026-04-02", "tutor_questions": 38, "instructor_requests": 8, "total": 46 }
]
```

---

### Course Endpoints

#### `GET /analytics/courses/popular?sort_by=enrollments&limit=10`
**Auth:** Instructor only

Returns top N courses sorted by either `enrollments` or `completion_rate`.

```json
[
  {
    "course_id": "abc-123",
    "title": "Python for Beginners",
    "total_enrollments": 340,
    "completed_enrollments": 120,
    "completion_rate": "35.29",
    "avg_progress_percentage": "62.10"
  }
]
```

#### `GET /analytics/courses/{course_id}`
**Auth:** Instructor only

Full metrics for a single course.

#### `GET /analytics/courses/{course_id}/trends?from_date=...&to_date=...`
**Auth:** Instructor only

Daily enrollment trends for a specific course (same shape as platform trends but course-scoped).

---

### Instructor Endpoints

#### `GET /analytics/instructors/leaderboard?sort_by=students&limit=10`
**Auth:** Instructor only

Returns top instructors ranked by `students`, `completions`, or `avg_completion_rate`.

#### `GET /analytics/instructors/{instructor_id}`
**Auth:** Instructor only, OR the instructor themselves

Full metrics for a single instructor.

---

### Student Endpoints

#### `GET /analytics/students/{student_id}`
**Auth:** Instructor, OR the student themselves

Full metrics for a single student.

```json
{
  "student_id": "xyz-456",
  "total_enrollments": 5,
  "active_enrollments": 2,
  "completed_courses": 2,
  "dropped_courses": 1,
  "avg_progress": "67.50",
  "avg_quiz_score": "84.00",
  "total_certificates": 2,
  "last_active_at": "2026-04-04T14:22:00Z"
}
```

#### `GET /analytics/students/{student_id}/courses`
**Auth:** Instructor, OR the student themselves

Currently returns an empty array `[]` — placeholder for future per-course student breakdown.

---

## 6. Auth & Gateway

### How JWT auth works

The Nginx API gateway sits in front of all services on port 8000. Every request goes through an **auth sidecar** (port 8010) before reaching the analytics service.

```
Browser → http://localhost:8000/analytics/...
           ↓
         Nginx (port 8000)
           ↓
         Auth sidecar (port 8010) — validates your JWT
           ↓ (if valid)
         Injects headers: X-User-ID, X-User-Role, X-Profile-ID
           ↓
         Analytics Service (port 8007) — reads X-User-Role to check permissions
```

### What "instructor only" means in code

```python
# api/dependencies.py
def require_instructor(request: Request):
    role = request.headers.get("X-User-Role", "")
    if role != "instructor":
        raise HTTPException(status_code=403)
```

The analytics service **never validates the JWT directly** — it just trusts the `X-User-Role` header that Nginx injected. This is safe because Nginx already validated the token.

### How to get a token for the dashboard

1. Login as an instructor through the auth endpoint
2. Copy the `access_token` from the response
3. In the dashboard, click **Config** → paste the token → Save

---

## 7. Dashboard HTML File

File: `test-clients/analytics-dashboard.html`

This is a **single self-contained HTML file** — no build step, no npm, no framework. Open it directly in a browser.

### Dependencies

Only one external dependency loaded from CDN:
- **Chart.js 4.4.0** — for all charts (bar charts, line charts)

Everything else (layout, dark theme, tabs, modals, tables) is plain HTML, CSS, and vanilla JavaScript.

### Structure Overview

```
analytics-dashboard.html
├── <head>
│   ├── Chart.js CDN script
│   └── All CSS (GitHub dark theme)
├── <body>
│   ├── Top nav bar (tabs + Load Data button + Config button)
│   ├── Config modal (base URL + JWT token input)
│   └── Main content area
│       ├── #tab-platform   — Platform tab
│       ├── #tab-courses    — Courses tab
│       ├── #tab-instructors — Instructors tab
│       ├── #tab-students   — Students tab
│       └── #tab-ai         — AI Usage tab
└── <script>
    ├── Config helpers (save/load from localStorage)
    ├── API helper (apiFetch)
    ├── Tab switching (switchTab)
    ├── Load Data (loadCurrentTab)
    ├── loadPlatform()
    ├── loadPopularCourses()
    ├── loadInstructorLeaderboard()
    ├── loadStudentDetails()
    ├── loadAI()
    └── Chart rendering helpers
```

### How Config & Auth Work

The dashboard stores your settings in `localStorage` so you don't have to re-enter them on every refresh:

```javascript
// Saves when you click "Save & Close" in the config modal
localStorage.setItem("sc_base_url", baseUrl);
localStorage.setItem("sc_token", token);
```

On every API call, the token is sent as a Bearer header:

```javascript
async function apiFetch(path, params = {}) {
  const url = new URL(BASE_URL + path);
  // adds query params...
  const resp = await fetch(url, {
    headers: { Authorization: `Bearer ${TOKEN}` }
  });
  // ...
}
```

If no token is saved, the auth status badge shows "Not authenticated" in red. If a token exists on load, it auto-fetches platform data.

### Tab System

There are 5 tabs. Clicking a tab just shows/hides the corresponding `div`:

```javascript
function switchTab(name, el) {
  // Hide all .tab-panel divs
  // Show #tab-{name}
  // Mark clicked tab as .active
}
```

Switching tabs does **NOT** fetch data — that only happens when you click **Load Data**.

### Load Data Button

The Load Data button fires **all 4 data loaders in parallel** using `Promise.all`:

```javascript
function loadCurrentTab() {
  $("loadBtn").disabled = true;
  $("loadBtn").textContent = "Loading…";
  Promise.all([
    loadPlatform(),
    loadPopularCourses(),
    loadInstructorLeaderboard(),
    loadAI(),
  ]).finally(() => {
    $("loadBtn").disabled = false;
    $("loadBtn").textContent = "Load Data";
    toast("All data refreshed", "success");
  });
}
```

This fires ~8 API calls simultaneously. The button is disabled during loading and re-enabled when all are done.

> Note: Students tab has no bulk loader — you look up students individually by pasting their UUID.

### What Each Tab Shows

#### Platform Tab
- **Stat cards**: Total students, instructors, published courses, enrollments, completions, avg completion rate
- **Line chart**: Daily enrollments, completions, and drops over the last 30 days

API calls made:
- `GET /analytics/platform/overview`
- `GET /analytics/platform/trends`

#### Courses Tab
- **Bar chart**: Top 10 courses by enrollment count
- **Bar chart**: Top 10 courses by completion rate
- **Full table**: All popular courses with enrollment/completion/progress numbers
- **Course deep-dive**: Enter a course UUID → see detailed stats + daily trend chart

API calls made:
- `GET /analytics/courses/popular?sort_by=enrollments`
- `GET /analytics/courses/popular?sort_by=completion_rate`
- (On lookup) `GET /analytics/courses/{id}` + `GET /analytics/courses/{id}/trends`

#### Instructors Tab
- **Leaderboard table**: Top 10 instructors ranked by student count, with progress bars for completion rate
- **Instructor deep-dive**: Enter an instructor UUID → see full stats

API calls made:
- `GET /analytics/instructors/leaderboard?limit=10`
- (On lookup) `GET /analytics/instructors/{id}`

#### Students Tab
- **No bulk load** — requires manual ID input
- Enter a student UUID → shows stat cards (enrollments, completions, drops, progress, quiz score, certificates)

API calls made (on lookup only):
- `GET /analytics/students/{student_id}`

#### AI Usage Tab
- **Stat cards**: Total questions, tutor questions, instructor requests (summed over range)
- **Line chart**: Daily AI questions over the date range
- **Bar chart**: Tutor vs instructor requests split per day
- Date range picker to narrow the window (default: last 30 days)

API calls made:
- `GET /analytics/platform/ai-usage?from_date=...&to_date=...`

### Chart Implementation

Charts are created using Chart.js. Each chart has a dedicated `<canvas>` element with a fixed ID. The JavaScript uses a pattern to destroy and recreate charts on reload (to avoid Chart.js duplicate chart warnings):

```javascript
// Example: destroy old chart if it exists, then create new one
if (window._enrollChart) window._enrollChart.destroy();
window._enrollChart = new Chart(document.getElementById("enrollmentTrendChart"), {
  type: "line",
  data: { ... },
  options: { ... }
});
```

### Error Handling & Toast Notifications

All API calls go through `apiFetch`. If a call fails, it logs the error and shows a red toast notification at the bottom of the screen. Success actions (like Load Data completing) show a green toast.

```javascript
function toast(msg, type = "error", duration = 3000) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = `toast show ${type === "success" ? "success" : ""}`;
  setTimeout(() => el.classList.remove("show"), duration);
}
```

---

## 8. Full Data Flow — End to End

Here is what happens from a student enrolling to you seeing the number in the dashboard:

```
1. Student clicks "Enroll" on the frontend
         ↓
2. Course service creates enrollment in its DB
         ↓
3. Course service publishes event to Kafka topic: ENROLLMENT
   Payload: { event_type: "enrollment.created", course_id, student_id, instructor_id }
         ↓
4. Analytics EnrollmentConsumer picks up the message
         ↓
5. Checks processed_events — not seen before, proceed
         ↓
6. Increments course_metrics.total_enrollments
   Increments student_metrics.total_enrollments
   Increments instructor_metrics.total_enrollments
   Increments enrollment_daily.new_enrollments for today
         ↓
7. Commits the DB transaction
         ↓
8. Invalidates Redis cache keys matching analytics:courses:*, analytics:instructor:*, etc.
         ↓
9. You click "Load Data" in the dashboard
         ↓
10. Browser sends GET /analytics/platform/overview
    with Authorization: Bearer <your-instructor-jwt>
         ↓
11. Nginx validates JWT with auth sidecar
    Injects X-User-Role: instructor header
         ↓
12. Analytics FastAPI receives request
    Checks X-User-Role == "instructor" ✓
         ↓
13. Calls get_or_set_json (Redis cache helper)
    Cache miss (was just invalidated) → queries PostgreSQL
    Returns fresh counts
    Stores result in Redis for next 5 minutes
         ↓
14. Dashboard renders the updated stat cards and charts
```

---

## Summary Cheat Sheet

| Thing | Where |
|---|---|
| Analytics service code | `services/analytics-service/src/analytics_service/` |
| Kafka consumers | `consumers/` folder — one file per topic |
| DB models (tables) | `models/` folder |
| API endpoints | `api/` folder — platform.py, courses.py, instructors.py, students.py |
| Redis caching logic | `core/cache.py` |
| Dashboard HTML | `test-clients/analytics-dashboard.html` |
| This document | `test-clients/ANALYTICS-DEEP-DIVE.md` |
| Load Data behavior doc | `test-clients/HOW-LOAD-DATA-WORKS.md` |
