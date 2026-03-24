"""RAG indexing service — builds vector index from course content."""

import asyncio
import uuid as _uuid
import structlog
from datetime import datetime, timezone

from ai_service.services.content_extractor import ContentExtractor
from ai_service.services.text_chunker import TextChunker
from ai_service.clients.openai_client import OpenAIClient
from ai_service.repositories.vector_store import VectorStoreRepository
from ai_service.services.generation_status import GenerationStatusTracker
from ai_service.services.index_graph import build_index_graph, IndexState
from ai_service.schemas.index import (
    BuildIndexRequest,
    IndexBuildResponse,
    IndexStatusResponse,
)
from ai_service.schemas.common import IndexStatus
from ai_service.config import settings

logger = structlog.get_logger(__name__)


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

        # Compile the graph once — reused for every invocation
        self._index_graph = build_index_graph(
            text_chunker=text_chunker,
            openai_client=openai_client,
            vector_store=vector_store,
        )

    async def _invoke_module_index_graph(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        module_title: str,
        lesson_texts: dict[str, str],
        lessons: list[dict],
        force_rebuild: bool,
    ) -> tuple[int, str | None]:
        """Invoke the LangGraph indexing pipeline for a single module.

        Args:
            course_id: Course ID.
            module_id: Module ID.
            module_title: Module title.
            lesson_texts: Dict of lesson_id → text content.
            lessons: List of lesson metadata dicts.
            force_rebuild: Whether this is a force rebuild.

        Returns:
            Tuple of (chunks_stored, error_message).
            If successful, error_message is None.
            If failed, chunks_stored is 0 and error_message contains the error.
        """
        log = logger.bind(course_id=course_id, module_id=module_id)

        try:
            result = await self._index_graph.ainvoke(
                IndexState(
                    course_id=course_id,
                    module_id=module_id,
                    module_title=module_title,
                    lesson_texts=lesson_texts,
                    lessons=lessons,
                    force_rebuild=force_rebuild,
                )
            )

            # Check for graph-level errors
            if result.get("error"):
                error_msg = result["error"]
                log.error("Module indexing failed in graph", error=error_msg)
                return 0, error_msg

            chunks_stored = result.get("total_chunks_stored", 0)
            log.info("Module indexing succeeded", chunks_stored=chunks_stored)
            return chunks_stored, None

        except Exception as e:
            error_msg = f"Module indexing error: {str(e)}"
            log.exception("Module indexing exception", error=str(e))
            return 0, error_msg

    async def build_course_index(
        self, course_id: _uuid.UUID, request: BuildIndexRequest
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

    async def build_module_index(self, course_id: _uuid.UUID, module_id: str) -> IndexBuildResponse:
        """Trigger index build for a single module (background task)."""
        log = logger.bind(course_id=course_id, module_id=module_id)
        log.info("Module index build requested")

        asyncio.create_task(self._build_module_index_task(course_id, module_id))

        return IndexBuildResponse(
            course_id=course_id,
            module_id=module_id,
            status=IndexStatus.PENDING,
            message="Module index build started. Poll the status endpoint to track progress.",
            requested_at=datetime.now(timezone.utc),
        )

    async def _build_course_index_task(self, course_id: _uuid.UUID, force_rebuild: bool) -> None:
        """Background task: index all modules in a course using LangGraph."""
        log = logger.bind(course_id=course_id)
        try:
            await self.status_tracker.set_in_progress(course_id, "course", "index")

            # Extract all course content
            course_content = await self.content_extractor.extract_course_content(course_id)
            if not course_content:
                await self.status_tracker.set_failed(
                    course_id, "course", "index", "Course not found in MongoDB"
                )
                return

            total_chunks = 0

            # Run the LangGraph pipeline for each module
            # Each module's cleanup node respects the force_rebuild flag
            for module_data in course_content["modules"]:
                chunks_stored, error = await self._invoke_module_index_graph(
                    course_id=course_id,
                    module_id=module_data["module_id"],
                    module_title=module_data["module_title"],
                    lesson_texts=module_data["lesson_texts"],
                    lessons=module_data["lessons"],
                    force_rebuild=force_rebuild,
                )

                if error:
                    # Continue with other modules — don't fail the whole course
                    continue

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

    async def _build_module_index_task(self, course_id: _uuid.UUID, module_id: str) -> None:
        """Background task: index a single module using LangGraph."""
        log = logger.bind(course_id=course_id, module_id=module_id)
        try:
            await self.status_tracker.set_in_progress(course_id, module_id, "index")

            # Extract module content
            module_content = await self.content_extractor.extract_module_content(
                course_id, module_id
            )
            if not module_content:
                await self.status_tracker.set_failed(
                    course_id, module_id, "index", "Module not found in MongoDB"
                )
                return

            # Run the LangGraph pipeline via centralized helper
            # Module endpoint always deletes existing vectors (force_rebuild=True)
            chunks_stored, error = await self._invoke_module_index_graph(
                course_id=course_id,
                module_id=module_id,
                module_title=module_content["module_title"],
                lesson_texts=module_content["lesson_texts"],
                lessons=module_content["lessons"],
                force_rebuild=True,
            )

            if error:
                await self.status_tracker.set_failed(course_id, module_id, "index", error)
                return

            await self.status_tracker.set_completed(course_id, module_id, "index")
            log.info("Module index build completed", chunks_stored=chunks_stored)

        except Exception as e:
            log.exception("Module index build failed", error=str(e))
            await self.status_tracker.set_failed(course_id, module_id, "index", str(e))

    async def get_course_status(self, course_id: _uuid.UUID) -> IndexStatusResponse:
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

    async def get_module_status(self, course_id: _uuid.UUID, module_id: str) -> IndexStatusResponse:
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
