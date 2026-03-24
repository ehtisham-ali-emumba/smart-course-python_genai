# Implementation Plan: Centralized PDF Content Pipeline via LangGraph

## Overview

This plan reorganizes `text_chunker`, `resource_extractor`, and `content_extractor` into a shared `content_pipeline/` package, replaces manual PyMuPDF parsing with LangChain's `PyMuPDFLoader` wrapped as a LangGraph node (including image understanding via GPT-4o vision), and makes both the **instructor flow** (quiz/summary) and the **index flow** (RAG) use the same centralized content extraction graph node.

---

## Current Problems

1. **Scattered files**: `text_chunker.py` lives in `services/`, `resource_extractor.py` lives in `clients/`, `content_extractor.py` lives in `services/` — no cohesion.
2. **Manual PDF parsing**: `ResourceTextExtractor` uses raw PyMuPDF to extract text — no image handling, no LangGraph involvement.
3. **Images ignored**: PDFs with images produce no visual context — only raw text is extracted.
4. **Inconsistent extraction placement**: Instructor graphs run `extract_content` as a LangGraph node. Index flow runs `ContentExtractor` *outside* the graph and passes `lesson_texts` into the graph state — this asymmetry makes it harder to centralize and reuse.

---

## Target Architecture

```
services/ai-service/src/ai_service/
├── services/
│   ├── content_pipeline/          # NEW — grouped package
│   │   ├── __init__.py            # Re-exports: ContentExtractionGraph, TextChunker, etc.
│   │   ├── pdf_processor.py       # NEW — LangGraph nodes for PDF download + extraction + vision
│   │   ├── content_extractor.py   # MOVED from services/content_extractor.py (refactored)
│   │   └── text_chunker.py        # MOVED from services/text_chunker.py (unchanged logic)
│   ├── instructor_graphs.py       # MODIFIED — uses shared extract_content subgraph
│   ├── index_graph.py             # MODIFIED — extract_content is now a graph node (no longer outside)
│   ├── index.py                   # MODIFIED — no longer calls content_extractor before graph
│   ├── instructor.py              # MINOR — import path changes only
│   └── ...
├── clients/
│   ├── resource_extractor.py      # DELETED — replaced by content_pipeline/pdf_processor.py
│   └── ...
```

---

## Step-by-Step Implementation

### Step 1: Create the `content_pipeline/` package

Create directory: `services/ai-service/src/ai_service/services/content_pipeline/`

#### File: `__init__.py`

```python
"""Centralized content extraction pipeline.

Groups PDF processing, content extraction, and text chunking into a
single cohesive package used by both instructor and index flows.
"""

from ai_service.services.content_pipeline.text_chunker import TextChunker, TextChunk
from ai_service.services.content_pipeline.content_extractor import ContentExtractor
from ai_service.services.content_pipeline.pdf_processor import (
    build_pdf_extraction_node,
    PDFExtractionResult,
)

__all__ = [
    "TextChunker",
    "TextChunk",
    "ContentExtractor",
    "build_pdf_extraction_node",
    "PDFExtractionResult",
]
```

---

### Step 2: Move `text_chunker.py` into the new package

Move `services/text_chunker.py` -> `services/content_pipeline/text_chunker.py`

**No code changes needed** — the file stays exactly the same. Only the import path changes from:
```python
from ai_service.services.text_chunker import TextChunker
```
to:
```python
from ai_service.services.content_pipeline import TextChunker
```

---

### Step 3: Add `describe_image` method to `OpenAIClient`

Add this method to `clients/openai_client.py` in the `OpenAIClient` class (after the existing `chat_completion` method):

```python
IMAGE_DESCRIPTION_MAX_TOKENS = 300

async def describe_image(self, base64_image: str) -> str:
    """Describe an image using GPT-4o vision.

    Used by the PDF processor to understand images extracted from course PDFs.

    Args:
        base64_image: Base64-encoded image string (PNG format).

    Returns:
        Text description of the image.

    Raises:
        openai.OpenAIError: On API errors.
    """
    try:
        response = await self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Describe this image from a course PDF. "
                                "If it is a chart, graph, or diagram, describe: "
                                "the type of visualization, axes/labels, data trends, "
                                "and key takeaways. If it is a photo or illustration, "
                                "describe what it shows and its educational relevance. "
                                "Be concise but thorough."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
            max_tokens=IMAGE_DESCRIPTION_MAX_TOKENS,
        )

        result = response.choices[0].message.content
        if result is None:
            raise ValueError("OpenAI returned empty response for image description")
        return result.strip()

    except Exception as e:
        logger.error("Failed to describe image", error=str(e))
        raise
```

---

### Step 4: Create `pdf_processor.py` — LangChain loader + GPT-4o vision as LangGraph node

This is the core new file. Instead of manually calling PyMuPDF APIs, we use **`PyMuPDFLoader`** from `langchain-community` — the LangChain document loader built on top of PyMuPDF. It handles:
- Text extraction per page -> `Document` objects with metadata
- Image extraction via `extract_images=True` -> base64 images in document metadata

We then send extracted images to GPT-4o vision for understanding, and wrap the whole thing as a LangGraph node factory.

**Why `PyMuPDFLoader` specifically?**
- It's the fastest LangChain PDF loader (uses PyMuPDF/fitz under the hood — which you already have)
- Supports `extract_images=True` out of the box — returns base64 images in `Document.metadata["images"]`
- Returns structured `Document` objects with page numbers, source metadata
- Works with in-memory bytes via `Blob` — no need to save temp files
- Async support via `.alazy_load()`

**New dependency needed:**
```bash
pip install langchain-community
```
Add to `pyproject.toml`:
```toml
"langchain-community>=0.3.0",
```

#### File: `services/content_pipeline/pdf_processor.py`

```python
"""LangChain + LangGraph PDF processing with image understanding via GPT-4o vision.

Uses PyMuPDFLoader (from langchain-community) for text + image extraction,
then sends extracted images to GPT-4o vision for understanding.

This replaces the old clients/resource_extractor.py which used raw PyMuPDF calls.
"""

import httpx
import structlog
from dataclasses import dataclass, field
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_core.documents import Document, Blob

from ai_service.clients.openai_client import OpenAIClient

logger = structlog.get_logger(__name__)

# ── Configuration ──────────────────────────────────────────────────

PDF_MIME_TYPES = {"pdf", "application/pdf"}
MAX_PDF_SIZE_MB = 50
MAX_PAGES_PER_PDF = 200
MAX_CHARS_PER_RESOURCE = 50_000   # ~12,500 tokens safety cap
MAX_IMAGES_PER_PDF = 20           # Safety cap on images to process
MIN_IMAGE_SIZE_BYTES = 5_000      # Skip tiny decorative images (~icons, bullets)
IMAGE_DESCRIPTION_MAX_TOKENS = 300


# ── Data Models ────────────────────────────────────────────────────


@dataclass
class ExtractedImage:
    """An image extracted from a PDF with its AI-generated description."""
    page_number: int
    image_index: int
    description: str


@dataclass
class PDFExtractionResult:
    """Complete extraction result for a single PDF resource."""
    resource_name: str
    text: str
    images: list[ExtractedImage] = field(default_factory=list)

    @property
    def combined_text(self) -> str:
        """Merge extracted text and image descriptions into one block."""
        parts = []
        if self.text:
            parts.append(self.text)
        for img in self.images:
            parts.append(
                f"\n[Image on page {img.page_number}: {img.description}]"
            )
        return "\n\n".join(parts)


# ── PDF Download ───────────────────────────────────────────────────


async def _download_pdf(
    client: httpx.AsyncClient, url: str, name: str
) -> bytes | None:
    """Download a PDF, return raw bytes or None on failure."""
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        if len(resp.content) > MAX_PDF_SIZE_MB * 1024 * 1024:
            logger.warning("PDF too large, skipping", name=name,
                           size_mb=len(resp.content) / (1024 * 1024))
            return None
        return resp.content
    except httpx.HTTPError as e:
        logger.warning("Failed to download PDF", name=name, error=str(e))
        return None


# ── LangChain Loader: Text + Image Extraction ─────────────────────


async def _load_pdf_with_langchain(
    pdf_bytes: bytes, name: str
) -> tuple[list[Document], list[dict]]:
    """Use PyMuPDFLoader to extract text documents and images from PDF bytes.

    PyMuPDFLoader with extract_images=True returns:
      - Document.page_content: the text of each page
      - Document.metadata["images"]: list of base64-encoded images on that page

    Args:
        pdf_bytes: Raw PDF bytes (downloaded from URL).
        name: Resource name for logging.

    Returns:
        Tuple of:
          - text_docs: List of Document objects (one per page) with page text
          - images: List of dicts {page_number, image_index, base64_image}
    """
    try:
        # Create a Blob from in-memory bytes — no temp file needed
        blob = Blob(data=pdf_bytes, mime_type="application/pdf")

        # PyMuPDFLoader can parse from a Blob via .lazy_parse()
        loader = PyMuPDFLoader(
            file_path="",  # Not used when parsing from blob
            extract_images=True,
        )

        text_docs: list[Document] = []
        images: list[dict] = []
        total_chars = 0
        image_count = 0

        # Use lazy_parse with the blob for async-friendly loading
        for doc in loader.lazy_parse(blob):
            page_num = doc.metadata.get("page", len(text_docs))

            # Respect page limit
            if page_num >= MAX_PAGES_PER_PDF:
                break

            # Collect text
            text_docs.append(doc)
            total_chars += len(doc.page_content)

            # Collect images from metadata (PyMuPDFLoader puts them here)
            page_images = doc.metadata.get("images", [])
            for img_idx, img_b64 in enumerate(page_images):
                if image_count >= MAX_IMAGES_PER_PDF:
                    break

                # Skip tiny images (likely decorative)
                # base64 is ~1.33x the byte size, so 5000 base64 chars ≈ 3750 bytes
                if isinstance(img_b64, str) and len(img_b64) < MIN_IMAGE_SIZE_BYTES:
                    continue

                images.append({
                    "page_number": page_num + 1,  # 1-indexed for display
                    "image_index": img_idx,
                    "base64_image": img_b64 if isinstance(img_b64, str) else "",
                })
                image_count += 1

            # Respect char limit
            if total_chars >= MAX_CHARS_PER_RESOURCE:
                logger.info("PDF text cap reached, truncating", name=name,
                            pages_read=page_num + 1)
                break

        logger.info(
            "PyMuPDFLoader extraction complete",
            name=name,
            pages=len(text_docs),
            images=len(images),
            total_chars=total_chars,
        )
        return text_docs, images

    except Exception as e:
        logger.warning("PyMuPDFLoader failed", name=name, error=str(e))
        return [], []


# ── GPT-4o Vision: Image Understanding ────────────────────────────


async def _describe_image_with_vision(
    openai_client: OpenAIClient,
    base64_image: str,
) -> str:
    """Send a single image to GPT-4o vision via OpenAIClient.describe_image()."""
    try:
        return await openai_client.describe_image(base64_image)
    except Exception as e:
        logger.warning("Vision API failed for image", error=str(e))
        return "Image could not be described."


# ── Single PDF Pipeline ───────────────────────────────────────────


async def _process_single_pdf(
    http_client: httpx.AsyncClient,
    openai_client: OpenAIClient,
    url: str,
    name: str,
) -> PDFExtractionResult | None:
    """Full pipeline for one PDF: download -> LangChain load -> vision describe.

    1. Download PDF bytes via httpx
    2. Parse with PyMuPDFLoader (text + images)
    3. Send images to GPT-4o vision for descriptions
    4. Return combined result
    """
    # 1. Download
    pdf_bytes = await _download_pdf(http_client, url, name)
    if not pdf_bytes:
        return None

    # 2. Extract text + images via LangChain PyMuPDFLoader
    text_docs, raw_images = await _load_pdf_with_langchain(pdf_bytes, name)

    # Combine page texts into one string
    text = "\n".join(doc.page_content for doc in text_docs).strip()
    if text:
        text = text[:MAX_CHARS_PER_RESOURCE]

    # 3. Describe images via GPT-4o vision
    described_images: list[ExtractedImage] = []
    for img_data in raw_images:
        if not img_data["base64_image"]:
            continue
        description = await _describe_image_with_vision(
            openai_client, img_data["base64_image"]
        )
        described_images.append(
            ExtractedImage(
                page_number=img_data["page_number"],
                image_index=img_data["image_index"],
                description=description,
            )
        )

    if not text and not described_images:
        return None

    return PDFExtractionResult(
        resource_name=name,
        text=text,
        images=described_images,
    )


# ── Public API: LangGraph Node Factory ─────────────────────────────


def build_pdf_extraction_node(openai_client: OpenAIClient):
    """Factory that returns an async function usable as a LangGraph node.

    The returned node expects the graph state to have a `lessons` field
    (list[dict] with lesson_id, title, resources) and returns
    `pdf_texts`: dict[lesson_id -> combined extracted text].

    Usage in a LangGraph StateGraph:
        graph.add_node("extract_pdfs", build_pdf_extraction_node(openai_client))
    """

    async def extract_pdfs(state: dict) -> dict:
        """Download and extract content from all PDF resources across lessons.

        Uses LangChain PyMuPDFLoader for text + image extraction,
        GPT-4o vision for image understanding.
        """
        lessons = state.get("lessons", [])
        log = logger.bind(num_lessons=len(lessons))
        log.info("[PDF_PROCESSOR] Starting PDF extraction for all lessons")

        pdf_texts: dict[str, str] = {}

        async with httpx.AsyncClient(
            timeout=60.0,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        ) as http_client:
            for lesson in lessons:
                lesson_id = lesson["lesson_id"]
                resources = lesson.get("resources", [])
                pdf_resources = [
                    r for r in resources
                    if r.get("is_active", True)
                    and r.get("type", "").lower() in PDF_MIME_TYPES
                    and r.get("url", "")
                ]

                if not pdf_resources:
                    continue

                lesson_parts: list[str] = []
                for resource in pdf_resources:
                    result = await _process_single_pdf(
                        http_client,
                        openai_client,
                        resource["url"],
                        resource.get("name", "unknown"),
                    )
                    if result:
                        lesson_parts.append(
                            f"[Resource: {result.resource_name}]\n{result.combined_text}"
                        )

                if lesson_parts:
                    pdf_texts[lesson_id] = "\n\n".join(lesson_parts)

        log.info(
            "[PDF_PROCESSOR] PDF extraction complete",
            lessons_with_pdfs=len(pdf_texts),
        )
        return {"pdf_texts": pdf_texts}

    return extract_pdfs
```

**Why this approach uses LangChain properly:**

| What | Before (manual) | After (LangChain) |
|---|---|---|
| Text extraction | `fitz.open()` + `page.get_text("text")` | `PyMuPDFLoader.lazy_parse(blob)` -> `Document.page_content` |
| Image extraction | `page.get_images()` + `doc.extract_image()` + `Pixmap` + manual base64 | `PyMuPDFLoader(extract_images=True)` -> `Document.metadata["images"]` |
| Page metadata | Manual page number tracking | Automatic `Document.metadata["page"]`, `source`, etc. |
| In-memory loading | `fitz.open(stream=bytes)` | `Blob(data=bytes)` + `loader.lazy_parse(blob)` |
| Error handling | Manual try/except around fitz | LangChain handles internally, we wrap at the top level |

The only "manual" part left is the GPT-4o vision call — there's no LangChain loader that auto-describes images with an LLM, so that's our custom node logic. This is the standard pattern in LangChain/LangGraph: **loader extracts raw content, custom node adds AI understanding**.

---

### Step 5: Refactor `content_extractor.py` into the pipeline package

Move `services/content_extractor.py` -> `services/content_pipeline/content_extractor.py`

The key change: **remove the dependency on `ResourceTextExtractor`**. The content extractor now only fetches data from MongoDB. PDF extraction is handled by the LangGraph `extract_pdfs` node, and the content extractor focuses on building the combined text from MongoDB text + already-extracted PDF text that flows through the graph state.

#### File: `services/content_pipeline/content_extractor.py`

```python
"""Centralized content extraction for course materials.

Responsible for:
  1. Fetching course/module/lesson data from MongoDB
  2. Combining inline text content with PDF-extracted text (provided via state)
  3. Building structured output for downstream LLM or embedding consumption

Used as a LangGraph node factory — both instructor and index flows
call build_extract_content_node() to get a shared node.
"""

import structlog
import uuid as _uuid

from ai_service.repositories.course_content import CourseContentRepository

logger = structlog.get_logger(__name__)


class ContentExtractor:
    """Fetches course content from MongoDB and combines with extracted PDF text."""

    def __init__(self, repo: CourseContentRepository):
        self.repo = repo

    async def fetch_module_data(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        lesson_ids: list[str] | None = None,
    ) -> dict | None:
        """Fetch raw module + lessons from MongoDB (no PDF processing).

        Returns:
            Dict with keys: module_title, module_description, lessons
            Returns None if module not found.
        """
        context_data = await self.repo.get_module_with_lessons(
            course_id, module_id, lesson_ids
        )
        if not context_data:
            return None
        return context_data

    async def fetch_course_data(
        self,
        course_id: _uuid.UUID,
    ) -> dict | None:
        """Fetch all modules and lessons for a course from MongoDB.

        Returns:
            Dict with keys: course_id, modules (list of module data dicts)
            Returns None if course not found.
        """
        course_doc = await self.repo.get_course_content(course_id)
        if not course_doc:
            return None

        modules_data = []
        for module in course_doc.get("modules", []):
            module_id = module.get("module_id", "")
            module_data = await self.fetch_module_data(course_id, module_id)
            if module_data:
                modules_data.append({"module_id": module_id, **module_data})

        return {"course_id": course_id, "modules": modules_data}

    @staticmethod
    def build_combined_text(
        module_data: dict,
        pdf_texts: dict[str, str],
    ) -> tuple[str, dict[str, str]]:
        """Combine MongoDB text + PDF-extracted text into final output.

        Args:
            module_data: Dict from fetch_module_data() with module_title,
                         module_description, lessons.
            pdf_texts:   Dict mapping lesson_id -> extracted PDF text
                         (produced by the extract_pdfs LangGraph node).

        Returns:
            Tuple of:
              - combined_text: Full markdown-formatted text block
              - lesson_texts: Dict mapping lesson_id -> per-lesson full text
        """
        sections = [
            f"## Module: {module_data['module_title']}\n"
            f"{module_data['module_description']}"
        ]
        lesson_texts: dict[str, str] = {}

        for lesson in module_data["lessons"]:
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
        return combined_text, lesson_texts


def build_extract_content_node(content_extractor: ContentExtractor):
    """Factory for a LangGraph node that fetches MongoDB data + merges PDF text.

    This node expects the graph state to already have `pdf_texts` populated
    by the upstream `extract_pdfs` node. It reads from MongoDB and combines.

    State requirements:
        Input:  course_id, module_id, source_lesson_ids (optional), pdf_texts
        Output: combined_text, lesson_texts, lessons, module_title, module_description
    """

    async def extract_content(state: dict) -> dict:
        course_id = state["course_id"]
        module_id = state["module_id"]
        source_lesson_ids = state.get("source_lesson_ids")
        pdf_texts = state.get("pdf_texts", {})

        log = logger.bind(course_id=course_id, module_id=module_id)
        log.info("[EXTRACT_CONTENT] Fetching module data from MongoDB")

        try:
            module_data = await content_extractor.fetch_module_data(
                course_id, module_id, source_lesson_ids
            )
            if not module_data:
                return {
                    "combined_text": "",
                    "error": "Module not found or has no content",
                }

            combined_text, lesson_texts = ContentExtractor.build_combined_text(
                module_data, pdf_texts
            )

            if not combined_text.strip():
                return {
                    "combined_text": "",
                    "error": "Module has no extractable content",
                }

            log.info(
                "[EXTRACT_CONTENT] Content built successfully",
                text_length=len(combined_text),
                num_lesson_texts=len(lesson_texts),
            )
            return {
                "combined_text": combined_text,
                "lesson_texts": lesson_texts,
                "lessons": module_data["lessons"],
                "module_title": module_data["module_title"],
                "module_description": module_data["module_description"],
            }

        except Exception as e:
            log.exception("[EXTRACT_CONTENT] Error", error=str(e))
            return {"error": str(e)}

    return extract_content
```

---

### Step 6: Refactor `instructor_graphs.py` — use the shared pipeline nodes

The instructor graphs currently have their own `_build_extract_content_node`. Replace it with the two shared nodes: `extract_pdfs` -> `extract_content`.

#### Changes to `instructor_graphs.py`:

**1. Update imports:**
```python
# REMOVE this:
from ai_service.services.content_extractor import ContentExtractor

# ADD these:
from ai_service.services.content_pipeline.content_extractor import (
    ContentExtractor,
    build_extract_content_node,
)
from ai_service.services.content_pipeline.pdf_processor import build_pdf_extraction_node
```

**2. Add `pdf_texts` and `lessons` fields to `QuizState` and `SummaryState`:**
```python
class QuizState(TypedDict):
    # ... existing fields ...
    lessons: list[dict]           # ADD — raw lesson data from MongoDB
    pdf_texts: dict[str, str]     # ADD — lesson_id -> PDF text from extract_pdfs node
    # combined_text already exists — no change

class SummaryState(TypedDict):
    # ... existing fields ...
    lessons: list[dict]           # ADD
    pdf_texts: dict[str, str]     # ADD
```

**3. Add a new `fetch_lessons` node** that loads lessons from MongoDB (needed before extract_pdfs can run):
```python
def _build_fetch_lessons_node(content_extractor: ContentExtractor):
    """Fetch lesson metadata from MongoDB so the PDF extractor knows what to download."""

    async def fetch_lessons(state: dict) -> dict:
        course_id = state["course_id"]
        module_id = state["module_id"]
        source_lesson_ids = state.get("source_lesson_ids")

        log = logger.bind(course_id=course_id, module_id=module_id)
        log.info("[FETCH_LESSONS] Loading lesson data from MongoDB")

        try:
            module_data = await content_extractor.fetch_module_data(
                course_id, module_id, source_lesson_ids
            )
            if not module_data:
                return {"error": "Module not found or has no content"}

            return {"lessons": module_data["lessons"]}
        except Exception as e:
            log.exception("[FETCH_LESSONS] Error", error=str(e))
            return {"error": str(e)}

    return fetch_lessons
```

**4. Delete the old `_build_extract_content_node` function entirely** — it's replaced by the pipeline.

**5. Update `build_quiz_graph`:**
```python
def build_quiz_graph(
    openai_client: OpenAIClient,
    course_client: CourseServiceClient,
    content_extractor: ContentExtractor,
) -> CompiledStateGraph:
    # Create nodes
    fetch_lessons_node = _build_fetch_lessons_node(content_extractor)
    extract_pdfs_node = build_pdf_extraction_node(openai_client)
    extract_content_node = build_extract_content_node(content_extractor)
    generate_node = _build_generate_quiz_node(openai_client)
    validate_node = _build_validate_quiz_node()
    persist_node = _build_persist_quiz_node(course_client)

    graph = StateGraph(QuizState)

    # Nodes
    graph.add_node("fetch_lessons", fetch_lessons_node)
    graph.add_node("extract_pdfs", extract_pdfs_node)
    graph.add_node("extract_content", extract_content_node)
    graph.add_node("generate_quiz", generate_node)
    graph.add_node("validate_quiz", validate_node)
    graph.add_node("persist_quiz", persist_node)

    # Edges — NEW flow:
    # START -> fetch_lessons -> extract_pdfs -> extract_content -> generate_quiz -> ...
    graph.add_edge(START, "fetch_lessons")

    def _error_check(next_node):
        def router(state):
            return END if state.get("error") else next_node
        return router

    graph.add_conditional_edges("fetch_lessons", _error_check("extract_pdfs"))
    graph.add_edge("extract_pdfs", "extract_content")
    graph.add_conditional_edges("extract_content", _error_check("generate_quiz"))
    graph.add_edge("generate_quiz", "validate_quiz")
    graph.add_conditional_edges("validate_quiz", _quiz_validation_router)
    graph.add_edge("persist_quiz", END)

    return graph.compile()
```

**6. Apply the same pattern to `build_summary_graph`** — identical node additions and edge wiring, just with `generate_summary` / `validate_summary` / `persist_summary` instead.

---

### Step 7: Refactor `index_graph.py` — add content extraction inside the graph

Currently, `IndexService` calls `content_extractor.extract_module_content()` *before* invoking the graph and passes `lesson_texts` in the initial state. We want extraction inside the graph.

#### Changes to `index_graph.py`:

**1. Update imports:**
```python
from ai_service.services.content_pipeline.text_chunker import TextChunker
from ai_service.services.content_pipeline.content_extractor import (
    ContentExtractor,
    build_extract_content_node,
)
from ai_service.services.content_pipeline.pdf_processor import build_pdf_extraction_node
```

**2. Update `IndexState`:**
```python
class IndexState(BaseModel):
    # ── Required Input ──
    course_id: _uuid.UUID
    module_id: str
    force_rebuild: bool
    source_lesson_ids: list[str] | None = None  # ADD — optional lesson filter

    # ── Set by extraction nodes (no longer required as input) ──
    lessons: list[dict] = Field(default_factory=list)
    module_title: str = ""
    pdf_texts: dict[str, str] = Field(default_factory=dict)
    combined_text: str = ""
    lesson_texts: dict[str, str] = Field(default_factory=dict)

    # ── Intermediate (existing) ──
    lesson_chunks: dict[str, list[dict]] = Field(default_factory=dict)
    lesson_embeddings: dict[str, list[list[float]]] = Field(default_factory=dict)
    total_chunks_stored: int = 0

    # ── Output / Error ──
    error: str | None = None
    completed: bool = False
```

**3. Add a `fetch_lessons` node** (same pattern as instructor):
```python
def _build_fetch_lessons_node(content_extractor: ContentExtractor):
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
```

**4. Add a `merge_content` node** that combines MongoDB text + PDF text:
```python
def _build_merge_content_node(content_extractor: ContentExtractor):
    """Merge MongoDB text + PDF text into lesson_texts for chunking."""
    async def merge_content(state: IndexState) -> dict:
        module_data = {
            "module_title": state.module_title,
            "module_description": "",  # Not critical for RAG chunks
            "lessons": state.lessons,
        }
        _, lesson_texts = ContentExtractor.build_combined_text(
            module_data, state.pdf_texts
        )
        if not lesson_texts:
            return {"error": "No content to index after merging"}
        return {"lesson_texts": lesson_texts}
    return merge_content
```

**5. Update `build_index_graph`:**
```python
def build_index_graph(
    content_extractor: ContentExtractor,
    text_chunker: TextChunker,
    openai_client: OpenAIClient,
    vector_store: VectorStoreRepository,
) -> CompiledStateGraph:
    """Build the full indexing pipeline with content extraction inside the graph.

    New flow:
      START -> cleanup_vectors -> fetch_lessons -> extract_pdfs
            -> merge_content -> chunk_texts -> embed_chunks -> store_vectors -> END
    """
    cleanup_node = _build_cleanup_node(vector_store)
    fetch_node = _build_fetch_lessons_node(content_extractor)
    extract_pdfs_node = build_pdf_extraction_node(openai_client)
    merge_node = _build_merge_content_node(content_extractor)
    chunk_node = _build_chunk_node(text_chunker)
    embed_node = _build_embed_node(openai_client)
    store_node = _build_store_node(vector_store)

    graph = StateGraph(IndexState)

    graph.add_node("cleanup_vectors", cleanup_node)
    graph.add_node("fetch_lessons", fetch_node)
    graph.add_node("extract_pdfs", extract_pdfs_node)
    graph.add_node("merge_content", merge_node)
    graph.add_node("chunk_texts", chunk_node)
    graph.add_node("embed_chunks", embed_node)
    graph.add_node("store_vectors", store_node)

    graph.add_edge(START, "cleanup_vectors")
    graph.add_conditional_edges("cleanup_vectors", _error_router("fetch_lessons"))
    graph.add_conditional_edges("fetch_lessons", _error_router("extract_pdfs"))
    graph.add_edge("extract_pdfs", "merge_content")
    graph.add_conditional_edges("merge_content", _error_router("chunk_texts"))
    graph.add_conditional_edges("chunk_texts", _error_router("embed_chunks"))
    graph.add_conditional_edges("embed_chunks", _error_router("store_vectors"))
    graph.add_edge("store_vectors", END)

    return graph.compile()
```

---

### Step 8: Refactor `index.py` (IndexService) — simplify invocation

Since content extraction is now inside the graph, `IndexService` no longer needs to call `content_extractor` before invoking the graph.

#### Changes to `services/index.py`:

**1. Simplify `__init__`:**
```python
class IndexService:
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

        self._index_graph = build_index_graph(
            content_extractor=content_extractor,
            text_chunker=text_chunker,
            openai_client=openai_client,
            vector_store=vector_store,
        )
```

**2. Simplify `_invoke_module_index_graph` — just pass IDs, no content:**
```python
async def _invoke_module_index_graph(
    self,
    course_id: _uuid.UUID,
    module_id: str,
    force_rebuild: bool,
) -> tuple[int, str | None]:
    """Invoke graph — content extraction happens inside the graph now."""
    try:
        result = await self._index_graph.ainvoke(
            IndexState(
                course_id=course_id,
                module_id=module_id,
                force_rebuild=force_rebuild,
            )
        )
        if result.get("error"):
            return 0, result["error"]
        return result.get("total_chunks_stored", 0), None
    except Exception as e:
        return 0, f"Module indexing error: {str(e)}"
```

**3. Simplify `_build_course_index_task`:**
```python
async def _build_course_index_task(self, course_id, force_rebuild):
    try:
        await self.status_tracker.set_in_progress(course_id, "course", "index")

        # Fetch course structure (just module IDs)
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

    except Exception as e:
        await self.status_tracker.set_failed(course_id, "course", "index", str(e))
```

**4. Simplify `_build_module_index_task`:**
```python
async def _build_module_index_task(self, course_id, module_id):
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

    except Exception as e:
        await self.status_tracker.set_failed(course_id, module_id, "index", str(e))
```

---

### Step 9: Update `service_factory.py`

The factory needs to create the new `ContentExtractor` (without `ResourceTextExtractor`). No `raw_openai_client` needed — `OpenAIClient` now handles vision too.

```python
"""Centralized service initialization."""

import logging

from ai_service.clients.openai_client import OpenAIClient
from ai_service.clients.course_service_client import CourseServiceClient
from ai_service.core.mongodb import get_mongodb
from ai_service.core.redis import get_redis
from ai_service.repositories.course_content import CourseContentRepository
from ai_service.repositories.vector_store import VectorStoreRepository
from ai_service.services.content_pipeline import ContentExtractor, TextChunker
from ai_service.services.generation_status import GenerationStatusTracker
from ai_service.services.index import IndexService
from ai_service.services.instructor import InstructorService
from ai_service.services.tutor import TutorService

logger = logging.getLogger(__name__)


def _get_shared_deps():
    """Get shared dependencies (MongoDB, Redis, repos)."""
    db = get_mongodb()
    if db is None:
        raise RuntimeError("MongoDB connection not initialized")
    redis = get_redis()
    if redis is None:
        raise RuntimeError("Redis connection not initialized")

    repo = CourseContentRepository(db)
    content_extractor = ContentExtractor(repo)  # No more ResourceTextExtractor
    status_tracker = GenerationStatusTracker(redis)
    return repo, content_extractor, status_tracker


def create_tutor_service(
    openai_client: OpenAIClient,
    vector_store: VectorStoreRepository,
) -> TutorService:
    logger.info("Creating TutorService")
    return TutorService(openai_client=openai_client, vector_store=vector_store)


def create_index_service(
    openai_client: OpenAIClient,
    vector_store: VectorStoreRepository,
) -> IndexService:
    repo, content_extractor, status_tracker = _get_shared_deps()
    text_chunker = TextChunker()

    logger.info("Creating IndexService (index graph compiled once)")
    return IndexService(
        content_extractor=content_extractor,
        text_chunker=text_chunker,
        openai_client=openai_client,
        vector_store=vector_store,
        status_tracker=status_tracker,
    )


def create_instructor_service(
    openai_client: OpenAIClient,
) -> InstructorService:
    repo, content_extractor, status_tracker = _get_shared_deps()
    course_client = CourseServiceClient()

    logger.info("Creating InstructorService (quiz + summary graphs compiled once)")
    return InstructorService(
        repo=repo,
        openai_client=openai_client,
        course_client=course_client,
        content_extractor=content_extractor,
        status_tracker=status_tracker,
    )
```

---

### Step 10: Update `instructor.py` (InstructorService) — import path changes only

No constructor signature changes needed. The same `openai_client: OpenAIClient` is passed to the graph builders, which now also use it for vision. The graph builders already receive `openai_client` — they just pass it along to `build_pdf_extraction_node(openai_client)` internally.

Only update the import path for `ContentExtractor`:
```python
# REMOVE:
from ai_service.services.content_extractor import ContentExtractor
# ADD:
from ai_service.services.content_pipeline import ContentExtractor
```

---

### Step 11: Update all import paths across the codebase

Search and replace these import paths:

| Old Import | New Import |
|---|---|
| `from ai_service.services.text_chunker import TextChunker` | `from ai_service.services.content_pipeline import TextChunker` |
| `from ai_service.services.text_chunker import TextChunk` | `from ai_service.services.content_pipeline import TextChunk` |
| `from ai_service.services.content_extractor import ContentExtractor` | `from ai_service.services.content_pipeline import ContentExtractor` |
| `from ai_service.clients.resource_extractor import ResourceTextExtractor` | **DELETE** (no longer used) |

Files affected:
- `services/index_graph.py`
- `services/index.py`
- `services/instructor_graphs.py`
- `services/instructor.py`
- `core/service_factory.py`

---

### Step 12: Delete the old `resource_extractor.py`

Delete: `clients/resource_extractor.py`

Its functionality is fully replaced by `content_pipeline/pdf_processor.py`.

---

### Step 13: Delete old `content_extractor.py` and `text_chunker.py` from `services/`

Delete:
- `services/content_extractor.py` (moved to `services/content_pipeline/content_extractor.py`)
- `services/text_chunker.py` (moved to `services/content_pipeline/text_chunker.py`)

---

## New Graph Flows (After Refactor)

### Instructor Flow (Quiz/Summary)
```
START
  -> fetch_lessons          # MongoDB: get lesson metadata + resources list
  -> extract_pdfs           # Download PDFs, extract text + images, GPT-4o vision
  -> extract_content        # Merge MongoDB text + PDF text into combined_text
  -> generate_quiz/summary  # LLM generation
  -> validate               # Structural validation
  -> persist                # Save to course-service
END
```

### Index Flow (RAG)
```
START
  -> cleanup_vectors        # Delete existing vectors if force_rebuild
  -> fetch_lessons          # MongoDB: get lesson metadata + resources list
  -> extract_pdfs           # Download PDFs, extract text + images, GPT-4o vision
  -> merge_content          # Combine MongoDB text + PDF text into lesson_texts
  -> chunk_texts            # Split into overlapping chunks
  -> embed_chunks           # OpenAI embeddings (batched)
  -> store_vectors          # Upsert to Qdrant with metadata
END
```

### What's shared between both flows:
- `fetch_lessons` — same node factory, same logic
- `extract_pdfs` — same node factory (the `build_pdf_extraction_node`)
- Content combining logic — `ContentExtractor.build_combined_text()` static method

---

## Key Design Decisions

### 1. Why separate `fetch_lessons` + `extract_pdfs` + `extract_content` instead of one big node?

**Single Responsibility**: Each node does one thing. This makes debugging easier (you can see in LangGraph traces exactly which step failed), and makes it possible to skip or swap nodes in the future (e.g., skip PDF extraction for modules with no PDFs).

### 2. Why GPT-4o vision for images instead of OCR?

Images contain *semantic* information that OCR cannot capture. GPT-4o vision describes what the image actually shows and its educational meaning. This produces much better RAG retrieval and summary generation than raw pixel-to-text OCR.

### 3. Why is image description stored as text (not as image embeddings)?

Text embeddings via `text-embedding-3-small` are what Qdrant is already set up for. Storing `[Image on page 3: Diagram showing the water cycle with evaporation, condensation...]` as text means it participates naturally in vector search without needing a separate CLIP/multimodal embedding pipeline. Simple and effective.

### 4. Why add `describe_image` to `OpenAIClient` instead of a separate client?

One client, one place. `OpenAIClient` already wraps `AsyncOpenAI` and handles chat completions, structured outputs, and embeddings. Adding a `describe_image` method keeps all OpenAI API interactions in one class — no need to pass two clients around or manage two connection lifecycles.

### 5. Why not make the entire content pipeline a LangGraph subgraph?

Subgraphs add nesting complexity and make state passing harder to debug. Since the nodes are simple sequential steps with error routing, flat nodes in the parent graph are cleaner. The `build_pdf_extraction_node` factory pattern already gives you reusability without subgraph overhead.

### 6. Why PyMuPDFLoader instead of other LangChain PDF loaders?

LangChain has many PDF loaders (`PyPDFLoader`, `PDFPlumberLoader`, `UnstructuredPDFLoader`, etc.). `PyMuPDFLoader` is the best fit because:
- **Fastest** — PyMuPDF is a C-based library, significantly faster than pure-Python alternatives like PyPDF
- **Image extraction built-in** — `extract_images=True` gives you base64 images in `Document.metadata["images"]` with zero extra code
- **You already have PyMuPDF installed** — no new native dependency, just the `langchain-community` Python wrapper
- **Blob support** — can parse from in-memory bytes without writing temp files (important since you download PDFs from URLs)
- **Page-level metadata** — automatic `page`, `source`, `total_pages` in `Document.metadata`

---

## Implementation Order

Execute in this exact order to avoid breaking imports at any step:

1. Create `services/content_pipeline/` directory and `__init__.py`
2. Copy `text_chunker.py` into `content_pipeline/` (keep old file temporarily)
3. Add `describe_image` method to `clients/openai_client.py`
4. Create `content_pipeline/pdf_processor.py` (new file)
5. Create `content_pipeline/content_extractor.py` (refactored version)
6. Update `instructor_graphs.py` (new nodes + edges)
7. Update `index_graph.py` (new nodes + edges)
8. Update `index.py` (simplified invocation)
9. Update `service_factory.py` (new wiring)
10. Update `instructor.py` (import path changes only)
11. Update all remaining import paths
12. Delete old files: `clients/resource_extractor.py`, `services/content_extractor.py`, `services/text_chunker.py`
13. Test both flows end-to-end

---

## Dependencies to Install

**New package needed:**
```bash
pip install langchain-community>=0.3.0
```

Add to `pyproject.toml` under `[project] dependencies`:
```toml
"langchain-community>=0.3.0",
```

This gives you `PyMuPDFLoader` (and all other LangChain document loaders). It uses your existing `PyMuPDF` (fitz) under the hood for the actual PDF parsing.

**Already installed (no changes needed):**
- `PyMuPDF>=1.24.0` — used by PyMuPDFLoader internally
- `langchain-core>=0.3.0` — provides `Document`, `Blob` classes
- `langchain-text-splitters>=0.3.0` — used by TextChunker
- `langgraph>=0.2.0` — graph orchestration
- `openai>=1.40.0` — vision API for image understanding
- `httpx` — PDF download
