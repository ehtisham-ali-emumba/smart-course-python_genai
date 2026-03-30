"""LangGraph-powered RAG indexing pipeline.

Implements a multi-node state machine for course content indexing:
  cleanup_vectors → chunk_texts → embed_chunks → store_vectors → END

Each node handles one stage of the pipeline. Conditional edges route to END
on errors, preventing wasted work downstream.

Follows the same closure/factory pattern as tutor_agent.py and instructor_graphs.py.
"""

import asyncio
from ai_service.rate_limiters import EMBEDDING_SEMAPHORE
import uuid as _uuid
import structlog
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from ai_service.services.content_pipeline.text_chunker import TextChunker
from ai_service.services.content_pipeline.content_extractor import ContentExtractor
from ai_service.services.content_pipeline.pdf_processor import build_pdf_extraction_node
from ai_service.services.content_pipeline.audio_processor import build_audio_extraction_node
from ai_service.clients.openai_client import OpenAIClient
from ai_service.repositories.vector_store import VectorStoreRepository

logger = structlog.get_logger(__name__)

# ── Configuration ──────────────────────────────────────────────────

EMBEDDING_BATCH_SIZE = 100


# ── State ──────────────────────────────────────────────────────────


class IndexState(BaseModel):
    """State flowing through the indexing pipeline."""

    # ── Required Input ──
    course_id: _uuid.UUID
    module_id: str
    force_rebuild: bool
    source_lesson_ids: list[str] | None = None

    # ── Set by extraction nodes (no longer required as input) ──
    lessons: list[dict] = Field(default_factory=list)
    module_title: str = ""
    pdf_texts: dict[str, str] = Field(default_factory=dict)
    audio_texts: dict[str, str] = Field(default_factory=dict)
    video_texts: dict[str, str] = Field(default_factory=dict)  # NEW
    combined_text: str = ""
    lesson_texts: dict[str, str] = Field(default_factory=dict)

    # ── Intermediate (set by nodes) ──
    lesson_chunks: dict[str, list[dict]] = Field(default_factory=dict)
    lesson_embeddings: dict[str, list[list[float]]] = Field(default_factory=dict)
    total_chunks_stored: int = 0

    # ── Output / Error ──
    error: str | None = None
    completed: bool = False

    class Config:
        """Pydantic config."""

        arbitrary_types_allowed = True


# ── Node: Fetch Lessons ────────────────────────────────────────────


def _build_fetch_lessons_node(content_extractor: ContentExtractor):
    """Fetch lesson metadata from MongoDB before PDF extraction."""

    async def fetch_lessons(state: IndexState) -> dict:
        log = logger.bind(course_id=state.course_id, module_id=state.module_id)
        log.info("[FETCH_LESSONS] Loading from MongoDB")
        try:
            module_data = await content_extractor.fetch_module_data(
                state.course_id, state.module_id, state.source_lesson_ids
            )
            if not module_data:
                return {"error": "Module not found"}
            return {
                "lessons": module_data["lessons"],
                "module_title": module_data["module_title"],
            }
        except Exception as e:
            log.exception("[FETCH_LESSONS] Error", error=str(e))
            return {"error": str(e)}

    return fetch_lessons


# ── Node: Merge Content ────────────────────────────────────────────


def _build_merge_content_node(content_extractor: ContentExtractor):
    """Merge MongoDB text + PDF/audio/video text into lesson_texts for chunking."""

    async def merge_content(state: IndexState) -> dict:
        audio_texts = state.audio_texts
        video_texts = state.video_texts
        lesson_texts = ContentExtractor.build_lesson_texts(
            state.lessons, state.pdf_texts, audio_texts, video_texts
        )
        if not lesson_texts:
            return {"error": "No content to index after merging"}
        return {"lesson_texts": lesson_texts}

    return merge_content


# ── Node: Cleanup Vectors ──────────────────────────────────────────


def _build_cleanup_node(vector_store: VectorStoreRepository):
    """Delete existing vectors for the module before re-indexing."""

    async def cleanup_vectors(state: IndexState) -> dict:
        course_id = state.course_id
        module_id = state.module_id
        force_rebuild = state.force_rebuild

        log = logger.bind(course_id=course_id, module_id=module_id)

        # Only delete vectors if force_rebuild is True
        if not force_rebuild:
            log.info("[CLEANUP] Skipping vector deletion (force_rebuild=False)")
            return {}

        log.info("[CLEANUP] Deleting existing module vectors (force_rebuild=True)")

        try:
            await vector_store.delete_module_vectors(course_id, module_id)
            log.info("[CLEANUP] Module vectors deleted successfully")
            return {}
        except Exception as e:
            log.exception("[CLEANUP] Failed to delete vectors", error=str(e))
            return {"error": f"Cleanup failed: {e}"}

    return cleanup_vectors


# ── Node: Chunk Texts ──────────────────────────────────────────────


def _build_chunk_node(text_chunker: TextChunker):
    """Chunk all lesson texts into overlapping segments."""

    async def chunk_texts(state: IndexState) -> dict:
        lesson_texts = state.lesson_texts
        course_id = state.course_id
        module_id = state.module_id

        log = logger.bind(course_id=course_id, module_id=module_id)
        log.info("[CHUNK] Starting text chunking", num_lessons=len(lesson_texts))

        try:
            lesson_chunks: dict[str, list[dict]] = {}
            total = 0

            for lesson_id, text in lesson_texts.items():
                chunks = text_chunker.chunk_text(text)
                if chunks:
                    lesson_chunks[lesson_id] = [
                        {
                            "text": c.text,
                            "chunk_index": c.chunk_index,
                            "start_char": c.start_char,
                            "end_char": c.end_char,
                        }
                        for c in chunks
                    ]
                    total += len(chunks)

            if total == 0:
                log.warning("[CHUNK] No chunks produced from any lesson")
                return {"error": "No content to index — all lessons produced zero chunks"}

            log.info(
                "[CHUNK] Chunking complete",
                total_chunks=total,
                lessons_with_chunks=len(lesson_chunks),
            )
            return {"lesson_chunks": lesson_chunks}

        except Exception as e:
            log.exception("[CHUNK] Chunking failed", error=str(e))
            return {"error": f"Chunking failed: {e}"}

    return chunk_texts


# ── Node: Embed Chunks ─────────────────────────────────────────────


def _build_embed_node(openai_client: OpenAIClient):
    """Embed all chunks in batches using OpenAI text-embedding-3-small."""

    async def embed_chunks(state: IndexState) -> dict:
        lesson_chunks = state.lesson_chunks
        log = logger.bind(course_id=state.course_id, module_id=state.module_id)

        # Flatten all chunks into one list for minimal API calls
        flat_texts = []
        index_map = []  # (lesson_id, local_index) to reconstruct later
        for lesson_id, chunks in lesson_chunks.items():
            for i, c in enumerate(chunks):
                flat_texts.append(c["text"])
                index_map.append((lesson_id, i))

        total = len(flat_texts)
        log.info("[EMBED] Starting embedding", total_texts=total)

        async def _rate_limited_embed(batch):
            async with EMBEDDING_SEMAPHORE:
                return await openai_client.embed_texts(batch)

        try:
            # Embed everything in batches (but all batches can also run in parallel)
            all_embeddings = []
            tasks = []
            for i in range(0, total, EMBEDDING_BATCH_SIZE):
                batch = flat_texts[i : i + EMBEDDING_BATCH_SIZE]
                tasks.append(_rate_limited_embed(batch))

            batch_results = await asyncio.gather(*tasks)
            for batch_embs in batch_results:
                all_embeddings.extend(batch_embs)

            # Reconstruct per-lesson structure
            lesson_embeddings: dict[str, list[list[float]]] = {}
            for (lesson_id, _), embedding in zip(index_map, all_embeddings):
                lesson_embeddings.setdefault(lesson_id, []).append(embedding)

            log.info("[EMBED] Embedding complete", total_embedded=total)
            return {"lesson_embeddings": lesson_embeddings}

        except Exception as e:
            log.exception("[EMBED] Embedding failed", error=str(e))
            return {"error": f"Embedding failed: {e}"}

    return embed_chunks


# ── Node: Store Vectors ────────────────────────────────────────────


def _build_store_node(vector_store: VectorStoreRepository):
    """Upsert embedded chunks into Qdrant with full metadata."""

    async def store_vectors(state: IndexState) -> dict:
        log = logger.bind(course_id=state.course_id, module_id=state.module_id)
        log.info("[STORE] Starting vector storage")

        lesson_title_map = {l["lesson_id"]: l.get("title", "") for l in state.lessons}

        try:

            async def _upsert_lesson(lesson_id: str) -> int:
                chunks = state.lesson_chunks[lesson_id]
                embeddings = state.lesson_embeddings[lesson_id]
                chunk_records = [
                    {
                        "text": chunk["text"],
                        "embedding": emb,
                        "chunk_index": chunk["chunk_index"],
                        "lesson_title": lesson_title_map.get(lesson_id, ""),
                        "module_title": state.module_title,
                    }
                    for chunk, emb in zip(chunks, embeddings)
                ]
                return await vector_store.upsert_chunks(
                    course_id=state.course_id,
                    module_id=state.module_id,
                    lesson_id=lesson_id,
                    chunks=chunk_records,
                )

            results = await asyncio.gather(*(_upsert_lesson(lid) for lid in state.lesson_chunks))
            total_stored = sum(results)

            log.info("[STORE] Vector storage complete", total_stored=total_stored)
            return {"total_chunks_stored": total_stored, "completed": True}

        except Exception as e:
            log.exception("[STORE] Storage failed", error=str(e))
            return {"error": f"Storage failed: {e}"}

    return store_vectors


# ── Error Router ───────────────────────────────────────────────────


def _error_router(next_node: str):
    """Generic router: if state has error, go to END; otherwise go to next_node."""

    def router(state: IndexState) -> str:
        if state.error:
            return END
        return next_node

    return router


# ── Graph Builder ──────────────────────────────────────────────────


from ai_service.services.content_pipeline.video_processor import build_video_extraction_node


def build_index_graph(
    content_extractor: ContentExtractor,
    text_chunker: TextChunker,
    openai_client: OpenAIClient,
    vector_store: VectorStoreRepository,
) -> CompiledStateGraph:
    """Build and compile the LangGraph indexing pipeline.

    New flow:
      START -> cleanup_vectors -> fetch_lessons -> extract_pdfs
            -> extract_audio -> extract_video -> merge_content -> chunk_texts -> embed_chunks -> store_vectors -> END

    Args:
        content_extractor: Fetches module/lesson data from MongoDB.
        text_chunker: Text splitter for chunking lesson content.
        openai_client: OpenAI client for batch embeddings and PDF/vision/video.
        vector_store: Qdrant repository for vector storage.

    Returns:
        Compiled LangGraph StateGraph ready for invocation.
    """
    cleanup_node = _build_cleanup_node(vector_store)
    fetch_node = _build_fetch_lessons_node(content_extractor)
    extract_pdfs_node = build_pdf_extraction_node(openai_client)
    extract_audio_node = build_audio_extraction_node(openai_client)
    extract_video_node = build_video_extraction_node()
    merge_node = _build_merge_content_node(content_extractor)
    chunk_node = _build_chunk_node(text_chunker)
    embed_node = _build_embed_node(openai_client)
    store_node = _build_store_node(vector_store)

    graph = StateGraph(IndexState)

    graph.add_node("cleanup_vectors", cleanup_node)
    graph.add_node("fetch_lessons", fetch_node)
    graph.add_node("extract_pdfs", extract_pdfs_node)
    graph.add_node("extract_audio", extract_audio_node)
    graph.add_node("extract_video", extract_video_node)
    graph.add_node("merge_content", merge_node)
    graph.add_node("chunk_texts", chunk_node)
    graph.add_node("embed_chunks", embed_node)
    graph.add_node("store_vectors", store_node)

    graph.add_edge(START, "cleanup_vectors")
    graph.add_conditional_edges("cleanup_vectors", _error_router("fetch_lessons"))
    graph.add_conditional_edges("fetch_lessons", _error_router("extract_pdfs"))
    graph.add_edge("extract_pdfs", "extract_audio")
    graph.add_edge("extract_audio", "extract_video")
    graph.add_edge("extract_video", "merge_content")
    graph.add_conditional_edges("merge_content", _error_router("chunk_texts"))
    graph.add_conditional_edges("chunk_texts", _error_router("embed_chunks"))
    graph.add_conditional_edges("embed_chunks", _error_router("store_vectors"))
    graph.add_edge("store_vectors", END)

    return graph.compile()
