# AI Service Implementation Guide for SmartCourse

> **Purpose**: This document is a complete implementation specification for the `ai-service` microservice. It is intended to be followed step-by-step by an engineer or LLM to produce a working (stub) service that is architecturally consistent with the existing SmartCourse monorepo.

---

## Table of Contents

1. [Service Overview](#1-service-overview)
2. [Architecture & Role](#2-architecture--role)
3. [Directory & File Structure](#3-directory--file-structure)
4. [Configuration (`config.py`)](#4-configuration-configpy)
5. [Application Startup (`main.py`)](#5-application-startup-mainpy)
6. [Authentication & Dependencies](#6-authentication--dependencies)
7. [Pydantic Schemas](#7-pydantic-schemas)
8. [API Endpoints](#8-api-endpoints)
9. [Service Layer](#9-service-layer)
10. [Repository Layer](#10-repository-layer)
11. [Dockerfile & `pyproject.toml`](#11-dockerfile--pyprojecttoml)
12. [Docker Compose Integration](#12-docker-compose-integration)
13. [Shared Module Usage](#13-shared-module-usage)
14. [Implementation Constraints](#14-implementation-constraints)
15. [Deliverables Checklist](#15-deliverables-checklist)

---

## 1. Service Overview

The **ai-service** is a new FastAPI microservice that provides three capabilities:

| Capability | Description | Router Prefix |
|---|---|---|
| **Instructor Content Generation** | Generate module summaries and quiz questions from lesson content | `/api/v1/ai/instructor` |
| **Student AI Tutor** | RAG-powered conversational tutoring scoped by course/module/lesson | `/api/v1/ai/tutor` |
| **RAG Indexing** | Build and manage vector indexes of course content | `/api/v1/ai/index` |

**Port**: `8009` (as defined in the system design doc).

In the **initial implementation phase**, all endpoint handlers are stubs. They validate input and return placeholder JSON responses. No real LLM calls, no vector database operations, and no direct MongoDB writes from this service.

---

## 2. Architecture & Role

```
┌─────────────┐       ┌──────────────────┐       ┌────────────────┐
│  API Gateway │──────▶│   ai-service     │──────▶│  course-service│
│  (port 8000) │       │   (port 8009)    │       │  (port 8002)   │
└─────────────┘       └──────────────────┘       └────────────────┘
                             │                          │
                             │ (future)                 │
                             ▼                          ▼
                      ┌──────────┐              ┌──────────┐
                      │  Qdrant  │              │ MongoDB  │
                      │ (vectors)│              │ (content)│
                      └──────────┘              └──────────┘
```

**Key architectural decisions:**

- The ai-service does **not** write directly to MongoDB in phase 1. Generated content will eventually be persisted via internal HTTP calls to `course-service` or through shared MongoDB repositories (TBD in phase 2).
- Authentication follows the same gateway pattern as all other services: the API Gateway verifies JWTs and forwards `X-User-ID` and `X-User-Role` headers.
- The ai-service connects to **MongoDB** (read-only in phase 1, to fetch course/module/lesson content), **Redis** (caching), and **Kafka** (event publishing, stubbed initially).
- Future phases will add **Qdrant** for vector storage and **OpenAI** (or equivalent) for LLM/embedding calls.

---

## 3. Directory & File Structure

Create the following structure under `services/ai-service/`:

```
services/ai-service/
├── .env                          # Environment variables (see Section 4)
├── Dockerfile                    # Container build (see Section 11)
├── pyproject.toml                # Dependencies (see Section 11)
└── src/
    ├── __init__.py               # Empty
    ├── config.py                 # Settings (pydantic-settings)
    ├── main.py                   # FastAPI app, lifespan, health check
    ├── api/
    │   ├── __init__.py
    │   ├── dependencies.py       # Auth helpers (X-User-ID, X-User-Role)
    │   ├── router.py             # Aggregates all sub-routers
    │   ├── instructor.py         # Instructor content generation endpoints
    │   ├── tutor.py              # Student AI tutor endpoints
    │   └── index.py              # RAG indexing endpoints
    ├── schemas/
    │   ├── __init__.py
    │   ├── common.py             # Shared enums, base models
    │   ├── instructor.py         # Instructor generation request/response schemas
    │   ├── tutor.py              # Tutor session/message schemas
    │   └── index.py              # Index build/status schemas
    ├── services/
    │   ├── __init__.py
    │   ├── instructor.py         # Instructor generation business logic (stubs)
    │   ├── tutor.py              # Tutor business logic (stubs)
    │   └── index.py              # RAG indexing business logic (stubs)
    ├── repositories/
    │   ├── __init__.py
    │   ├── course_content.py     # Read course/module/lesson data from MongoDB
    │   └── vector_store.py       # Future: Qdrant operations (stub)
    └── core/
        ├── __init__.py
        ├── mongodb.py            # MongoDB connection (same pattern as course-service)
        └── redis.py              # Redis connection (same pattern as course-service)
```

### Naming Conventions

Follow the existing repo conventions:
- **File names**: No folder prefix. Use `repositories/course_content.py`, NOT `repositories/course_content_repository.py`.
- **Collection names**: `snake_case` — `course_content`, `module_quizzes`, `module_summaries`.
- **Field names**: `snake_case` — `course_id`, `module_id`, `lesson_id`.
- **ID formats**: `course_id` is `int` (PostgreSQL auto-increment). `module_id` and `lesson_id` are `str` (bson ObjectId hex strings). `session_id` for tutor is `str` (uuid4 hex).

---

## 4. Configuration (`config.py`)

Model after `services/course-service/src/config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """AI Service settings loaded from environment variables."""

    # MongoDB (read-only access to course content)
    MONGODB_URL: str
    MONGODB_DB_NAME: str

    # Redis (caching)
    REDIS_URL: str

    # Kafka (event publishing — stubbed initially)
    KAFKA_BOOTSTRAP_SERVERS: str
    SCHEMA_REGISTRY_URL: str

    # Course Service (internal HTTP calls — future use)
    COURSE_SERVICE_URL: str = "http://course-service:8002"

    # LLM Provider (future use — stub for now)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # Qdrant (future use — stub for now)
    QDRANT_URL: str = "http://qdrant:6333"
    QDRANT_COLLECTION: str = "course_embeddings"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()  # type: ignore[call-arg]
```

### `.env` file template

```env
MONGODB_URL=mongodb://user:password@mongodb:27017/smartcourse?authSource=admin
MONGODB_DB_NAME=smartcourse
REDIS_URL=redis://:password@redis:6379/0
KAFKA_BOOTSTRAP_SERVERS=kafka:29092
SCHEMA_REGISTRY_URL=http://schema-registry:8081
COURSE_SERVICE_URL=http://course-service:8002
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=course_embeddings
```

---

## 5. Application Startup (`main.py`)

Follow the exact pattern from `services/course-service/src/main.py`:

```python
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.router import router
from config import settings
from core.mongodb import connect_mongodb, close_mongodb
from core.redis import connect_redis, close_redis, get_redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    await connect_mongodb()
    await connect_redis(settings.REDIS_URL)

    # TODO: Initialize Kafka producer (same pattern as course-service)
    # TODO: Initialize Qdrant client
    # TODO: Initialize LLM client

    yield

    await close_redis()
    await close_mongodb()


app = FastAPI(
    title="SmartCourse AI Service",
    description="AI-powered content generation, tutoring, and indexing",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)


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
        "service": "ai-service",
        "dependencies": {
            "redis": "connected" if redis_ok else "disconnected",
        },
    }
```

---

## 6. Authentication & Dependencies

Create `api/dependencies.py` identical to the course-service pattern:

```python
from fastapi import HTTPException, Request, status


def get_current_user_id(request: Request) -> int:
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return int(user_id)


def get_current_user_role(request: Request) -> str:
    role = request.headers.get("X-User-Role")
    if not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return role


def require_instructor(request: Request) -> int:
    user_id = get_current_user_id(request)
    role = get_current_user_role(request)
    if role not in ("instructor", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Instructor role required",
        )
    return user_id


def require_student(request: Request) -> int:
    user_id = get_current_user_id(request)
    role = get_current_user_role(request)
    if role not in ("student", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student role required",
        )
    return user_id


def get_authenticated_user(request: Request) -> tuple[int, str]:
    user_id = get_current_user_id(request)
    role = get_current_user_role(request)
    return user_id, role
```

---

## 7. Pydantic Schemas

All schemas go under `src/schemas/`. These MUST align with existing course-service schemas (see `services/course-service/src/schemas/quiz_summary.py`).

### 7.1 Common Enums and Base Models (`schemas/common.py`)

```python
from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class GenerationStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NOT_IMPLEMENTED = "not_implemented"


class DifficultyLevel(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class QuestionType(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"
    MULTIPLE_SELECT = "multiple_select"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"


class ContentScope(str, Enum):
    """Scope level for AI operations."""
    COURSE = "course"
    MODULE = "module"
    LESSON = "lesson"


class IndexStatus(str, Enum):
    PENDING = "pending"
    INDEXING = "indexing"
    INDEXED = "indexed"
    FAILED = "failed"
    STALE = "stale"


class BaseTimestampSchema(BaseModel):
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
```

### 7.2 Instructor Generation Schemas (`schemas/instructor.py`)

These schemas define the request/response structures for AI-powered summary and quiz generation. They are designed to be **compatible** with the existing `QuizResponse`, `SummaryResponse`, `QuizGenerateRequest`, and `SummaryGenerateRequest` schemas in course-service.

```python
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from schemas.common import (
    GenerationStatus,
    DifficultyLevel,
    QuestionType,
)


# ── Summary Generation ──────────────────────────────────────────────


class GenerateSummaryRequest(BaseModel):
    """Request body for POST /modules/{module_id}/generate-summary."""

    source_lesson_ids: Optional[list[str]] = Field(
        None,
        description="Specific lesson IDs to use. If omitted, all lessons in the module are used.",
    )
    include_glossary: bool = True
    include_key_points: bool = True
    include_learning_objectives: bool = True
    language: str = Field("en", max_length=10)
    tone: Optional[str] = Field(
        None,
        description="Desired tone: 'formal', 'conversational', 'academic'. Optional.",
    )
    max_length_words: Optional[int] = Field(None, ge=50, le=5000)


class GenerateSummaryResponse(BaseModel):
    """Response for summary generation request."""

    course_id: int
    module_id: str
    source_lesson_ids: list[str] = Field(default_factory=list)
    summary_id: Optional[str] = Field(
        None,
        description="MongoDB _id of the persisted summary (populated after generation).",
    )
    status: GenerationStatus = GenerationStatus.NOT_IMPLEMENTED
    message: str = "Summary generation is not yet implemented."
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


# ── Quiz Generation ──────────────────────────────────────────────────


class GenerateQuizRequest(BaseModel):
    """Request body for POST /modules/{module_id}/generate-quiz."""

    source_lesson_ids: Optional[list[str]] = Field(
        None,
        description="Specific lesson IDs to use. If omitted, all lessons in the module are used.",
    )
    num_questions: int = Field(5, ge=1, le=20)
    difficulty: Optional[DifficultyLevel] = None
    question_types: list[QuestionType] = Field(
        default_factory=lambda: [
            QuestionType.MULTIPLE_CHOICE,
            QuestionType.TRUE_FALSE,
        ],
    )
    passing_score: int = Field(70, ge=0, le=100)
    max_attempts: int = Field(3, ge=1)
    time_limit_minutes: Optional[int] = Field(None, ge=1)
    language: str = Field("en", max_length=10)


class GenerateQuizResponse(BaseModel):
    """Response for quiz generation request."""

    course_id: int
    module_id: str
    source_lesson_ids: list[str] = Field(default_factory=list)
    quiz_id: Optional[str] = Field(
        None,
        description="MongoDB _id of the persisted quiz (populated after generation).",
    )
    question_count: int = 0
    status: GenerationStatus = GenerationStatus.NOT_IMPLEMENTED
    message: str = "Quiz generation is not yet implemented."
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


# ── Combined Generation ──────────────────────────────────────────────


class GenerateAllRequest(BaseModel):
    """Request body for POST /modules/{module_id}/generate-all."""

    source_lesson_ids: Optional[list[str]] = None

    # Summary options
    include_glossary: bool = True
    include_key_points: bool = True
    include_learning_objectives: bool = True
    summary_language: str = Field("en", max_length=10)

    # Quiz options
    num_questions: int = Field(5, ge=1, le=20)
    difficulty: Optional[DifficultyLevel] = None
    question_types: list[QuestionType] = Field(
        default_factory=lambda: [
            QuestionType.MULTIPLE_CHOICE,
            QuestionType.TRUE_FALSE,
        ],
    )
    quiz_language: str = Field("en", max_length=10)


class GenerateAllResponse(BaseModel):
    """Response for combined summary + quiz generation."""

    course_id: int
    module_id: str
    summary: GenerateSummaryResponse
    quiz: GenerateQuizResponse


# ── Generation Status ────────────────────────────────────────────────


class GenerationStatusResponse(BaseModel):
    """Response for GET /modules/{module_id}/generation-status."""

    course_id: int
    module_id: str
    summary_status: GenerationStatus = GenerationStatus.NOT_IMPLEMENTED
    quiz_status: GenerationStatus = GenerationStatus.NOT_IMPLEMENTED
    last_generation_at: Optional[datetime] = None
    message: str = "Generation status tracking is not yet implemented."
```

### 7.3 Tutor Schemas (`schemas/tutor.py`)

```python
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field
from uuid import uuid4


class CreateSessionRequest(BaseModel):
    """Request body for POST /sessions."""

    course_id: int
    module_id: Optional[str] = Field(
        None,
        description="Scope the tutor to a specific module.",
    )
    lesson_id: Optional[str] = Field(
        None,
        description="Scope the tutor to a specific lesson.",
    )
    initial_message: Optional[str] = Field(
        None,
        description="Optional first question to immediately ask.",
    )


class SessionResponse(BaseModel):
    """Response for tutor session creation."""

    session_id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="Unique session identifier.",
    )
    student_id: int
    course_id: int
    module_id: Optional[str] = None
    lesson_id: Optional[str] = None
    is_active: bool = True
    initial_reply: Optional[str] = Field(
        None,
        description="AI reply to the initial message (placeholder).",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SendMessageRequest(BaseModel):
    """Request body for POST /sessions/{session_id}/messages."""

    message: str = Field(..., min_length=1, max_length=5000)
    module_id: Optional[str] = Field(
        None,
        description="Optionally narrow or change the scope to a module.",
    )
    lesson_id: Optional[str] = Field(
        None,
        description="Optionally narrow or change the scope to a lesson.",
    )


class MessageResponse(BaseModel):
    """A single message in a tutor conversation."""

    message_id: str = Field(default_factory=lambda: uuid4().hex)
    session_id: str
    role: Literal["user", "assistant"]
    content: str
    module_id: Optional[str] = None
    lesson_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SendMessageResponse(BaseModel):
    """Response for sending a message to the tutor."""

    user_message: MessageResponse
    assistant_message: MessageResponse
```

### 7.4 Index Schemas (`schemas/index.py`)

```python
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from schemas.common import IndexStatus


class BuildIndexRequest(BaseModel):
    """Optional body for build requests (both course and module level)."""

    force_rebuild: bool = Field(
        False,
        description="If True, rebuild even if content hasn't changed.",
    )


class IndexBuildResponse(BaseModel):
    """Response for triggering an index build."""

    course_id: int
    module_id: Optional[str] = None
    status: IndexStatus = IndexStatus.PENDING
    message: str = "Index building is not yet implemented."
    requested_at: datetime = Field(default_factory=datetime.utcnow)


class IndexStatusResponse(BaseModel):
    """Response for checking index build status."""

    course_id: int
    module_id: Optional[str] = None
    status: IndexStatus = IndexStatus.PENDING
    total_chunks: int = 0
    embedding_model: Optional[str] = None
    last_build_at: Optional[datetime] = None
    error_message: Optional[str] = None
    message: str = "Index status tracking is not yet implemented."
```

### 7.5 RAG Metadata Design

When indexing is eventually implemented, each vector chunk stored in Qdrant **MUST** include the following metadata fields so that retrieval can be filtered at any scope level (course, module, or lesson):

```python
# Example Qdrant point payload structure (for reference — not a Pydantic model)
{
    "course_id": 42,               # int — FK to PostgreSQL courses.id
    "module_id": "6a8b9c...",      # str — bson ObjectId hex
    "lesson_id": "3d4e5f...",      # str — bson ObjectId hex
    "chunk_index": 0,              # int — position within the source document
    "content_type": "text",        # str — one of: "lesson-content", "pdf", "video-transcript"
    "resource_id": "abc123...",    # str — bson ObjectId hex (if from a resource), else null
    "resource_url": "https://...", # str — S3 URL of the original resource, if applicable
    "text": "The actual chunk...", # str — the text content of this chunk
    "metadata": {
        "course_title": "...",
        "module_title": "...",
        "lesson_title": "...",
    }
}
```

This design allows the tutor to filter retrieval by:
- **Course scope**: `filter: { course_id: 42 }`
- **Module scope**: `filter: { course_id: 42, module_id: "6a8b9c..." }`
- **Lesson scope**: `filter: { course_id: 42, module_id: "6a8b9c...", lesson_id: "3d4e5f..." }`

---

## 8. API Endpoints

### 8.1 Router Aggregation (`api/router.py`)

```python
from fastapi import APIRouter

from api import instructor, tutor, index

router = APIRouter()

router.include_router(
    instructor.router,
    prefix="/api/v1/ai/instructor",
    tags=["Instructor Content Generation"],
)
router.include_router(
    tutor.router,
    prefix="/api/v1/ai/tutor",
    tags=["Student AI Tutor"],
)
router.include_router(
    index.router,
    prefix="/api/v1/ai/index",
    tags=["RAG Indexing"],
)
```

### 8.2 Instructor Content Generation (`api/instructor.py`)

All endpoints require the `instructor` or `admin` role (use `require_instructor` dependency).

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/modules/{module_id}/generate-summary` | Generate a summary for a module |
| `POST` | `/modules/{module_id}/generate-quiz` | Generate quiz questions for a module |
| `POST` | `/modules/{module_id}/generate-all` | Generate both summary and quiz |
| `GET`  | `/modules/{module_id}/generation-status` | Check generation status |

#### `POST /modules/{module_id}/generate-summary`

- **Path params**: `module_id: str` (bson ObjectId hex)
- **Query params**: `course_id: int` (required — needed to look up the module in `course_content`)
- **Body**: `GenerateSummaryRequest`
- **Response** `200`: `GenerateSummaryResponse`
- **Auth**: `require_instructor`
- **Behavior (stub)**:
  1. Validate that `course_id` and `module_id` exist in MongoDB `course_content` collection.
  2. If `source_lesson_ids` is provided, validate they exist in the module.
  3. Return `GenerateSummaryResponse` with `status="not_implemented"`.
  4. `# TODO: Call instructor service to generate summary via LLM.`
  5. `# TODO: Persist result via course-service quiz/summary CRUD (POST or PUT to module_summaries).`

#### `POST /modules/{module_id}/generate-quiz`

- **Path params**: `module_id: str`
- **Query params**: `course_id: int` (required)
- **Body**: `GenerateQuizRequest`
- **Response** `200`: `GenerateQuizResponse`
- **Auth**: `require_instructor`
- **Behavior (stub)**:
  1. Validate `course_id` and `module_id` exist.
  2. If `source_lesson_ids` is provided, validate they exist in the module.
  3. Return `GenerateQuizResponse` with `status="not_implemented"`.
  4. `# TODO: Call instructor service to generate quiz via LLM.`
  5. `# TODO: Persist result via course-service quiz CRUD (POST or PUT to module_quizzes).`

#### `POST /modules/{module_id}/generate-all`

- **Path params**: `module_id: str`
- **Query params**: `course_id: int` (required)
- **Body**: `GenerateAllRequest`
- **Response** `200`: `GenerateAllResponse`
- **Auth**: `require_instructor`
- **Behavior (stub)**: Combines the logic of both summary and quiz generation. Returns both sub-responses with `status="not_implemented"`.

#### `GET /modules/{module_id}/generation-status`

- **Path params**: `module_id: str`
- **Query params**: `course_id: int` (required)
- **Response** `200`: `GenerationStatusResponse`
- **Auth**: `require_instructor`
- **Behavior (stub)**: Return `GenerationStatusResponse` with both statuses set to `"not_implemented"`.

### 8.3 Student AI Tutor (`api/tutor.py`)

Tutor endpoints require any authenticated user (use `get_authenticated_user` dependency). In phase 2, the service should verify that the student is enrolled in the course.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions` | Create a new tutor session |
| `POST` | `/sessions/{session_id}/messages` | Send a message in an existing session |

#### `POST /sessions`

- **Body**: `CreateSessionRequest`
- **Response** `201`: `SessionResponse`
- **Auth**: `get_authenticated_user` → extracts `student_id`
- **Behavior (stub)**:
  1. Generate a `session_id` (uuid4 hex).
  2. `# TODO: Validate that the student is enrolled in the course.`
  3. `# TODO: If module_id/lesson_id provided, validate they exist.`
  4. If `initial_message` is provided, set `initial_reply` to `"AI tutor is not yet implemented."`.
  5. Return `SessionResponse`.
  6. `# TODO: Persist session to PostgreSQL ai_conversations table.`
  7. `# TODO: If initial_message provided, perform RAG retrieval and LLM call.`

#### `POST /sessions/{session_id}/messages`

- **Path params**: `session_id: str`
- **Body**: `SendMessageRequest`
- **Response** `200`: `SendMessageResponse`
- **Auth**: `get_authenticated_user`
- **Behavior (stub)**:
  1. `# TODO: Validate session exists and belongs to the authenticated user.`
  2. Create a `MessageResponse` for the user message.
  3. Create a `MessageResponse` for the assistant reply with `content="AI tutor is not yet implemented."`.
  4. Return `SendMessageResponse` with both messages.
  5. `# TODO: Perform RAG retrieval filtered by session scope (course/module/lesson).`
  6. `# TODO: Call LLM with retrieved context + conversation history.`
  7. `# TODO: Persist both messages to PostgreSQL ai_messages table.`

### 8.4 RAG Indexing (`api/index.py`)

Index endpoints require the `instructor` or `admin` role.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/courses/{course_id}/build` | Build index for entire course |
| `POST` | `/modules/{module_id}/build` | Build index for a single module |
| `GET`  | `/courses/{course_id}/status` | Get index status for a course |
| `GET`  | `/modules/{module_id}/status` | Get index status for a module |

#### `POST /courses/{course_id}/build`

- **Path params**: `course_id: int`
- **Body** (optional): `BuildIndexRequest`
- **Response** `202`: `IndexBuildResponse`
- **Auth**: `require_instructor`
- **Behavior (stub)**:
  1. `# TODO: Validate course exists in course_content collection.`
  2. Return `IndexBuildResponse` with `status="pending"` and message `"Index building is not yet implemented."`.
  3. `# TODO: Kick off async indexing job (read all modules/lessons, chunk, embed, store in Qdrant).`

#### `POST /modules/{module_id}/build`

- **Path params**: `module_id: str`
- **Query params**: `course_id: int` (required)
- **Body** (optional): `BuildIndexRequest`
- **Response** `202`: `IndexBuildResponse`
- **Auth**: `require_instructor`
- **Behavior (stub)**: Same as course-level but scoped to one module.

#### `GET /courses/{course_id}/status`

- **Path params**: `course_id: int`
- **Response** `200`: `IndexStatusResponse`
- **Auth**: `require_instructor`
- **Behavior (stub)**: Return `IndexStatusResponse` with `status="pending"`.

#### `GET /modules/{module_id}/status`

- **Path params**: `module_id: str`
- **Query params**: `course_id: int` (required)
- **Response** `200`: `IndexStatusResponse`
- **Auth**: `require_instructor`
- **Behavior (stub)**: Same as course-level but scoped to one module.

---

## 9. Service Layer

Create service classes under `src/services/` following the course-service pattern (plain classes with async methods, no dependency injection framework).

### 9.1 `services/instructor.py`

```python
class InstructorService:
    """Handles AI content generation for instructors."""

    async def generate_summary(
        self, course_id: int, module_id: str, request: GenerateSummaryRequest
    ) -> GenerateSummaryResponse:
        # TODO: Fetch module content from MongoDB via CourseContentRepository
        # TODO: If source_lesson_ids provided, filter to those lessons
        # TODO: Optionally fetch lesson resources from S3
        # TODO: Call LLM to generate summary
        # TODO: Persist via course-service summary CRUD (POST/PUT to module_summaries)
        # TODO: Publish "summary.generated" event to Kafka
        return GenerateSummaryResponse(
            course_id=course_id,
            module_id=module_id,
            status=GenerationStatus.NOT_IMPLEMENTED,
        )

    async def generate_quiz(
        self, course_id: int, module_id: str, request: GenerateQuizRequest
    ) -> GenerateQuizResponse:
        # TODO: Same flow as summary but for quiz generation
        # TODO: Validate generated quiz structure matches QuizQuestionCreate schema
        # TODO: Persist via course-service quiz CRUD (POST/PUT to module_quizzes)
        # TODO: Set authorship.source = "ai_generated", authorship.ai_model = settings.OPENAI_MODEL
        # TODO: Publish "quiz.generated" event to Kafka
        return GenerateQuizResponse(
            course_id=course_id,
            module_id=module_id,
            status=GenerationStatus.NOT_IMPLEMENTED,
        )

    async def generate_all(
        self, course_id: int, module_id: str, request: GenerateAllRequest
    ) -> GenerateAllResponse:
        # TODO: Run summary and quiz generation (can be parallel)
        ...

    async def get_generation_status(
        self, course_id: int, module_id: str
    ) -> GenerationStatusResponse:
        # TODO: Check if quiz/summary exist for this module and their generation metadata
        ...
```

### 9.2 `services/tutor.py`

```python
class TutorService:
    """Handles AI tutor sessions and messages."""

    async def create_session(
        self, student_id: int, request: CreateSessionRequest
    ) -> SessionResponse:
        # TODO: Verify student enrollment via course-service or direct DB query
        # TODO: Persist session to PostgreSQL
        # TODO: If initial_message, perform RAG + LLM call
        ...

    async def send_message(
        self, session_id: str, user_id: int, request: SendMessageRequest
    ) -> SendMessageResponse:
        # TODO: Validate session ownership
        # TODO: Embed user question via OpenAI embeddings
        # TODO: Search Qdrant for relevant chunks (filtered by session scope)
        # TODO: Build prompt with context + conversation history
        # TODO: Call LLM and stream response
        # TODO: Persist both messages to PostgreSQL
        ...
```

### 9.3 `services/index.py`

```python
class IndexService:
    """Handles RAG index building and status."""

    async def build_course_index(
        self, course_id: int, request: BuildIndexRequest
    ) -> IndexBuildResponse:
        # TODO: Read all modules/lessons from course_content collection
        # TODO: For each lesson: extract text content or download resource from S3
        # TODO: Chunk content (512 tokens, 10% overlap)
        # TODO: Generate embeddings via OpenAI
        # TODO: Store vectors in Qdrant with metadata (course_id, module_id, lesson_id, etc.)
        # TODO: Update rag_index_status in PostgreSQL
        # TODO: Publish "rag.indexed" or "rag.failed" event to Kafka
        ...

    async def build_module_index(
        self, course_id: int, module_id: str, request: BuildIndexRequest
    ) -> IndexBuildResponse:
        # TODO: Same as course-level but for a single module
        ...

    async def get_course_status(self, course_id: int) -> IndexStatusResponse:
        # TODO: Query rag_index_status table
        ...

    async def get_module_status(
        self, course_id: int, module_id: str
    ) -> IndexStatusResponse:
        # TODO: Query rag_index_status table filtered by module
        ...
```

---

## 10. Repository Layer

### 10.1 `repositories/course_content.py`

This repository reads from the **existing** MongoDB collections managed by course-service. It is **read-only** in the ai-service.

```python
class CourseContentRepository:
    """Read-only access to course content in MongoDB."""

    def __init__(self, db):
        self.course_content = db["course_content"]
        self.module_quizzes = db["module_quizzes"]
        self.module_summaries = db["module_summaries"]

    async def get_course_content(self, course_id: int) -> dict | None:
        """Fetch the full course_content document for a course."""
        return await self.course_content.find_one({"course_id": course_id})

    async def get_module(self, course_id: int, module_id: str) -> dict | None:
        """Fetch a specific module from course_content."""
        doc = await self.course_content.find_one(
            {"course_id": course_id, "modules.module_id": module_id},
            {"modules.$": 1},
        )
        if doc and doc.get("modules"):
            return doc["modules"][0]
        return None

    async def get_lessons_for_module(
        self, course_id: int, module_id: str, lesson_ids: list[str] | None = None
    ) -> list[dict]:
        """Fetch lessons for a module, optionally filtered by lesson_ids."""
        module = await self.get_module(course_id, module_id)
        if not module:
            return []
        lessons = module.get("lessons", [])
        if lesson_ids:
            lessons = [l for l in lessons if l["lesson_id"] in lesson_ids]
        return lessons

    async def get_existing_quiz(self, course_id: int, module_id: str) -> dict | None:
        """Check if a quiz already exists for this module."""
        return await self.module_quizzes.find_one(
            {"course_id": course_id, "module_id": module_id, "is_active": True}
        )

    async def get_existing_summary(self, course_id: int, module_id: str) -> dict | None:
        """Check if a summary already exists for this module."""
        return await self.module_summaries.find_one(
            {"course_id": course_id, "module_id": module_id, "is_active": True}
        )
```

### 10.2 `repositories/vector_store.py`

```python
class VectorStoreRepository:
    """Qdrant vector store operations — stub for phase 1."""

    # TODO: Initialize Qdrant client in __init__

    async def upsert_chunks(
        self,
        course_id: int,
        module_id: str,
        lesson_id: str,
        chunks: list[dict],
    ) -> int:
        """Store embedding chunks with metadata. Returns count stored."""
        # TODO: Implement Qdrant upsert
        raise NotImplementedError("Vector store not yet implemented")

    async def search(
        self,
        query_embedding: list[float],
        course_id: int,
        module_id: str | None = None,
        lesson_id: str | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        """Search for relevant chunks, filtered by scope."""
        # TODO: Implement Qdrant search with metadata filters
        raise NotImplementedError("Vector store not yet implemented")

    async def delete_course_vectors(self, course_id: int) -> int:
        """Delete all vectors for a course. Returns count deleted."""
        # TODO: Implement Qdrant delete by filter
        raise NotImplementedError("Vector store not yet implemented")

    async def delete_module_vectors(self, course_id: int, module_id: str) -> int:
        """Delete all vectors for a module. Returns count deleted."""
        # TODO: Implement Qdrant delete by filter
        raise NotImplementedError("Vector store not yet implemented")
```

---

## 11. Dockerfile & `pyproject.toml`

### 11.1 `pyproject.toml`

Follow the exact pattern from `services/course-service/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "smartcourse-ai-service"
version = "0.1.0"
description = "SmartCourse AI Service — content generation, tutoring, and indexing"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "motor>=3.3.0",
    "redis>=5.0.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "httpx>=0.26.0",
    "structlog>=24.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "httpx>=0.26.0",
    "ruff>=0.1.0",
    "black>=24.1.0",
    "mypy>=1.8.0",
]

# Future AI dependencies (add when implementing real logic):
# ai = [
#     "openai>=1.12.0",
#     "langchain>=0.3.0",
#     "langgraph>=0.2.0",
#     "qdrant-client>=1.12.0",
#     "tiktoken>=0.5.0",
# ]

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]

[tool.ruff]
line-length = 100
select = ["E", "F", "I", "N", "W"]

[tool.black]
line-length = 100

[tool.mypy]
python_version = "3.11"
strict = true
```

### 11.2 `Dockerfile`

Follow the exact pattern from `services/course-service/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install shared library
COPY shared/pyproject.toml /tmp/shared/pyproject.toml
COPY shared/src/shared /tmp/shared/src/shared
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir /tmp/shared

# Copy only pyproject.toml first for better caching
COPY services/ai-service/pyproject.toml .

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    fastapi>=0.109.0 \
    uvicorn[standard]>=0.27.0 \
    motor>=3.3.0 \
    redis>=5.0.0 \
    pydantic>=2.5.0 \
    pydantic-settings>=2.1.0 \
    httpx>=0.26.0 \
    structlog>=24.1.0

COPY services/ai-service/src/ ./src/

# Install the package in editable mode
RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/src:/app
EXPOSE 8009

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8009"]
```

> **Note**: No `alembic` in the ai-service Dockerfile. The ai-service does not manage its own PostgreSQL migrations in phase 1. When PostgreSQL tables are needed (ai_conversations, ai_messages, rag_index_status), they will be added in a future phase.

---

## 12. Docker Compose Integration

Add the following service block to the root `docker-compose.yml`:

```yaml
  ai-service:
    build:
      context: .
      dockerfile: services/ai-service/Dockerfile
    container_name: smartcourse-ai-service
    volumes:
      - ./services/ai-service/src:/app/src:ro
    env_file:
      - ./.env
      - ./services/ai-service/.env
    depends_on:
      mongodb:
        condition: service_healthy
      redis:
        condition: service_healthy
      kafka:
        condition: service_healthy
      schema-registry:
        condition: service_healthy
    networks:
      - smartcourse-network
```

Also add `ai-service` to the `api-gateway` service's `depends_on` list, and configure the nginx reverse proxy to route `/api/v1/ai/` to the ai-service on port 8009.

Add a Kafka topic for AI events in the `kafka-init` service command:

```bash
kafka-topics --bootstrap-server kafka:29092 --create --if-not-exists --topic ai.events --partitions 3 --replication-factor 1
```

---

## 13. Shared Module Usage

The ai-service should import and use these shared utilities from `shared/src/shared/`:

| Module | Usage |
|--------|-------|
| `shared.exceptions.common.NotFoundError` | Raise when course/module/lesson not found in MongoDB |
| `shared.exceptions.common.BadRequestError` | Raise for invalid input beyond Pydantic validation |
| `shared.kafka.producer.EventProducer` | Publish AI events (stubbed initially) |
| `shared.kafka.topics.Topics` | Use topic constants (add `AI = "ai.events"` to the enum) |
| `shared.schemas.envelope.EventEnvelope` | Wrap events for Kafka |
| `shared.storage.s3.S3Uploader` | Download lesson resources from S3 (future use for PDF parsing) |

When adding the `AI` topic, update `shared/src/shared/kafka/topics.py`:

```python
class Topics(str, Enum):
    # ... existing topics ...
    AI = "ai.events"
```

---

## 14. Implementation Constraints

The implementer **MUST** follow these constraints:

1. **Follow existing conventions**: Match the architectural and coding style of `services/course-service` and `services/user-service` exactly — file naming, import style, error handling, logging, config pattern.

2. **Stub endpoints only**: All endpoint handlers validate input and return simple placeholder JSON. No real LLM calls, no real vector DB operations.

3. **No external AI providers**: Do not call OpenAI or any other LLM provider. Configuration placeholders are included but should not be used yet.

4. **No direct MongoDB writes**: The ai-service reads from MongoDB but does not write to `module_quizzes` or `module_summaries`. Future implementations will persist generated content by calling course-service APIs or using shared repositories.

5. **No Kafka/Temporal wiring**: Define clear extension points (TODO comments) where events will be published or workflows triggered, but do not implement the wiring.

6. **No PostgreSQL**: The ai-service does not have its own PostgreSQL database in phase 1. When tables like `ai_conversations`, `ai_messages`, and `rag_index_status` are needed, they will be added in phase 2 with Alembic migrations.

7. **ID format consistency**: Use `int` for `course_id` and `student_id`. Use `str` (bson ObjectId hex) for `module_id` and `lesson_id`. Use `str` (uuid4 hex) for `session_id` and `message_id`.

8. **Authorship compatibility**: When quiz/summary generation is eventually implemented, the persisted documents must set `authorship.source = "ai_generated"`, `authorship.ai_model` to the model name, and `authorship.source_lesson_ids` to the lesson IDs used.

---

## 15. Deliverables Checklist

- [ ] **1. Create `services/ai-service/` directory** with the full structure described in Section 3.
- [ ] **2. Create `pyproject.toml`** with dependencies as specified in Section 11.1.
- [ ] **3. Create `Dockerfile`** following the pattern in Section 11.2.
- [ ] **4. Create `.env`** with the template from Section 4.
- [ ] **5. Implement `config.py`** with all settings as specified in Section 4.
- [ ] **6. Implement `main.py`** with lifespan, health check, and router inclusion (Section 5).
- [ ] **7. Implement `api/dependencies.py`** with auth helpers (Section 6).
- [ ] **8. Implement `api/router.py`** aggregating all sub-routers (Section 8.1).
- [ ] **9. Implement all Pydantic schemas** under `schemas/` (Section 7).
- [ ] **10. Implement `api/instructor.py`** with four stub endpoints (Section 8.2).
- [ ] **11. Implement `api/tutor.py`** with two stub endpoints (Section 8.3).
- [ ] **12. Implement `api/index.py`** with four stub endpoints (Section 8.4).
- [ ] **13. Implement `services/instructor.py`** with stub service methods (Section 9.1).
- [ ] **14. Implement `services/tutor.py`** with stub service methods (Section 9.2).
- [ ] **15. Implement `services/index.py`** with stub service methods (Section 9.3).
- [ ] **16. Implement `repositories/course_content.py`** with read-only MongoDB access (Section 10.1).
- [ ] **17. Implement `repositories/vector_store.py`** with stub methods (Section 10.2).
- [ ] **18. Implement `core/mongodb.py` and `core/redis.py`** — copy from course-service and adjust.
- [ ] **19. Update `shared/src/shared/kafka/topics.py`** to add `AI = "ai.events"`.
- [ ] **20. Update `docker-compose.yml`** to add the ai-service container (Section 12).
- [ ] **21. Verify** the service starts with `uvicorn main:app --port 8009` and the `/health` endpoint returns `200 OK`.
- [ ] **22. Verify** all endpoints are visible in the OpenAPI docs at `http://localhost:8009/docs`.
- [ ] **23. Mark TODOs** at every point where real AI logic, persistence, or event publishing will be added later.
