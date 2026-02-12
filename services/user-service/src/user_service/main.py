from contextlib import asynccontextmanager

from fastapi import FastAPI

from user_service.api.router import router
from user_service.config import settings
from user_service.core.database import engine
from user_service.core.redis import close_redis, connect_redis, get_redis
from user_service.models import User, InstructorProfile  # noqa: F401 - register with Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    await connect_redis(settings.REDIS_URL)
    yield
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="SmartCourse User Service",
    description="User authentication and profile management",
    version="0.1.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(router)


@app.get("/health")
async def health_check():
    """Health check endpoint with dependency status."""
    redis_ok = False
    client = get_redis()
    if client:
        try:
            await client.ping()
            redis_ok = True
        except Exception:
            pass

    return {
        "status": "ok",
        "service": "user-service",
        "dependencies": {
            "redis": "connected" if redis_ok else "disconnected",
        },
    }
