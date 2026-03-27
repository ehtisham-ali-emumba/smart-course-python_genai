"""Audio transcription using OpenAI Whisper API.

Audio files (mp3, wav, m4a, etc.) are downloaded from S3 URLs and
transcribed using OpenAI's whisper-1 model. Transcriptions are
merged into lesson content alongside PDF text and inline text.

No LangChain/LangGraph audio integration exists for Python, so this
uses httpx for download and AsyncOpenAI for transcription directly.
Concurrency is controlled via AUDIO_TRANSCRIPTION_SEMAPHORE.
"""

import asyncio
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import boto3
import structlog
from openai import AsyncOpenAI

from ai_service.config import settings
from ai_service.rate_limiters import AUDIO_TRANSCRIPTION_SEMAPHORE

logger = structlog.get_logger(__name__)

AUDIO_MIME_TYPES = {
    "audio",
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/mp4",
    "audio/m4a",
    "audio/webm",
    "audio/ogg",
    "audio/flac",
    "audio/x-m4a",
    "audio/mpeg3",
}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg", ".flac", ".mpga", ".mpeg"}

MAX_FILE_SIZE_MB = 25  # OpenAI Whisper limit
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_AUDIO_DURATION_MINUTES = 120
MAX_CHARS_PER_RESOURCE = 50_000
TRANSCRIPT_PREVIEW_CHARS = 220


def _is_audio_resource(resource: dict) -> bool:
    """Check if a resource is an audio file by type or URL extension."""
    res_type = resource.get("type", "").lower()
    if res_type in AUDIO_MIME_TYPES:
        return True
    url = resource.get("url", "")
    return Path(url.split("?")[0]).suffix.lower() in AUDIO_EXTENSIONS


def _s3_key_from_url(url: str) -> str:
    """Extract S3 key from a virtual-hosted S3 URL.

    https://{bucket}.s3.{region}.amazonaws.com/{key}  →  {key}
    """
    return urlparse(url).path.lstrip("/")


async def _download_audio(url: str, name: str) -> bytes | None:
    """Download private S3 audio file using boto3. Returns bytes or None on failure."""
    try:
        key = _s3_key_from_url(url)
        s3 = boto3.client(
            "s3",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

        def _sync_get() -> bytes:
            resp = s3.get_object(Bucket=settings.S3_BUCKET_NAME, Key=key)
            return resp["Body"].read()

        content = await asyncio.to_thread(_sync_get)

        if len(content) > MAX_FILE_SIZE_BYTES:
            logger.warning(
                "Audio file too large for Whisper API",
                name=name,
                size_mb=len(content) / (1024 * 1024),
                limit_mb=MAX_FILE_SIZE_MB,
            )
            return None

        return content
    except Exception as e:
        logger.warning("Audio download failed", name=name, error=str(e))
        return None


async def _transcribe_audio(audio_bytes: bytes, name: str) -> str | None:
    """Transcribe audio bytes using OpenAI Whisper API."""
    try:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        # Write to temp file (OpenAI SDK requires file-like object with name)
        suffix = Path(name).suffix or ".mp3"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as audio_file:
                transcript = await client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text",
                )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        text = transcript.strip() if isinstance(transcript, str) else transcript.text.strip()
        return text if text else None

    except Exception as e:
        logger.warning("Audio transcription failed", name=name, error=str(e))
        return None


async def _process_single_audio(url: str, name: str) -> str | None:
    """Download and transcribe a single audio file.

    Uses AUDIO_TRANSCRIPTION_SEMAPHORE to limit concurrent API calls.
    """
    async with AUDIO_TRANSCRIPTION_SEMAPHORE:
        audio_log = logger.bind(resource_name=name)
        audio_log.info("Audio transcription starting")

        # Step 1: Download
        audio_bytes = await _download_audio(url, name)
        if not audio_bytes:
            return None

        audio_log.info(
            "Audio downloaded",
            size_mb=round(len(audio_bytes) / (1024 * 1024), 2),
        )

        # Step 2: Transcribe
        text = await _transcribe_audio(audio_bytes, name)
        if not text:
            return None

        # Truncate if needed
        text = text[:MAX_CHARS_PER_RESOURCE]

        compact = " ".join(text.split())
        audio_log.info(
            "Audio transcription complete",
            chars=len(text),
            preview_head=compact[:TRANSCRIPT_PREVIEW_CHARS],
            preview_tail=compact[-TRANSCRIPT_PREVIEW_CHARS:] if compact else "",
        )
        return text


def build_audio_extraction_node(openai_client=None):
    """Factory that returns an async function usable as a LangGraph node.

    The returned node expects the graph state to have a `lessons` field
    (list[dict] with lesson_id, title, resources) and returns
    `audio_texts`: dict[lesson_id -> combined transcribed text].

    Args:
        openai_client: Kept for signature compatibility with pdf_processor.
            Transcription uses AsyncOpenAI internally with settings.OPENAI_API_KEY.

    Usage in a LangGraph StateGraph:
        graph.add_node("extract_audio", build_audio_extraction_node())
    """

    async def extract_audio(state) -> dict:
        # Support both Pydantic .lessons and TypedDict ["lessons"]
        lessons = state.lessons if hasattr(state, "lessons") else state.get("lessons", [])
        log = logger.bind(num_lessons=len(lessons))
        log.info("[AUDIO_PROCESSOR] Starting audio extraction for all lessons")

        async def _extract_lesson_audio(lesson: dict) -> tuple[str, str] | None:
            lesson_id = lesson["lesson_id"]
            resources = lesson.get("resources", [])
            audio_resources = [
                r
                for r in resources
                if r.get("is_active", True) and _is_audio_resource(r) and r.get("url", "")
            ]
            if not audio_resources:
                return None

            # Process audio files for this lesson in parallel (semaphore limits concurrency)
            texts = await asyncio.gather(
                *(
                    _process_single_audio(r["url"], r.get("name", "unknown"))
                    for r in audio_resources
                )
            )
            parts = [
                f"[Audio Resource: {r.get('name', 'unknown')}]\n{text}"
                for r, text in zip(audio_resources, texts)
                if text
            ]
            if parts:
                return lesson_id, "\n\n".join(parts)
            return None

        # Run all lessons in parallel
        results = await asyncio.gather(*(_extract_lesson_audio(lesson) for lesson in lessons))

        audio_texts = {lid: text for r in results if r for lid, text in [r]}

        log.info(
            "[AUDIO_PROCESSOR] Audio extraction complete",
            lessons_with_audio=len(audio_texts),
        )
        return {"audio_texts": audio_texts}

    return extract_audio
