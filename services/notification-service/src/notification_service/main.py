import asyncio
import sys
from contextlib import asynccontextmanager


from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from notification_service.api.router import router
from notification_service.core.logging import get_logger, setup_logging
from notification_service.consumers.kafka_consumer import run_notification_consumer

_consumer_task: asyncio.Task | None = None


def _consumer_task_done(task: asyncio.Task) -> None:
    """Surface any exception from the background consumer so it isn't swallowed."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        print(
            f"[notification-service] CONSUMER TASK CRASHED: {exc!r}",
            file=sys.stderr,
            flush=True,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    global _consumer_task
    setup_logging()
    log = get_logger("main")
    log.info("notification_service_starting", port=8005)

    _consumer_task = asyncio.create_task(run_notification_consumer())
    _consumer_task.add_done_callback(_consumer_task_done)

    yield

    if _consumer_task:
        _consumer_task.cancel()
        try:
            await _consumer_task
        except asyncio.CancelledError:
            pass
    log.info("notification_service_shutting_down")


app = FastAPI(
    title="SmartCourse Notification Service",
    description="Handles email, push, and in-app notifications for the SmartCourse platform",
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
# Include routers
app.include_router(router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "notification-service",
    }
