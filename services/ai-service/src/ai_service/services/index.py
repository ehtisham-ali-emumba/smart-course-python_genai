"""RAG indexing service — builds vector index from course content."""

import asyncio
import uuid as _uuid
import structlog
from datetime import datetime, timezone
from fastapi import HTTPException

from ai_service.services.content_pipeline.content_extractor import ContentExtractor
from ai_service.services.content_pipeline.text_chunker import TextChunker
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
        self.vector_store = vector_store
        self.status_tracker = status_tracker

        # Compile the graph once — reused for every invocation
        self._index_graph = build_index_graph(
            content_extractor=content_extractor,
            text_chunker=text_chunker,
            openai_client=openai_client,
            vector_store=vector_store,
        )

    async def _invoke_module_index_graph(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        force_rebuild: bool,
    ) -> tuple[int, str | None]:
        """Invoke the LangGraph indexing pipeline for a single module.

        Content extraction happens inside the graph now.

        Returns:
            Tuple of (chunks_stored, error_message).
        """
        log = logger.bind(course_id=course_id, module_id=module_id)

        try:
            result = await self._index_graph.ainvoke(
                IndexState(
                    course_id=course_id,
                    module_id=module_id,
                    force_rebuild=force_rebuild,
                )
            )

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

        if await self.status_tracker.is_running(course_id, "course", "index"):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Course indexing is already in progress. " "Check status endpoint for updates."
                ),
            )

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

        if await self.status_tracker.is_running(course_id, module_id, "index"):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Module indexing is already in progress. " "Check status endpoint for updates."
                ),
            )

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

            # Fetch course structure (just module IDs — content extraction is inside the graph)
            course_data = await self.content_extractor.fetch_course_data(course_id)
            if not course_data:
                await self.status_tracker.set_failed(
                    course_id, "course", "index", "Course not found"
                )
                return

            total_chunks = 0
            for module_data in course_data["modules"]:
                chunks_stored, error = await self._invoke_module_index_graph(
                    course_id=course_id,
                    module_id=module_data["module_id"],
                    force_rebuild=force_rebuild,
                )
                if not error:
                    total_chunks += chunks_stored

            await self.status_tracker.set_completed(course_id, "course", "index")
            log.info(
                "Course index build completed",
                total_chunks=total_chunks,
                total_modules=len(course_data["modules"]),
            )

        except Exception as e:
            log.exception("Course index build failed", error=str(e))
            await self.status_tracker.set_failed(course_id, "course", "index", str(e))

    async def _build_module_index_task(self, course_id: _uuid.UUID, module_id: str) -> None:
        """Background task: index a single module using LangGraph."""
        log = logger.bind(course_id=course_id, module_id=module_id)
        try:
            await self.status_tracker.set_in_progress(course_id, module_id, "index")

            chunks_stored, error = await self._invoke_module_index_graph(
                course_id=course_id,
                module_id=module_id,
                force_rebuild=True,
            )

            if error:
                await self.status_tracker.set_failed(course_id, module_id, "index", error)
            else:
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
