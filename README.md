# SmartCourse - Online Learning Platform

A microservices-based online learning platform built with FastAPI, PostgreSQL, Redis, and Docker.

## Quick Start

### Prerequisites

- Docker Desktop running on your Mac
- Docker Compose

### Running the Services

1. **Start all services:**

   ```bash
   docker compose up --build
   ```

2. **Stop services:**

   ```bash
   docker compose down
   ```

3. **Stop and remove volumes:**
   ```bash
   docker compose down -v
   ```

## Services

| Service      | Port | Status     |
| ------------ | ---- | ---------- |
| User Service | 8001 | ✅ Running |
| PostgreSQL   | 5432 | ✅ Running |
| Redis        | 6379 | ✅ Running |

## API Endpoints (User Service)

### Authentication Endpoints

#### 1. Register

```bash
curl -X POST http://localhost:8001/auth/register
```

**Response:**

```json
{ "message": "User registered (mock)" }
```

#### 2. Login

```bash
curl -X POST http://localhost:8001/auth/login
```

**Response:**

```json
{
  "access_token": "mock_token",
  "refresh_token": "mock_refresh",
  "token_type": "bearer"
}
```

#### 3. Refresh Token

```bash
curl -X POST http://localhost:8001/auth/refresh
```

**Response:**

```json
{
  "access_token": "mock_token",
  "refresh_token": "mock_refresh",
  "token_type": "bearer"
}
```

#### 4. Get Current User

```bash
curl http://localhost:8001/auth/me
```

**Response:**

```json
{
  "id": 1,
  "email": "mock@example.com",
  "role": "student"
}
```

## Project Structure

```
smart-course/
├── docker-compose.yml          # Docker services configuration
├── .env                        # Environment variables
├── docs/                       # Documentation
├── infrastructure/             # Database initialization scripts
│   └── postgres/
│       └── init.sql
├── services/
│   └── user-service/          # User & Authentication Service
│       ├── Dockerfile
│       ├── pyproject.toml
│       └── src/
│           └── user_service/
│               ├── main.py
│               └── api/
│                   ├── router.py
│                   └── auth.py
└── shared/                     # Shared utilities (to be implemented)
```

## Development

### Viewing Logs

```bash
docker compose logs -f user-service
```

### Accessing Services

- User Service API: http://localhost:8001
- User Service Docs: http://localhost:8001/docs
- PostgreSQL: localhost:5432
- Redis: localhost:6379

## Next Steps

- [ ] Implement actual authentication with JWT
- [ ] Add database models and repositories
- [ ] Implement API Gateway
- [ ] Add Course Service
- [ ] Add Notification Service

## Architecture

Following the SmartCourse Week 1 Implementation Guide:

- Microservices architecture
- Docker containerization
- FastAPI framework
- PostgreSQL for relational data
- Redis for caching
- HS256 JWT authentication (to be implemented)
