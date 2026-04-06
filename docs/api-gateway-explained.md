# API Gateway

Single front door for all SmartCourse services. Every request hits port `8000` — the gateway handles routing, auth, rate limiting, and CORS so individual services don't have to.

```
Client → [ API Gateway :8000 ] → user-service    :8001
                               → course-service  :8002
                               → notification    :8005
                               → core-service    :8006
                               → analytics       :8007
                               → ai-service      :8009
```

---

## What It Does

| Responsibility | How |
|---|---|
| Route requests | Nginx path matching → `proxy_pass` |
| Verify JWT | `auth_request` subrequest to auth-sidecar |
| Pass user identity | `X-User-ID` / `X-User-Role` headers |
| Rate limiting | 5 req/s on auth, 30 req/s elsewhere (per IP) |
| CORS | `Access-Control-Allow-*` headers in one place |
| Error responses | Uniform JSON shape for 401, 403, 429, 502, 504 |
| Request tracing | `X-Request-ID` on every request |

---

## Auth Flow (Protected Routes)

```
Client → GET /courses/123  (Bearer token)
           │
           ├─ Nginx subrequest → auth-sidecar:8010/verify
           │       ├─ Invalid → 401 returned, request blocked
           │       └─ Valid   → X-User-ID, X-User-Role extracted
           │
           └─ Forward to course-service with X-User-ID header set
```

Services never verify JWTs themselves — they just read the trusted `X-User-ID` header the gateway injected.

---

## Route Map

### Public (no JWT required)

| Endpoint | Service |
|---|---|
| `POST /auth/register` | user-service |
| `POST /auth/login` | user-service |
| `POST /auth/refresh` | user-service |

### Protected (JWT required)

| Endpoint | Service |
|---|---|
| `GET/PATCH /auth/me` | user-service |
| `/auth/*`, `/profile/*`, `/users/*` | user-service |
| `GET /courses`, `/courses/*` | course-service |
| `/course/enrollments`, `/course/certificates`, `/course/progress` | course-service |
| `/notifications/*` | notification-service |
| `/core/*` | core-service |
| `/api/v1/ai/*` | ai-service |
| `/analytics/*` | analytics-service |

---

## API Documentation

Each service exposes Swagger UI and ReDoc through the gateway. No auth required.

| Service | Swagger UI | ReDoc | Purpose |
|---|---|---|---|
| User | `/user-service/docs` | `/user-service/redoc` | Auth, registration, profiles |
| Course | `/course-service/docs` | `/course-service/redoc` | Courses, enrollments, certificates, progress |
| Notification | `/notification-service/docs` | `/notification-service/redoc` | Email and in-app notifications |
| Core | `/core-service/docs` | `/core-service/redoc` | Workflow orchestration (Temporal) |
| AI | `/ai-service/docs` | `/ai-service/redoc` | RAG tutoring, content generation, indexing |
| Analytics | `/analytics-service/docs` | `/analytics-service/redoc` | Materialized metrics and read-optimized analytics |

> OpenAPI spec for each service: replace `/docs` with `/openapi.json`
