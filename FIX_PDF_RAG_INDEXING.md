# Fix: PDF RAG Indexing — "File path is not a valid file or url"

## Problem

When the `/status` endpoint triggers the Temporal workflow for RAG indexing, all PDF extractions fail with:

```
PyMuPDFLoader failed   error='File path  is not a valid file or url'
```

**Result:** `lessons_with_pdfs=0` — no PDF content gets indexed.

## Root Cause

**File:** `services/ai-service/src/ai_service/services/content_pipeline/pdf_processor.py` — lines 107-110

```python
loader = PyMuPDFLoader(
    file_path="",  # <-- BUG: empty string fails validation
    extract_images=True,
)
```

The code manually downloads PDF bytes via httpx, creates a Blob, then tries to use `PyMuPDFLoader` with an empty `file_path`. But `PyMuPDFLoader` validates `file_path` at init.

**The real issue:** This entire approach is over-engineered. `PyMuPDFLoader` natively accepts URLs and has `lazy_load()` for page-by-page streaming. There's no need to manually download, create Blobs, or use `lazy_parse()`.

## Fix

Simplify the pipeline: pass the S3 URL directly to `PyMuPDFLoader` and use `lazy_load()`. Remove the manual httpx download step entirely.

### Changes in `pdf_processor.py`

**1. Remove unused imports (lines 9, 14):**

```python
# REMOVE these lines:
import httpx
from langchain_core.documents.base import Blob
```

**2. Delete the `_download_pdf` function entirely (lines 64-78).**

No longer needed — `PyMuPDFLoader` handles URL fetching internally.

**3. Replace `_load_pdf_with_langchain` (lines 84-164) — now takes a URL instead of bytes:**

```python
async def _load_pdf_with_langchain(
    url: str, name: str
) -> tuple[list[Document], list[dict]]:
    """Use PyMuPDFLoader to extract text documents and images from a PDF URL.

    PyMuPDFLoader natively handles URLs and returns page-by-page documents
    via lazy_load(). With extract_images=True, each document's metadata
    contains base64-encoded images.

    Args:
        url: S3 URL of the PDF.
        name: Resource name for logging.

    Returns:
        Tuple of:
          - text_docs: List of Document objects (one per page) with page text
          - images: List of dicts {page_number, image_index, base64_image}
    """
    try:
        loader = PyMuPDFLoader(
            file_path=url,
            extract_images=True,
        )

        text_docs: list[Document] = []
        images: list[dict] = []
        total_chars = 0
        image_count = 0

        for doc in loader.lazy_load():
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
```

**4. Simplify `_process_single_pdf` (lines 185-234) — remove download step, remove http_client param:**

```python
async def _process_single_pdf(
    openai_client: OpenAIClient,
    url: str,
    name: str,
) -> PDFExtractionResult | None:
    """Full pipeline for one PDF: load via URL -> vision describe.

    1. Load and parse PDF directly from URL via PyMuPDFLoader (text + images)
    2. Send images to GPT-4o vision for descriptions
    3. Return combined result
    """
    # 1. Extract text + images via PyMuPDFLoader (handles URL fetching)
    text_docs, raw_images = await _load_pdf_with_langchain(url, name)

    # Combine page texts into one string
    text = "\n".join(doc.page_content for doc in text_docs).strip()
    if text:
        text = text[:MAX_CHARS_PER_RESOURCE]

    # 2. Describe images via GPT-4o vision
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
```

**5. Simplify `extract_pdfs` inside `build_pdf_extraction_node` (lines 251-300) — remove httpx client:**

```python
    async def extract_pdfs(state) -> dict:
        """Extract content from all PDF resources across lessons.

        Uses PyMuPDFLoader for text + image extraction directly from URLs,
        GPT-4o vision for image understanding.
        """
        lessons = state.lessons
        log = logger.bind(num_lessons=len(lessons))
        log.info("[PDF_PROCESSOR] Starting PDF extraction for all lessons")

        pdf_texts: dict[str, str] = {}

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
```

**6. Remove `MAX_PDF_SIZE_MB` constant (line 23):**

No longer needed since we're not manually downloading and checking size.

### Summary of what's removed vs changed

| Removed | Why |
|---|---|
| `import httpx` | No manual download |
| `from langchain_core.documents.base import Blob` | No Blob creation |
| `_download_pdf()` function | PyMuPDFLoader fetches URLs natively |
| `MAX_PDF_SIZE_MB` constant | No manual size check |
| `httpx.AsyncClient` context manager in `extract_pdfs` | No manual HTTP client |

| Changed | What |
|---|---|
| `_load_pdf_with_langchain(pdf_bytes, name)` | Now takes `(url, name)` instead of bytes |
| `PyMuPDFLoader(file_path="")` | Now `PyMuPDFLoader(file_path=url)` |
| `loader.lazy_parse(blob)` | Now `loader.lazy_load()` |
| `_process_single_pdf(http_client, openai_client, url, name)` | Dropped `http_client` param |

## Note on httpx

After removing `httpx` from this file, check if it's still used elsewhere in the codebase. If this was the only usage, you can remove it from `pyproject.toml` dependencies too.

## Verification

After applying the fix:

1. Rebuild the ai-service image: `docker compose build ai-service`
2. Restart: `docker compose up -d ai-service`
3. Re-run the seed script or hit the `/status` endpoint
4. Check logs — you should see:
   - `PyMuPDFLoader extraction complete` (instead of `PyMuPDFLoader failed`)
   - `lessons_with_pdfs=4` (instead of `lessons_with_pdfs=0`)
   - Image descriptions from GPT-4o vision (if PDFs contain images/charts)
