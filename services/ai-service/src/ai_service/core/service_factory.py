"""Centralized service initialization.

Creates all service singletons at startup so that LangGraph compiled graphs
(and other heavy objects) are built exactly once and reused across requests.
"""

import logging

from ai_service.clients.openai_client import OpenAIClient
from ai_service.clients.course_service_client import CourseServiceClient
from ai_service.clients.resource_extractor import ResourceTextExtractor
from ai_service.core.mongodb import get_mongodb
from ai_service.core.redis import get_redis
from ai_service.repositories.course_content import CourseContentRepository
from ai_service.repositories.vector_store import VectorStoreRepository
from ai_service.services.content_extractor import ContentExtractor
from ai_service.services.generation_status import GenerationStatusTracker
from ai_service.services.index import IndexService
from ai_service.services.instructor import InstructorService
from ai_service.services.text_chunker import TextChunker
from ai_service.services.tutor import TutorService

logger = logging.getLogger(__name__)


def create_tutor_service(
    openai_client: OpenAIClient,
    vector_store: VectorStoreRepository,
) -> TutorService:
    """Create TutorService singleton with pre-built tutor graph."""
    logger.info("Creating TutorService (tutor graph compiled once)")
    return TutorService(
        openai_client=openai_client,
        vector_store=vector_store,
    )


def create_index_service(
    openai_client: OpenAIClient,
    vector_store: VectorStoreRepository,
) -> IndexService:
    """Create IndexService singleton with pre-built index graph."""
    db = get_mongodb()
    if db is None:
        raise RuntimeError("MongoDB connection not initialized")

    redis = get_redis()
    if redis is None:
        raise RuntimeError("Redis connection not initialized")

    repo = CourseContentRepository(db)
    resource_extractor = ResourceTextExtractor()
    content_extractor = ContentExtractor(repo, resource_extractor)
    text_chunker = TextChunker()
    status_tracker = GenerationStatusTracker(redis)

    logger.info("Creating IndexService (index graph compiled once)")
    return IndexService(
        content_extractor=content_extractor,
        text_chunker=text_chunker,
        openai_client=openai_client,
        vector_store=vector_store,
        status_tracker=status_tracker,
    )


def create_instructor_service(
    openai_client: OpenAIClient,
) -> InstructorService:
    """Create InstructorService singleton with pre-built quiz & summary graphs."""
    db = get_mongodb()
    if db is None:
        raise RuntimeError("MongoDB connection not initialized")

    redis = get_redis()
    if redis is None:
        raise RuntimeError("Redis connection not initialized")

    repo = CourseContentRepository(db)
    resource_extractor = ResourceTextExtractor()
    content_extractor = ContentExtractor(repo, resource_extractor)
    course_client = CourseServiceClient()
    status_tracker = GenerationStatusTracker(redis)

    logger.info("Creating InstructorService (quiz + summary graphs compiled once)")
    return InstructorService(
        repo=repo,
        openai_client=openai_client,
        course_client=course_client,
        content_extractor=content_extractor,
        status_tracker=status_tracker,
    )
