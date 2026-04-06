"""AI Service main FastAPI application."""

import logging
from contextlib import asynccontextmanager


from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from ai_service.api.router import router
from ai_service.config import settings
from ai_service.core.mongodb import connect_mongodb, close_mongodb
from ai_service.core.redis import connect_redis, close_redis, get_redis
from ai_service.repositories.vector_store import VectorStoreRepository
from ai_service.clients.openai_client import OpenAIClient
from ai_service.core.service_factory import (
    create_index_service,
    create_tutor_service,
    create_instructor_service,
)
from ai_service.api.dependencies import set_index_service, set_tutor_service, set_instructor_service
from ai_service.core.kafka import connect_kafka, close_kafka
from ai_service.patches import pymupdf_images

pymupdf_images.apply()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Module-level reference for cleanup
_vector_store: VectorStoreRepository | None = None


def _initialize_services(vector_store: VectorStoreRepository) -> None:
    """Create and register all service singletons (graphs compiled once at startup)."""
    openai_client = OpenAIClient()

    index_service = create_index_service(openai_client, vector_store)
    set_index_service(index_service)

    tutor_service = create_tutor_service(openai_client, vector_store)
    set_tutor_service(tutor_service)

    instructor_service = create_instructor_service(openai_client)
    set_instructor_service(instructor_service)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    global _vector_store

    await connect_mongodb(settings.MONGODB_URL, settings.MONGODB_DB_NAME)
    await connect_redis(settings.REDIS_URL)
    await connect_kafka(settings.KAFKA_BOOTSTRAP_SERVERS, settings.SCHEMA_REGISTRY_URL)

    # Initialize Qdrant vector store
    _vector_store = VectorStoreRepository()
    await _vector_store.connect()

    _initialize_services(_vector_store)

    logger.info(
        "AI Service startup complete (MongoDB + Redis + Qdrant + Index + Tutor + Instructor)"
    )

    yield

    logger.info("AI Service shutting down")
    if _vector_store:
        await _vector_store.close()
    await close_kafka()
    await close_redis()
    await close_mongodb()


app = FastAPI(
    title="SmartCourse AI Service",
    description="AI-powered content generation, tutoring, and indexing",
    version="0.1.0",
    lifespan=lifespan,
    root_path="/ai-service",
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
