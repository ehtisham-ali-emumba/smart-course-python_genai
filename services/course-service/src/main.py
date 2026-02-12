from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.router import router
from core.database import engine
from core.mongodb import close_mongodb, connect_mongodb
from models import Certificate, Course, Enrollment  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    # Connect to MongoDB on startup
    await connect_mongodb()
    yield
    # Cleanup on shutdown
    await close_mongodb()
    await engine.dispose()


app = FastAPI(
    title="SmartCourse Course Service",
    description="Course management, enrollment, and certification",
    version="0.1.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "course-service"}
