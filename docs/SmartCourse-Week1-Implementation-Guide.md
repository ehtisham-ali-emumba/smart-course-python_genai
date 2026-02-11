# SmartCourse - Week 1 Implementation Guide

**Version:** 1.0  
**Date:** February 11, 2026  
**Author:** SmartCourse Architecture Team  
**Scope:** Week 1 - Foundation Setup & Core Services Implementation

---

## 1. Overview

This guide provides step-by-step instructions for implementing the SmartCourse platform foundation. Follow these guidelines precisely to ensure consistent, maintainable code.

---

## 2. Project Structure

### 2.1 Root Directory Structure

```
smart-course/
├── docker-compose.yml              # Root docker-compose for all services
├── docker-compose.dev.yml          # Development overrides
├── docker-compose.prod.yml         # Production overrides
├── .env.example                    # Environment variables template
├── .gitignore
├── README.md
├── docs/                           # Documentation
│   ├── SmartCourse-System-Design.md
│   ├── SmartCourse-ERD-Complete.md
│   └── SmartCourse-Week1-Implementation-Guide.md
├── shared/                         # Shared code across microservices
│   ├── pyproject.toml
│   ├── shared/
│   │   ├── __init__.py
│   │   ├── schemas/                # Shared Pydantic schemas
│   │   │   ├── __init__.py
│   │   │   ├── base.py             # Base response schemas
│   │   │   └── pagination.py       # Pagination schemas
│   │   ├── utils/                  # Shared utilities
│   │   │   ├── __init__.py
│   │   │   ├── datetime.py         # Date/time helpers
│   │   │   ├── hashing.py          # Password hashing (bcrypt)
│   │   │   └── validators.py       # Common validators
│   │   ├── exceptions/             # Custom exceptions
│   │   │   ├── __init__.py
│   │   │   └── base.py
│   │   ├── middleware/             # Shared middleware
│   │   │   ├── __init__.py
│   │   │   └── logging.py
│   │   └── config/                 # Shared config patterns
│   │       ├── __init__.py
│   │       └── settings.py         # Base settings class
│   └── tests/
├── services/
│   ├── api-gateway/                # API Gateway service
│   ├── user-service/               # User & Auth service
│   ├── course-service/             # Course + Enrollment + Progress + Certificate
│   └── notification-service/       # Notification service
└── infrastructure/                 # Infrastructure configs
    ├── postgres/
    │   └── init.sql
    ├── mongodb/
    │   └── init.js
    └── redis/
        └── redis.conf
```

### 2.2 Microservice Internal Structure

**IMPORTANT: File naming convention - Do NOT include folder names in file names.**

Example: Use `repositories/user.py` NOT `repositories/user_repository.py`

```
services/user-service/
├── Dockerfile                      # Service-specific Dockerfile
├── pyproject.toml                  # Dependencies (NO requirements.txt)
├── .env.example
├── venv/                           # Virtual environment (gitignored)
├── src/
│   └── user_service/               # Main package (use underscores)
│       ├── __init__.py
│       ├── main.py                 # FastAPI app entry point
│       ├── config.py               # Service configuration
│       ├── api/                    # API layer
│       │   ├── __init__.py
│       │   ├── router.py           # Main router aggregating all routes
│       │   ├── auth.py             # Auth endpoints (NOT auth_routes.py)
│       │   ├── users.py            # User endpoints (NOT user_routes.py)
│       │   ├── instructors.py      # Instructor endpoints
│       │   └── deps.py             # Route dependencies
│       ├── models/                 # SQLAlchemy models
│       │   ├── __init__.py
│       │   ├── user.py             # User model (NOT user_model.py)
│       │   └── instructor.py       # InstructorProfile model
│       ├── schemas/                # Pydantic schemas
│       │   ├── __init__.py
│       │   ├── user.py             # User schemas (NOT user_schema.py)
│       │   ├── auth.py             # Auth schemas
│       │   └── instructor.py       # Instructor schemas
│       ├── repositories/           # Data access layer
│       │   ├── __init__.py
│       │   ├── base.py             # Base repository class
│       │   ├── user.py             # User repository (NOT user_repository.py)
│       │   └── instructor.py       # Instructor repository
│       ├── services/               # Business logic layer
│       │   ├── __init__.py
│       │   ├── auth.py             # Auth service (NOT auth_service.py)
│       │   └── user.py             # User service
│       ├── core/                   # Core utilities
│       │   ├── __init__.py
│       │   ├── security.py         # JWT, password hashing
│       │   └── database.py         # Database connection
│       └── events/                 # Kafka event producers
│           ├── __init__.py
│           └── producer.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── unit/
    └── integration/
```

---

## 3. Docker Configuration

### 3.1 Service Dockerfile Template

Each microservice MUST have its own Dockerfile in the service root:

```dockerfile
# services/user-service/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy shared library (mounted or copied during build)
COPY --from=shared /app/shared /app/shared

# Copy service code
COPY src/ ./src/

# Set Python path
ENV PYTHONPATH=/app/src:/app

# Expose port
EXPOSE 8001

# Run with uvicorn
CMD ["uvicorn", "user_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

### 3.2 Root docker-compose.yml

```yaml
# docker-compose.yml
version: "3.9"

services:
  # ==================== INFRASTRUCTURE ====================
  postgres:
    image: postgres:15-alpine
    container_name: smartcourse-postgres
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-smartcourse}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-smartcourse_secret}
      POSTGRES_DB: ${POSTGRES_DB:-smartcourse}
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./infrastructure/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U smartcourse"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - smartcourse-network

  mongodb:
    image: mongo:7
    container_name: smartcourse-mongodb
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${MONGO_USER:-smartcourse}
      MONGO_INITDB_ROOT_PASSWORD: ${MONGO_PASSWORD:-smartcourse_secret}
    ports:
      - "27017:27017"
    volumes:
      - mongodb_data:/data/db
      - ./infrastructure/mongodb/init.js:/docker-entrypoint-initdb.d/init.js
    healthcheck:
      test: echo 'db.runCommand("ping").ok' | mongosh localhost:27017/test --quiet
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - smartcourse-network

  redis:
    image: redis:7-alpine
    container_name: smartcourse-redis
    command: redis-server --requirepass ${REDIS_PASSWORD:-smartcourse_secret}
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test:
        [
          "CMD",
          "redis-cli",
          "-a",
          "${REDIS_PASSWORD:-smartcourse_secret}",
          "ping",
        ]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - smartcourse-network

  # ==================== MICROSERVICES ====================
  api-gateway:
    build:
      context: ./services/api-gateway
      dockerfile: Dockerfile
    container_name: smartcourse-api-gateway
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://:${REDIS_PASSWORD:-smartcourse_secret}@redis:6379/0
      - USER_SERVICE_URL=http://user-service:8001
      - COURSE_SERVICE_URL=http://course-service:8002
      - NOTIFICATION_SERVICE_URL=http://notification-service:8005
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - JWT_ALGORITHM=HS256
    depends_on:
      redis:
        condition: service_healthy
      user-service:
        condition: service_started
      course-service:
        condition: service_started
    volumes:
      - ./shared:/app/shared:ro
    networks:
      - smartcourse-network

  user-service:
    build:
      context: ./services/user-service
      dockerfile: Dockerfile
    container_name: smartcourse-user-service
    ports:
      - "8001:8001"
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER:-smartcourse}:${POSTGRES_PASSWORD:-smartcourse_secret}@postgres:5432/${POSTGRES_DB:-smartcourse}
      - REDIS_URL=redis://:${REDIS_PASSWORD:-smartcourse_secret}@redis:6379/0
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - JWT_ALGORITHM=HS256
      - JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
      - JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./shared:/app/shared:ro
    networks:
      - smartcourse-network

  course-service:
    build:
      context: ./services/course-service
      dockerfile: Dockerfile
    container_name: smartcourse-course-service
    ports:
      - "8002:8002"
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER:-smartcourse}:${POSTGRES_PASSWORD:-smartcourse_secret}@postgres:5432/${POSTGRES_DB:-smartcourse}
      - MONGODB_URL=mongodb://${MONGO_USER:-smartcourse}:${MONGO_PASSWORD:-smartcourse_secret}@mongodb:27017/smartcourse?authSource=admin
      - REDIS_URL=redis://:${REDIS_PASSWORD:-smartcourse_secret}@redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      mongodb:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./shared:/app/shared:ro
    networks:
      - smartcourse-network

  notification-service:
    build:
      context: ./services/notification-service
      dockerfile: Dockerfile
    container_name: smartcourse-notification-service
    ports:
      - "8005:8005"
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER:-smartcourse}:${POSTGRES_PASSWORD:-smartcourse_secret}@postgres:5432/${POSTGRES_DB:-smartcourse}
      - REDIS_URL=redis://:${REDIS_PASSWORD:-smartcourse_secret}@redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./shared:/app/shared:ro
    networks:
      - smartcourse-network

networks:
  smartcourse-network:
    driver: bridge

volumes:
  postgres_data:
  mongodb_data:
  redis_data:
```

### 3.3 Running Services Without Docker (Using venv)

For local development without Docker, each service can be run using a virtual environment:

```bash
# Navigate to service directory
cd services/user-service

# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate  # macOS/Linux
# or
.\venv\Scripts\activate   # Windows

# Install dependencies from pyproject.toml
pip install -e .

# Install shared library (editable mode)
pip install -e ../../shared

# Set environment variables
export DATABASE_URL="postgresql://smartcourse:smartcourse_secret@localhost:5432/smartcourse"
export REDIS_URL="redis://:smartcourse_secret@localhost:6379/0"
export JWT_SECRET_KEY="your-secret-key"
export JWT_ALGORITHM="HS256"

# Run the service
uvicorn user_service.main:app --reload --port 8001
```

---

## 4. Dependencies (pyproject.toml)

### 4.1 Shared Library pyproject.toml

```toml
# shared/pyproject.toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "smartcourse-shared"
version = "0.1.0"
description = "Shared utilities for SmartCourse microservices"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "bcrypt>=4.1.0",
    "python-dateutil>=2.8.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["shared*"]
```

### 4.2 User Service pyproject.toml

```toml
# services/user-service/pyproject.toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "smartcourse-user-service"
version = "0.1.0"
description = "SmartCourse User & Authentication Service"
requires-python = ">=3.11"
dependencies = [
    # Web Framework
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",

    # Database
    "sqlalchemy>=2.0.25",
    "asyncpg>=0.29.0",

    # Cache
    "redis>=5.0.0",

    # Authentication
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",

    # Validation & Settings
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "email-validator>=2.1.0",

    # Utilities
    "python-multipart>=0.0.6",
    "httpx>=0.26.0",

    # Observability
    "opentelemetry-api>=1.22.0",
    "opentelemetry-sdk>=1.22.0",
    "opentelemetry-instrumentation-fastapi>=0.43b0",
    "opentelemetry-instrumentation-sqlalchemy>=0.43b0",
    "prometheus-client>=0.19.0",
    "structlog>=24.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "httpx>=0.26.0",
    "factory-boy>=3.3.0",
    "faker>=22.0.0",
    "ruff>=0.1.0",
    "black>=24.1.0",
    "mypy>=1.8.0",
]

[tool.setuptools.packages.find]
where = ["src"]
include = ["user_service*"]

[tool.ruff]
line-length = 100
select = ["E", "F", "I", "N", "W"]

[tool.black]
line-length = 100

[tool.mypy]
python_version = "3.11"
strict = true
```

### 4.3 Course Service pyproject.toml

```toml
# services/course-service/pyproject.toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "smartcourse-course-service"
version = "0.1.0"
description = "SmartCourse Course Management Service (Course + Enrollment + Progress + Certificate)"
requires-python = ">=3.11"
dependencies = [
    # Web Framework
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",

    # PostgreSQL
    "sqlalchemy>=2.0.25",
    "asyncpg>=0.29.0",

    # MongoDB
    "motor>=3.3.0",
    "pymongo>=4.6.0",

    # Cache
    "redis>=5.0.0",

    # Validation & Settings
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",

    # Utilities
    "python-multipart>=0.0.6",
    "httpx>=0.26.0",
    "python-slugify>=8.0.0",

    # File handling
    "aiofiles>=23.2.0",
    "python-magic>=0.4.27",

    # PDF generation (for certificates)
    "reportlab>=4.0.0",
    "weasyprint>=60.0",

    # Observability
    "opentelemetry-api>=1.22.0",
    "opentelemetry-sdk>=1.22.0",
    "opentelemetry-instrumentation-fastapi>=0.43b0",
    "prometheus-client>=0.19.0",
    "structlog>=24.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "httpx>=0.26.0",
    "factory-boy>=3.3.0",
    "faker>=22.0.0",
    "ruff>=0.1.0",
    "black>=24.1.0",
    "mypy>=1.8.0",
]

[tool.setuptools.packages.find]
where = ["src"]
include = ["course_service*"]
```

### 4.4 API Gateway pyproject.toml

```toml
# services/api-gateway/pyproject.toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "smartcourse-api-gateway"
version = "0.1.0"
description = "SmartCourse API Gateway - Frontend Interface & JWT Verification"
requires-python = ">=3.11"
dependencies = [
    # Web Framework
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",

    # HTTP Client (for proxying requests)
    "httpx>=0.26.0",

    # Cache & Rate Limiting
    "redis>=5.0.0",

    # JWT Verification (HS256)
    "python-jose[cryptography]>=3.3.0",

    # Validation & Settings
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",

    # Observability
    "opentelemetry-api>=1.22.0",
    "opentelemetry-sdk>=1.22.0",
    "opentelemetry-instrumentation-fastapi>=0.43b0",
    "opentelemetry-exporter-jaeger>=1.22.0",
    "prometheus-client>=0.19.0",
    "structlog>=24.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.26.0",
    "ruff>=0.1.0",
    "black>=24.1.0",
]

[tool.setuptools.packages.find]
where = ["src"]
include = ["api_gateway*"]
```

---

## 5. Authentication Architecture

### 5.1 JWT Configuration (HS256)

**IMPORTANT: Use HS256 (symmetric) algorithm for JWT signing.**

```python
# services/user-service/src/user_service/core/security.py
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from user_service.config import settings


# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenPayload(BaseModel):
    sub: str  # user_id
    exp: datetime
    iat: datetime
    type: str  # "access" or "refresh"
    role: str  # user role


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate password hash using bcrypt."""
    return pwd_context.hash(password)


def create_access_token(
    user_id: int,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create JWT access token using HS256.

    Args:
        user_id: The user's ID
        role: The user's role (student/instructor/admin)
        expires_delta: Optional custom expiry time

    Returns:
        Encoded JWT token string
    """
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )

    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
        "role": role,
    }

    # Use HS256 algorithm
    encoded_jwt = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,  # "HS256"
    )
    return encoded_jwt


def create_refresh_token(user_id: int, role: str) -> str:
    """Create JWT refresh token using HS256."""
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )

    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
        "role": role,
    }

    encoded_jwt = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded_jwt


def decode_token(token: str) -> TokenPayload:
    """
    Decode and validate JWT token.

    Raises:
        JWTError: If token is invalid or expired
    """
    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    return TokenPayload(**payload)
```

### 5.2 API Gateway - JWT Verification

**The API Gateway is the ONLY interface for frontend and handles ALL JWT verification:**

```python
# services/api-gateway/src/api_gateway/middleware/auth.py
from typing import Optional
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from api_gateway.config import settings


security = HTTPBearer(auto_error=False)


class JWTAuthMiddleware:
    """
    JWT verification middleware for API Gateway.

    The API Gateway is the ONLY point where JWT verification happens.
    Backend services trust requests coming from the gateway.
    """

    # Endpoints that don't require authentication
    PUBLIC_ENDPOINTS = [
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/refresh",
        "/api/courses",  # Public course listing
        "/health",
        "/docs",
        "/openapi.json",
    ]

    async def __call__(self, request: Request, call_next):
        # Skip auth for public endpoints
        path = request.url.path
        if self._is_public_endpoint(path):
            return await call_next(request)

        # Extract and verify JWT
        try:
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing or invalid authorization header",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            token = auth_header.split(" ")[1]
            payload = self._verify_token(token)

            # Add user info to request headers for downstream services
            request.state.user_id = payload["sub"]
            request.state.user_role = payload["role"]

            # Forward user context to downstream services
            # Services trust these headers from the gateway

        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )

        response = await call_next(request)
        return response

    def _is_public_endpoint(self, path: str) -> bool:
        """Check if endpoint is public."""
        for public_path in self.PUBLIC_ENDPOINTS:
            if path.startswith(public_path):
                return True
        return False

    def _verify_token(self, token: str) -> dict:
        """Verify JWT token using HS256."""
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],  # HS256
        )

        # Verify token type
        if payload.get("type") != "access":
            raise JWTError("Invalid token type")

        return payload
```

### 5.3 User Service - Auth Endpoints

**All auth-related endpoints exist in User Service:**

```python
# services/user-service/src/user_service/api/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from user_service.core.database import get_db
from user_service.core.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
    get_password_hash,
    decode_token,
)
from user_service.schemas.auth import (
    UserRegister,
    UserLogin,
    TokenResponse,
    RefreshTokenRequest,
)
from user_service.schemas.user import UserResponse
from user_service.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user.

    - Creates user in database
    - Publishes user.registered event
    - Returns created user
    """
    auth_service = AuthService(db)
    user = await auth_service.register(user_data)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate user and return JWT tokens.

    Returns:
        - access_token: Short-lived token (15 min) for API access
        - refresh_token: Long-lived token (7 days) for refreshing
        - token_type: "bearer"
    """
    auth_service = AuthService(db)
    user = await auth_service.authenticate(
        credentials.email,
        credentials.password,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(user.id, user.role)
    refresh_token = create_refresh_token(user.id, user.role)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Refresh access token using refresh token.
    """
    try:
        payload = decode_token(request.refresh_token)

        if payload.type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        auth_service = AuthService(db)
        user = await auth_service.get_user_by_id(int(payload.sub))

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )

        access_token = create_access_token(user.id, user.role)
        refresh_token = create_refresh_token(user.id, user.role)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Get current authenticated user profile.

    Note: User info is passed from API Gateway via headers.
    """
    # User ID is set by API Gateway after JWT verification
    user_id = request.headers.get("X-User-ID")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    auth_service = AuthService(db)
    user = await auth_service.get_user_by_id(int(user_id))

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return user
```

---

## 6. Service Specifications

### 6.1 Services Overview (Updated)

| Service                  | Port | Responsibilities                                                |
| ------------------------ | ---- | --------------------------------------------------------------- |
| **API Gateway**          | 8000 | Frontend interface, JWT verification, rate limiting, routing    |
| **User Service**         | 8001 | User CRUD, Authentication (JWT generation), Instructor profiles |
| **Course Service**       | 8002 | Courses, Enrollments, Progress, Certificates (MERGED)           |
| **Notification Service** | 8005 | Email, Push, In-App notifications                               |

### 6.2 Course Service (Merged)

The Course Service now handles:

- Course CRUD operations
- Module & Lesson management
- Enrollment operations
- Progress tracking
- Certificate generation

```python
# services/course-service/src/course_service/api/router.py
from fastapi import APIRouter

from course_service.api import (
    courses,
    modules,
    enrollments,
    progress,
    certificates,
)

router = APIRouter(prefix="/api")

# Course management
router.include_router(courses.router)
router.include_router(modules.router)

# Enrollment & Progress (merged functionality)
router.include_router(enrollments.router)
router.include_router(progress.router)

# Certificates
router.include_router(certificates.router)
```

**Course Service Endpoints:**

| Method | Endpoint                      | Description              |
| ------ | ----------------------------- | ------------------------ |
| GET    | /courses                      | List courses (paginated) |
| POST   | /courses                      | Create new course        |
| GET    | /courses/{id}                 | Get course details       |
| PUT    | /courses/{id}                 | Update course            |
| DELETE | /courses/{id}                 | Archive course           |
| POST   | /courses/{id}/publish         | Publish course           |
| POST   | /courses/{id}/modules         | Add module               |
| PUT    | /courses/{id}/modules/{mid}   | Update module            |
| POST   | /enrollments                  | Enroll in course         |
| GET    | /enrollments/my-courses       | Student's enrollments    |
| GET    | /enrollments/{id}             | Get enrollment details   |
| DELETE | /enrollments/{id}             | Drop course              |
| GET    | /enrollments/{id}/progress    | Get progress (merged)    |
| POST   | /lessons/{id}/complete        | Mark lesson complete     |
| POST   | /quizzes/{id}/submit          | Submit quiz              |
| POST   | /enrollments/{id}/certificate | Generate certificate     |
| GET    | /certificates/{id}            | Get certificate          |
| GET    | /certificates/verify/{code}   | Verify certificate       |

---

## 7. Database Schema (Updated)

### 7.1 Merged ENROLLMENTS Table

**IMPORTANT: Progress and Enrollment tables are MERGED (1:1 relationship)**

```sql
-- The ENROLLMENTS table now includes all progress fields
CREATE TABLE enrollments (
    id SERIAL PRIMARY KEY,

    -- Original enrollment fields
    student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL CHECK (status IN ('active', 'completed', 'dropped', 'suspended')),
    enrolled_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    dropped_at TIMESTAMP,
    last_accessed_at TIMESTAMP,
    payment_status VARCHAR(20) CHECK (payment_status IN ('pending', 'completed', 'refunded')),
    payment_amount DECIMAL(10, 2),
    enrollment_source VARCHAR(100),

    -- Progress fields (merged from progress table)
    completed_modules INTEGER[] DEFAULT '{}',
    completed_lessons INTEGER[] DEFAULT '{}',
    total_modules INTEGER NOT NULL DEFAULT 0,
    total_lessons INTEGER NOT NULL DEFAULT 0,
    completion_percentage DECIMAL(5, 2) DEFAULT 0.00 CHECK (completion_percentage >= 0 AND completion_percentage <= 100),
    completed_quizzes INTEGER[] DEFAULT '{}',
    quiz_scores JSONB DEFAULT '{}',
    time_spent_minutes INTEGER DEFAULT 0,
    current_module_id INTEGER,
    current_lesson_id INTEGER,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Constraints
    UNIQUE (student_id, course_id)
);

-- Indexes
CREATE INDEX idx_enrollments_student ON enrollments(student_id);
CREATE INDEX idx_enrollments_course ON enrollments(course_id);
CREATE INDEX idx_enrollments_status ON enrollments(status);
CREATE INDEX idx_enrollments_enrolled_at ON enrollments(enrolled_at);
CREATE INDEX idx_enrollments_last_accessed ON enrollments(last_accessed_at);
```

### 7.2 Simplified CERTIFICATES Table

**IMPORTANT: Certificates only reference enrollment_id (not student_id or course_id)**

```sql
-- Certificates table with only enrollment reference
CREATE TABLE certificates (
    id SERIAL PRIMARY KEY,

    -- Only enrollment reference (student & course derived from enrollment)
    enrollment_id INTEGER UNIQUE NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,

    -- Certificate data
    certificate_number VARCHAR(100) UNIQUE NOT NULL,
    issue_date DATE NOT NULL,
    certificate_url VARCHAR(500),
    verification_code VARCHAR(50) UNIQUE NOT NULL,
    grade VARCHAR(10),
    score_percentage DECIMAL(5, 2),
    issued_by_id INTEGER REFERENCES users(id),
    is_revoked BOOLEAN DEFAULT FALSE,
    revoked_at TIMESTAMP,
    revoked_reason TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE UNIQUE INDEX idx_certificates_number ON certificates(certificate_number);
CREATE UNIQUE INDEX idx_certificates_verification ON certificates(verification_code);
CREATE INDEX idx_certificates_enrollment ON certificates(enrollment_id);
```

### 7.3 SQLAlchemy Models

```python
# services/course-service/src/course_service/models/enrollment.py
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, ForeignKey, DateTime,
    DECIMAL, ARRAY, Boolean, CheckConstraint, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from course_service.core.database import Base


class Enrollment(Base):
    """
    Merged Enrollment + Progress model.

    Tracks student enrollment in a course and their progress.
    """
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, index=True)

    # Enrollment fields
    student_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), nullable=False, default="active")
    enrolled_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    dropped_at = Column(DateTime, nullable=True)
    last_accessed_at = Column(DateTime, nullable=True)
    payment_status = Column(String(20), nullable=True)
    payment_amount = Column(DECIMAL(10, 2), nullable=True)
    enrollment_source = Column(String(100), nullable=True)

    # Progress fields (merged)
    completed_modules = Column(ARRAY(Integer), default=list)
    completed_lessons = Column(ARRAY(Integer), default=list)
    total_modules = Column(Integer, nullable=False, default=0)
    total_lessons = Column(Integer, nullable=False, default=0)
    completion_percentage = Column(DECIMAL(5, 2), default=0.00)
    completed_quizzes = Column(ARRAY(Integer), default=list)
    quiz_scores = Column(JSONB, default=dict)
    time_spent_minutes = Column(Integer, default=0)
    current_module_id = Column(Integer, nullable=True)
    current_lesson_id = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    certificate = relationship("Certificate", back_populates="enrollment", uselist=False)

    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="uq_enrollment_student_course"),
        CheckConstraint("status IN ('active', 'completed', 'dropped', 'suspended')", name="chk_enrollment_status"),
        CheckConstraint("completion_percentage >= 0 AND completion_percentage <= 100", name="chk_completion_percentage"),
    )


# services/course-service/src/course_service/models/certificate.py
class Certificate(Base):
    """
    Certificate model - only references enrollment.
    Student and course info is derived via enrollment relationship.
    """
    __tablename__ = "certificates"

    id = Column(Integer, primary_key=True, index=True)

    # Only enrollment reference
    enrollment_id = Column(
        Integer,
        ForeignKey("enrollments.id", ondelete="CASCADE"),
        unique=True,
        nullable=False
    )

    # Certificate data
    certificate_number = Column(String(100), unique=True, nullable=False)
    issue_date = Column(DateTime, nullable=False)
    certificate_url = Column(String(500), nullable=True)
    verification_code = Column(String(50), unique=True, nullable=False)
    grade = Column(String(10), nullable=True)
    score_percentage = Column(DECIMAL(5, 2), nullable=True)
    issued_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_revoked = Column(Boolean, default=False)
    revoked_at = Column(DateTime, nullable=True)
    revoked_reason = Column(String, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    enrollment = relationship("Enrollment", back_populates="certificate")

    @property
    def student_id(self) -> int:
        """Get student_id via enrollment."""
        return self.enrollment.student_id

    @property
    def course_id(self) -> int:
        """Get course_id via enrollment."""
        return self.enrollment.course_id
```

---

## 8. Shared Library

### 8.1 Purpose

The `shared/` directory contains reusable code used across multiple microservices:

- Common Pydantic schemas (pagination, responses)
- Utility functions (hashing, datetime helpers)
- Custom exceptions
- Shared middleware
- Base configuration patterns

### 8.2 Structure

```
shared/
├── pyproject.toml
├── shared/
│   ├── __init__.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── pagination.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── datetime.py
│   │   ├── hashing.py
│   │   └── validators.py
│   ├── exceptions/
│   │   ├── __init__.py
│   │   └── base.py
│   └── config/
│       ├── __init__.py
│       └── settings.py
└── tests/
```

### 8.3 Usage in Services

```python
# In any microservice
from shared.schemas.pagination import PaginatedResponse
from shared.utils.datetime import utc_now
from shared.exceptions.base import NotFoundError
```

---

## 9. Implementation Checklist

### Week 1 Tasks

- [ ] **Day 1-2: Project Setup**
  - [ ] Create root directory structure
  - [ ] Set up docker-compose.yml with infrastructure services
  - [ ] Create shared library with base utilities
  - [ ] Initialize PostgreSQL database with schema

- [ ] **Day 3-4: User Service**
  - [ ] Create user-service with Dockerfile & pyproject.toml
  - [ ] Implement User & InstructorProfile models
  - [ ] Implement auth endpoints (register, login, refresh)
  - [ ] Implement HS256 JWT token generation
  - [ ] Add user CRUD endpoints
  - [ ] Write unit tests

- [ ] **Day 5-6: API Gateway**
  - [ ] Create api-gateway with Dockerfile & pyproject.toml
  - [ ] Implement JWT verification middleware (HS256)
  - [ ] Set up request routing to services
  - [ ] Implement rate limiting
  - [ ] Add health checks

- [ ] **Day 7: Integration & Testing**
  - [ ] Test full auth flow (register → login → access protected routes)
  - [ ] Verify Docker compose starts all services correctly
  - [ ] Document any issues or improvements

---

## 10. Key Implementation Rules

### DO:

1. ✅ Use `pyproject.toml` for all dependencies (NO requirements.txt)
2. ✅ Use HS256 algorithm for JWT tokens
3. ✅ Keep file names simple (e.g., `repositories/user.py` NOT `repositories/user_repository.py`)
4. ✅ Create Dockerfile in each microservice root
5. ✅ Use docker-compose.yml at project root
6. ✅ Handle JWT verification ONLY in API Gateway
7. ✅ Keep all auth logic in User Service
8. ✅ Use merged Enrollments table (includes progress fields)
9. ✅ Certificates table only references enrollment_id
10. ✅ Use shared library for common code
11. ✅ Set up venv in each service for non-Docker development

### DON'T:

1. ❌ Don't use requirements.txt
2. ❌ Don't use RS256 for JWT (use HS256)
3. ❌ Don't duplicate folder names in file names
4. ❌ Don't verify JWT in individual microservices
5. ❌ Don't create separate Progress table
6. ❌ Don't add student_id or course_id to Certificates table
7. ❌ Don't create separate Enrollment, Progress, Certificate services

---

_Document Version: 1.0 | Last Updated: February 11, 2026_
