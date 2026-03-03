# Implementation Plan: Remove `generate-all` & Fix Generation Status Tracking via Redis

## Overview

Two changes:
1. **Remove** the `/modules/{module_id}/generate-all` endpoint and all its artifacts (schema, service method, route, imports).
2. **Implement proper generation status tracking** using Redis with TTL-based ephemeral keys so the `/modules/{module_id}/generation-status` endpoint returns accurate `PENDING → IN_PROGRESS → COMPLETED / FAILED` states.

---

## Part 1: Remove `generate-all` Endpoint

### Files to modify:

#### 1. `src/ai_service/schemas/instructor.py`
- **Delete** the `GenerateAllRequest` class (lines 95–115).
- **Delete** the `GenerateAllResponse` class (lines 118–124).

#### 2. `src/ai_service/services/instructor.py`
- **Delete** the entire `generate_all()` method (lines 400–486).
- **Remove** `GenerateAllRequest` and `GenerateAllResponse` from the imports at the top (lines 18–19).

#### 3. `src/ai_service/api/instructor.py`
- **Delete** the entire `generate_all` route handler (lines 115–139).
- **Remove** `GenerateAllRequest` and `GenerateAllResponse` from the import block (lines 17–18).

That's it. No other files reference `generate-all`.

---

## Part 2: Proper Generation Status Tracking via Redis

### Why Redis?

- You already have Redis connected in `main.py` lifespan (`connect_redis` / `close_redis`) and the `get_redis()` helper exists in `core/redis.py`.
- Redis is the standard solution for ephemeral, fast-expiring status keys — no need for Postgres or MongoDB writes.
- Keys auto-expire via TTL, so no cleanup needed.
- Sub-millisecond reads make it ideal for 3-second polling.

### Redis Key Design

```
generation_status:{course_id}:{module_id}:summary   → JSON string
generation_status:{course_id}:{module_id}:quiz       → JSON string
```

**Value format** (JSON):
```json
{
  "status": "in_progress",          // "in_progress" | "completed" | "failed"
  "started_at": "2026-03-03T12:00:00Z",
  "completed_at": null,             // set on completion/failure
  "error": null                     // set on failure (short message)
}
```

**TTL**: 1 hour (3600 seconds). Keys auto-expire after 1 hour — long enough for any polling window, short enough to not accumulate garbage.

---

### New File: `src/ai_service/services/generation_status.py`

Create a small, focused status tracker class that wraps Redis operations.

```python
"""Generation status tracker using Redis."""

import json
from datetime import datetime, timezone

from redis.asyncio import Redis

from ai_service.schemas.common import GenerationStatus


# Keys expire after 1 hour — plenty of time for polling, no manual cleanup needed
_TTL_SECONDS = 3600


def _key(course_id: int, module_id: str, content_type: str) -> str:
    """Build Redis key for generation status."""
    return f"generation_status:{course_id}:{module_id}:{content_type}"


class GenerationStatusTracker:
    """Tracks in-flight generation status in Redis."""

    def __init__(self, redis: Redis):
        self._redis = redis

    async def set_in_progress(self, course_id: int, module_id: str, content_type: str) -> None:
        """Mark a generation task as in-progress. Call this BEFORE starting LLM work."""
        payload = json.dumps({
            "status": GenerationStatus.IN_PROGRESS.value,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "error": None,
        })
        await self._redis.set(_key(course_id, module_id, content_type), payload, ex=_TTL_SECONDS)

    async def set_completed(self, course_id: int, module_id: str, content_type: str) -> None:
        """Mark a generation task as completed. Call this AFTER successful save."""
        payload = json.dumps({
            "status": GenerationStatus.COMPLETED.value,
            "started_at": None,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": None,
        })
        await self._redis.set(_key(course_id, module_id, content_type), payload, ex=_TTL_SECONDS)

    async def set_failed(self, course_id: int, module_id: str, content_type: str, error: str) -> None:
        """Mark a generation task as failed. Call this in the except block."""
        payload = json.dumps({
            "status": GenerationStatus.FAILED.value,
            "started_at": None,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": error[:500],  # Truncate long error messages
        })
        await self._redis.set(_key(course_id, module_id, content_type), payload, ex=_TTL_SECONDS)

    async def get_status(self, course_id: int, module_id: str, content_type: str) -> dict | None:
        """Get current generation status. Returns parsed dict or None if no key exists."""
        raw = await self._redis.get(_key(course_id, module_id, content_type))
        if raw is None:
            return None
        return json.loads(raw)
```

---

### Modify: `src/ai_service/api/instructor.py` — Inject Redis into the service

Update `get_instructor_service()` to pass Redis (and the status tracker) to `InstructorService`:

```python
from ai_service.core.redis import get_redis
from ai_service.services.generation_status import GenerationStatusTracker

def get_instructor_service() -> InstructorService:
    db = get_mongodb()
    if db is None:
        raise RuntimeError("MongoDB connection not initialized")

    redis = get_redis()
    if redis is None:
        raise RuntimeError("Redis connection not initialized")

    repo = CourseContentRepository(db)
    openai_client = OpenAIClient()
    course_client = CourseServiceClient()
    resource_extractor = ResourceTextExtractor()
    status_tracker = GenerationStatusTracker(redis)

    return InstructorService(repo, openai_client, course_client, resource_extractor, status_tracker)
```

---

### Modify: `src/ai_service/services/instructor.py`

#### A. Update constructor to accept `GenerationStatusTracker`

```python
from ai_service.services.generation_status import GenerationStatusTracker

class InstructorService:
    def __init__(
        self,
        repo: CourseContentRepository,
        openai_client: OpenAIClient,
        course_client: CourseServiceClient,
        resource_extractor: ResourceTextExtractor,
        status_tracker: GenerationStatusTracker,  # NEW
    ):
        self.repo = repo
        self.openai_client = openai_client
        self.course_client = course_client
        self.resource_extractor = resource_extractor
        self.status_tracker = status_tracker  # NEW
```

#### B. Update `_process_and_save_summary()` — add status tracking

```python
async def _process_and_save_summary(self, course_id, module_id, request, user_id):
    try:
        # ✅ Mark IN_PROGRESS before doing any work
        await self.status_tracker.set_in_progress(course_id, module_id, "summary")

        # ... existing fetch, extract, LLM, persist logic stays the same ...

        # ✅ Mark COMPLETED after successful save
        if result:
            await self.status_tracker.set_completed(course_id, module_id, "summary")
            logger.info("Summary generated and saved successfully", ...)
        else:
            await self.status_tracker.set_failed(course_id, module_id, "summary", "Failed to save to course-service")
            logger.warning("Summary generated but failed to save", ...)

    except Exception as e:
        # ✅ Mark FAILED on error
        await self.status_tracker.set_failed(course_id, module_id, "summary", str(e))
        logger.exception("Error during summary generation", ...)
```

#### C. Update `_process_and_save_quiz()` — same pattern

```python
async def _process_and_save_quiz(self, course_id, module_id, request, user_id):
    try:
        # ✅ Mark IN_PROGRESS before doing any work
        await self.status_tracker.set_in_progress(course_id, module_id, "quiz")

        # ... existing fetch, extract, LLM, persist logic stays the same ...

        # ✅ Mark COMPLETED after successful save
        if result:
            await self.status_tracker.set_completed(course_id, module_id, "quiz")
            logger.info("Quiz generated and saved successfully", ...)
        else:
            await self.status_tracker.set_failed(course_id, module_id, "quiz", "Failed to save to course-service")
            logger.warning("Quiz generated but failed to save", ...)

    except Exception as e:
        # ✅ Mark FAILED on error
        await self.status_tracker.set_failed(course_id, module_id, "quiz", str(e))
        logger.exception("Error during quiz generation", ...)
```

#### D. Rewrite `get_generation_status()` — use Redis + MongoDB fallback

The logic should be:

1. **Check Redis first** (for in-flight or recently completed tasks).
2. **Fall back to MongoDB** (for tasks completed before Redis keys expired, i.e., content that already exists).
3. If neither Redis nor MongoDB has data → status is `NOT_STARTED` (we'll add this enum value).

```python
async def get_generation_status(self, course_id: int, module_id: str) -> GenerationStatusResponse:
    # 1. Check Redis for active/recent status
    redis_summary = await self.status_tracker.get_status(course_id, module_id, "summary")
    redis_quiz = await self.status_tracker.get_status(course_id, module_id, "quiz")

    # 2. Determine summary status
    if redis_summary:
        summary_status = GenerationStatus(redis_summary["status"])
        summary_error = redis_summary.get("error")
    else:
        # Fallback: check if content already exists in MongoDB
        existing = await self.repo.get_existing_summary(course_id, module_id)
        summary_status = GenerationStatus.COMPLETED if existing else GenerationStatus.NOT_STARTED
        summary_error = None

    # 3. Determine quiz status
    if redis_quiz:
        quiz_status = GenerationStatus(redis_quiz["status"])
        quiz_error = redis_quiz.get("error")
    else:
        existing = await self.repo.get_existing_quiz(course_id, module_id)
        quiz_status = GenerationStatus.COMPLETED if existing else GenerationStatus.NOT_STARTED
        quiz_error = None

    # 4. Determine last_generation_at from whichever source has data
    last_generation_at = None
    for redis_data in [redis_summary, redis_quiz]:
        if redis_data and redis_data.get("completed_at"):
            ts = datetime.fromisoformat(redis_data["completed_at"])
            if not last_generation_at or ts > last_generation_at:
                last_generation_at = ts

    # Fallback timestamps from MongoDB if no Redis data
    if not last_generation_at:
        for getter in [self.repo.get_existing_summary, self.repo.get_existing_quiz]:
            doc = await getter(course_id, module_id)
            if doc and doc.get("created_at"):
                ts = doc["created_at"]
                if not last_generation_at or ts > last_generation_at:
                    last_generation_at = ts

    return GenerationStatusResponse(
        course_id=course_id,
        module_id=module_id,
        summary_status=summary_status,
        quiz_status=quiz_status,
        summary_error=summary_error,
        quiz_error=quiz_error,
        last_generation_at=last_generation_at,
    )
```

---

### Modify: `src/ai_service/schemas/common.py` — Add `NOT_STARTED` enum

```python
class GenerationStatus(str, Enum):
    NOT_STARTED = "not_started"       # NEW — nothing has been generated yet
    PENDING = "pending"                # Request accepted, task queued
    IN_PROGRESS = "in_progress"        # Background task is running
    COMPLETED = "completed"            # Done successfully
    FAILED = "failed"                  # Task errored out
```

Remove `NOT_IMPLEMENTED` — it was a placeholder and no longer needed.

---

### Modify: `src/ai_service/schemas/instructor.py` — Update `GenerationStatusResponse`

```python
class GenerationStatusResponse(BaseModel):
    """Response for GET /modules/{module_id}/generation-status."""

    course_id: int
    module_id: str
    summary_status: GenerationStatus = GenerationStatus.NOT_STARTED
    quiz_status: GenerationStatus = GenerationStatus.NOT_STARTED
    summary_error: str | None = None      # NEW — populated when summary_status is FAILED
    quiz_error: str | None = None         # NEW — populated when quiz_status is FAILED
    last_generation_at: datetime | None = None
```

Remove the `message` field — status + error fields are self-describing.

---

## Summary of All Changes

| File | Action |
|------|--------|
| `schemas/common.py` | Replace `NOT_IMPLEMENTED` with `NOT_STARTED` in `GenerationStatus` |
| `schemas/instructor.py` | Delete `GenerateAllRequest`, `GenerateAllResponse`. Update `GenerationStatusResponse` (add error fields, remove message, update defaults). |
| `api/instructor.py` | Delete `generate_all` route. Remove its imports. Add Redis + status tracker to DI function. |
| `services/instructor.py` | Delete `generate_all()`. Add `status_tracker` to constructor. Add `set_in_progress` / `set_completed` / `set_failed` calls in both background tasks. Rewrite `get_generation_status()` to use Redis-first + MongoDB-fallback. |
| `services/generation_status.py` | **NEW FILE** — `GenerationStatusTracker` class wrapping Redis get/set with TTL. |

---

## How the Frontend Should Poll

```
1. Instructor clicks "Generate Summary" (or Quiz)
2. Frontend POSTs to /generate-summary (or /generate-quiz)
3. Gets back 202 with status: "pending"
4. Frontend starts polling GET /generation-status?course_id=X every 3 seconds
5. Response will show:
   - summary_status: "in_progress"  ← show spinner
   - quiz_status: "not_started"
6. After ~10-30 seconds:
   - summary_status: "completed"    ← hide spinner, show content
   - quiz_status: "not_started"
7. Frontend stops polling when target status is "completed" or "failed"
8. If "failed", show summary_error or quiz_error to the user
```

---

## Flow Diagram

```
┌─────────────┐     POST /generate-summary      ┌──────────────────┐
│  Frontend   │ ────────────────────────────────→ │   API Router     │
│  (Polling)  │ ←──── 202 { status: "pending" }  │                  │
│             │                                   │  Validates auth  │
│             │                                   │  + ownership     │
│             │                                   └────────┬─────────┘
│             │                                            │
│             │                                  asyncio.create_task()
│             │                                            │
│             │                                            ▼
│             │                                   ┌────────────────────┐
│             │                                   │  Background Task   │
│             │                                   │                    │
│             │                                   │  1. Redis SET      │
│             │                                   │     status=        │
│             │                                   │     "in_progress"  │
│             │                                   │                    │
│             │    GET /generation-status          │  2. Fetch content  │
│             │ ──────────────────────────→        │  3. Extract PDFs   │
│             │ ←── { summary_status:              │  4. Call LLM       │
│             │      "in_progress" }               │  5. Save to        │
│             │                                   │     course-service │
│             │    GET /generation-status          │                    │
│             │ ──────────────────────────→        │  6. Redis SET      │
│             │ ←── { summary_status:              │     status=        │
│             │      "completed" }                 │     "completed"    │
│             │                                   └────────────────────┘
│  ✅ Done!   │
└─────────────┘
```

---

## Notes

- **No Postgres/MongoDB writes** for status — Redis only (as requested).
- **TTL handles cleanup** — no cron jobs, no manual deletion.
- **Scalable** — if you add more generation types later (e.g., flashcards), just use a new `content_type` string like `"flashcards"` with the same tracker.
- **Redis is already wired** — `connect_redis()` runs in lifespan, `get_redis()` returns the client. Zero new infrastructure.
- **Idempotent** — calling generate again just overwrites the Redis key, restarting the status cycle.
