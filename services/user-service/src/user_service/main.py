import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core_service.providers.kafka.producer import EventProducer
from user_service.api.router import router
from user_service.config import settings
from user_service.core.database import engine
from user_service.core.redis import close_redis, connect_redis, get_redis
from user_service.models import User, InstructorProfile  # noqa: F401 - register with Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    await connect_redis(settings.REDIS_URL)

    producer = EventProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        service_name="user-service",
        schema_registry_url=settings.SCHEMA_REGISTRY_URL,
    )
    try:
        await producer.start()
        logger.info("Kafka producer connected to %s", settings.KAFKA_BOOTSTRAP_SERVERS)
    except Exception:
        logger.exception("Failed to start Kafka producer — events will be dropped")

    app.state.event_producer = producer

    yield

    await producer.stop()
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
