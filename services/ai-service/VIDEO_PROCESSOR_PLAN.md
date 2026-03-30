# Video Processor - Learning Guide & Implementation Plan

## 1. Understanding the Problem

You have **PDF** and **audio** processors that extract text from resources and feed it into your LangGraph pipelines (indexing, quiz, summary). Now you want the same for **video files on S3**.

A video has **two information channels**:
- **Audio track** - spoken words (lectures, narration)
- **Visual track** - slides, diagrams, code on screen, whiteboard writing

To get useful text from a video, you need to handle both.

---

## 2. The Three Approaches (and why approach 2 is your best bet)

### Approach 1: Audio-only (extract audio track, transcribe with Whisper)
- **How**: Use `ffmpeg` to strip the audio from the video, then send to Whisper (exactly like your `audio_processor.py`)
- **Pros**: Simple, cheap, reuses your existing audio pipeline
- **Cons**: Loses all visual information (slides, diagrams, code). If the instructor says "as you can see here..." you get nothing useful

### Approach 2: Audio + Sampled Frame Descriptions (RECOMMENDED)
- **How**:
  1. Extract audio with `ffmpeg` -> transcribe with Whisper
  2. Sample keyframes from the video (e.g., 1 frame every 30-60 seconds) with `ffmpeg`
  3. Send frames to GPT-4o vision API for descriptions
  4. Merge transcription + frame descriptions into structured text
- **Pros**: Captures both channels. Cost-controllable (fewer frames = cheaper). Fits your existing pattern perfectly
- **Cons**: Frame sampling may miss fast transitions; GPT-4o vision calls add cost

### Approach 3: Google Gemini native video understanding
- **How**: Upload entire video to Gemini's multimodal API which natively accepts video
- **Pros**: Best comprehension — model sees actual video, not just snapshots
- **Cons**: Requires adding a new LLM provider (Gemini), different API patterns, vendor lock-in, potentially expensive for long videos. Gemini has a 1-hour video limit. You'd need `google-genai` SDK

**Verdict**: Go with **Approach 2**. It follows your existing patterns (S3 download -> process -> text), uses your existing OpenAI setup, and gives you both audio and visual understanding.

---

## 3. How It Works Step by Step

```
S3 Video URL
     |
     v
[Download from S3]          (shared S3Uploader.download_file(), reuses existing shared utility)
     |
     v
[Save to temp file]         (tempfile, needed for ffmpeg)
     |
     +---> [ffmpeg: extract audio] ---> [Whisper API] ---> transcript text
     |
     +---> [ffmpeg: sample keyframes every N seconds] ---> frame_0.jpg, frame_1.jpg, ...
                |
                v
           [GPT-4o vision: describe each frame]  ---> frame descriptions
                |
                v
[Merge transcript + frame descriptions into structured text]
     |
     v
Return "video_texts" dict (lesson_id -> text)
```

---

## 4. Key Challenges You'll Face

### Challenge 1: Video file size
- For demo purposes, videos are max ~5 minutes long (relatively small files)
- **Solution**: Use the shared `S3Uploader.download_file()` which returns bytes. Write to a temp file for ffmpeg. No streaming needed for short demo videos.

### Challenge 2: ffmpeg is a system dependency
- `ffmpeg` must be installed in your Docker container / runtime
- **Solution**: Add `ffmpeg` to your Dockerfile: `RUN apt-get update && apt-get install -y ffmpeg`
- Python wrapper: Use `ffmpeg-python` package (clean API) or just `subprocess` calls

### Challenge 3: Whisper's 25MB limit for audio
- A 1-hour video's audio track (extracted as mp3) is typically 30-60MB
- **Solution**: Use `pydub` to split audio into chunks < 25MB, transcribe each chunk, concatenate results. OR use `ffmpeg` to compress audio to lower bitrate (64kbps mono mp3 = ~3.75MB per 8 minutes)

### Challenge 4: Frame sampling strategy
- Too many frames = expensive (each GPT-4o vision call costs ~$0.01-0.03)
- Too few frames = miss important visual content
- **Solution**: Sample 1 frame every 60 seconds. For a 5-min demo video = ~5 frames. At ~$0.02/frame = ~$0.10 per video. Very cheap for demo. Use the semaphore pattern you already have.

### Challenge 5: Processing time
- A 5-min demo video: fast download + quick audio extraction + ~5s transcription + ~10s frame descriptions
- **Solution**: Parallel processing (transcription runs simultaneously with frame extraction/description), same `asyncio.gather` pattern you use now

### Challenge 6: Temp file cleanup
- Multiple temp files (video, audio, frames) must be cleaned up
- **Solution**: Use `tempfile.TemporaryDirectory` as context manager — auto-cleans everything

---

## 5. LangGraph Integration

No special "LangGraph video support" exists. LangGraph is just a state machine orchestrator — it doesn't care what your nodes do internally. Your video processor will be a node factory (same pattern as `build_pdf_extraction_node` and `build_audio_extraction_node`).

**The node just needs to:**
1. Accept state with `lessons` field
2. Return `{"video_texts": {lesson_id: text}}`

That's it. LangGraph doesn't need to know it's processing video.

### Where it fits in your graphs:

```
Current:  fetch_lessons -> extract_pdfs -> extract_audio -> merge_content -> ...
New:      fetch_lessons -> extract_pdfs -> extract_audio -> extract_video -> merge_content -> ...
```

The `extract_pdfs`, `extract_audio`, and `extract_video` nodes could even run in **parallel** since they're independent. But sequential is fine too and simpler to debug.

---

## 6. Implementation Plan

### Step 1: Dependencies

```
# pyproject.toml additions
ffmpeg-python = "^0.2.0"    # Python wrapper for ffmpeg CLI
pydub = "^0.25.1"           # Audio splitting (handles Whisper 25MB limit)

# Dockerfile addition
RUN apt-get update && apt-get install -y ffmpeg
```

### Step 2: Rate Limiter (`rate_limiters.py`)

Add to your existing file:

```python
# gpt-4o (video frame descriptions): same pool as PDF vision
# We use 3 because video processing generates many frames per resource
VIDEO_VISION_SEMAPHORE = asyncio.Semaphore(
    int(os.getenv("MAX_CONCURRENT_VIDEO_VISION", "3"))
)
```

### Step 3: Config (`config.py`)

No changes needed — you already have `OPENAI_API_KEY`, `AWS_*`, and `S3_BUCKET_NAME`.

### Step 4: Video Processor (`content_pipeline/video_processor.py`)

This is the main file. Here's the structure:

```python
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
    "video", "video/mp4", "video/mpeg", "video/webm",
    "video/quicktime", "video/x-msvideo", "video/x-matroska",
}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mpeg", ".mpg"}

MAX_CHARS_PER_RESOURCE = 50_000
FRAME_INTERVAL_SECONDS = 60        # 1 frame every 60 seconds (demo: ~5 frames for 5-min video)
MAX_FRAMES_PER_VIDEO = 10          # cap at 10 frames (demo videos are max ~5 min)
AUDIO_BITRATE = "64k"              # compress audio to keep under Whisper limit
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
            "ffmpeg", "-i", str(video_path),
            "-vn",                    # no video
            "-acodec", "libmp3lame",  # mp3 codec
            "-ab", AUDIO_BITRATE,     # low bitrate to stay under 25MB
            "-ac", "1",               # mono
            "-y",                     # overwrite
            str(audio_path),
        ]
        await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, check=True, timeout=300
        )

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
            "ffmpeg", "-i", str(video_path),
            "-vf", f"fps=1/{FRAME_INTERVAL_SECONDS}",  # 1 frame per N seconds
            "-frames:v", str(MAX_FRAMES_PER_VIDEO),
            "-q:v", "3",             # JPEG quality (2=best, 31=worst)
            "-y",
            pattern,
        ]
        await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, check=True, timeout=300
        )

        frames = sorted(output_dir.glob("frame_*.jpg"))
        return frames

    except Exception as e:
        logger.warning("Frame extraction failed", error=str(e))
        return []


async def _describe_single_frame(
    frame_path: Path, frame_index: int, client: AsyncOpenAI
) -> str:
    """Send a single frame to GPT-4o vision and get a description."""
    with open(frame_path, "rb") as f:
        b64_image = base64.b64encode(f.read()).decode()

    response = await client.chat.completions.create(
        model="gpt-4o",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": (
                    "Describe the educational content visible in this video frame. "
                    "Focus on: text on slides, diagrams, code, formulas, key visuals. "
                    "Be concise. If there's nothing educational, say 'No educational content visible.'"
                )},
                {"type": "image_url", "image_url": {
                    "url": f"data:image/jpeg;base64,{b64_image}",
                    "detail": "low",  # cheaper, sufficient for slides/text
                }},
            ],
        }],
    )
    return response.choices[0].message.content.strip()


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

            logger.info("Video downloaded", name=name,
                        size_mb=round(video_path.stat().st_size / 1e6, 1))

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
                parts.append("## Visual Content from Video Frames\n" + "\n\n".join(useful_descriptions))

            if not parts:
                return None

            text = "\n\n".join(parts).strip()[:MAX_CHARS_PER_RESOURCE]
            logger.info("Video processing complete", name=name, chars=len(text),
                        has_transcript=bool(transcript), frames_described=len(frame_descriptions))
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
                r for r in resources
                if r.get("is_active", True) and _is_video_resource(r) and r.get("url", "")
            ]
            if not video_resources:
                return None

            texts = await asyncio.gather(
                *(_process_single_video(r["url"], r.get("name", "unknown"))
                  for r in video_resources)
            )
            parts = [
                f"[Video Resource: {r.get('name', 'unknown')}]\n{text}"
                for r, text in zip(video_resources, texts)
                if text
            ]
            if parts:
                return lesson_id, "\n\n".join(parts)
            return None

        results = await asyncio.gather(
            *(_extract_lesson_video(lesson) for lesson in lessons)
        )

        video_texts = {lid: text for r in results if r for lid, text in [r]}

        log.info("[VIDEO_PROCESSOR] Video extraction complete",
                 lessons_with_video=len(video_texts))
        return {"video_texts": video_texts}

    return extract_video
```

### Step 5: State Updates

**`index_graph.py` - IndexState:**
```python
video_texts: dict[str, str] = Field(default_factory=dict)
```

**`instructor_graphs.py` - QuizState & SummaryState:**
```python
video_texts: dict[str, str]  # lesson_id -> video text
```

### Step 6: Graph Wiring

In `index_graph.py`:
```python
# Add import
from ai_service.services.content_pipeline.video_processor import build_video_extraction_node

# In build_index_graph():
extract_video_node = build_video_extraction_node()
graph.add_node("extract_video", extract_video_node)

# Update edges (add extract_video after extract_audio):
graph.add_edge("extract_audio", "extract_video")
graph.add_edge("extract_video", "merge_content")
# Remove: graph.add_edge("extract_audio", "merge_content")
```

Same pattern for `instructor_graphs.py` (both quiz and summary graphs).

### Step 7: Merge Content Updates

**`content_extractor.py`** - add `video_texts` param to both methods:

```python
# build_combined_text: add after audio section
if lesson_id in video_texts:
    section += f"\n\n#### Video Content:\n{video_texts[lesson_id]}"

# build_lesson_texts: add after audio section
if lesson_id in video_texts:
    parts.append(video_texts[lesson_id])
```

**`index_graph.py` - merge_content node:**
```python
lesson_texts = ContentExtractor.build_lesson_texts(
    state.lessons, state.pdf_texts, audio_texts, video_texts
)
```

**`instructor_graphs.py` - merge_content node:**
```python
video_texts = state.get("video_texts", {})
combined_text = ContentExtractor.build_combined_text(
    module_data, pdf_texts, audio_texts, video_texts
)
```

---

## 7. Cost Estimation

For a typical 5-minute demo video:

| Component | Estimate |
|-----------|----------|
| S3 download | ~$0.00 (negligible egress) |
| Whisper transcription | ~$0.03 (5 min * $0.006/min) |
| Frame extraction (ffmpeg) | $0.00 (local CPU) |
| GPT-4o vision (~5 frames, low detail) | ~$0.10 |
| **Total per video** | **~$0.13** |

Tuning knobs to reduce cost:
- Increase `FRAME_INTERVAL_SECONDS` (already at 60s for demo)
- Reduce `MAX_FRAMES_PER_VIDEO`
- Use `detail: "low"` on the vision API (already doing this)
- Skip frame description entirely and only transcribe audio (cheapest)

---

## 8. Implementation Order (do this in sequence)

1. **Add ffmpeg to Docker** and `ffmpeg-python` to dependencies
2. **Create `video_processor.py`** following the code above
3. **Add `VIDEO_VISION_SEMAPHORE`** to `rate_limiters.py`
4. **Add `video_texts` to state classes** in `index_graph.py` and `instructor_graphs.py`
5. **Wire the node into graphs** (add node + update edges)
6. **Update `content_extractor.py`** to accept and merge `video_texts`
7. **Update merge_content nodes** in both graphs to pass `video_texts`
8. **Test** with a short video (< 5 min) on S3 first

---

## 9. What You Don't Need

- **No LangChain video loader** - none exists in langchain-community for this use case
- **No new LLM provider** - GPT-4o vision + Whisper covers everything
- **No video-specific LangGraph features** - your existing node pattern works perfectly
- **No streaming** - video processing is inherently batch (download -> process -> return text)
