# RAG Indexing Implementation Guide — SmartCourse AI Service

> **Scope**: This guide covers RAG (Retrieval-Augmented Generation) indexing — taking your course content (PDFs), chunking it, embedding it, and storing it in a vector database. The AI Tutor (LangGraph consumer of this index) will be covered in the next session.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [When Does RAG Indexing Happen? (Course Lifecycle)](#2-when-does-rag-indexing-happen-course-lifecycle)
3. [Technology Choices & Rationale](#3-technology-choices--rationale)
4. [Prerequisites & API Keys](#4-prerequisites--api-keys)
5. [Infrastructure Setup (Qdrant + Docker)](#5-infrastructure-setup-qdrant--docker)
6. [New Dependencies](#6-new-dependencies)
7. [Centralize Content Extraction (Refactor)](#7-centralize-content-extraction-refactor)
8. [Text Chunking Strategy](#8-text-chunking-strategy)
9. [Embedding Generation](#9-embedding-generation)
10. [Vector Store Implementation (Qdrant)](#10-vector-store-implementation-qdrant)
11. [Index Service — Temporal-Ready Activities](#11-index-service--temporal-ready-activities)
12. [Index Status Tracking](#12-index-status-tracking)
13. [API Endpoints (Wire It Up)](#13-api-endpoints-wire-it-up)
14. [Startup/Lifespan Changes](#14-startuplifespan-changes)
15. [File-by-File Summary](#15-file-by-file-summary)
16. [Testing the Pipeline](#16-testing-the-pipeline)
17. [What Comes Next (AI Tutor with LangGraph)](#17-what-comes-next-ai-tutor-with-langgraph)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    RAG Indexing Pipeline                         │
│                                                                 │
│  Instructor triggers POST /api/v1/ai/index/courses/{id}/build   │
│                          │                                      │
│                          ▼                                      │
│               ┌──────────────────┐                              │
│               │  IndexService    │                              │
│               │  (Background)    │                              │
│               └────────┬─────────┘                              │
│                        │                                        │
│          ┌─────────────┼──────────────┐                         │
│          ▼             ▼              ▼                          │
│   ┌────────────┐ ┌──────────┐ ┌─────────────┐                  │
│   │ MongoDB    │ │ PDF      │ │ Redis       │                   │
│   │ (content)  │ │ Extract  │ │ (status)    │                   │
│   └─────┬──────┘ └────┬─────┘ └─────────────┘                  │
│         │              │                                        │
│         ▼              ▼                                        │
│   ┌─────────────────────────┐                                   │
│   │  ContentExtractor       │  ← NEW centralized service        │
│   │  (fetch + extract +     │                                   │
│   │   combine text)         │                                   │
│   └────────────┬────────────┘                                   │
│                │                                                │
│                ▼                                                │
│   ┌─────────────────────────┐                                   │
│   │  TextChunker            │  ← NEW                            │
│   │  (split into ~512 token │                                   │
│   │   chunks with overlap)  │                                   │
│   └────────────┬────────────┘                                   │
│                │                                                │
│                ▼                                                │
│   ┌─────────────────────────┐                                   │
│   │  OpenAI Embeddings      │                                   │
│   │  text-embedding-3-small │  ← Already configured in .env     │
│   │  1536 dimensions        │                                   │
│   └────────────┬────────────┘                                   │
│                │                                                │
│                ▼                                                │
│   ┌─────────────────────────┐                                   │
│   │  Qdrant Vector DB       │  ← NEW container                  │
│   │  Collection:            │                                   │
│   │  "course_embeddings"    │                                   │
│   │                         │                                   │
│   │  Payload metadata:      │                                   │
│   │  - course_id            │                                   │
│   │  - module_id            │                                   │
│   │  - lesson_id            │                                   │
│   │  - chunk_index          │                                   │
│   │  - lesson_title         │                                   │
│   │  - module_title         │                                   │
│   │  - source_text (first   │                                   │
│   │    200 chars preview)   │                                   │
│   └─────────────────────────┘                                   │
└─────────────────────────────────────────────────────────────────┘
```

**Key idea**: When a student asks a question to the AI Tutor, the tutor will embed the question, search Qdrant for the most relevant chunks, and feed those chunks as context to the LLM. But first, we need to **build the index** — that's what this guide covers.

---

## 2. When Does RAG Indexing Happen? (Course Lifecycle)

### The Timeline

RAG indexing does **NOT** happen during course creation. Here's how it fits into the full course lifecycle:

```
┌─────────────────────────────────────────────────────────────────────┐
│                     COURSE CREATION PHASE                           │
│                     (Instructor is building the course)             │
│                                                                     │
│  1. Instructor creates course                                       │
│  2. Instructor adds modules + lessons (uploads PDFs)                │
│  3. Instructor triggers summary generation  ← AI (already done)    │
│  4. Instructor triggers quiz generation     ← AI (already done)    │
│  5. Instructor reviews generated content                            │
│                                                                     │
│  ❌ NO RAG indexing yet — course is still in draft                  │
│     (no students can see it, no tutor needed)                       │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │  Instructor clicks "Publish Course"
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     PUBLISH WORKFLOW                                 │
│                     (Temporal Workflow from course-service)          │
│                                                                     │
│  Temporal Workflow: PublishCourseWorkflow                            │
│  ┌────────────────────────────────────────────────────────────┐     │
│  │                                                            │     │
│  │  Activity 1: validate_course_ready                         │     │
│  │    → Check all modules have content, summaries, quizzes    │     │
│  │                                                            │     │
│  │  Activity 2: extract_course_content    ← RAG STEP 1       │     │
│  │    → Fetch all modules/lessons from MongoDB                │     │
│  │    → Download + extract PDF text                           │     │
│  │    → Returns structured content per lesson                 │     │
│  │                                                            │     │
│  │  Activity 3: chunk_course_content      ← RAG STEP 2       │     │
│  │    → Split extracted text into ~375-token chunks           │     │
│  │    → Returns list of chunks with metadata                  │     │
│  │                                                            │     │
│  │  Activity 4: embed_chunks              ← RAG STEP 3       │     │
│  │    → Send chunks to OpenAI text-embedding-3-small          │     │
│  │    → Returns embedding vectors                             │     │
│  │                                                            │     │
│  │  Activity 5: store_vectors             ← RAG STEP 4       │     │
│  │    → Upsert embeddings + metadata into Qdrant              │     │
│  │    → course_id, module_id, lesson_id attached              │     │
│  │                                                            │     │
│  │  Activity 6: mark_course_published                         │     │
│  │    → Update course status to "published"                   │     │
│  │    → Students can now enroll and use AI Tutor              │     │
│  │                                                            │     │
│  └────────────────────────────────────────────────────────────┘     │
│                                                                     │
│  If any activity fails → Temporal retries automatically             │
│  If RAG indexing fails → course stays in "publishing" state         │
│  (never half-published without a working index)                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     LIVE COURSE                                     │
│                                                                     │
│  ✅ Students enroll                                                 │
│  ✅ AI Tutor available (uses RAG index for answers)                 │
│  ✅ Summaries + quizzes already generated                           │
└─────────────────────────────────────────────────────────────────────┘
```

### Why This Order Matters

| Concern | How It's Handled |
|---------|-----------------|
| **Instructor generates summaries/quizzes first** | These happen during course creation (already implemented). They don't need RAG — they use the full content directly via `ContentExtractor`. |
| **RAG happens at publish time** | A draft course has no students, so there's no one to use the AI Tutor. Building the index at publish time ensures it's ready when students arrive. |
| **Temporal guarantees atomicity** | If RAG indexing fails mid-way, Temporal retries the failed activity. The course never gets published with a broken/missing index. |
| **Activities are individually retriable** | Each RAG step (extract, chunk, embed, store) is a separate Temporal activity. If embedding fails due to an OpenAI rate limit, only that step retries — not the whole pipeline. |

### Design Principle: Components as Activities

This is why the `IndexService` in Section 11 is designed with **public, independently callable methods** instead of one big private method. Each method maps to a Temporal activity:

| IndexService Method | Temporal Activity | What It Does |
|--------------------|--------------------|-------------|
| `extract_course_content()` | `extract_course_content` | Fetch from MongoDB + extract PDFs |
| `chunk_course_content()` | `chunk_course_content` | Split text into overlapping chunks |
| `embed_chunks()` | `embed_chunks` | Generate OpenAI embeddings |
| `store_vectors()` | `store_vectors` | Upsert into Qdrant with metadata |
| `delete_course_vectors()` | `delete_course_vectors` | Clean up before re-index |

The API endpoints (`POST /index/courses/{id}/build`) still work for **manual triggering** (useful during development/testing), but in production the Temporal workflow will call these same methods directly as activities.

### The Manual API Endpoint Is Still Useful

Even though the Temporal workflow will handle production indexing, the REST API endpoint remains valuable:
- **Development**: Trigger re-indexing without publishing
- **Admin operations**: Force rebuild if content was updated post-publish
- **Debugging**: Test the pipeline in isolation

---

## 3. Technology Choices & Rationale

| Choice | Why |
|--------|-----|
| **Qdrant** (vector DB) | Open-source, runs as a Docker container (no cloud account needed), excellent Python SDK, supports payload filtering (we need `course_id`, `module_id` filters), free, and very fast. Perfect for an MVP. |
| **OpenAI `text-embedding-3-small`** (embeddings) | Already configured in your `.env`. 1536 dimensions. Cheap (~$0.02 per 1M tokens). You already paid $5 — this will barely dent it. No extra API key needed. |
| **`langchain-text-splitters`** (chunking) | Battle-tested recursive text splitter. Handles markdown headers, paragraphs, sentences intelligently. We'll use this one library from LangChain without pulling in all of LangChain. |
| **Redis** (index status) | Already used for summary/quiz status tracking. Same pattern: `index_status:{course_id}` key with TTL. |

### Why NOT these alternatives?

| Alternative | Why not (for this MVP) |
|-------------|----------------------|
| Pinecone / Weaviate / Milvus | Require cloud accounts or heavier setup. Qdrant runs locally in Docker with zero config. |
| ChromaDB | Good for prototyping but Qdrant is more production-ready and supports filtering better. |
| pgvector (PostgreSQL) | Your Postgres is managed by course-service. Adding vector extension creates coupling. Keep vector concerns isolated. |
| Full LangChain | Too heavy. We only need the text splitter. Your codebase already has clean separation — no need for LangChain's abstractions over OpenAI (you already have `OpenAIClient`). |

---

## 3. Prerequisites & API Keys

### OpenAI API Key (You Already Have It)

Your existing OpenAI API key in `services/ai-service/.env` already supports embeddings. The `text-embedding-3-small` model is available on all OpenAI API tiers. **No additional key needed.**

```env
# Already in your .env — no changes needed for these:
OPENAI_API_KEY=sk-proj-...          # ← your existing key works for embeddings too
OPENAI_EMBEDDING_MODEL=text-embedding-3-small  # ← already configured
```

### Qdrant (No API Key Needed)

Qdrant runs locally in Docker. No API key, no account, no cloud. Just add the container to `docker-compose.yml`.

```env
# Already in your .env — no changes needed:
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=course_embeddings
```

### Cost Estimate

For a typical course with 5 modules × 4 lessons × 10-page PDFs:
- **Extracted text**: ~200 pages × 500 words = ~100K words ≈ 133K tokens
- **Embedding cost**: 133K tokens × $0.02/1M = **$0.003** (less than 1 cent)
- **Qdrant**: Free (self-hosted)
- **Total per course index**: < $0.01

Your $5 budget handles thousands of course indexes.

---

## 4. Infrastructure Setup (Qdrant + Docker)

### Step 1: Add Qdrant to `docker-compose.yml`

Add this service block after the `mongodb` service in your `docker-compose.yml`:

```yaml
  # ═══════════════════════════════════════════════════════════════
  #  QDRANT — Vector Database for RAG
  # ═══════════════════════════════════════════════════════════════

  qdrant:
    image: qdrant/qdrant:v1.12.4
    container_name: smartcourse-qdrant
    ports:
      - "6333:6333"    # REST API
      - "6334:6334"    # gRPC (used by Python SDK for speed)
    volumes:
      - qdrant_data:/qdrant/storage
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:6333/healthz"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - smartcourse-network
```

### Step 2: Add volume

Add to the `volumes:` section at the bottom of `docker-compose.yml`:

```yaml
volumes:
  postgres_data:
  redis_data:
  mongodb_data:
  rabbitmq_data:
  qdrant_data:        # ← ADD THIS
```

### Step 3: Update ai-service dependency

Update the `ai-service` block to depend on Qdrant:

```yaml
  ai-service:
    build:
      context: .
      dockerfile: services/ai-service/Dockerfile
    container_name: smartcourse-ai-service
    volumes:
      - ./services/ai-service/src:/app/src:ro
    env_file:
      - ./.env
      - ./services/ai-service/.env
    depends_on:
      mongodb:
        condition: service_healthy
      redis:
        condition: service_healthy
      kafka:
        condition: service_healthy
      schema-registry:
        condition: service_healthy
      kafka-init:
        condition: service_completed_successfully
      qdrant:                              # ← ADD THIS
        condition: service_healthy         # ← ADD THIS
    networks:
      - smartcourse-network
```

### Step 4: Start Qdrant

```bash
docker compose up -d qdrant
```

Verify it's running:
```bash
curl http://localhost:6333/healthz
# Should return: {"title":"qdrant - vectorass engine","version":"1.12.4","status":"ok"}
```

---

## 5. New Dependencies

### Add to `pyproject.toml`

Add these two packages to the `dependencies` list:

```toml
dependencies = [
    # ... existing deps ...
    "qdrant-client>=1.12.0",            # Qdrant Python SDK (async support)
    "langchain-text-splitters>=0.3.0",  # Text chunking (just the splitter, not all of LangChain)
]
```

### Install

```bash
cd services/ai-service
pip install -e ".[dev]"
# or if using Docker, rebuild:
docker compose build ai-service
```

**Why `langchain-text-splitters` instead of full LangChain?** This is a standalone package (~50KB) that only contains text splitting logic. It does NOT pull in LangChain core, LangChain OpenAI, or any other heavy dependencies. It gives us `RecursiveCharacterTextSplitter` which is the gold standard for chunking.

---

## 6. Centralize Content Extraction (Refactor)

### The Problem

Right now, both `_process_and_save_summary` and `_process_and_save_quiz` in `services/instructor.py` have **duplicate code** for:
1. Fetching module + lessons from MongoDB
2. Extracting PDF text from lesson resources
3. Building enriched context text

RAG indexing needs the **exact same pipeline**. Instead of copy-pasting a third time, let's centralize it.

### Create: `services/content_extractor.py` (NEW FILE)

```python
"""Centralized content extraction for course materials.

Used by: InstructorService (summary/quiz generation), IndexService (RAG indexing).
Fetches course content from MongoDB, downloads+extracts PDF text, and combines
everything into structured text ready for LLM or embedding consumption.
"""

import structlog

from ai_service.repositories.course_content import CourseContentRepository
from ai_service.clients.resource_extractor import ResourceTextExtractor

logger = structlog.get_logger(__name__)


class ContentExtractor:
    """Fetches and combines course content (MongoDB text + PDF resources) into text."""

    def __init__(
        self,
        repo: CourseContentRepository,
        resource_extractor: ResourceTextExtractor,
    ):
        self.repo = repo
        self.resource_extractor = resource_extractor

    async def extract_module_content(
        self,
        course_id: int,
        module_id: str,
        lesson_ids: list[str] | None = None,
    ) -> dict | None:
        """Extract all text content for a module (MongoDB text + PDF resources).

        Returns:
            Dict with keys:
              - module_title: str
              - module_description: str
              - lessons: list[dict] — each with lesson_id, title, text_content, resources
              - combined_text: str — all content merged into one text block
              - lesson_texts: dict[str, str] — mapping lesson_id → full text (inline + PDF)
            Returns None if module not found.
        """
        # 1. Fetch module + lessons from MongoDB
        context_data = await self.repo.get_module_with_lessons(
            course_id, module_id, lesson_ids
        )
        if not context_data:
            return None

        # 2. Extract PDF text from lesson resources
        pdf_texts = await self.resource_extractor.extract_text_from_lessons(
            context_data["lessons"]
        )

        # 3. Build enriched text per lesson and combined
        sections = [
            f"## Module: {context_data['module_title']}\n{context_data['module_description']}"
        ]
        lesson_texts: dict[str, str] = {}

        for lesson in context_data["lessons"]:
            lesson_id = lesson["lesson_id"]
            lesson_title = lesson["title"]
            text_content = lesson.get("text_content", "")

            # Build per-lesson text
            parts = []
            if text_content:
                parts.append(text_content)
            if lesson_id in pdf_texts:
                parts.append(pdf_texts[lesson_id])

            full_lesson_text = "\n\n".join(parts)
            if full_lesson_text.strip():
                lesson_texts[lesson_id] = full_lesson_text

            # Build section for combined text
            section = f"### Lesson: {lesson_title}\n{text_content}"
            if lesson_id in pdf_texts:
                section += f"\n\n#### PDF Resources:\n{pdf_texts[lesson_id]}"
            sections.append(section)

        combined_text = "\n\n".join(sections)

        return {
            "module_title": context_data["module_title"],
            "module_description": context_data["module_description"],
            "lessons": context_data["lessons"],
            "combined_text": combined_text,
            "lesson_texts": lesson_texts,
        }

    async def extract_course_content(
        self,
        course_id: int,
    ) -> dict | None:
        """Extract all text content for an entire course (all modules, all lessons).

        Returns:
            Dict with keys:
              - course_id: int
              - modules: list[dict] — each module's extraction result
              - total_lessons: int
            Returns None if course not found.
        """
        course_doc = await self.repo.get_course_content(course_id)
        if not course_doc:
            return None

        modules_data = []
        total_lessons = 0

        for module in course_doc.get("modules", []):
            module_id = module.get("module_id", "")
            module_result = await self.extract_module_content(course_id, module_id)
            if module_result:
                modules_data.append({
                    "module_id": module_id,
                    **module_result,
                })
                total_lessons += len(module_result.get("lesson_texts", {}))

        return {
            "course_id": course_id,
            "modules": modules_data,
            "total_lessons": total_lessons,
        }
```

### Refactor `services/instructor.py`

After creating `ContentExtractor`, update `InstructorService` to use it. Replace the duplicate fetch+extract+build logic in `_process_and_save_summary` and `_process_and_save_quiz`:

**Before** (in both methods):
```python
# Fetch module and lessons from MongoDB
context_data = await self.repo.get_module_with_lessons(...)
# Extract PDF text from lesson resources
pdf_texts = await self.resource_extractor.extract_text_from_lessons(...)
# Build enriched context with PDF content inline
sections = [...]
# ... 10 lines of section building ...
combined_text = "\n\n".join(sections)
```

**After** (in both methods):
```python
# Extract all content (MongoDB + PDFs) via centralized extractor
content = await self.content_extractor.extract_module_content(
    course_id, module_id, request.source_lesson_ids
)
if not content:
    await self.status_tracker.set_failed(...)
    return
combined_text = content["combined_text"]
```

Update `InstructorService.__init__` to accept `ContentExtractor`:
```python
def __init__(
    self,
    repo: CourseContentRepository,
    openai_client: OpenAIClient,
    course_client: CourseServiceClient,
    content_extractor: ContentExtractor,   # ← NEW (replaces resource_extractor)
    status_tracker: GenerationStatusTracker,
):
    self.repo = repo
    self.openai_client = openai_client
    self.course_client = course_client
    self.content_extractor = content_extractor  # ← NEW
    self.status_tracker = status_tracker
```

---

## 7. Text Chunking Strategy

### Create: `services/text_chunker.py` (NEW FILE)

```python
"""Text chunking for RAG indexing.

Splits lesson content into overlapping chunks suitable for embedding.
Uses LangChain's RecursiveCharacterTextSplitter which handles markdown,
paragraphs, and sentences intelligently.
"""

from dataclasses import dataclass
from langchain_text_splitters import RecursiveCharacterTextSplitter


@dataclass
class TextChunk:
    """A single chunk of text with its position metadata."""
    text: str
    chunk_index: int
    start_char: int
    end_char: int


# ── Configuration ─────────────────────────────────────────────
# text-embedding-3-small handles up to 8191 tokens.
# ~4 chars per token → 512 tokens ≈ 2048 chars.
# We use a conservative chunk size for better retrieval precision.
CHUNK_SIZE = 1500          # ~375 tokens per chunk
CHUNK_OVERLAP = 200        # ~50 tokens overlap (13%)

# Separators ordered from most to least preferred split point.
# The splitter tries the first separator, falls back to the next if chunks are still too big.
SEPARATORS = [
    "\n## ",      # Markdown H2 (module boundary)
    "\n### ",     # Markdown H3 (lesson boundary)
    "\n#### ",    # Markdown H4 (section boundary)
    "\n\n",       # Paragraph boundary
    "\n",         # Line boundary
    ". ",         # Sentence boundary
    " ",          # Word boundary
]


class TextChunker:
    """Splits text into overlapping chunks for RAG embedding."""

    def __init__(
        self,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
    ):
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=SEPARATORS,
            length_function=len,
            is_separator_regex=False,
        )

    def chunk_text(self, text: str) -> list[TextChunk]:
        """Split text into chunks with position tracking.

        Args:
            text: The full text to split.

        Returns:
            List of TextChunk objects with text, index, and character positions.
        """
        if not text or not text.strip():
            return []

        docs = self._splitter.create_documents([text])

        chunks: list[TextChunk] = []
        search_start = 0

        for i, doc in enumerate(docs):
            chunk_text = doc.page_content

            # Track character positions for debugging/reference
            start_char = text.find(chunk_text[:50], search_start)
            if start_char == -1:
                start_char = search_start
            end_char = start_char + len(chunk_text)
            search_start = max(search_start, start_char + 1)

            chunks.append(TextChunk(
                text=chunk_text,
                chunk_index=i,
                start_char=start_char,
                end_char=end_char,
            ))

        return chunks
```

### Why These Parameters?

| Parameter | Value | Reason |
|-----------|-------|--------|
| `chunk_size=1500` chars | ~375 tokens | Small enough for precise retrieval, large enough for context. The embedding model (8191 token limit) can handle much more, but smaller chunks = more precise matching. |
| `chunk_overlap=200` chars | ~50 tokens | 13% overlap ensures no information is lost at chunk boundaries. If a key concept spans two paragraphs, the overlap captures it in both chunks. |
| Separators | Markdown-aware | Respects your content structure: tries to split at headings first, then paragraphs, then sentences. Never splits mid-word. |

---

## 8. Embedding Generation

### Update: `clients/openai_client.py`

Add an `embed_texts` method to the existing `OpenAIClient`:

```python
# Add this method to the existing OpenAIClient class:

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts.

        Uses OpenAI's text-embedding-3-small model (1536 dimensions).
        Handles batching internally — OpenAI supports up to 2048 texts per request.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors (each is a list of 1536 floats).
            Order matches input texts.

        Raises:
            openai.OpenAIError: On API errors.
        """
        if not texts:
            return []

        try:
            response = await self.client.embeddings.create(
                model=settings.OPENAI_EMBEDDING_MODEL,
                input=texts,
            )

            # Sort by index to guarantee order matches input
            sorted_data = sorted(response.data, key=lambda x: x.index)
            return [item.embedding for item in sorted_data]

        except Exception as e:
            logger.error(
                "Failed to generate embeddings",
                error=str(e),
                model=settings.OPENAI_EMBEDDING_MODEL,
                num_texts=len(texts),
            )
            raise

    async def embed_query(self, query: str) -> list[float]:
        """Generate embedding for a single query string.

        Convenience method for search-time embedding (AI Tutor will use this).

        Args:
            query: The search query text.

        Returns:
            Embedding vector (list of 1536 floats).
        """
        result = await self.embed_texts([query])
        return result[0]
```

### Batching Strategy

The OpenAI embeddings API accepts up to **2048 texts per request** and up to **8191 tokens per text**. For a typical course:
- 200 chunks × 375 tokens each = ~75K tokens per batch
- Cost: ~$0.0015 (less than a penny)
- One API call handles the entire course

For very large courses (2000+ chunks), we'll batch in groups of 100 in the IndexService (covered in Step 10).

---

## 9. Vector Store Implementation (Qdrant)

### Rewrite: `repositories/vector_store.py`

Replace the stub with a full implementation:

```python
"""Vector store repository for Qdrant operations."""

import uuid
import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from ai_service.config import settings

logger = structlog.get_logger(__name__)

# Embedding dimension for text-embedding-3-small
EMBEDDING_DIMENSION = 1536


class VectorStoreRepository:
    """Qdrant vector store operations for RAG."""

    def __init__(self):
        self.client: AsyncQdrantClient | None = None
        self.collection_name = settings.QDRANT_COLLECTION

    async def connect(self) -> None:
        """Initialize async Qdrant client and ensure collection exists."""
        self.client = AsyncQdrantClient(url=settings.QDRANT_URL)

        # Create collection if it doesn't exist
        collections = await self.client.get_collections()
        existing_names = [c.name for c in collections.collections]

        if self.collection_name not in existing_names:
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIMENSION,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(
                "Created Qdrant collection",
                collection=self.collection_name,
                dimension=EMBEDDING_DIMENSION,
            )

            # Create payload indexes for fast filtering
            for field in ["course_id", "module_id", "lesson_id"]:
                await self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema="keyword",
                )

            logger.info("Created payload indexes for filtering")
        else:
            logger.info("Qdrant collection already exists", collection=self.collection_name)

    async def close(self) -> None:
        """Close the Qdrant client."""
        if self.client:
            await self.client.close()
            self.client = None

    async def upsert_chunks(
        self,
        course_id: int,
        module_id: str,
        lesson_id: str,
        chunks: list[dict],
    ) -> int:
        """Store embedding chunks with metadata.

        Args:
            course_id: Course ID
            module_id: Module ID (ObjectId hex string)
            lesson_id: Lesson ID (ObjectId hex string)
            chunks: List of dicts, each with:
                - text: str (the chunk text)
                - embedding: list[float] (the embedding vector)
                - chunk_index: int
                - lesson_title: str
                - module_title: str

        Returns:
            Number of points stored.
        """
        if not chunks:
            return 0

        points = []
        for chunk in chunks:
            point_id = str(uuid.uuid4())
            points.append(
                PointStruct(
                    id=point_id,
                    vector=chunk["embedding"],
                    payload={
                        "course_id": str(course_id),
                        "module_id": module_id,
                        "lesson_id": lesson_id,
                        "chunk_index": chunk["chunk_index"],
                        "lesson_title": chunk.get("lesson_title", ""),
                        "module_title": chunk.get("module_title", ""),
                        "text": chunk["text"],
                        # Preview for debugging (first 200 chars)
                        "preview": chunk["text"][:200],
                    },
                )
            )

        # Upsert in batches of 100 (Qdrant handles large batches well,
        # but batching avoids memory spikes for huge courses)
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            await self.client.upsert(
                collection_name=self.collection_name,
                points=batch,
            )

        logger.info(
            "Upserted chunks to Qdrant",
            course_id=course_id,
            module_id=module_id,
            lesson_id=lesson_id,
            num_chunks=len(points),
        )
        return len(points)

    async def search(
        self,
        query_embedding: list[float],
        course_id: int,
        module_id: str | None = None,
        lesson_id: str | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        """Search for relevant chunks by vector similarity.

        Args:
            query_embedding: The query embedding vector.
            course_id: Filter to this course.
            module_id: Optionally filter to a specific module.
            lesson_id: Optionally filter to a specific lesson.
            top_k: Number of results to return.

        Returns:
            List of dicts with: text, score, course_id, module_id, lesson_id,
            chunk_index, lesson_title, module_title.
        """
        # Build filter conditions
        must_conditions = [
            FieldCondition(key="course_id", match=MatchValue(value=str(course_id)))
        ]
        if module_id:
            must_conditions.append(
                FieldCondition(key="module_id", match=MatchValue(value=module_id))
            )
        if lesson_id:
            must_conditions.append(
                FieldCondition(key="lesson_id", match=MatchValue(value=lesson_id))
            )

        results = await self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            query_filter=Filter(must=must_conditions),
            limit=top_k,
            with_payload=True,
        )

        return [
            {
                "text": point.payload.get("text", ""),
                "score": point.score,
                "course_id": point.payload.get("course_id"),
                "module_id": point.payload.get("module_id"),
                "lesson_id": point.payload.get("lesson_id"),
                "chunk_index": point.payload.get("chunk_index"),
                "lesson_title": point.payload.get("lesson_title"),
                "module_title": point.payload.get("module_title"),
            }
            for point in results.points
        ]

    async def delete_course_vectors(self, course_id: int) -> None:
        """Delete all vectors for a course."""
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="course_id",
                        match=MatchValue(value=str(course_id)),
                    )
                ]
            ),
        )
        logger.info("Deleted course vectors from Qdrant", course_id=course_id)

    async def delete_module_vectors(self, course_id: int, module_id: str) -> None:
        """Delete all vectors for a module."""
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="course_id",
                        match=MatchValue(value=str(course_id)),
                    ),
                    FieldCondition(
                        key="module_id",
                        match=MatchValue(value=module_id),
                    ),
                ]
            ),
        )
        logger.info(
            "Deleted module vectors from Qdrant",
            course_id=course_id,
            module_id=module_id,
        )

    async def get_collection_info(self) -> dict:
        """Get collection stats (useful for status endpoint)."""
        info = await self.client.get_collection(self.collection_name)
        return {
            "total_points": info.points_count,
            "vectors_count": info.vectors_count,
            "status": info.status.value,
        }

    async def count_course_vectors(self, course_id: int) -> int:
        """Count vectors for a specific course."""
        result = await self.client.count(
            collection_name=self.collection_name,
            count_filter=Filter(
                must=[
                    FieldCondition(
                        key="course_id",
                        match=MatchValue(value=str(course_id)),
                    )
                ]
            ),
        )
        return result.count
```

### Metadata Design — Why These Fields?

| Field | Type | Why |
|-------|------|-----|
| `course_id` | keyword (string) | **Filter at search time**. A student in Course 101 should only search Course 101 vectors. Stored as string for Qdrant keyword filter compatibility. |
| `module_id` | keyword | **Scope search to current module** (optional). The AI Tutor can scope results to the module the student is currently studying. |
| `lesson_id` | keyword | **Granular filtering** and **re-indexing**. When a lesson PDF is updated, delete its old vectors and re-index just that lesson. |
| `chunk_index` | integer | **Ordering**. If the tutor retrieves chunks 3 and 5 from the same lesson, it can present them in order. |
| `lesson_title` | keyword | **Source attribution**. The tutor can say "Based on Lesson: Introduction to React..." |
| `module_title` | keyword | **Source attribution** at module level. |
| `text` | text | **The actual chunk text**. Returned with search results so the tutor can feed it to the LLM as context. |
| `preview` | text | **Debugging**. First 200 chars for quick inspection in Qdrant dashboard. |

---

## 10. Index Service Implementation

### Rewrite: `services/index.py`

Replace the stub with the full implementation:

```python
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
        asyncio.create_task(
            self._build_course_index_task(course_id, request.force_rebuild)
        )

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

    async def _build_course_index_task(
        self, course_id: int, force_rebuild: bool
    ) -> None:
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
            await self.status_tracker.set_failed(
                course_id, "course", "index", str(e)
            )

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
                    course_id, module_id, "index", "Module not found"
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
            await self.status_tracker.set_failed(
                course_id, module_id, "index", str(e)
            )

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
        lesson_title_map = {
            lesson["lesson_id"]: lesson.get("title", "")
            for lesson in lessons
        }

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
            status = IndexStatus(
                self._map_generation_to_index_status(redis_status["status"])
            )
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
            message=f"Index has {total_chunks} chunks." if total_chunks > 0 else "Index not built yet.",
        )

    async def get_module_status(self, course_id: int, module_id: str) -> IndexStatusResponse:
        """Get index status for a module."""
        redis_status = await self.status_tracker.get_status(course_id, module_id, "index")

        if redis_status:
            status = IndexStatus(
                self._map_generation_to_index_status(redis_status["status"])
            )
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
```

---

## 11. Index Status Tracking

The existing `GenerationStatusTracker` in `services/generation_status.py` already supports any `content_type` string. It uses Redis keys like:

```
generation_status:{course_id}:{module_id}:{content_type}
```

For indexing, we'll use:
- **Course-level**: `generation_status:{course_id}:course:index`
- **Module-level**: `generation_status:{course_id}:{module_id}:index`

**No changes needed** to `GenerationStatusTracker` — it already works generically. The `IndexService` above already calls it with `"index"` as the content type.

---

## 12. API Endpoints (Wire It Up)

### Update: `api/index.py`

The stub endpoints are already defined. We need to update them to inject the real `IndexService` with all its dependencies:

```python
"""RAG indexing API routes."""

from fastapi import APIRouter, Depends, status

from ai_service.api.dependencies import require_instructor, get_index_service
from ai_service.schemas.index import (
    BuildIndexRequest,
    IndexBuildResponse,
    IndexStatusResponse,
)
from ai_service.services.index import IndexService

router = APIRouter()


@router.post(
    "/courses/{course_id}/build",
    response_model=IndexBuildResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def build_course_index(
    course_id: int,
    request: BuildIndexRequest | None = None,
    user_id: int = Depends(require_instructor),
    index_service: IndexService = Depends(get_index_service),
) -> IndexBuildResponse:
    """Build RAG index for an entire course."""
    if request is None:
        request = BuildIndexRequest(force_rebuild=False)
    return await index_service.build_course_index(course_id, request)


@router.post(
    "/modules/{module_id}/build",
    response_model=IndexBuildResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def build_module_index(
    module_id: str,
    course_id: int,
    request: BuildIndexRequest | None = None,
    user_id: int = Depends(require_instructor),
    index_service: IndexService = Depends(get_index_service),
) -> IndexBuildResponse:
    """Build RAG index for a single module."""
    if request is None:
        request = BuildIndexRequest(force_rebuild=False)
    return await index_service.build_module_index(course_id, module_id, request)


@router.get(
    "/courses/{course_id}/status",
    response_model=IndexStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_course_index_status(
    course_id: int,
    user_id: int = Depends(require_instructor),
    index_service: IndexService = Depends(get_index_service),
) -> IndexStatusResponse:
    """Get RAG index status for a course."""
    return await index_service.get_course_status(course_id)


@router.get(
    "/modules/{module_id}/status",
    response_model=IndexStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_module_index_status(
    module_id: str,
    course_id: int,
    user_id: int = Depends(require_instructor),
    index_service: IndexService = Depends(get_index_service),
) -> IndexStatusResponse:
    """Get RAG index status for a module."""
    return await index_service.get_module_status(course_id, module_id)
```

### Update: `api/dependencies.py`

Add a dependency provider for `IndexService`:

```python
# Add these imports at the top:
from ai_service.services.index import IndexService
from ai_service.services.content_extractor import ContentExtractor
from ai_service.services.text_chunker import TextChunker
from ai_service.clients.openai_client import OpenAIClient
from ai_service.repositories.course_content import CourseContentRepository
from ai_service.repositories.vector_store import VectorStoreRepository
from ai_service.clients.resource_extractor import ResourceTextExtractor
from ai_service.services.generation_status import GenerationStatusTracker
from ai_service.core.mongodb import get_database
from ai_service.core.redis import get_redis

# Add this at module level (singleton-ish pattern matching existing code):
_vector_store: VectorStoreRepository | None = None

def set_vector_store(vs: VectorStoreRepository) -> None:
    """Called during app startup to set the vector store singleton."""
    global _vector_store
    _vector_store = vs

def get_index_service() -> IndexService:
    """FastAPI dependency that builds IndexService with all its dependencies."""
    db = get_database()
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
```

---

## 13. Startup/Lifespan Changes

### Update: `main.py`

Add Qdrant initialization to the app lifespan:

```python
"""AI Service main FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ai_service.api.router import router
from ai_service.config import settings
from ai_service.core.mongodb import connect_mongodb, close_mongodb
from ai_service.core.redis import connect_redis, close_redis, get_redis
from ai_service.repositories.vector_store import VectorStoreRepository
from ai_service.api.dependencies import set_vector_store

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Module-level reference for cleanup
_vector_store: VectorStoreRepository | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    global _vector_store

    await connect_mongodb(settings.MONGODB_URL, settings.MONGODB_DB_NAME)
    await connect_redis(settings.REDIS_URL)

    # Initialize Qdrant vector store
    _vector_store = VectorStoreRepository()
    await _vector_store.connect()
    set_vector_store(_vector_store)

    logger.info("AI Service startup complete (MongoDB + Redis + Qdrant)")

    yield

    logger.info("AI Service shutting down")
    if _vector_store:
        await _vector_store.close()
    await close_redis()
    await close_mongodb()


app = FastAPI(
    title="SmartCourse AI Service",
    description="AI-powered content generation, tutoring, and indexing",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/health")
async def health_check():
    """Health check endpoint with dependency status."""
    redis_ok = False
    client = get_redis()
    if client:
        try:
            await client.ping()
            redis_ok = True
        except Exception:
            pass

    qdrant_ok = False
    if _vector_store and _vector_store.client:
        try:
            await _vector_store.client.get_collections()
            qdrant_ok = True
        except Exception:
            pass

    return {
        "status": "ok",
        "service": "ai-service",
        "dependencies": {
            "redis": "connected" if redis_ok else "disconnected",
            "qdrant": "connected" if qdrant_ok else "disconnected",
        },
    }
```

---

## 14. File-by-File Summary

Here's every file you need to create or modify, in order:

### New Files (Create)

| # | File | Purpose |
|---|------|---------|
| 1 | `services/content_extractor.py` | Centralized content fetching (MongoDB + PDF). Reused by InstructorService and IndexService. |
| 2 | `services/text_chunker.py` | Splits text into overlapping chunks using `RecursiveCharacterTextSplitter`. |

### Modified Files (Edit)

| # | File | What Changes |
|---|------|-------------|
| 3 | `docker-compose.yml` (project root) | Add `qdrant` service + `qdrant_data` volume + ai-service depends_on qdrant. |
| 4 | `pyproject.toml` | Add `qdrant-client>=1.12.0` and `langchain-text-splitters>=0.3.0` to dependencies. |
| 5 | `clients/openai_client.py` | Add `embed_texts()` and `embed_query()` methods to `OpenAIClient`. |
| 6 | `repositories/vector_store.py` | Full rewrite: Qdrant connect, upsert, search, delete, count. |
| 7 | `services/index.py` | Full rewrite: background index building with chunk→embed→store pipeline. |
| 8 | `api/index.py` | Wire endpoints to real IndexService via dependency injection. |
| 9 | `api/dependencies.py` | Add `get_index_service()` and `set_vector_store()`. |
| 10 | `main.py` | Add Qdrant init/cleanup to lifespan + health check. |
| 11 | `services/instructor.py` | Refactor to use `ContentExtractor` (removes duplicate code). |

### Files That Stay Unchanged

- `config.py` — Already has `QDRANT_URL`, `QDRANT_COLLECTION`, `OPENAI_EMBEDDING_MODEL`
- `schemas/index.py` — Already has `BuildIndexRequest`, `IndexBuildResponse`, `IndexStatusResponse`
- `schemas/common.py` — Already has `IndexStatus` enum
- `services/generation_status.py` — Already generic enough for index status
- `clients/resource_extractor.py` — Used as-is inside ContentExtractor
- `repositories/course_content.py` — Used as-is inside ContentExtractor

---

## 15. Testing the Pipeline

### Step 1: Start infrastructure

```bash
docker compose up -d qdrant mongodb redis
```

### Step 2: Verify Qdrant is healthy

```bash
curl http://localhost:6333/healthz
# → {"title":"qdrant - vector engine","version":"...","status":"ok"}
```

### Step 3: Start ai-service

```bash
docker compose up -d ai-service
# Check logs:
docker compose logs -f ai-service
# Should see: "Created Qdrant collection" and "AI Service startup complete"
```

### Step 4: Trigger a course index build

```bash
curl -X POST http://localhost:8000/api/v1/ai/index/courses/1/build \
  -H "X-User-ID: 1" \
  -H "X-User-Role: instructor" \
  -H "Content-Type: application/json" \
  -d '{"force_rebuild": true}'

# → 202 Accepted
# {
#   "course_id": 1,
#   "status": "pending",
#   "message": "Course index build started. Poll the status endpoint to track progress."
# }
```

### Step 5: Poll status

```bash
curl http://localhost:8000/api/v1/ai/index/courses/1/status \
  -H "X-User-ID: 1" \
  -H "X-User-Role: instructor"

# → 200 OK
# {
#   "course_id": 1,
#   "status": "indexed",
#   "total_chunks": 47,
#   "embedding_model": "text-embedding-3-small",
#   "message": "Index has 47 chunks."
# }
```

### Step 6: Verify in Qdrant Dashboard

Open http://localhost:6333/dashboard in your browser. You should see:
- Collection `course_embeddings` with points
- Each point has payload with `course_id`, `module_id`, `lesson_id`, `text`

### Step 7: Quick search test (optional, for validation)

```python
# Quick Python script to test search works:
import asyncio
from qdrant_client import AsyncQdrantClient
from openai import AsyncOpenAI

async def test_search():
    openai = AsyncOpenAI(api_key="your-key")
    qdrant = AsyncQdrantClient(url="http://localhost:6333")

    # Embed a test query
    resp = await openai.embeddings.create(
        model="text-embedding-3-small",
        input=["What is machine learning?"]
    )
    query_vec = resp.data[0].embedding

    # Search
    results = await qdrant.query_points(
        collection_name="course_embeddings",
        query=query_vec,
        limit=3,
        with_payload=True,
    )
    for r in results.points:
        print(f"Score: {r.score:.4f} | {r.payload['lesson_title']}: {r.payload['preview']}")

asyncio.run(test_search())
```

---

## 16. What Comes Next (AI Tutor with LangGraph)

This session focused on **indexing** (getting content into the vector DB). The next session will cover the **retrieval + generation** side using LangGraph:

```
Student asks a question
        │
        ▼
┌───────────────────┐
│  LangGraph Agent  │
│  (State Machine)  │
│                   │
│  States:          │
│  1. RECEIVE_QUERY │ ─── Student's question
│  2. EMBED_QUERY   │ ─── OpenAI embed_query()
│  3. RETRIEVE      │ ─── Qdrant search (top 5 chunks)
│  4. GENERATE      │ ─── GPT-4o-mini with retrieved context
│  5. RESPOND       │ ─── Stream response to student
│                   │
│  Tools:           │
│  - qdrant_search  │
│  - scope_filter   │ ─── Filter by course/module/lesson
│                   │
└───────────────────┘
```

**What you'll need for the next session:**
- `langgraph` package
- `langchain-openai` (for LangGraph's LLM integration)
- Tutor session management (conversation history in Redis/MongoDB)
- Streaming responses via SSE (Server-Sent Events)

**The index you build today is the foundation.** The AI Tutor will call `vector_store.search()` and `openai_client.embed_query()` — both of which you'll have implemented after following this guide.

---

## Quick Reference: Implementation Order

Follow this order to minimize back-and-forth:

1. **Infrastructure** — Add Qdrant to docker-compose, start it
2. **Dependencies** — Add `qdrant-client` and `langchain-text-splitters` to pyproject.toml
3. **Content Extractor** — Create `services/content_extractor.py` (centralized content pipeline)
4. **Text Chunker** — Create `services/text_chunker.py`
5. **OpenAI Embeddings** — Add `embed_texts()` / `embed_query()` to `clients/openai_client.py`
6. **Vector Store** — Rewrite `repositories/vector_store.py` (Qdrant CRUD)
7. **Index Service** — Rewrite `services/index.py` (orchestrator)
8. **Dependencies DI** — Update `api/dependencies.py` (add `get_index_service`)
9. **API Endpoints** — Update `api/index.py` (wire to real service)
10. **App Startup** — Update `main.py` (Qdrant lifecycle + health)
11. **Refactor Instructor** — Update `services/instructor.py` to use `ContentExtractor`
12. **Test** — Trigger build, poll status, verify in Qdrant dashboard
