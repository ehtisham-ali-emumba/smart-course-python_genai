# Redis Caching — Complete Implementation Guide

**Date:** February 12, 2026  
**Scope:** User Service + Course Service  
**Pattern:** Cache-Aside (Lazy Loading) at the Service Layer  
**Infrastructure:** Single Redis 7 instance (already in Docker)

---

## Table of Contents

1. [Caching Philosophy](#1-caching-philosophy)
2. [Caching Evaluation — What to Cache & What NOT to Cache](#2-caching-evaluation)
3. [Architecture](#3-architecture)
4. [Docker & Infrastructure Changes](#4-docker--infrastructure-changes)
5. [Shared Module — `core/redis.py` & `core/cache.py`](#5-shared-module)
6. [Course Service — File-by-File Changes](#6-course-service-changes)
7. [User Service — File-by-File Changes](#7-user-service-changes)
8. [Cache Invalidation Strategy](#8-cache-invalidation-strategy)
9. [Health Checks & Monitoring](#9-health-checks--monitoring)
10. [Production Notes](#10-production-notes)

---

## 1. Caching Philosophy

### Core Principles

| Principle | Rule |
|-----------|------|
| **Cache reads, not writes** | Only cache data on the read path. Writes go straight to the database, then invalidate relevant cache keys. |
| **Service-layer caching** | Cache logic lives in the **Service** layer — NOT in repositories (too granular) and NOT in API routes (too coarse). |
| **Explicit over magic** | No decorators or automatic caching. Every cache get/set/delete is a visible, explicit call in the service method. Easy to read, easy to debug. |
| **Graceful degradation** | If Redis is down, the app works normally — just slower (falls through to database). Cache is acceleration, not a requirement. |
| **Don't over-cache** | Only cache data with a high read-to-write ratio. Frequently-mutated or user-specific data with low reuse gets short TTLs or no cache. |

### Pattern: Cache-Aside (Lazy Loading)

```
READ PATH:
  1. Service receives request
  2. Check Redis for cached data
  3. Cache HIT  → return cached data (fast path)
  4. Cache MISS → query database → store result in Redis → return data

WRITE PATH:
  1. Service receives mutation
  2. Write to database
  3. Delete (invalidate) affected cache keys
  4. Do NOT update cache — let the next read repopulate it
```

**Why delete on write (not update)?** Simpler, avoids race conditions, and guarantees consistency. The next read repopulates the cache from the source of truth.

---

## 2. Caching Evaluation

### 2.1 What to Cache (Recommended)

| # | Data | Endpoint | Read Frequency | Write Frequency | TTL | Cache Key Pattern | Invalidation Trigger | Service |
|---|------|----------|----------------|-----------------|-----|-------------------|---------------------|---------|
| 1 | **Published course list** | `GET /courses/` | Very High (every browsing student) | Low (publish/archive) | 5 min | `courses:published:p:{page}:l:{limit}` | Course publish, update, archive, delete | Course |
| 2 | **Single course detail** | `GET /courses/{id}` | Very High (course page views) | Low (instructor edits) | 10 min | `course:{id}` | Course update, delete | Course |
| 3 | **Course content (MongoDB)** | `GET /courses/{id}/content` | Very High (enrolled students loading lessons) | Very Low (after publish, rarely changes) | 15 min | `course_content:{course_id}` | Content upsert, module/lesson add, delete | Course |
| 4 | **Enrollment existence check** | Internal check during content access, enrollment creation | Very High (every content request validates enrollment) | Low (enroll/drop) | 30 min | `enrolled:{student_id}:{course_id}` | Enroll, drop | Course |
| 5 | **User profile** | `GET /users/{id}`, `GET /auth/me` | High (profile page, header display) | Low (profile edits) | 15 min | `user:{id}` | Profile update | User |
| 6 | **Instructor profile** | `GET /instructors/{id}` | High (shown on course pages) | Very Low | 30 min | `instructor:{user_id}` | Profile update | User |
| 7 | **Course enrollment count** | Internal (shown on course cards, enrollment limit checks) | High | Medium (every enrollment) | 5 min | `course:{course_id}:enrollment_count` | Enroll, drop | Course |

### 2.2 What NOT to Cache

| Data | Why NOT |
|------|---------|
| **Student enrollment list** (`GET /enrollments/my-enrollments`) | User-specific, low reuse across users. The same student won't reload this repeatedly. DB query with index is fast enough. |
| **Enrollment progress details** (`GET /enrollments/{id}`) | Frequently mutated (every lesson completion). Caching would require constant invalidation, negating the benefit. |
| **Certificate data** | Rarely accessed (only on completion). Not worth cache memory. |
| **Certificate verification** | Infrequent public access. Simple indexed lookup is sub-millisecond. |
| **Instructor's own course list** (`GET /courses/my-courses`) | User-specific, low reuse. Instructor is one person viewing their own data. |
| **JWT tokens / Sessions** | JWTs are stateless by design. Auth sidecar verifies tokens without state. Adding token caching introduces a session-like dependency. |
| **Rate limiting** | Already handled by Nginx `limit_req` zones (in-memory, per-worker). Moving to Redis would add network latency to every request. |

### 2.3 Decision Summary

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        WHAT GETS CACHED (7 items)                            │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  COURSE SERVICE (5 cache points):                                            │
│  ├── Published course listings    (high traffic, paginated)                  │
│  ├── Individual course details    (high traffic, stable data)                │
│  ├── Course content from MongoDB  (very high traffic, almost never changes)  │
│  ├── Enrollment existence flag    (checked on every content access)          │
│  └── Course enrollment count      (shown on cards, limit checks)            │
│                                                                              │
│  USER SERVICE (2 cache points):                                              │
│  ├── User profile                 (loaded on every page via header/me)       │
│  └── Instructor profile           (shown on course pages)                    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Architecture

### 3.1 Cache Placement

```
┌──────────────────────────────────────────────────────────────────────┐
│                     SERVICE LAYER CACHING                            │
└──────────────────────────────────────────────────────────────────────┘

    API Routes
        │
        ▼
  ┌─────────────┐       ┌────────────┐
  │   Service    │◄─────►│   Redis    │   ← Cache checks happen HERE
  │   Layer      │       │   Cache    │
  └──────┬──────┘       └────────────┘
         │
         ▼
  ┌─────────────┐
  │ Repository  │  ← Only called on cache MISS
  │   Layer     │
  └──────┬──────┘
         │
    ┌────┴────┐
    ▼         ▼
PostgreSQL  MongoDB
```

**Why the service layer?**
- Services already orchestrate business logic — cache is a natural extension
- Services know when data changes and which keys to invalidate
- Repositories stay clean — pure database access, no cache concerns
- Routes stay clean — just request/response handling

### 3.2 Redis Database Allocation

A single Redis instance supports 16 logical databases (db 0–15). Use separate databases per service for clean isolation:

| Database | Service | Purpose |
|----------|---------|---------|
| `db 0` | User Service | User profiles, instructor profiles |
| `db 1` | Course Service | Course data, content, enrollment flags |
| `db 2` | (Reserved) | Future: API Gateway rate limits if migrated from Nginx |
| `db 3` | (Reserved) | Future: Notification Service |

**Why separate databases?** Allows `FLUSHDB` per service without affecting others. Also makes monitoring clearer — you can see memory usage per database.

### 3.3 Key Naming Convention

```
Format: {service}:{entity}:{identifier}:{qualifier}

Examples:
  course:published:p:1:l:20       → Published course list, page 1, limit 20
  course:detail:42                → Course #42 details
  course:content:42               → Course #42 MongoDB content
  course:enrolled:7:42            → Student #7 enrolled in course #42? (boolean)
  course:enrollment_count:42      → Enrollment count for course #42
  user:profile:7                  → User #7 profile
  user:instructor:3               → Instructor profile for user #3
```

**Rules:**
- All lowercase
- Colon `:` as separator (Redis convention, enables pattern matching with `SCAN`)
- Service prefix for namespacing
- No spaces, no special characters

### 3.4 Connection Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DOCKER NETWORK                                     │
│                                                                             │
│  ┌───────────────┐        ┌─────────────┐        ┌───────────────┐         │
│  │  user-service  │───────►│             │◄───────│ course-service │         │
│  │   (db 0)      │        │    REDIS    │        │   (db 1)      │         │
│  └───────────────┘        │   :6379     │        └───────────────┘         │
│                            │             │                                  │
│                            └─────────────┘                                  │
│                                                                             │
│  Each service gets its own async connection pool (max 10 connections).      │
│  Connection URL includes the database number:                               │
│    user-service:   redis://:password@redis:6379/0                           │
│    course-service: redis://:password@redis:6379/1                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Docker & Infrastructure Changes

### 4.1 Redis Container — No Changes Needed

The Redis container is already configured correctly in `docker-compose.yml`:

```yaml
redis:
  image: redis:7-alpine
  container_name: smartcourse-redis
  command: redis-server --requirepass ${REDIS_PASSWORD:-smartcourse_secret}
  ports:
    - "6379:6379"
  volumes:
    - redis_data:/data
  healthcheck:
    test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD:-smartcourse_secret}", "ping"]
    interval: 10s
    timeout: 5s
    retries: 5
  networks:
    - smartcourse-network
```

**No changes needed.** Redis is already running, healthy, and on the Docker network.

### 4.2 `docker-compose.yml` — Add Redis env to Course Service

The course-service currently does NOT have a `REDIS_URL` environment variable. Add it:

**File:** `docker-compose.yml` (root)

Find the `course-service` block and add the `REDIS_URL` env var and `redis` dependency:

```yaml
  course-service:
    build:
      context: ./services/course-service
      dockerfile: Dockerfile
    container_name: smartcourse-course-service
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER:-smartcourse}:${POSTGRES_PASSWORD:-smartcourse_secret}@postgres:5432/${POSTGRES_DB:-smartcourse}
      - MONGODB_URL=mongodb://${MONGO_USER:-smartcourse}:${MONGO_PASSWORD:-smartcourse_secret}@mongodb:27017/${MONGO_DB:-smartcourse}?authSource=admin
      - MONGODB_DB_NAME=${MONGO_DB:-smartcourse}
      - REDIS_URL=redis://:${REDIS_PASSWORD:-smartcourse_secret}@redis:6379/1      # <-- ADD (db 1)
    depends_on:
      postgres:
        condition: service_healthy
      mongodb:
        condition: service_healthy
      redis:                                                                        # <-- ADD
        condition: service_healthy                                                  # <-- ADD
    networks:
      - smartcourse-network
```

**Changes:**
1. Added `REDIS_URL` environment variable with `db 1` (course-service uses database 1)
2. Added `redis` to `depends_on` with health check condition

### 4.3 Verify User Service — Already Has Redis Config

The user-service already has `REDIS_URL` configured in `docker-compose.yml`:

```yaml
  user-service:
    environment:
      - REDIS_URL=redis://:${REDIS_PASSWORD:-smartcourse_secret}@redis:6379/0   # Already exists, db 0
    depends_on:
      redis:
        condition: service_healthy   # Already exists
```

**No changes needed for user-service Docker config.**

### 4.4 Root `.env` — No Changes Needed

```env
REDIS_PASSWORD=smartcourse_secret   # Already exists
```

---

## 5. Shared Module — `core/redis.py` & `core/cache.py`

Both services need a Redis client module and a cache utility module. Since services are independently deployable and the code is small (~50 lines each), **create these files in each service's `core/` directory** rather than a shared package. This keeps services self-contained.

The files are identical in pattern but configured per-service.

### 5.1 `core/redis.py` — Redis Client Management

This module mirrors the pattern of `core/mongodb.py` — global client initialized on startup, closed on shutdown.

```python
"""
Redis client management.

Provides async Redis connection with connection pooling.
Initialize on app startup, close on shutdown.
If Redis is unavailable, the app continues to work (cache misses fall through to DB).
"""

import redis.asyncio as redis
import structlog

logger = structlog.get_logger(__name__)

# Global Redis client (initialized on startup)
_redis_client: redis.Redis | None = None


async def connect_redis(redis_url: str) -> None:
    """
    Initialize Redis connection pool. Call on app startup.

    Args:
        redis_url: Full Redis URL including database number.
                   e.g., redis://:password@redis:6379/0
    """
    global _redis_client
    try:
        _redis_client = redis.from_url(
            redis_url,
            decode_responses=True,   # Return strings, not bytes
            max_connections=10,      # Connection pool size
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        # Verify connection
        await _redis_client.ping()
        logger.info("redis_connected", url=redis_url.split("@")[-1])  # Log without password
    except Exception as e:
        logger.warning("redis_connection_failed", error=str(e))
        _redis_client = None  # App will work without cache


async def close_redis() -> None:
    """Close Redis connection pool. Call on app shutdown."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        logger.info("redis_disconnected")


def get_redis() -> redis.Redis | None:
    """
    Get Redis client instance.

    Returns None if Redis is not connected (graceful degradation).
    """
    return _redis_client
```

### 5.2 `core/cache.py` — Cache Utility Functions

A thin utility layer over the Redis client. All functions are safe — they catch exceptions and return `None` on failure (graceful degradation).

```python
"""
Cache utility functions.

Provides get/set/delete operations with JSON serialization.
All functions are fault-tolerant — if Redis is down, they return None
and the caller falls through to the database.
"""

import json
from typing import Any, Optional

import structlog

from core.redis import get_redis

logger = structlog.get_logger(__name__)


async def cache_get(key: str) -> Optional[Any]:
    """
    Get a value from cache.

    Returns:
        Deserialized Python object, or None on miss/error.
    """
    client = get_redis()
    if not client:
        return None

    try:
        data = await client.get(key)
        if data is not None:
            logger.debug("cache_hit", key=key)
            return json.loads(data)
        logger.debug("cache_miss", key=key)
        return None
    except Exception as e:
        logger.warning("cache_get_error", key=key, error=str(e))
        return None


async def cache_set(key: str, value: Any, ttl: int = 300) -> bool:
    """
    Set a value in cache with TTL.

    Args:
        key: Cache key.
        value: Any JSON-serializable Python object.
        ttl: Time-to-live in seconds (default: 5 minutes).

    Returns:
        True if stored successfully, False otherwise.
    """
    client = get_redis()
    if not client:
        return False

    try:
        serialized = json.dumps(value, default=str)  # default=str handles datetime, Decimal
        await client.set(key, serialized, ex=ttl)
        logger.debug("cache_set", key=key, ttl=ttl)
        return True
    except Exception as e:
        logger.warning("cache_set_error", key=key, error=str(e))
        return False


async def cache_delete(key: str) -> bool:
    """
    Delete a single key from cache.

    Returns:
        True if deleted, False otherwise.
    """
    client = get_redis()
    if not client:
        return False

    try:
        await client.delete(key)
        logger.debug("cache_delete", key=key)
        return True
    except Exception as e:
        logger.warning("cache_delete_error", key=key, error=str(e))
        return False


async def cache_delete_pattern(pattern: str) -> int:
    """
    Delete all keys matching a pattern using SCAN (non-blocking).

    Uses SCAN instead of KEYS to avoid blocking Redis on large datasets.
    Pattern examples: "course:published:*", "course:detail:*"

    Returns:
        Number of keys deleted.
    """
    client = get_redis()
    if not client:
        return 0

    try:
        deleted = 0
        async for key in client.scan_iter(match=pattern, count=100):
            await client.delete(key)
            deleted += 1
        if deleted > 0:
            logger.debug("cache_delete_pattern", pattern=pattern, deleted=deleted)
        return deleted
    except Exception as e:
        logger.warning("cache_delete_pattern_error", pattern=pattern, error=str(e))
        return 0


async def cache_exists(key: str) -> bool:
    """
    Check if a key exists in cache (without fetching the value).
    Useful for boolean flags like enrollment checks.

    Returns:
        True if key exists, False otherwise.
    """
    client = get_redis()
    if not client:
        return False

    try:
        return bool(await client.exists(key))
    except Exception as e:
        logger.warning("cache_exists_error", key=key, error=str(e))
        return False
```

---

## 6. Course Service — File-by-File Changes

### 6.1 `services/course-service/pyproject.toml` — Add Redis Dependency

Add `redis` to the dependencies list:

```toml
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "sqlalchemy>=2.0.25",
    "asyncpg>=0.29.0",
    "psycopg2-binary>=2.9.9",
    "motor>=3.3.0",
    "redis>=5.0.0",                    # <-- ADD THIS LINE
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "python-multipart>=0.0.6",
    "httpx>=0.26.0",
    "opentelemetry-api>=1.22.0",
    "opentelemetry-sdk>=1.22.0",
    "opentelemetry-instrumentation-fastapi>=0.43b0",
    "opentelemetry-instrumentation-sqlalchemy>=0.43b0",
    "prometheus-client>=0.19.0",
    "structlog>=24.1.0",
    "alembic>=1.13.0",
]
```

### 6.2 `services/course-service/Dockerfile` — Add Redis to pip install

Add `redis>=5.0.0` to the `pip install` command in the Dockerfile:

```dockerfile
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    fastapi>=0.109.0 \
    uvicorn[standard]>=0.27.0 \
    sqlalchemy>=2.0.25 \
    asyncpg>=0.29.0 \
    psycopg2-binary>=2.9.9 \
    motor>=3.3.0 \
    redis>=5.0.0 \
    pydantic>=2.5.0 \
    pydantic-settings>=2.1.0 \
    python-multipart>=0.0.6 \
    httpx>=0.26.0 \
    opentelemetry-api>=1.22.0 \
    opentelemetry-sdk>=1.22.0 \
    opentelemetry-instrumentation-fastapi>=0.43b0 \
    opentelemetry-instrumentation-sqlalchemy>=0.43b0 \
    prometheus-client>=0.19.0 \
    structlog>=24.1.0 \
    alembic>=1.13.0
```

### 6.3 `services/course-service/.env.example` — Add REDIS_URL

Append:

```env
# Redis (use service name "redis" inside Docker, "localhost" outside)
REDIS_URL=redis://:smartcourse_secret@localhost:6379/1
```

### 6.4 `services/course-service/src/config.py` — Add REDIS_URL Setting

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # PostgreSQL
    DATABASE_URL: str = "postgresql://smartcourse:smartcourse_secret@localhost:5432/smartcourse"

    # MongoDB
    MONGODB_URL: str = "mongodb://smartcourse:smartcourse_secret@localhost:27017/smartcourse?authSource=admin"
    MONGODB_DB_NAME: str = "smartcourse"

    # Redis
    REDIS_URL: str = "redis://:smartcourse_secret@localhost:6379/1"     # <-- ADD (db 1)

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
```

### 6.5 Create `services/course-service/src/core/redis.py`

Copy the module from [Section 5.1](#51-coreredispy--redis-client-management) — paste it exactly as-is into `services/course-service/src/core/redis.py`.

### 6.6 Create `services/course-service/src/core/cache.py`

Copy the module from [Section 5.2](#52-corecachepy--cache-utility-functions) — paste it exactly as-is into `services/course-service/src/core/cache.py`.

### 6.7 `services/course-service/src/main.py` — Add Redis Startup/Shutdown

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.router import router
from config import settings
from core.database import engine
from core.mongodb import close_mongodb, connect_mongodb
from core.redis import connect_redis, close_redis                     # <-- ADD
from models import Certificate, Course, Enrollment  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    # Connect to MongoDB on startup
    await connect_mongodb()
    # Connect to Redis on startup                                      # <-- ADD
    await connect_redis(settings.REDIS_URL)                            # <-- ADD
    yield
    # Cleanup on shutdown
    await close_redis()                                                # <-- ADD
    await close_mongodb()
    await engine.dispose()


app = FastAPI(
    title="SmartCourse Course Service",
    description="Course management, enrollment, and certification",
    version="0.1.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "course-service"}
```

### 6.8 `services/course-service/src/services/course.py` — Add Caching

This is the most important file. Adding cache to **3 read paths** and invalidation to **3 write paths**.

```python
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import cache_get, cache_set, cache_delete, cache_delete_pattern
from models.course import Course
from repositories.course import CourseRepository
from schemas.course import CourseCreate, CourseUpdate, CourseStatusUpdate


# ── TTL Constants ─────────────────────────────────────────────────
COURSE_DETAIL_TTL = 600       # 10 minutes
COURSE_LIST_TTL = 300         # 5 minutes


class CourseService:
    """Business logic for course operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.course_repo = CourseRepository(db)

    # ── READS (with cache) ────────────────────────────────────────

    async def get_course(self, course_id: int) -> Optional[Course]:
        """Get a single course by ID (excludes soft-deleted)."""
        # 1. Try cache
        cache_key = f"course:detail:{course_id}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        # 2. Fallback to DB
        course = await self.course_repo.get_by_id(course_id)
        if course and course.is_deleted:
            return None

        # 3. Store in cache (serialize SQLAlchemy object to dict)
        if course:
            from schemas.course import CourseResponse
            course_dict = CourseResponse.model_validate(course).model_dump(mode="json")
            await cache_set(cache_key, course_dict, ttl=COURSE_DETAIL_TTL)

        return course

    async def get_course_by_slug(self, slug: str) -> Optional[Course]:
        """Get a course by its URL slug. No cache — slug lookups are rare."""
        return await self.course_repo.get_by_slug(slug)

    async def list_published_courses(self, skip: int = 0, limit: int = 100):
        """List published courses for browsing."""
        # 1. Try cache
        cache_key = f"course:published:p:{skip}:l:{limit}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached["items"], cached["total"]

        # 2. Fallback to DB
        courses = await self.course_repo.get_published(skip=skip, limit=limit)
        total = await self.course_repo.count_published()

        # 3. Store in cache
        from schemas.course import CourseResponse
        items = [CourseResponse.model_validate(c).model_dump(mode="json") for c in courses]
        await cache_set(cache_key, {"items": items, "total": total}, ttl=COURSE_LIST_TTL)

        return courses, total

    async def list_instructor_courses(
        self, instructor_id: int, skip: int = 0, limit: int = 100
    ):
        """List all courses by an instructor. No cache — instructor-specific, low reuse."""
        courses = await self.course_repo.get_by_instructor(instructor_id, skip=skip, limit=limit)
        total = await self.course_repo.count_by_instructor(instructor_id)
        return courses, total

    # ── WRITES (with cache invalidation) ──────────────────────────

    async def create_course(self, data: CourseCreate, instructor_id: int) -> Course:
        """Create a new course. No cache invalidation needed — new courses are drafts."""
        if await self.course_repo.slug_exists(data.slug):
            raise ValueError(f"Slug '{data.slug}' is already taken")

        course_data = data.model_dump()
        course_data["instructor_id"] = instructor_id
        course_data["status"] = "draft"
        return await self.course_repo.create(course_data)

    async def update_course(
        self, course_id: int, data: CourseUpdate, instructor_id: int
    ) -> Optional[Course]:
        """Update course details. Invalidates detail and list caches."""
        course = await self.course_repo.get_by_id(course_id)
        if not course or course.is_deleted:
            return None
        if course.instructor_id != instructor_id:
            raise PermissionError("You do not own this course")

        update_data = data.model_dump(exclude_unset=True)
        result = await self.course_repo.update(course_id, update_data)

        # Invalidate caches
        await cache_delete(f"course:detail:{course_id}")
        await cache_delete_pattern("course:published:*")    # Any listing page could include this course

        return result

    async def update_status(
        self, course_id: int, data: CourseStatusUpdate, instructor_id: int
    ) -> Optional[Course]:
        """Change course status. Invalidates all course caches."""
        course = await self.course_repo.get_by_id(course_id)
        if not course or course.is_deleted:
            return None
        if course.instructor_id != instructor_id:
            raise PermissionError("You do not own this course")

        update_data = {"status": data.status}
        if data.status == "published" and course.status != "published":
            update_data["published_at"] = datetime.utcnow()

        result = await self.course_repo.update(course_id, update_data)

        # Invalidate caches — status change affects listings
        await cache_delete(f"course:detail:{course_id}")
        await cache_delete_pattern("course:published:*")

        return result

    async def delete_course(self, course_id: int, instructor_id: int) -> bool:
        """Soft-delete a course. Invalidates all course caches."""
        course = await self.course_repo.get_by_id(course_id)
        if not course or course.is_deleted:
            return False
        if course.instructor_id != instructor_id:
            raise PermissionError("You do not own this course")

        await self.course_repo.soft_delete(course_id)

        # Invalidate caches
        await cache_delete(f"course:detail:{course_id}")
        await cache_delete_pattern("course:published:*")

        return True
```

**Important note about `list_published_courses` cache return:** When the cache is hit, it returns dicts (not SQLAlchemy objects). The API route must handle both cases. See Section 6.10 for the route adjustment.

### 6.9 `services/course-service/src/services/course_content.py` — Add Caching

```python
from typing import Optional, Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from core.cache import cache_get, cache_set, cache_delete
from repositories.course_content import CourseContentRepository
from schemas.course_content import (
    CourseContentCreate,
    ModuleCreate,
    LessonCreate,
)


# ── TTL Constants ─────────────────────────────────────────────────
CONTENT_TTL = 900    # 15 minutes — content rarely changes after publish


class CourseContentService:
    """Business logic for course content (MongoDB)."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.content_repo = CourseContentRepository(db)

    # ── READS (with cache) ────────────────────────────────────────

    async def get_content(self, course_id: int) -> Optional[dict[str, Any]]:
        """Get full course content by course_id."""
        # 1. Try cache
        cache_key = f"course:content:{course_id}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        # 2. Fallback to MongoDB
        doc = await self.content_repo.get_by_course_id(course_id)
        if doc:
            doc.pop("_id", None)  # Remove MongoDB ObjectId for serialization
            # 3. Store in cache
            await cache_set(cache_key, doc, ttl=CONTENT_TTL)

        return doc

    # ── WRITES (with cache invalidation) ──────────────────────────

    async def create_or_update_content(
        self, course_id: int, data: CourseContentCreate
    ) -> dict[str, Any]:
        """Create or fully replace course content (upsert)."""
        content_data = data.model_dump()

        # Auto-calculate metadata if not provided
        if data.metadata is None:
            total_modules = len(data.modules)
            total_lessons = sum(len(m.lessons) for m in data.modules)
            content_data["metadata"] = {
                "total_modules": total_modules,
                "total_lessons": total_lessons,
                "total_duration_hours": None,
                "tags": [],
            }

        doc = await self.content_repo.upsert(course_id, content_data)
        doc.pop("_id", None)

        # Invalidate content cache
        await cache_delete(f"course:content:{course_id}")

        return doc

    async def add_module(self, course_id: int, data: ModuleCreate) -> Optional[dict[str, Any]]:
        """Add a single module to existing course content."""
        module_data = data.model_dump()
        doc = await self.content_repo.add_module(course_id, module_data)
        if doc:
            doc.pop("_id", None)
            # Invalidate content cache
            await cache_delete(f"course:content:{course_id}")
        return doc

    async def add_lesson(
        self, course_id: int, module_id: int, data: LessonCreate
    ) -> Optional[dict[str, Any]]:
        """Add a single lesson to a specific module."""
        lesson_data = data.model_dump()
        doc = await self.content_repo.add_lesson_to_module(course_id, module_id, lesson_data)
        if doc:
            doc.pop("_id", None)
            # Invalidate content cache
            await cache_delete(f"course:content:{course_id}")
        return doc

    async def delete_content(self, course_id: int) -> bool:
        """Delete all content for a course."""
        result = await self.content_repo.delete(course_id)

        # Invalidate content cache
        await cache_delete(f"course:content:{course_id}")

        return result
```

### 6.10 `services/course-service/src/services/enrollment.py` — Add Enrollment Cache

Only caching the **enrollment existence check** and **enrollment count** — NOT full enrollment data.

```python
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import cache_get, cache_set, cache_delete, cache_delete_pattern
from models.enrollment import Enrollment
from repositories.enrollment import EnrollmentRepository
from repositories.course import CourseRepository
from schemas.enrollment import EnrollmentCreate, ProgressUpdate


# ── TTL Constants ─────────────────────────────────────────────────
ENROLLMENT_FLAG_TTL = 1800     # 30 minutes — enrollment status rarely changes
ENROLLMENT_COUNT_TTL = 300     # 5 minutes


class EnrollmentService:
    """Business logic for enrollment and progress operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.enrollment_repo = EnrollmentRepository(db)
        self.course_repo = CourseRepository(db)

    # ── CACHED HELPERS ────────────────────────────────────────────

    async def _is_enrolled_cached(self, student_id: int, course_id: int) -> bool:
        """Check enrollment with cache. Used internally."""
        cache_key = f"course:enrolled:{student_id}:{course_id}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached  # True or False

        is_enrolled = await self.enrollment_repo.is_enrolled(student_id, course_id)
        await cache_set(cache_key, is_enrolled, ttl=ENROLLMENT_FLAG_TTL)
        return is_enrolled

    async def _get_enrollment_count_cached(self, course_id: int) -> int:
        """Get enrollment count with cache. Used for limit checks and display."""
        cache_key = f"course:enrollment_count:{course_id}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        count = await self.enrollment_repo.count_by_course(course_id)
        await cache_set(cache_key, count, ttl=ENROLLMENT_COUNT_TTL)
        return count

    # ── READS ─────────────────────────────────────────────────────

    async def enroll_student(self, student_id: int, data: EnrollmentCreate) -> Enrollment:
        """Enroll a student in a course."""
        # Check course exists and is published
        course = await self.course_repo.get_by_id(data.course_id)
        if not course or course.is_deleted:
            raise ValueError("Course not found")
        if course.status != "published":
            raise ValueError("Course is not available for enrollment")

        # Check max_students limit (uses cached count)
        if course.max_students:
            current_count = await self._get_enrollment_count_cached(data.course_id)
            if current_count >= course.max_students:
                raise ValueError("Course enrollment limit reached")

        # Check not already enrolled (uses cached flag)
        if await self._is_enrolled_cached(student_id, data.course_id):
            raise ValueError("Already enrolled in this course")

        enrollment_data = {
            "student_id": student_id,
            "course_id": data.course_id,
            "status": "active",
            "payment_amount": data.payment_amount,
            "payment_status": "completed" if data.payment_amount else None,
            "enrollment_source": data.enrollment_source,
        }
        enrollment = await self.enrollment_repo.create(enrollment_data)

        # Invalidate enrollment caches
        await cache_set(
            f"course:enrolled:{student_id}:{data.course_id}", True, ttl=ENROLLMENT_FLAG_TTL
        )
        await cache_delete(f"course:enrollment_count:{data.course_id}")

        return enrollment

    async def get_enrollment(self, enrollment_id: int) -> Optional[Enrollment]:
        """Get a single enrollment by ID. No cache — low frequency, user-specific."""
        return await self.enrollment_repo.get_by_id(enrollment_id)

    async def get_student_enrollments(
        self, student_id: int, skip: int = 0, limit: int = 100
    ):
        """List all enrollments for a student. No cache — user-specific."""
        enrollments = await self.enrollment_repo.get_by_student(student_id, skip=skip, limit=limit)
        total = await self.enrollment_repo.count_by_student(student_id)
        return enrollments, total

    async def get_course_enrollments(
        self, course_id: int, skip: int = 0, limit: int = 100
    ):
        """List all enrollments for a course (instructor view). No cache."""
        enrollments = await self.enrollment_repo.get_by_course(course_id, skip=skip, limit=limit)
        total = await self.enrollment_repo.count_by_course(course_id)
        return enrollments, total

    async def update_progress(
        self, enrollment_id: int, student_id: int, data: ProgressUpdate
    ) -> Optional[Enrollment]:
        """Update student progress on a course. No cache — frequent writes."""
        enrollment = await self.enrollment_repo.get_by_id(enrollment_id)
        if not enrollment:
            return None
        if enrollment.student_id != student_id:
            raise PermissionError("This is not your enrollment")

        update_data: dict = {"last_accessed_at": datetime.utcnow()}

        # Mark lesson as completed
        if data.lesson_id is not None:
            completed = list(enrollment.completed_lessons or [])
            if data.lesson_id not in completed:
                completed.append(data.lesson_id)
                update_data["completed_lessons"] = completed

            # Recalculate completion percentage
            total = enrollment.total_lessons
            if total > 0:
                update_data["completion_percentage"] = round(
                    (len(completed) / total) * 100, 2
                )

        # Mark module as completed
        if data.module_id is not None:
            completed_mods = list(enrollment.completed_modules or [])
            if data.module_id not in completed_mods:
                completed_mods.append(data.module_id)
                update_data["completed_modules"] = completed_mods

        # Add time spent
        if data.time_spent_minutes is not None:
            update_data["time_spent_minutes"] = (
                enrollment.time_spent_minutes + data.time_spent_minutes
            )

        # Set started_at on first progress update
        if enrollment.started_at is None:
            update_data["started_at"] = datetime.utcnow()

        # Auto-complete if 100%
        pct = update_data.get("completion_percentage", float(enrollment.completion_percentage))
        if pct >= 100 and enrollment.status == "active":
            update_data["status"] = "completed"
            update_data["completed_at"] = datetime.utcnow()

        return await self.enrollment_repo.update(enrollment_id, update_data)

    async def drop_enrollment(self, enrollment_id: int, student_id: int) -> Optional[Enrollment]:
        """Student drops a course."""
        enrollment = await self.enrollment_repo.get_by_id(enrollment_id)
        if not enrollment:
            return None
        if enrollment.student_id != student_id:
            raise PermissionError("This is not your enrollment")

        result = await self.enrollment_repo.update(enrollment_id, {
            "status": "dropped",
            "dropped_at": datetime.utcnow(),
        })

        # Invalidate enrollment caches
        await cache_delete(f"course:enrolled:{student_id}:{enrollment.course_id}")
        await cache_delete(f"course:enrollment_count:{enrollment.course_id}")

        return result
```

### 6.11 `services/course-service/src/api/courses.py` — Handle Cached List Returns

The `list_published_courses` cache returns dicts instead of SQLAlchemy objects. Update the route to handle both cases:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from api.dependencies import get_current_user_id, require_instructor
from schemas.course import (
    CourseCreate,
    CourseUpdate,
    CourseStatusUpdate,
    CourseResponse,
    CourseListResponse,
)
from services.course import CourseService

router = APIRouter()


@router.post("/", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
async def create_course(
    data: CourseCreate,
    instructor_id: int = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """Create a new course (instructors only)."""
    service = CourseService(db)
    try:
        course = await service.create_course(data, instructor_id)
        return CourseResponse.model_validate(course)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/", response_model=CourseListResponse)
async def list_published_courses(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List all published courses (any authenticated user)."""
    service = CourseService(db)
    courses, total = await service.list_published_courses(skip=skip, limit=limit)

    # Handle both SQLAlchemy objects (cache miss) and dicts (cache hit)
    if courses and isinstance(courses[0], dict):
        items = [CourseResponse(**c) for c in courses]
    else:
        items = [CourseResponse.model_validate(c) for c in courses]

    return CourseListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/my-courses", response_model=CourseListResponse)
async def list_my_courses(
    skip: int = 0,
    limit: int = 20,
    instructor_id: int = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """List courses created by the current instructor."""
    service = CourseService(db)
    courses, total = await service.list_instructor_courses(instructor_id, skip=skip, limit=limit)
    return CourseListResponse(
        items=[CourseResponse.model_validate(c) for c in courses],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{course_id}", response_model=CourseResponse)
async def get_course(
    course_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a single course by ID."""
    service = CourseService(db)
    course = await service.get_course(course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    # Handle both SQLAlchemy object (cache miss) and dict (cache hit)
    if isinstance(course, dict):
        return CourseResponse(**course)
    return CourseResponse.model_validate(course)


@router.put("/{course_id}", response_model=CourseResponse)
async def update_course(
    course_id: int,
    data: CourseUpdate,
    instructor_id: int = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """Update a course (owning instructor only)."""
    service = CourseService(db)
    try:
        course = await service.update_course(course_id, data, instructor_id)
        if not course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
        return CourseResponse.model_validate(course)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.patch("/{course_id}/status", response_model=CourseResponse)
async def update_course_status(
    course_id: int,
    data: CourseStatusUpdate,
    instructor_id: int = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """Change course status — publish, archive, etc. (owning instructor only)."""
    service = CourseService(db)
    try:
        course = await service.update_status(course_id, data, instructor_id)
        if not course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
        return CourseResponse.model_validate(course)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_course(
    course_id: int,
    instructor_id: int = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a course (owning instructor only)."""
    service = CourseService(db)
    try:
        deleted = await service.delete_course(course_id, instructor_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
```

---

## 7. User Service — File-by-File Changes

The user-service already has `redis>=5.0.0` in `pyproject.toml` and `REDIS_URL` in `config.py`. Only code additions are needed.

### 7.1 `services/user-service/pyproject.toml` — No Changes

`redis>=5.0.0` is already listed in dependencies.

### 7.2 `services/user-service/src/user_service/config.py` — No Changes

`REDIS_URL` is already defined:

```python
REDIS_URL: str = "redis://:smartcourse_secret@localhost:6379/0"
```

### 7.3 Create `services/user-service/src/user_service/core/redis.py`

**Identical to the course-service version** — copy from [Section 5.1](#51-coreredispy--redis-client-management).

Place at: `services/user-service/src/user_service/core/redis.py`

The import path for config differs — update the file to use the user-service import style. The module itself doesn't import config (it receives `redis_url` as a parameter), so no changes needed.

### 7.4 Create `services/user-service/src/user_service/core/cache.py`

**Identical to the course-service version** — copy from [Section 5.2](#52-corecachepy--cache-utility-functions).

Place at: `services/user-service/src/user_service/core/cache.py`

**One change needed:** Update the import path for `get_redis`:

```python
from user_service.core.redis import get_redis    # user-service uses user_service. prefix
```

### 7.5 `services/user-service/src/user_service/main.py` — Add Redis Startup/Shutdown

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager

from user_service.api.router import router
from user_service.config import settings
from user_service.core.database import engine
from user_service.core.redis import connect_redis, close_redis       # <-- ADD
from user_service.models import User, InstructorProfile  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    await connect_redis(settings.REDIS_URL)                           # <-- ADD
    yield
    await close_redis()                                               # <-- ADD
    await engine.dispose()


app = FastAPI(
    title="SmartCourse User Service",
    description="User authentication and profile management",
    version="0.1.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "user-service"}
```

### 7.6 `services/user-service/src/user_service/services/user.py` — Add Caching

You need to add caching to the user profile and instructor profile reads, and invalidation on writes.

**Read the existing file first**, then add cache logic to these methods:

```python
from user_service.core.cache import cache_get, cache_set, cache_delete

# ── TTL Constants ─────────────────────────────────────────────────
USER_PROFILE_TTL = 900           # 15 minutes
INSTRUCTOR_PROFILE_TTL = 1800    # 30 minutes
```

**Methods to add caching to:**

```python
async def get_user_by_id(self, user_id: int):
    """Get user by ID — with cache."""
    # 1. Try cache
    cache_key = f"user:profile:{user_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    # 2. Fallback to DB
    user = await self.user_repo.get_by_id(user_id)

    # 3. Store in cache
    if user:
        from user_service.schemas.user import UserResponse
        user_dict = UserResponse.model_validate(user).model_dump(mode="json")
        await cache_set(cache_key, user_dict, ttl=USER_PROFILE_TTL)

    return user
```

**Methods to add invalidation to:**

```python
async def update_user(self, user_id: int, data) -> ...:
    """Update user profile — invalidate cache."""
    result = await self.user_repo.update(user_id, ...)
    await cache_delete(f"user:profile:{user_id}")
    return result
```

**Instructor profile caching** — if there's a `get_instructor_profile` method:

```python
async def get_instructor_profile(self, user_id: int):
    """Get instructor profile — with cache."""
    cache_key = f"user:instructor:{user_id}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    profile = await self.instructor_repo.get_by_user_id(user_id)
    if profile:
        # Serialize and cache
        profile_dict = InstructorResponse.model_validate(profile).model_dump(mode="json")
        await cache_set(cache_key, profile_dict, ttl=INSTRUCTOR_PROFILE_TTL)

    return profile
```

> **Note to implementor:** The user-service has existing service methods in `services/user.py` and `services/auth.py`. Read each method and decide:
> - `get_user_by_id` → ADD cache
> - `update_user`/`update_profile` → ADD invalidation for `user:profile:{id}`
> - `get_instructor_profile` → ADD cache
> - `update_instructor_profile` → ADD invalidation for `user:instructor:{id}`
> - `register`, `login`, `refresh_token` → NO cache (auth flows should always hit DB)

---

## 8. Cache Invalidation Strategy

### 8.1 Invalidation Matrix

| Operation | Keys to Invalidate | Pattern |
|-----------|-------------------|---------|
| **Course updated** | `course:detail:{id}`, `course:published:*` | Direct delete + pattern |
| **Course published** | `course:detail:{id}`, `course:published:*` | Direct delete + pattern |
| **Course archived/deleted** | `course:detail:{id}`, `course:published:*` | Direct delete + pattern |
| **Content updated** | `course:content:{course_id}` | Direct delete |
| **Module/lesson added** | `course:content:{course_id}` | Direct delete |
| **Student enrolls** | `course:enrolled:{s}:{c}` (set True), `course:enrollment_count:{c}` (delete) | Set + delete |
| **Student drops** | `course:enrolled:{s}:{c}` (delete), `course:enrollment_count:{c}` (delete) | Direct delete |
| **User profile updated** | `user:profile:{id}` | Direct delete |
| **Instructor profile updated** | `user:instructor:{user_id}` | Direct delete |

### 8.2 Pattern-Based Invalidation

For course listings, we use `cache_delete_pattern("course:published:*")` which scans all keys matching the pattern and deletes them. This is safe because:

- We use `SCAN` (non-blocking) instead of `KEYS` (blocking)
- The number of listing keys is small (roughly `total_pages × limit_variants`, typically < 50 keys)
- This only happens on writes (publish, update, delete), which are infrequent

### 8.3 Cross-Service Cache Invalidation (Future — Kafka)

Currently, user-service and course-service cache independently. If the instructor profile changes (user-service), the course-service doesn't know to re-fetch instructor data displayed on course pages.

**Current approach:** This is fine for now. Instructor profiles are served directly from user-service endpoints. Course-service doesn't cache instructor data — it only caches its own entities.

**Future approach (when Kafka events are implemented):**

```
User-Service publishes: user.profile_updated {user_id: 7}
    ↓
Course-Service consumes → invalidates any cross-service caches
```

This is NOT needed for the initial implementation. Only add it when services start caching each other's data.

---

## 9. Health Checks & Monitoring

### 9.1 Enhanced Health Check — Both Services

Update the `/health` endpoint in both services to include Redis status:

```python
from core.redis import get_redis


@app.get("/health")
async def health_check():
    """Health check endpoint with dependency status."""
    redis_ok = False
    client = get_redis()
    if client:
        try:
            await client.ping()
            redis_ok = True
        except Exception:
            pass

    return {
        "status": "ok",
        "service": "course-service",    # or "user-service"
        "dependencies": {
            "redis": "connected" if redis_ok else "disconnected",
        },
    }
```

### 9.2 Cache Metrics (Optional — Add Later)

For production observability, add Prometheus metrics for cache hit/miss rates. This is optional for the initial implementation but recommended for production.

Add to `core/cache.py`:

```python
from prometheus_client import Counter

cache_hits = Counter("cache_hits_total", "Total cache hits", ["key_prefix"])
cache_misses = Counter("cache_misses_total", "Total cache misses", ["key_prefix"])
```

Then in `cache_get`:

```python
if data is not None:
    cache_hits.labels(key_prefix=key.split(":")[0]).inc()
else:
    cache_misses.labels(key_prefix=key.split(":")[0]).inc()
```

This lets you track hit rates per entity type (course, user, etc.) in Grafana.

---

## 10. Production Notes

### 10.1 Memory Policy

Configure Redis to evict keys when memory is full. Add to the Redis `command` in `docker-compose.yml`:

```yaml
redis:
  command: >
    redis-server
    --requirepass ${REDIS_PASSWORD:-smartcourse_secret}
    --maxmemory 256mb
    --maxmemory-policy allkeys-lru
```

| Policy | Description |
|--------|-------------|
| `allkeys-lru` | Evict least-recently-used keys from ALL keys (recommended for caching) |
| `256mb` | Sufficient for the SmartCourse caching workload. Adjust based on actual usage. |

### 10.2 Redis Persistence

The current `redis:7-alpine` image saves data to disk by default (RDB snapshots). For a pure cache, you can disable persistence to improve performance:

```yaml
command: >
  redis-server
  --requirepass ${REDIS_PASSWORD:-smartcourse_secret}
  --maxmemory 256mb
  --maxmemory-policy allkeys-lru
  --save ""
  --appendonly no
```

**However**, keep persistence if you want cache to survive Redis restarts (e.g., during deployments). For a small cache, the performance difference is negligible. **Recommendation: keep default persistence for now.**

### 10.3 Connection Pooling

Both `core/redis.py` implementations use `max_connections=10`. This creates a connection pool of up to 10 concurrent Redis connections per service. For the current workload (2 services, single Redis), this is optimal.

| Setting | Value | Rationale |
|---------|-------|-----------|
| `max_connections` | 10 | Handles concurrent requests without exhausting Redis |
| `socket_connect_timeout` | 5s | Fail fast if Redis is unreachable |
| `socket_timeout` | 5s | Don't wait forever for a response |
| `retry_on_timeout` | True | Auto-retry on network hiccup |
| `decode_responses` | True | Get strings instead of bytes (simplifies JSON handling) |

### 10.4 Scaling to Redis Sentinel / Cluster

When you need high availability in production:

1. **Redis Sentinel** (recommended for moderate scale):
   - Provides automatic failover with master/replica
   - Change `redis.from_url()` to `redis.Sentinel()`
   - Only requires config change, not code change

2. **Redis Cluster** (for large scale):
   - Shards data across multiple nodes
   - Requires code change — no `SELECT` (database switching) or `SCAN` across nodes
   - Switch from `cache_delete_pattern` to explicit key tracking

**For SmartCourse's current scale, single Redis is more than sufficient.** A single Redis instance handles 100,000+ ops/sec. Upgrade to Sentinel only when you need HA guarantees.

### 10.5 Docker Compose — Updated `docker-compose.yml` Redis Config (Optional)

If you want to apply the memory policy now, update the `redis` service:

```yaml
  redis:
    image: redis:7-alpine
    container_name: smartcourse-redis
    command: >
      redis-server
      --requirepass ${REDIS_PASSWORD:-smartcourse_secret}
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test:
        ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD:-smartcourse_secret}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - smartcourse-network
```

---

## Checklist

### Docker & Infrastructure
- [ ] `docker-compose.yml` → course-service has `REDIS_URL` env var pointing to `redis:6379/1`
- [ ] `docker-compose.yml` → course-service `depends_on` includes `redis` with health check
- [ ] `docker-compose.yml` → (optional) redis command includes `--maxmemory 256mb --maxmemory-policy allkeys-lru`
- [ ] Root `.env` → `REDIS_PASSWORD` already exists (no changes needed)

### Course Service
- [ ] `pyproject.toml` → `redis>=5.0.0` added to dependencies
- [ ] `Dockerfile` → `redis>=5.0.0` added to pip install
- [ ] `.env.example` → `REDIS_URL` added
- [ ] `src/config.py` → `REDIS_URL` setting added
- [ ] `src/core/redis.py` → Created (Redis client management)
- [ ] `src/core/cache.py` → Created (Cache utilities)
- [ ] `src/main.py` → `connect_redis` / `close_redis` added to lifespan
- [ ] `src/services/course.py` → Cache added to `get_course`, `list_published_courses`; invalidation added to `update_course`, `update_status`, `delete_course`
- [ ] `src/services/course_content.py` → Cache added to `get_content`; invalidation added to `create_or_update_content`, `add_module`, `add_lesson`, `delete_content`
- [ ] `src/services/enrollment.py` → Enrollment flag cache and count cache added; invalidation on `enroll_student`, `drop_enrollment`
- [ ] `src/api/courses.py` → Updated to handle both dict (cache hit) and ORM object (cache miss) responses

### User Service
- [ ] `pyproject.toml` → `redis>=5.0.0` already exists (no changes)
- [ ] `src/user_service/core/redis.py` → Created (Redis client management)
- [ ] `src/user_service/core/cache.py` → Created (Cache utilities, updated import path)
- [ ] `src/user_service/main.py` → `connect_redis` / `close_redis` added to lifespan
- [ ] `src/user_service/services/user.py` → Cache added to `get_user_by_id`, `get_instructor_profile`; invalidation added to `update_user`, `update_instructor_profile`

### Verification
- [ ] `docker compose build` succeeds
- [ ] `docker compose up -d` — all containers healthy
- [ ] `redis-cli -a smartcourse_secret -p 6379 ping` returns `PONG`
- [ ] First `GET /courses/` → cache miss (loads from DB)
- [ ] Second `GET /courses/` → cache hit (fast, no DB query)
- [ ] `PUT /courses/{id}` → cache invalidated, next GET loads fresh from DB
- [ ] Redis down → services still work (just slower)
- [ ] Check Redis keys: `redis-cli -a smartcourse_secret -p 6379 KEYS "*"` shows expected patterns

---

## Summary

| Metric | Value |
|--------|-------|
| **Total cache points** | 7 (5 in course-service, 2 in user-service) |
| **New files created** | 4 (2 × `core/redis.py`, 2 × `core/cache.py`) |
| **Files modified** | ~8 (configs, main.py, service files, one route file) |
| **Docker changes** | 1 line in docker-compose (REDIS_URL for course-service) |
| **TTLs** | 5–30 minutes depending on data volatility |
| **Memory footprint** | < 50MB for typical course catalog (well within 256MB limit) |
| **Degradation** | Graceful — app works without Redis, just hits DB directly |

---

_Document Version: 1.0 | Created: February 12, 2026_
