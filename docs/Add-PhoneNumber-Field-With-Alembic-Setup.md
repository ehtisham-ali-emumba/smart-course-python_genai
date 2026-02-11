# Add `phone_number` Field to Users Table + Alembic Migration Setup

> **Goal**: Integrate Alembic into the `user-service` microservice, replace the auto-create-tables-on-startup pattern with Alembic-managed migrations, and add a `phone_number` column to the `users` table — all within a Dockerized environment.

---

## Table of Contents

1. [Project Context](#1-project-context)
2. [Install Alembic](#2-install-alembic)
3. [Initialize Alembic Inside user-service](#3-initialize-alembic-inside-user-service)
4. [Configure Alembic for Async SQLAlchemy](#4-configure-alembic-for-async-sqlalchemy)
5. [Add `phone_number` to the User Model](#5-add-phone_number-to-the-user-model)
6. [Update Pydantic Schemas](#6-update-pydantic-schemas)
7. [Generate the Migration](#7-generate-the-migration)
8. [Review & Verify the Migration Script](#8-review--verify-the-migration-script)
9. [Update the Dockerfile](#9-update-the-dockerfile)
10. [Update docker-compose.yml to Run Migrations](#10-update-docker-composeyml-to-run-migrations)
11. [Remove `create_all` from App Lifespan](#11-remove-create_all-from-app-lifespan)
12. [Run Migrations](#12-run-migrations)
13. [Verify](#13-verify)
14. [File Change Summary](#14-file-change-summary)

---

## 1. Project Context

**Relevant structure** (only files that will be touched or referenced):

```
smart-course/
├── docker-compose.yml
├── .env
└── services/
    └── user-service/
        ├── Dockerfile
        ├── pyproject.toml
        └── src/
            └── user_service/
                ├── main.py                  # lifespan with create_all
                ├── config.py                # Settings (DATABASE_URL)
                ├── core/
                │   └── database.py          # engine, Base, get_db
                ├── models/
                │   ├── __init__.py           # exports User, InstructorProfile
                │   ├── user.py              # User model (will be modified)
                │   └── instructor.py
                └── schemas/
                    ├── auth.py              # UserRegister (will be modified)
                    └── user.py              # UserResponse, UserUpdate (will be modified)
```

**Current table creation**: `main.py` runs `Base.metadata.create_all` inside the FastAPI `lifespan` context manager on every startup. This must be replaced by Alembic.

**Database**: PostgreSQL 15 via async engine (`asyncpg`). The `DATABASE_URL` env var uses the `postgresql://` scheme and is converted to `postgresql+asyncpg://` at runtime in `database.py`.

**Docker**: App runs as `user-service` container; depends on `postgres` and `redis` containers with health checks.

---

## 2. Install Alembic

Add `alembic` to `pyproject.toml` dependencies:

**File**: `services/user-service/pyproject.toml`

In the `dependencies` list, add:

```
"alembic>=1.13.0",
```

Place it alongside the existing SQLAlchemy dependency. The full line should sit inside:

```toml
dependencies = [
    "fastapi>=0.109.0",
    ...
    "sqlalchemy>=2.0.25",
    "alembic>=1.13.0",        # <-- ADD THIS
    ...
]
```

Also add `alembic` to the Dockerfile's explicit `pip install` list (see [Step 9](#9-update-the-dockerfile)).

---

## 3. Initialize Alembic Inside user-service

Run **from inside the `services/user-service/` directory** (or exec into the container):

```bash
cd services/user-service
alembic init -t async src/user_service/alembic
```

> **Why `-t async`?** The project uses `AsyncSession` + `asyncpg`. The async template generates a `env.py` that runs migrations through an async engine.

This creates:

```
services/user-service/
├── alembic.ini                              # Alembic config (root of user-service)
└── src/user_service/alembic/
    ├── env.py                               # Migration environment (will be edited)
    ├── script.py.mako                       # Template for new migrations
    └── versions/                            # Migration scripts go here
```

---

## 4. Configure Alembic for Async SQLAlchemy

### 4a. Edit `alembic.ini`

**File**: `services/user-service/alembic.ini`

Set the `script_location` to point to the alembic directory inside the package:

```ini
script_location = src/user_service/alembic
```

**Remove or comment out** the default `sqlalchemy.url` line — we will supply it from the app config at runtime:

```ini
# sqlalchemy.url = driver://user:pass@localhost/dbname
```

### 4b. Edit `env.py`

**File**: `services/user-service/src/user_service/alembic/env.py`

Replace the entire generated `env.py` with:

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from user_service.config import settings
from user_service.core.database import Base

# Import ALL models so they register with Base.metadata
from user_service.models import User, InstructorProfile  # noqa: F401

# Alembic Config object — gives access to alembic.ini values
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
    """Run migrations in 'offline' mode (generates SQL without DB connection)."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Run migrations using a synchronous connection callback."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connects to the DB)."""
    connectable = create_async_engine(get_url())

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

**Key points**:
- `get_url()` reuses the same `DATABASE_URL` from `config.py` and applies the same `postgresql://` → `postgresql+asyncpg://` conversion used in `database.py`.
- All models are imported so autogenerate can detect them.
- Uses `create_async_engine` matching the project's async pattern.

---

## 5. Add `phone_number` to the User Model

**File**: `services/user-service/src/user_service/models/user.py`

Add a `phone_number` column after `is_verified`:

```python
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean

from user_service.core.database import Base


class User(Base):
    """User model for authentication and profile management."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="student")
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    phone_number = Column(String(20), nullable=True)  # <-- NEW FIELD

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"
```

**What changed**: One new line — `phone_number = Column(String(20), nullable=True)`. It's `nullable=True` because existing rows won't have a value.

---

## 6. Update Pydantic Schemas

### 6a. Registration schema (optional field at registration)

**File**: `services/user-service/src/user_service/schemas/auth.py`

```python
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    """User registration request schema."""
    email: EmailStr
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, max_length=100)
    role: str = Field(default="student", pattern="^(student|instructor)$")
    phone_number: Optional[str] = Field(None, min_length=10, max_length=20)  # <-- NEW


# ... rest of file unchanged ...
```

### 6b. User response & update schemas

**File**: `services/user-service/src/user_service/schemas/user.py`

Add `phone_number` to both `UserResponse` and `UserUpdate`:

```python
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Optional


class UserResponse(BaseModel):
    """User response schema for API responses."""
    id: int
    email: EmailStr
    first_name: str
    last_name: str
    role: str
    is_active: bool
    is_verified: bool
    phone_number: Optional[str] = None        # <-- NEW
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
        ser_json_timedelta="iso8601",
    )


class UserUpdate(BaseModel):
    """User update schema."""
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone_number: Optional[str] = Field(None, min_length=10, max_length=20)  # <-- NEW


# ... InstructorProfileResponse & InstructorProfileUpdate unchanged ...
```

### 6c. Update AuthService to pass phone_number during registration

**File**: `services/user-service/src/user_service/services/auth.py`

In the `register` method, add `phone_number` to the create dict:

```python
user = await self.user_repo.create({
    "email": user_data.email,
    "first_name": user_data.first_name,
    "last_name": user_data.last_name,
    "password_hash": password_hash,
    "role": user_data.role,
    "is_active": True,
    "is_verified": False,
    "phone_number": user_data.phone_number,  # <-- NEW
})
```

---

## 7. Generate the Migration

### Option A: From host (if alembic is installed locally)

```bash
cd services/user-service
DATABASE_URL="postgresql://smartcourse:smartcourse_secret@localhost:5432/smartcourse" \
  alembic revision --autogenerate -m "add_phone_number_to_users"
```

### Option B: From inside Docker (recommended — ensures matching environment)

First, make sure Postgres is up:

```bash
docker compose up -d postgres
```

Then run:

```bash
docker compose run --rm user-service \
  alembic revision --autogenerate -m "add_phone_number_to_users"
```

> **Note**: If this is the very first migration, Alembic will also detect all existing tables. If the DB already has the tables (created by `create_all`), you need to stamp the current state first. See the section below.

### First-time Alembic on an existing database (tables already exist)

If the `users` and `instructor_profiles` tables already exist in the DB:

1. **Create an initial "baseline" migration** that represents the current schema:

```bash
docker compose run --rm user-service \
  alembic revision --autogenerate -m "initial_baseline"
```

2. **Stamp the database** as already being at this revision (do NOT run `upgrade` for this one — the tables are already there):

```bash
docker compose run --rm user-service \
  alembic stamp head
```

3. **Now generate the phone_number migration**:

```bash
docker compose run --rm user-service \
  alembic revision --autogenerate -m "add_phone_number_to_users"
```

This second migration will only contain the `phone_number` column addition.

---

## 8. Review & Verify the Migration Script

After generation, a new file appears in `src/user_service/alembic/versions/`. Open it and verify it looks like:

```python
"""add_phone_number_to_users"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'xxxxxxxxxxxx'
down_revision = 'yyyyyyyyyyyy'  # or None if first migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('phone_number', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'phone_number')
```

**Check**:
- `upgrade` adds only `phone_number` to `users`.
- `downgrade` drops it.
- No unexpected changes to other tables.

---

## 9. Update the Dockerfile

**File**: `services/user-service/Dockerfile`

Add `alembic` to the `pip install` list:

```dockerfile
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    fastapi>=0.109.0 \
    uvicorn[standard]>=0.27.0 \
    sqlalchemy>=2.0.25 \
    alembic>=1.13.0 \
    asyncpg>=0.29.0 \
    ...
```

Also copy the `alembic.ini` from the service root into the container. Update the COPY instructions:

```dockerfile
# Copy only pyproject.toml and alembic.ini first for better caching
COPY pyproject.toml alembic.ini ./

# ... (pip install block stays the same) ...

# Copy application code
COPY src/ ./src/
```

Update the `CMD` to run migrations before starting the app:

```dockerfile
CMD ["sh", "-c", "alembic upgrade head && uvicorn user_service.main:app --host 0.0.0.0 --port 8001"]
```

> This ensures migrations run every time the container starts. `alembic upgrade head` is idempotent — if the DB is already at head, it's a no-op.

---

## 10. Update docker-compose.yml to Run Migrations

No structural changes needed to `docker-compose.yml` since the `CMD` in the Dockerfile now handles migrations. The existing `depends_on` with health check ensures Postgres is ready before the user-service starts.

If you prefer to keep the Dockerfile `CMD` clean and run migrations separately, you can alternatively add a one-off migration service:

```yaml
  user-service-migrate:
    build:
      context: ./services/user-service
      dockerfile: Dockerfile
    container_name: smartcourse-user-migrate
    command: alembic upgrade head
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER:-smartcourse}:${POSTGRES_PASSWORD:-smartcourse_secret}@postgres:5432/${POSTGRES_DB:-smartcourse}
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - smartcourse-network
```

Then make `user-service` depend on it:

```yaml
  user-service:
    ...
    depends_on:
      user-service-migrate:
        condition: service_completed_successfully
      redis:
        condition: service_healthy
```

Pick whichever approach you prefer. The inline `CMD` approach is simpler.

---

## 11. Remove `create_all` from App Lifespan

**File**: `services/user-service/src/user_service/main.py`

**Before** (current):

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables if missing, then cleanup on shutdown."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
```

**After** (with Alembic managing schema):

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    # Tables are now managed by Alembic migrations.
    # Run `alembic upgrade head` before starting the app.
    yield
    await engine.dispose()
```

**Why**: `Base.metadata.create_all` will conflict with Alembic. It creates tables outside of Alembic's version tracking, which means Alembic won't know about them and may try to create them again (or, worse, never generate proper migrations for them). With Alembic, schema changes are *only* made through migration scripts.

**Update imports** — you can remove the `Base` import from `main.py` since it's no longer used there (the `engine` import stays for `dispose()`):

```python
from user_service.core.database import engine
```

Keep the model imports if you have them for other reasons, but they're no longer needed in `main.py` for table registration — that's now handled in Alembic's `env.py`.

---

## 12. Run Migrations

### First time (existing DB with tables from `create_all`)

```bash
# 1. Bring up Postgres
docker compose up -d postgres

# 2. Rebuild user-service image (picks up alembic + code changes)
docker compose build user-service

# 3. Generate baseline migration (captures existing schema)
docker compose run --rm user-service alembic revision --autogenerate -m "initial_baseline"

# 4. Stamp the DB as being at this baseline (tables already exist)
docker compose run --rm user-service alembic stamp head

# 5. Generate the phone_number migration
docker compose run --rm user-service alembic revision --autogenerate -m "add_phone_number_to_users"

# 6. Apply the phone_number migration
docker compose run --rm user-service alembic upgrade head

# 7. Start all services
docker compose up -d
```

### Subsequent times (normal workflow)

```bash
docker compose up -d
# migrations run automatically via CMD if configured that way
```

---

## 13. Verify

```bash
# Check the alembic version table
docker compose exec postgres psql -U smartcourse -d smartcourse -c "SELECT * FROM alembic_version;"

# Check the users table has the new column
docker compose exec postgres psql -U smartcourse -d smartcourse -c "\d users;"

# Test the API
curl -X POST http://localhost:8001/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "first_name": "Test",
    "last_name": "User",
    "password": "securepass123",
    "phone_number": "+1234567890"
  }'
```

---

## 14. File Change Summary

| File | Action | What Changed |
|------|--------|-------------|
| `services/user-service/pyproject.toml` | Modified | Added `alembic>=1.13.0` to dependencies |
| `services/user-service/Dockerfile` | Modified | Added `alembic` to pip install, copy `alembic.ini`, migration in CMD |
| `services/user-service/alembic.ini` | **Created** | Alembic configuration (generated by `alembic init`) |
| `services/user-service/src/user_service/alembic/env.py` | **Created** | Async migration environment wired to app config |
| `services/user-service/src/user_service/alembic/script.py.mako` | **Created** | Migration template (generated by `alembic init`) |
| `services/user-service/src/user_service/alembic/versions/` | **Created** | Directory for migration scripts |
| `services/user-service/src/user_service/models/user.py` | Modified | Added `phone_number` column |
| `services/user-service/src/user_service/schemas/auth.py` | Modified | Added `phone_number` to `UserRegister` |
| `services/user-service/src/user_service/schemas/user.py` | Modified | Added `phone_number` to `UserResponse` and `UserUpdate` |
| `services/user-service/src/user_service/services/auth.py` | Modified | Pass `phone_number` in `register()` create dict |
| `services/user-service/src/user_service/main.py` | Modified | Removed `create_all`; Alembic manages schema now |
