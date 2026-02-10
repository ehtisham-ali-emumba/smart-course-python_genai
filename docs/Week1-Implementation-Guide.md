# SmartCourse - Week 1 Implementation Guide

**Version:** 1.1  
**Date:** February 10, 2026  
**Scope:** CRUD Microservices Setup with JWT Authentication  
**Tech Stack:** Python 3.12+, FastAPI, PostgreSQL, MongoDB, Redis, Nginx, Docker

---

## Table of Contents

1. [Project Structure](#1-project-structure)
2. [Shared Library](#2-shared-library)
3. [Nginx API Gateway](#3-nginx-api-gateway)
4. [User Service](#4-user-service)
5. [Course Service](#5-course-service)
6. [Enrollment Service](#6-enrollment-service)
7. [Progress Service](#7-progress-service)
8. [Certificate Service](#8-certificate-service)
9. [Docker Compose](#9-docker-compose)
10. [Environment Variables](#10-environment-variables)
11. [Database Migrations](#11-database-migrations)
12. [Testing Setup](#12-testing-setup)
13. [Implementation Checklist](#13-implementation-checklist)

---

## 1. Project Structure

```
smart-course/
│
├── docker-compose.yml                 # Orchestrates all services
├── docker-compose.override.yml        # Development overrides
├── .env                               # Environment variables
├── .env.example                       # Example env file
├── Makefile                           # Common commands
├── README.md
│
├── shared/                            # Shared library (installed as package)
│   ├── pyproject.toml
│   ├── setup.py
│   └── smartcourse_shared/
│       ├── __init__.py
│       ├── auth/
│       │   ├── __init__.py
│       │   ├── jwt_handler.py         # JWT creation/validation
│       │   ├── dependencies.py        # FastAPI auth dependencies
│       │   └── schemas.py             # Token schemas
│       ├── database/
│       │   ├── __init__.py
│       │   ├── postgres.py            # PostgreSQL connection
│       │   ├── mongodb.py             # MongoDB connection
│       │   └── redis.py               # Redis connection
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── base.py                # Base schemas
│       │   └── responses.py           # Standard API responses
│       ├── exceptions/
│       │   ├── __init__.py
│       │   └── handlers.py            # Exception handlers
│       ├── middleware/
│       │   ├── __init__.py
│       │   ├── logging.py             # Request logging
│       │   └── cors.py                # CORS configuration
│       └── utils/
│           ├── __init__.py
│           ├── password.py            # Password hashing
│           └── helpers.py             # Common utilities
│
├── nginx/                             # Nginx API Gateway
│   ├── Dockerfile
│   ├── nginx.conf                     # Main Nginx configuration
│   ├── conf.d/
│   │   ├── default.conf               # Server block configuration
│   │   ├── upstream.conf              # Upstream services definition
│   │   └── rate_limit.conf            # Rate limiting configuration
│   └── ssl/                           # SSL certificates (for production)
│       ├── .gitkeep
│       └── README.md
│
├── services/
│   │
│   ├── user-service/                  # Port 8001
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── alembic.ini
│   │   ├── alembic/
│   │   │   ├── env.py
│   │   │   └── versions/
│   │   ├── app/
│   │   │   ├── __init__.py
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── models/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── user.py
│   │   │   │   ├── instructor_profile.py
│   │   │   │   └── refresh_token.py
│   │   │   ├── schemas/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── user.py
│   │   │   │   └── auth.py
│   │   │   ├── repositories/
│   │   │   │   ├── __init__.py
│   │   │   │   └── user_repository.py
│   │   │   ├── services/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── user_service.py
│   │   │   │   └── auth_service.py
│   │   │   ├── routes/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth.py
│   │   │   │   └── users.py
│   │   │   └── database.py
│   │   └── tests/
│   │       ├── __init__.py
│   │       ├── conftest.py
│   │       └── test_users.py
│   │
│   ├── course-service/                # Port 8002
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── alembic.ini
│   │   ├── alembic/
│   │   │   ├── env.py
│   │   │   └── versions/
│   │   ├── app/
│   │   │   ├── __init__.py
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── models/
│   │   │   │   ├── __init__.py
│   │   │   │   └── course.py
│   │   │   ├── documents/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── course_content.py
│   │   │   │   └── course_material.py
│   │   │   ├── schemas/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── course.py
│   │   │   │   ├── module.py
│   │   │   │   └── material.py
│   │   │   ├── repositories/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── course_repository.py
│   │   │   │   └── content_repository.py
│   │   │   ├── services/
│   │   │   │   ├── __init__.py
│   │   │   │   └── course_service.py
│   │   │   ├── routes/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── courses.py
│   │   │   │   └── modules.py
│   │   │   └── database.py
│   │   └── tests/
│   │       └── __init__.py
│   │
│   ├── enrollment-service/            # Port 8003
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── alembic.ini
│   │   ├── alembic/
│   │   │   ├── env.py
│   │   │   └── versions/
│   │   ├── app/
│   │   │   ├── __init__.py
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── models/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── enrollment.py
│   │   │   │   └── enrollment_history.py
│   │   │   ├── schemas/
│   │   │   │   ├── __init__.py
│   │   │   │   └── enrollment.py
│   │   │   ├── repositories/
│   │   │   │   ├── __init__.py
│   │   │   │   └── enrollment_repository.py
│   │   │   ├── services/
│   │   │   │   ├── __init__.py
│   │   │   │   └── enrollment_service.py
│   │   │   ├── routes/
│   │   │   │   ├── __init__.py
│   │   │   │   └── enrollments.py
│   │   │   └── database.py
│   │   └── tests/
│   │       └── __init__.py
│   │
│   ├── progress-service/              # Port 8004
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── alembic.ini
│   │   ├── alembic/
│   │   │   ├── env.py
│   │   │   └── versions/
│   │   ├── app/
│   │   │   ├── __init__.py
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── models/
│   │   │   │   ├── __init__.py
│   │   │   │   └── progress.py
│   │   │   ├── schemas/
│   │   │   │   ├── __init__.py
│   │   │   │   └── progress.py
│   │   │   ├── repositories/
│   │   │   │   ├── __init__.py
│   │   │   │   └── progress_repository.py
│   │   │   ├── services/
│   │   │   │   ├── __init__.py
│   │   │   │   └── progress_service.py
│   │   │   ├── routes/
│   │   │   │   ├── __init__.py
│   │   │   │   └── progress.py
│   │   │   └── database.py
│   │   └── tests/
│   │       └── __init__.py
│   │
│   └── certificate-service/           # Port 8005
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── alembic.ini
│       ├── alembic/
│       │   ├── env.py
│       │   └── versions/
│       ├── app/
│       │   ├── __init__.py
│       │   ├── main.py
│       │   ├── config.py
│       │   ├── models/
│       │   │   ├── __init__.py
│       │   │   └── certificate.py
│       │   ├── schemas/
│       │   │   ├── __init__.py
│       │   │   └── certificate.py
│       │   ├── repositories/
│       │   │   ├── __init__.py
│       │   │   └── certificate_repository.py
│       │   ├── services/
│       │   │   ├── __init__.py
│       │   │   └── certificate_service.py
│       │   ├── routes/
│       │   │   ├── __init__.py
│       │   │   └── certificates.py
│       │   └── database.py
│       └── tests/
│           └── __init__.py
│
└── migrations/                        # Global migration scripts
    └── init.sql                       # Initial database setup
```

---

## 2. Shared Library

### 2.1 `shared/pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "smartcourse-shared"
version = "0.1.0"
description = "Shared utilities for SmartCourse microservices"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.109.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
    "sqlalchemy>=2.0.0",
    "asyncpg>=0.29.0",
    "motor>=3.3.0",
    "redis>=5.0.0",
    "httpx>=0.26.0",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["smartcourse_shared*"]
```

### 2.2 `shared/smartcourse_shared/__init__.py`

```python
"""SmartCourse Shared Library."""

__version__ = "0.1.0"
```

### 2.3 `shared/smartcourse_shared/auth/jwt_handler.py`

```python
"""JWT Token Handler for SmartCourse."""

from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from pydantic import BaseModel


class TokenPayload(BaseModel):
    """JWT Token payload structure."""
    sub: str  # user_id
    email: str
    role: str
    exp: datetime
    iat: datetime
    type: str  # "access" or "refresh"


class JWTHandler:
    """Handles JWT token creation and validation."""

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_expire_minutes: int = 30,
        refresh_token_expire_days: int = 7,
    ):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes
        self.refresh_token_expire_days = refresh_token_expire_days

    def create_access_token(
        self,
        user_id: str,
        email: str,
        role: str,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Create an access token."""
        now = datetime.now(timezone.utc)
        if expires_delta:
            expire = now + expires_delta
        else:
            expire = now + timedelta(minutes=self.access_token_expire_minutes)

        payload = {
            "sub": str(user_id),
            "email": email,
            "role": role,
            "exp": expire,
            "iat": now,
            "type": "access",
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(
        self,
        user_id: str,
        email: str,
        role: str,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Create a refresh token."""
        now = datetime.now(timezone.utc)
        if expires_delta:
            expire = now + expires_delta
        else:
            expire = now + timedelta(days=self.refresh_token_expire_days)

        payload = {
            "sub": str(user_id),
            "email": email,
            "role": role,
            "exp": expire,
            "iat": now,
            "type": "refresh",
        }
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def decode_token(self, token: str) -> Optional[TokenPayload]:
        """Decode and validate a JWT token."""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
            )
            return TokenPayload(**payload)
        except JWTError:
            return None

    def verify_token(self, token: str, token_type: str = "access") -> Optional[TokenPayload]:
        """Verify token and check type."""
        payload = self.decode_token(token)
        if payload is None:
            return None
        if payload.type != token_type:
            return None
        return payload
```

### 2.4 `shared/smartcourse_shared/auth/dependencies.py`

```python
"""FastAPI Authentication Dependencies."""

from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .jwt_handler import JWTHandler, TokenPayload


security = HTTPBearer()


class AuthDependency:
    """Authentication dependency for FastAPI routes."""

    def __init__(self, jwt_handler: JWTHandler):
        self.jwt_handler = jwt_handler

    async def get_current_user(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(security),
    ) -> TokenPayload:
        """Get current authenticated user from token."""
        token = credentials.credentials
        payload = self.jwt_handler.verify_token(token, token_type="access")

        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload

    async def get_current_user_optional(
        self,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(
            HTTPBearer(auto_error=False)
        ),
    ) -> Optional[TokenPayload]:
        """Get current user if authenticated, None otherwise."""
        if credentials is None:
            return None

        token = credentials.credentials
        return self.jwt_handler.verify_token(token, token_type="access")


class RoleChecker:
    """Check if user has required role."""

    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, user: TokenPayload) -> TokenPayload:
        if user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user


# Role checker instances
require_admin = RoleChecker(["admin"])
require_instructor = RoleChecker(["admin", "instructor"])
require_student = RoleChecker(["admin", "instructor", "student"])
```

### 2.5 `shared/smartcourse_shared/auth/schemas.py`

```python
"""Authentication Schemas."""

from pydantic import BaseModel, EmailStr


class TokenResponse(BaseModel):
    """Token response schema."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class TokenRefreshRequest(BaseModel):
    """Token refresh request schema."""
    refresh_token: str


class UserPayload(BaseModel):
    """User payload extracted from token."""
    user_id: str
    email: str
    role: str
```

### 2.6 `shared/smartcourse_shared/database/postgres.py`

```python
"""PostgreSQL Database Connection."""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class PostgresDatabase:
    """PostgreSQL database connection manager."""

    def __init__(self, database_url: str, echo: bool = False):
        # Convert postgres:// to postgresql+asyncpg://
        if database_url.startswith("postgres://"):
            database_url = database_url.replace(
                "postgres://", "postgresql+asyncpg://", 1
            )
        elif database_url.startswith("postgresql://"):
            database_url = database_url.replace(
                "postgresql://", "postgresql+asyncpg://", 1
            )

        self.engine = create_async_engine(
            database_url,
            echo=echo,
            pool_size=20,
            max_overflow=10,
            pool_pre_ping=True,
        )
        self.async_session = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session."""
        async with self.async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def create_tables(self):
        """Create all tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self):
        """Close database connection."""
        await self.engine.dispose()
```

### 2.7 `shared/smartcourse_shared/database/mongodb.py`

```python
"""MongoDB Database Connection."""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from beanie import init_beanie
from typing import List, Type
from beanie import Document


class MongoDatabase:
    """MongoDB database connection manager."""

    def __init__(self, mongodb_url: str, database_name: str):
        self.client = AsyncIOMotorClient(mongodb_url)
        self.database: AsyncIOMotorDatabase = self.client[database_name]

    async def init_beanie(self, document_models: List[Type[Document]]):
        """Initialize Beanie ODM with document models."""
        await init_beanie(
            database=self.database,
            document_models=document_models,
        )

    async def close(self):
        """Close database connection."""
        self.client.close()
```

### 2.8 `shared/smartcourse_shared/database/redis.py`

```python
"""Redis Connection."""

from typing import Optional
import redis.asyncio as redis


class RedisClient:
    """Redis client manager."""

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.client: Optional[redis.Redis] = None

    async def connect(self) -> redis.Redis:
        """Connect to Redis."""
        self.client = redis.from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        return self.client

    async def disconnect(self):
        """Disconnect from Redis."""
        if self.client:
            await self.client.close()

    async def get(self, key: str) -> Optional[str]:
        """Get value by key."""
        if self.client:
            return await self.client.get(key)
        return None

    async def set(
        self,
        key: str,
        value: str,
        expire: Optional[int] = None,
    ) -> bool:
        """Set key-value pair with optional expiry (seconds)."""
        if self.client:
            return await self.client.set(key, value, ex=expire)
        return False

    async def delete(self, key: str) -> int:
        """Delete key."""
        if self.client:
            return await self.client.delete(key)
        return 0

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        if self.client:
            return await self.client.exists(key) > 0
        return False
```

### 2.9 `shared/smartcourse_shared/schemas/base.py`

```python
"""Base Schemas."""

from datetime import datetime
from typing import Optional, Generic, TypeVar
from pydantic import BaseModel, ConfigDict


T = TypeVar("T")


class BaseSchema(BaseModel):
    """Base schema with common configuration."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


class TimestampMixin(BaseModel):
    """Mixin for timestamp fields."""
    created_at: datetime
    updated_at: Optional[datetime] = None


class PaginationParams(BaseModel):
    """Pagination parameters."""
    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper."""
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: list[T],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedResponse[T]":
        total_pages = (total + page_size - 1) // page_size
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
```

### 2.10 `shared/smartcourse_shared/schemas/responses.py`

```python
"""Standard API Response Schemas."""

from typing import Any, Optional
from pydantic import BaseModel


class APIResponse(BaseModel):
    """Standard API response."""
    success: bool = True
    message: str = "Success"
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    """Error response."""
    success: bool = False
    message: str
    error_code: Optional[str] = None
    details: Optional[dict] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
    version: str
    dependencies: Optional[dict] = None
```

### 2.11 `shared/smartcourse_shared/exceptions/handlers.py`

```python
"""Exception Handlers."""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        error_code: Optional[str] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)


class NotFoundException(AppException):
    """Resource not found exception."""

    def __init__(self, resource: str, identifier: str):
        super().__init__(
            message=f"{resource} with id '{identifier}' not found",
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="NOT_FOUND",
        )


class ConflictException(AppException):
    """Resource conflict exception."""

    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            error_code="CONFLICT",
        )


class UnauthorizedException(AppException):
    """Unauthorized exception."""

    def __init__(self, message: str = "Unauthorized"):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code="UNAUTHORIZED",
        )


class ForbiddenException(AppException):
    """Forbidden exception."""

    def __init__(self, message: str = "Forbidden"):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="FORBIDDEN",
        )


async def app_exception_handler(request: Request, exc: AppException):
    """Handle application exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.message,
            "error_code": exc.error_code,
        },
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "message": "Validation error",
            "error_code": "VALIDATION_ERROR",
            "details": exc.errors(),
        },
    )
```

### 2.12 `shared/smartcourse_shared/utils/password.py`

```python
"""Password Utilities."""

from passlib.context import CryptContext


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)
```

---

## 3. Nginx API Gateway

The API Gateway is built on **Nginx** as instructed. Nginx handles:

- Reverse proxy routing to microservices
- Load balancing (for future scaling)
- Rate limiting
- CORS headers
- SSL termination (production)
- Request/response logging

### 3.1 `nginx/Dockerfile`

```dockerfile
FROM nginx:1.25-alpine

# Remove default config
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom configuration
COPY nginx.conf /etc/nginx/nginx.conf
COPY conf.d/ /etc/nginx/conf.d/

# Create log directory
RUN mkdir -p /var/log/nginx

# Expose ports
EXPOSE 80 443

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
```

### 3.2 `nginx/nginx.conf`

```nginx
# Main Nginx configuration
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 4096;
    use epoll;
    multi_accept on;
}

http {
    include /etc/nginx/mime.types;
    default_type application/json;

    # Logging format
    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for" '
                    'rt=$request_time uct="$upstream_connect_time" '
                    'uht="$upstream_header_time" urt="$upstream_response_time"';

    log_format json_logs escape=json '{'
        '"time": "$time_iso8601",'
        '"remote_addr": "$remote_addr",'
        '"method": "$request_method",'
        '"uri": "$request_uri",'
        '"status": $status,'
        '"body_bytes_sent": $body_bytes_sent,'
        '"request_time": $request_time,'
        '"upstream_response_time": "$upstream_response_time",'
        '"user_agent": "$http_user_agent"'
    '}';

    access_log /var/log/nginx/access.log json_logs;

    # Performance optimizations
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml application/json application/javascript
               application/xml application/xml+rss text/javascript application/x-javascript;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Request body size
    client_max_body_size 50M;
    client_body_buffer_size 10M;

    # Timeouts
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;

    # Include additional configs
    include /etc/nginx/conf.d/*.conf;
}
```

### 3.3 `nginx/conf.d/upstream.conf`

```nginx
# Upstream service definitions
# These define the backend microservices

upstream user_service {
    least_conn;
    server user-service:8000 max_fails=3 fail_timeout=30s;
    keepalive 32;
}

upstream course_service {
    least_conn;
    server course-service:8000 max_fails=3 fail_timeout=30s;
    keepalive 32;
}

upstream enrollment_service {
    least_conn;
    server enrollment-service:8000 max_fails=3 fail_timeout=30s;
    keepalive 32;
}

upstream progress_service {
    least_conn;
    server progress-service:8000 max_fails=3 fail_timeout=30s;
    keepalive 32;
}

upstream certificate_service {
    least_conn;
    server certificate-service:8000 max_fails=3 fail_timeout=30s;
    keepalive 32;
}
```

### 3.4 `nginx/conf.d/rate_limit.conf`

```nginx
# Rate limiting configuration

# Define rate limit zones
# $binary_remote_addr uses less memory than $remote_addr
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/s;
limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=heavy_limit:10m rate=20r/s;

# Connection limits
limit_conn_zone $binary_remote_addr zone=conn_limit:10m;

# Rate limit status
limit_req_status 429;
limit_conn_status 429;
```

### 3.5 `nginx/conf.d/default.conf`

```nginx
# Main server configuration

server {
    listen 80;
    listen [::]:80;
    server_name localhost;

    # Health check endpoint
    location /health {
        access_log off;
        return 200 '{"status":"healthy","service":"api-gateway","type":"nginx"}';
        add_header Content-Type application/json;
    }

    # API Documentation - Swagger UI aggregation (optional)
    location /docs {
        return 301 /api/v1/users/docs;
    }

    # ==================== CORS Configuration ====================
    # Handle preflight requests
    location / {
        if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' '*' always;
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, PATCH, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization' always;
            add_header 'Access-Control-Max-Age' 1728000;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
        }

        # Default response for root
        return 200 '{"message":"SmartCourse API Gateway","version":"1.0.0","docs":"/docs"}';
        add_header Content-Type application/json;
    }

    # ==================== Authentication Routes ====================
    # Rate limited more strictly to prevent brute force
    location /api/v1/auth/ {
        limit_req zone=auth_limit burst=20 nodelay;
        limit_conn conn_limit 10;

        # CORS headers
        add_header 'Access-Control-Allow-Origin' '*' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type' always;

        # Proxy settings
        proxy_pass http://user_service/auth/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";

        # Pass Authorization header
        proxy_set_header Authorization $http_authorization;
        proxy_pass_header Authorization;
    }

    # ==================== User Service Routes ====================
    location /api/v1/users {
        limit_req zone=api_limit burst=50 nodelay;

        # CORS headers
        add_header 'Access-Control-Allow-Origin' '*' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type' always;

        # Proxy settings
        proxy_pass http://user_service/users;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_set_header Authorization $http_authorization;
        proxy_pass_header Authorization;
    }

    # ==================== Course Service Routes ====================
    location /api/v1/courses {
        limit_req zone=api_limit burst=50 nodelay;

        # CORS headers
        add_header 'Access-Control-Allow-Origin' '*' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type' always;

        # Proxy settings
        proxy_pass http://course_service/courses;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_set_header Authorization $http_authorization;
        proxy_pass_header Authorization;
    }

    # ==================== Enrollment Service Routes ====================
    location /api/v1/enrollments {
        limit_req zone=api_limit burst=50 nodelay;

        # CORS headers
        add_header 'Access-Control-Allow-Origin' '*' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type' always;

        # Proxy settings
        proxy_pass http://enrollment_service/enrollments;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_set_header Authorization $http_authorization;
        proxy_pass_header Authorization;
    }

    # ==================== Progress Service Routes ====================
    location /api/v1/progress {
        limit_req zone=api_limit burst=50 nodelay;

        # CORS headers
        add_header 'Access-Control-Allow-Origin' '*' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type' always;

        # Proxy settings
        proxy_pass http://progress_service/progress;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_set_header Authorization $http_authorization;
        proxy_pass_header Authorization;
    }

    # ==================== Certificate Service Routes ====================
    location /api/v1/certificates {
        limit_req zone=api_limit burst=50 nodelay;

        # CORS headers
        add_header 'Access-Control-Allow-Origin' '*' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type' always;

        # Proxy settings
        proxy_pass http://certificate_service/certificates;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Connection "";
        proxy_set_header Authorization $http_authorization;
        proxy_pass_header Authorization;
    }

    # Public certificate verification (no auth required)
    location /api/v1/certificates/verify/ {
        limit_req zone=api_limit burst=100 nodelay;

        # CORS headers - allow from anywhere for public verification
        add_header 'Access-Control-Allow-Origin' '*' always;

        proxy_pass http://certificate_service/certificates/verify/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # ==================== Error Pages ====================
    error_page 429 /429.json;
    location = /429.json {
        internal;
        return 429 '{"success":false,"message":"Too many requests. Please try again later.","error_code":"RATE_LIMIT_EXCEEDED"}';
        add_header Content-Type application/json always;
    }

    error_page 502 /502.json;
    location = /502.json {
        internal;
        return 502 '{"success":false,"message":"Service temporarily unavailable","error_code":"SERVICE_UNAVAILABLE"}';
        add_header Content-Type application/json always;
    }

    error_page 503 /503.json;
    location = /503.json {
        internal;
        return 503 '{"success":false,"message":"Service overloaded. Please try again later.","error_code":"SERVICE_OVERLOADED"}';
        add_header Content-Type application/json always;
    }

    error_page 504 /504.json;
    location = /504.json {
        internal;
        return 504 '{"success":false,"message":"Request timeout","error_code":"GATEWAY_TIMEOUT"}';
        add_header Content-Type application/json always;
    }
}
```

### 3.6 `nginx/ssl/README.md`

````markdown
# SSL Certificates

For production, place your SSL certificates here:

- `fullchain.pem` - Full certificate chain
- `privkey.pem` - Private key

## Generate Self-Signed Certificates (Development)

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout privkey.pem \
  -out fullchain.pem \
  -subj "/CN=localhost"
```
````

## Production SSL Configuration

Add this to your server block in `default.conf`:

```nginx
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;

    ssl_certificate /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;

    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:50m;
    ssl_session_tickets off;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;

    add_header Strict-Transport-Security "max-age=63072000" always;
}
```

````

### 3.7 Nginx Configuration Notes

**Key Features:**

| Feature | Configuration | Purpose |
|---------|--------------|---------|
| Rate Limiting | `limit_req_zone` | Prevents abuse, DDoS protection |
| Connection Pooling | `keepalive 32` | Reuses connections to backends |
| Load Balancing | `least_conn` | Distributes load evenly |
| Health Checks | `max_fails=3` | Removes unhealthy backends |
| CORS | `add_header` | Enables cross-origin requests |
| Compression | `gzip on` | Reduces response size |
| Logging | `json_logs` | Structured logging for monitoring |

**Route Mapping:**

| External Route | Internal Service | Internal Path |
|----------------|------------------|---------------|
| `/api/v1/auth/*` | user-service:8000 | `/auth/*` |
| `/api/v1/users/*` | user-service:8000 | `/users/*` |
| `/api/v1/courses/*` | course-service:8000 | `/courses/*` |
| `/api/v1/enrollments/*` | enrollment-service:8000 | `/enrollments/*` |
| `/api/v1/progress/*` | progress-service:8000 | `/progress/*` |
| `/api/v1/certificates/*` | certificate-service:8000 | `/certificates/*` |

---

## 4. User Service

### 4.1 `services/user-service/Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy shared library first
COPY shared /app/shared
RUN pip install /app/shared

# Copy requirements and install
COPY services/user-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/user-service/app ./app
COPY services/user-service/alembic.ini .
COPY services/user-service/alembic ./alembic

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
````

### 4.2 `services/user-service/requirements.txt`

```text
fastapi==0.109.2
uvicorn[standard]==0.27.1
sqlalchemy==2.0.25
asyncpg==0.29.0
alembic==1.13.1
pydantic==2.6.1
pydantic-settings==2.1.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
redis==5.0.1
```

### 4.3 `services/user-service/app/config.py`

```python
"""User Service Configuration."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings."""

    # Service Info
    SERVICE_NAME: str = "user-service"
    VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str = "redis://redis:6379"

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

### 4.4 `services/user-service/app/models/user.py`

```python
"""User Model."""

from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Enum as SQLEnum,
    Text,
)
from sqlalchemy.orm import relationship

from smartcourse_shared.database.postgres import Base


class UserRole(str, Enum):
    """User roles."""
    STUDENT = "student"
    INSTRUCTOR = "instructor"
    ADMIN = "admin"


class User(Base):
    """User model."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    first_name = Column(String(100))
    last_name = Column(String(100))
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.STUDENT)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    profile_image_url = Column(String(500))
    bio = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime)
    is_deleted = Column(Boolean, default=False)

    # Relationships
    instructor_profile = relationship(
        "InstructorProfile",
        back_populates="user",
        uselist=False,
    )
    refresh_tokens = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<User {self.email}>"
```

### 4.5 `services/user-service/app/models/instructor_profile.py`

```python
"""Instructor Profile Model."""

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Numeric,
    JSON,
)
from sqlalchemy.orm import relationship

from smartcourse_shared.database.postgres import Base


class InstructorProfile(Base):
    """Instructor profile model."""

    __tablename__ = "instructor_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    specialization = Column(String(255))
    bio = Column(Text)
    website_url = Column(String(500))
    linkedin_url = Column(String(500))
    total_students = Column(Integer, default=0)
    total_courses = Column(Integer, default=0)
    average_rating = Column(Numeric(3, 2), default=0.00)
    total_reviews = Column(Integer, default=0)
    is_verified = Column(Boolean, default=False)
    verified_at = Column(DateTime)
    payout_info = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="instructor_profile")

    def __repr__(self):
        return f"<InstructorProfile user_id={self.user_id}>"
```

### 4.6 `services/user-service/app/models/refresh_token.py`

```python
"""Refresh Token Model."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from smartcourse_shared.database.postgres import Base


class RefreshToken(Base):
    """Refresh token model for managing user sessions."""

    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(500), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_revoked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    revoked_at = Column(DateTime)

    # Relationships
    user = relationship("User", back_populates="refresh_tokens")

    def __repr__(self):
        return f"<RefreshToken user_id={self.user_id}>"
```

### 4.7 `services/user-service/app/schemas/user.py`

```python
"""User Schemas."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator

from smartcourse_shared.schemas.base import BaseSchema, TimestampMixin


class UserBase(BaseSchema):
    """Base user schema."""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)


class UserCreate(UserBase):
    """User creation schema."""
    password: str = Field(..., min_length=8, max_length=100)
    role: str = Field(default="student")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        allowed = ["student", "instructor"]
        if v not in allowed:
            raise ValueError(f"Role must be one of: {allowed}")
        return v


class UserUpdate(BaseSchema):
    """User update schema."""
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    bio: Optional[str] = None
    profile_image_url: Optional[str] = None


class UserResponse(UserBase, TimestampMixin):
    """User response schema."""
    id: int
    role: str
    is_active: bool
    is_verified: bool
    profile_image_url: Optional[str] = None
    bio: Optional[str] = None


class UserListResponse(BaseSchema):
    """User list item response."""
    id: int
    email: EmailStr
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str
    is_active: bool


class InstructorProfileResponse(BaseSchema):
    """Instructor profile response."""
    id: int
    user_id: int
    specialization: Optional[str] = None
    bio: Optional[str] = None
    website_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    total_students: int
    total_courses: int
    average_rating: float
    total_reviews: int
    is_verified: bool
```

### 4.8 `services/user-service/app/schemas/auth.py`

```python
"""Authentication Schemas."""

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Login request schema."""
    email: EmailStr
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    """Register request schema."""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8, max_length=100)
    first_name: str = Field(None, max_length=100)
    last_name: str = Field(None, max_length=100)
    role: str = Field(default="student")


class TokenResponse(BaseModel):
    """Token response schema."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    """Refresh token request schema."""
    refresh_token: str
```

### 4.9 `services/user-service/app/repositories/user_repository.py`

```python
"""User Repository."""

from typing import Optional, List
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import User, UserRole
from ..models.instructor_profile import InstructorProfile


class UserRepository:
    """Repository for user database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user: User) -> User:
        """Create a new user."""
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def get_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID."""
        result = await self.session.execute(
            select(User).where(
                and_(User.id == user_id, User.is_deleted == False)
            )
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        result = await self.session.execute(
            select(User).where(
                and_(User.email == email, User.is_deleted == False)
            )
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        result = await self.session.execute(
            select(User).where(
                and_(User.username == username, User.is_deleted == False)
            )
        )
        return result.scalar_one_or_none()

    async def get_by_email_or_username(
        self, email: str, username: str
    ) -> Optional[User]:
        """Get user by email or username."""
        result = await self.session.execute(
            select(User).where(
                and_(
                    or_(User.email == email, User.username == username),
                    User.is_deleted == False,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        offset: int = 0,
        limit: int = 20,
        role: Optional[UserRole] = None,
    ) -> List[User]:
        """Get all users with pagination."""
        query = select(User).where(User.is_deleted == False)

        if role:
            query = query.where(User.role == role)

        query = query.offset(offset).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def count(self, role: Optional[UserRole] = None) -> int:
        """Count users."""
        from sqlalchemy import func
        query = select(func.count(User.id)).where(User.is_deleted == False)

        if role:
            query = query.where(User.role == role)

        result = await self.session.execute(query)
        return result.scalar_one()

    async def update(self, user: User) -> User:
        """Update user."""
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def soft_delete(self, user: User) -> User:
        """Soft delete user."""
        user.is_deleted = True
        await self.session.flush()
        return user

    async def create_instructor_profile(
        self, profile: InstructorProfile
    ) -> InstructorProfile:
        """Create instructor profile."""
        self.session.add(profile)
        await self.session.flush()
        await self.session.refresh(profile)
        return profile

    async def get_instructor_profile(
        self, user_id: int
    ) -> Optional[InstructorProfile]:
        """Get instructor profile by user ID."""
        result = await self.session.execute(
            select(InstructorProfile).where(
                InstructorProfile.user_id == user_id
            )
        )
        return result.scalar_one_or_none()
```

### 4.10 `services/user-service/app/services/auth_service.py`

```python
"""Authentication Service."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from smartcourse_shared.auth.jwt_handler import JWTHandler
from smartcourse_shared.utils.password import hash_password, verify_password
from smartcourse_shared.exceptions.handlers import (
    ConflictException,
    UnauthorizedException,
    NotFoundException,
)

from ..models.user import User, UserRole
from ..models.instructor_profile import InstructorProfile
from ..models.refresh_token import RefreshToken
from ..repositories.user_repository import UserRepository
from ..schemas.auth import RegisterRequest, LoginRequest, TokenResponse


class AuthService:
    """Authentication service."""

    def __init__(
        self,
        session: AsyncSession,
        jwt_handler: JWTHandler,
    ):
        self.session = session
        self.jwt_handler = jwt_handler
        self.user_repo = UserRepository(session)

    async def register(self, request: RegisterRequest) -> User:
        """Register a new user."""
        # Check if user exists
        existing = await self.user_repo.get_by_email_or_username(
            request.email, request.username
        )
        if existing:
            if existing.email == request.email:
                raise ConflictException("Email already registered")
            raise ConflictException("Username already taken")

        # Create user
        user = User(
            email=request.email,
            username=request.username,
            hashed_password=hash_password(request.password),
            first_name=request.first_name,
            last_name=request.last_name,
            role=UserRole(request.role),
        )
        user = await self.user_repo.create(user)

        # Create instructor profile if instructor
        if user.role == UserRole.INSTRUCTOR:
            profile = InstructorProfile(user_id=user.id)
            await self.user_repo.create_instructor_profile(profile)

        return user

    async def login(self, request: LoginRequest) -> TokenResponse:
        """Login user and return tokens."""
        user = await self.user_repo.get_by_email(request.email)

        if not user:
            raise UnauthorizedException("Invalid email or password")

        if not verify_password(request.password, user.hashed_password):
            raise UnauthorizedException("Invalid email or password")

        if not user.is_active:
            raise UnauthorizedException("Account is deactivated")

        # Update last login
        user.last_login_at = datetime.utcnow()
        await self.user_repo.update(user)

        # Create tokens
        access_token = self.jwt_handler.create_access_token(
            user_id=str(user.id),
            email=user.email,
            role=user.role.value,
        )
        refresh_token = self.jwt_handler.create_refresh_token(
            user_id=str(user.id),
            email=user.email,
            role=user.role.value,
        )

        # Store refresh token
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        token_record = RefreshToken(
            user_id=user.id,
            token=refresh_token,
            expires_at=expires_at,
        )
        self.session.add(token_record)
        await self.session.flush()

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=self.jwt_handler.access_token_expire_minutes * 60,
        )

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        """Refresh access token."""
        # Verify refresh token
        payload = self.jwt_handler.verify_token(refresh_token, token_type="refresh")
        if not payload:
            raise UnauthorizedException("Invalid refresh token")

        # Check if token is in database and not revoked
        from sqlalchemy import select, and_
        result = await self.session.execute(
            select(RefreshToken).where(
                and_(
                    RefreshToken.token == refresh_token,
                    RefreshToken.is_revoked == False,
                    RefreshToken.expires_at > datetime.utcnow(),
                )
            )
        )
        token_record = result.scalar_one_or_none()

        if not token_record:
            raise UnauthorizedException("Invalid or expired refresh token")

        # Get user
        user = await self.user_repo.get_by_id(int(payload.sub))
        if not user or not user.is_active:
            raise UnauthorizedException("User not found or inactive")

        # Create new tokens
        new_access_token = self.jwt_handler.create_access_token(
            user_id=str(user.id),
            email=user.email,
            role=user.role.value,
        )
        new_refresh_token = self.jwt_handler.create_refresh_token(
            user_id=str(user.id),
            email=user.email,
            role=user.role.value,
        )

        # Revoke old refresh token
        token_record.is_revoked = True
        token_record.revoked_at = datetime.utcnow()

        # Store new refresh token
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        new_token_record = RefreshToken(
            user_id=user.id,
            token=new_refresh_token,
            expires_at=expires_at,
        )
        self.session.add(new_token_record)
        await self.session.flush()

        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer",
            expires_in=self.jwt_handler.access_token_expire_minutes * 60,
        )

    async def logout(self, refresh_token: str) -> bool:
        """Logout user by revoking refresh token."""
        from sqlalchemy import select
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.token == refresh_token)
        )
        token_record = result.scalar_one_or_none()

        if token_record:
            token_record.is_revoked = True
            token_record.revoked_at = datetime.utcnow()
            await self.session.flush()

        return True
```

### 4.11 `services/user-service/app/services/user_service.py`

```python
"""User Service."""

from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession

from smartcourse_shared.exceptions.handlers import NotFoundException
from smartcourse_shared.schemas.base import PaginatedResponse

from ..models.user import User, UserRole
from ..repositories.user_repository import UserRepository
from ..schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserListResponse,
)


class UserService:
    """User service for business logic."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

    async def get_user(self, user_id: int) -> UserResponse:
        """Get user by ID."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException("User", str(user_id))
        return UserResponse.model_validate(user)

    async def get_users(
        self,
        page: int = 1,
        page_size: int = 20,
        role: Optional[str] = None,
    ) -> PaginatedResponse[UserListResponse]:
        """Get all users with pagination."""
        offset = (page - 1) * page_size
        role_enum = UserRole(role) if role else None

        users = await self.user_repo.get_all(
            offset=offset,
            limit=page_size,
            role=role_enum,
        )
        total = await self.user_repo.count(role=role_enum)

        items = [UserListResponse.model_validate(u) for u in users]
        return PaginatedResponse.create(items, total, page, page_size)

    async def update_user(
        self,
        user_id: int,
        update_data: UserUpdate,
        current_user_id: int,
    ) -> UserResponse:
        """Update user profile."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException("User", str(user_id))

        # Only allow self-update or admin
        if user.id != current_user_id:
            # Check if current user is admin
            current_user = await self.user_repo.get_by_id(current_user_id)
            if not current_user or current_user.role != UserRole.ADMIN:
                raise NotFoundException("User", str(user_id))

        # Update fields
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(user, field, value)

        user = await self.user_repo.update(user)
        return UserResponse.model_validate(user)

    async def delete_user(self, user_id: int) -> bool:
        """Soft delete user."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException("User", str(user_id))

        await self.user_repo.soft_delete(user)
        return True
```

### 4.12 `services/user-service/app/routes/auth.py`

```python
"""Authentication Routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from smartcourse_shared.auth.jwt_handler import JWTHandler

from ..database import get_db
from ..config import get_settings
from ..schemas.auth import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    RefreshTokenRequest,
)
from ..schemas.user import UserResponse
from ..services.auth_service import AuthService


router = APIRouter()
settings = get_settings()

jwt_handler = JWTHandler(
    secret_key=settings.JWT_SECRET_KEY,
    algorithm=settings.JWT_ALGORITHM,
    access_token_expire_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    refresh_token_expire_days=settings.REFRESH_TOKEN_EXPIRE_DAYS,
)


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user."""
    service = AuthService(db, jwt_handler)
    user = await service.register(request)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Login and get tokens."""
    service = AuthService(db, jwt_handler)
    return await service.login(request)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token."""
    service = AuthService(db, jwt_handler)
    return await service.refresh_token(request.refresh_token)


@router.post("/logout")
async def logout(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """Logout user."""
    service = AuthService(db, jwt_handler)
    await service.logout(request.refresh_token)
    return {"message": "Successfully logged out"}
```

### 4.13 `services/user-service/app/routes/users.py`

```python
"""User Routes."""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from smartcourse_shared.auth.jwt_handler import TokenPayload
from smartcourse_shared.auth.dependencies import AuthDependency
from smartcourse_shared.schemas.base import PaginatedResponse

from ..database import get_db
from ..config import get_settings
from ..schemas.user import UserResponse, UserUpdate, UserListResponse
from ..services.user_service import UserService
from ..routes.auth import jwt_handler


router = APIRouter()
settings = get_settings()
auth_dependency = AuthDependency(jwt_handler)


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    current_user: TokenPayload = Depends(auth_dependency.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current authenticated user."""
    service = UserService(db)
    return await service.get_user(int(current_user.sub))


@router.get("", response_model=PaginatedResponse[UserListResponse])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: Optional[str] = Query(None),
    current_user: TokenPayload = Depends(auth_dependency.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users (admin only)."""
    # TODO: Add admin role check
    service = UserService(db)
    return await service.get_users(page, page_size, role)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: TokenPayload = Depends(auth_dependency.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user by ID."""
    service = UserService(db)
    return await service.get_user(user_id)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    update_data: UserUpdate,
    current_user: TokenPayload = Depends(auth_dependency.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user profile."""
    service = UserService(db)
    return await service.update_user(
        user_id,
        update_data,
        int(current_user.sub),
    )


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    current_user: TokenPayload = Depends(auth_dependency.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete user (soft delete)."""
    # TODO: Add admin role check or self-delete only
    service = UserService(db)
    await service.delete_user(user_id)
    return {"message": "User deleted successfully"}
```

### 4.14 `services/user-service/app/database.py`

```python
"""Database Configuration."""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

from smartcourse_shared.database.postgres import PostgresDatabase

from .config import get_settings


settings = get_settings()
database = PostgresDatabase(settings.DATABASE_URL, echo=settings.DEBUG)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database session."""
    async for session in database.get_session():
        yield session
```

### 4.15 `services/user-service/app/main.py`

```python
"""User Service Main Application."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from smartcourse_shared.exceptions.handlers import (
    AppException,
    app_exception_handler,
    validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError

from .config import get_settings
from .database import database
from .routes import auth, users


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    await database.create_tables()
    yield
    # Shutdown
    await database.close()


app = FastAPI(
    title="SmartCourse User Service",
    description="User management microservice for SmartCourse",
    version=settings.VERSION,
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/users", tags=["Users"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "version": settings.VERSION,
    }
```

---

## 5. Course Service

### 5.1 `services/course-service/Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy shared library first
COPY shared /app/shared
RUN pip install /app/shared

# Copy requirements and install
COPY services/course-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/course-service/app ./app
COPY services/course-service/alembic.ini .
COPY services/course-service/alembic ./alembic

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 5.2 `services/course-service/requirements.txt`

```text
fastapi==0.109.2
uvicorn[standard]==0.27.1
sqlalchemy==2.0.25
asyncpg==0.29.0
alembic==1.13.1
motor==3.3.2
beanie==1.25.0
pydantic==2.6.1
pydantic-settings==2.1.0
python-jose[cryptography]==3.3.0
python-slugify==8.0.1
```

### 5.3 `services/course-service/app/models/course.py`

```python
"""Course Model (PostgreSQL)."""

from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Enum as SQLEnum,
    Text,
    Numeric,
    ForeignKey,
)

from smartcourse_shared.database.postgres import Base


class CourseLevel(str, Enum):
    """Course difficulty levels."""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class CourseStatus(str, Enum):
    """Course status."""
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Course(Base):
    """Course model - stores in PostgreSQL."""

    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, index=True, nullable=False)
    description = Column(Text)
    long_description = Column(Text)
    instructor_id = Column(Integer, nullable=False, index=True)  # FK to users
    category = Column(String(100), index=True)
    level = Column(SQLEnum(CourseLevel))
    language = Column(String(50), default="en")
    duration_hours = Column(Numeric(5, 2))
    price = Column(Numeric(10, 2), default=0.00)
    currency = Column(String(3), default="USD")
    thumbnail_url = Column(String(500))
    video_preview_url = Column(String(500))
    status = Column(
        SQLEnum(CourseStatus),
        default=CourseStatus.DRAFT,
        index=True,
    )
    published_at = Column(DateTime)
    max_students = Column(Integer)
    prerequisites = Column(Text)
    learning_objectives = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    is_deleted = Column(Boolean, default=False)

    def __repr__(self):
        return f"<Course {self.title}>"
```

### 5.4 `services/course-service/app/documents/course_content.py`

```python
"""Course Content Document (MongoDB)."""

from datetime import datetime
from typing import List, Optional
from beanie import Document
from pydantic import Field


class Lesson(BaseModel):
    """Lesson within a module."""
    lesson_id: int
    title: str
    description: Optional[str] = None
    type: str  # video, text, quiz, assignment
    content: Optional[str] = None  # For text lessons
    video_url: Optional[str] = None
    duration_minutes: Optional[int] = None
    order: int
    is_preview: bool = False
    is_mandatory: bool = True


class Module(BaseModel):
    """Module within a course."""
    module_id: int
    title: str
    description: Optional[str] = None
    order: int
    is_published: bool = False
    lessons: List[Lesson] = Field(default_factory=list)


class CourseContent(Document):
    """Course content stored in MongoDB for flexibility."""

    course_id: int = Field(..., unique=True)
    modules: List[Module] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    total_modules: int = 0
    total_lessons: int = 0
    total_duration_minutes: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "course_contents"

    def add_module(self, module: Module):
        """Add a module to the course."""
        # Auto-increment module_id
        max_id = max([m.module_id for m in self.modules], default=0)
        module.module_id = max_id + 1
        module.order = len(self.modules) + 1
        self.modules.append(module)
        self._recalculate_totals()

    def add_lesson_to_module(self, module_id: int, lesson: Lesson):
        """Add a lesson to a specific module."""
        for module in self.modules:
            if module.module_id == module_id:
                max_id = max([l.lesson_id for l in module.lessons], default=0)
                lesson.lesson_id = max_id + 1
                lesson.order = len(module.lessons) + 1
                module.lessons.append(lesson)
                self._recalculate_totals()
                return
        raise ValueError(f"Module {module_id} not found")

    def _recalculate_totals(self):
        """Recalculate total modules, lessons, and duration."""
        self.total_modules = len(self.modules)
        self.total_lessons = sum(len(m.lessons) for m in self.modules)
        self.total_duration_minutes = sum(
            l.duration_minutes or 0
            for m in self.modules
            for l in m.lessons
        )
        self.updated_at = datetime.utcnow()


# Need to import BaseModel from pydantic
from pydantic import BaseModel
```

### 5.5 `services/course-service/app/schemas/course.py`

```python
"""Course Schemas."""

from datetime import datetime
from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel, Field

from smartcourse_shared.schemas.base import BaseSchema, TimestampMixin


class CourseBase(BaseSchema):
    """Base course schema."""
    title: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = None
    long_description: Optional[str] = None
    category: Optional[str] = Field(None, max_length=100)
    level: Optional[str] = None
    language: str = "en"
    price: Decimal = Decimal("0.00")
    currency: str = "USD"
    max_students: Optional[int] = None
    prerequisites: Optional[str] = None
    learning_objectives: Optional[str] = None


class CourseCreate(CourseBase):
    """Course creation schema."""
    pass


class CourseUpdate(BaseSchema):
    """Course update schema."""
    title: Optional[str] = Field(None, min_length=3, max_length=255)
    description: Optional[str] = None
    long_description: Optional[str] = None
    category: Optional[str] = None
    level: Optional[str] = None
    language: Optional[str] = None
    price: Optional[Decimal] = None
    currency: Optional[str] = None
    max_students: Optional[int] = None
    prerequisites: Optional[str] = None
    learning_objectives: Optional[str] = None
    thumbnail_url: Optional[str] = None
    video_preview_url: Optional[str] = None


class CourseResponse(CourseBase, TimestampMixin):
    """Course response schema."""
    id: int
    slug: str
    instructor_id: int
    status: str
    published_at: Optional[datetime] = None
    thumbnail_url: Optional[str] = None
    video_preview_url: Optional[str] = None
    duration_hours: Optional[float] = None


class CourseListResponse(BaseSchema):
    """Course list item response."""
    id: int
    title: str
    slug: str
    description: Optional[str] = None
    instructor_id: int
    category: Optional[str] = None
    level: Optional[str] = None
    price: Decimal
    status: str
    thumbnail_url: Optional[str] = None
```

### 5.6 `services/course-service/app/schemas/module.py`

```python
"""Module and Lesson Schemas."""

from typing import Optional, List
from pydantic import BaseModel, Field

from smartcourse_shared.schemas.base import BaseSchema


class LessonCreate(BaseSchema):
    """Lesson creation schema."""
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    type: str = Field(..., pattern="^(video|text|quiz|assignment)$")
    content: Optional[str] = None
    video_url: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, ge=0)
    is_preview: bool = False
    is_mandatory: bool = True


class LessonUpdate(BaseSchema):
    """Lesson update schema."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    type: Optional[str] = Field(None, pattern="^(video|text|quiz|assignment)$")
    content: Optional[str] = None
    video_url: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, ge=0)
    is_preview: Optional[bool] = None
    is_mandatory: Optional[bool] = None


class LessonResponse(BaseSchema):
    """Lesson response schema."""
    lesson_id: int
    title: str
    description: Optional[str] = None
    type: str
    content: Optional[str] = None
    video_url: Optional[str] = None
    duration_minutes: Optional[int] = None
    order: int
    is_preview: bool
    is_mandatory: bool


class ModuleCreate(BaseSchema):
    """Module creation schema."""
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class ModuleUpdate(BaseSchema):
    """Module update schema."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    is_published: Optional[bool] = None


class ModuleResponse(BaseSchema):
    """Module response schema."""
    module_id: int
    title: str
    description: Optional[str] = None
    order: int
    is_published: bool
    lessons: List[LessonResponse] = []


class CourseContentResponse(BaseSchema):
    """Full course content response."""
    course_id: int
    modules: List[ModuleResponse]
    total_modules: int
    total_lessons: int
    total_duration_minutes: int
```

---

## 6. Enrollment Service

### 6.1 `services/enrollment-service/Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy shared library first
COPY shared /app/shared
RUN pip install /app/shared

# Copy requirements and install
COPY services/enrollment-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/enrollment-service/app ./app
COPY services/enrollment-service/alembic.ini .
COPY services/enrollment-service/alembic ./alembic

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 6.2 `services/enrollment-service/app/models/enrollment.py`

```python
"""Enrollment Model."""

from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Enum as SQLEnum,
    Numeric,
    UniqueConstraint,
)

from smartcourse_shared.database.postgres import Base


class EnrollmentStatus(str, Enum):
    """Enrollment status."""
    ACTIVE = "active"
    COMPLETED = "completed"
    DROPPED = "dropped"
    SUSPENDED = "suspended"


class PaymentStatus(str, Enum):
    """Payment status."""
    PENDING = "pending"
    COMPLETED = "completed"
    REFUNDED = "refunded"


class Enrollment(Base):
    """Enrollment model."""

    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="uq_student_course"),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, nullable=False, index=True)
    course_id = Column(Integer, nullable=False, index=True)
    status = Column(
        SQLEnum(EnrollmentStatus),
        default=EnrollmentStatus.ACTIVE,
        index=True,
    )
    enrolled_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    dropped_at = Column(DateTime)
    completion_percentage = Column(Numeric(5, 2), default=0.00)
    last_accessed_at = Column(DateTime)
    payment_status = Column(SQLEnum(PaymentStatus))
    payment_amount = Column(Numeric(10, 2))
    payment_id = Column(String(255))
    enrollment_source = Column(String(100))
    notes = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Enrollment student={self.student_id} course={self.course_id}>"
```

### 6.3 `services/enrollment-service/app/schemas/enrollment.py`

```python
"""Enrollment Schemas."""

from datetime import datetime
from typing import Optional
from decimal import Decimal
from pydantic import BaseModel, Field

from smartcourse_shared.schemas.base import BaseSchema, TimestampMixin


class EnrollmentCreate(BaseSchema):
    """Enrollment creation schema."""
    course_id: int
    payment_amount: Optional[Decimal] = None
    payment_id: Optional[str] = None
    enrollment_source: str = "web"


class EnrollmentResponse(BaseSchema, TimestampMixin):
    """Enrollment response schema."""
    id: int
    student_id: int
    course_id: int
    status: str
    enrolled_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    completion_percentage: float
    last_accessed_at: Optional[datetime] = None
    payment_status: Optional[str] = None
    payment_amount: Optional[Decimal] = None


class EnrollmentListResponse(BaseSchema):
    """Enrollment list item response."""
    id: int
    course_id: int
    status: str
    enrolled_at: datetime
    completion_percentage: float


class EnrollmentUpdateStatus(BaseSchema):
    """Update enrollment status schema."""
    status: str = Field(..., pattern="^(active|dropped|suspended)$")
    reason: Optional[str] = None
```

---

## 7. Progress Service

### 7.1 `services/progress-service/app/models/progress.py`

```python
"""Progress Model."""

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    DateTime,
    Numeric,
    ARRAY,
    JSON,
)

from smartcourse_shared.database.postgres import Base


class Progress(Base):
    """Progress tracking model."""

    __tablename__ = "progress"

    id = Column(Integer, primary_key=True, index=True)
    enrollment_id = Column(Integer, unique=True, nullable=False, index=True)
    completed_modules = Column(ARRAY(Integer), default=[])
    completed_lessons = Column(ARRAY(Integer), default=[])
    total_modules = Column(Integer, nullable=False)
    total_lessons = Column(Integer, nullable=False)
    completed_quizzes = Column(ARRAY(Integer), default=[])
    quiz_scores = Column(JSON, default={})
    time_spent_minutes = Column(Integer, default=0)
    current_module_id = Column(Integer)
    current_lesson_id = Column(Integer)
    last_accessed_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    @property
    def completion_percentage(self) -> float:
        """Calculate completion percentage."""
        if self.total_lessons == 0:
            return 0.0
        return (len(self.completed_lessons or []) / self.total_lessons) * 100

    def __repr__(self):
        return f"<Progress enrollment={self.enrollment_id}>"
```

### 7.2 `services/progress-service/app/schemas/progress.py`

```python
"""Progress Schemas."""

from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, Field

from smartcourse_shared.schemas.base import BaseSchema


class ProgressResponse(BaseSchema):
    """Progress response schema."""
    id: int
    enrollment_id: int
    completed_modules: List[int]
    completed_lessons: List[int]
    total_modules: int
    total_lessons: int
    completed_quizzes: List[int]
    quiz_scores: Dict[str, float]
    time_spent_minutes: int
    current_module_id: Optional[int] = None
    current_lesson_id: Optional[int] = None
    completion_percentage: float
    last_accessed_at: datetime


class LessonCompleteRequest(BaseSchema):
    """Mark lesson as complete request."""
    lesson_id: int
    time_spent_minutes: int = 0


class QuizSubmitRequest(BaseSchema):
    """Submit quiz request."""
    quiz_id: int
    score: float = Field(..., ge=0, le=100)


class ProgressSummary(BaseSchema):
    """Progress summary response."""
    enrollment_id: int
    completion_percentage: float
    completed_modules: int
    total_modules: int
    completed_lessons: int
    total_lessons: int
    time_spent_minutes: int
    average_quiz_score: Optional[float] = None
```

---

## 8. Certificate Service

### 8.1 `services/certificate-service/app/models/certificate.py`

```python
"""Certificate Model."""

from datetime import datetime, date
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Date,
    Numeric,
    Text,
)

from smartcourse_shared.database.postgres import Base


class Certificate(Base):
    """Certificate model."""

    __tablename__ = "certificates"

    id = Column(Integer, primary_key=True, index=True)
    enrollment_id = Column(Integer, unique=True, nullable=False, index=True)
    student_id = Column(Integer, nullable=False, index=True)
    course_id = Column(Integer, nullable=False, index=True)
    certificate_number = Column(String(100), unique=True, nullable=False, index=True)
    issue_date = Column(Date, nullable=False)
    certificate_url = Column(String(500))
    verification_code = Column(String(50), unique=True, nullable=False, index=True)
    grade = Column(String(10))
    score_percentage = Column(Numeric(5, 2))
    issued_by_id = Column(Integer)
    notes = Column(Text)
    is_revoked = Column(Boolean, default=False)
    revoked_at = Column(DateTime)
    revoked_reason = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Certificate {self.certificate_number}>"
```

### 8.2 `services/certificate-service/app/schemas/certificate.py`

```python
"""Certificate Schemas."""

from datetime import datetime, date
from typing import Optional
from decimal import Decimal
from pydantic import BaseModel, Field

from smartcourse_shared.schemas.base import BaseSchema


class CertificateCreate(BaseSchema):
    """Certificate creation schema (internal use)."""
    enrollment_id: int
    student_id: int
    course_id: int
    grade: Optional[str] = None
    score_percentage: Optional[Decimal] = None
    issued_by_id: Optional[int] = None


class CertificateResponse(BaseSchema):
    """Certificate response schema."""
    id: int
    enrollment_id: int
    student_id: int
    course_id: int
    certificate_number: str
    issue_date: date
    certificate_url: Optional[str] = None
    verification_code: str
    grade: Optional[str] = None
    score_percentage: Optional[float] = None
    is_revoked: bool
    created_at: datetime


class CertificateVerifyResponse(BaseSchema):
    """Public certificate verification response."""
    valid: bool
    certificate_number: Optional[str] = None
    student_name: Optional[str] = None
    course_title: Optional[str] = None
    issue_date: Optional[date] = None
    grade: Optional[str] = None
    is_revoked: bool = False
    message: str


class CertificateRevokeRequest(BaseSchema):
    """Revoke certificate request."""
    reason: str = Field(..., min_length=10)
```

---

## 9. Docker Compose

### 9.1 `docker-compose.yml`

```yaml
version: "3.8"

services:
  # ==================== INFRASTRUCTURE ====================

  postgres:
    image: postgres:15-alpine
    container_name: smartcourse-postgres
    environment:
      POSTGRES_DB: smartcourse
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres123
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./migrations/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  mongodb:
    image: mongo:7
    container_name: smartcourse-mongodb
    environment:
      MONGO_INITDB_ROOT_USERNAME: mongo
      MONGO_INITDB_ROOT_PASSWORD: mongo123
    ports:
      - "27017:27017"
    volumes:
      - mongodb_data:/data/db
    healthcheck:
      test: echo 'db.runCommand("ping").ok' | mongosh localhost:27017/test --quiet
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: smartcourse-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  # ==================== MICROSERVICES ====================

  # Nginx API Gateway
  nginx:
    build:
      context: ./nginx
      dockerfile: Dockerfile
    container_name: smartcourse-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - nginx_logs:/var/log/nginx
    depends_on:
      - user-service
      - course-service
      - enrollment-service
      - progress-service
      - certificate-service
    restart: unless-stopped
    healthcheck:
      test:
        [
          "CMD",
          "wget",
          "--no-verbose",
          "--tries=1",
          "--spider",
          "http://localhost/health",
        ]
      interval: 30s
      timeout: 10s
      retries: 3

  user-service:
    build:
      context: .
      dockerfile: services/user-service/Dockerfile
    container_name: smartcourse-user-service
    ports:
      - "8001:8000"
    environment:
      - SERVICE_NAME=user-service
      - DEBUG=true
      - DATABASE_URL=postgresql://postgres:postgres123@postgres:5432/smartcourse
      - REDIS_URL=redis://redis:6379
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

  course-service:
    build:
      context: .
      dockerfile: services/course-service/Dockerfile
    container_name: smartcourse-course-service
    ports:
      - "8002:8000"
    environment:
      - SERVICE_NAME=course-service
      - DEBUG=true
      - DATABASE_URL=postgresql://postgres:postgres123@postgres:5432/smartcourse
      - MONGODB_URL=mongodb://mongo:mongo123@mongodb:27017
      - MONGODB_DATABASE=smartcourse
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
    depends_on:
      postgres:
        condition: service_healthy
      mongodb:
        condition: service_healthy
    restart: unless-stopped

  enrollment-service:
    build:
      context: .
      dockerfile: services/enrollment-service/Dockerfile
    container_name: smartcourse-enrollment-service
    ports:
      - "8003:8000"
    environment:
      - SERVICE_NAME=enrollment-service
      - DEBUG=true
      - DATABASE_URL=postgresql://postgres:postgres123@postgres:5432/smartcourse
      - REDIS_URL=redis://redis:6379
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - COURSE_SERVICE_URL=http://course-service:8000
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

  progress-service:
    build:
      context: .
      dockerfile: services/progress-service/Dockerfile
    container_name: smartcourse-progress-service
    ports:
      - "8004:8000"
    environment:
      - SERVICE_NAME=progress-service
      - DEBUG=true
      - DATABASE_URL=postgresql://postgres:postgres123@postgres:5432/smartcourse
      - REDIS_URL=redis://redis:6379
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped

  certificate-service:
    build:
      context: .
      dockerfile: services/certificate-service/Dockerfile
    container_name: smartcourse-certificate-service
    ports:
      - "8005:8000"
    environment:
      - SERVICE_NAME=certificate-service
      - DEBUG=true
      - DATABASE_URL=postgresql://postgres:postgres123@postgres:5432/smartcourse
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

volumes:
  postgres_data:
  mongodb_data:
  redis_data:
  nginx_logs:
```

---

## 10. Environment Variables

### 10.1 `.env.example`

```bash
# JWT Configuration
JWT_SECRET_KEY=your-super-secret-key-change-in-production-min-32-chars

# Database
POSTGRES_DB=smartcourse
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres123
DATABASE_URL=postgresql://postgres:postgres123@localhost:5432/smartcourse

# MongoDB
MONGO_INITDB_ROOT_USERNAME=mongo
MONGO_INITDB_ROOT_PASSWORD=mongo123
MONGODB_URL=mongodb://mongo:mongo123@localhost:27017
MONGODB_DATABASE=smartcourse

# Redis
REDIS_URL=redis://localhost:6379

# Service URLs (for local development)
USER_SERVICE_URL=http://localhost:8001
COURSE_SERVICE_URL=http://localhost:8002
ENROLLMENT_SERVICE_URL=http://localhost:8003
PROGRESS_SERVICE_URL=http://localhost:8004
CERTIFICATE_SERVICE_URL=http://localhost:8005

# Debug Mode
DEBUG=true
```

---

## 11. Database Migrations

### 11.1 `migrations/init.sql`

```sql
-- Initial database setup script
-- This runs when PostgreSQL container starts for the first time

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create enum types
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
        CREATE TYPE user_role AS ENUM ('student', 'instructor', 'admin');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'course_level') THEN
        CREATE TYPE course_level AS ENUM ('beginner', 'intermediate', 'advanced');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'course_status') THEN
        CREATE TYPE course_status AS ENUM ('draft', 'published', 'archived');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'enrollment_status') THEN
        CREATE TYPE enrollment_status AS ENUM ('active', 'completed', 'dropped', 'suspended');
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'payment_status') THEN
        CREATE TYPE payment_status AS ENUM ('pending', 'completed', 'refunded');
    END IF;
END
$$;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE smartcourse TO postgres;
```

### 11.2 Alembic Setup for Each Service

Create `alembic/env.py` for each service:

```python
"""Alembic migration environment."""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import your models
from app.models import *  # noqa
from smartcourse_shared.database.postgres import Base
from app.config import get_settings

settings = get_settings()
config = context.config

# Set the database URL from settings
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace(
    "postgresql://", "postgresql+asyncpg://"
))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

---

## 12. Testing Setup

### 12.1 `services/user-service/tests/conftest.py`

```python
"""Test configuration and fixtures."""

import asyncio
import pytest
from typing import AsyncGenerator
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from smartcourse_shared.database.postgres import Base
from app.main import app
from app.database import get_db


# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres123@localhost:5432/smartcourse_test"


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create database session for tests."""
    async_session = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """Create test client."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
```

### 12.2 `services/user-service/tests/test_users.py`

```python
"""User service tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    """Test user registration."""
    response = await client.post(
        "/auth/register",
        json={
            "email": "test@example.com",
            "username": "testuser",
            "password": "password123",
            "first_name": "Test",
            "last_name": "User",
            "role": "student",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert data["username"] == "testuser"
    assert data["role"] == "student"


@pytest.mark.asyncio
async def test_login_user(client: AsyncClient):
    """Test user login."""
    # First register
    await client.post(
        "/auth/register",
        json={
            "email": "login@example.com",
            "username": "loginuser",
            "password": "password123",
            "role": "student",
        },
    )

    # Then login
    response = await client.post(
        "/auth/login",
        json={
            "email": "login@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_get_current_user(client: AsyncClient):
    """Test getting current user."""
    # Register and login
    await client.post(
        "/auth/register",
        json={
            "email": "me@example.com",
            "username": "meuser",
            "password": "password123",
            "role": "student",
        },
    )
    login_response = await client.post(
        "/auth/login",
        json={
            "email": "me@example.com",
            "password": "password123",
        },
    )
    token = login_response.json()["access_token"]

    # Get current user
    response = await client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "me@example.com"
```

---

## 13. Implementation Checklist

### Week 1 Day-by-Day Checklist

#### Day 1: Project Setup

- [ ] Create project directory structure
- [ ] Initialize git repository
- [ ] Create shared library package
- [ ] Set up Docker Compose with infrastructure services
- [ ] Verify PostgreSQL, MongoDB, Redis are running
- [ ] Create `.env` file with required variables

#### Day 2: Shared Library & User Service Models

- [ ] Implement JWT handler in shared library
- [ ] Implement auth dependencies
- [ ] Implement database connections (PostgreSQL, MongoDB, Redis)
- [ ] Implement exception handlers
- [ ] Implement password utilities
- [ ] Create User, InstructorProfile, RefreshToken models
- [ ] Set up Alembic migrations for User Service

#### Day 3: User Service Implementation

- [ ] Implement UserRepository
- [ ] Implement AuthService (register, login, refresh, logout)
- [ ] Implement UserService (CRUD operations)
- [ ] Create auth routes
- [ ] Create user routes
- [ ] Test User Service endpoints with Postman/curl

#### Day 4: Course Service Implementation

- [ ] Create Course model (PostgreSQL)
- [ ] Create CourseContent document (MongoDB)
- [ ] Implement CourseRepository
- [ ] Implement ContentRepository
- [ ] Implement CourseService
- [ ] Create course routes
- [ ] Create module/lesson routes
- [ ] Test Course Service endpoints

#### Day 5: Enrollment & Progress Services

- [ ] Create Enrollment model
- [ ] Implement EnrollmentRepository
- [ ] Implement EnrollmentService with validation
- [ ] Create enrollment routes
- [ ] Create Progress model
- [ ] Implement ProgressRepository
- [ ] Implement ProgressService
- [ ] Create progress routes

#### Day 6: Certificate Service & Nginx API Gateway

- [ ] Create Certificate model
- [ ] Implement CertificateRepository
- [ ] Implement CertificateService
- [ ] Create certificate routes (including public verify)
- [ ] Create Nginx configuration files
- [ ] Configure upstream servers in Nginx
- [ ] Configure rate limiting in Nginx
- [ ] Test all routes through Nginx API Gateway

#### Day 7: Integration & Testing

- [ ] Write unit tests for each service
- [ ] Write integration tests for main flows
- [ ] Test complete user journey:
  - Register → Login → Create Course → Enroll → Progress → Certificate
- [ ] Fix any bugs found
- [ ] Document API endpoints
- [ ] Update README with setup instructions

---

## Quick Start Commands

```bash
# Create .env file
cp .env.example .env

# Generate JWT secret key
echo "JWT_SECRET_KEY=$(openssl rand -hex 32)" >> .env

# Start all services
docker-compose up -d

# Check logs
docker-compose logs -f

# Check Nginx logs specifically
docker-compose logs -f nginx

# Run migrations (for each service)
docker-compose exec user-service alembic upgrade head
docker-compose exec course-service alembic upgrade head
docker-compose exec enrollment-service alembic upgrade head
docker-compose exec progress-service alembic upgrade head
docker-compose exec certificate-service alembic upgrade head

# Access services via Nginx API Gateway
# API Gateway (Nginx): http://localhost (port 80)
# Health Check: http://localhost/health

# Direct service access (for debugging)
# User Service: http://localhost:8001
# Course Service: http://localhost:8002
# Enrollment Service: http://localhost:8003
# Progress Service: http://localhost:8004
# Certificate Service: http://localhost:8005

# Service API Documentation (direct access)
# http://localhost:8001/docs  (User Service)
# http://localhost:8002/docs  (Course Service)
# http://localhost:8003/docs  (Enrollment Service)
# http://localhost:8004/docs  (Progress Service)
# http://localhost:8005/docs  (Certificate Service)

# Test Nginx configuration
docker-compose exec nginx nginx -t

# Reload Nginx configuration without downtime
docker-compose exec nginx nginx -s reload

# Stop all services
docker-compose down

# Stop and remove volumes (fresh start)
docker-compose down -v
```

---

## API Endpoints Summary

### Authentication (via API Gateway)

| Method | Endpoint                | Description       | Auth |
| ------ | ----------------------- | ----------------- | ---- |
| POST   | `/api/v1/auth/register` | Register new user | No   |
| POST   | `/api/v1/auth/login`    | Login user        | No   |
| POST   | `/api/v1/auth/refresh`  | Refresh token     | No   |
| POST   | `/api/v1/auth/logout`   | Logout user       | Yes  |

### Users

| Method | Endpoint             | Description      | Auth  |
| ------ | -------------------- | ---------------- | ----- |
| GET    | `/api/v1/users/me`   | Get current user | Yes   |
| GET    | `/api/v1/users`      | List users       | Admin |
| GET    | `/api/v1/users/{id}` | Get user by ID   | Yes   |
| PUT    | `/api/v1/users/{id}` | Update user      | Yes   |
| DELETE | `/api/v1/users/{id}` | Delete user      | Admin |

### Courses

| Method | Endpoint                             | Description    | Auth       |
| ------ | ------------------------------------ | -------------- | ---------- |
| GET    | `/api/v1/courses`                    | List courses   | No         |
| POST   | `/api/v1/courses`                    | Create course  | Instructor |
| GET    | `/api/v1/courses/{id}`               | Get course     | No         |
| PUT    | `/api/v1/courses/{id}`               | Update course  | Instructor |
| DELETE | `/api/v1/courses/{id}`               | Archive course | Instructor |
| POST   | `/api/v1/courses/{id}/modules`       | Add module     | Instructor |
| PUT    | `/api/v1/courses/{id}/modules/{mid}` | Update module  | Instructor |
| DELETE | `/api/v1/courses/{id}/modules/{mid}` | Delete module  | Instructor |

### Enrollments

| Method | Endpoint                         | Description        | Auth    |
| ------ | -------------------------------- | ------------------ | ------- |
| POST   | `/api/v1/enrollments`            | Enroll in course   | Student |
| GET    | `/api/v1/enrollments/my-courses` | Get my enrollments | Student |
| GET    | `/api/v1/enrollments/{id}`       | Get enrollment     | Yes     |
| DELETE | `/api/v1/enrollments/{id}`       | Drop course        | Student |

### Progress

| Method | Endpoint                                 | Description     | Auth    |
| ------ | ---------------------------------------- | --------------- | ------- |
| GET    | `/api/v1/progress/{enrollment_id}`       | Get progress    | Yes     |
| POST   | `/api/v1/progress/lessons/{id}/complete` | Complete lesson | Student |
| POST   | `/api/v1/progress/quizzes/{id}/submit`   | Submit quiz     | Student |

### Certificates

| Method | Endpoint                               | Description        | Auth    |
| ------ | -------------------------------------- | ------------------ | ------- |
| GET    | `/api/v1/certificates/my-certificates` | Get my certs       | Student |
| GET    | `/api/v1/certificates/{id}`            | Get certificate    | Yes     |
| GET    | `/api/v1/certificates/verify/{code}`   | Verify certificate | No      |
| POST   | `/api/v1/certificates/{id}/revoke`     | Revoke certificate | Admin   |

---

_Document Version: 1.1 | Last Updated: February 10, 2026 | API Gateway: Nginx_
