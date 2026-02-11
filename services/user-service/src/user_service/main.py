from fastapi import FastAPI
from contextlib import asynccontextmanager

from user_service.api.router import router
from user_service.core.database import Base, engine
from user_service.models import User, InstructorProfile  # noqa: F401 - register with Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables if missing, then cleanup on shutdown."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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
