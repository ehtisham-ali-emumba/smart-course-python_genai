"""API dependencies for authentication and authorization."""

from fastapi import HTTPException, Request, status

from ai_service.services.index import IndexService
from ai_service.services.content_extractor import ContentExtractor
from ai_service.services.text_chunker import TextChunker
from ai_service.clients.openai_client import OpenAIClient
from ai_service.repositories.course_content import CourseContentRepository
from ai_service.repositories.vector_store import VectorStoreRepository
from ai_service.clients.resource_extractor import ResourceTextExtractor
from ai_service.services.generation_status import GenerationStatusTracker
from ai_service.core.mongodb import get_mongodb, connect_mongodb, close_mongodb
from ai_service.core.redis import get_redis


def get_current_user_id(request: Request) -> int:
    """Extract user ID from X-User-ID header."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return int(user_id)


def get_current_user_role(request: Request) -> str:
    """Extract user role from X-User-Role header."""
    role = request.headers.get("X-User-Role")
    if not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return role


def require_instructor(request: Request) -> int:
    """Require instructor or admin role."""
    user_id = get_current_user_id(request)
    role = get_current_user_role(request)
    if role not in ("instructor", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Instructor role required",
        )
    return user_id


def require_student(request: Request) -> int:
    """Require student or admin role."""
    user_id = get_current_user_id(request)
    role = get_current_user_role(request)
    if role not in ("student", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student role required",
        )
    return user_id


def get_authenticated_user(request: Request) -> tuple[int, str]:
    """Get authenticated user ID and role."""
    user_id = get_current_user_id(request)
    role = get_current_user_role(request)
    return user_id, role


# Module-level reference for vector store singleton
_vector_store: VectorStoreRepository | None = None


def set_vector_store(vs: VectorStoreRepository) -> None:
    """Called during app startup to set the vector store singleton."""
    global _vector_store
    _vector_store = vs


def get_index_service() -> IndexService:
    """FastAPI dependency that builds IndexService with all its dependencies."""
    db = get_mongodb()
    if db is None:
        raise RuntimeError("MongoDB connection not initialized")
    repo = CourseContentRepository(db)
    resource_extractor = ResourceTextExtractor()
    content_extractor = ContentExtractor(repo, resource_extractor)
    text_chunker = TextChunker()
    openai_client = OpenAIClient()
    redis_client = get_redis()
    status_tracker = GenerationStatusTracker(redis_client)

    return IndexService(
        content_extractor=content_extractor,
        text_chunker=text_chunker,
        openai_client=openai_client,
        vector_store=_vector_store,
        status_tracker=status_tracker,
    )
