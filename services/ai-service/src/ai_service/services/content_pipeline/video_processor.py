"""Video processing: audio transcription (Whisper) + frame description (GPT-4o vision).

Video files are downloaded from S3, then processed in two parallel tracks:
  1. Audio track extracted via ffmpeg -> transcribed with Whisper
  2. Keyframes sampled via ffmpeg -> described with GPT-4o vision

Both outputs are merged into structured text for downstream consumption.
"""

import asyncio
import subprocess
import tempfile
from pathlib import Path

import structlog
from openai import AsyncOpenAI
import base64

from ai_service.config import settings
from ai_service.rate_limiters import VIDEO_VISION_SEMAPHORE
from shared.storage.s3 import S3Uploader

logger = structlog.get_logger(__name__)

# ── Constants ──

VIDEO_MIME_TYPES = {
    "video",
    "video/mp4",
    "video/mpeg",
    "video/webm",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mpeg", ".mpg"}

MAX_CHARS_PER_RESOURCE = 50_000
FRAME_INTERVAL_SECONDS = 60  # 1 frame every 60 seconds (demo: ~5 frames for 5-min video)
MAX_FRAMES_PER_VIDEO = 10  # cap at 10 frames (demo videos are max ~5 min)
AUDIO_BITRATE = "64k"  # compress audio to keep under Whisper limit
WHISPER_MAX_BYTES = 25 * 1024 * 1024


def _is_video_resource(resource: dict) -> bool:
    """Check if a resource is a video by MIME type or URL extension."""
    res_type = resource.get("type", "").lower()
    if res_type in VIDEO_MIME_TYPES:
        return True
    url = resource.get("url", "")
    return Path(url.split("?")[0]).suffix.lower() in VIDEO_EXTENSIONS


# ── S3 Client (reuse shared uploader) ──


def _get_s3_uploader() -> S3Uploader:
    return S3Uploader(
        bucket=settings.S3_BUCKET_NAME,
        region=settings.AWS_REGION,
        access_key=settings.AWS_ACCESS_KEY_ID,
        secret_key=settings.AWS_SECRET_ACCESS_KEY,
    )


# ── Download ──


async def _download_video(url: str, dest_path: Path, name: str) -> bool:
    """Download video from S3 using shared S3Uploader, write to temp file. Returns True on success."""
    try:
        uploader = _get_s3_uploader()
        key = S3Uploader.key_from_url(url)
        data = await uploader.download_file(key)
        dest_path.write_bytes(data)
        return True
    except Exception as e:
        logger.warning("Video download failed", name=name, error=str(e))
        return False


# ── Audio Extraction & Transcription ──


async def _extract_and_transcribe_audio(video_path: Path, name: str) -> str | None:
    """Extract audio track from video via ffmpeg, transcribe with Whisper."""
    audio_path = video_path.with_suffix(".mp3")

    try:
        # Extract audio as compressed mp3
        cmd = [
            "ffmpeg",
            "-i",
            str(video_path),
            "-vn",  # no video
            "-acodec",
            "libmp3lame",  # mp3 codec
            "-ab",
            AUDIO_BITRATE,  # low bitrate to stay under 25MB
            "-ac",
            "1",  # mono
            "-y",  # overwrite
            str(audio_path),
        ]
        await asyncio.to_thread(subprocess.run, cmd, capture_output=True, check=True, timeout=300)

        size = audio_path.stat().st_size
        if size > WHISPER_MAX_BYTES:
            logger.warning("Extracted audio too large for Whisper", name=name, size_mb=size / 1e6)
            # TODO: implement chunked transcription with pydub for very long videos
            return None

        # Transcribe
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        with open(audio_path, "rb") as f:
            transcript = await client.audio.transcriptions.create(
                model="whisper-1", file=f, response_format="text"
            )
        text = transcript.strip() if isinstance(transcript, str) else transcript.text.strip()
        return text if text else None

    except Exception as e:
        logger.warning("Audio extraction/transcription failed", name=name, error=str(e))
        return None


# ── Frame Extraction & Description ──


async def _extract_keyframes(video_path: Path, output_dir: Path) -> list[Path]:
    """Sample keyframes from video using ffmpeg. Returns list of frame file paths."""
    try:
        pattern = str(output_dir / "frame_%04d.jpg")
        cmd = [
            "ffmpeg",
            "-i",
            str(video_path),
            "-vf",
            f"fps=1/{FRAME_INTERVAL_SECONDS}",  # 1 frame per N seconds
            "-frames:v",
            str(MAX_FRAMES_PER_VIDEO),
            "-q:v",
            "3",  # JPEG quality (2=best, 31=worst)
            "-y",
            pattern,
        ]
        await asyncio.to_thread(subprocess.run, cmd, capture_output=True, check=True, timeout=300)

        frames = sorted(output_dir.glob("frame_*.jpg"))
        return frames

    except Exception as e:
        logger.warning("Frame extraction failed", error=str(e))
        return []


async def _describe_single_frame(frame_path: Path, frame_index: int, client: AsyncOpenAI) -> str:
    """Send a single frame to GPT-4o vision and get a description."""
    with open(frame_path, "rb") as f:
        b64_image = base64.b64encode(f.read()).decode()

    response = await client.chat.completions.create(
        model="gpt-4o",
        max_tokens=300,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Describe the educational content visible in this video frame. "
                            "Focus on: text on slides, diagrams, code, formulas, key visuals. "
                            "Be concise. If there's nothing educational, say 'No educational content visible.'"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64_image}",
                            "detail": "low",  # cheaper, sufficient for slides/text
                        },
                    },
                ],
            }
        ],
    )
    content = response.choices[0].message.content
    return content.strip() if content else ""


async def _describe_frames(frames: list[Path], name: str) -> list[str]:
    """Describe all frames using GPT-4o vision with semaphore-limited concurrency."""
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def _rate_limited_describe(frame_path: Path, idx: int) -> str:
        async with VIDEO_VISION_SEMAPHORE:
            try:
                return await _describe_single_frame(frame_path, idx, client)
            except Exception as e:
                logger.warning("Frame description failed", frame=idx, error=str(e))
                return ""

    tasks = [_rate_limited_describe(fp, i) for i, fp in enumerate(frames)]
    return await asyncio.gather(*tasks)


# ── Main Processing Function ──


async def _process_single_video(url: str, name: str) -> str | None:
    """Download, extract audio+frames, transcribe+describe, merge into text."""
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            video_path = tmp / f"video{Path(name).suffix or '.mp4'}"

            # Step 1: Download
            if not await _download_video(url, video_path, name):
                return None

            logger.info(
                "Video downloaded", name=name, size_mb=round(video_path.stat().st_size / 1e6, 1)
            )

            # Step 2: Run audio transcription and frame extraction IN PARALLEL
            transcript_task = _extract_and_transcribe_audio(video_path, name)
            frames_task = _extract_keyframes(video_path, tmp)

            transcript, frames = await asyncio.gather(transcript_task, frames_task)

            # Step 3: Describe frames (only if we got frames)
            frame_descriptions = []
            if frames:
                frame_descriptions = await _describe_frames(frames, name)

            # Step 4: Merge into structured text
            parts = []

            if transcript:
                parts.append("## Video Transcript\n" + transcript)

            useful_descriptions = [
                f"[Frame at ~{i * FRAME_INTERVAL_SECONDS}s]: {desc}"
                for i, desc in enumerate(frame_descriptions)
                if desc and "no educational content" not in desc.lower()
            ]
            if useful_descriptions:
                parts.append(
                    "## Visual Content from Video Frames\n" + "\n\n".join(useful_descriptions)
                )

            if not parts:
                return None

            text = "\n\n".join(parts).strip()[:MAX_CHARS_PER_RESOURCE]
            logger.info(
                "Video processing complete",
                name=name,
                chars=len(text),
                has_transcript=bool(transcript),
                frames_described=len(frame_descriptions),
            )
            return text

    except Exception as e:
        logger.warning("Video processing failed", name=name, error=str(e))
        return None


# ── LangGraph Node Factory ──


def build_video_extraction_node(openai_client=None):
    """Factory that returns an async LangGraph node.

    Returns `video_texts`: dict[lesson_id -> combined extracted text].

    Usage:
        graph.add_node("extract_video", build_video_extraction_node())
    """

    async def extract_video(state) -> dict:
        lessons = state.lessons if hasattr(state, "lessons") else state.get("lessons", [])
        log = logger.bind(num_lessons=len(lessons))
        log.info("[VIDEO_PROCESSOR] Starting video extraction for all lessons")

        async def _extract_lesson_video(lesson: dict) -> tuple[str, str] | None:
            lesson_id = lesson["lesson_id"]
            resources = lesson.get("resources", [])
            video_resources = [
                r
                for r in resources
                if r.get("is_active", True) and _is_video_resource(r) and r.get("url", "")
            ]
            if not video_resources:
                return None

            texts = await asyncio.gather(
                *(
                    _process_single_video(r["url"], r.get("name", "unknown"))
                    for r in video_resources
                )
            )
            parts = [
                f"[Video Resource: {r.get('name', 'unknown')}]\n{text}"
                for r, text in zip(video_resources, texts)
                if text
            ]
            if parts:
                return lesson_id, "\n\n".join(parts)
            return None

        results = await asyncio.gather(*(_extract_lesson_video(lesson) for lesson in lessons))

        video_texts = {lid: text for r in results if r for lid, text in [r]}

        log.info("[VIDEO_PROCESSOR] Video extraction complete", lessons_with_video=len(video_texts))
        return {"video_texts": video_texts}

    return extract_video
