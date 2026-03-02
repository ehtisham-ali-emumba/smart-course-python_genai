"""
AI activities for the CoursePublishWorkflow.

DummyAIService is a placeholder for the real AI service (Week 3).
It demonstrates the interface that the real AI service must implement.

Real implementation will:
  - Use OpenAI text-embedding-3-small (or Ollama) for embeddings
  - Store vectors in Qdrant or pgvector
  - Expose a proper AI microservice on port 8009
"""

import logging
import random
from dataclasses import dataclass, field

from temporalio import activity

from core_service.config import core_settings
from core_service.temporal.activities.http_client import get_json

logger = logging.getLogger(__name__)

COURSE_SERVICE = core_settings.COURSE_SERVICE_URL


# ─────────────────────────────────────────────────────────────────────────────
# Dummy AI Service
# Replace this entire class in Week 3 with a real HTTP call to ai-service:8009
# ─────────────────────────────────────────────────────────────────────────────


class DummyAIService:
    """
    Mock AI service for RAG generation.

    In Week 3, this becomes real:
      - Embeddings: POST http://ai-service:8009/api/v1/rag/embed
      - Store:      POST http://ai-service:8009/api/v1/rag/index
      - Status:     GET  http://ai-service:8009/api/v1/rag/{course_id}/status

    The in-memory _rag_store is module-level so it persists for the worker process lifetime.
    It is NOT durable — only for demo purposes.
    """

    _rag_store: dict[int, dict] = {}

    def chunk_text(self, content: dict) -> list[str]:
        """
        Simple text chunking: split course content into chunks by module/lesson.
        In real implementation, this would use proper text splitting with overlap.
        """
        chunks = []
        modules = content.get("modules", [])

        for module in modules:
            module_title = module.get("title", "Module")
            chunks.append(f"Module: {module_title}")

            lessons = module.get("lessons", [])
            for lesson in lessons:
                lesson_title = lesson.get("title", "Lesson")
                lesson_content = lesson.get("content", "")
                # Simple chunking: title + first 500 chars of content
                chunk = f"Lesson: {lesson_title}\n{lesson_content[:500]}"
                chunks.append(chunk)

        # If no modules, chunk the whole content
        if not chunks:
            full_content = str(content)
            chunk_size = 1000
            for i in range(0, len(full_content), chunk_size):
                chunks.append(full_content[i : i + chunk_size])

        return chunks

    def generate_embeddings(self, chunks: list[str]) -> list[list[float]]:
        """
        Generate fake embeddings for demo.
        In real implementation: call OpenAI API or local Ollama.
        """
        embeddings = []
        for chunk in chunks:
            # Generate random 1536-dim embedding (OpenAI ada-002 size)
            embedding = [random.uniform(-1.0, 1.0) for _ in range(1536)]
            embeddings.append(embedding)
        return embeddings

    def store_index(
        self, course_id: int, chunks: list[str], embeddings: list[list[float]]
    ) -> dict:
        """
        Store in in-memory dict for demo.
        In real implementation: store in Qdrant/pgvector via AI service.
        """
        self._rag_store[course_id] = {
            "status": "indexed",
            "chunk_count": len(chunks),
            "embedding_dim": len(embeddings[0]) if embeddings else 0,
            "chunks": chunks[:5],  # Store first 5 chunks for demo
            "embeddings": embeddings[:5],  # Store first 5 embeddings
        }
        return self._rag_store[course_id]

    def get_index_status(self, course_id: int) -> str:
        """Check if a course is already indexed."""
        entry = self._rag_store.get(course_id)
        return entry["status"] if entry else "not_indexed"


# Module-level singleton — shared across all activity executions in this worker
_ai_service = DummyAIService()


# ─────────────────────────────────────────────────────────────────────────────
# Data classes for Course Publish Workflow activities
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ValidateCoursePublishInput:
    course_id: int
    instructor_id: int


@dataclass
class ValidateCoursePublishOutput:
    is_valid: bool
    course_id: int
    title: str = ""
    has_content: bool = False
    module_count: int = 0
    reason: str | None = None


@dataclass
class FetchCourseContentForRagInput:
    course_id: int
    instructor_id: int


@dataclass
class FetchCourseContentForRagOutput:
    success: bool
    course_id: int
    content: dict | None = None
    module_count: int = 0
    error: str | None = None


@dataclass
class GenerateRagEmbeddingsInput:
    course_id: int
    content: dict


@dataclass
class GenerateRagEmbeddingsOutput:
    success: bool
    course_id: int
    chunks: list[str] = field(default_factory=list)
    embeddings: list[list[float]] = field(default_factory=list)
    chunks_processed: int = 0
    error: str | None = None


@dataclass
class StoreRagIndexInput:
    course_id: int
    chunks: list[str]
    embeddings: list[list[float]]


@dataclass
class StoreRagIndexOutput:
    success: bool
    index_id: str | None = None
    chunk_count: int = 0
    error: str | None = None


@dataclass
class FetchEnrolledStudentsInput:
    course_id: int
    instructor_id: int


@dataclass
class FetchEnrolledStudentsOutput:
    success: bool
    course_id: int
    student_ids: list[int] = field(default_factory=list)
    count: int = 0
    error: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Activities
# ─────────────────────────────────────────────────────────────────────────────


@activity.defn(name="validate_course_for_publishing")
async def validate_course_for_publishing(
    input: ValidateCoursePublishInput,
) -> ValidateCoursePublishOutput:
    """
    Verify the course exists, is published, and has at least one module of content.
    Calls:
      - GET http://course-service:8002/api/v1/courses/{course_id}
      - GET http://course-service:8002/api/v1/courses/{course_id}/content
    """
    try:
        # Step A: verify course record
        course_url = f"{COURSE_SERVICE}/courses/{input.course_id}"
        course_data = await get_json(course_url)

        if course_data.get("status") != "published":
            return ValidateCoursePublishOutput(
                is_valid=False,
                course_id=input.course_id,
                reason=f"Course status is {course_data.get('status')}, not published",
            )

        # Step B: verify course has content
        content_url = f"{COURSE_SERVICE}/courses/{input.course_id}/content"
        headers = {"X-User-ID": str(input.instructor_id), "X-User-Role": "instructor"}
        content_data = await get_json(content_url, headers=headers)

        modules = content_data.get("modules", [])
        if not modules:
            return ValidateCoursePublishOutput(
                is_valid=False,
                course_id=input.course_id,
                reason="Course has no content modules",
            )

        return ValidateCoursePublishOutput(
            is_valid=True,
            course_id=input.course_id,
            title=course_data.get("title", ""),
            has_content=True,
            module_count=len(modules),
        )

    except Exception as e:
        logger.error("validate_course_for_publishing failed: %s", e)
        raise  # Let Temporal retry


@activity.defn(name="fetch_course_content_for_rag")
async def fetch_course_content_for_rag(
    input: FetchCourseContentForRagInput,
) -> FetchCourseContentForRagOutput:
    """
    Fetch full course content from course-service for RAG chunking.
    GET http://course-service:8002/api/v1/courses/{course_id}/content
    """
    url = f"{COURSE_SERVICE}/courses/{input.course_id}/content"
    headers = {"X-User-ID": str(input.instructor_id), "X-User-Role": "instructor"}

    try:
        data = await get_json(url, headers=headers)
        modules = data.get("modules", [])
        return FetchCourseContentForRagOutput(
            success=True,
            course_id=input.course_id,
            content=data,
            module_count=len(modules),
        )
    except Exception as e:
        logger.warning(
            "fetch_course_content_for_rag failed for course %d: %s", input.course_id, e
        )
        return FetchCourseContentForRagOutput(
            success=False, course_id=input.course_id, error=str(e)
        )


@activity.defn(name="generate_rag_embeddings")
async def generate_rag_embeddings(
    input: GenerateRagEmbeddingsInput,
) -> GenerateRagEmbeddingsOutput:
    """
    Chunk course content and generate embeddings using DummyAIService.

    WEEK 3 UPGRADE PATH:
      Replace DummyAIService call with HTTP POST to ai-service:8009/api/v1/rag/embed
      Payload: { chunks: string[] }
      Response: { embeddings: [[float]] }
    """
    if not input.content:
        return GenerateRagEmbeddingsOutput(
            success=False,
            course_id=input.course_id,
            error="No content provided",
        )

    try:
        chunks = _ai_service.chunk_text(input.content)
        embeddings = _ai_service.generate_embeddings(chunks)
        return GenerateRagEmbeddingsOutput(
            success=True,
            course_id=input.course_id,
            chunks=chunks,
            embeddings=embeddings,
            chunks_processed=len(chunks),
        )
    except Exception as e:
        logger.error(
            "generate_rag_embeddings failed for course %d: %s", input.course_id, e
        )
        return GenerateRagEmbeddingsOutput(
            success=False, course_id=input.course_id, error=str(e)
        )


@activity.defn(name="store_rag_index")
async def store_rag_index(input: StoreRagIndexInput) -> StoreRagIndexOutput:
    """
    Store the embeddings/index using DummyAIService.

    WEEK 3 UPGRADE PATH:
      Replace with HTTP POST to ai-service:8009/api/v1/rag/index
      Payload: { course_id, chunks, embeddings }
      Response: { index_id, chunk_count, status }
    """
    try:
        result = _ai_service.store_index(
            input.course_id, input.chunks, input.embeddings
        )
        return StoreRagIndexOutput(
            success=True,
            index_id=f"dummy-{input.course_id}",
            chunk_count=result["chunk_count"],
        )
    except Exception as e:
        logger.error("store_rag_index failed for course %d: %s", input.course_id, e)
        return StoreRagIndexOutput(success=False, error=str(e))


@activity.defn(name="fetch_enrolled_students")
async def fetch_enrolled_students(
    input: FetchEnrolledStudentsInput,
) -> FetchEnrolledStudentsOutput:
    """
    GET http://course-service:8002/api/v1/enrollments/course/{course_id}/active-students
    Returns the list of active student IDs to notify.
    (This endpoint is added to course-service in Section 3.2)
    """
    url = (
        f"{COURSE_SERVICE}/course/enrollments/course/{input.course_id}/active-students"
    )
    headers = {"X-User-ID": str(input.instructor_id), "X-User-Role": "instructor"}

    try:
        data = await get_json(url, headers=headers)
        student_ids = data.get("student_ids", [])
        return FetchEnrolledStudentsOutput(
            success=True,
            course_id=input.course_id,
            student_ids=student_ids,
            count=len(student_ids),
        )
    except Exception as e:
        logger.warning(
            "fetch_enrolled_students failed for course %d: %s", input.course_id, e
        )
        return FetchEnrolledStudentsOutput(
            success=False, course_id=input.course_id, error=str(e)
        )


AI_ACTIVITIES = [
    validate_course_for_publishing,
    fetch_course_content_for_rag,
    generate_rag_embeddings,
    store_rag_index,
    fetch_enrolled_students,
]

__all__ = [
    "validate_course_for_publishing",
    "fetch_course_content_for_rag",
    "generate_rag_embeddings",
    "store_rag_index",
    "fetch_enrolled_students",
    "DummyAIService",
    "ValidateCoursePublishInput",
    "ValidateCoursePublishOutput",
    "FetchCourseContentForRagInput",
    "FetchCourseContentForRagOutput",
    "GenerateRagEmbeddingsInput",
    "GenerateRagEmbeddingsOutput",
    "StoreRagIndexInput",
    "StoreRagIndexOutput",
    "FetchEnrolledStudentsInput",
    "FetchEnrolledStudentsOutput",
    "AI_ACTIVITIES",
]
