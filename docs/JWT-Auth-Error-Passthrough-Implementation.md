# JWT Auth Error Passthrough - Implementation Guide

## Problem

All JWT authentication failures (missing token, expired token, invalid token, wrong token type) return the **same generic error**:

```json
{"error": "Unauthorized", "message": "Authentication required.", "status": 401}
```

This happens because nginx's `auth_request` module discards the response body from the auth sidecar subrequest. It only uses the HTTP status code. When it sees a 401, it triggers `error_page 401 @err401`, which always returns the same static JSON — regardless of the actual failure reason.

## Solution

Pass the specific error message from the auth sidecar to nginx via a **response header** (`X-Auth-Error`), capture it with `auth_request_set`, and return it to the client instead of the generic message.

## Changes Required (3 files)

### 1. `services/api-gateway/auth-sidecar.py`

Extract a shared helper that builds both the response body and the `X-Auth-Error` header from the same dict — single source of truth, no duplication.

```python
import json

def _auth_error(message: str) -> JSONResponse:
    body = {"error": "Unauthorized", "message": message, "status": 401}
    return JSONResponse(
        status_code=401,
        content=body,
        headers={"X-Auth-Error": json.dumps(body)},
    )
```

Then replace every inline `JSONResponse(status_code=401, ...)` with a call to `_auth_error(message)`:

```python
# Before
return JSONResponse(status_code=401, content={"error": "Unauthorized", "message": "Invalid or expired token"})

# After
return _auth_error("Invalid or expired token")
```

Apply for all 4 error cases:
- `"Missing or malformed Authorization header"`
- `"Invalid or expired token"`
- `"Token missing required 'sub' claim"`
- `"Invalid token type. Use an access token."`

### 2. `services/api-gateway/protected.conf`

Add two lines:
- Capture the `X-Auth-Error` header from the sidecar response into an nginx variable
- Override the error page for 401 to use a new named location that returns the captured error

```nginx
auth_request /internal/auth-verify;
auth_request_set $auth_user_id   $upstream_http_x_auth_user_id;
auth_request_set $auth_user_role $upstream_http_x_auth_user_role;
auth_request_set $auth_error_body $upstream_http_x_auth_error;   # NEW: capture error body
proxy_set_header X-User-ID   $auth_user_id;
proxy_set_header X-User-Role $auth_user_role;
error_page 401 = @auth_error;                                    # NEW: override error page
```

The `= @auth_error` syntax (with `=`) tells nginx to use the status code from the named location rather than preserving the original.

### 3. `services/api-gateway/nginx.conf`

Add a new named location `@auth_error` next to the existing `@err401`:

```nginx
location @auth_error { internal; default_type application/json; return 401 $auth_error_body; }
```

This returns the specific error message captured from the sidecar. The existing `@err401` is kept as a fallback for any non-auth-related 401 errors.

## How It Works (Flow)

1. Client sends request to a protected route (missing/bad JWT)
2. Nginx makes a subrequest to auth sidecar via `auth_request`
3. Auth sidecar validates the token, fails, and returns:
   - HTTP 401 status
   - `X-Auth-Error` header with the specific JSON error body
4. Nginx captures `X-Auth-Error` into `$auth_error_body` via `auth_request_set`
5. `error_page 401 = @auth_error` routes to the new named location
6. `@auth_error` returns 401 with `$auth_error_body` — the **actual specific error**

## Expected Results

| Scenario | Before (generic) | After (specific) |
|---|---|---|
| No Authorization header | `Authentication required.` | `Missing or malformed Authorization header` |
| Expired/invalid JWT | `Authentication required.` | `Invalid or expired token` |
| Token missing `sub` | `Authentication required.` | `Token missing required sub claim` |
| Wrong token type | `Authentication required.` | `Invalid token type. Use an access token.` |
