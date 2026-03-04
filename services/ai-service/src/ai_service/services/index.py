"""RAG indexing service — builds vector index from course content."""

import asyncio
import structlog
from datetime import datetime, timezone

from ai_service.services.content_extractor import ContentExtractor
from ai_service.services.text_chunker import TextChunker
from ai_service.clients.openai_client import OpenAIClient
from ai_service.repositories.vector_store import VectorStoreRepository
from ai_service.services.generation_status import GenerationStatusTracker
from ai_service.schemas.index import (
    BuildIndexRequest,
    IndexBuildResponse,
    IndexStatusResponse,
)
from ai_service.schemas.common import IndexStatus
from ai_service.config import settings

logger = structlog.get_logger(__name__)

# Max texts per OpenAI embedding batch
EMBEDDING_BATCH_SIZE = 100


class IndexService:
    """Handles RAG index building and status tracking."""

    def __init__(
        self,
        content_extractor: ContentExtractor,
        text_chunker: TextChunker,
        openai_client: OpenAIClient,
        vector_store: VectorStoreRepository,
        status_tracker: GenerationStatusTracker,
    ):
        self.content_extractor = content_extractor
        self.text_chunker = text_chunker
        self.openai_client = openai_client
        self.vector_store = vector_store
        self.status_tracker = status_tracker

    async def build_course_index(
        self, course_id: int, request: BuildIndexRequest
    ) -> IndexBuildResponse:
        """Trigger index build for an entire course (background task)."""
        log = logger.bind(course_id=course_id)
        log.info("Course index build requested", force_rebuild=request.force_rebuild)

        # Fire background task
        asyncio.create_task(self._build_course_index_task(course_id, request.force_rebuild))

        return IndexBuildResponse(
            course_id=course_id,
            status=IndexStatus.PENDING,
            message="Course index build started. Poll the status endpoint to track progress.",
            requested_at=datetime.now(timezone.utc),
        )

    async def build_module_index(
        self, course_id: int, module_id: str, request: BuildIndexRequest
    ) -> IndexBuildResponse:
        """Trigger index build for a single module (background task)."""
        log = logger.bind(course_id=course_id, module_id=module_id)
        log.info("Module index build requested", force_rebuild=request.force_rebuild)

        asyncio.create_task(
            self._build_module_index_task(course_id, module_id, request.force_rebuild)
        )

        return IndexBuildResponse(
            course_id=course_id,
            module_id=module_id,
            status=IndexStatus.PENDING,
            message="Module index build started. Poll the status endpoint to track progress.",
            requested_at=datetime.now(timezone.utc),
        )

    async def _build_course_index_task(self, course_id: int, force_rebuild: bool) -> None:
        """Background task: index all modules in a course."""
        log = logger.bind(course_id=course_id)
        try:
            await self.status_tracker.set_in_progress(course_id, "course", "index")

            # If force rebuild, delete existing vectors first
            if force_rebuild:
                log.info("Force rebuild: deleting existing course vectors")
                await self.vector_store.delete_course_vectors(course_id)

            # Extract all course content
            course_content = await self.content_extractor.extract_course_content(course_id)
            if not course_content:
                await self.status_tracker.set_failed(
                    course_id, "course", "index", "Course not found in MongoDB"
                )
                return

            total_chunks = 0

            for module_data in course_content["modules"]:
                module_id = module_data["module_id"]
                module_title = module_data["module_title"]

                # If force rebuild, module vectors already deleted above
                if not force_rebuild:
                    # Delete only this module's vectors before re-indexing
                    await self.vector_store.delete_module_vectors(course_id, module_id)

                chunks_stored = await self._index_module_lessons(
                    course_id=course_id,
                    module_id=module_id,
                    module_title=module_title,
                    lesson_texts=module_data["lesson_texts"],
                    lessons=module_data["lessons"],
                )
                total_chunks += chunks_stored

            await self.status_tracker.set_completed(course_id, "course", "index")
            log.info(
                "Course index build completed",
                total_chunks=total_chunks,
                total_modules=len(course_content["modules"]),
            )

        except Exception as e:
            log.exception("Course index build failed", error=str(e))
            await self.status_tracker.set_failed(course_id, "course", "index", str(e))

    async def _build_module_index_task(
        self, course_id: int, module_id: str, force_rebuild: bool
    ) -> None:
        """Background task: index a single module."""
        log = logger.bind(course_id=course_id, module_id=module_id)
        try:
            await self.status_tracker.set_in_progress(course_id, module_id, "index")

            # Delete existing module vectors
            await self.vector_store.delete_module_vectors(course_id, module_id)

            # Extract module content
            module_content = await self.content_extractor.extract_module_content(
                course_id, module_id
            )
            if not module_content:
                await self.status_tracker.set_failed(
                    course_id, module_id, "index", "Module not found in MongoDB"
                )
                return

            chunks_stored = await self._index_module_lessons(
                course_id=course_id,
                module_id=module_id,
                module_title=module_content["module_title"],
                lesson_texts=module_content["lesson_texts"],
                lessons=module_content["lessons"],
            )

            await self.status_tracker.set_completed(course_id, module_id, "index")
            log.info("Module index build completed", chunks_stored=chunks_stored)

        except Exception as e:
            log.exception("Module index build failed", error=str(e))
            await self.status_tracker.set_failed(course_id, module_id, "index", str(e))

    async def _index_module_lessons(
        self,
        course_id: int,
        module_id: str,
        module_title: str,
        lesson_texts: dict[str, str],
        lessons: list[dict],
    ) -> int:
        """Chunk, embed, and store vectors for all lessons in a module.

        Returns total chunks stored.
        """
        # Build lesson_id → title mapping
        lesson_title_map = {lesson["lesson_id"]: lesson.get("title", "") for lesson in lessons}

        total_stored = 0

        for lesson_id, text in lesson_texts.items():
            lesson_title = lesson_title_map.get(lesson_id, "")

            # 1. Chunk the text
            chunks = self.text_chunker.chunk_text(text)
            if not chunks:
                continue

            # 2. Embed all chunks (batch for efficiency)
            chunk_texts = [c.text for c in chunks]
            embeddings = await self._embed_in_batches(chunk_texts)

            # 3. Build chunk records for Qdrant
            chunk_records = [
                {
                    "text": chunk.text,
                    "embedding": embedding,
                    "chunk_index": chunk.chunk_index,
                    "lesson_title": lesson_title,
                    "module_title": module_title,
                }
                for chunk, embedding in zip(chunks, embeddings)
            ]

            # 4. Store in Qdrant
            stored = await self.vector_store.upsert_chunks(
                course_id=course_id,
                module_id=module_id,
                lesson_id=lesson_id,
                chunks=chunk_records,
            )
            total_stored += stored

        return total_stored

    async def _embed_in_batches(self, texts: list[str]) -> list[list[float]]:
        """Embed texts in batches to avoid API limits.

        Args:
            texts: List of text strings.

        Returns:
            List of embedding vectors matching input order.
        """
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = texts[i : i + EMBEDDING_BATCH_SIZE]
            batch_embeddings = await self.openai_client.embed_texts(batch)
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    async def get_course_status(self, course_id: int) -> IndexStatusResponse:
        """Get index status for a course."""
        # Check Redis for in-flight status
        redis_status = await self.status_tracker.get_status(course_id, "course", "index")

        if redis_status:
            status = IndexStatus(self._map_generation_to_index_status(redis_status["status"]))
            error_message = redis_status.get("error")
            last_build_at = (
                datetime.fromisoformat(redis_status["completed_at"])
                if redis_status.get("completed_at")
                else None
            )
        else:
            # Fallback: check if vectors exist in Qdrant
            count = await self.vector_store.count_course_vectors(course_id)
            if count > 0:
                status = IndexStatus.INDEXED
                last_build_at = None  # Unknown when it was built
            else:
                status = IndexStatus.PENDING
                last_build_at = None
            error_message = None

        # Get total chunks from Qdrant
        total_chunks = await self.vector_store.count_course_vectors(course_id)

        return IndexStatusResponse(
            course_id=course_id,
            status=status,
            total_chunks=total_chunks,
            embedding_model=settings.OPENAI_EMBEDDING_MODEL,
            last_build_at=last_build_at,
            error_message=error_message,
            message=(
                f"Index has {total_chunks} chunks." if total_chunks > 0 else "Index not built yet."
            ),
        )

    async def get_module_status(self, course_id: int, module_id: str) -> IndexStatusResponse:
        """Get index status for a module."""
        redis_status = await self.status_tracker.get_status(course_id, module_id, "index")

        if redis_status:
            status = IndexStatus(self._map_generation_to_index_status(redis_status["status"]))
            error_message = redis_status.get("error")
        else:
            status = IndexStatus.PENDING
            error_message = None

        return IndexStatusResponse(
            course_id=course_id,
            module_id=module_id,
            status=status,
            embedding_model=settings.OPENAI_EMBEDDING_MODEL,
            error_message=error_message,
            message="Check the course-level status for aggregate chunk count.",
        )

    @staticmethod
    def _map_generation_to_index_status(gen_status: str) -> str:
        """Map GenerationStatus values to IndexStatus values."""
        mapping = {
            "pending": "pending",
            "in_progress": "indexing",
            "completed": "indexed",
            "failed": "failed",
        }
        return mapping.get(gen_status, "pending")
