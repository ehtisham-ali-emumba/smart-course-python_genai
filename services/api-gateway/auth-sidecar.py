"""
SmartCourse Auth Sidecar - Single-file JWT verification service.

Called internally by Nginx via auth_request. Not exposed to the internet.
Verifies JWT tokens and returns user identity headers to Nginx.
"""

import json
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from gateway_health import build_gateway_health_report
from jose import JWTError, jwt
from prometheus_fastapi_instrumentator import Instrumentator

# --- Config (was config.py) ---
JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
HEALTHCHECK_TIMEOUT_SECONDS = float(
    os.environ.get("HEALTHCHECK_TIMEOUT_SECONDS", "2.0")
)

# --- App ---
app = FastAPI(title="Auth Sidecar", docs_url=None, redoc_url=None)

Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    excluded_handlers=["/health", "/metrics"],
    should_instrument_requests_inprogress=True,
    inprogress_name="smartcourse_auth_inprogress_requests",
    inprogress_labels=True,
).instrument(app).expose(app, endpoint="/metrics")


def _auth_error(message: str) -> JSONResponse:
    body = {"error": "Unauthorized", "message": message, "status": 401}
    return JSONResponse(
        status_code=401,
        content=body,
        headers={"X-Auth-Error": json.dumps(body)},
    )


@app.get("/verify")
async def verify_token(request: Request):
    auth_header = request.headers.get("Authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        return _auth_error("Missing or malformed Authorization header")

    try:
        payload = jwt.decode(
            auth_header[7:], JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM]
        )
    except JWTError:
        return _auth_error("Invalid or expired token")

    user_id = payload.get("sub")
    if not user_id:
        return _auth_error("Token missing required 'sub' claim")

    if payload.get("type") != "access":
        return _auth_error("Invalid token type. Use an access token.")

    return JSONResponse(
        status_code=200,
        content={"status": "ok"},
        headers={
            "X-Auth-User-ID": str(user_id),
            "X-Auth-User-Role": str(payload.get("role", "")),
            "X-Auth-Profile-ID": str(payload.get("profile_id", "")),
        },
    )


@app.get("/health")
async def health():
    return await build_gateway_health_report(HEALTHCHECK_TIMEOUT_SECONDS)
