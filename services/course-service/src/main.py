import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.router import router
from config import settings
from core.database import engine
from core.mongodb import close_mongodb, connect_mongodb
from core.redis import close_redis, connect_redis, get_redis
from core_service.providers.kafka.producer import EventProducer
from models import Certificate, Course, Enrollment, Progress  # noqa: F401

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    # Connect to MongoDB on startup
    await connect_mongodb()
    # Connect to Redis on startup
    await connect_redis(settings.REDIS_URL)

    producer = EventProducer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        service_name="course-service",
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
        "service": "course-service",
        "dependencies": {
            "redis": "connected" if redis_ok else "disconnected",
        },
    }
