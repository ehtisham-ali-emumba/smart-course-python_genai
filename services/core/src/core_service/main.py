"""Core service application entrypoint."""

import asyncio
import logging
from contextlib import asynccontextmanager


from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from core_service.config import core_settings
from core_service.temporal.common.temporal_client import close_temporal_client
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
    _background_tasks.append(worker_task)

    logger.info("Background tasks started: temporal-worker")

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
# Expose Prometheus metrics
instrumentator = Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    should_respect_env_var=False,
    excluded_handlers=["/health", "/metrics"],
    should_instrument_requests_inprogress=True,
    inprogress_name="smartcourse_inprogress_requests",
    inprogress_labels=True,
)
instrumentator.instrument(app).expose(app, endpoint="/metrics")


@app.get("/health")
async def health_check() -> dict:
    """Container/local health endpoint."""
    return {
        "status": "ok",
        "service": "core-service",
    }
