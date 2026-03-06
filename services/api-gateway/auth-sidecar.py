"""
SmartCourse Auth Sidecar - Single-file JWT verification service.

Called internally by Nginx via auth_request. Not exposed to the internet.
Verifies JWT tokens and returns user identity headers to Nginx.
"""

import json
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from jose import JWTError, jwt

# --- Config (was config.py) ---
JWT_SECRET_KEY = os.environ["JWT_SECRET_KEY"]
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")

# --- App ---
app = FastAPI(title="Auth Sidecar", docs_url=None, redoc_url=None)


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
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "auth-sidecar"}
