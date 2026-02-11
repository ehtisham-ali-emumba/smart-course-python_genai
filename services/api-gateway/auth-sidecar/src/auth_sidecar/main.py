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
