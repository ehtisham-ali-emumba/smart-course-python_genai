# LangGraph RAG Indexing Pipeline — Migration Guide

## Executive Summary

Your **tutor agent** (`tutor_agent.py`) and **instructor graphs** (`instructor_graphs.py`) already use LangGraph beautifully. But the **indexing pipeline** (`services/index.py`) is still a manual procedural chain: extract → chunk → embed → store, orchestrated with raw `asyncio.create_task` and nested loops.

This guide migrates the indexing pipeline to a LangGraph `StateGraph`, giving you:
- **Consistent architecture** — every AI workflow in the service uses LangGraph
- **Built-in error routing** — conditional edges handle failures at each step
- **Retry support** — embedding/storage failures can retry without restarting
- **Observability** — LangGraph's tracing shows exactly which node failed and why
- **Extensibility** — easy to add nodes like `validate_chunks`, `deduplicate`, or `summarize_before_embed`

---

## Current Architecture (What Changes)

```
services/index.py (BEFORE — procedural)
├── build_course_index()          → asyncio.create_task
├── _build_course_index_task()    → manual loop over modules
├── _build_module_index_task()    → manual extract → chunk → embed → store
├── _index_module_lessons()       → nested loop: per-lesson chunk/embed/store
└── _embed_in_batches()           → manual batch splitting
```

```
services/index_graph.py (AFTER — LangGraph)
├── IndexState (TypedDict)
├── Nodes: cleanup → extract → chunk → embed → store
├── Conditional edges: error → END at each step
├── build_index_graph()           → compiled StateGraph
└── IndexService uses the graph instead of manual orchestration
```

---

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `services/index_graph.py` | **CREATE** | LangGraph indexing pipeline |
| `services/index.py` | **MODIFY** | Use graph instead of manual orchestration |
| `pyproject.toml` | **NO CHANGE** | `langgraph` already in dependencies |

---

## Step 1: Create `services/index_graph.py`

This is the new LangGraph pipeline. It follows the exact same factory/closure pattern as your existing `instructor_graphs.py` and `tutor_agent.py`.

```python
"""LangGraph-powered RAG indexing pipeline.

Implements a multi-node state machine for course content indexing:
  cleanup_vectors → extract_content → chunk_texts → embed_chunks → store_vectors → END

Each node handles one stage of the pipeline. Conditional edges route to END
on errors, preventing wasted work downstream.

Follows the same closure/factory pattern as tutor_agent.py and instructor_graphs.py.
"""

import uuid as _uuid
import structlog
from typing import TypedDict
from dataclasses import asdict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from ai_service.services.content_extractor import ContentExtractor
from ai_service.services.text_chunker import TextChunker
from ai_service.clients.openai_client import OpenAIClient
from ai_service.repositories.vector_store import VectorStoreRepository

logger = structlog.get_logger(__name__)

# ── Configuration ──────────────────────────────────────────────────

EMBEDDING_BATCH_SIZE = 100


# ── State ──────────────────────────────────────────────────────────


class IndexState(TypedDict, total=False):
    """State flowing through the indexing pipeline."""

    # ── Input (set before graph invocation) ──
    course_id: _uuid.UUID
    module_id: str
    module_title: str
    lesson_texts: dict[str, str]       # lesson_id → full text
    lessons: list[dict]                # lesson metadata (for title mapping)
    force_rebuild: bool

    # ── Intermediate (set by nodes) ──
    lesson_chunks: dict[str, list[dict]]   # lesson_id → [{text, chunk_index, ...}]
    lesson_embeddings: dict[str, list[list[float]]]  # lesson_id → [embedding vectors]
    total_chunks_stored: int

    # ── Output / Error ──
    error: str | None
    completed: bool


# ── Node: Cleanup Vectors ──────────────────────────────────────────


def _build_cleanup_node(vector_store: VectorStoreRepository):
    """Delete existing vectors for the module before re-indexing."""

    async def cleanup_vectors(state: IndexState) -> dict:
        course_id = state["course_id"]
        module_id = state["module_id"]

        log = logger.bind(course_id=course_id, module_id=module_id)
        log.info("[CLEANUP] Deleting existing module vectors")

        try:
            await vector_store.delete_module_vectors(course_id, module_id)
            log.info("[CLEANUP] Module vectors deleted")
            return {}
        except Exception as e:
            log.exception("[CLEANUP] Failed to delete vectors", error=str(e))
            return {"error": f"Cleanup failed: {e}"}

    return cleanup_vectors


# ── Node: Chunk Texts ──────────────────────────────────────────────


def _build_chunk_node(text_chunker: TextChunker):
    """Chunk all lesson texts into overlapping segments."""

    async def chunk_texts(state: IndexState) -> dict:
        lesson_texts = state["lesson_texts"]
        course_id = state["course_id"]
        module_id = state["module_id"]

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

            log.info("[CHUNK] Chunking complete", total_chunks=total, lessons_with_chunks=len(lesson_chunks))
            return {"lesson_chunks": lesson_chunks}

        except Exception as e:
            log.exception("[CHUNK] Chunking failed", error=str(e))
            return {"error": f"Chunking failed: {e}"}

    return chunk_texts


# ── Node: Embed Chunks ─────────────────────────────────────────────


def _build_embed_node(openai_client: OpenAIClient):
    """Embed all chunks in batches using OpenAI text-embedding-3-small."""

    async def embed_chunks(state: IndexState) -> dict:
        lesson_chunks = state["lesson_chunks"]
        course_id = state["course_id"]
        module_id = state["module_id"]

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
        course_id = state["course_id"]
        module_id = state["module_id"]
        module_title = state.get("module_title", "")
        lesson_chunks = state["lesson_chunks"]
        lesson_embeddings = state["lesson_embeddings"]
        lessons = state.get("lessons", [])

        log = logger.bind(course_id=course_id, module_id=module_id)
        log.info("[STORE] Starting vector storage")

        # Build lesson_id → title mapping
        lesson_title_map = {
            lesson["lesson_id"]: lesson.get("title", "")
            for lesson in lessons
        }

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
        if state.get("error"):
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
```

---

## Step 2: Modify `services/index.py`

Replace the manual orchestration with graph invocations. The `IndexService` becomes much thinner — it delegates to the graph and handles status tracking.

### What to remove from `services/index.py`:
- `_index_module_lessons()` — replaced by the graph
- `_embed_in_batches()` — now inside the embed node

### Full replacement for `services/index.py`:

```python
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

    async def build_course_index(
        self, course_id: _uuid.UUID, request: BuildIndexRequest
    ) -> IndexBuildResponse:
        """Trigger index build for an entire course (background task)."""
        log = logger.bind(course_id=course_id)
        log.info("Course index build requested", force_rebuild=request.force_rebuild)

        asyncio.create_task(self._build_course_index_task(course_id, request.force_rebuild))

        return IndexBuildResponse(
            course_id=course_id,
            status=IndexStatus.PENDING,
            message="Course index build started. Poll the status endpoint to track progress.",
            requested_at=datetime.now(timezone.utc),
        )

    async def build_module_index(
        self, course_id: _uuid.UUID, module_id: str, request: BuildIndexRequest
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

    async def _build_course_index_task(self, course_id: _uuid.UUID, force_rebuild: bool) -> None:
        """Background task: index all modules in a course using LangGraph."""
        log = logger.bind(course_id=course_id)
        try:
            await self.status_tracker.set_in_progress(course_id, "course", "index")

            # If force rebuild, delete all course vectors upfront
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

            # Run the LangGraph pipeline for each module
            for module_data in course_content["modules"]:
                module_id = module_data["module_id"]

                result = await self._index_graph.ainvoke(
                    IndexState(
                        course_id=course_id,
                        module_id=module_id,
                        module_title=module_data["module_title"],
                        lesson_texts=module_data["lesson_texts"],
                        lessons=module_data["lessons"],
                        force_rebuild=force_rebuild,
                    )
                )

                # Check for graph-level errors
                if result.get("error"):
                    log.error(
                        "Module indexing failed in graph",
                        module_id=module_id,
                        error=result["error"],
                    )
                    # Continue with other modules — don't fail the whole course
                    continue

                total_chunks += result.get("total_chunks_stored", 0)

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
        self, course_id: _uuid.UUID, module_id: str, force_rebuild: bool
    ) -> None:
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

            # Run the LangGraph pipeline
            result = await self._index_graph.ainvoke(
                IndexState(
                    course_id=course_id,
                    module_id=module_id,
                    module_title=module_content["module_title"],
                    lesson_texts=module_content["lesson_texts"],
                    lessons=module_content["lessons"],
                    force_rebuild=force_rebuild,
                )
            )

            if result.get("error"):
                await self.status_tracker.set_failed(
                    course_id, module_id, "index", result["error"]
                )
                return

            chunks_stored = result.get("total_chunks_stored", 0)
            await self.status_tracker.set_completed(course_id, module_id, "index")
            log.info("Module index build completed", chunks_stored=chunks_stored)

        except Exception as e:
            log.exception("Module index build failed", error=str(e))
            await self.status_tracker.set_failed(course_id, module_id, "index", str(e))

    # ── Status methods remain unchanged ──

    async def get_course_status(self, course_id: _uuid.UUID) -> IndexStatusResponse:
        """Get index status for a course."""
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
            count = await self.vector_store.count_course_vectors(course_id)
            if count > 0:
                status = IndexStatus.INDEXED
                last_build_at = None
            else:
                status = IndexStatus.PENDING
                last_build_at = None
            error_message = None

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
        mapping = {
            "pending": "pending",
            "in_progress": "indexing",
            "completed": "indexed",
            "failed": "failed",
        }
        return mapping.get(gen_status, "pending")
```

---

## Step 3: No Changes Needed

These files require **zero changes**:

| File | Why unchanged |
|------|---------------|
| `api/index.py` | Calls `IndexService` methods — same interface |
| `api/dependencies.py` | Injects same dependencies into `IndexService` |
| `services/text_chunker.py` | Used as-is inside the chunk node |
| `clients/openai_client.py` | Used as-is inside the embed node |
| `repositories/vector_store.py` | Used as-is inside cleanup + store nodes |
| `services/content_extractor.py` | Still called by `IndexService` before graph invocation |
| `services/tutor_agent.py` | Completely separate pipeline |
| `services/instructor_graphs.py` | Completely separate pipeline |
| `pyproject.toml` | `langgraph>=0.2.0` already listed |

---

## Architecture Comparison

### Before (Manual Orchestration)
```
IndexService._build_course_index_task()
    │
    ├── for module in modules:           ← manual loop
    │   ├── _index_module_lessons()      ← manual orchestration
    │   │   ├── for lesson in lessons:   ← nested loop
    │   │   │   ├── text_chunker.chunk_text()
    │   │   │   ├── _embed_in_batches()
    │   │   │   └── vector_store.upsert_chunks()
    │   │   └── return total_stored
    │   └── total_chunks += chunks_stored
    └── status_tracker.set_completed()
```

### After (LangGraph Pipeline)
```
IndexService._build_course_index_task()
    │
    ├── for module in modules:
    │   └── self._index_graph.ainvoke(IndexState(...))
    │       │
    │       │  ┌─────────────────────────────────────────────┐
    │       └──│ LangGraph: cleanup → chunk → embed → store  │
    │          │             ↓err     ↓err    ↓err    ↓err   │
    │          │             END      END     END     END    │
    │          └─────────────────────────────────────────────┘
    │
    └── status_tracker.set_completed()
```

---

## Key Design Decisions

### 1. Graph compiled once, invoked per-module
The graph is compiled in `IndexService.__init__()` and reused for every module. LangGraph graphs are stateless after compilation — state is passed per invocation. This avoids recompilation overhead.

### 2. Content extraction stays outside the graph
Unlike `instructor_graphs.py` where extraction is a graph node, here extraction stays in `IndexService` because:
- Course-level builds extract ALL modules first, then iterate
- The graph operates per-module, not per-course
- This matches the existing data flow without forcing the graph to handle course-level iteration

### 3. Cleanup is a graph node
Vector cleanup (delete old module vectors) is the first graph node because it's part of the per-module pipeline and should fail-fast if Qdrant is unreachable.

### 4. Error routing at every step
Each node returns `{"error": "..."}` on failure. The `_error_router` conditional edge checks for errors and routes to `END`, preventing wasted API calls (e.g., don't call OpenAI embeddings if chunking produced nothing).

### 5. No retry on embedding failures (yet)
Unlike quiz/summary generation which retries with validation feedback, embedding is deterministic — if it fails, it's an API error. You can add retry logic later by adding a conditional edge from `embed_chunks` back to itself with a retry counter (same pattern as `instructor_graphs.py`).

---

## Future Enhancements (Easy with LangGraph)

Once the base migration is done, these become trivial additions:

### Add a `validate_chunks` node
Insert between `chunk_texts` and `embed_chunks` to check chunk quality:
```python
graph.add_node("validate_chunks", validate_node)
graph.add_conditional_edges("chunk_texts", _error_router("validate_chunks"))
graph.add_conditional_edges("validate_chunks", _error_router("embed_chunks"))
```

### Add retry on embedding failure
```python
def _embed_retry_router(state: IndexState) -> str:
    if state.get("error") and state.get("embed_retry_count", 0) < 2:
        return "embed_chunks"  # retry
    if state.get("error"):
        return END
    return "store_vectors"
```

### Add a `deduplicate` node
Before embedding, check if chunk text is near-duplicate of existing vectors:
```python
graph.add_node("deduplicate", dedup_node)
# Insert between chunk and embed
```

### Add LangSmith tracing
LangGraph natively supports LangSmith. Just set:
```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your-key
```
Every graph invocation is automatically traced with node-level timing and state snapshots.

---

## Testing Strategy

1. **Unit test each node independently** — pass mock state, verify output dict
2. **Integration test the compiled graph** — invoke with real ContentExtractor output, mock only OpenAI
3. **Verify error routing** — inject errors at each node, verify graph exits cleanly
4. **Compare output** — run old and new pipelines on the same course, verify identical Qdrant vectors

Example test:
```python
import pytest
from ai_service.services.index_graph import build_index_graph, IndexState

@pytest.mark.asyncio
async def test_index_graph_error_routing(mock_chunker, mock_openai, mock_vector_store):
    """Graph should route to END when chunking produces no chunks."""
    graph = build_index_graph(mock_chunker, mock_openai, mock_vector_store)

    result = await graph.ainvoke(
        IndexState(
            course_id=uuid4(),
            module_id="abc123",
            module_title="Test Module",
            lesson_texts={"lesson1": ""},  # empty text → no chunks
            lessons=[{"lesson_id": "lesson1", "title": "Test"}],
            force_rebuild=False,
        )
    )

    assert result.get("error") is not None
    assert "zero chunks" in result["error"]
    mock_openai.embed_texts.assert_not_called()  # should never reach embed node
```

---

## Migration Checklist

- [ ] Create `services/index_graph.py` with the code from Step 1
- [ ] Replace `services/index.py` with the code from Step 2
- [ ] Run existing tests to verify no regressions
- [ ] Test course-level index build end-to-end
- [ ] Test module-level index build end-to-end
- [ ] Test error scenarios (empty content, OpenAI failure, Qdrant down)
- [ ] Verify status endpoint still works correctly
- [ ] (Optional) Enable LangSmith tracing for observability
