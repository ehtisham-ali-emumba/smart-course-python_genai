# SmartCourse Analytics Implementation Plan

## Understanding the Architecture: What Goes Where and Why

### What We Already Have

Every service already has `Instrumentator().instrument(app).expose(app)` which automatically exposes a `/metrics` endpoint. Prometheus scrapes this every 15 seconds. But it only gives us **default HTTP metrics** — request count, latency, and status codes.

- **Prometheus** = a time-series database that stores metric numbers over time
- **Grafana** = a UI that draws charts/dashboards by querying Prometheus

Right now, Grafana has **zero dashboards** — even default HTTP metrics are not being visualized.

### The Problem

The requirements doc (Section 6) asks for business metrics like "Total Students", "Course Completion Rate", "AI Assistant Usage". The default HTTP metrics cannot answer any of these business questions. No service is currently telling Prometheus about these numbers.

### Two Types of Metrics We Need

#### Type 1: Simple Counts (One Service Knows the Answer)

Some metrics only require data from a single service. For example, **"How many users registered?"** — only `user-service` knows this.

We solve this by adding a Prometheus counter inside user-service:

```python
# In user-service metrics.py
user_registrations_total = Counter("user_registrations_total", "Total registrations", ["role"])

# In the registration endpoint, after successful registration:
user_registrations_total.labels(role="student").inc()  # adds +1
```

Now when Prometheus scrapes `/metrics`, it sees `user_registrations_total{role="student"} 47`, and Grafana can display "Total Students: 47".

**No new service needed for these.** Each existing service adds counters/gauges for the data it already owns:
- `user-service` → user registrations, logins, active users
- `course-service` → courses created/published, enrollments, certificates
- `ai-service` → AI questions asked, response times, tokens used
- `notification-service` → emails sent, failures, Kafka consumer stats
- `core-service` → Temporal workflow counts, durations, failures

#### Type 2: Cross-Service Aggregates (Need Data From Multiple Services)

Some metrics require combining data from multiple services. For example, **"Course Completion Rate"** needs:
- Enrollment data (from `enrollment.events` Kafka topic)
- Completion data (from `progress.events` Kafka topic)
- Both linked by `student_id` + `course_id` to calculate: completions ÷ enrollments

No single service has both pieces. **This is why we need the analytics-service.**

The analytics-service:
1. **Listens to Kafka events** from all topics (user, course, enrollment, progress, certificate, ai)
2. **Stores tracking data** in its own PostgreSQL tables (not querying other services' databases)
3. **Computes aggregates** every 60 seconds (e.g., completion rate = completed ÷ enrolled)
4. **Exposes results** via `/metrics` for Prometheus to scrape

```
Kafka events flow in:
  enrollment.created → saves: student X enrolled in course Y at time T1
  progress.completed → saves: student X completed course Y at time T2

Every 60 seconds, analytics-service computes:
  completion_rate = completed / total_enrolled = 0.73
  avg_time = average(T2 - T1) = 12.5 hours

Prometheus scrapes /metrics and sees:
  smartcourse_course_completion_rate{course_id="abc"} 0.73
  smartcourse_avg_completion_time_hours{course_id="abc"} 12.5
```

### The Full Data Flow

```
user-service ──────► /metrics ──► "47 students registered"
course-service ────► /metrics ──► "12 courses published"        ──► Prometheus ──► Grafana
ai-service ────────► /metrics ──► "230 AI questions asked"          (stores)       (draws charts)
notification-svc ──► /metrics ──► "89 emails sent"
analytics-service ─► /metrics ──► "73% completion rate"
                                  "12.5 hrs avg completion"
                                  "3.2 courses per student"
         ▲
         │
    Kafka events from all services
    feed into analytics-service
```

### Summary Table

| What | Where | Why |
|------|-------|-----|
| Simple counts (registrations, courses created, AI questions) | Add counters to **existing services** | Each service already knows this data |
| Cross-service aggregates (completion rate, avg time, courses per student) | **New analytics-service** | Needs data from multiple Kafka topics combined |
| Storage | **Prometheus** | Time-series database, scrapes `/metrics` every 15s |
| Visualization | **Grafana** | Draws charts/dashboards from Prometheus data |

---

## Current State Assessment

### What's Already in Place

| Component | Status | Details |
|-----------|--------|---------|
| Prometheus | Deployed | Scraping all 5 services at `/metrics`, 15s interval |
| Grafana | Deployed | Prometheus datasource configured, **no dashboards** |
| prometheus-fastapi-instrumentator | All services | Default HTTP metrics only (request count, latency, status codes) |
| Kafka Event System | Fully implemented | 7 topics: user, course, enrollment, progress, notification, certificate, ai |
| OpenTelemetry | Deps installed | **Not wired up** - packages in pyproject.toml but no active instrumentation |

### What's Missing (from Requirement Doc Section 6)

| Required Metric | Current State |
|-----------------|---------------|
| Total Students | NOT tracked |
| Total Instructors | NOT tracked |
| Total Courses Published | NOT tracked |
| New Enrollments Over Time | NOT tracked |
| Course Completion Rate | NOT tracked |
| Average Time to Complete a Course | NOT tracked |
| Most Popular Courses | NOT tracked |
| Average Courses per Student | NOT tracked |
| AI Assistant Usage | NOT tracked |
| Failed Events / Workflow Issues | Only basic HTTP error codes |

**Zero custom Prometheus metrics exist across the entire codebase.** All services only expose the default FastAPI HTTP metrics.

---

## Architecture Decision: Do We Need a Separate Analytics Service?

**Yes - a hybrid approach is the best practice here. Here's why:**

### Two Categories of Metrics

**Category 1: Service-Local Metrics** - Each service instruments its own operations.
- Example: user-service tracks `user_registrations_total`, course-service tracks `course_publish_total`
- These are best exposed directly from each service via custom Prometheus counters/gauges
- No new service needed - just add custom metrics to existing services

**Category 2: Cross-Service / Aggregated Business Metrics** - Metrics that span multiple services or require event correlation.
- Example: "Course Completion Rate" needs enrollment data + progress data + completion data
- Example: "Average Time to Complete a Course" needs enrollment timestamp + completion timestamp from different events
- These need a single service that consumes Kafka events, maintains state, and exposes aggregated metrics

### The Hybrid Architecture

```
                                          Prometheus (scrapes /metrics from all)
                                                    |
                    +-------------------------------+-------------------------------+
                    |               |               |               |               |
              user-service    course-service   ai-service    notification    analytics-service
              (local metrics)  (local metrics)  (local metrics) (local metrics) (aggregated metrics)
                    |               |               |               |               |
                    +---> Kafka <---+---------------+---------------+               |
                              |                                                     |
                              +-------------------> consumes events ----------------+
                                                                                    |
                                                                              PostgreSQL
                                                                          (analytics tables)

                                          Grafana (queries Prometheus)
                                                    |
                              +---------------------+---------------------+
                              |                     |                     |
                     System Dashboard      Business Dashboard      AI Dashboard
```

---

## Implementation Plan

### Phase 1: Add Custom Prometheus Metrics to Existing Services

Each service gets a new `metrics.py` file defining custom Prometheus metrics. The existing `Instrumentator().instrument(app).expose(app)` already exposes `/metrics` - custom metrics registered with the default Prometheus registry are automatically included.

#### 1.1 User Service (`services/user-service/src/user_service/metrics.py`)

```python
from prometheus_client import Counter, Gauge

# Counters (increment-only, tracks totals)
user_registrations_total = Counter(
    "user_registrations_total",
    "Total user registrations",
    ["role"],  # labels: student, instructor, admin
)

user_login_total = Counter(
    "user_login_total",
    "Total login attempts",
    ["status"],  # labels: success, failed
)

user_verification_total = Counter(
    "user_verification_total",
    "Total email verifications",
    ["status"],  # labels: success, failed
)

# Gauges (can go up/down, tracks current state)
active_users_gauge = Gauge(
    "active_users_total",
    "Current number of active users",
    ["role"],  # labels: student, instructor
)
```

**Where to increment:** In your API route handlers or service layer:
```python
# In user registration endpoint
from user_service.metrics import user_registrations_total
user_registrations_total.labels(role=user.role).inc()

# In login endpoint
user_login_total.labels(status="success").inc()
```

**Populate gauges on startup:** Query the database once at startup to set initial gauge values, then keep them updated via increments/decrements as events occur.

```python
# In main.py lifespan
async def set_initial_metrics(session):
    student_count = await session.scalar(
        select(func.count()).where(User.role == "student", User.is_active == True)
    )
    active_users_gauge.labels(role="student").set(student_count)
    # ... same for instructor
```

#### 1.2 Course Service (`services/course-service/src/metrics.py`)

```python
from prometheus_client import Counter, Gauge, Histogram

# Counters
courses_created_total = Counter(
    "courses_created_total",
    "Total courses created",
)

courses_published_total = Counter(
    "courses_published_total",
    "Total courses published",
)

enrollments_total = Counter(
    "enrollments_total",
    "Total enrollments",
    ["status"],  # labels: active, completed, dropped
)

progress_updates_total = Counter(
    "progress_updates_total",
    "Total progress update events",
)

certificates_issued_total = Counter(
    "certificates_issued_total",
    "Total certificates issued",
)

# Gauges
published_courses_gauge = Gauge(
    "published_courses_current",
    "Current number of published courses",
)

active_enrollments_gauge = Gauge(
    "active_enrollments_current",
    "Current active enrollments",
    ["course_id"],  # per-course tracking for "most popular"
)

# Histograms
enrollment_processing_duration = Histogram(
    "enrollment_processing_duration_seconds",
    "Time to process an enrollment",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)
```

**Where to increment:**
```python
# In course publish endpoint/service
courses_published_total.inc()
published_courses_gauge.inc()

# In enrollment endpoint
enrollments_total.labels(status="active").inc()

# Use histogram as context manager
with enrollment_processing_duration.time():
    await process_enrollment(...)
```

#### 1.3 AI Service (`services/ai-service/src/ai_service/metrics.py`)

```python
from prometheus_client import Counter, Histogram

# Counters
ai_questions_total = Counter(
    "ai_questions_total",
    "Total AI assistant questions",
    ["type"],  # labels: contextual_qa, content_enhancement
)

ai_responses_total = Counter(
    "ai_responses_total",
    "Total AI responses generated",
    ["type", "status"],  # labels: type + success/error
)

# Histograms
ai_response_duration = Histogram(
    "ai_response_duration_seconds",
    "AI response generation time",
    ["type"],
    buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
)

ai_indexing_duration = Histogram(
    "ai_indexing_duration_seconds",
    "Course content indexing time",
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

ai_tokens_used_total = Counter(
    "ai_tokens_used_total",
    "Total LLM tokens consumed",
    ["type", "direction"],  # type: contextual/enhancement, direction: input/output
)
```

#### 1.4 Notification Service (`services/notification-service/src/notification_service/metrics.py`)

```python
from prometheus_client import Counter, Histogram

notifications_sent_total = Counter(
    "notifications_sent_total",
    "Total notifications sent",
    ["type", "channel"],  # type: welcome/progress/certificate, channel: email/in-app
)

notifications_failed_total = Counter(
    "notifications_failed_total",
    "Total failed notifications",
    ["type", "reason"],
)

kafka_messages_consumed_total = Counter(
    "kafka_messages_consumed_total",
    "Total Kafka messages consumed",
    ["topic", "status"],  # status: processed, failed, skipped
)

kafka_consumer_lag = Histogram(
    "kafka_consumer_lag_seconds",
    "Kafka consumer processing lag",
    ["topic"],
)
```

#### 1.5 Core Service (`services/core/src/core_service/metrics.py`)

```python
from prometheus_client import Counter, Histogram

temporal_workflows_started_total = Counter(
    "temporal_workflows_started_total",
    "Total Temporal workflows started",
    ["workflow_type"],  # labels: course_publish, enrollment
)

temporal_workflows_completed_total = Counter(
    "temporal_workflows_completed_total",
    "Total Temporal workflows completed",
    ["workflow_type", "status"],  # status: success, failed
)

temporal_workflow_duration = Histogram(
    "temporal_workflow_duration_seconds",
    "Temporal workflow execution time",
    ["workflow_type"],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

temporal_activities_total = Counter(
    "temporal_activities_total",
    "Total Temporal activities executed",
    ["activity_type", "status"],
)
```

---

### Phase 2: Analytics Service (New Microservice)

This service consumes Kafka events to compute cross-service business metrics that no single service can calculate alone.

#### 2.1 Service Structure

```
services/analytics-service/
├── Dockerfile
├── pyproject.toml
└── src/
    └── analytics_service/
        ├── __init__.py
        ├── main.py              # FastAPI app + Kafka consumer background task
        ├── config.py            # Settings
        ├── metrics.py           # Prometheus business metrics
        ├── consumers/
        │   ├── __init__.py
        │   └── event_consumer.py  # Kafka consumer + event dispatcher
        ├── handlers/
        │   ├── __init__.py
        │   ├── enrollment.py    # Handles enrollment.events
        │   ├── progress.py      # Handles progress.events
        │   ├── course.py        # Handles course.events
        │   ├── user.py          # Handles user.events
        │   ├── ai.py            # Handles ai.events
        │   └── certificate.py   # Handles certificate.events
        ├── models/
        │   ├── __init__.py
        │   └── analytics.py     # SQLAlchemy models for analytics tables
        └── db.py                # PostgreSQL connection
```

#### 2.2 Dependencies (`pyproject.toml`)

```toml
[project]
name = "analytics-service"
version = "0.1.0"
requires-python = ">=3.12"

dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "aiokafka>=0.10.0",
    "sqlalchemy[asyncio]>=2.0.25",
    "asyncpg>=0.29.0",
    "prometheus-client>=0.20.0",
    "prometheus-fastapi-instrumentator>=7.0.2",
    "structlog>=24.1.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
]
```

> **Note:** This service does NOT need `prometheus-fastapi-instrumentator` for the business metrics. The `prometheus_client` library is sufficient. However, including `prometheus-fastapi-instrumentator` keeps consistency with other services for HTTP endpoint metrics.

#### 2.3 Analytics Database Models

The analytics service needs its own tables in PostgreSQL to maintain state for computing aggregated metrics. These are lightweight tracking tables, not duplicates of the source data.

```python
# models/analytics.py
from sqlalchemy import Column, String, DateTime, Integer, Float, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase
import uuid

class Base(DeclarativeBase):
    pass

class EnrollmentAnalytics(Base):
    """Tracks enrollment events for time-series analysis."""
    __tablename__ = "enrollment_analytics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    course_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    enrolled_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="active")  # active, completed, dropped
    event_id = Column(String, nullable=False, unique=True)  # idempotency key

class CourseAnalytics(Base):
    """Tracks course-level aggregated stats."""
    __tablename__ = "course_analytics"

    course_id = Column(UUID(as_uuid=True), primary_key=True)
    title = Column(String, nullable=False)
    total_enrollments = Column(Integer, default=0)
    total_completions = Column(Integer, default=0)
    avg_completion_time_hours = Column(Float, nullable=True)
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class AIUsageAnalytics(Base):
    """Tracks AI assistant usage."""
    __tablename__ = "ai_usage_analytics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    course_id = Column(UUID(as_uuid=True), nullable=True)
    interaction_type = Column(String, nullable=False)  # contextual_qa, content_enhancement
    timestamp = Column(DateTime(timezone=True), nullable=False)
    event_id = Column(String, nullable=False, unique=True)  # idempotency key
```

#### 2.4 Prometheus Business Metrics (`metrics.py`)

These are the cross-cutting business metrics that map directly to the requirement doc:

```python
from prometheus_client import Gauge, Counter

# === Requirement Doc Section 6 Metrics ===

# Total Students (Gauge - queried from enrollment_analytics on startup, updated via events)
total_students = Gauge(
    "smartcourse_total_students",
    "Total number of active students on the platform",
)

# Total Instructors (Gauge)
total_instructors = Gauge(
    "smartcourse_total_instructors",
    "Total number of active instructors",
)

# Total Courses Published (Gauge)
total_courses_published = Gauge(
    "smartcourse_total_courses_published",
    "Total published courses",
)

# New Enrollments Over Time (Counter - Prometheus handles time-series natively)
new_enrollments = Counter(
    "smartcourse_new_enrollments_total",
    "New enrollments (use rate() in Grafana for over-time)",
)

# Course Completion Rate (Gauge - recomputed periodically)
course_completion_rate = Gauge(
    "smartcourse_course_completion_rate",
    "Course completion rate (completions/enrollments)",
    ["course_id"],
)

# Average Time to Complete (Gauge - recomputed periodically)
avg_completion_time_hours = Gauge(
    "smartcourse_avg_completion_time_hours",
    "Average hours from enrollment to completion",
    ["course_id"],
)

# Most Popular Courses (Gauge - enrollment count per course)
course_enrollment_count = Gauge(
    "smartcourse_course_enrollment_count",
    "Total enrollments per course",
    ["course_id", "course_title"],
)

# Average Courses per Student (Gauge)
avg_courses_per_student = Gauge(
    "smartcourse_avg_courses_per_student",
    "Average courses each student is enrolled in",
)

# AI Assistant Usage (Counter)
ai_interactions_total = Counter(
    "smartcourse_ai_interactions_total",
    "AI assistant interactions",
    ["interaction_type"],  # contextual_qa, content_enhancement
)

# Failed Events / Workflow Issues (Counter)
failed_events_total = Counter(
    "smartcourse_failed_events_total",
    "Failed background events",
    ["source", "event_type"],  # source: kafka/temporal/celery
)
```

#### 2.5 Kafka Event Consumer

```python
# consumers/event_consumer.py
from shared.kafka.consumer import EventConsumer
from shared.kafka.topics import Topics

class AnalyticsEventConsumer:
    def __init__(self, bootstrap_servers: str):
        self.consumer = EventConsumer(
            bootstrap_servers=bootstrap_servers,
            group_id="analytics-service",
            topics=[
                Topics.USER,
                Topics.COURSE,
                Topics.ENROLLMENT,
                Topics.PROGRESS,
                Topics.CERTIFICATE,
                Topics.AI,
            ],
        )

    async def start(self):
        """Register handlers and start consuming."""
        self.consumer.register_handler("user.created", self.handle_user_created)
        self.consumer.register_handler("course.published", self.handle_course_published)
        self.consumer.register_handler("enrollment.created", self.handle_enrollment_created)
        self.consumer.register_handler("progress.completed", self.handle_course_completed)
        self.consumer.register_handler("ai.question.asked", self.handle_ai_interaction)
        # ... register all relevant event handlers
        await self.consumer.start()
```

#### 2.6 `main.py`

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Connect to PostgreSQL
    # 2. Run table creation / alembic migrations
    # 3. Load initial metric values from DB into Prometheus gauges
    # 4. Start Kafka consumer as background task
    yield
    # Cleanup

app = FastAPI(title="Analytics Service", lifespan=lifespan)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "analytics-service"}
```

#### 2.7 Periodic Gauge Refresh

Some gauges (completion rate, avg time) should be recomputed periodically since they are aggregate calculations:

```python
import asyncio

async def refresh_aggregate_metrics(session_factory):
    """Runs every 60 seconds to recompute aggregate gauges."""
    while True:
        async with session_factory() as session:
            # Completion rate per course
            rows = await session.execute(text("""
                SELECT course_id,
                       COUNT(*) FILTER (WHERE status = 'completed')::float / COUNT(*) as rate,
                       AVG(EXTRACT(EPOCH FROM (completed_at - enrolled_at)) / 3600)
                           FILTER (WHERE status = 'completed') as avg_hours
                FROM enrollment_analytics
                GROUP BY course_id
            """))
            for row in rows:
                course_completion_rate.labels(course_id=str(row.course_id)).set(row.rate)
                if row.avg_hours:
                    avg_completion_time_hours.labels(course_id=str(row.course_id)).set(row.avg_hours)

            # Avg courses per student
            result = await session.scalar(text("""
                SELECT AVG(course_count) FROM (
                    SELECT student_id, COUNT(DISTINCT course_id) as course_count
                    FROM enrollment_analytics
                    WHERE status = 'active'
                    GROUP BY student_id
                ) sub
            """))
            if result:
                avg_courses_per_student.set(float(result))

        await asyncio.sleep(60)  # refresh every 60 seconds
```

Start this in the lifespan:
```python
asyncio.create_task(refresh_aggregate_metrics(async_session_factory))
```

---

### Phase 3: Docker Compose & Prometheus Configuration

#### 3.1 Add to `docker-compose.yml`

```yaml
  analytics-service:
    build:
      context: .
      dockerfile: services/analytics-service/Dockerfile
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/smartcourse_analytics
      - KAFKA_BOOTSTRAP_SERVERS=kafka:29092
    depends_on:
      - postgres
      - kafka
    networks:
      - smartcourse-network
```

#### 3.2 Add to `monitoring/prometheus.yml`

```yaml
  - job_name: "analytics-service"
    metrics_path: /metrics
    static_configs:
      - targets: ["analytics-service:8007"]
```

---

### Phase 4: Grafana Dashboard Provisioning

Create pre-built dashboards as JSON provisioning so they load automatically.

#### 4.1 Dashboard Provisioning Config

```
monitoring/grafana/provisioning/dashboards/
├── dashboard.yaml          # tells Grafana where to find dashboards
└── smartcourse/
    ├── business-metrics.json
    ├── system-overview.json
    └── ai-assistant.json
```

**`dashboard.yaml`:**
```yaml
apiVersion: 1
providers:
  - name: "SmartCourse"
    orgId: 1
    folder: "SmartCourse"
    type: file
    disableDeletion: false
    editable: true
    options:
      path: /var/lib/grafana/dashboards/smartcourse
      foldersFromFilesStructure: true
```

**Mount in docker-compose (add to grafana volumes):**
```yaml
  grafana:
    volumes:
      - ./monitoring/grafana/provisioning/datasources:/etc/grafana/provisioning/datasources
      - ./monitoring/grafana/provisioning/dashboards:/etc/grafana/provisioning/dashboards
      - ./monitoring/grafana/dashboards/smartcourse:/var/lib/grafana/dashboards/smartcourse
```

#### 4.2 Dashboard Panels (what to include)

**Business Metrics Dashboard:**

| Panel | Type | PromQL Query |
|-------|------|-------------|
| Total Students | Stat | `smartcourse_total_students` |
| Total Instructors | Stat | `smartcourse_total_instructors` |
| Total Courses Published | Stat | `smartcourse_total_courses_published` |
| Enrollments Over Time | Time Series | `rate(smartcourse_new_enrollments_total[1h])` |
| Course Completion Rate | Bar Gauge | `smartcourse_course_completion_rate` |
| Avg Completion Time | Table | `smartcourse_avg_completion_time_hours` |
| Most Popular Courses | Bar Chart | `topk(10, smartcourse_course_enrollment_count)` |
| Avg Courses per Student | Stat | `smartcourse_avg_courses_per_student` |
| AI Usage Over Time | Time Series | `rate(smartcourse_ai_interactions_total[1h])` |
| Failed Events | Time Series | `rate(smartcourse_failed_events_total[5m])` |

**System Overview Dashboard:**

| Panel | Type | PromQL Query |
|-------|------|-------------|
| Request Rate (per service) | Time Series | `rate(http_requests_total[5m])` |
| Response Latency p95 | Time Series | `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))` |
| Error Rate | Time Series | `rate(http_requests_total{status=~"5.."}[5m])` |
| Kafka Messages Consumed | Time Series | `rate(kafka_messages_consumed_total[5m])` |
| Temporal Workflow Success Rate | Gauge | `temporal_workflows_completed_total{status="success"} / temporal_workflows_completed_total` |
| Notification Delivery Rate | Time Series | `rate(notifications_sent_total[5m])` |

**AI Assistant Dashboard:**

| Panel | Type | PromQL Query |
|-------|------|-------------|
| Questions Asked | Time Series | `rate(ai_questions_total[1h])` |
| Response Time p50/p95 | Time Series | `histogram_quantile(0.5/0.95, rate(ai_response_duration_seconds_bucket[5m]))` |
| Tokens Consumed | Time Series | `rate(ai_tokens_used_total[1h])` |
| Indexing Duration | Histogram | `ai_indexing_duration_seconds` |
| Error Rate | Time Series | `rate(ai_responses_total{status="error"}[5m])` |

---

## Phase 5: Missing Event Attributes to Add

Some Kafka events may not carry all the data the analytics service needs. Here's what to verify and add:

### Events That Need Verification/Enhancement

| Topic | Event Type | Required Fields for Analytics | Action |
|-------|-----------|-------------------------------|--------|
| `enrollment.events` | `enrollment.created` | `student_id`, `course_id`, `enrolled_at`, `event_id` | Verify `enrolled_at` timestamp is included |
| `progress.events` | `progress.completed` | `student_id`, `course_id`, `completed_at`, `event_id` | Verify `completed_at` timestamp is included |
| `course.events` | `course.published` | `course_id`, `title`, `instructor_id`, `published_at` | Verify `title` is included for dashboard labels |
| `ai.events` | `ai.question.asked` | `user_id`, `course_id`, `interaction_type`, `tokens_used` | **Likely missing** - add `tokens_used` and `interaction_type` to AI event payload |
| `user.events` | `user.created` | `user_id`, `role`, `created_at` | Verify `role` is included |
| `certificate.events` | `certificate.issued` | `student_id`, `course_id`, `issued_at` | Verify fields exist |

### What to Check in Existing Code

1. **`shared/src/shared/kafka/producer.py`** - Verify the `EventEnvelope` includes a timestamp field
2. **Course service enrollment handler** - Verify `enrolled_at` is part of the Kafka payload
3. **AI service event publishing** - Likely needs the most work; verify events include `interaction_type`, `tokens_used`, `course_id`
4. **Progress events** - Verify `completed_at` is sent when a course is fully completed

---

## Implementation Order (Recommended)

```
Step 1: Add custom metrics to existing services (Phase 1)
   |
   |--- 1a. Create metrics.py in each service
   |--- 1b. Wire metrics into route handlers / service layer
   |--- 1c. Add startup gauge initialization from DB
   |
Step 2: Verify & enhance Kafka event payloads (Phase 5)
   |
   |--- 2a. Audit each event type's payload
   |--- 2b. Add missing fields (especially AI events)
   |
Step 3: Build analytics service (Phase 2)
   |
   |--- 3a. Scaffold the service (config, main, models)
   |--- 3b. Implement Kafka consumer + event handlers
   |--- 3c. Implement periodic gauge refresh
   |--- 3d. Add Dockerfile
   |
Step 4: Infrastructure updates (Phase 3)
   |
   |--- 4a. Add analytics-service to docker-compose.yml
   |--- 4b. Add scrape target to prometheus.yml
   |--- 4c. Create analytics DB in PostgreSQL init
   |
Step 5: Grafana dashboards (Phase 4)
   |
   |--- 5a. Create dashboard provisioning config
   |--- 5b. Build Business Metrics dashboard JSON
   |--- 5c. Build System Overview dashboard JSON
   |--- 5d. Build AI Assistant dashboard JSON
```

---

## Key Design Decisions & Best Practices

### 1. Idempotency
Every event handler in the analytics service uses `event_id` as a unique constraint. If the same event is delivered twice (Kafka at-least-once), the second insert is silently ignored via `ON CONFLICT DO NOTHING`.

### 2. Metric Naming Convention
All metrics follow Prometheus naming best practices:
- `smartcourse_` prefix for business metrics (analytics service)
- Service-specific names for operational metrics (no prefix needed - job label differentiates)
- `_total` suffix for counters
- `_seconds` suffix for duration histograms
- `_current` suffix for point-in-time gauges

### 3. Why Not Query Source DBs Directly?
The analytics service maintains its own tables rather than querying user-service or course-service databases because:
- **Service isolation** - Microservices should not share databases
- **Performance** - Analytics queries (aggregations, joins) would impact the operational database
- **Decoupling** - Source schema changes don't break analytics

### 4. Why Prometheus Gauges + Periodic Refresh Instead of Real-Time?
Aggregate metrics like "completion rate" and "avg time" require SQL aggregation. Computing these on every event would be wasteful. A 60-second refresh cycle is appropriate for dashboard display while keeping DB load minimal.

### 5. Grafana Dashboard as Code
Provisioning dashboards as JSON files means they are version-controlled, reproducible, and automatically loaded on `docker compose up`. No manual dashboard creation needed.
