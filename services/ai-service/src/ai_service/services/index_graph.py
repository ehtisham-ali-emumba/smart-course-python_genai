"""LangGraph-powered RAG indexing pipeline.

Implements a multi-node state machine for course content indexing:
  cleanup_vectors → chunk_texts → embed_chunks → store_vectors → END

Each node handles one stage of the pipeline. Conditional edges route to END
on errors, preventing wasted work downstream.

Follows the same closure/factory pattern as tutor_agent.py and instructor_graphs.py.
"""

import uuid as _uuid
import structlog
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from ai_service.services.text_chunker import TextChunker
from ai_service.clients.openai_client import OpenAIClient
from ai_service.repositories.vector_store import VectorStoreRepository

logger = structlog.get_logger(__name__)

# ── Configuration ──────────────────────────────────────────────────

EMBEDDING_BATCH_SIZE = 100


# ── State ──────────────────────────────────────────────────────────


class IndexState(BaseModel):
    """State flowing through the indexing pipeline."""

    # ── Required Input (set before graph invocation) ──
    course_id: _uuid.UUID
    module_id: str
    module_title: str
    lesson_texts: dict[str, str]  # lesson_id → full text
    lessons: list[dict]  # lesson metadata (for title mapping)
    force_rebuild: bool

    # ── Intermediate (set by nodes) ──
    lesson_chunks: dict[str, list[dict]] = Field(
        default_factory=dict
    )  # lesson_id → [{text, chunk_index, ...}]
    lesson_embeddings: dict[str, list[list[float]]] = Field(
        default_factory=dict
    )  # lesson_id → [embedding vectors]
    total_chunks_stored: int = 0

    # ── Output / Error ──
    error: str | None = None
    completed: bool = False

    class Config:
        """Pydantic config."""

        arbitrary_types_allowed = True


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
        lesson_chunks: dict[str, list[dict]] = state.lesson_chunks
        course_id = state.course_id
        module_id = state.module_id

        log = logger.bind(course_id=course_id, module_id=module_id)

        total_texts = sum(len(chunks) for chunks in lesson_chunks.values())
        log.info("[EMBED] Starting embedding", total_texts=total_texts)

        try:
            lesson_embeddings: dict[str, list[list[float]]] = {}

            for lesson_id, chunks in lesson_chunks.items():
                texts = [c["text"] for c in chunks]
                all_embeddings: list[list[float]] = []

                # Batch embed (max EMBEDDING_BATCH_SIZE per API call)
                for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
                    batch = texts[i : i + EMBEDDING_BATCH_SIZE]
                    batch_embeddings = await openai_client.embed_texts(batch)
                    all_embeddings.extend(batch_embeddings)

                lesson_embeddings[lesson_id] = all_embeddings

            log.info("[EMBED] Embedding complete", total_embedded=total_texts)
            return {"lesson_embeddings": lesson_embeddings}

        except Exception as e:
            log.exception("[EMBED] Embedding failed", error=str(e))
            return {"error": f"Embedding failed: {e}"}

    return embed_chunks


# ── Node: Store Vectors ────────────────────────────────────────────


def _build_store_node(vector_store: VectorStoreRepository):
    """Upsert embedded chunks into Qdrant with full metadata."""

    async def store_vectors(state: IndexState) -> dict:
        course_id = state.course_id
        module_id = state.module_id
        module_title = state.module_title
        lesson_chunks: dict[str, list[dict]] = state.lesson_chunks
        lesson_embeddings: dict[str, list[list[float]]] = state.lesson_embeddings
        lessons = state.lessons

        log = logger.bind(course_id=course_id, module_id=module_id)
        log.info("[STORE] Starting vector storage")

        # Build lesson_id → title mapping
        lesson_title_map = {lesson["lesson_id"]: lesson.get("title", "") for lesson in lessons}

        try:
            total_stored = 0

            for lesson_id in lesson_chunks:
                chunks = lesson_chunks[lesson_id]
                embeddings = lesson_embeddings[lesson_id]

                chunk_records = [
                    {
                        "text": chunk["text"],
                        "embedding": embedding,
                        "chunk_index": chunk["chunk_index"],
                        "lesson_title": lesson_title_map.get(lesson_id, ""),
                        "module_title": module_title,
                    }
                    for chunk, embedding in zip(chunks, embeddings)
                ]

                stored = await vector_store.upsert_chunks(
                    course_id=course_id,
                    module_id=module_id,
                    lesson_id=lesson_id,
                    chunks=chunk_records,
                )
                total_stored += stored

            log.info("[STORE] Vector storage complete", total_stored=total_stored)
            return {
                "total_chunks_stored": total_stored,
                "completed": True,
            }

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


def build_index_graph(
    text_chunker: TextChunker,
    openai_client: OpenAIClient,
    vector_store: VectorStoreRepository,
) -> CompiledStateGraph:
    """Build and compile the LangGraph indexing pipeline.

    Flow:
      START → cleanup_vectors → chunk_texts → embed_chunks → store_vectors → END
                  ↓ error          ↓ error       ↓ error        ↓ error
                 END               END           END            END

    Args:
        text_chunker: Text splitter for chunking lesson content.
        openai_client: OpenAI client for batch embeddings.
        vector_store: Qdrant repository for vector storage.

    Returns:
        Compiled LangGraph StateGraph ready for invocation.
    """
    # Create node functions with injected dependencies
    cleanup_node = _build_cleanup_node(vector_store)
    chunk_node = _build_chunk_node(text_chunker)
    embed_node = _build_embed_node(openai_client)
    store_node = _build_store_node(vector_store)

    # Build the graph
    graph = StateGraph(IndexState)

    # Add nodes
    graph.add_node("cleanup_vectors", cleanup_node)
    graph.add_node("chunk_texts", chunk_node)
    graph.add_node("embed_chunks", embed_node)
    graph.add_node("store_vectors", store_node)

    # Define edges with error routing at each step
    graph.add_edge(START, "cleanup_vectors")
    graph.add_conditional_edges("cleanup_vectors", _error_router("chunk_texts"))
    graph.add_conditional_edges("chunk_texts", _error_router("embed_chunks"))
    graph.add_conditional_edges("embed_chunks", _error_router("store_vectors"))
    graph.add_edge("store_vectors", END)

    return graph.compile()
