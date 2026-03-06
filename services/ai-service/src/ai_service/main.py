"""AI Service main FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ai_service.api.router import router
from ai_service.config import settings
from ai_service.core.mongodb import connect_mongodb, close_mongodb
from ai_service.core.redis import connect_redis, close_redis, get_redis
from ai_service.repositories.vector_store import VectorStoreRepository
from ai_service.services.tutor import TutorService
from ai_service.clients.openai_client import OpenAIClient
from ai_service.api.dependencies import set_vector_store, set_tutor_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Module-level reference for cleanup
_vector_store: VectorStoreRepository | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    global _vector_store

    await connect_mongodb(settings.MONGODB_URL, settings.MONGODB_DB_NAME)
    await connect_redis(settings.REDIS_URL)

    # Initialize Qdrant vector store
    _vector_store = VectorStoreRepository()
    await _vector_store.connect()
    set_vector_store(_vector_store)

    # Initialize Tutor Service (singleton — holds session state)
    openai_client = OpenAIClient()
    tutor_service = TutorService(
        openai_client=openai_client,
        vector_store=_vector_store,
    )
    set_tutor_service(tutor_service)

    logger.info("AI Service startup complete (MongoDB + Redis + Qdrant + Tutor)")

    yield

    logger.info("AI Service shutting down")
    if _vector_store:
        await _vector_store.close()
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

    qdrant_ok = False
    if _vector_store and _vector_store.client:
        try:
            await _vector_store.client.get_collections()
            qdrant_ok = True
        except Exception:
            pass

    return {
        "status": "ok",
        "service": "ai-service",
        "dependencies": {
            "redis": "connected" if redis_ok else "disconnected",
            "qdrant": "connected" if qdrant_ok else "disconnected",
        },
    }
