# API Gateway — Lean Implementation Guide

## Problem

The current api-gateway service has **17 files** across nested folders:

```
services/api-gateway/
├── nginx/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── conf.d/
│   │   ├── cors.conf
│   │   ├── error-pages.conf
│   │   ├── protected-snippet.conf
│   │   ├── proxy-params.conf
│   │   ├── rate-limiting.conf
│   │   └── upstreams.conf
│   └── html/
│       ├── 401.json
│       ├── 403.json
│       ├── 429.json
│       ├── 502.json
│       └── 504.json
└── auth-sidecar/
    ├── .env
    ├── Dockerfile
    ├── pyproject.toml
    └── src/
        └── auth_sidecar/
            ├── __init__.py
            ├── config.py
            └── main.py
```

Mentor feedback: **too large, too many files**. This guide consolidates everything while keeping the same functionality.

---

## Target Structure (After Lean Refactor)

```
services/api-gateway/
├── nginx.conf          # Single consolidated nginx config (was 7 files)
├── Dockerfile.nginx    # Nginx Dockerfile (simplified)
├── auth-sidecar.py     # Single-file auth sidecar (was 5 files)
├── Dockerfile.sidecar  # Sidecar Dockerfile (simplified)
└── .env                # Shared env for sidecar
```

**17 files → 5 files**. Same exact functionality. Two containers (nginx + auth-sidecar) remain because they serve different roles.

---

## Step-by-Step Implementation

### Step 1: Create the consolidated `nginx.conf`

Merge `nginx.conf` + all `conf.d/*.conf` + inline the JSON error bodies. No more `include` directives, no `html/` folder.

Create `services/api-gateway/nginx.conf`:

```nginx
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 2048;
    multi_accept on;
}

http {
    include       /etc/nginx/mime.types;
    default_type  application/json;
    resolver 127.0.0.11 valid=10s ipv6=off;

    # --- Logging (JSON structured) ---
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
            '"request_id":"$request_id",'
            '"upstream_addr":"$upstream_addr"'
        '}';
    access_log /var/log/nginx/access.log json_combined;

    # --- Performance ---
    sendfile        on;
    tcp_nopush      on;
    tcp_nodelay     on;
    keepalive_timeout 65;
    keepalive_requests 1000;

    # --- Security ---
    server_tokens off;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Request-ID $request_id always;

    # --- Buffers ---
    client_max_body_size 10m;
    client_body_buffer_size 128k;
    proxy_buffer_size 16k;
    proxy_buffers 4 32k;
    proxy_busy_buffers_size 64k;

    # --- Rate Limiting (was rate-limiting.conf) ---
    limit_req_zone $binary_remote_addr zone=api_general:10m rate=30r/s;
    limit_req_zone $binary_remote_addr zone=api_auth:10m   rate=5r/s;
    limit_req_zone $binary_remote_addr zone=api_refresh:5m rate=2r/s;
    limit_req_status 429;
    limit_req_log_level warn;

    # --- Upstreams (was upstreams.conf) ---
    upstream auth-sidecar       { server smartcourse-auth-sidecar:8010;         keepalive 16; }
    upstream user-service        { server smartcourse-user-service:8001;         keepalive 32; }
    upstream course-service      { server smartcourse-course-service:8002;       keepalive 32; }
    upstream notification-service { server smartcourse-notification-service:8005; keepalive 32; }

    server {
        listen 8000;
        server_name _;

        # --- Service variables (for dynamic DNS resolution) ---
        set $auth_sidecar         http://smartcourse-auth-sidecar:8010;
        set $user_service         http://smartcourse-user-service:8001;
        set $course_service       http://smartcourse-course-service:8002;
        set $notification_service http://smartcourse-notification-service:8005;
        set $core_service         http://smartcourse-core-service:8006;
        set $ai_service           http://smartcourse-ai-service:8009;

        # --- CORS (was cors.conf) ---
        add_header 'Access-Control-Allow-Origin' '*' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, PATCH, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type, X-Requested-With, Accept, Origin' always;
        add_header 'Access-Control-Expose-Headers' 'X-Request-ID' always;

        # --- Inline error pages (was error-pages.conf + html/*.json) ---
        error_page 401 @err401;
        error_page 403 @err403;
        error_page 429 @err429;
        error_page 502 @err502;
        error_page 504 @err504;
        location @err401 { internal; return 401 '{"error":"Unauthorized","message":"Authentication required.","status":401}'; }
        location @err403 { internal; return 403 '{"error":"Forbidden","message":"You do not have permission.","status":403}'; }
        location @err429 { internal; return 429 '{"error":"Too Many Requests","message":"Rate limit exceeded.","status":429}'; }
        location @err502 { internal; return 502 '{"error":"Bad Gateway","message":"Upstream service unavailable.","status":502}'; }
        location @err504 { internal; return 504 '{"error":"Gateway Timeout","message":"Upstream did not respond in time.","status":504}'; }

        # --- Handle OPTIONS preflight ---
        if ($request_method = 'OPTIONS') {
            return 204;
        }

        # === HEALTH CHECK ===
        location = /health {
            access_log off;
            return 200 '{"status":"ok","service":"api-gateway"}';
        }

        # === PUBLIC (no auth) ===
        location ~ ^/auth/(register|login|refresh)$ {
            limit_req zone=api_auth burst=10 nodelay;
            proxy_set_header X-User-ID "";
            proxy_set_header X-User-Role "";
            proxy_pass $user_service$request_uri;
            include /etc/nginx/proxy-params.conf;
        }

        # === PROTECTED ROUTES (JWT required) ===

        # User service
        location = /auth/me {
            limit_req zone=api_general burst=20 nodelay;
            include /etc/nginx/protected.conf;
            proxy_pass $user_service$request_uri;
            include /etc/nginx/proxy-params.conf;
        }
        location /auth/ {
            limit_req zone=api_general burst=20 nodelay;
            include /etc/nginx/protected.conf;
            proxy_pass $user_service$request_uri;
            include /etc/nginx/proxy-params.conf;
        }
        location /profile/ {
            limit_req zone=api_general burst=20 nodelay;
            include /etc/nginx/protected.conf;
            proxy_pass $user_service$request_uri;
            include /etc/nginx/proxy-params.conf;
        }
        location /users/ {
            limit_req zone=api_general burst=20 nodelay;
            include /etc/nginx/protected.conf;
            proxy_pass $user_service$request_uri;
            include /etc/nginx/proxy-params.conf;
        }

        # Course service
        location = /courses {
            limit_req zone=api_general burst=20 nodelay;
            include /etc/nginx/protected.conf;
            proxy_pass $course_service/courses/$is_args$args;
            include /etc/nginx/proxy-params.conf;
        }
        location /courses/ {
            limit_req zone=api_general burst=20 nodelay;
            include /etc/nginx/protected.conf;
            proxy_pass $course_service$request_uri;
            include /etc/nginx/proxy-params.conf;
        }
        location /course/enrollments {
            limit_req zone=api_general burst=20 nodelay;
            include /etc/nginx/protected.conf;
            proxy_pass $course_service$request_uri;
            include /etc/nginx/proxy-params.conf;
        }
        location /course/certificates {
            limit_req zone=api_general burst=20 nodelay;
            include /etc/nginx/protected.conf;
            proxy_pass $course_service$request_uri;
            include /etc/nginx/proxy-params.conf;
        }
        location /course/progress {
            limit_req zone=api_general burst=20 nodelay;
            include /etc/nginx/protected.conf;
            proxy_pass $course_service$request_uri;
            include /etc/nginx/proxy-params.conf;
        }

        # Notification service
        location /notifications/ {
            limit_req zone=api_general burst=20 nodelay;
            include /etc/nginx/protected.conf;
            proxy_pass $notification_service$request_uri;
            include /etc/nginx/proxy-params.conf;
        }

        # Core service
        location = /core/health {
            limit_req zone=api_general burst=20 nodelay;
            include /etc/nginx/protected.conf;
            proxy_pass $core_service$request_uri;
            include /etc/nginx/proxy-params.conf;
        }
        location /core/ {
            limit_req zone=api_general burst=20 nodelay;
            include /etc/nginx/protected.conf;
            proxy_pass $core_service$request_uri;
            include /etc/nginx/proxy-params.conf;
        }

        # AI service
        location /api/v1/ai/ {
            limit_req zone=api_general burst=20 nodelay;
            include /etc/nginx/protected.conf;
            proxy_pass $ai_service$request_uri;
            include /etc/nginx/proxy-params.conf;
        }

        # === INTERNAL auth subrequest ===
        location = /internal/auth-verify {
            internal;
            proxy_pass $auth_sidecar/verify;
            proxy_pass_request_body off;
            proxy_set_header Content-Length "";
            proxy_set_header X-Original-URI $request_uri;
            proxy_set_header X-Original-Method $request_method;
            proxy_set_header Authorization $http_authorization;
        }

        # Catch-all
        location / {
            return 404 '{"error":"Not Found","message":"The requested endpoint does not exist"}';
        }
    }
}
```

> **Why `proxy-params.conf` and `protected.conf` still use `include`**: Nginx does not support inline macros. These two tiny snippets are reused in every location block — without `include`, you'd copy 12+ lines into each of 15 locations. Two snippet files is acceptable and standard practice.

### Step 2: Create `protected.conf` snippet (6 lines)

Create `services/api-gateway/protected.conf`:

```nginx
auth_request /internal/auth-verify;
auth_request_set $auth_user_id   $upstream_http_x_auth_user_id;
auth_request_set $auth_user_role $upstream_http_x_auth_user_role;
proxy_set_header X-User-ID   $auth_user_id;
proxy_set_header X-User-Role $auth_user_role;
```

### Step 3: Create `proxy-params.conf` snippet (9 lines)

Create `services/api-gateway/proxy-params.conf`:

```nginx
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Request-ID $request_id;
proxy_set_header Connection "";
proxy_connect_timeout 5s;
proxy_send_timeout 30s;
proxy_read_timeout 30s;
proxy_next_upstream error timeout http_502 http_503;
proxy_next_upstream_tries 2;
```

### Step 4: Create `Dockerfile.nginx` (simplified)

Create `services/api-gateway/Dockerfile.nginx`:

```dockerfile
FROM nginx:1.25-alpine
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf       /etc/nginx/nginx.conf
COPY protected.conf   /etc/nginx/protected.conf
COPY proxy-params.conf /etc/nginx/proxy-params.conf
EXPOSE 8000
CMD ["nginx", "-g", "daemon off;"]
```

No more `conf.d/` or `html/` folders copied — everything is in `nginx.conf` or the two snippets.

### Step 5: Create single-file `auth-sidecar.py`

Merge `config.py`, `main.py`, `__init__.py` into one file.

Create `services/api-gateway/auth-sidecar.py`:

```python
"""
SmartCourse Auth Sidecar - Single-file JWT verification service.

Called internally by Nginx via auth_request. Not exposed to the internet.
Verifies JWT tokens and returns user identity headers to Nginx.
"""

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from jose import JWTError, jwt

# --- Config (was config.py) ---
JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")

# --- App ---
app = FastAPI(title="Auth Sidecar", docs_url=None, redoc_url=None)


@app.get("/verify")
async def verify_token(request: Request):
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=401,
            content={"error": "Unauthorized", "message": "Missing or malformed Authorization header"},
        )

    try:
        payload = jwt.decode(auth_header[7:], JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return JSONResponse(
            status_code=401,
            content={"error": "Unauthorized", "message": "Invalid or expired token"},
        )

    user_id = payload.get("sub")
    if not user_id:
        return JSONResponse(
            status_code=401,
            content={"error": "Unauthorized", "message": "Token missing required 'sub' claim"},
        )

    if payload.get("type") != "access":
        return JSONResponse(
            status_code=401,
            content={"error": "Unauthorized", "message": "Invalid token type. Use an access token."},
        )

    return JSONResponse(
        status_code=200,
        content={"status": "ok"},
        headers={"X-Auth-User-ID": str(user_id), "X-Auth-User-Role": str(payload.get("role", ""))},
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "auth-sidecar"}
```

**Changes from original**:
- Removed `pydantic-settings` dependency — just use `os.environ` (2 env vars don't need a settings class)
- No `__init__.py`, no `config.py`, no `src/` package structure
- Same exact logic and responses

### Step 6: Create `Dockerfile.sidecar` (simplified)

Create `services/api-gateway/Dockerfile.sidecar`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn[standard] python-jose[cryptography]
COPY auth-sidecar.py .
EXPOSE 8010
CMD ["uvicorn", "auth-sidecar:app", "--host", "0.0.0.0", "--port", "8010"]
```

**Changes from original**:
- No `pyproject.toml` needed — direct `pip install` of 3 dependencies
- No `setuptools` build, no package install step
- Single file copy

### Step 7: Create `.env`

Create `services/api-gateway/.env`:

```env
JWT_SECRET_KEY=your-super-secret-jwt-key-change-this-in-production
JWT_ALGORITHM=HS256
```

### Step 8: Update `docker-compose.yml` references

In your `docker-compose.yml`, update the two api-gateway services to point to the new paths:

```yaml
# Nginx gateway
smartcourse-api-gateway:
  build:
    context: ./services/api-gateway
    dockerfile: Dockerfile.nginx
  # ... rest stays the same

# Auth sidecar
smartcourse-auth-sidecar:
  build:
    context: ./services/api-gateway
    dockerfile: Dockerfile.sidecar
  env_file:
    - ./services/api-gateway/.env
  # ... rest stays the same
```

### Step 9: Delete old files

After verifying the lean version works, delete the old structure:

```
rm -rf services/api-gateway/nginx/
rm -rf services/api-gateway/auth-sidecar/
```

---

## Final Structure

```
services/api-gateway/
├── nginx.conf           # All nginx config in one file (~150 lines)
├── protected.conf       # Auth snippet, 5 lines (must use include - nginx limitation)
├── proxy-params.conf    # Proxy snippet, 11 lines (must use include - nginx limitation)
├── Dockerfile.nginx     # 6 lines
├── auth-sidecar.py      # All Python in one file (~55 lines)
├── Dockerfile.sidecar   # 5 lines
└── .env                 # 2 env vars
```

**17 files → 7 files** (5 if you don't count the two nginx snippets which are unavoidable).

---

## What Was Removed vs Kept

| Removed | Reason |
|---------|--------|
| `conf.d/cors.conf` | Inlined into `nginx.conf` server block |
| `conf.d/error-pages.conf` + `html/*.json` (6 files) | Replaced with inline named locations `@err4xx` |
| `conf.d/rate-limiting.conf` | Inlined into `nginx.conf` http block |
| `conf.d/upstreams.conf` | Inlined into `nginx.conf` http block |
| `pyproject.toml` | Not needed — deps installed directly in Dockerfile |
| `src/auth_sidecar/__init__.py` | Not needed — single file, no package |
| `src/auth_sidecar/config.py` | Replaced with 2 lines of `os.environ` |

| Kept | Reason |
|------|--------|
| `protected.conf` snippet | Nginx has no macros — 5 lines reused in 15 locations |
| `proxy-params.conf` snippet | Same reason — 11 lines reused in 15 locations |
| Two Dockerfiles | Two separate containers (nginx + python) is the correct pattern |
| Auth sidecar as Python | JWT verification needs a runtime — nginx can't do it natively |

---

## Verification Checklist

After implementing, verify nothing broke:

1. `docker compose up --build` — both containers start without errors
2. `curl http://localhost:8000/health` — returns `{"status":"ok","service":"api-gateway"}`
3. `curl http://localhost:8000/auth/login -X POST -d '...'` — works without auth (public route)
4. `curl http://localhost:8000/courses/` without token — returns 401
5. `curl http://localhost:8000/courses/ -H "Authorization: Bearer <valid_token>"` — returns courses
6. `curl http://localhost:8000/nonexistent` — returns 404 JSON
7. Check response headers include `X-Request-ID`, CORS headers
8. Rapid requests to `/auth/login` — should get 429 after burst exceeded
