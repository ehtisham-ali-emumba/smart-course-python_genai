"""AI Service main FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ai_service.api.router import router
from ai_service.config import settings
from ai_service.core.mongodb import connect_mongodb, close_mongodb
from ai_service.core.redis import connect_redis, close_redis, get_redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    await connect_mongodb(settings.MONGODB_URL, settings.MONGODB_DB_NAME)
    await connect_redis(settings.REDIS_URL)

    logger.info("AI Service startup complete")
    # TODO: Initialize Kafka producer
    # TODO: Initialize Qdrant client
    # TODO: Initialize LLM client

    yield

    logger.info("AI Service shutting down")
    await close_redis()
    await close_mongodb()


app = FastAPI(
    title="SmartCourse AI Service",
    description="AI-powered content generation, tutoring, and indexing",
    version="0.1.0",
    lifespan=lifespan,
)

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
        "service": "ai-service",
        "dependencies": {
            "redis": "connected" if redis_ok else "disconnected",
        },
    }
