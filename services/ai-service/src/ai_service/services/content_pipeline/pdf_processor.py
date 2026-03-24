"""LangChain + LangGraph PDF processing with image understanding via GPT-4o vision.

Uses PyMuPDFLoader (from langchain-community) for text + image extraction,
then sends extracted images to GPT-4o vision for understanding.

This replaces the old clients/resource_extractor.py which used raw PyMuPDF calls.
"""

import httpx
import structlog
from dataclasses import dataclass, field
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_core.documents import Document
from langchain_core.documents.base import Blob

from ai_service.clients.openai_client import OpenAIClient

logger = structlog.get_logger(__name__)

# ── Configuration ──────────────────────────────────────────────────────

PDF_MIME_TYPES = {"pdf", "application/pdf"}
MAX_PDF_SIZE_MB = 50
MAX_PAGES_PER_PDF = 200
MAX_CHARS_PER_RESOURCE = 50_000   # ~12,500 tokens safety cap
MAX_IMAGES_PER_PDF = 20           # Safety cap on images to process
MIN_IMAGE_SIZE_BYTES = 5_000      # Skip tiny decorative images (~icons, bullets)


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
        blob = Blob.from_data(pdf_bytes, mime_type="application/pdf")

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

    async def extract_pdfs(state) -> dict:
        """Download and extract content from all PDF resources across lessons.

        Uses LangChain PyMuPDFLoader for text + image extraction,
        GPT-4o vision for image understanding.
        """
        lessons = state.lessons
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
