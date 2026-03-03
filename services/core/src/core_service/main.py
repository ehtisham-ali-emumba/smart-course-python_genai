"""Core service application entrypoint."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core_service.config import core_settings
from core_service.kafka.enrollment_consumer import run_enrollment_consumer
from core_service.temporal.client import close_temporal_client
from core_service.temporal.worker import run_worker_with_retry

logging.basicConfig(
    level=getattr(logging, core_settings.LOG_LEVEL.upper(), logging.INFO)
)
logger = logging.getLogger(__name__)

# Background tasks
_background_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Core service startup/shutdown hooks."""
    logger.info(
        "core_service_starting temporal=%s namespace=%s task_queue=%s",
        core_settings.TEMPORAL_HOST,
        core_settings.TEMPORAL_NAMESPACE,
        core_settings.TEMPORAL_TASK_QUEUE,
    )

    # Start background tasks
    worker_task = asyncio.create_task(
        run_worker_with_retry(),
        name="temporal-worker",
    )
    consumer_task = asyncio.create_task(
        run_enrollment_consumer(),
        name="enrollment-consumer",
    )
    _background_tasks.extend([worker_task, consumer_task])

    logger.info("Background tasks started: temporal-worker, enrollment-consumer")

    yield

    # Shutdown
    logger.info("core_service_shutting_down")

    # Cancel background tasks
    for task in _background_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Close Temporal client
    await close_temporal_client()

    logger.info("core_service_shutdown_complete")


app = FastAPI(
    title="SmartCourse Core Service",
    description="Workflow orchestration and cross-cutting platform workflows",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> dict:
    """Container/local health endpoint."""
    return {
        "status": "ok",
        "service": "core-service",
    }
