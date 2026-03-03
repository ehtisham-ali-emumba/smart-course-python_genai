"""PDF resource text extractor for lesson content enrichment."""

import fitz  # PyMuPDF
import httpx
import structlog
from io import BytesIO

logger = structlog.get_logger(__name__)

PDF_MIME_TYPES = {"pdf", "application/pdf"}
MAX_PDF_SIZE_MB = 50
MAX_PAGES_PER_PDF = 200
MAX_CHARS_PER_RESOURCE = 50_000  # ~12,500 tokens — safety cap per PDF


class ResourceTextExtractor:
    """Downloads and extracts text from lesson PDF resources."""

    async def extract_text_from_lessons(self, lessons: list[dict]) -> dict[str, str]:
        """Extract text from all PDF resources across multiple lessons.

        Args:
            lessons: List of lesson dicts from CourseContentRepository.
                     Each has 'lesson_id', 'title', 'resources': [...].

        Returns:
            Dict mapping lesson_id → extracted text from all its PDF resources.
            Lessons with no PDFs or failed extractions are omitted.
        """
        results: dict[str, str] = {}

        async with httpx.AsyncClient(
            timeout=60.0,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        ) as client:
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

                lesson_texts: list[str] = []
                for resource in pdf_resources:
                    text = await self._download_and_extract(
                        client, resource["url"], resource.get("name", "unknown")
                    )
                    if text:
                        lesson_texts.append(f"[Resource: {resource.get('name', 'PDF')}]\n{text}")

                if lesson_texts:
                    results[lesson_id] = "\n\n".join(lesson_texts)

        return results

    async def _download_and_extract(
        self, client: httpx.AsyncClient, url: str, name: str
    ) -> str | None:
        """Download a single PDF and extract its text.

        Returns None on any failure (network, parsing, etc.) — never crashes.
        """
        try:
            resp = await client.get(url)
            resp.raise_for_status()

            # Safety check: skip if too large
            content_length = len(resp.content)
            if content_length > MAX_PDF_SIZE_MB * 1024 * 1024:
                logger.warning(
                    "PDF too large, skipping",
                    name=name,
                    size_mb=content_length / (1024 * 1024),
                )
                return None

            return self._extract_text_from_bytes(resp.content, name)

        except httpx.HTTPError as e:
            logger.warning("Failed to download PDF", name=name, url=url, error=str(e))
            return None
        except Exception as e:
            logger.warning("Unexpected error processing PDF", name=name, error=str(e))
            return None

    def _extract_text_from_bytes(self, pdf_bytes: bytes, name: str) -> str | None:
        """Extract text from raw PDF bytes using PyMuPDF."""
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            pages_to_read = min(len(doc), MAX_PAGES_PER_PDF)
            text_parts: list[str] = []
            total_chars = 0

            for page_num in range(pages_to_read):
                page_text = doc[page_num].get_text("text")
                text_parts.append(page_text)
                total_chars += len(page_text)
                if total_chars >= MAX_CHARS_PER_RESOURCE:
                    logger.info(
                        "PDF text cap reached, truncating",
                        name=name,
                        pages_read=page_num + 1,
                    )
                    break

            doc.close()

            full_text = "\n".join(text_parts).strip()
            if not full_text:
                logger.info("PDF has no extractable text (may be scanned image)", name=name)
                return None

            return full_text[:MAX_CHARS_PER_RESOURCE]

        except Exception as e:
            logger.warning("Failed to extract text from PDF", name=name, error=str(e))
            return None
