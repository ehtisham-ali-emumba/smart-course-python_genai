"""Core service application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core_service.api.router import router
from core_service.config import core_settings

logging.basicConfig(level=getattr(logging, core_settings.LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Core service startup/shutdown hooks."""
    logger.info(
        "core_service_starting temporal=%s namespace=%s task_queue=%s",
        core_settings.TEMPORAL_HOST,
        core_settings.TEMPORAL_NAMESPACE,
        core_settings.TEMPORAL_TASK_QUEUE,
    )
    yield
    logger.info("core_service_shutting_down")


app = FastAPI(
    title="SmartCourse Core Service",
    description="Workflow orchestration and cross-cutting platform workflows",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/health")
async def health_check() -> dict:
    """Container/local health endpoint."""
    return {
        "status": "ok",
        "service": "core-service",
    }

