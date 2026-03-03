"""RAG indexing service."""

from ai_service.schemas.index import (
    BuildIndexRequest,
    IndexBuildResponse,
    IndexStatusResponse,
)
from ai_service.schemas.common import IndexStatus


class IndexService:
    """Handles RAG index building and status."""

    async def build_course_index(
        self, course_id: int, request: BuildIndexRequest
    ) -> IndexBuildResponse:
        """Build index for entire course."""
        # TODO: Read all modules/lessons from course_content collection
        # TODO: For each lesson: extract text content or download resource from S3
        # TODO: Chunk content (512 tokens, 10% overlap)
        # TODO: Generate embeddings via OpenAI
        # TODO: Store vectors in Qdrant with metadata (course_id, module_id, lesson_id, etc.)
        # TODO: Update rag_index_status in PostgreSQL
        # TODO: Publish "rag.indexed" or "rag.failed" event to Kafka
        return IndexBuildResponse(
            course_id=course_id,
            status=IndexStatus.PENDING,
        )

    async def build_module_index(
        self, course_id: int, module_id: str, request: BuildIndexRequest
    ) -> IndexBuildResponse:
        """Build index for a single module."""
        # TODO: Same as course-level but for a single module
        return IndexBuildResponse(
            course_id=course_id,
            module_id=module_id,
            status=IndexStatus.PENDING,
        )

    async def get_course_status(self, course_id: int) -> IndexStatusResponse:
        """Get index status for a course."""
        # TODO: Query rag_index_status table
        return IndexStatusResponse(
            course_id=course_id,
            status=IndexStatus.PENDING,
        )

    async def get_module_status(self, course_id: int, module_id: str) -> IndexStatusResponse:
        """Get index status for a module."""
        # TODO: Query rag_index_status table filtered by module
        return IndexStatusResponse(
            course_id=course_id,
            module_id=module_id,
            status=IndexStatus.PENDING,
        )
