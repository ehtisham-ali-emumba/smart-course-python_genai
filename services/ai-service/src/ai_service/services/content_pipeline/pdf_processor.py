"""PDF processing using PyMuPDFLoader + LLMImageBlobParser (GPT-4o vision).

Text is extracted directly by PyMuPDF.
Images are sent to GPT-4o via LLMImageBlobParser - descriptions are
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

PDF_MIME_TYPES = {"pdf", "application/pdf"}
MAX_PAGES_PER_PDF = 200
MAX_CHARS_PER_RESOURCE = 50_000
MAX_LOGGED_PAGES_PER_PDF = 5
PAGE_PREVIEW_CHARS = 220


def _log_pdf_page_preview(pdf_log, page_num: int, page_content: str) -> None:
    """Callback-style helper for gentle per-page extraction observability."""
    if page_num < MAX_LOGGED_PAGES_PER_PDF:
        compact = " ".join(page_content.split())
        pdf_log.info(
            "PDF page extracted (LLM-enriched)",
            page=page_num + 1,
            chars=len(page_content),
            preview_head=compact[:PAGE_PREVIEW_CHARS],
            preview_tail=compact[-PAGE_PREVIEW_CHARS:] if compact else "",
        )
    elif page_num == MAX_LOGGED_PAGES_PER_PDF:
        pdf_log.info(
            "PDF page preview logging capped",
            logged_pages=MAX_LOGGED_PAGES_PER_PDF,
        )


async def _process_single_pdf(url: str, name: str) -> str | None:
    """Extract text + image descriptions from a single PDF.

    Uses PyMuPDFLoader with LLMImageBlobParser so that:
    - Text -> extracted directly into page_content (NOT sent to LLM)
    - Images -> sent to GPT-4o via LLMImageBlobParser, descriptions appended to page_content
    """
    try:
        pdf_log = logger.bind(resource_name=name)
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

            page_content = doc.page_content or ""
            parts.append(page_content)
            total_chars += len(page_content)

            _log_pdf_page_preview(pdf_log, page_num, page_content)

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
                    lesson_parts.append(f"[Resource: {resource.get('name', 'unknown')}]\n{text}")

            if lesson_parts:
                pdf_texts[lesson_id] = "\n\n".join(lesson_parts)

        log.info(
            "[PDF_PROCESSOR] PDF extraction complete",
            lessons_with_pdfs=len(pdf_texts),
        )
        return {"pdf_texts": pdf_texts}

    return extract_pdfs
