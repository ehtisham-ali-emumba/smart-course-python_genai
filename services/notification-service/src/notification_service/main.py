from contextlib import asynccontextmanager

from fastapi import FastAPI

from notification_service.api.router import router
from notification_service.core.logging import get_logger, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    setup_logging()
    logger = get_logger("main")
    logger.info("notification_service_starting", port=8005)
    yield
    logger.info("notification_service_shutting_down")


app = FastAPI(
    title="SmartCourse Notification Service",
    description="Handles email, push, and in-app notifications for the SmartCourse platform",
    version="0.1.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "notification-service",
    }
