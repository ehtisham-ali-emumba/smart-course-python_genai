import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from analytics_service.api.router import router
from analytics_service.config import settings
from analytics_service.consumers.consumer_manager import ConsumerManager
from analytics_service.core.database import AsyncSessionLocal, engine
from analytics_service.core.redis import close_redis, connect_redis, get_redis
from analytics_service.models import (  # noqa: F401
    AIUsageDaily,
    CourseMetrics,
    EnrollmentDaily,
    InstructorMetrics,
    PlatformSnapshot,
    ProcessedEvent,
    StudentMetrics,
)
from analytics_service.services.snapshot_service import SnapshotService


async def daily_snapshot_loop(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        now = datetime.now(timezone.utc)
        next_run = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
        sleep_seconds = max((next_run - now).total_seconds(), 60)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=sleep_seconds)
            break
        except TimeoutError:
            pass

        async with AsyncSessionLocal() as session:
            service = SnapshotService(session)
            await service.build_daily_snapshot(date.today())


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_redis(settings.REDIS_URL)

    consumer_manager = ConsumerManager(AsyncSessionLocal)
    await consumer_manager.start()
    app.state.consumer_manager = consumer_manager

    stop_event = asyncio.Event()
    snapshot_task = asyncio.create_task(daily_snapshot_loop(stop_event))
    app.state.snapshot_stop_event = stop_event
    app.state.snapshot_task = snapshot_task

    yield

    stop_event.set()
    snapshot_task.cancel()
    await consumer_manager.stop()
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title="SmartCourse Analytics Service",
    description="Read-optimized analytics APIs backed by materialized metrics",
    version="0.1.0",
    lifespan=lifespan,
)

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

app.include_router(router)


@app.get("/health")
async def health_check():
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
        "service": "analytics-service",
        "dependencies": {
            "redis": "connected" if redis_ok else "disconnected",
        },
    }
