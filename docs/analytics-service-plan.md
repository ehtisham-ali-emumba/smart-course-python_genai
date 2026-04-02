# Analytics Service — Implementation Plan

## 1. Overview

The analytics service is a **read-heavy, event-driven microservice** that consumes Kafka events from existing services (user, course, enrollment, progress, AI) and materializes pre-computed metrics into its own PostgreSQL tables + Redis cache. It exposes REST endpoints for dashboards and reports.

**Key design decision**: The analytics service does NOT query other services' databases directly. It builds its own read-optimized data store from Kafka events. This keeps services decoupled and lets analytics scale independently.

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ user-service │  │course-service│  │  ai-service   │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │ Kafka           │ Kafka           │ Kafka
       ▼                 ▼                 ▼
┌─────────────────────────────────────────────────┐
│              analytics-service                   │
│                                                  │
│  ┌────────────┐  ┌────────────┐  ┌───────────┐  │
│  │  Kafka     │  │  Metrics   │  │   API     │  │
│  │  Consumer  │──▶  Engine    │  │  Layer    │  │
│  └────────────┘  └─────┬──────┘  └─────┬─────┘  │
│                        │               │         │
│                  ┌─────▼──────┐  ┌─────▼─────┐   │
│                  │ PostgreSQL │  │   Redis   │   │
│                  │ (metrics)  │  │  (cache)  │   │
│                  └────────────┘  └───────────┘   │
└─────────────────────────────────────────────────┘
```

---

## 2. Service Structure

Follow the exact same patterns as existing services:

```
services/analytics-service/
├── Dockerfile
├── pyproject.toml
├── alembic.ini
├── alembic/
│   └── versions/
└── src/
    └── analytics_service/
        ├── main.py                    # FastAPI app + lifespan
        ├── config.py                  # Pydantic Settings
        ├── core/
        │   ├── database.py            # SQLAlchemy async engine
        │   ├── redis.py               # Redis connection
        │   └── cache.py               # Cache decorator/helpers
        ├── models/
        │   ├── __init__.py
        │   ├── base.py               # DeclarativeBase
        │   ├── platform_snapshot.py   # Daily platform-level snapshot
        │   ├── course_metrics.py      # Per-course metrics
        │   ├── instructor_metrics.py  # Per-instructor metrics
        │   ├── student_metrics.py     # Per-student metrics
        │   ├── enrollment_daily.py    # Daily enrollment counts
        │   └── ai_usage.py           # AI assistant usage metrics
        ├── schemas/
        │   ├── __init__.py
        │   ├── platform.py           # Response schemas for platform stats
        │   ├── courses.py            # Response schemas for course analytics
        │   ├── instructors.py
        │   ├── students.py
        │   └── ai_usage.py
        ├── repositories/
        │   ├── base.py               # BaseRepository (reuse from shared or copy)
        │   ├── platform_repo.py
        │   ├── course_metrics_repo.py
        │   ├── instructor_metrics_repo.py
        │   ├── student_metrics_repo.py
        │   └── enrollment_daily_repo.py
        ├── services/
        │   ├── platform_service.py    # Business logic for platform metrics
        │   ├── course_analytics_service.py
        │   ├── instructor_analytics_service.py
        │   ├── student_analytics_service.py
        │   └── snapshot_service.py    # Builds daily snapshots
        ├── consumers/
        │   ├── __init__.py
        │   ├── consumer_manager.py    # Starts/stops all consumers
        │   ├── user_consumer.py       # Handles user.events
        │   ├── course_consumer.py     # Handles course.events
        │   ├── enrollment_consumer.py # Handles enrollment.events
        │   ├── progress_consumer.py   # Handles progress.events
        │   └── ai_consumer.py         # Handles ai.events
        └── api/
            ├── router.py             # Combines all routers
            ├── dependencies.py       # get_db, get_cache, require_admin, etc.
            ├── platform.py           # Platform-wide analytics endpoints
            ├── courses.py            # Course analytics endpoints
            ├── instructors.py        # Instructor analytics endpoints
            └── students.py           # Student analytics endpoints
```

---

## 3. Database Models (PostgreSQL — analytics DB)

The analytics service gets its **own PostgreSQL database** (`analytics_db`). These are materialized/pre-computed tables, NOT normalized relational tables.

### 3.1 `platform_snapshots` — Daily platform-level rollup

```python
class PlatformSnapshot(Base):
    __tablename__ = "platform_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    snapshot_date: Mapped[date] = mapped_column(Date, unique=True, index=True)

    total_students: Mapped[int] = mapped_column(default=0)
    total_instructors: Mapped[int] = mapped_column(default=0)
    total_courses_published: Mapped[int] = mapped_column(default=0)
    total_enrollments: Mapped[int] = mapped_column(default=0)
    total_completions: Mapped[int] = mapped_column(default=0)
    total_certificates_issued: Mapped[int] = mapped_column(default=0)

    new_students_today: Mapped[int] = mapped_column(default=0)
    new_instructors_today: Mapped[int] = mapped_column(default=0)
    new_enrollments_today: Mapped[int] = mapped_column(default=0)
    new_completions_today: Mapped[int] = mapped_column(default=0)

    avg_courses_per_student: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=0)
    avg_completion_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)

    ai_questions_asked_today: Mapped[int] = mapped_column(default=0)
    ai_questions_answered_today: Mapped[int] = mapped_column(default=0)

    created_at: Mapped[datetime] = mapped_column(default=func.now())
```

### 3.2 `course_metrics` — Per-course analytics (updated on events)

```python
class CourseMetrics(Base):
    __tablename__ = "course_metrics"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(unique=True, index=True)
    instructor_id: Mapped[uuid.UUID] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(255))
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    total_enrollments: Mapped[int] = mapped_column(default=0)
    active_enrollments: Mapped[int] = mapped_column(default=0)
    completed_enrollments: Mapped[int] = mapped_column(default=0)
    dropped_enrollments: Mapped[int] = mapped_column(default=0)
    completion_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)

    avg_progress_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    avg_time_to_complete_hours: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)

    avg_quiz_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    total_quiz_attempts: Mapped[int] = mapped_column(default=0)

    ai_questions_asked: Mapped[int] = mapped_column(default=0)

    published_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_enrollment_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
```

### 3.3 `instructor_metrics` — Per-instructor rollup

```python
class InstructorMetrics(Base):
    __tablename__ = "instructor_metrics"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    instructor_id: Mapped[uuid.UUID] = mapped_column(unique=True, index=True)

    total_courses: Mapped[int] = mapped_column(default=0)
    published_courses: Mapped[int] = mapped_column(default=0)
    total_students: Mapped[int] = mapped_column(default=0)       # unique students across all courses
    total_enrollments: Mapped[int] = mapped_column(default=0)
    total_completions: Mapped[int] = mapped_column(default=0)
    avg_completion_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    avg_quiz_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
```

### 3.4 `student_metrics` — Per-student rollup

```python
class StudentMetrics(Base):
    __tablename__ = "student_metrics"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(unique=True, index=True)

    total_enrollments: Mapped[int] = mapped_column(default=0)
    active_enrollments: Mapped[int] = mapped_column(default=0)
    completed_courses: Mapped[int] = mapped_column(default=0)
    dropped_courses: Mapped[int] = mapped_column(default=0)
    avg_progress: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    avg_quiz_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    total_certificates: Mapped[int] = mapped_column(default=0)

    last_active_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
```

### 3.5 `enrollment_daily` — Time-series for enrollment trends

```python
class EnrollmentDaily(Base):
    __tablename__ = "enrollment_daily"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    date: Mapped[date] = mapped_column(Date, index=True)
    course_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True, index=True)  # NULL = platform-wide

    new_enrollments: Mapped[int] = mapped_column(default=0)
    new_completions: Mapped[int] = mapped_column(default=0)
    new_drops: Mapped[int] = mapped_column(default=0)

    __table_args__ = (
        UniqueConstraint("date", "course_id", name="uq_enrollment_daily_date_course"),
    )
```

### 3.6 `ai_usage_daily` — AI assistant usage tracking

```python
class AIUsageDaily(Base):
    __tablename__ = "ai_usage_daily"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    date: Mapped[date] = mapped_column(Date, index=True)
    course_id: Mapped[Optional[uuid.UUID]] = mapped_column(nullable=True, index=True)

    tutor_questions: Mapped[int] = mapped_column(default=0)       # student contextual Q&A
    instructor_requests: Mapped[int] = mapped_column(default=0)   # content generation
    total_questions: Mapped[int] = mapped_column(default=0)

    __table_args__ = (
        UniqueConstraint("date", "course_id", name="uq_ai_usage_daily_date_course"),
    )
```

---

## 4. Kafka Consumer Design

The analytics service joins the **`analytics` consumer group** for each topic, so it gets its own independent read of every event without affecting existing consumers.

### 4.1 Consumer Manager

```python
# consumers/consumer_manager.py
class ConsumerManager:
    """Starts all Kafka consumers as asyncio tasks during app lifespan."""

    def __init__(self, db_session_factory, redis):
        self.consumers = [
            UserEventConsumer(db_session_factory, group_id="analytics-user"),
            CourseEventConsumer(db_session_factory, group_id="analytics-course"),
            EnrollmentEventConsumer(db_session_factory, group_id="analytics-enrollment"),
            ProgressEventConsumer(db_session_factory, group_id="analytics-progress"),
            AIEventConsumer(db_session_factory, group_id="analytics-ai"),
        ]

    async def start(self):
        self.tasks = [asyncio.create_task(c.run()) for c in self.consumers]

    async def stop(self):
        for c in self.consumers:
            await c.stop()
```

### 4.2 Event → Metric Mapping

| Kafka Topic | Event Type | Analytics Action |
|---|---|---|
| `user.events` | `user.registered` | Increment `total_students` or `total_instructors` based on role. Create `student_metrics` / `instructor_metrics` row. |
| `course.events` | `course.published` | Increment `total_courses_published`. Create `course_metrics` row. Update `instructor_metrics.published_courses`. |
| `course.events` | `course.archived` | Decrement `total_courses_published`. Update `course_metrics`. |
| `enrollment.events` | `enrollment.created` | Increment counters on `course_metrics`, `student_metrics`, `instructor_metrics`. Insert into `enrollment_daily`. |
| `enrollment.events` | `enrollment.completed` | Update completion counts & rates. Compute `avg_time_to_complete`. |
| `enrollment.events` | `enrollment.dropped` | Update drop counts. Recalculate `completion_rate`. |
| `progress.events` | `progress.updated` | Update `course_metrics.avg_progress_percentage`, `student_metrics.avg_progress`. |
| `progress.events` | `quiz.graded` | Update `avg_quiz_score`, `total_quiz_attempts`. |
| `certificate.events` | `certificate.issued` | Increment `student_metrics.total_certificates`, `total_certificates_issued` in snapshot. |
| `ai.events` | `ai.question.asked` | Increment `ai_usage_daily`, `course_metrics.ai_questions_asked`. |

### 4.3 Idempotency

Each consumer tracks processed event IDs using the Kafka offset commit mechanism. Additionally, all metric updates use **upsert (INSERT ON CONFLICT UPDATE)** operations, making re-processing safe. The `enrollment_daily` and `ai_usage_daily` tables use date+course_id unique constraints to support idempotent increment-or-create.

---

## 5. API Endpoints

**Base path**: `/analytics` (proxied via API Gateway)

### 5.1 Platform Overview (Admin)

```
GET /analytics/platform/overview
    → PlatformOverviewResponse {
        total_students, total_instructors, total_courses_published,
        total_enrollments, total_completions, avg_completion_rate,
        avg_courses_per_student, total_certificates_issued
      }

GET /analytics/platform/trends?period=daily|weekly|monthly&from=2026-01-01&to=2026-04-01
    → list of { date, new_enrollments, new_completions, new_drops }

GET /analytics/platform/ai-usage?from=...&to=...
    → list of { date, tutor_questions, instructor_requests, total }
```

### 5.2 Course Analytics (Admin + Instructor for own courses)

```
GET /analytics/courses/popular?limit=10&sort_by=enrollments|completion_rate
    → list of { course_id, title, total_enrollments, completion_rate, avg_progress }

GET /analytics/courses/{course_id}
    → CourseAnalyticsResponse {
        course_id, title, total_enrollments, active_enrollments,
        completed_enrollments, dropped_enrollments, completion_rate,
        avg_progress_percentage, avg_time_to_complete_hours,
        avg_quiz_score, total_quiz_attempts, ai_questions_asked,
        enrollment_trend: [{ date, count }]
      }

GET /analytics/courses/{course_id}/trends?period=daily&from=...&to=...
    → list of { date, new_enrollments, new_completions }
```

### 5.3 Instructor Analytics (Admin + Instructor for self)

```
GET /analytics/instructors/{instructor_id}
    → InstructorAnalyticsResponse {
        instructor_id, total_courses, published_courses,
        total_students, total_enrollments, total_completions,
        avg_completion_rate, avg_quiz_score,
        courses: [{ course_id, title, enrollments, completion_rate }]
      }

GET /analytics/instructors/leaderboard?limit=10&sort_by=students|completion_rate
    → list of { instructor_id, total_students, avg_completion_rate }
```

### 5.4 Student Analytics (Admin + Student for self)

```
GET /analytics/students/{student_id}
    → StudentAnalyticsResponse {
        student_id, total_enrollments, active_enrollments,
        completed_courses, dropped_courses, avg_progress,
        avg_quiz_score, total_certificates, last_active_at
      }

GET /analytics/students/{student_id}/courses
    → list of { course_id, title, status, progress_percentage, quiz_score }
```

---

## 6. Caching Strategy

| Endpoint | Cache Key | TTL | Invalidation |
|---|---|---|---|
| Platform overview | `analytics:platform:overview` | 5 min | On any event processed |
| Popular courses | `analytics:courses:popular:{sort}:{limit}` | 5 min | On enrollment/completion event |
| Course detail | `analytics:course:{course_id}` | 2 min | On event for that course |
| Instructor detail | `analytics:instructor:{id}` | 2 min | On event for that instructor |
| Student detail | `analytics:student:{id}` | 2 min | On event for that student |
| Trends | `analytics:trends:{hash(params)}` | 10 min | Time-based expiry only |

Use Redis with a simple pattern: check cache → return if hit → query DB → set cache on miss. Invalidate relevant keys in the consumer after writing metrics.

---

## 7. Infrastructure & Docker Setup

### 7.1 Add to `docker-compose.yml`

```yaml
analytics-service:
  build:
    context: ./services/analytics-service
    dockerfile: Dockerfile
  ports:
    - "8006:8006"
  environment:
    - DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/analytics_db
    - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/2
    - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
    - SCHEMA_REGISTRY_URL=http://schema-registry:8081
  depends_on:
    - postgres
    - redis
    - kafka
    - schema-registry
  volumes:
    - ./services/analytics-service/src:/app/src
  networks:
    - smartcourse-network
```

### 7.2 Add to Nginx API Gateway

```nginx
location /analytics/ {
    auth_request /auth;
    auth_request_set $user_id $upstream_http_x_user_id;
    auth_request_set $user_role $upstream_http_x_user_role;

    proxy_pass http://analytics-service:8006/;
    proxy_set_header X-User-ID $user_id;
    proxy_set_header X-User-Role $user_role;
}
```

### 7.3 Separate Database

Create `analytics_db` in the existing PostgreSQL instance (or a separate instance later for scale). Add to the postgres init script:

```sql
CREATE DATABASE analytics_db;
```

---

## 8. Snapshot Job (Daily Rollup)

A background task runs once daily (via `asyncio` scheduler or a simple cron in the container) to build the `platform_snapshots` row for the current day. This aggregates from the live metric tables:

```python
class SnapshotService:
    async def build_daily_snapshot(self, target_date: date):
        """Aggregates current state of all metrics into a platform_snapshots row."""
        students = await self.student_repo.count()
        instructors = await self.instructor_repo.count()
        courses = await self.course_repo.count_published()
        # ... aggregate from metric tables
        await self.snapshot_repo.upsert(snapshot_date=target_date, **aggregates)
```

Schedule this via a simple approach — an `asyncio.create_task` in the lifespan that sleeps until midnight and runs:

```python
async def daily_snapshot_loop(app):
    while True:
        now = datetime.utcnow()
        tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0)
        await asyncio.sleep((tomorrow - now).total_seconds())
        async with app.state.db_session_factory() as session:
            service = SnapshotService(session)
            await service.build_daily_snapshot(date.today())
```

---

## 9. Authorization Model

| Role | Access |
|---|---|
| **Admin** | All endpoints, all data |
| **Instructor** | Own instructor analytics + own courses analytics |
| **Student** | Own student analytics only |

Enforce via `X-User-ID` and `X-User-Role` headers from the auth sidecar, same as other services.

---

## 10. New Kafka Events Needed

The existing services need to emit a few events that may not exist yet:

| Service | Event | When |
|---|---|---|
| ai-service | `ai.question.asked` on `ai.events` topic | When student asks tutor a question |
| ai-service | `ai.content.generated` on `ai.events` topic | When instructor uses content generation |
| course-service | `quiz.graded` on `progress.events` topic | When a quiz attempt is graded (may already exist) |
| course-service | `certificate.issued` on `certificate.events` topic | When certificate is created (may already exist) |

Check existing event schemas in `shared/src/shared/schemas/events/` and add only what's missing.

---

## 11. Observability

- **Prometheus metrics**: Expose `/metrics` endpoint using `prometheus-fastapi-instrumentator` (same as other services)
- **Custom metrics to track**:
  - `analytics_events_processed_total{topic, event_type}` — counter per event type
  - `analytics_event_processing_lag_seconds{topic}` — how far behind the consumer is
  - `analytics_cache_hit_total` / `analytics_cache_miss_total` — cache effectiveness
- **Grafana dashboard**: Add an analytics-service dashboard to `monitoring/grafana/provisioning/dashboards/json/`
- **Structured logging**: JSON logs with `event_type`, `course_id`, `duration_ms` for every event processed

---

## 12. Implementation Order

| Phase | What | Depends On |
|---|---|---|
| **1** | Scaffold service (Dockerfile, pyproject.toml, main.py, config, DB setup) | Nothing |
| **2** | Create all SQLAlchemy models + Alembic migrations | Phase 1 |
| **3** | Build Kafka consumers (user, course, enrollment events) | Phase 2 |
| **4** | Build repositories + services for metrics computation | Phase 3 |
| **5** | Build API endpoints (platform overview, course analytics) | Phase 4 |
| **6** | Add Redis caching layer | Phase 5 |
| **7** | Add progress + AI event consumers | Phase 3 |
| **8** | Daily snapshot job | Phase 4 |
| **9** | Docker compose + nginx integration | Phase 1 |
| **10** | Grafana dashboard + Prometheus custom metrics | Phase 5 |
| **11** | Add missing Kafka events to ai-service | Independent |

---

## 13. Future Enhancements (Post-MVP)

These are NOT part of the initial build but are worth designing for:

| Enhancement | Description |
|---|---|
| **Real-time WebSocket dashboard** | Push metric updates to admin dashboard via WebSocket instead of polling |
| **Cohort analysis** | Group students by enrollment month, compare completion rates across cohorts |
| **Funnel analytics** | Enrollment → First lesson → 50% progress → Completion funnel per course |
| **Retention metrics** | Weekly/monthly active students, churn rate |
| **Revenue analytics** | Revenue per course, per instructor, MRR if subscription model added |
| **Learning path analytics** | Which module sequences lead to best outcomes |
| **A/B test support** | Compare metrics between course variants |
| **Export API** | CSV/Excel export of any analytics view |
| **Anomaly detection** | Alert when enrollment drops unusually, completion rate tanks, etc. |
| **ClickHouse migration** | If data volume grows beyond PostgreSQL comfort zone, migrate time-series tables to ClickHouse |

---

## 14. Key Architectural Decisions Summary

| Decision | Rationale |
|---|---|
| **Own database, not querying other services' DBs** | Service autonomy. Analytics can scale, fail, and deploy independently. |
| **Event-sourced via Kafka** | Eventually consistent but decoupled. No added load on source services. |
| **Pre-computed metrics, not on-the-fly aggregation** | Fast reads. Dashboard queries hit simple indexed lookups, not expensive aggregations. |
| **PostgreSQL for analytics storage** | Good enough for current scale. Familiar to the team. Easy to migrate to ClickHouse later if needed. |
| **Redis cache with short TTL** | Analytics data is inherently slightly stale. 2-5 min TTL is acceptable and prevents DB hammering. |
| **Upsert-based idempotency** | Safe to re-process events. No dedup table needed. |
| **Daily snapshots as materialized rows** | Historical trend queries are O(1) lookups, not full-table scans. |
