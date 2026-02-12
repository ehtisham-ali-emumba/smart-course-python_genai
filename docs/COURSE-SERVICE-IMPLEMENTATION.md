# Course Service — Complete Implementation Instructions

**Date:** February 12, 2026
**Service:** `course-service`
**Port:** 8002 (internal, behind API Gateway)
**Scope:** Courses, Enrollments, Certificates (PostgreSQL) + Course Content (MongoDB)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Prerequisites — Docker Changes](#2-prerequisites--docker-changes)
3. [Directory Structure](#3-directory-structure)
4. [File-by-File Implementation](#4-file-by-file-implementation)
5. [API Gateway Integration](#5-api-gateway-integration)
6. [Docker Compose Updates](#6-docker-compose-updates)
7. [Alembic Setup & Migration](#7-alembic-setup--migration)
8. [Running Everything](#8-running-everything)
9. [API Endpoints Summary](#9-api-endpoints-summary)
10. [Production Notes — Alembic & Table Creation](#10-production-notes--alembic--table-creation)

---

## 1. Overview

The `course-service` manages:

| Entity | Storage | Purpose |
|--------|---------|---------|
| **courses** | PostgreSQL | Course metadata (title, slug, instructor, price, status, etc.) |
| **enrollments** | PostgreSQL | Student enrollment + progress tracking (merged with progress) |
| **certificates** | PostgreSQL | Completion certificates linked to enrollments |
| **course_content** | MongoDB | Flexible nested course structure (modules → lessons) |

**Architecture pattern** — identical to `user-service`:
- Layered: API Routes → Services → Repositories → Models
- Async/await throughout (SQLAlchemy async + Motor for MongoDB)
- FastAPI with Pydantic v2
- All routes protected via JWT (API Gateway passes `X-User-ID` and `X-User-Role` headers)
- Alembic for PostgreSQL migrations (async)

---

## 2. Prerequisites — Docker Changes

### 2.1 Add MongoDB to `docker-compose.yml` (root)

MongoDB does NOT exist in Docker yet. Add this service block to the root `docker-compose.yml`, right after the `redis` service:

```yaml
  mongodb:
    image: mongo:7-jammy
    container_name: smartcourse-mongodb
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${MONGO_USER:-smartcourse}
      MONGO_INITDB_ROOT_PASSWORD: ${MONGO_PASSWORD:-smartcourse_secret}
      MONGO_INITDB_DATABASE: ${MONGO_DB:-smartcourse}
    ports:
      - "27017:27017"
    volumes:
      - mongodb_data:/data/db
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - smartcourse-network
```

Also add `mongodb_data` to the `volumes:` section at the bottom:

```yaml
volumes:
  postgres_data:
  redis_data:
  mongodb_data:
```

### 2.2 Add MongoDB env vars to root `.env`

Append these lines to the root `.env` file:

```env
# MongoDB Configuration
MONGO_USER=smartcourse
MONGO_PASSWORD=smartcourse_secret
MONGO_DB=smartcourse
```

---

## 3. Directory Structure

Create this exact structure under `services/course-service/`:

```
services/course-service/
├── .env.example
├── alembic.ini
├── Dockerfile
├── pyproject.toml
└── src/
    ├── __init__.py                  (empty)
    ├── config.py
    ├── main.py
    ├── alembic/
    │   ├── env.py
    │   ├── script.py.mako
    │   └── versions/               (empty directory, migrations go here)
    ├── api/
    │   ├── __init__.py              (empty)
    │   ├── router.py
    │   ├── courses.py
    │   ├── enrollments.py
    │   ├── certificates.py
    │   ├── course_content.py
    │   └── dependencies.py
    ├── core/
    │   ├── __init__.py              (empty)
    │   ├── database.py
    │   └── mongodb.py
    ├── models/
    │   ├── __init__.py
    │   ├── course.py
    │   ├── enrollment.py
    │   └── certificate.py
    ├── repositories/
    │   ├── __init__.py              (empty)
    │   ├── base.py
    │   ├── course.py
    │   ├── enrollment.py
    │   ├── certificate.py
    │   └── course_content.py
    ├── schemas/
    │   ├── __init__.py              (empty)
    │   ├── course.py
    │   ├── enrollment.py
    │   ├── certificate.py
    │   └── course_content.py
    └── services/
        ├── __init__.py              (empty)
        ├── course.py
        ├── enrollment.py
        ├── certificate.py
        └── course_content.py
```

---

## 4. File-by-File Implementation

### 4.1 `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "smartcourse-course-service"
version = "0.1.0"
description = "SmartCourse Course Management Service"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "sqlalchemy>=2.0.25",
    "asyncpg>=0.29.0",
    "psycopg2-binary>=2.9.9",
    "motor>=3.3.0",
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

**Key difference from user-service:** added `motor>=3.3.0` (async MongoDB driver). Removed `redis`, `python-jose`, `bcrypt`, `email-validator` since this service does NOT handle auth — JWT verification is done by the API Gateway. The service trusts `X-User-ID` and `X-User-Role` headers.

---

### 4.2 `.env.example`

```env
# PostgreSQL (use service name "postgres" inside Docker, "localhost" outside)
DATABASE_URL=postgresql://smartcourse:smartcourse_secret@localhost:5432/smartcourse

# MongoDB (use service name "mongodb" inside Docker, "localhost" outside)
MONGODB_URL=mongodb://smartcourse:smartcourse_secret@localhost:27017/smartcourse?authSource=admin
MONGODB_DB_NAME=smartcourse
```

---

### 4.3 `Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only pyproject.toml first for better caching
COPY pyproject.toml .

# Install dependencies first (without the package itself)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    fastapi>=0.109.0 \
    uvicorn[standard]>=0.27.0 \
    sqlalchemy>=2.0.25 \
    asyncpg>=0.29.0 \
    psycopg2-binary>=2.9.9 \
    motor>=3.3.0 \
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

COPY src/ ./src/
COPY alembic.ini ./

# Install the package in editable mode
RUN pip install --no-cache-dir -e .

COPY src/alembic/ ./src/alembic/

ENV PYTHONPATH=/app/src:/app
EXPOSE 8002

CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port 8002"]
```

---

### 4.4 `alembic.ini`

```ini
[alembic]
script_location = src/alembic
# sqlalchemy.url is set programmatically in env.py — do NOT set it here

[loggers]
keys = root

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)s: %(name)s: %(message)s
```

---

### 4.5 `src/__init__.py`

```python
# Empty — package marker
```

> **Why does `src/` need an `__init__.py`?** Since `src/` is now the package root itself (no nested `course_service/` folder), it needs `__init__.py` to be importable. The Dockerfile sets `PYTHONPATH=/app/src` so all imports like `from config import settings`, `from core.database import get_db`, etc. resolve from `src/` directly.

---

### 4.6 `src/config.py`

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # PostgreSQL
    DATABASE_URL: str = "postgresql://smartcourse:smartcourse_secret@localhost:5432/smartcourse"

    # MongoDB
    MONGODB_URL: str = "mongodb://smartcourse:smartcourse_secret@localhost:27017/smartcourse?authSource=admin"
    MONGODB_DB_NAME: str = "smartcourse"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
```

---

### 4.7 `src/core/database.py`

Identical pattern to user-service — async SQLAlchemy engine + session factory.

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
    echo=False,
    future=True,
)

# Create async session factory
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    future=True,
)

# Declarative base for SQLAlchemy models
Base = declarative_base()


async def get_db() -> AsyncSession:
    """Get database session dependency for FastAPI routes."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
```

---

### 4.8 `src/core/mongodb.py`

New file — Motor async client for MongoDB.

```python
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from config import settings

# Global client instance (initialized on startup, closed on shutdown)
_client: AsyncIOMotorClient | None = None
_database: AsyncIOMotorDatabase | None = None


async def connect_mongodb() -> None:
    """Initialize MongoDB connection. Call on app startup."""
    global _client, _database
    _client = AsyncIOMotorClient(settings.MONGODB_URL)
    _database = _client[settings.MONGODB_DB_NAME]

    # Create indexes on first connect
    await _database.course_content.create_index("course_id", unique=True)
    await _database.course_content.create_index("updated_at")


async def close_mongodb() -> None:
    """Close MongoDB connection. Call on app shutdown."""
    global _client
    if _client:
        _client.close()


def get_mongodb() -> AsyncIOMotorDatabase:
    """Get MongoDB database instance. Used as FastAPI dependency."""
    if _database is None:
        raise RuntimeError("MongoDB not initialized. Call connect_mongodb() first.")
    return _database
```

---

### 4.9 `src/core/__init__.py`

```python
# Empty — package marker
```

---

### 4.10 `src/main.py`

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager

from api.router import router
from core.database import engine
from core.mongodb import connect_mongodb, close_mongodb
from models import Course, Enrollment, Certificate  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    # Connect to MongoDB on startup
    await connect_mongodb()
    yield
    # Cleanup on shutdown
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

---

### 4.11 SQLAlchemy Models (PostgreSQL)

#### `src/models/__init__.py`

```python
from models.course import Course
from models.enrollment import Enrollment
from models.certificate import Certificate

__all__ = ["Course", "Enrollment", "Certificate"]
```

#### `src/models/course.py`

Based on the ERD `COURSES` table definition:

```python
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, Numeric, Index
)

from core.database import Base


class Course(Base):
    """Course metadata model — stored in PostgreSQL."""
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    long_description = Column(Text, nullable=True)
    instructor_id = Column(Integer, nullable=False, index=True)  # FK to instructor_profiles.id (in user-service DB)
    category = Column(String(100), nullable=True, index=True)
    level = Column(String(50), nullable=True)          # beginner, intermediate, advanced
    language = Column(String(50), default="en", nullable=False)
    duration_hours = Column(Numeric(5, 2), nullable=True)
    price = Column(Numeric(10, 2), default=0.00, nullable=False)
    currency = Column(String(3), default="USD", nullable=False)
    thumbnail_url = Column(String(500), nullable=True)
    status = Column(String(50), nullable=False, default="draft", index=True)  # draft, published, archived
    published_at = Column(DateTime, nullable=True)
    max_students = Column(Integer, nullable=True)
    prerequisites = Column(Text, nullable=True)
    learning_objectives = Column(Text, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_courses_published_at", "published_at"),
    )

    def __repr__(self) -> str:
        return f"<Course(id={self.id}, title={self.title}, status={self.status})>"
```

**Note about `instructor_id`:** In a microservice architecture, the `instructor_profiles` table lives in the user-service database. Since both services share the same PostgreSQL database (single `smartcourse` DB), the FK relationship technically exists at the database level, but we do NOT declare a SQLAlchemy `ForeignKey()` here because Alembic would try to manage a table it doesn't own. The course-service trusts that `instructor_id` values are valid (validated at the API layer via the user-service or the `X-User-ID` header). If you later split into separate databases per service, this is already correct.

#### `src/models/enrollment.py`

Based on the ERD `ENROLLMENTS` table (merged with progress):

```python
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, Numeric, Boolean, Index,
    UniqueConstraint, ARRAY
)
from sqlalchemy.dialects.postgresql import JSONB

from core.database import Base


class Enrollment(Base):
    """Enrollment model with merged progress fields — stored in PostgreSQL."""
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, nullable=False, index=True)     # FK to users.id (in user-service DB)
    course_id = Column(Integer, nullable=False, index=True)      # FK to courses.id

    # Enrollment fields
    status = Column(String(50), nullable=False, default="active", index=True)  # active, completed, dropped, suspended
    enrolled_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    dropped_at = Column(DateTime, nullable=True)
    last_accessed_at = Column(DateTime, nullable=True)

    # Payment fields
    payment_status = Column(String(50), nullable=True)           # pending, completed, refunded
    payment_amount = Column(Numeric(10, 2), nullable=True)
    enrollment_source = Column(String(100), nullable=True)       # web, mobile, api

    # Progress fields (merged from former progress table)
    completed_modules = Column(ARRAY(Integer), default=[], nullable=False)
    completed_lessons = Column(ARRAY(Integer), default=[], nullable=False)
    total_modules = Column(Integer, default=0, nullable=False)
    total_lessons = Column(Integer, default=0, nullable=False)
    completion_percentage = Column(Numeric(5, 2), default=0.00, nullable=False)
    completed_quizzes = Column(ARRAY(Integer), default=[], nullable=False)
    quiz_scores = Column(JSONB, nullable=True)                   # {quiz_id: score}
    time_spent_minutes = Column(Integer, default=0, nullable=False)
    current_module_id = Column(Integer, nullable=True)
    current_lesson_id = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="uq_enrollment_student_course"),
        Index("idx_enrollments_enrolled_at", "enrolled_at"),
        Index("idx_enrollments_last_accessed", "last_accessed_at"),
    )

    def __repr__(self) -> str:
        return f"<Enrollment(id={self.id}, student={self.student_id}, course={self.course_id}, status={self.status})>"
```

#### `src/models/certificate.py`

Based on the ERD `CERTIFICATES` table:

```python
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Text, Date, DateTime, Boolean, Numeric,
    ForeignKey, Index
)

from core.database import Base


class Certificate(Base):
    """Certificate model — stored in PostgreSQL."""
    __tablename__ = "certificates"

    id = Column(Integer, primary_key=True, index=True)
    enrollment_id = Column(
        Integer,
        ForeignKey("enrollments.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    certificate_number = Column(String(100), unique=True, nullable=False)
    issue_date = Column(Date, nullable=False, default=date.today)
    certificate_url = Column(String(500), nullable=True)
    verification_code = Column(String(50), unique=True, nullable=False)
    grade = Column(String(10), nullable=True)                    # A, B, C
    score_percentage = Column(Numeric(5, 2), nullable=True)
    issued_by_id = Column(Integer, nullable=True)                # FK to users.id (instructor)
    is_revoked = Column(Boolean, default=False, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    revoked_reason = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_certificates_enrollment", "enrollment_id"),
    )

    def __repr__(self) -> str:
        return f"<Certificate(id={self.id}, cert_number={self.certificate_number})>"
```

---

### 4.12 Pydantic Schemas

#### `src/schemas/__init__.py`

```python
# Empty — package marker
```

#### `src/schemas/course.py`

```python
from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class CourseCreate(BaseModel):
    """Schema for creating a new course."""
    title: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: Optional[str] = None
    long_description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=100)
    level: Optional[str] = Field(None, pattern=r"^(beginner|intermediate|advanced)$")
    language: str = Field(default="en", max_length=50)
    duration_hours: Optional[Decimal] = None
    price: Decimal = Field(default=Decimal("0.00"), ge=0)
    currency: str = Field(default="USD", max_length=3)
    thumbnail_url: Optional[str] = Field(None, max_length=500)
    max_students: Optional[int] = Field(None, gt=0)
    prerequisites: Optional[str] = None
    learning_objectives: Optional[str] = None


class CourseUpdate(BaseModel):
    """Schema for updating a course."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    long_description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=100)
    level: Optional[str] = Field(None, pattern=r"^(beginner|intermediate|advanced)$")
    language: Optional[str] = Field(None, max_length=50)
    duration_hours: Optional[Decimal] = None
    price: Optional[Decimal] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=3)
    thumbnail_url: Optional[str] = Field(None, max_length=500)
    max_students: Optional[int] = Field(None, gt=0)
    prerequisites: Optional[str] = None
    learning_objectives: Optional[str] = None


class CourseStatusUpdate(BaseModel):
    """Schema for changing course status (publish, archive)."""
    status: str = Field(..., pattern=r"^(draft|published|archived)$")


class CourseResponse(BaseModel):
    """Schema for course API responses."""
    id: int
    title: str
    slug: str
    description: Optional[str]
    long_description: Optional[str]
    instructor_id: int
    category: Optional[str]
    level: Optional[str]
    language: str
    duration_hours: Optional[Decimal]
    price: Decimal
    currency: str
    thumbnail_url: Optional[str]
    status: str
    published_at: Optional[datetime]
    max_students: Optional[int]
    prerequisites: Optional[str]
    learning_objectives: Optional[str]
    is_deleted: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CourseListResponse(BaseModel):
    """Paginated list of courses."""
    items: list[CourseResponse]
    total: int
    skip: int
    limit: int
```

#### `src/schemas/enrollment.py`

```python
from datetime import datetime
from decimal import Decimal
from typing import Optional, Any
from pydantic import BaseModel, ConfigDict, Field


class EnrollmentCreate(BaseModel):
    """Schema for enrolling a student in a course."""
    course_id: int
    payment_amount: Optional[Decimal] = None
    enrollment_source: Optional[str] = Field(None, max_length=100)


class EnrollmentUpdate(BaseModel):
    """Schema for updating enrollment (progress)."""
    status: Optional[str] = Field(None, pattern=r"^(active|completed|dropped|suspended)$")
    current_module_id: Optional[int] = None
    current_lesson_id: Optional[int] = None


class ProgressUpdate(BaseModel):
    """Schema for updating lesson/module completion progress."""
    lesson_id: Optional[int] = None        # Mark this lesson as completed
    module_id: Optional[int] = None        # Mark this module as completed
    time_spent_minutes: Optional[int] = Field(None, ge=0)


class EnrollmentResponse(BaseModel):
    """Schema for enrollment API responses."""
    id: int
    student_id: int
    course_id: int
    status: str
    enrolled_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    dropped_at: Optional[datetime]
    last_accessed_at: Optional[datetime]
    payment_status: Optional[str]
    payment_amount: Optional[Decimal]
    enrollment_source: Optional[str]
    completed_modules: list[int]
    completed_lessons: list[int]
    total_modules: int
    total_lessons: int
    completion_percentage: Decimal
    completed_quizzes: list[int]
    quiz_scores: Optional[dict[str, Any]]
    time_spent_minutes: int
    current_module_id: Optional[int]
    current_lesson_id: Optional[int]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EnrollmentListResponse(BaseModel):
    """Paginated list of enrollments."""
    items: list[EnrollmentResponse]
    total: int
    skip: int
    limit: int
```

#### `src/schemas/certificate.py`

```python
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class CertificateCreate(BaseModel):
    """Schema for issuing a certificate."""
    enrollment_id: int
    grade: Optional[str] = Field(None, max_length=10)
    score_percentage: Optional[Decimal] = Field(None, ge=0, le=100)


class CertificateResponse(BaseModel):
    """Schema for certificate API responses."""
    id: int
    enrollment_id: int
    certificate_number: str
    issue_date: date
    certificate_url: Optional[str]
    verification_code: str
    grade: Optional[str]
    score_percentage: Optional[Decimal]
    issued_by_id: Optional[int]
    is_revoked: bool
    revoked_at: Optional[datetime]
    revoked_reason: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CertificateVerifyResponse(BaseModel):
    """Schema for public certificate verification."""
    is_valid: bool
    certificate_number: Optional[str] = None
    issue_date: Optional[date] = None
    grade: Optional[str] = None
    is_revoked: bool = False
```

#### `src/schemas/course_content.py`

```python
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ResourceSchema(BaseModel):
    """A single resource attached to a lesson."""
    name: str
    url: str
    type: str   # pdf, video, link, etc.


class LessonSchema(BaseModel):
    """A single lesson within a module."""
    lesson_id: int
    title: str
    type: str = Field(..., pattern=r"^(video|text|quiz|assignment)$")
    content: Optional[str] = None
    duration_minutes: Optional[int] = None
    order: int
    is_preview: bool = False
    resources: list[ResourceSchema] = []


class ModuleSchema(BaseModel):
    """A single module containing lessons."""
    module_id: int
    title: str
    description: Optional[str] = None
    order: int
    is_published: bool = True
    lessons: list[LessonSchema] = []


class CourseContentMetadata(BaseModel):
    """Metadata stored alongside course content."""
    total_modules: int = 0
    total_lessons: int = 0
    total_duration_hours: Optional[float] = None
    tags: list[str] = []


class CourseContentCreate(BaseModel):
    """Schema for creating/replacing full course content."""
    modules: list[ModuleSchema] = []
    metadata: Optional[CourseContentMetadata] = None


class CourseContentResponse(BaseModel):
    """Schema for course content API responses."""
    course_id: int
    modules: list[ModuleSchema] = []
    metadata: Optional[CourseContentMetadata] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ModuleCreate(BaseModel):
    """Schema for adding a single module."""
    module_id: int
    title: str
    description: Optional[str] = None
    order: int
    is_published: bool = True
    lessons: list[LessonSchema] = []


class LessonCreate(BaseModel):
    """Schema for adding a single lesson to a module."""
    lesson_id: int
    title: str
    type: str = Field(..., pattern=r"^(video|text|quiz|assignment)$")
    content: Optional[str] = None
    duration_minutes: Optional[int] = None
    order: int
    is_preview: bool = False
    resources: list[ResourceSchema] = []
```

---

### 4.13 Repositories

#### `src/repositories/__init__.py`

```python
# Empty — package marker
```

#### `src/repositories/base.py`

Copy directly from user-service — identical generic base repository:

```python
from typing import TypeVar, Generic, Type, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

T = TypeVar("T")


class BaseRepository(Generic[T]):
    """Base repository with common database operations."""

    def __init__(self, db: AsyncSession, model: Type[T]):
        self.db = db
        self.model = model

    async def create(self, obj_in: dict) -> T:
        """Create a new record."""
        db_obj = self.model(**obj_in)
        self.db.add(db_obj)
        await self.db.commit()
        await self.db.refresh(db_obj)
        return db_obj

    async def get_by_id(self, id: int) -> Optional[T]:
        """Get record by ID."""
        result = await self.db.execute(select(self.model).where(self.model.id == id))
        return result.scalars().first()

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        """Get all records with pagination."""
        result = await self.db.execute(
            select(self.model).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def count(self) -> int:
        """Count total records."""
        result = await self.db.execute(select(func.count(self.model.id)))
        return result.scalar() or 0

    async def update(self, id: int, obj_in: dict) -> Optional[T]:
        """Update a record."""
        db_obj = await self.get_by_id(id)
        if db_obj:
            for key, value in obj_in.items():
                setattr(db_obj, key, value)
            await self.db.commit()
            await self.db.refresh(db_obj)
        return db_obj

    async def delete(self, id: int) -> bool:
        """Delete a record."""
        db_obj = await self.get_by_id(id)
        if db_obj:
            await self.db.delete(db_obj)
            await self.db.commit()
            return True
        return False
```

#### `src/repositories/course.py`

```python
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from models.course import Course
from repositories.base import BaseRepository


class CourseRepository(BaseRepository[Course]):
    """Course repository for PostgreSQL operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(db, Course)

    async def get_by_slug(self, slug: str) -> Optional[Course]:
        """Get course by URL slug."""
        result = await self.db.execute(
            select(Course).where(Course.slug == slug, Course.is_deleted == False)
        )
        return result.scalars().first()

    async def slug_exists(self, slug: str) -> bool:
        """Check if a slug already exists."""
        course = await self.get_by_slug(slug)
        return course is not None

    async def get_by_instructor(
        self, instructor_id: int, skip: int = 0, limit: int = 100
    ) -> List[Course]:
        """Get all courses by an instructor."""
        result = await self.db.execute(
            select(Course)
            .where(Course.instructor_id == instructor_id, Course.is_deleted == False)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_published(self, skip: int = 0, limit: int = 100) -> List[Course]:
        """Get all published courses (for students browsing)."""
        result = await self.db.execute(
            select(Course)
            .where(Course.status == "published", Course.is_deleted == False)
            .order_by(Course.published_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_published(self) -> int:
        """Count total published courses."""
        result = await self.db.execute(
            select(func.count(Course.id))
            .where(Course.status == "published", Course.is_deleted == False)
        )
        return result.scalar() or 0

    async def count_by_instructor(self, instructor_id: int) -> int:
        """Count courses by instructor."""
        result = await self.db.execute(
            select(func.count(Course.id))
            .where(Course.instructor_id == instructor_id, Course.is_deleted == False)
        )
        return result.scalar() or 0

    async def soft_delete(self, id: int) -> Optional[Course]:
        """Soft delete a course."""
        return await self.update(id, {"is_deleted": True})
```

#### `src/repositories/enrollment.py`

```python
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from models.enrollment import Enrollment
from repositories.base import BaseRepository


class EnrollmentRepository(BaseRepository[Enrollment]):
    """Enrollment repository for PostgreSQL operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(db, Enrollment)

    async def get_by_student_and_course(
        self, student_id: int, course_id: int
    ) -> Optional[Enrollment]:
        """Get enrollment by student + course (unique pair)."""
        result = await self.db.execute(
            select(Enrollment).where(
                Enrollment.student_id == student_id,
                Enrollment.course_id == course_id,
            )
        )
        return result.scalars().first()

    async def get_by_student(
        self, student_id: int, skip: int = 0, limit: int = 100
    ) -> List[Enrollment]:
        """Get all enrollments for a student."""
        result = await self.db.execute(
            select(Enrollment)
            .where(Enrollment.student_id == student_id)
            .order_by(Enrollment.enrolled_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_course(
        self, course_id: int, skip: int = 0, limit: int = 100
    ) -> List[Enrollment]:
        """Get all enrollments for a course."""
        result = await self.db.execute(
            select(Enrollment)
            .where(Enrollment.course_id == course_id)
            .order_by(Enrollment.enrolled_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_course(self, course_id: int) -> int:
        """Count enrollments for a course."""
        result = await self.db.execute(
            select(func.count(Enrollment.id))
            .where(Enrollment.course_id == course_id)
        )
        return result.scalar() or 0

    async def count_by_student(self, student_id: int) -> int:
        """Count enrollments for a student."""
        result = await self.db.execute(
            select(func.count(Enrollment.id))
            .where(Enrollment.student_id == student_id)
        )
        return result.scalar() or 0

    async def is_enrolled(self, student_id: int, course_id: int) -> bool:
        """Check if a student is enrolled in a course."""
        enrollment = await self.get_by_student_and_course(student_id, course_id)
        return enrollment is not None
```

#### `src/repositories/certificate.py`

```python
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.certificate import Certificate
from repositories.base import BaseRepository


class CertificateRepository(BaseRepository[Certificate]):
    """Certificate repository for PostgreSQL operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(db, Certificate)

    async def get_by_enrollment(self, enrollment_id: int) -> Optional[Certificate]:
        """Get certificate by enrollment ID."""
        result = await self.db.execute(
            select(Certificate).where(Certificate.enrollment_id == enrollment_id)
        )
        return result.scalars().first()

    async def get_by_certificate_number(self, cert_number: str) -> Optional[Certificate]:
        """Get certificate by its unique certificate number."""
        result = await self.db.execute(
            select(Certificate).where(Certificate.certificate_number == cert_number)
        )
        return result.scalars().first()

    async def get_by_verification_code(self, code: str) -> Optional[Certificate]:
        """Get certificate by its public verification code."""
        result = await self.db.execute(
            select(Certificate).where(Certificate.verification_code == code)
        )
        return result.scalars().first()
```

#### `src/repositories/course_content.py`

MongoDB repository using Motor:

```python
from datetime import datetime
from typing import Optional, Any

from motor.motor_asyncio import AsyncIOMotorDatabase


class CourseContentRepository:
    """Course content repository for MongoDB operations."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db["course_content"]

    async def get_by_course_id(self, course_id: int) -> Optional[dict[str, Any]]:
        """Get course content document by course_id."""
        return await self.collection.find_one({"course_id": course_id})

    async def create(self, course_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new course content document."""
        now = datetime.utcnow()
        document = {
            "course_id": course_id,
            "modules": data.get("modules", []),
            "metadata": data.get("metadata", {}),
            "created_at": now,
            "updated_at": now,
        }
        result = await self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    async def update(self, course_id: int, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Replace course content for a given course_id."""
        now = datetime.utcnow()
        update_data = {
            "modules": data.get("modules", []),
            "metadata": data.get("metadata", {}),
            "updated_at": now,
        }
        result = await self.collection.find_one_and_update(
            {"course_id": course_id},
            {"$set": update_data},
            return_document=True,
        )
        return result

    async def upsert(self, course_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Create or update course content (upsert)."""
        now = datetime.utcnow()
        update_data = {
            "modules": data.get("modules", []),
            "metadata": data.get("metadata", {}),
            "updated_at": now,
        }
        result = await self.collection.find_one_and_update(
            {"course_id": course_id},
            {
                "$set": update_data,
                "$setOnInsert": {"course_id": course_id, "created_at": now},
            },
            upsert=True,
            return_document=True,
        )
        return result

    async def delete(self, course_id: int) -> bool:
        """Delete course content document."""
        result = await self.collection.delete_one({"course_id": course_id})
        return result.deleted_count > 0

    async def add_module(self, course_id: int, module: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Add a module to course content."""
        result = await self.collection.find_one_and_update(
            {"course_id": course_id},
            {
                "$push": {"modules": module},
                "$set": {"updated_at": datetime.utcnow()},
            },
            return_document=True,
        )
        return result

    async def add_lesson_to_module(
        self, course_id: int, module_id: int, lesson: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Add a lesson to a specific module."""
        result = await self.collection.find_one_and_update(
            {"course_id": course_id, "modules.module_id": module_id},
            {
                "$push": {"modules.$.lessons": lesson},
                "$set": {"updated_at": datetime.utcnow()},
            },
            return_document=True,
        )
        return result
```

---

### 4.14 Services

#### `src/services/__init__.py`

```python
# Empty — package marker
```

#### `src/services/course.py`

```python
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from models.course import Course
from repositories.course import CourseRepository
from schemas.course import CourseCreate, CourseUpdate, CourseStatusUpdate


class CourseService:
    """Business logic for course operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.course_repo = CourseRepository(db)

    async def create_course(self, data: CourseCreate, instructor_id: int) -> Course:
        """Create a new course. instructor_id comes from X-User-ID header."""
        if await self.course_repo.slug_exists(data.slug):
            raise ValueError(f"Slug '{data.slug}' is already taken")

        course_data = data.model_dump()
        course_data["instructor_id"] = instructor_id
        course_data["status"] = "draft"
        return await self.course_repo.create(course_data)

    async def get_course(self, course_id: int) -> Optional[Course]:
        """Get a single course by ID (excludes soft-deleted)."""
        course = await self.course_repo.get_by_id(course_id)
        if course and course.is_deleted:
            return None
        return course

    async def get_course_by_slug(self, slug: str) -> Optional[Course]:
        """Get a course by its URL slug."""
        return await self.course_repo.get_by_slug(slug)

    async def list_published_courses(self, skip: int = 0, limit: int = 100):
        """List published courses for browsing."""
        courses = await self.course_repo.get_published(skip=skip, limit=limit)
        total = await self.course_repo.count_published()
        return courses, total

    async def list_instructor_courses(
        self, instructor_id: int, skip: int = 0, limit: int = 100
    ):
        """List all courses by an instructor."""
        courses = await self.course_repo.get_by_instructor(instructor_id, skip=skip, limit=limit)
        total = await self.course_repo.count_by_instructor(instructor_id)
        return courses, total

    async def update_course(
        self, course_id: int, data: CourseUpdate, instructor_id: int
    ) -> Optional[Course]:
        """Update course details. Only the owning instructor can update."""
        course = await self.get_course(course_id)
        if not course:
            return None
        if course.instructor_id != instructor_id:
            raise PermissionError("You do not own this course")

        update_data = data.model_dump(exclude_unset=True)
        return await self.course_repo.update(course_id, update_data)

    async def update_status(
        self, course_id: int, data: CourseStatusUpdate, instructor_id: int
    ) -> Optional[Course]:
        """Change course status (draft → published → archived)."""
        course = await self.get_course(course_id)
        if not course:
            return None
        if course.instructor_id != instructor_id:
            raise PermissionError("You do not own this course")

        update_data = {"status": data.status}
        if data.status == "published" and course.status != "published":
            update_data["published_at"] = datetime.utcnow()

        return await self.course_repo.update(course_id, update_data)

    async def delete_course(self, course_id: int, instructor_id: int) -> bool:
        """Soft-delete a course. Only the owning instructor can delete."""
        course = await self.get_course(course_id)
        if not course:
            return False
        if course.instructor_id != instructor_id:
            raise PermissionError("You do not own this course")

        await self.course_repo.soft_delete(course_id)
        return True
```

#### `src/services/enrollment.py`

```python
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from models.enrollment import Enrollment
from repositories.enrollment import EnrollmentRepository
from repositories.course import CourseRepository
from schemas.enrollment import EnrollmentCreate, ProgressUpdate


class EnrollmentService:
    """Business logic for enrollment and progress operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.enrollment_repo = EnrollmentRepository(db)
        self.course_repo = CourseRepository(db)

    async def enroll_student(self, student_id: int, data: EnrollmentCreate) -> Enrollment:
        """Enroll a student in a course."""
        # Check course exists and is published
        course = await self.course_repo.get_by_id(data.course_id)
        if not course or course.is_deleted:
            raise ValueError("Course not found")
        if course.status != "published":
            raise ValueError("Course is not available for enrollment")

        # Check max_students limit
        if course.max_students:
            current_count = await self.enrollment_repo.count_by_course(data.course_id)
            if current_count >= course.max_students:
                raise ValueError("Course enrollment limit reached")

        # Check not already enrolled
        if await self.enrollment_repo.is_enrolled(student_id, data.course_id):
            raise ValueError("Already enrolled in this course")

        enrollment_data = {
            "student_id": student_id,
            "course_id": data.course_id,
            "status": "active",
            "payment_amount": data.payment_amount,
            "payment_status": "completed" if data.payment_amount else None,
            "enrollment_source": data.enrollment_source,
        }
        return await self.enrollment_repo.create(enrollment_data)

    async def get_enrollment(self, enrollment_id: int) -> Optional[Enrollment]:
        """Get a single enrollment by ID."""
        return await self.enrollment_repo.get_by_id(enrollment_id)

    async def get_student_enrollments(
        self, student_id: int, skip: int = 0, limit: int = 100
    ):
        """List all enrollments for a student."""
        enrollments = await self.enrollment_repo.get_by_student(student_id, skip=skip, limit=limit)
        total = await self.enrollment_repo.count_by_student(student_id)
        return enrollments, total

    async def get_course_enrollments(
        self, course_id: int, skip: int = 0, limit: int = 100
    ):
        """List all enrollments for a course (instructor view)."""
        enrollments = await self.enrollment_repo.get_by_course(course_id, skip=skip, limit=limit)
        total = await self.enrollment_repo.count_by_course(course_id)
        return enrollments, total

    async def update_progress(
        self, enrollment_id: int, student_id: int, data: ProgressUpdate
    ) -> Optional[Enrollment]:
        """Update student progress on a course."""
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

        return await self.enrollment_repo.update(enrollment_id, {
            "status": "dropped",
            "dropped_at": datetime.utcnow(),
        })
```

#### `src/services/certificate.py`

```python
import uuid
from datetime import date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from models.certificate import Certificate
from repositories.certificate import CertificateRepository
from repositories.enrollment import EnrollmentRepository
from schemas.certificate import CertificateCreate


class CertificateService:
    """Business logic for certificate operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.cert_repo = CertificateRepository(db)
        self.enrollment_repo = EnrollmentRepository(db)

    async def issue_certificate(
        self, data: CertificateCreate, issued_by_id: int
    ) -> Certificate:
        """Issue a certificate for a completed enrollment."""
        # Verify enrollment exists and is completed
        enrollment = await self.enrollment_repo.get_by_id(data.enrollment_id)
        if not enrollment:
            raise ValueError("Enrollment not found")
        if enrollment.status != "completed":
            raise ValueError("Enrollment is not completed — cannot issue certificate")

        # Check if certificate already exists for this enrollment
        existing = await self.cert_repo.get_by_enrollment(data.enrollment_id)
        if existing:
            raise ValueError("Certificate already issued for this enrollment")

        cert_data = {
            "enrollment_id": data.enrollment_id,
            "certificate_number": f"SC-{uuid.uuid4().hex[:12].upper()}",
            "issue_date": date.today(),
            "verification_code": uuid.uuid4().hex[:8].upper(),
            "grade": data.grade,
            "score_percentage": data.score_percentage,
            "issued_by_id": issued_by_id,
        }
        return await self.cert_repo.create(cert_data)

    async def get_certificate(self, certificate_id: int) -> Optional[Certificate]:
        """Get certificate by ID."""
        return await self.cert_repo.get_by_id(certificate_id)

    async def get_certificate_by_enrollment(self, enrollment_id: int) -> Optional[Certificate]:
        """Get certificate by enrollment ID."""
        return await self.cert_repo.get_by_enrollment(enrollment_id)

    async def verify_certificate(self, verification_code: str) -> Optional[Certificate]:
        """Public verification — look up certificate by verification code."""
        return await self.cert_repo.get_by_verification_code(verification_code)

    async def revoke_certificate(
        self, certificate_id: int, reason: str, revoked_by_id: int
    ) -> Optional[Certificate]:
        """Revoke a certificate."""
        from datetime import datetime

        cert = await self.cert_repo.get_by_id(certificate_id)
        if not cert:
            return None

        return await self.cert_repo.update(certificate_id, {
            "is_revoked": True,
            "revoked_at": datetime.utcnow(),
            "revoked_reason": reason,
        })
```

#### `src/services/course_content.py`

```python
from typing import Optional, Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from repositories.course_content import CourseContentRepository
from schemas.course_content import (
    CourseContentCreate,
    ModuleCreate,
    LessonCreate,
)


class CourseContentService:
    """Business logic for course content (MongoDB)."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.content_repo = CourseContentRepository(db)

    async def get_content(self, course_id: int) -> Optional[dict[str, Any]]:
        """Get full course content by course_id."""
        doc = await self.content_repo.get_by_course_id(course_id)
        if doc:
            doc.pop("_id", None)  # Remove MongoDB ObjectId for serialization
        return doc

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
        return doc

    async def add_module(self, course_id: int, data: ModuleCreate) -> Optional[dict[str, Any]]:
        """Add a single module to existing course content."""
        module_data = data.model_dump()
        doc = await self.content_repo.add_module(course_id, module_data)
        if doc:
            doc.pop("_id", None)
        return doc

    async def add_lesson(
        self, course_id: int, module_id: int, data: LessonCreate
    ) -> Optional[dict[str, Any]]:
        """Add a single lesson to a specific module."""
        lesson_data = data.model_dump()
        doc = await self.content_repo.add_lesson_to_module(course_id, module_id, lesson_data)
        if doc:
            doc.pop("_id", None)
        return doc

    async def delete_content(self, course_id: int) -> bool:
        """Delete all content for a course."""
        return await self.content_repo.delete(course_id)
```

---

### 4.15 API Dependencies

#### `src/api/dependencies.py`

Shared dependencies for extracting user info from gateway headers:

```python
from fastapi import Request, HTTPException, status


def get_current_user_id(request: Request) -> int:
    """
    Extract current user ID from X-User-ID header.
    This header is set by the API Gateway after JWT verification.
    """
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return int(user_id)


def get_current_user_role(request: Request) -> str:
    """
    Extract current user role from X-User-Role header.
    This header is set by the API Gateway after JWT verification.
    """
    role = request.headers.get("X-User-Role")
    if not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return role


def require_instructor(request: Request) -> int:
    """
    Require that the current user is an instructor.
    Returns user_id if authorized.
    """
    user_id = get_current_user_id(request)
    role = get_current_user_role(request)
    if role not in ("instructor", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Instructor role required",
        )
    return user_id
```

---

### 4.16 API Routes

#### `src/api/__init__.py`

```python
# Empty — package marker
```

#### `src/api/router.py`

```python
from fastapi import APIRouter
from api import courses, enrollments, certificates, course_content

# Main API router
router = APIRouter()

router.include_router(courses.router, prefix="/courses", tags=["Courses"])
router.include_router(enrollments.router, prefix="/course/enrollments", tags=["Enrollments"])
router.include_router(certificates.router, prefix="/course/certificates", tags=["Certificates"])
router.include_router(course_content.router, prefix="/courses", tags=["Course Content"])
```

#### `src/api/courses.py`

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
    return CourseListResponse(
        items=[CourseResponse.model_validate(c) for c in courses],
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

#### `src/api/enrollments.py`

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from api.dependencies import get_current_user_id
from schemas.enrollment import (
    EnrollmentCreate,
    ProgressUpdate,
    EnrollmentResponse,
    EnrollmentListResponse,
)
from services.enrollment import EnrollmentService

router = APIRouter()


@router.post("/", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED)
async def enroll(
    data: EnrollmentCreate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Enroll the current user in a course."""
    service = EnrollmentService(db)
    try:
        enrollment = await service.enroll_student(user_id, data)
        return EnrollmentResponse.model_validate(enrollment)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/my-enrollments", response_model=EnrollmentListResponse)
async def list_my_enrollments(
    skip: int = 0,
    limit: int = 20,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List all enrollments for the current user."""
    service = EnrollmentService(db)
    enrollments, total = await service.get_student_enrollments(user_id, skip=skip, limit=limit)
    return EnrollmentListResponse(
        items=[EnrollmentResponse.model_validate(e) for e in enrollments],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{enrollment_id}", response_model=EnrollmentResponse)
async def get_enrollment(
    enrollment_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get a single enrollment (must be the enrolled student)."""
    service = EnrollmentService(db)
    enrollment = await service.get_enrollment(enrollment_id)
    if not enrollment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")
    if enrollment.student_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your enrollment")
    return EnrollmentResponse.model_validate(enrollment)


@router.patch("/{enrollment_id}/progress", response_model=EnrollmentResponse)
async def update_progress(
    enrollment_id: int,
    data: ProgressUpdate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Update progress on an enrollment (mark lessons/modules complete)."""
    service = EnrollmentService(db)
    try:
        enrollment = await service.update_progress(enrollment_id, user_id, data)
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found"
            )
        return EnrollmentResponse.model_validate(enrollment)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.patch("/{enrollment_id}/drop", response_model=EnrollmentResponse)
async def drop_enrollment(
    enrollment_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Drop a course enrollment."""
    service = EnrollmentService(db)
    try:
        enrollment = await service.drop_enrollment(enrollment_id, user_id)
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found"
            )
        return EnrollmentResponse.model_validate(enrollment)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
```

#### `src/api/certificates.py`

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from api.dependencies import require_instructor
from schemas.certificate import (
    CertificateCreate,
    CertificateResponse,
    CertificateVerifyResponse,
)
from services.certificate import CertificateService

router = APIRouter()


@router.post("/", response_model=CertificateResponse, status_code=status.HTTP_201_CREATED)
async def issue_certificate(
    data: CertificateCreate,
    instructor_id: int = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """Issue a certificate for a completed enrollment (instructors only)."""
    service = CertificateService(db)
    try:
        cert = await service.issue_certificate(data, instructor_id)
        return CertificateResponse.model_validate(cert)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/verify/{verification_code}", response_model=CertificateVerifyResponse)
async def verify_certificate(
    verification_code: str,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint to verify a certificate by its verification code."""
    service = CertificateService(db)
    cert = await service.verify_certificate(verification_code)
    if not cert:
        return CertificateVerifyResponse(is_valid=False)
    return CertificateVerifyResponse(
        is_valid=not cert.is_revoked,
        certificate_number=cert.certificate_number,
        issue_date=cert.issue_date,
        grade=cert.grade,
        is_revoked=cert.is_revoked,
    )


@router.get("/{certificate_id}", response_model=CertificateResponse)
async def get_certificate(
    certificate_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a certificate by ID."""
    service = CertificateService(db)
    cert = await service.get_certificate(certificate_id)
    if not cert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Certificate not found")
    return CertificateResponse.model_validate(cert)
```

#### `src/api/course_content.py`

```python
from fastapi import APIRouter, Depends, HTTPException, status

from core.mongodb import get_mongodb
from api.dependencies import require_instructor, get_current_user_id
from schemas.course_content import (
    CourseContentCreate,
    CourseContentResponse,
    ModuleCreate,
    LessonCreate,
)
from services.course_content import CourseContentService

router = APIRouter()


@router.get("/{course_id}/content", response_model=CourseContentResponse)
async def get_course_content(
    course_id: int,
    user_id: int = Depends(get_current_user_id),
):
    """Get full course content (modules and lessons)."""
    db = get_mongodb()
    service = CourseContentService(db)
    content = await service.get_content(course_id)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course content not found",
        )
    return CourseContentResponse(**content)


@router.put("/{course_id}/content", response_model=CourseContentResponse)
async def upsert_course_content(
    course_id: int,
    data: CourseContentCreate,
    instructor_id: int = Depends(require_instructor),
):
    """Create or fully replace course content (instructors only)."""
    db = get_mongodb()
    service = CourseContentService(db)
    content = await service.create_or_update_content(course_id, data)
    return CourseContentResponse(**content)


@router.post("/{course_id}/content/modules", response_model=CourseContentResponse)
async def add_module(
    course_id: int,
    data: ModuleCreate,
    instructor_id: int = Depends(require_instructor),
):
    """Add a module to existing course content (instructors only)."""
    db = get_mongodb()
    service = CourseContentService(db)
    content = await service.add_module(course_id, data)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course content not found — create content first",
        )
    return CourseContentResponse(**content)


@router.post(
    "/{course_id}/content/modules/{module_id}/lessons",
    response_model=CourseContentResponse,
)
async def add_lesson(
    course_id: int,
    module_id: int,
    data: LessonCreate,
    instructor_id: int = Depends(require_instructor),
):
    """Add a lesson to a module (instructors only)."""
    db = get_mongodb()
    service = CourseContentService(db)
    content = await service.add_lesson(course_id, module_id, data)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course content or module not found",
        )
    return CourseContentResponse(**content)


@router.delete("/{course_id}/content", status_code=status.HTTP_204_NO_CONTENT)
async def delete_course_content(
    course_id: int,
    instructor_id: int = Depends(require_instructor),
):
    """Delete all content for a course (instructors only)."""
    db = get_mongodb()
    service = CourseContentService(db)
    deleted = await service.delete_content(course_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course content not found",
        )
```

---

### 4.17 Alembic Files

#### `src/alembic/env.py`

Follows the exact same pattern as user-service's `alembic/env.py`:

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from config import settings
from core.database import Base

# Import ALL models so they register with Base.metadata
from models import Course, Enrollment, Certificate  # noqa: F401

# Alembic Config object
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata for autogenerate
target_metadata = Base.metadata


def get_url() -> str:
    """Build the async database URL from app settings."""
    return settings.DATABASE_URL.replace(
        "postgresql://", "postgresql+asyncpg://"
    )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table="alembic_version_course",  # Separate from user-service
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Run migrations using a synchronous connection callback."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table="alembic_version_course",  # Separate from user-service
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_async_engine(get_url())

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

#### `src/alembic/script.py.mako`

Identical to user-service:

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

#### `src/alembic/versions/` — Empty Directory

Create this as an empty directory. The first migration will be generated below.

---

## 5. API Gateway Integration

All course-service routes must be JWT-protected and proxied through the gateway.

### 5.1 Update `services/api-gateway/nginx/conf.d/upstreams.conf`

Uncomment and enable the course-service upstream:

```nginx
# Course service
upstream course-service {
    server smartcourse-course-service:8002;
    keepalive 32;
}
```

### 5.2 Update `services/api-gateway/nginx/nginx.conf`

Add these location blocks inside the `server { }` block, **after the existing `/users/` block** and **before the catch-all `location / { }` block**:

```nginx
        # ==============================================================
        #  COURSE SERVICE — All routes protected by JWT
        # ==============================================================
        location /courses/ {
            limit_req zone=api_general burst=20 nodelay;
            include /etc/nginx/conf.d/protected-snippet.conf;
            proxy_pass http://course-service$request_uri;
            include /etc/nginx/conf.d/proxy-params.conf;
        }

        location /course/enrollments {
            limit_req zone=api_general burst=20 nodelay;
            include /etc/nginx/conf.d/protected-snippet.conf;
            proxy_pass http://course-service$request_uri;
            include /etc/nginx/conf.d/proxy-params.conf;
        }

        location /course/certificates {
            limit_req zone=api_general burst=20 nodelay;
            include /etc/nginx/conf.d/protected-snippet.conf;
            proxy_pass http://course-service$request_uri;
            include /etc/nginx/conf.d/proxy-params.conf;
        }
```

**Important:** The `protected-snippet.conf` performs the `auth_request` to the auth-sidecar, which verifies the JWT and sets `X-User-ID` and `X-User-Role` headers. This means **every** course-service route is JWT-protected at the gateway level.

---

## 6. Docker Compose Updates

### 6.1 Full `course-service` block to add to `docker-compose.yml`

Add this after the `user-service` block:

```yaml
  course-service:
    build:
      context: ./services/course-service
      dockerfile: Dockerfile
    container_name: smartcourse-course-service
    # No ports exposed to host — only accessible through API Gateway
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER:-smartcourse}:${POSTGRES_PASSWORD:-smartcourse_secret}@postgres:5432/${POSTGRES_DB:-smartcourse}
      - MONGODB_URL=mongodb://${MONGO_USER:-smartcourse}:${MONGO_PASSWORD:-smartcourse_secret}@mongodb:27017/${MONGO_DB:-smartcourse}?authSource=admin
      - MONGODB_DB_NAME=${MONGO_DB:-smartcourse}
    depends_on:
      postgres:
        condition: service_healthy
      mongodb:
        condition: service_healthy
    networks:
      - smartcourse-network
```

### 6.2 Update `api-gateway` depends_on

Add `course-service` to the API gateway's `depends_on`:

```yaml
  api-gateway:
    # ... existing config ...
    depends_on:
      - auth-sidecar
      - user-service
      - course-service          # <-- ADD THIS LINE
```

### 6.3 Final `docker-compose.yml` service order (for reference)

After all changes, the services section should contain (in order):
1. `postgres`
2. `redis`
3. `mongodb` (NEW)
4. `user-service`
5. `course-service` (NEW)
6. `auth-sidecar`
7. `api-gateway`

And the volumes section:
```yaml
volumes:
  postgres_data:
  redis_data:
  mongodb_data:          # <-- ADD THIS
```

---

## 7. Alembic Setup & Migration

### 7.1 Important: Shared Database

Both `user-service` and `course-service` connect to the **same PostgreSQL database** (`smartcourse`). Each service manages its own tables via its own Alembic migration history. This is fine because:
- user-service manages: `users`, `instructor_profiles`
- course-service manages: `courses`, `enrollments`, `certificates`
- Each has its own `alembic_version` table? **No** — by default both would use the same `alembic_version` table, which would conflict.

**Fix (already applied):** The `src/alembic/env.py` file in Section 4.17 already includes `version_table="alembic_version_course"` in both `run_migrations_offline()` and `do_run_migrations()`. This ensures user-service uses the default `alembic_version` table and course-service uses `alembic_version_course`. They will never conflict.

### 7.2 Generate Initial Migration

After creating all the files, from the `services/course-service/` directory, run:

```bash
# Inside Docker (recommended) — exec into the running container:
docker exec -it smartcourse-course-service alembic revision --autogenerate -m "initial_course_tables"

# OR locally (if you have the venv set up):
cd services/course-service
DATABASE_URL=postgresql://smartcourse:smartcourse_secret@localhost:5432/smartcourse \
  alembic revision --autogenerate -m "initial_course_tables"
```

This will auto-generate a migration file in `src/alembic/versions/` that creates the `courses`, `enrollments`, and `certificates` tables.

### 7.3 Apply Migration

```bash
# Inside Docker (happens automatically on container start via CMD):
docker exec -it smartcourse-course-service alembic upgrade head

# OR the container CMD already runs "alembic upgrade head" on startup.
```

---

## 8. Running Everything

### 8.1 Build and Start

```bash
# From the project root:
docker compose build
docker compose up -d
```

This will:
1. Start PostgreSQL, Redis, MongoDB
2. Build and start `user-service` (runs `alembic upgrade head` on boot)
3. Build and start `course-service` (runs `alembic upgrade head` on boot — creates courses, enrollments, certificates tables)
4. Start auth-sidecar and api-gateway

### 8.2 Verify

```bash
# Check all containers are running
docker compose ps

# Health check via gateway
curl http://localhost:8000/health

# Course service health (through gateway — will be 404 since no /health route through gateway)
# Instead test via docker directly:
docker exec -it smartcourse-course-service curl http://localhost:8002/health

# Test a protected endpoint (requires valid JWT from user-service login)
curl -H "Authorization: Bearer <your-access-token>" http://localhost:8000/courses/
```

### 8.3 MongoDB Verification

```bash
# Connect to MongoDB shell
docker exec -it smartcourse-mongodb mongosh -u smartcourse -p smartcourse_secret --authenticationDatabase admin

# Inside mongosh:
use smartcourse
db.course_content.find()
```

---

## 9. API Endpoints Summary

All endpoints are accessed through the API Gateway at `http://localhost:8000`. All require `Authorization: Bearer <token>` header.

### Courses

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/courses/` | Instructor | Create a new course |
| GET | `/courses/` | Any | List published courses |
| GET | `/courses/my-courses` | Instructor | List own courses |
| GET | `/courses/{id}` | Any | Get course by ID |
| PUT | `/courses/{id}` | Instructor (owner) | Update course |
| PATCH | `/courses/{id}/status` | Instructor (owner) | Publish/archive course |
| DELETE | `/courses/{id}` | Instructor (owner) | Soft-delete course |

### Course Content (MongoDB)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/courses/{id}/content` | Any | Get full course content |
| PUT | `/courses/{id}/content` | Instructor | Create/replace content |
| POST | `/courses/{id}/content/modules` | Instructor | Add a module |
| POST | `/courses/{id}/content/modules/{mid}/lessons` | Instructor | Add a lesson |
| DELETE | `/courses/{id}/content` | Instructor | Delete all content |

### Enrollments

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/course/enrollments/` | Any | Enroll in a course |
| GET | `/course/enrollments/my-enrollments` | Any | List my enrollments |
| GET | `/course/enrollments/{id}` | Student (owner) | Get enrollment detail |
| PATCH | `/course/enrollments/{id}/progress` | Student (owner) | Update progress |
| PATCH | `/course/enrollments/{id}/drop` | Student (owner) | Drop enrollment |

### Certificates

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/course/certificates/` | Instructor | Issue a certificate |
| GET | `/course/certificates/verify/{code}` | Any | Public verification |
| GET | `/course/certificates/{id}` | Any | Get certificate by ID |

---

## 10. Production Notes — Alembic & Table Creation

### Do I need to create tables manually in production?

**No. Alembic handles everything.** Here is exactly how it works:

### How Alembic Works in Production

1. **Alembic tracks database state** via a version table (`alembic_version` for user-service, `alembic_version_course` for course-service). This table has a single row containing the revision ID of the last applied migration.

2. **On first deployment** (fresh database):
   - `alembic upgrade head` is run (it's in the Dockerfile CMD)
   - Alembic sees no version table → creates it
   - Applies ALL migrations from oldest to newest
   - Result: all tables are created exactly matching your SQLAlchemy models

3. **On subsequent deployments** (existing database):
   - `alembic upgrade head` is run
   - Alembic checks the version table → sees which migration was last applied
   - Only applies NEW migrations (ones after the current revision)
   - Result: only new schema changes are applied (new columns, new tables, etc.)

4. **Migration file = source of truth.** The migration files in `alembic/versions/` are the single source of truth for your database schema. They are committed to git and version controlled.

### Production Deployment Workflow

```
Developer makes a model change
    ↓
Run: alembic revision --autogenerate -m "add_xyz_column"
    ↓
Review the generated migration file (always review!)
    ↓
Commit migration file to git
    ↓
Deploy to production (Docker image build + deploy)
    ↓
Container starts → CMD runs "alembic upgrade head"
    ↓
Alembic applies only new migrations
    ↓
App starts with updated schema
```

### Key Rules for Production

- **Never modify a migration that has already been applied in production.** Always create a new migration.
- **Always review autogenerated migrations.** Alembic autogenerate is good but not perfect — check that it does what you expect.
- **Never run `alembic downgrade` in production** unless you know exactly what you're doing.
- **Back up the database before applying migrations** in production.
- **The Dockerfile CMD `alembic upgrade head && uvicorn ...`** means the app won't start until migrations succeed. This is intentional — if a migration fails, the container crashes and you know immediately.

### What about MongoDB in production?

MongoDB is **schemaless** — there are no migrations. The `connect_mongodb()` function in `core/mongodb.py` creates indexes on startup. MongoDB collections are created automatically when you first insert a document. No manual setup required.

---

## Checklist

Before running `docker compose up --build`:

- [ ] Root `.env` has `MONGO_USER`, `MONGO_PASSWORD`, `MONGO_DB` variables
- [ ] `docker-compose.yml` has `mongodb` service with volume
- [ ] `docker-compose.yml` has `course-service` service block
- [ ] `docker-compose.yml` `api-gateway` depends_on includes `course-service`
- [ ] `docker-compose.yml` volumes section includes `mongodb_data`
- [ ] `services/api-gateway/nginx/conf.d/upstreams.conf` has `course-service` upstream
- [ ] `services/api-gateway/nginx/nginx.conf` has `/courses/`, `/course/enrollments`, `/course/certificates` location blocks
- [ ] All files under `services/course-service/` are created per directory structure
- [ ] `src/alembic/versions/` directory exists (even if empty — first migration will be generated)
- [ ] Initial migration generated: `alembic revision --autogenerate -m "initial_course_tables"`

---

_Document Version: 1.0 | Created: February 12, 2026_
