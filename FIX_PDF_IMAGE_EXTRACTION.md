# Fix: PDF Image Extraction in ai-service

## Problem

PDFs have images but PyMuPDFLoader finds zero — due to a bug in `langchain-community==0.4.1`.

## Root Cause

Bug in `PyMuPDFParser._extract_images_from_page` — BytesIO size is checked BEFORE data is written:

```python
image_bytes = io.BytesIO()              # empty
if image_bytes.getbuffer().nbytes == 0:  # always True!
    continue                             # every image skipped
numpy.save(image_bytes, image)           # never reached
```

- **Bug:** https://github.com/langchain-ai/langchain/issues/34400
- **Fix PR (merged, not released):** https://github.com/langchain-ai/langchain-community/pull/193
- `langchain-community==0.4.1` is the latest release and still has the bug

## Solution

Monkey-patch the bug + use the official `LLMImageBlobParser` approach from the LangChain docs. When langchain releases the fix, just delete the patch — zero other changes needed.

---

### Step 1: Add `langchain-openai` dependency

**File:** `services/ai-service/pyproject.toml`

Add `"langchain-openai>=0.3.0"` to the `dependencies` list. This is required by `LLMImageBlobParser` to use `ChatOpenAI`.

```toml
dependencies = [
    # ... existing deps ...
    "langchain-openai>=0.3.0",   # NEW — required for LLMImageBlobParser
]
```

---

### Step 2: Create the monkey-patch files

**New file:** `services/ai-service/src/ai_service/patches/__init__.py`

```python
"""Monkey-patches for third-party library bugs.

Remove patches as upstream fixes are released.
"""
```

**New file:** `services/ai-service/src/ai_service/patches/pymupdf_images.py`

```python
"""Fix for langchain-community 0.4.1 BytesIO bug in PyMuPDFParser.

Bug: _extract_images_from_page checks BytesIO size BEFORE writing image data.
Issue: https://github.com/langchain-ai/langchain/issues/34400
Fix PR: https://github.com/langchain-ai/langchain-community/pull/193 (merged, not released)

TODO: Remove this patch once langchain-community releases a version with the fix.
"""

import io
import numpy as np
import pymupdf
import structlog
from langchain_community.document_loaders.parsers.pdf import PyMuPDFParser
from langchain_core.document_loaders import Blob

logger = structlog.get_logger(__name__)


def _patched_extract_images_from_page(self, doc, page):
    """Fixed: numpy.save() BEFORE BytesIO size check."""
    if not self.images_parser:
        return ""

    from langchain_community.document_loaders.parsers.pdf import (
        _FORMAT_IMAGE_STR,
        _JOIN_IMAGES,
        _format_inner_image,
    )

    img_list = page.get_images()
    images = []
    for img in img_list:
        xref = img[0]
        pix = pymupdf.Pixmap(doc, xref)
        image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, -1
        )
        image_bytes = io.BytesIO()
        np.save(image_bytes, image)  # FIX: save BEFORE checking size
        if image_bytes.getbuffer().nbytes == 0:
            continue
        blob = Blob.from_data(image_bytes.getvalue(), mime_type="application/x-npy")
        image_text = next(self.images_parser.lazy_parse(blob)).page_content
        images.append(
            _format_inner_image(blob, image_text, self.images_inner_format)
        )
    return _FORMAT_IMAGE_STR.format(
        image_text=_JOIN_IMAGES.join(filter(None, images))
    )


def apply():
    """Apply the monkey-patch."""
    PyMuPDFParser._extract_images_from_page = _patched_extract_images_from_page
    logger.info(
        "[PATCH] Applied fix for langchain-community 0.4.1 PyMuPDF image extraction bug"
    )
```

---

### Step 3: Apply patch at startup

**File:** `services/ai-service/src/ai_service/main.py`

Add these 2 lines near the top of the file, after the existing imports (before `logging.basicConfig`):

```python
from ai_service.patches import pymupdf_images
pymupdf_images.apply()
```

---

### Step 4: Replace `pdf_processor.py`

**File:** `services/ai-service/src/ai_service/services/content_pipeline/pdf_processor.py`

Replace the entire file contents with:

```python
"""PDF processing using PyMuPDFLoader + LLMImageBlobParser (GPT-4o vision).

Text is extracted directly by PyMuPDF.
Images are sent to GPT-4o via LLMImageBlobParser — descriptions are
automatically merged into page_content.

Requires the monkey-patch in ai_service.patches.pymupdf_images to be applied
at startup (fixes langchain-community 0.4.1 BytesIO bug).
"""

import structlog
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_community.document_loaders.parsers import LLMImageBlobParser
from langchain_openai import ChatOpenAI

from ai_service.config import settings

logger = structlog.get_logger(__name__)

# ── Configuration ──────────────────────────────────────────────────────

PDF_MIME_TYPES = {"pdf", "application/pdf"}
MAX_PAGES_PER_PDF = 200
MAX_CHARS_PER_RESOURCE = 50_000


# ── Single PDF Pipeline ───────────────────────────────────────────────


async def _process_single_pdf(url: str, name: str) -> str | None:
    """Extract text + image descriptions from a single PDF.

    Uses PyMuPDFLoader with LLMImageBlobParser so that:
    - Text → extracted directly into page_content (NOT sent to LLM)
    - Images → sent to GPT-4o via LLMImageBlobParser, descriptions appended to page_content
    """
    try:
        loader = PyMuPDFLoader(
            file_path=url,
            mode="page",
            images_inner_format="markdown-img",
            images_parser=LLMImageBlobParser(
                model=ChatOpenAI(
                    model="gpt-4o",
                    max_tokens=1024,
                    api_key=settings.OPENAI_API_KEY,
                )
            ),
        )

        parts: list[str] = []
        total_chars = 0

        for doc in loader.lazy_load():
            page_num = doc.metadata.get("page", len(parts))
            if page_num >= MAX_PAGES_PER_PDF:
                break

            parts.append(doc.page_content)
            total_chars += len(doc.page_content)

            if total_chars >= MAX_CHARS_PER_RESOURCE:
                logger.info("PDF text cap reached", name=name, pages_read=page_num + 1)
                break

        text = "\n".join(parts).strip()[:MAX_CHARS_PER_RESOURCE]
        if not text:
            return None

        logger.info("PDF extraction complete", name=name, pages=len(parts), chars=len(text))
        return text

    except Exception as e:
        logger.warning("PDF extraction failed", name=name, error=str(e))
        return None


# ── Public API: LangGraph Node Factory ─────────────────────────────


def build_pdf_extraction_node(openai_client=None):
    """Factory that returns an async function usable as a LangGraph node.

    The returned node expects the graph state to have a `lessons` field
    (list[dict] with lesson_id, title, resources) and returns
    `pdf_texts`: dict[lesson_id -> combined extracted text].

    Args:
        openai_client: Kept for backward compatibility with existing callers.
            Image description is now handled internally by LLMImageBlobParser.

    Usage in a LangGraph StateGraph:
        graph.add_node("extract_pdfs", build_pdf_extraction_node(openai_client))
    """

    async def extract_pdfs(state) -> dict:
        lessons = state.lessons
        log = logger.bind(num_lessons=len(lessons))
        log.info("[PDF_PROCESSOR] Starting PDF extraction for all lessons")

        pdf_texts: dict[str, str] = {}

        for lesson in lessons:
            lesson_id = lesson["lesson_id"]
            resources = lesson.get("resources", [])
            pdf_resources = [
                r
                for r in resources
                if r.get("is_active", True)
                and r.get("type", "").lower() in PDF_MIME_TYPES
                and r.get("url", "")
            ]

            if not pdf_resources:
                continue

            lesson_parts: list[str] = []
            for resource in pdf_resources:
                text = await _process_single_pdf(
                    resource["url"],
                    resource.get("name", "unknown"),
                )
                if text:
                    lesson_parts.append(
                        f"[Resource: {resource.get('name', 'unknown')}]\n{text}"
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

---

### Step 5: Update `__init__.py` exports

**File:** `services/ai-service/src/ai_service/services/content_pipeline/__init__.py`

Remove `PDFExtractionResult` from imports and `__all__` (it no longer exists). Replace entire file with:

```python
"""Centralized content extraction pipeline.

Groups PDF processing, content extraction, and text chunking into a
single cohesive package used by both instructor and index flows.
"""

from ai_service.services.content_pipeline.text_chunker import TextChunker, TextChunk
from ai_service.services.content_pipeline.content_extractor import ContentExtractor
from ai_service.services.content_pipeline.pdf_processor import build_pdf_extraction_node

__all__ = [
    "TextChunker",
    "TextChunk",
    "ContentExtractor",
    "build_pdf_extraction_node",
]
```

---

## Complete list of file changes

| # | File | Action | What changes |
|---|---|---|---|
| 1 | `services/ai-service/pyproject.toml` | Edit | Add `"langchain-openai>=0.3.0"` to dependencies |
| 2 | `services/ai-service/src/ai_service/patches/__init__.py` | Create | Empty package docstring |
| 3 | `services/ai-service/src/ai_service/patches/pymupdf_images.py` | Create | Monkey-patch that swaps 2 lines |
| 4 | `services/ai-service/src/ai_service/main.py` | Edit | Add 2 import+apply lines after existing imports |
| 5 | `services/ai-service/src/ai_service/services/content_pipeline/pdf_processor.py` | Replace | Use `LLMImageBlobParser` + `ChatOpenAI` |
| 6 | `services/ai-service/src/ai_service/services/content_pipeline/__init__.py` | Edit | Remove `PDFExtractionResult` export |

## Callers that need NO changes

These files call `build_pdf_extraction_node(openai_client)` — the signature accepts `openai_client=None` for backward compatibility so they keep working as-is:

- `services/ai-service/src/ai_service/services/index_graph.py` (line 327)
- `services/ai-service/src/ai_service/services/instructor_graphs.py` (lines 833, 885)

## After implementation: rebuild Docker

```bash
docker compose build ai-service
docker compose up -d ai-service
```

## When to remove the patch

When `langchain-community` releases a version newer than 0.4.1 that includes [PR #193](https://github.com/langchain-ai/langchain-community/pull/193):

1. Update `langchain-community` version in `pyproject.toml`
2. Delete `services/ai-service/src/ai_service/patches/pymupdf_images.py`
3. Remove the 2 `pymupdf_images` lines from `main.py`
4. Everything else stays the same
