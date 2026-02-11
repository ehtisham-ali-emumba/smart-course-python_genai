from fastapi import FastAPI
from contextlib import asynccontextmanager

from user_service.api.router import router
from user_service.core.database import engine
from user_service.models import User, InstructorProfile  # noqa: F401 - register with Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    # Tables are now managed by Alembic migrations.
    # Run `alembic upgrade head` before starting the app.
    yield
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
    """Health check endpoint."""
    return {"status": "ok", "service": "user-service"}
