# Nginx API Gateway — Deep Dive Guide

This document explains every Nginx concept used in the SmartCourse api-gateway service, line by line. Read this before presenting to your mentor.

---

## Table of Contents

1. [What is Nginx and Why We Use It](#1-what-is-nginx-and-why-we-use-it)
2. [The Big Picture — How Our Gateway Works](#2-the-big-picture)
3. [Config Structure — The 3 Nesting Levels](#3-config-structure)
4. [Top-Level Directives](#4-top-level-directives)
5. [The `http` Block — Global Settings](#5-the-http-block)
6. [The `server` Block — Our API Gateway](#6-the-server-block)
7. [Location Blocks — Route Matching](#7-location-blocks)
8. [Reverse Proxy — proxy_pass Explained](#8-reverse-proxy)
9. [Auth Subrequest — The JWT Flow](#9-auth-subrequest)
10. [Rate Limiting](#10-rate-limiting)
11. [CORS Headers](#11-cors-headers)
12. [Error Handling](#12-error-handling)
13. [The Two Include Files — Why They Exist](#13-the-two-include-files)
14. [Variables and Dynamic DNS](#14-variables-and-dynamic-dns)
15. [Upstream Blocks](#15-upstream-blocks)
16. [Auth Sidecar — The Python Side](#16-auth-sidecar)
17. [Full Request Lifecycle — End to End](#17-full-request-lifecycle)
18. [Mentor Q&A — Common Questions](#18-mentor-qa)

---

## 1. What is Nginx and Why We Use It

Nginx is a **reverse proxy server**. In our architecture, it sits between the frontend/client and all backend microservices.

```
Client (browser/mobile)
        |
        v
   [ Nginx :8000 ]  <-- single entry point
        |
   +---------+---------+---------+--------+
   |         |         |         |        |
user-svc  course-svc  core-svc  ai-svc  notif-svc
 :8001      :8002      :8006    :8009    :8005
```

**Why not let clients call services directly?**

- **Single entry point**: Clients only know about port 8000, not 5+ service ports
- **Auth in one place**: JWT verification happens once at the gateway, not in every service
- **Rate limiting**: Protects all services from abuse centrally
- **CORS**: Handled once, not duplicated in every service
- **Service discovery**: If a service port changes, only nginx config changes — clients are unaffected

---

## 2. The Big Picture

Our api-gateway is **two containers** working together:

| Container | Tech | Port | Role |
|-----------|------|------|------|
| `smartcourse-api-gateway` | Nginx | 8000 (public) | Routing, rate limiting, CORS, proxying |
| `smartcourse-auth-sidecar` | Python/FastAPI | 8010 (internal only) | JWT token verification |

**Why two containers?** Nginx is extremely fast at routing HTTP requests but it **cannot decode JWT tokens natively**. It has no built-in JWT library. So we use Nginx's `auth_request` feature to ask a tiny Python service "is this token valid?" before forwarding the request.

The sidecar is **never exposed to the internet** — it only lives on the internal Docker network.

---

## 3. Config Structure

Every `nginx.conf` has this hierarchy:

```
# Top level (main context)
worker_processes auto;

events { ... }        # Connection handling

http {                # All HTTP settings
    server {          # A virtual host (we have one)
        location { }  # Route rules (we have many)
        location { }
    }
}
```

Think of it as: **http** contains **server** contains **location**. Settings at a higher level are inherited by lower levels unless overridden.

---

## 4. Top-Level Directives

```nginx
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;
```

- **`worker_processes auto`**: Nginx spawns multiple worker processes to handle requests in parallel. `auto` means "use as many workers as CPU cores". On a 4-core machine, this creates 4 workers.

- **`error_log ... warn`**: Where Nginx writes error logs. `warn` is the severity threshold — it logs warnings and above (warn, error, crit, alert, emerg). Debug and info are excluded.

- **`pid`**: File where Nginx stores its process ID. Standard boilerplate.

### Events Block

```nginx
events {
    worker_connections 2048;
    multi_accept on;
}
```

- **`worker_connections 2048`**: Each worker can handle up to 2048 simultaneous connections. Total capacity = workers x 2048. For our use case this is more than enough.

- **`multi_accept on`**: When a worker gets notified of new connections, accept ALL pending connections at once instead of one at a time. Slightly better performance under load.

---

## 5. The `http` Block

Everything inside `http { }` applies to all HTTP traffic.

### 5.1 Basics

```nginx
include       /etc/nginx/mime.types;
default_type  application/json;
resolver 127.0.0.11 valid=10s ipv6=off;
```

- **`include /etc/nginx/mime.types`**: Loads a file that maps file extensions to MIME types (`.html` -> `text/html`, `.css` -> `text/css`, etc.). This comes with Nginx by default.

- **`default_type application/json`**: If Nginx can't determine the content type, default to JSON. We set this because our gateway only serves API responses, never HTML pages.

- **`resolver 127.0.0.11`**: This is **Docker's internal DNS server**. When Nginx sees a hostname like `smartcourse-user-service`, it asks this resolver to convert it to an IP address. `valid=10s` means cache the DNS result for 10 seconds then re-resolve (important: if a container restarts and gets a new IP, Nginx picks it up within 10 seconds). `ipv6=off` because Docker networking is IPv4.

### 5.2 Logging

```nginx
log_format json_combined escape=json
    '{'
        '"time":"$time_iso8601",'
        '"remote_addr":"$remote_addr",'
        '"request":"$request",'
        '"status":$status,'
        ...
    '}';
access_log /var/log/nginx/access.log json_combined;
```

This defines a **custom log format** in JSON. Each request produces one JSON line:

```json
{"time":"2026-03-06T10:30:00+00:00","remote_addr":"172.18.0.1","request":"GET /courses/ HTTP/1.1","status":200,...}
```

**Why JSON logs?** They're machine-parseable. If you ever send logs to a monitoring tool (ELK, Grafana, Datadog), JSON logs can be indexed directly without regex parsing.

The `$variables` are Nginx built-in variables:
- `$time_iso8601` — timestamp
- `$remote_addr` — client IP
- `$request` — full request line ("GET /courses/ HTTP/1.1")
- `$status` — response status code
- `$request_time` — total time to process the request (seconds)
- `$upstream_response_time` — time the backend took to respond
- `$request_id` — unique ID Nginx generates per request (for tracing)

### 5.3 Performance Tuning

```nginx
sendfile        on;
tcp_nopush      on;
tcp_nodelay     on;
keepalive_timeout 65;
keepalive_requests 1000;
```

- **`sendfile on`**: Uses the OS kernel's `sendfile()` syscall to transfer files directly from disk to network socket without copying through userspace. Faster for serving static files (less relevant for our proxy-only gateway, but no harm).

- **`tcp_nopush on`**: Waits until a full TCP packet is assembled before sending. Reduces the number of small packets. Works with `sendfile`.

- **`tcp_nodelay on`**: Once a response starts sending, send data immediately without waiting to fill a packet. Seems contradictory with `tcp_nopush` but they work at different stages — `nopush` for headers, `nodelay` for the body.

- **`keepalive_timeout 65`**: Keep idle client connections open for 65 seconds. If the same client makes another request within 65 seconds, it reuses the same TCP connection (faster than opening a new one).

- **`keepalive_requests 1000`**: After 1000 requests on a single keepalive connection, close it and force the client to open a new one. Prevents memory leaks from very long-lived connections.

### 5.4 Security Headers

```nginx
server_tokens off;
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header X-Request-ID $request_id always;
```

- **`server_tokens off`**: Hides the Nginx version from response headers. Without this, responses include `Server: nginx/1.25.3` — an attacker could look up known vulnerabilities for that exact version. With it: just `Server: nginx`.

- **`X-Content-Type-Options "nosniff"`**: Tells browsers "trust the Content-Type header I send, don't try to guess". Prevents MIME-type sniffing attacks where a browser might execute a disguised file.

- **`X-Frame-Options "DENY"`**: Prevents our API responses from being loaded inside an `<iframe>`. Blocks clickjacking attacks.

- **`X-Request-ID`**: Attaches a unique ID to every response. If a user reports a bug, they can share this ID, and you can grep your logs for it to trace the exact request path through all services.

- **`always`**: Add these headers on ALL responses, even error responses (4xx, 5xx). Without `always`, headers are only added on successful 2xx/3xx responses.

### 5.5 Buffer Settings

```nginx
client_max_body_size 10m;
client_body_buffer_size 128k;
proxy_buffer_size 16k;
proxy_buffers 4 32k;
proxy_busy_buffers_size 64k;
```

- **`client_max_body_size 10m`**: Maximum request body size. If someone tries to POST more than 10MB, Nginx immediately returns `413 Request Entity Too Large` without forwarding to the backend. Protects services from huge payloads.

- **`client_body_buffer_size 128k`**: If the request body is under 128KB, Nginx keeps it in memory. If larger, it writes to a temp file on disk. 128k covers most JSON API requests.

- **`proxy_buffer_size 16k`**: Size of the buffer for reading the **first part** of the response from a backend (usually the headers). 16k is enough for most API response headers.

- **`proxy_buffers 4 32k`**: Nginx uses 4 buffers of 32KB each (128KB total) to buffer the backend response body before sending it to the client. If the response is larger than 128KB, Nginx starts sending to the client before the backend finishes (streaming).

- **`proxy_busy_buffers_size 64k`**: How much buffered data Nginx can be actively sending to the client at once while still receiving more from the backend.

---

## 6. The `server` Block

```nginx
server {
    listen 8000;
    server_name _;
    ...
}
```

- **`listen 8000`**: This server listens on port 8000. This is the only port exposed from the Nginx container.

- **`server_name _`**: The underscore is a catch-all — accept requests regardless of the `Host` header. In production with a real domain, you'd set `server_name api.smartcourse.com`.

---

## 7. Location Blocks — Route Matching

Locations are how Nginx decides what to do with a request based on the URL path. There are different match types:

### 7.1 Exact Match (`=`)

```nginx
location = /health { ... }
location = /courses { ... }
location = /auth/me { ... }
```

The `=` means **exact match only**. `/health` matches, `/health/` does NOT, `/healthcheck` does NOT. This is the fastest match — Nginx stops searching immediately.

### 7.2 Prefix Match (no modifier)

```nginx
location /courses/ { ... }
location /auth/ { ... }
location /profile/ { ... }
```

No modifier means **prefix match**. `/courses/` matches `/courses/`, `/courses/123`, `/courses/123/lessons`, etc. — anything that starts with `/courses/`.

### 7.3 Regex Match (`~`)

```nginx
location ~ ^/auth/(register|login|refresh)$ { ... }
```

The `~` means **case-sensitive regex**. This matches exactly:
- `/auth/register`
- `/auth/login`
- `/auth/refresh`

And nothing else. The `^` anchors to the start, `$` anchors to the end, `(register|login|refresh)` means "one of these three words".

### 7.4 Named Location (`@`)

```nginx
location @err401 { internal; return 401 '...'; }
```

The `@` prefix creates a **named location** that can only be reached internally (via `error_page` or `try_files`), never by a client request. Clients cannot visit `@err401` directly.

### 7.5 Match Priority

When multiple locations could match, Nginx uses this priority:

1. `= /exact` — exact match wins first (highest priority)
2. `^~ /prefix` — prefix match with `^~` (we don't use this)
3. `~ regex` — regex match
4. `/prefix` — regular prefix match (longest prefix wins)

**Example with our config**: A request to `/auth/login`:
1. Does it match `= /auth/me`? No.
2. Does it match `~ ^/auth/(register|login|refresh)$`? **Yes** — goes to public route (no auth required).
3. It would also match `/auth/` prefix, but regex has higher priority.

This is how we make login/register public while everything else under `/auth/` requires JWT.

---

## 8. Reverse Proxy — proxy_pass

```nginx
proxy_pass $user_service$request_uri;
```

This is the core of what makes Nginx a **reverse proxy**. It forwards the client's request to a backend service.

- `$user_service` resolves to `http://smartcourse-user-service:8001` (set via `set` directive)
- `$request_uri` is the original request path including query string (e.g., `/auth/me?include=profile`)

So a request to `http://localhost:8000/auth/me` gets forwarded to `http://smartcourse-user-service:8001/auth/me`.

**The client never knows which backend handled it.** The response flows back: backend -> Nginx -> client.

### Special case: /courses without trailing slash

```nginx
location = /courses {
    proxy_pass $course_service/courses/$is_args$args;
}
```

If someone requests `/courses` (no slash), we proxy to `/courses/` on the backend. `$is_args` is either `?` (if there are query params) or empty. `$args` is the query string. This handles the edge case so both `/courses` and `/courses/` work.

---

## 9. Auth Subrequest — The JWT Flow

This is the most important concept in the gateway. It's how we authenticate requests using Nginx + Python together.

### 9.1 The Mechanism: `auth_request`

In `protected.conf`:
```nginx
auth_request /internal/auth-verify;
```

This tells Nginx: **before processing this request, first send a subrequest to `/internal/auth-verify`**. If that subrequest returns 200, proceed. If it returns 401/403, deny the request.

### 9.2 The Internal Location

```nginx
location = /internal/auth-verify {
    internal;
    proxy_pass $auth_sidecar/verify;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_set_header Authorization $http_authorization;
}
```

- **`internal`**: This location can ONLY be called by Nginx internally (via `auth_request`). If a client tries to visit `/internal/auth-verify` directly, they get 404.

- **`proxy_pass $auth_sidecar/verify`**: Forward the subrequest to the Python sidecar at `http://smartcourse-auth-sidecar:8010/verify`.

- **`proxy_pass_request_body off`**: Don't send the original request body to the sidecar. It only needs the Authorization header, not the POST data. This makes the auth check faster.

- **`proxy_set_header Content-Length ""`**: Since we stripped the body, clear the Content-Length header.

- **`proxy_set_header Authorization $http_authorization`**: Forward the client's `Authorization: Bearer <token>` header to the sidecar. `$http_authorization` is Nginx's way of accessing any request header — `$http_` + header name in lowercase with dashes replaced by underscores.

### 9.3 Capturing the Response

Back in `protected.conf`:
```nginx
auth_request_set $auth_user_id   $upstream_http_x_auth_user_id;
auth_request_set $auth_user_role $upstream_http_x_auth_user_role;
proxy_set_header X-User-ID   $auth_user_id;
proxy_set_header X-User-Role $auth_user_role;
```

When the sidecar returns 200, it includes custom headers:
```
X-Auth-User-ID: 123
X-Auth-User-Role: student
```

- **`auth_request_set`**: Captures response headers from the auth subrequest into Nginx variables. `$upstream_http_x_auth_user_id` means "the `X-Auth-User-ID` header from the upstream (sidecar) response".

- **`proxy_set_header X-User-ID`**: Injects the captured user ID into the request that goes to the actual backend service. So the course-service receives `X-User-ID: 123` as a trusted header — it doesn't need to decode the JWT itself.

### 9.4 The Complete Flow (Visual)

```
Client: GET /courses/  (Authorization: Bearer eyJhbG...)
  |
  v
Nginx: matches "location /courses/" -> sees "auth_request"
  |
  v
Nginx -> Sidecar: GET /verify  (Authorization: Bearer eyJhbG...)
  |
  v
Sidecar: decodes JWT, extracts user_id=123, role=student
  |
  v
Sidecar -> Nginx: 200 OK  (X-Auth-User-ID: 123, X-Auth-User-Role: student)
  |
  v
Nginx: auth passed! captures headers, adds X-User-ID: 123 to request
  |
  v
Nginx -> Course Service: GET /courses/  (X-User-ID: 123, X-User-Role: student)
  |
  v
Course Service -> Nginx -> Client: 200 OK [{...courses...}]
```

If the token is invalid:
```
Sidecar -> Nginx: 401 Unauthorized
  |
  v
Nginx: auth failed! triggers error_page 401 -> returns @err401 JSON to client
(request NEVER reaches the course service)
```

### 9.5 Public Routes — Skipping Auth

```nginx
location ~ ^/auth/(register|login|refresh)$ {
    proxy_set_header X-User-ID "";
    proxy_set_header X-User-Role "";
    proxy_pass $user_service$request_uri;
}
```

Notice: **no `include protected.conf`** here. That means no `auth_request`, no subrequest to the sidecar. The request goes straight to the user service.

The empty `proxy_set_header X-User-ID ""` is a security measure — it **clears** these headers so a malicious client can't fake them by sending `X-User-ID: admin` in their request.

---

## 10. Rate Limiting

### 10.1 Defining Zones

```nginx
limit_req_zone $binary_remote_addr zone=api_general:10m rate=30r/s;
limit_req_zone $binary_remote_addr zone=api_auth:10m   rate=5r/s;
```

- **`$binary_remote_addr`**: The client's IP address in binary form (uses 64 bytes per entry vs 128 for string form). This is the **key** — each IP gets its own counter.

- **`zone=api_auth:10m`**: Creates a shared memory zone named `api_auth` of 10MB. At ~64 bytes per IP, 10MB tracks ~160,000 unique IPs. The zone name is referenced in location blocks.

- **`rate=5r/s`**: Allow 5 requests per second per IP. Internally, Nginx converts this to "1 request every 200ms" — it's a token bucket algorithm.

### 10.2 Applying Rate Limits

```nginx
location ~ ^/auth/(register|login|refresh)$ {
    limit_req zone=api_auth burst=10 nodelay;
    ...
}
```

- **`zone=api_auth`**: Use the `api_auth` zone (5r/s per IP).

- **`burst=10`**: Allow bursts of up to 10 extra requests. Without burst, if you send 2 requests in the same millisecond, the second gets rejected. With `burst=10`, Nginx queues up to 10 excess requests.

- **`nodelay`**: Process burst requests immediately instead of spacing them out. Without `nodelay`, burst requests are delayed to maintain the rate. With it, all 10 burst requests are processed instantly, but the burst "bucket" takes time to refill.

**Why stricter rate on auth?** Login/register endpoints are brute-force targets. 5r/s is enough for legitimate users but prevents password-guessing attacks. General API gets 30r/s because normal app usage makes many requests.

```nginx
limit_req_status 429;
```

When rate limited, return HTTP 429 (Too Many Requests) instead of the default 503.

---

## 11. CORS Headers

```nginx
add_header 'Access-Control-Allow-Origin' '*' always;
add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, PATCH, DELETE, OPTIONS' always;
add_header 'Access-Control-Allow-Headers' 'Authorization, Content-Type, X-Requested-With, Accept, Origin' always;
add_header 'Access-Control-Expose-Headers' 'X-Request-ID' always;
```

**What is CORS?** When your React frontend at `http://localhost:3000` calls your API at `http://localhost:8000`, the browser blocks it by default — different origins (different ports = different origins). CORS headers tell the browser "it's okay, I allow this frontend to call me."

- **Allow-Origin `*`**: Allow any domain. In production, you'd restrict this to your actual frontend domain.
- **Allow-Methods**: Which HTTP methods the frontend can use.
- **Allow-Headers**: Which headers the frontend can send (notably `Authorization` for JWT).
- **Expose-Headers**: Which response headers the frontend JavaScript can read. Without this, `X-Request-ID` would be invisible to frontend code.

### Preflight Requests

```nginx
if ($request_method = 'OPTIONS') {
    return 204;
}
```

Before making a "complex" request (like POST with JSON or any request with Authorization header), browsers first send an OPTIONS request asking "are you CORS-friendly?". We return 204 (No Content) with the CORS headers — the browser sees the headers and proceeds with the actual request.

---

## 12. Error Handling

```nginx
error_page 401 @err401;
location @err401 {
    internal;
    return 401 '{"error":"Unauthorized","message":"Authentication required.","status":401}';
}
```

- **`error_page 401 @err401`**: When any location would return a 401 status, redirect internally to the named location `@err401`.

- **`internal`**: Named locations are always internal — clients can't access them directly.

- **`return 401 '...'`**: Return a JSON body with status 401. This ensures all error responses from the gateway are consistent JSON, not Nginx's default HTML error pages.

**Why this matters**: Without custom error pages, a 502 error would return:
```html
<html><head><title>502 Bad Gateway</title></head>...</html>
```

Your frontend expects JSON, so this would break error handling. With our setup, it returns:
```json
{"error":"Bad Gateway","message":"Upstream service unavailable.","status":502}
```

---

## 13. The Two Include Files

### 13.1 `protected.conf` (5 lines, used 13 times)

```nginx
auth_request /internal/auth-verify;
auth_request_set $auth_user_id   $upstream_http_x_auth_user_id;
auth_request_set $auth_user_role $upstream_http_x_auth_user_role;
proxy_set_header X-User-ID   $auth_user_id;
proxy_set_header X-User-Role $auth_user_role;
```

Every protected route needs these exact 5 lines. Nginx has no functions, no macros, no variables that can hold directive blocks. The `include` directive is the **only reuse mechanism**.

If we inlined this: 5 lines x 13 locations = 65 extra lines of identical code. Change the auth header name? Edit 13 places.

### 13.2 `proxy-params.conf` (11 lines, used 15 times)

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

What each line does:

- **`proxy_http_version 1.1`**: Use HTTP/1.1 to talk to backends (required for keepalive connections).
- **`Host $host`**: Forward the original Host header so the backend knows the original hostname.
- **`X-Real-IP $remote_addr`**: The actual client IP. Without this, backends only see Nginx's IP.
- **`X-Forwarded-For`**: Appends the client IP to a chain of proxies. If there are multiple proxies, this shows the full chain.
- **`X-Forwarded-Proto $scheme`**: Tells the backend whether the original request was HTTP or HTTPS.
- **`X-Request-ID $request_id`**: Passes the unique request ID to the backend for distributed tracing.
- **`Connection ""`**: Clears the Connection header to enable keepalive with the upstream. HTTP/1.1 keepalive requires this.
- **`proxy_connect_timeout 5s`**: Give up connecting to the backend after 5 seconds (backend is down).
- **`proxy_send_timeout 30s`**: If Nginx can't send data to the backend for 30 seconds, timeout.
- **`proxy_read_timeout 30s`**: If the backend doesn't send any data for 30 seconds, timeout.
- **`proxy_next_upstream error timeout http_502 http_503`**: If the backend returns 502/503 or connection fails, try the next upstream server (relevant when an upstream has multiple servers).
- **`proxy_next_upstream_tries 2`**: Try at most 2 upstream servers before giving up.

If we inlined this: 11 lines x 15 locations = 165 extra lines of identical code.

### 13.3 The Rule

**Inline** config that's used once (CORS, rate limit zones, upstreams, error pages). **Include** config that's used many times (proxy params, auth snippet). This is the exact reasoning behind the lean refactor.

---

## 14. Variables and Dynamic DNS

```nginx
set $user_service http://smartcourse-user-service:8001;
```

Then used as:
```nginx
proxy_pass $user_service$request_uri;
```

**Why use variables instead of hardcoding the URL directly in `proxy_pass`?**

This is a Docker-specific trick. When you write:
```nginx
proxy_pass http://smartcourse-user-service:8001;  # hardcoded
```
Nginx resolves the hostname **once at startup**. If the container restarts and gets a new IP, Nginx still uses the old IP — requests fail.

When you use a variable:
```nginx
set $user_service http://smartcourse-user-service:8001;
proxy_pass $user_service$request_uri;  # variable
```
Nginx resolves the hostname **on every request** using the configured `resolver`. The container can restart, get a new IP, and Nginx adapts automatically.

This works together with:
```nginx
resolver 127.0.0.11 valid=10s;
```
Docker's DNS (`127.0.0.11`) is re-queried every 10 seconds to refresh the IP mapping.

---

## 15. Upstream Blocks

```nginx
upstream user-service {
    server smartcourse-user-service:8001;
    keepalive 32;
}
```

An `upstream` block defines a **pool of backend servers**. Right now each pool has one server, but the structure supports scaling:

```nginx
upstream user-service {
    server smartcourse-user-service-1:8001;
    server smartcourse-user-service-2:8001;
    keepalive 32;
}
```

Nginx would automatically **load balance** between the two servers using round-robin.

**`keepalive 32`**: Maintain up to 32 idle keepalive connections to this upstream. Without keepalive, Nginx opens a new TCP connection for every single request to the backend — slow. With keepalive, it reuses existing connections.

**Note**: In our lean config, we use `set` variables for `proxy_pass` (for dynamic DNS resolution) and `upstream` blocks exist alongside them. The upstreams provide the keepalive connection pooling, while the variables provide dynamic resolution. They work complementarily.

---

## 16. Auth Sidecar — The Python Side

The sidecar is a minimal FastAPI app (single file, ~50 lines). Here's what it does:

```python
JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]   # same secret the user-service uses to sign tokens
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
```

It needs the **same secret key** that the user-service uses to sign JWTs. This is a symmetric key (HS256) — the same key signs and verifies.

### The /verify Endpoint

```python
@app.get("/verify")
async def verify_token(request: Request):
```

Called by Nginx's `auth_request`. Steps:

1. **Extract token**: Get `Authorization: Bearer <token>` header, strip the "Bearer " prefix
2. **Decode JWT**: `jwt.decode()` verifies the signature AND checks expiration automatically
3. **Validate claims**: Ensure `sub` (user ID) exists and `type` is "access" (not a refresh token)
4. **Return headers**: On success, return `X-Auth-User-ID` and `X-Auth-User-Role` as response headers

**Why check token type?** Your user-service issues two types of JWTs:
- **Access token**: Short-lived, used for API access
- **Refresh token**: Longer-lived, used only to get new access tokens

Without this check, someone could use a refresh token to access protected routes — the signature would be valid but it's the wrong type of token.

**Why `docs_url=None, redoc_url=None`?** FastAPI auto-generates Swagger docs at `/docs`. Since this service is internal-only, we disable the docs UI — no one should be browsing to it.

---

## 17. Full Request Lifecycle — End to End

Let's trace `GET /courses/` with a valid JWT through every step:

```
1. CLIENT sends:
   GET /courses/ HTTP/1.1
   Host: localhost:8000
   Authorization: Bearer eyJhbGciOiJIUzI1NiIs...

2. NGINX receives on port 8000
   - Matches: location /courses/ { ... }
   - Sees: include protected.conf -> auth_request /internal/auth-verify
   - PAUSES the main request

3. NGINX sends internal subrequest:
   GET /verify HTTP/1.1
   Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
   -> to smartcourse-auth-sidecar:8010

4. SIDECAR receives /verify
   - Extracts token from Authorization header
   - jwt.decode() verifies signature with shared secret
   - jwt.decode() checks expiration (automatic)
   - Extracts: sub="user-123", role="student", type="access"
   - Returns: 200 OK
     Headers: X-Auth-User-ID: user-123, X-Auth-User-Role: student

5. NGINX receives 200 from sidecar
   - auth_request_set captures X-Auth-User-ID -> $auth_user_id
   - auth_request_set captures X-Auth-User-Role -> $auth_user_role
   - RESUMES the main request

6. NGINX forwards to backend:
   GET /courses/ HTTP/1.1
   Host: localhost
   X-User-ID: user-123         <- injected by nginx
   X-User-Role: student        <- injected by nginx
   X-Real-IP: 172.18.0.1       <- from proxy-params.conf
   X-Request-ID: abc123def     <- from proxy-params.conf
   -> to smartcourse-course-service:8002

7. COURSE SERVICE receives the request
   - Trusts X-User-ID header (it came from nginx, not from the client)
   - Returns courses for user-123
   - 200 OK [{...}, {...}]

8. NGINX receives response from course service
   - Adds CORS headers
   - Adds X-Request-ID header
   - Adds security headers (X-Content-Type-Options, X-Frame-Options)
   - Forwards to client

9. CLIENT receives:
   HTTP/1.1 200 OK
   Access-Control-Allow-Origin: *
   X-Request-ID: abc123def
   X-Content-Type-Options: nosniff
   [{...courses...}]
```

**Total Nginx processing time**: typically under 1ms (excluding backend response time).

---

## 18. Mentor Q&A — Common Questions

### "Why Nginx and not Express/FastAPI as a gateway?"

Nginx handles **50,000+ requests/second** on a single core. An Express gateway might handle 5,000. Nginx is purpose-built for proxying — it doesn't load a runtime, doesn't interpret code per request, and uses async I/O natively. For pure routing + auth + rate limiting, it's the right tool.

### "Why not put JWT verification in every microservice?"

- **DRY**: Auth logic in one place, not duplicated across 5+ services in different languages
- **Security**: Services on the internal network trust `X-User-ID` headers from the gateway. They don't need the JWT secret key at all (except user-service which issues the tokens)
- **Performance**: The sidecar verifies once, not once per service per request

### "What if the auth sidecar goes down?"

Nginx gets no response from the subrequest, triggers `error_page 502`, and returns the JSON error to the client. No protected route works until the sidecar is back. This is correct behavior — better to reject all requests than to let unauthenticated requests through.

### "Why is the sidecar a separate container and not embedded in Nginx?"

Nginx can't run Python. You could compile Nginx with the lua-nginx-module or njs (Nginx JavaScript), but:
- lua/njs JWT libraries are less maintained than Python's `python-jose`
- A separate container is easier to debug, test, and replace
- The sidecar is ~50 lines of Python — the overhead of a container is justified by the simplicity

### "What does `internal` mean on a location?"

It means Nginx only allows access to that location from other Nginx directives (`auth_request`, `error_page`, `try_files`). If a client sends `GET /internal/auth-verify`, Nginx returns 404 — the location is invisible to the outside world.

### "How do you add a new microservice?"

Add 3 things:
1. A `set $new_service http://smartcourse-new-service:PORT;` variable
2. An `upstream` block (if you want keepalive pooling)
3. A `location` block that includes `protected.conf` and `proxy-params.conf`

That's it. About 6 lines of config.

### "What happens if someone sends a fake X-User-ID header?"

On **public routes**, we explicitly clear it:
```nginx
proxy_set_header X-User-ID "";
```

On **protected routes**, `proxy_set_header X-User-ID $auth_user_id;` **overwrites** whatever the client sent with the value from the sidecar. The client's fake header is discarded.

### "Why `$binary_remote_addr` and not `$remote_addr` for rate limiting?"

Storage efficiency. `$remote_addr` stores the IP as a string ("192.168.1.100" = ~15 bytes + overhead = ~128 bytes per entry). `$binary_remote_addr` stores it as raw bytes (4 bytes for IPv4, 16 for IPv6, ~64 bytes per entry with overhead). In a 10MB zone, that's ~80,000 vs ~160,000 IPs tracked. Double the capacity for the same memory.

### "Why both `upstream` blocks AND `set` variables for the same services?"

They serve different purposes:
- **`upstream`** blocks provide **keepalive connection pooling** — reusing TCP connections to backends
- **`set` variables** in `proxy_pass` enable **dynamic DNS resolution** — re-resolving hostnames when containers restart

Without the variable trick, Nginx resolves DNS once at startup and caches it forever. If a container restarts with a new IP, requests fail until you reload Nginx. The variable forces per-request resolution via the Docker DNS resolver.
