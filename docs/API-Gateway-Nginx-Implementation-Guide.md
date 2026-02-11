# SmartCourse — API Gateway (Nginx) Implementation Guide

**Version:** 2.0  
**Date:** February 11, 2026  
**Scope:** Complete implementation guide for the Nginx-based API Gateway microservice  
**Prerequisite:** User Service must be running (port 8001)

---

## Table of Contents

1. [Overview & Goals](#1-overview--goals)
2. [Architecture — Two-Container Pattern](#2-architecture--two-container-pattern)
3. [Directory Structure](#3-directory-structure)
4. [Part A — Auth Sidecar (FastAPI + Python)](#4-part-a--auth-sidecar-fastapi--python)
5. [Part B — Nginx Core Configuration](#5-part-b--nginx-core-configuration)
6. [Route Definitions & Upstream Services](#6-route-definitions--upstream-services)
7. [Public vs Protected Routes](#7-public-vs-protected-routes)
8. [Header Injection to Downstream Services](#8-header-injection-to-downstream-services)
9. [Rate Limiting](#9-rate-limiting)
10. [CORS Configuration](#10-cors-configuration)
11. [Health Check Endpoints](#11-health-check-endpoints)
12. [Dockerfiles](#12-dockerfiles)
13. [Docker Compose Integration](#13-docker-compose-integration)
14. [Environment Variables](#14-environment-variables)
15. [Logging & Observability](#15-logging--observability)
16. [Adding New Services in the Future](#16-adding-new-services-in-the-future)
17. [Error Handling](#17-error-handling)
18. [Security Hardening](#18-security-hardening)
19. [Testing the Gateway](#19-testing-the-gateway)
20. [Troubleshooting](#20-troubleshooting)

---

## 1. Overview & Goals

The API Gateway is the **single entry point** for all client requests (web, mobile, etc.) into the SmartCourse microservices platform. It replaces direct service access and centralises cross-cutting concerns.

### What the gateway must do

| Responsibility | Detail |
|---|---|
| **JWT verification** | Validate HS256 access tokens on every protected route; reject expired/invalid tokens with `401` |
| **Route proxying** | Forward requests to the correct backend service based on URL path |
| **Header injection** | After JWT verification, extract `sub` (user ID) and `role` from the token and add `X-User-ID` and `X-User-Role` headers to downstream requests |
| **Public route passthrough** | Allow certain endpoints (register, login, refresh, health) through **without** JWT verification |
| **Rate limiting** | Throttle requests per IP / per user to protect backend services |
| **CORS** | Handle preflight (`OPTIONS`) and set proper CORS headers |
| **Centralised error responses** | Return consistent JSON error bodies for `401`, `403`, `429`, `502`, `504` |
| **Logging** | Structured access/error logs in JSON for integration with the observability stack |
| **Extensibility** | Make it trivial to add new upstream services (course-service, notification-service, etc.) |

### Why Nginx + Python auth sidecar (not a pure FastAPI gateway or njs)

| Approach | Pros | Cons | Verdict |
|---|---|---|---|
| **Pure FastAPI gateway** | All Python, easy JWT | Not a real reverse proxy; poor at load balancing, rate limiting, connection pooling | Not ideal |
| **Nginx + njs (JavaScript)** | Single container, fast | Requires njs module; JS runtime inside Nginx; your team doesn't work in JS | Unnecessary complexity |
| **Nginx + Lua (OpenResty)** | Powerful | Requires custom OpenResty image; Lua is another language to maintain | Overkill |
| **Nginx + Python auth sidecar** | Nginx handles proxy/routing/rate-limiting (what it's built for); JWT logic stays in Python (your stack); uses the same `python-jose` library as user-service | Two containers instead of one | **Best fit** |

The pattern: Nginx uses its built-in `auth_request` directive to make an internal HTTP call to a tiny FastAPI app (the "auth sidecar") running alongside it. The sidecar does **one thing only** — verify JWTs and return identity headers. Nginx does everything else.

### Port assignment

| Component | Port | Exposed to host? |
|---|---|---|
| **Nginx (reverse proxy)** | **8000** | **Yes** (only port clients access) |
| Auth sidecar (internal) | 8010 | No (Docker internal only) |
| User Service (internal) | 8001 | Dev only (remove in production) |
| Course Service (future, internal) | 8002 | No |
| Notification Service (future, internal) | 8005 | No |
| Analytics Service (future, internal) | 8008 | No |

---

## 2. Architecture — Two-Container Pattern

```
                          ┌─────────────────┐
                          │   Client (Web/   │
                          │   Mobile/API)    │
                          └────────┬────────┘
                                   │
                                   │  :8000 (ONLY exposed port)
                                   ▼
          ┌─────────────────────────────────────────────────┐
          │              NGINX (reverse proxy)               │
          │                                                   │
          │  1. Receive request                               │
          │  2. Check if route is public                      │
          │     → YES: proxy directly to backend              │
          │     → NO:  auth_request → auth-sidecar (:8010)   │
          │            if 200: inject X-User-ID/Role headers  │
          │            if 401: return 401 to client           │
          │  3. Apply rate limiting                           │
          │  4. Proxy to upstream service                     │
          └────────┬───────────────┬───────────────┬─────────┘
                   │               │               │
          ┌────────▼──┐    ┌──────▼──────┐   ┌────▼──────────┐
          │Auth Sidecar│    │User Service │   │ Course Svc    │
          │(FastAPI)   │    │  :8001      │   │  :8002        │
          │  :8010     │    │             │   │  (future)     │
          │            │    └─────────────┘   └───────────────┘
          │ JWT verify │
          │ only       │
          └────────────┘
```

### How the auth_request flow works (step by step)

```
Client                     Nginx                    Auth Sidecar (Python)     User Service
  │                          │                             │                      │
  │ GET /api/auth/me         │                             │                      │
  │ Authorization: Bearer xxx│                             │                      │
  │─────────────────────────►│                             │                      │
  │                          │                             │                      │
  │                          │ 1. Matches protected route  │                      │
  │                          │    "location /api/auth/"    │                      │
  │                          │    has auth_request         │                      │
  │                          │                             │                      │
  │                          │ 2. Subrequest ─────────────►│                      │
  │                          │    GET /verify              │                      │
  │                          │    (forwards Authorization  │                      │
  │                          │     header automatically)   │                      │
  │                          │                             │                      │
  │                          │                  3. Python reads Bearer token      │
  │                          │                     jose.jwt.decode(token, HS256)  │
  │                          │                     Checks exp, type=="access"     │
  │                          │                     Extracts sub, role             │
  │                          │                             │                      │
  │                          │ 4. 200 OK ◄────────────────│                      │
  │                          │    X-Auth-User-ID: 42       │                      │
  │                          │    X-Auth-User-Role: student│                      │
  │                          │                             │                      │
  │                          │ 5. auth_request_set captures headers              │
  │                          │    $auth_user_id = 42                              │
  │                          │    $auth_user_role = student                       │
  │                          │                             │                      │
  │                          │ 6. proxy_set_header X-User-ID 42                  │
  │                          │    proxy_set_header X-User-Role student            │
  │                          │                             │                      │
  │                          │ 7. proxy_pass ─────────────────────────────────────►│
  │                          │                                                     │
  │                          │                                   GET /auth/me      │
  │                          │                                   X-User-ID: 42     │
  │                          │                                                     │
  │ 200 OK ◄─────────────────│◄────────────────────────────────────────────────────│
```

### How downstream services consume identity

Backend services (like the user-service) already expect identity via headers:

```python
# From user-service/src/user_service/api/auth.py (line 131)
user_id = request.headers.get("X-User-ID")
```

The gateway fulfils this contract. No changes needed in existing backend services.

### JWT token structure (generated by user-service)

```json
{
  "sub": "42",            // user ID (string)
  "exp": 1739284800,      // expiration (Unix timestamp)
  "iat": 1739283900,      // issued at
  "type": "access",       // "access" or "refresh"
  "role": "student"       // "student" | "instructor" | "admin"
}
```

- **Algorithm:** HS256 (symmetric, shared secret)
- **Secret key:** `JWT_SECRET_KEY` environment variable (same value as user-service)
- **Library:** `python-jose[cryptography]` (same as user-service)

---

## 3. Directory Structure

```
services/
└── api-gateway/
    ├── nginx/
    │   ├── Dockerfile                    # Nginx container image
    │   ├── nginx.conf                    # Main Nginx configuration
    │   ├── conf.d/
    │   │   ├── upstreams.conf            # Upstream service definitions
    │   │   ├── proxy-params.conf         # Common proxy parameters
    │   │   ├── rate-limiting.conf        # Rate-limit zones
    │   │   ├── cors.conf                 # CORS snippet (included in server block)
    │   │   └── error-pages.conf          # Custom JSON error responses
    │   └── html/
    │       ├── 401.json                  # {"error": "Unauthorized", ...}
    │       ├── 403.json                  # {"error": "Forbidden", ...}
    │       ├── 429.json                  # {"error": "Too Many Requests", ...}
    │       ├── 502.json                  # {"error": "Bad Gateway", ...}
    │       └── 504.json                  # {"error": "Gateway Timeout", ...}
    │
    └── auth-sidecar/
        ├── Dockerfile                    # Python auth container image
        ├── pyproject.toml                # Python dependencies
        └── src/
            └── auth_sidecar/
                ├── __init__.py
                ├── main.py               # FastAPI app (single /verify endpoint)
                └── config.py             # Settings (JWT_SECRET_KEY, etc.)
```

### Why this layout

- **`nginx/`** — pure Nginx config, no scripting languages mixed in. Standard `nginx:alpine` image, nothing exotic.
- **`auth-sidecar/`** — tiny Python FastAPI app. Uses the same `python-jose` library as user-service. Same patterns, same language, same team can maintain it.
- **Separation** — Nginx does what Nginx is best at (proxy, rate-limit, connection pool). Python does what Python is best at (JWT decode with your existing library).

---

## 4. Part A — Auth Sidecar (FastAPI + Python)

This is a minimal FastAPI app with a **single endpoint**: `GET /verify`. Nginx calls it via `auth_request` for every protected route.

### `auth-sidecar/src/auth_sidecar/config.py`

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Auth sidecar settings — loaded from environment variables."""

    JWT_SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
```

### `auth-sidecar/src/auth_sidecar/main.py`

```python
"""
SmartCourse Auth Sidecar — JWT Verification Service

This is a tiny internal FastAPI app called ONLY by Nginx via auth_request.
It is NOT exposed to the internet. It does one thing: verify JWT tokens.

Flow:
  1. Nginx receives a request on a protected route
  2. Nginx sends an internal subrequest to this service at GET /verify
     (the original Authorization header is forwarded automatically)
  3. This service decodes the JWT using python-jose (HS256)
  4. On success: returns 200 with X-Auth-User-ID and X-Auth-User-Role headers
  5. On failure: returns 401 with a JSON error body
  6. Nginx uses auth_request_set to capture the headers and inject them
     as X-User-ID and X-User-Role on the proxied request to the backend
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from jose import JWTError, jwt

from auth_sidecar.config import settings

app = FastAPI(
    title="SmartCourse Auth Sidecar",
    description="Internal JWT verification service for Nginx auth_request",
    version="0.1.0",
    docs_url=None,       # No swagger UI — this is internal only
    redoc_url=None,
)


@app.get("/verify")
async def verify_token(request: Request):
    """
    Verify JWT from the Authorization header.

    Called internally by Nginx auth_request directive.
    Never called directly by clients.

    Returns:
        200 with X-Auth-User-ID and X-Auth-User-Role headers on success.
        401 with JSON error body on failure.
    """
    # 1. Extract the Authorization header
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={
                "error": "Unauthorized",
                "message": "Missing or malformed Authorization header",
            },
        )

    token = auth_header[7:]  # Strip "Bearer "

    # 2. Decode and verify the JWT
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except JWTError:
        return JSONResponse(
            status_code=401,
            content={
                "error": "Unauthorized",
                "message": "Invalid or expired token",
            },
        )

    # 3. Validate required claims
    user_id = payload.get("sub")
    if not user_id:
        return JSONResponse(
            status_code=401,
            content={
                "error": "Unauthorized",
                "message": "Token missing required 'sub' claim",
            },
        )

    # 4. Ensure this is an access token (not a refresh token)
    token_type = payload.get("type", "")
    if token_type != "access":
        return JSONResponse(
            status_code=401,
            content={
                "error": "Unauthorized",
                "message": "Invalid token type. Use an access token, not a refresh token.",
            },
        )

    # 5. Extract role
    role = payload.get("role", "")

    # 6. Return 200 with identity headers for Nginx to capture
    return JSONResponse(
        status_code=200,
        content={"status": "ok"},
        headers={
            "X-Auth-User-ID": str(user_id),
            "X-Auth-User-Role": str(role),
        },
    )


@app.get("/health")
async def health_check():
    """Health check for the auth sidecar."""
    return {"status": "ok", "service": "auth-sidecar"}
```

### `auth-sidecar/src/auth_sidecar/__init__.py`

```python
# Auth Sidecar — JWT verification service for Nginx auth_request
```

### `auth-sidecar/pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "auth-sidecar"
version = "0.1.0"
description = "SmartCourse Auth Sidecar — JWT verification for Nginx"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "python-jose[cryptography]>=3.3.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
]

[tool.setuptools.packages.find]
where = ["src"]
```

### Why this approach is better than njs/Lua

| Aspect | njs (previous version) | Python auth sidecar (this version) |
|---|---|---|
| **Language** | JavaScript (njs subset — not full Node.js) | Python — same as all your services |
| **JWT library** | Hand-rolled HS256 HMAC verification | `python-jose` — same battle-tested library as user-service |
| **Debugging** | Hard — njs has limited tooling | Easy — standard Python, standard FastAPI, standard logging |
| **Team familiarity** | Requires JS knowledge | Your team already writes Python daily |
| **Expiry checking** | Manual `Date.now()` comparison | `python-jose` does it automatically on `jwt.decode()` |
| **Algorithm safety** | Must manually reject non-HS256 | `algorithms=[settings.JWT_ALGORITHM]` handles it |
| **Testing** | Requires njs test harness | Standard `pytest` + `httpx` — same as user-service tests |
| **Dependencies** | Requires `nginx-module-njs` package | Standard `nginx:alpine` image — no extra modules |

---

## 5. Part B — Nginx Core Configuration

### `nginx/nginx.conf`

```nginx
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 2048;
    multi_accept on;
}

http {
    # ─── Basic settings ───────────────────────────────────────────────
    include       /etc/nginx/mime.types;
    default_type  application/json;       # Default to JSON for an API gateway

    # ─── Logging (JSON structured) ────────────────────────────────────
    log_format json_combined escape=json
        '{'
            '"time":"$time_iso8601",'
            '"remote_addr":"$remote_addr",'
            '"request":"$request",'
            '"status":$status,'
            '"body_bytes_sent":$body_bytes_sent,'
            '"request_time":$request_time,'
            '"upstream_response_time":"$upstream_response_time",'
            '"http_user_agent":"$http_user_agent",'
            '"http_x_forwarded_for":"$http_x_forwarded_for",'
            '"request_id":"$request_id",'
            '"upstream_addr":"$upstream_addr"'
        '}';

    access_log /var/log/nginx/access.log json_combined;

    # ─── Performance ──────────────────────────────────────────────────
    sendfile        on;
    tcp_nopush      on;
    tcp_nodelay     on;
    keepalive_timeout 65;
    keepalive_requests 1000;

    # ─── Security headers ─────────────────────────────────────────────
    server_tokens off;                     # Hide Nginx version
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Request-ID $request_id always;

    # ─── Buffer / body size ───────────────────────────────────────────
    client_max_body_size 10m;              # Increase when file uploads are needed
    client_body_buffer_size 128k;
    proxy_buffer_size 16k;
    proxy_buffers 4 32k;
    proxy_busy_buffers_size 64k;

    # ─── Include modular configs ──────────────────────────────────────
    include /etc/nginx/conf.d/upstreams.conf;
    include /etc/nginx/conf.d/rate-limiting.conf;

    # ─── Server block ─────────────────────────────────────────────────
    server {
        listen 8000;
        server_name _;

        # ─── Custom error pages (JSON) ────────────────────────────────
        include /etc/nginx/conf.d/error-pages.conf;

        # ─── CORS (included as snippet) ──────────────────────────────
        include /etc/nginx/conf.d/cors.conf;

        # ==============================================================
        #  HEALTH CHECK (Gateway itself)
        # ==============================================================
        location = /health {
            access_log off;
            return 200 '{"status":"ok","service":"api-gateway"}';
        }

        # ==============================================================
        #  PUBLIC ROUTES — NO JWT VERIFICATION
        # ==============================================================

        # ── Auth: register, login, refresh ────────────────────────────
        location = /api/auth/register {
            limit_req zone=api_auth burst=5 nodelay;

            # Strip any spoofed identity headers
            proxy_set_header X-User-ID "";
            proxy_set_header X-User-Role "";

            proxy_pass http://user-service/auth/register;
            include /etc/nginx/conf.d/proxy-params.conf;
        }

        location = /api/auth/login {
            limit_req zone=api_auth burst=10 nodelay;

            proxy_set_header X-User-ID "";
            proxy_set_header X-User-Role "";

            proxy_pass http://user-service/auth/login;
            include /etc/nginx/conf.d/proxy-params.conf;
        }

        location = /api/auth/refresh {
            limit_req zone=api_refresh burst=3 nodelay;

            proxy_set_header X-User-ID "";
            proxy_set_header X-User-Role "";

            proxy_pass http://user-service/auth/refresh;
            include /etc/nginx/conf.d/proxy-params.conf;
        }

        # ── Service health checks (public) ────────────────────────────
        location = /api/users/health {
            proxy_pass http://user-service/health;
            include /etc/nginx/conf.d/proxy-params.conf;
        }

        # FUTURE: Public course listing
        # location /api/courses/public {
        #     proxy_set_header X-User-ID "";
        #     proxy_set_header X-User-Role "";
        #     proxy_pass http://course-service/courses/public;
        #     include /etc/nginx/conf.d/proxy-params.conf;
        # }

        # ==============================================================
        #  PROTECTED ROUTES — JWT VERIFICATION REQUIRED
        # ==============================================================

        # ── User service (auth/me, profile, etc.) ─────────────────────
        location /api/auth/ {
            limit_req zone=api_general burst=20 nodelay;

            # Call auth sidecar to verify JWT
            auth_request /internal/auth-verify;
            auth_request_set $auth_user_id   $upstream_http_x_auth_user_id;
            auth_request_set $auth_user_role $upstream_http_x_auth_user_role;

            # Inject verified identity headers
            proxy_set_header X-User-ID $auth_user_id;
            proxy_set_header X-User-Role $auth_user_role;

            # Proxy to user service (strip /api prefix)
            proxy_pass http://user-service/auth/;
            include /etc/nginx/conf.d/proxy-params.conf;
        }

        location /api/profile/ {
            limit_req zone=api_general burst=20 nodelay;

            auth_request /internal/auth-verify;
            auth_request_set $auth_user_id   $upstream_http_x_auth_user_id;
            auth_request_set $auth_user_role $upstream_http_x_auth_user_role;

            proxy_set_header X-User-ID $auth_user_id;
            proxy_set_header X-User-Role $auth_user_role;

            proxy_pass http://user-service/profile/;
            include /etc/nginx/conf.d/proxy-params.conf;
        }

        location /api/users/ {
            limit_req zone=api_general burst=20 nodelay;

            auth_request /internal/auth-verify;
            auth_request_set $auth_user_id   $upstream_http_x_auth_user_id;
            auth_request_set $auth_user_role $upstream_http_x_auth_user_role;

            proxy_set_header X-User-ID $auth_user_id;
            proxy_set_header X-User-Role $auth_user_role;

            proxy_pass http://user-service/users/;
            include /etc/nginx/conf.d/proxy-params.conf;
        }

        # ── Course service (FUTURE) ───────────────────────────────────
        # location /api/courses/ {
        #     limit_req zone=api_general burst=20 nodelay;
        #
        #     auth_request /internal/auth-verify;
        #     auth_request_set $auth_user_id   $upstream_http_x_auth_user_id;
        #     auth_request_set $auth_user_role $upstream_http_x_auth_user_role;
        #
        #     proxy_set_header X-User-ID $auth_user_id;
        #     proxy_set_header X-User-Role $auth_user_role;
        #
        #     proxy_pass http://course-service/courses/;
        #     include /etc/nginx/conf.d/proxy-params.conf;
        # }

        # ── Enrollment (FUTURE — part of course-service) ──────────────
        # location /api/enrollments/ {
        #     limit_req zone=api_general burst=20 nodelay;
        #
        #     auth_request /internal/auth-verify;
        #     auth_request_set $auth_user_id   $upstream_http_x_auth_user_id;
        #     auth_request_set $auth_user_role $upstream_http_x_auth_user_role;
        #
        #     proxy_set_header X-User-ID $auth_user_id;
        #     proxy_set_header X-User-Role $auth_user_role;
        #
        #     proxy_pass http://course-service/enrollments/;
        #     include /etc/nginx/conf.d/proxy-params.conf;
        # }

        # ── Notification service (FUTURE) ─────────────────────────────
        # location /api/notifications/ {
        #     limit_req zone=api_general burst=20 nodelay;
        #
        #     auth_request /internal/auth-verify;
        #     auth_request_set $auth_user_id   $upstream_http_x_auth_user_id;
        #     auth_request_set $auth_user_role $upstream_http_x_auth_user_role;
        #
        #     proxy_set_header X-User-ID $auth_user_id;
        #     proxy_set_header X-User-Role $auth_user_role;
        #
        #     proxy_pass http://notification-service/notifications/;
        #     include /etc/nginx/conf.d/proxy-params.conf;
        # }

        # ── Analytics service (FUTURE) ────────────────────────────────
        # location /api/analytics/ {
        #     limit_req zone=api_general burst=20 nodelay;
        #
        #     auth_request /internal/auth-verify;
        #     auth_request_set $auth_user_id   $upstream_http_x_auth_user_id;
        #     auth_request_set $auth_user_role $upstream_http_x_auth_user_role;
        #
        #     proxy_set_header X-User-ID $auth_user_id;
        #     proxy_set_header X-User-Role $auth_user_role;
        #
        #     proxy_pass http://analytics-service/analytics/;
        #     include /etc/nginx/conf.d/proxy-params.conf;
        # }

        # ==============================================================
        #  INTERNAL — Auth verification subrequest
        # ==============================================================
        location = /internal/auth-verify {
            internal;                       # Only callable by auth_request, not by clients

            proxy_pass http://auth-sidecar/verify;
            proxy_pass_request_body off;                # Don't send the request body
            proxy_set_header Content-Length "";          # Clear content-length
            proxy_set_header X-Original-URI $request_uri;
            proxy_set_header X-Original-Method $request_method;

            # Forward the Authorization header to the sidecar
            # (Nginx does this by default, but being explicit)
            proxy_set_header Authorization $http_authorization;
        }

        # Catch-all — return 404
        location / {
            return 404 '{"error":"Not Found","message":"The requested endpoint does not exist"}';
        }
    }
}
```

### `nginx/conf.d/proxy-params.conf`

```nginx
# Common proxy parameters — included by every location block that proxies to a backend service
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Request-ID $request_id;
proxy_set_header Connection "";              # Enable keepalive to upstream

proxy_connect_timeout 5s;
proxy_send_timeout 30s;
proxy_read_timeout 30s;

proxy_next_upstream error timeout http_502 http_503;
proxy_next_upstream_tries 2;
```

### `nginx/conf.d/upstreams.conf`

```nginx
# ─── Upstream service definitions ─────────────────────────────────
# Container names MUST match docker-compose container_name values.
# Docker DNS resolves these names to container IPs.

# Auth sidecar (JWT verification — internal only)
upstream auth-sidecar {
    server smartcourse-auth-sidecar:8010;
    keepalive 16;
}

# User service
upstream user-service {
    server smartcourse-user-service:8001;
    keepalive 32;
}

# ═══════════════════════════════════════════════════════════════════
# FUTURE SERVICES — uncomment when implemented
# ═══════════════════════════════════════════════════════════════════

# upstream course-service {
#     server smartcourse-course-service:8002;
#     keepalive 32;
# }

# upstream notification-service {
#     server smartcourse-notification-service:8005;
#     keepalive 32;
# }

# upstream analytics-service {
#     server smartcourse-analytics-service:8008;
#     keepalive 32;
# }
```

### `nginx/conf.d/rate-limiting.conf`

```nginx
# ─── Rate limit zones ─────────────────────────────────────────────
# $binary_remote_addr uses ~64 bytes per entry (vs ~128 for $remote_addr)

# General API rate limit: 30 requests/second per IP
limit_req_zone $binary_remote_addr zone=api_general:10m rate=30r/s;

# Auth endpoints: stricter to prevent brute force
# 5 requests/second per IP for login/register
limit_req_zone $binary_remote_addr zone=api_auth:10m rate=5r/s;

# Token refresh: 2 requests/second
limit_req_zone $binary_remote_addr zone=api_refresh:5m rate=2r/s;

# Default rate limit response code and log level
limit_req_status 429;
limit_req_log_level warn;
```

### `nginx/conf.d/cors.conf`

```nginx
# ─── CORS Configuration ──────────────────────────────────────────
# Handles preflight (OPTIONS) and adds CORS headers to all responses.
# Replace '*' with your actual frontend domain(s) in production.

# Handle preflight OPTIONS requests
if ($request_method = 'OPTIONS') {
    add_header 'Access-Control-Allow-Origin' '*';
    add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, PATCH, DELETE, OPTIONS';
    add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type, X-Requested-With, Accept, Origin';
    add_header 'Access-Control-Max-Age' 86400;
    add_header 'Content-Length' 0;
    add_header 'Content-Type' 'text/plain';
    return 204;
}

# Add CORS headers to all non-preflight responses
add_header 'Access-Control-Allow-Origin' '*' always;
add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, PATCH, DELETE, OPTIONS' always;
add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type, X-Requested-With, Accept, Origin' always;
add_header 'Access-Control-Expose-Headers' 'X-Request-ID' always;
```

### `nginx/conf.d/error-pages.conf`

```nginx
# ─── Custom JSON error responses ──────────────────────────────────
error_page 401 /401.json;
error_page 403 /403.json;
error_page 429 /429.json;
error_page 502 /502.json;
error_page 504 /504.json;

location = /401.json { internal; root /usr/share/nginx/html; }
location = /403.json { internal; root /usr/share/nginx/html; }
location = /429.json { internal; root /usr/share/nginx/html; }
location = /502.json { internal; root /usr/share/nginx/html; }
location = /504.json { internal; root /usr/share/nginx/html; }
```

---

## 6. Route Definitions & Upstream Services

### URL path mapping (current + planned)

| External URL (clients hit this) | Internal upstream | Target path | Auth required |
|---|---|---|---|
| `POST /api/auth/register` | user-service:8001 | `/auth/register` | No |
| `POST /api/auth/login` | user-service:8001 | `/auth/login` | No |
| `POST /api/auth/refresh` | user-service:8001 | `/auth/refresh` | No |
| `GET  /api/auth/me` | user-service:8001 | `/auth/me` | **Yes** |
| `GET  /api/profile/` | user-service:8001 | `/profile/` | **Yes** |
| `PUT  /api/profile/` | user-service:8001 | `/profile/` | **Yes** |
| `GET  /api/users/health` | user-service:8001 | `/health` | No |
| `GET  /health` | — (gateway itself) | — | No |
| *`/api/courses/*`* | *course-service:8002* | *`/courses/*`* | ***Yes*** |
| *`/api/enrollments/*`* | *course-service:8002* | *`/enrollments/*`* | ***Yes*** |
| *`/api/progress/*`* | *course-service:8002* | *`/progress/*`* | ***Yes*** |
| *`/api/certificates/*`* | *course-service:8002* | *`/certificates/*`* | ***Yes*** |
| *`/api/notifications/*`* | *notification-service:8005* | *`/notifications/*`* | ***Yes*** |
| *`/api/analytics/*`* | *analytics-service:8008* | *`/analytics/*`* | ***Yes*** |

*Italic rows are future services.*

### Path rewriting convention

Clients always use `/api/<service-prefix>/...` — the gateway strips `/api` and forwards the rest:

```
Client:    GET /api/auth/me
Gateway:   proxy_pass http://user-service/auth/me
Service:   receives GET /auth/me
```

---

## 7. Public vs Protected Routes

### Design principle

**By default, ALL routes are protected** (require a valid JWT). Public routes are explicitly whitelisted using `location =` (exact match) blocks that skip `auth_request`.

### Public route registry

```
# CURRENT PUBLIC ROUTES
/health                      → Gateway health check
/api/auth/register           → User registration
/api/auth/login              → User login (returns JWT)
/api/auth/refresh            → Token refresh
/api/users/health            → User service health

# FUTURE PUBLIC ROUTES (add when services exist)
# /api/courses/public         → Public course catalogue (no auth)
# /api/courses/{id}/preview   → Course preview (no auth)
```

### Important: Nginx location matching order

Nginx resolves locations in this priority:
1. **Exact match** `location = /api/auth/login` — highest priority
2. **Prefix match** `location /api/auth/` — lower priority

So `POST /api/auth/login` hits the exact-match (public, no auth), while `GET /api/auth/me` hits the prefix-match (protected, requires auth). This is how we selectively protect routes under the same path prefix.

---

## 8. Header Injection to Downstream Services

### Headers set by the gateway on EVERY proxied request

| Header | Value | Source |
|---|---|---|
| `X-User-ID` | User's database ID (e.g. `42`) | JWT `sub` claim (protected routes only) |
| `X-User-Role` | User's role (`student`/`instructor`/`admin`) | JWT `role` claim (protected routes only) |
| `X-Real-IP` | Client's real IP address | `$remote_addr` |
| `X-Forwarded-For` | Proxy chain | `$proxy_add_x_forwarded_for` |
| `X-Forwarded-Proto` | Protocol (`http`/`https`) | `$scheme` |
| `X-Request-ID` | Unique request ID for tracing | Nginx `$request_id` |
| `Host` | Original host | `$host` |

### Security: stripping spoofed headers

On **public** routes, the gateway explicitly clears identity headers:

```nginx
proxy_set_header X-User-ID "";
proxy_set_header X-User-Role "";
```

On **protected** routes, the values are overwritten with JWT-verified values from the auth sidecar, so spoofing is impossible.

### Downstream service contract

Every backend service can trust these headers unconditionally because:
1. The gateway is the **only** entry point (backend services are not exposed to the internet)
2. `X-User-ID` and `X-User-Role` are either cleared (public) or overwritten (protected)
3. Direct access to services is blocked (Docker network isolation, no port mapping in production)

---

## 9. Rate Limiting

### Rate limit zones (defined in `conf.d/rate-limiting.conf`)

| Zone | Rate | Burst | Applied to |
|---|---|---|---|
| `api_auth` | 5r/s per IP | 10 | `/api/auth/login`, `/api/auth/register` |
| `api_refresh` | 2r/s per IP | 3 | `/api/auth/refresh` |
| `api_general` | 30r/s per IP | 20 | All protected endpoints |

### Parameters explained

| Parameter | Meaning |
|---|---|
| `rate=30r/s` | 30 requests per second steady state |
| `burst=20` | Allow up to 20 extra requests in a burst |
| `nodelay` | Don't queue burst requests — process immediately or reject with 429 |
| `zone=api_general:10m` | 10MB shared memory ≈ 160,000 IP addresses tracked |

---

## 10. CORS Configuration

See `nginx/conf.d/cors.conf` above. Key points:

- Handles `OPTIONS` preflight requests with `204 No Content`
- Caches preflight for 24 hours (`Access-Control-Max-Age: 86400`)
- Allows `Authorization` header (needed for JWT Bearer tokens)
- Exposes `X-Request-ID` header to clients (for debugging)
- **Production:** Replace `'*'` with your actual frontend domain(s)

---

## 11. Health Check Endpoints

| Endpoint | Returns | Purpose |
|---|---|---|
| `GET /health` | `{"status":"ok","service":"api-gateway"}` | Gateway itself (Nginx) |
| `GET /api/users/health` | Proxied from user-service `/health` | User service health |
| (internal) auth-sidecar `/health` | `{"status":"ok","service":"auth-sidecar"}` | Used by Docker healthcheck |

---

## 12. Dockerfiles

### `nginx/Dockerfile`

```dockerfile
FROM nginx:1.25-alpine

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy configuration files
COPY nginx.conf /etc/nginx/nginx.conf
COPY conf.d/ /etc/nginx/conf.d/
COPY html/ /usr/share/nginx/html/

EXPOSE 8000

CMD ["nginx", "-g", "daemon off;"]
```

Note: This is the **standard `nginx:alpine` image** — no extra modules, no njs, no Lua, no custom builds.

### `auth-sidecar/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy dependency definition
COPY pyproject.toml .

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    fastapi>=0.109.0 \
    uvicorn[standard]>=0.27.0 \
    python-jose[cryptography]>=3.3.0 \
    pydantic>=2.5.0 \
    pydantic-settings>=2.1.0

# Copy source code
COPY src/ ./src/

# Install the package
RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/src:/app
EXPOSE 8010

CMD ["uvicorn", "auth_sidecar.main:app", "--host", "0.0.0.0", "--port", "8010"]
```

---

## 13. Docker Compose Integration

### Updated root `docker-compose.yml`

```yaml
version: "3.9"

services:
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
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U smartcourse"]
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
        ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD:-smartcourse_secret}", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - smartcourse-network

  user-service:
    build:
      context: ./services/user-service
      dockerfile: Dockerfile
    container_name: smartcourse-user-service
    # NOTE: Remove "ports" mapping in production — only gateway should be exposed
    ports:
      - "8001:8001"
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER:-smartcourse}:${POSTGRES_PASSWORD:-smartcourse_secret}@postgres:5432/${POSTGRES_DB:-smartcourse}
      - REDIS_URL=redis://:${REDIS_PASSWORD:-smartcourse_secret}@redis:6379/0
      - JWT_SECRET_KEY=${JWT_SECRET_KEY:-your-secret-key-change-in-production}
      - JWT_ALGORITHM=HS256
      - JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
      - JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    networks:
      - smartcourse-network

  # ═══════════════════════════════════════════════════════════════
  #  AUTH SIDECAR — JWT verification (Python/FastAPI)
  # ═══════════════════════════════════════════════════════════════
  auth-sidecar:
    build:
      context: ./services/api-gateway/auth-sidecar
      dockerfile: Dockerfile
    container_name: smartcourse-auth-sidecar
    # No ports exposed to host — only accessible within Docker network
    environment:
      - JWT_SECRET_KEY=${JWT_SECRET_KEY:-your-secret-key-change-in-production}
      - JWT_ALGORITHM=HS256
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8010/health')"]
      interval: 10s
      timeout: 5s
      retries: 3
    networks:
      - smartcourse-network

  # ═══════════════════════════════════════════════════════════════
  #  API GATEWAY — Nginx reverse proxy
  # ═══════════════════════════════════════════════════════════════
  api-gateway:
    build:
      context: ./services/api-gateway/nginx
      dockerfile: Dockerfile
    container_name: smartcourse-api-gateway
    ports:
      - "8000:8000"           # The ONLY port clients should access
    depends_on:
      - auth-sidecar
      - user-service
      # FUTURE: Add other services here as they come online
      # - course-service
      # - notification-service
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:8000/health"]
      interval: 15s
      timeout: 5s
      retries: 3
    networks:
      - smartcourse-network

networks:
  smartcourse-network:
    driver: bridge

volumes:
  postgres_data:
  redis_data:
```

### Key points

- **Auth sidecar** shares `JWT_SECRET_KEY` and `JWT_ALGORITHM` with the user-service (HS256 symmetric key)
- Auth sidecar has **no port mapping** — only accessible within the Docker network
- Nginx depends on both `auth-sidecar` and `user-service`
- In production, **remove** the `ports` mapping from `user-service` so only the gateway is accessible

---

## 14. Environment Variables

### Variables needed

| Variable | Used by | Required | Default | Description |
|---|---|---|---|---|
| `JWT_SECRET_KEY` | auth-sidecar, user-service | **Yes** | — | HS256 signing key (must be identical) |
| `JWT_ALGORITHM` | auth-sidecar, user-service | No | `HS256` | JWT algorithm |

### Root `.env` file (already exists — no changes needed)

The existing `.env` already contains `JWT_SECRET_KEY`. Both the auth sidecar and user-service read it via `${JWT_SECRET_KEY}`.

---

## 15. Logging & Observability

### Nginx — Structured JSON access logs

```json
{
  "time": "2026-02-11T10:30:45+00:00",
  "remote_addr": "172.18.0.1",
  "request": "GET /api/profile/ HTTP/1.1",
  "status": 200,
  "body_bytes_sent": 342,
  "request_time": 0.015,
  "upstream_response_time": "0.012",
  "http_user_agent": "Mozilla/5.0 ...",
  "http_x_forwarded_for": "",
  "request_id": "a1b2c3d4e5f6",
  "upstream_addr": "172.18.0.4:8001"
}
```

### Auth sidecar — standard Uvicorn logs

The auth sidecar uses standard Uvicorn logging. For structured JSON logging, add `--log-config` or use `structlog` (same as user-service).

### Viewing logs

```bash
# Nginx gateway logs
docker logs -f smartcourse-api-gateway

# Auth sidecar logs
docker logs -f smartcourse-auth-sidecar

# All gateway-related logs together
docker compose logs -f api-gateway auth-sidecar
```

### `X-Request-ID` for distributed tracing

Every request gets a unique `X-Request-ID` from Nginx. This header is:
- Forwarded to all backend services via `proxy-params.conf`
- Returned to the client via `add_header X-Request-ID $request_id always`
- Logged in every Nginx access log entry

Backend services can log this header to correlate requests across services.

---

## 16. Adding New Services in the Future

Follow this checklist every time a new microservice is added.

### Step-by-step: Adding a new service (e.g. `course-service`)

#### 1. Define the upstream in `nginx/conf.d/upstreams.conf`

```nginx
upstream course-service {
    server smartcourse-course-service:8002;
    keepalive 32;
}
```

#### 2. Add location blocks in `nginx/nginx.conf`

For **public** endpoints (no auth):

```nginx
location /api/courses/public/ {
    proxy_set_header X-User-ID "";
    proxy_set_header X-User-Role "";
    limit_req zone=api_general burst=20 nodelay;

    proxy_pass http://course-service/courses/public/;
    include /etc/nginx/conf.d/proxy-params.conf;
}
```

For **protected** endpoints (with auth):

```nginx
location /api/courses/ {
    limit_req zone=api_general burst=20 nodelay;

    auth_request /internal/auth-verify;
    auth_request_set $auth_user_id   $upstream_http_x_auth_user_id;
    auth_request_set $auth_user_role $upstream_http_x_auth_user_role;

    proxy_set_header X-User-ID $auth_user_id;
    proxy_set_header X-User-Role $auth_user_role;

    proxy_pass http://course-service/courses/;
    include /etc/nginx/conf.d/proxy-params.conf;
}
```

#### 3. Add health check endpoint

```nginx
location = /api/courses/health {
    proxy_pass http://course-service/health;
    include /etc/nginx/conf.d/proxy-params.conf;
}
```

#### 4. Add to `docker-compose.yml`

```yaml
course-service:
  build:
    context: ./services/course-service
    dockerfile: Dockerfile
  container_name: smartcourse-course-service
  environment:
    - DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
    - REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
  networks:
    - smartcourse-network
```

And update the gateway's `depends_on`:

```yaml
api-gateway:
  depends_on:
    - auth-sidecar
    - user-service
    - course-service       # ← Add this
```

#### 5. Rebuild and restart

```bash
docker compose up --build api-gateway course-service
```

### Checklist template

```
□ Created services/<name>/ with Dockerfile
□ Added upstream block in nginx/conf.d/upstreams.conf
□ Added public location blocks (if any) in nginx/nginx.conf
□ Added protected location blocks in nginx/nginx.conf
□ Added health check location in nginx/nginx.conf
□ Added service to docker-compose.yml
□ Added service to api-gateway depends_on in docker-compose.yml
□ Ensured the new service reads X-User-ID and X-User-Role headers
□ Tested: public endpoints work without token
□ Tested: protected endpoints require valid JWT
□ Tested: X-User-ID header arrives correctly at the new service
```

### What does NOT change when adding a new service

- The auth sidecar — it only verifies JWTs, doesn't care about routing
- The Nginx Dockerfile — just config files change
- The `.env` file — unless the new service needs new variables
- The auth flow — `auth_request` pattern is the same for every protected route

---

## 17. Error Handling

### Custom JSON error pages

Create these static files under `services/api-gateway/nginx/html/`:

**`401.json`**
```json
{"error": "Unauthorized", "message": "Authentication required. Provide a valid JWT token in the Authorization header.", "status": 401}
```

**`403.json`**
```json
{"error": "Forbidden", "message": "You do not have permission to access this resource.", "status": 403}
```

**`429.json`**
```json
{"error": "Too Many Requests", "message": "Rate limit exceeded. Please try again later.", "status": 429}
```

**`502.json`**
```json
{"error": "Bad Gateway", "message": "The upstream service is unavailable. Please try again later.", "status": 502}
```

**`504.json`**
```json
{"error": "Gateway Timeout", "message": "The upstream service did not respond in time.", "status": 504}
```

---

## 18. Security Hardening

### Measures already included

| Measure | How |
|---|---|
| **No server version leak** | `server_tokens off` |
| **XSS protection** | `X-Content-Type-Options: nosniff` |
| **Clickjacking protection** | `X-Frame-Options: DENY` |
| **Header spoofing prevention** | `X-User-ID` and `X-User-Role` cleared/overwritten on every request |
| **JWT expiry enforcement** | `python-jose` checks `exp` claim automatically during `jwt.decode()` |
| **Token type enforcement** | Auth sidecar rejects refresh tokens used as access tokens |
| **Rate limiting** | Per-IP limits on auth and general endpoints |
| **Request size limit** | `client_max_body_size 10m` prevents oversized payloads |
| **Auth sidecar not exposed** | No port mapping; only Nginx can reach it via Docker network |

### Additional hardening for production

```nginx
# 1. Restrict HTTP methods (add to server block)
if ($request_method !~ ^(GET|POST|PUT|PATCH|DELETE|OPTIONS)$) {
    return 405;
}

# 2. Block common exploit paths
location ~* \.(php|asp|aspx|jsp|cgi)$ {
    return 403;
}

# 3. Deny access to hidden files
location ~ /\. {
    deny all;
    return 404;
}
```

### Network isolation (Docker)

In production, **remove port mappings** from all services except the gateway:

```yaml
# docker-compose.prod.yml (override)
services:
  user-service:
    ports: []           # No external access
  auth-sidecar:
    ports: []           # Already not exposed, but be explicit
  api-gateway:
    ports:
      - "8000:8000"     # Only exposed port
```

---

## 19. Testing the Gateway

### Manual testing with cURL

```bash
# 1. Health check (should return 200)
curl http://localhost:8000/health

# 2. Register a user (public — no token needed)
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"StrongPass123!","first_name":"Test","last_name":"User"}'

# 3. Login (public — returns JWT tokens)
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"StrongPass123!"}'
# → Save the access_token from the response

# 4. Access protected endpoint WITHOUT token (should return 401)
curl http://localhost:8000/api/auth/me
# → {"error": "Unauthorized", "message": "Missing or malformed Authorization header"}

# 5. Access protected endpoint WITH valid token (should return 200)
curl http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer <access_token_from_step_3>"
# → {"id": 1, "email": "test@example.com", ...}

# 6. Access protected endpoint with EXPIRED token (should return 401)
# → {"error": "Unauthorized", "message": "Invalid or expired token"}

# 7. Try using a REFRESH token as access token (should return 401)
curl http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer <refresh_token_from_step_3>"
# → {"error": "Unauthorized", "message": "Invalid token type..."}

# 8. Test header spoofing prevention (spoofed header should be ignored)
curl http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer <valid_token>" \
  -H "X-User-ID: 9999"
# → Should return YOUR user, not user 9999

# 9. Test rate limiting (rapid-fire requests)
for i in $(seq 1 20); do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST http://localhost:8000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"test@example.com","password":"wrong"}'
done
# → Should see 429 responses after the burst limit is hit

# 10. Test non-existent endpoint (should return 404)
curl http://localhost:8000/api/nonexistent
# → {"error":"Not Found","message":"The requested endpoint does not exist"}
```

### Build and run

```bash
# Build everything
docker compose build

# Start all services
docker compose up -d

# Check all containers are healthy
docker compose ps

# Check gateway logs
docker logs -f smartcourse-api-gateway

# Check auth sidecar logs
docker logs -f smartcourse-auth-sidecar
```

---

## 20. Troubleshooting

### Common issues

| Symptom | Cause | Fix |
|---|---|---|
| `502 Bad Gateway` | Upstream service or auth sidecar is down | Check: `docker compose ps` — are all containers running? |
| `502` on startup | Gateway started before upstream was ready | `depends_on` should handle this; increase `proxy_connect_timeout` if needed |
| `401` on public routes | Route not matched as public (path mismatch) | Ensure exact `location =` match; check trailing slashes |
| JWT always rejected | Secret key mismatch between auth-sidecar and user-service | Verify both read the same `JWT_SECRET_KEY` from `.env` |
| JWT always rejected | Auth sidecar not reachable | Check: `docker logs smartcourse-auth-sidecar` |
| `413 Request Entity Too Large` | Body exceeds `client_max_body_size` | Increase the value in `nginx.conf` |
| CORS errors in browser | Preflight not handled or wrong origin | Check `cors.conf`; ensure `OPTIONS` returns `204` |
| Auth sidecar slow | Cold start or too few workers | Add `--workers 2` to uvicorn CMD in Dockerfile |

### Useful debug commands

```bash
# Test nginx config syntax (inside container)
docker exec smartcourse-api-gateway nginx -t

# Reload nginx config without restart
docker exec smartcourse-api-gateway nginx -s reload

# View real-time nginx access logs
docker exec smartcourse-api-gateway tail -f /var/log/nginx/access.log

# View nginx error logs
docker exec smartcourse-api-gateway tail -f /var/log/nginx/error.log

# Test DNS resolution inside nginx container
docker exec smartcourse-api-gateway nslookup smartcourse-auth-sidecar

# Test auth sidecar directly from nginx container
docker exec smartcourse-api-gateway wget -qO- http://smartcourse-auth-sidecar:8010/health

# Check auth sidecar logs
docker logs --tail 50 smartcourse-auth-sidecar
```

---

## Summary: Files to Create

| # | File Path | Purpose |
|---|---|---|
| 1 | `services/api-gateway/nginx/Dockerfile` | Nginx container (standard `nginx:alpine` — no extra modules) |
| 2 | `services/api-gateway/nginx/nginx.conf` | Main Nginx configuration |
| 3 | `services/api-gateway/nginx/conf.d/upstreams.conf` | Upstream service definitions |
| 4 | `services/api-gateway/nginx/conf.d/proxy-params.conf` | Common proxy parameters |
| 5 | `services/api-gateway/nginx/conf.d/rate-limiting.conf` | Rate limit zone definitions |
| 6 | `services/api-gateway/nginx/conf.d/cors.conf` | CORS headers and preflight handling |
| 7 | `services/api-gateway/nginx/conf.d/error-pages.conf` | Custom JSON error page mappings |
| 8 | `services/api-gateway/nginx/html/401.json` | Unauthorized error response |
| 9 | `services/api-gateway/nginx/html/403.json` | Forbidden error response |
| 10 | `services/api-gateway/nginx/html/429.json` | Rate limited error response |
| 11 | `services/api-gateway/nginx/html/502.json` | Bad gateway error response |
| 12 | `services/api-gateway/nginx/html/504.json` | Gateway timeout error response |
| 13 | `services/api-gateway/auth-sidecar/Dockerfile` | Python auth sidecar container |
| 14 | `services/api-gateway/auth-sidecar/pyproject.toml` | Python dependencies |
| 15 | `services/api-gateway/auth-sidecar/src/auth_sidecar/__init__.py` | Package init |
| 16 | `services/api-gateway/auth-sidecar/src/auth_sidecar/config.py` | Settings (JWT_SECRET_KEY) |
| 17 | `services/api-gateway/auth-sidecar/src/auth_sidecar/main.py` | FastAPI app (single `/verify` endpoint) |
| 18 | `docker-compose.yml` | **Update** — add `auth-sidecar` and `api-gateway` service blocks |

---

## Appendix: Quick Reference Card

```
┌──────────────────────────────────────────────────────────────────┐
│                 SmartCourse API Gateway                           │
│                                                                   │
│  Architecture:  Nginx (proxy) + Python auth sidecar (JWT)        │
│  Port:          8000 (Nginx) — only exposed port                 │
│  Auth sidecar:  8010 (internal only, not exposed)                │
│  JWT:           HS256 via python-jose (shared secret)            │
│                                                                   │
│  PUBLIC (no auth):                                               │
│    POST /api/auth/register                                       │
│    POST /api/auth/login                                          │
│    POST /api/auth/refresh                                        │
│    GET  /api/users/health                                        │
│    GET  /health                                                  │
│                                                                   │
│  PROTECTED (JWT required via auth sidecar):                      │
│    /api/auth/*    → user-service:8001/auth/*                     │
│    /api/profile/* → user-service:8001/profile/*                  │
│    /api/users/*   → user-service:8001/users/*                    │
│    /api/courses/* → course-service:8002/courses/*     (FUTURE)   │
│    /api/enrollments/* → course-service:8002            (FUTURE)  │
│    /api/notifications/* → notification-service:8005    (FUTURE)  │
│    /api/analytics/*     → analytics-service:8008       (FUTURE)  │
│                                                                   │
│  Headers injected on protected routes:                           │
│    X-User-ID   (from JWT sub claim)                              │
│    X-User-Role (from JWT role claim)                             │
│    X-Request-ID (Nginx generated — on all routes)                │
│                                                                   │
│  Adding a new service:                                           │
│    1. Add upstream in nginx/conf.d/upstreams.conf                │
│    2. Add location block(s) in nginx/nginx.conf                  │
│    3. Add service to docker-compose.yml                          │
│    4. Rebuild: docker compose up --build api-gateway             │
│    (Auth sidecar stays unchanged)                                │
└──────────────────────────────────────────────────────────────────┘
```
