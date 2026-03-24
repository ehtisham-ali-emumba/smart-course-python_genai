# AI Service — Deep Analysis & Improvement Guide

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [How LangGraph Works in Your System](#2-how-langgraph-works-in-your-system)
3. [How RAG Works End-to-End](#3-how-rag-works-end-to-end)
4. [How PDF Parsing Currently Works](#4-how-pdf-parsing-currently-works)
5. [LangGraph Improvements](#5-langgraph-improvements)
6. [PDF with Images — The Multimodal Approach](#6-pdf-with-images--the-multimodal-approach)
7. [Edge Cases & Best Practices](#7-edge-cases--best-practices)
8. [Priority Roadmap](#8-priority-roadmap)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FastAPI (main.py)                           │
├──────────┬──────────────┬───────────────────────────────────────────┤
│ api/     │ api/         │ api/                                      │
│ tutor.py │ instructor.py│ index.py                                  │
├──────────┴──────────────┴───────────────────────────────────────────┤
│ services/tutor.py    services/instructor.py    services/index.py    │
│   └─ tutor_agent.py    └─ instructor_graphs.py                     │
│                            (LangGraph state machines)               │
├─────────────────────────────────────────────────────────────────────┤
│ services/content_extractor.py  ←  Shared by Instructor + Indexing   │
│ services/text_chunker.py       ←  Used by Indexing                  │
│ services/generation_status.py  ←  Redis-based status tracking       │
├─────────────────────────────────────────────────────────────────────┤
│ clients/openai_client.py       ←  OpenAI API (chat + embeddings)    │
│ clients/resource_extractor.py  ←  PDF download + PyMuPDF extraction │
│ clients/course_service_client.py ← HTTP calls to course-service     │
├─────────────────────────────────────────────────────────────────────┤
│ repositories/vector_store.py   ←  Qdrant (async)                    │
│ repositories/course_content.py ←  MongoDB (async)                   │
├─────────────────────────────────────────────────────────────────────┤
│ core/mongodb.py   core/redis.py                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. How LangGraph Works in Your System

### 2.1 Instructor Graphs (`services/instructor_graphs.py`)

You have **two independent LangGraph state machines**:

#### Quiz Graph

```
START ─→ extract_content ─→ generate_quiz ─→ validate_quiz ─┬→ persist_quiz ─→ END
              │                     ▲                        │
              │ (error → END)       └────────────────────────┘
                                      (retry if invalid,
                                       max 1 retry)
```

**State**: `QuizState(TypedDict)` carries all data between nodes — input params, extracted text, generated quiz, validation results, and error info.

**Node pattern**: Factory functions (`_build_generate_quiz_node(openai_client)`) that return async closures. This lets you inject dependencies (OpenAI client, course client, content extractor) without global state.

**Retry mechanism**: When validation fails, the router sends state back to `generate_quiz`. The validation feedback is appended to the prompt so the LLM can self-correct. `MAX_RETRIES = 1` so you get at most 2 total attempts.

**Key detail**: The router functions (`_quiz_validation_router`) **mutate state directly** (`state["retry_count"] = current_retry + 1`). This works but is an anti-pattern in LangGraph — nodes should return state updates, not mutate state in routers.

#### Summary Graph

Identical pattern to Quiz. Same `extract_content` node factory, same validation → retry → persist flow.

#### Tutor Graph (`services/tutor_agent.py`)

```
START ─→ retrieve ─→ generate ─→ END
```

Linear 2-node graph. `retrieve` embeds the question and searches Qdrant (top-k=5, score threshold 0.3). `generate` builds a system prompt with retrieved context + last 10 messages of conversation history, then calls GPT-4o-mini.

**State**: `TutorState(TypedDict, total=False)` — the `total=False` makes all fields optional, which is the right call for a graph where nodes progressively fill in state.

### 2.2 How Graphs Are Invoked

```python
# In InstructorService:
graph = build_quiz_graph(openai_client, course_client, content_extractor)
result = await graph.ainvoke(initial_state)

# In TutorService:
graph = build_tutor_graph(openai_client, vector_store)
result = await graph.ainvoke({"query": ..., "course_id": ..., ...})
```

Graphs are **rebuilt on every invocation** — they're compiled fresh each time. This is fine for correctness but has a minor overhead cost (see improvements).

---

## 3. How RAG Works End-to-End

### Indexing Pipeline (write path)

```
Instructor triggers build → IndexService
  1. ContentExtractor fetches module+lessons from MongoDB
  2. ResourceTextExtractor downloads PDFs from S3 URLs, extracts text via PyMuPDF
  3. ContentExtractor combines MongoDB text + PDF text per lesson
  4. TextChunker splits each lesson's text (1500 chars, 200 overlap, recursive splitting)
  5. OpenAIClient.embed_texts() embeds chunks in batches of 100
  6. VectorStoreRepository.upsert_chunks() stores in Qdrant with metadata
     (course_id, module_id, lesson_id, module_title, lesson_title, chunk_index)
```

### Query Pipeline (read path — Tutor)

```
Student sends message → TutorService → TutorGraph
  1. retrieve node: embed query via OpenAI text-embedding-3-small
  2. Search Qdrant with course_id filter (optionally module_id/lesson_id)
  3. Take top-5 results, filter by score >= 0.3
  4. Format as "Source 1 (Module: X, Lesson: Y)\n{text}"
  5. generate node: system prompt with context + last 10 history messages → GPT-4o-mini
  6. Return response + source attributions
```

### S3/PDF Flow

PDFs are stored as lesson resources with URLs (presumably S3 presigned or public URLs). The `ResourceTextExtractor`:
1. Iterates lessons → finds PDF resources (type in `{"pdf", "application/pdf"}`)
2. Downloads via `httpx.AsyncClient` (60s timeout, max 10 connections)
3. Extracts text: `fitz.open(stream=bytes) → page.get_text("text")`
4. Safety caps: 50MB max size, 200 pages max, 50K chars max per PDF
5. Returns `dict[lesson_id, extracted_text]`

**Current limitation**: `page.get_text("text")` only extracts text layer. Images, diagrams, charts, tables, and scanned pages are completely ignored.

---

## 4. How PDF Parsing Currently Works

```python
# resource_extractor.py — the core extraction
doc = fitz.open(stream=pdf_bytes, filetype="pdf")
for page_num in range(min(len(doc), 200)):
    page_text = doc[page_num].get_text("text")  # ← TEXT ONLY
    text_parts.append(page_text)
```

**What works**: Clean text-based PDFs (lecture notes, articles, text documents).

**What fails silently**:
- PDFs with embedded diagrams/charts → images ignored, no text extracted from them
- Scanned PDFs → returns `None` (logged as "may be scanned image")
- PDFs where key info is in tables → table structure is lost, text comes out jumbled
- PDFs with mathematical formulas as images → completely missed
- Infographics, slides with screenshots → all visual content lost

---

## 5. LangGraph Improvements

### 5.1 State Mutation in Routers (Bug)

**Current problem** in `instructor_graphs.py:587`:
```python
def _quiz_validation_router(state: QuizState) -> str:
    # ...
    state["retry_count"] = current_retry + 1  # ← MUTATING STATE IN ROUTER!
    return "generate_quiz"
```

Routers should be **pure functions** that only read state and return a routing decision. State updates should only happen in nodes.

**Fix**: Move retry_count increment into the `validate_quiz` node:

```python
# In validate_quiz node, when validation fails:
return {
    "validation_passed": False,
    "validation_feedback": feedback,
    "retry_count": state.get("retry_count", 0) + 1,  # increment here
}

# Router becomes pure:
def _quiz_validation_router(state: QuizState) -> str:
    if state.get("validation_passed"):
        return "persist_quiz"
    if state.get("retry_count", 0) <= MAX_RETRIES:
        return "generate_quiz"
    return "persist_quiz"
```

Same fix for `_summary_validation_router`.

### 5.2 Cache Compiled Graphs

Currently graphs are built fresh on every request:
```python
# services/instructor.py
graph = build_quiz_graph(openai_client, course_client, content_extractor)
```

Graph compilation is deterministic — same dependencies = same graph. Cache it:

```python
class InstructorService:
    def __init__(self, ...):
        # Compile once at service init
        self._quiz_graph = build_quiz_graph(openai_client, course_client, content_extractor)
        self._summary_graph = build_summary_graph(openai_client, course_client, content_extractor)
```

Same for `TutorService` — compile the tutor graph once.

### 5.3 Add Error Handling Edges to Generation Nodes

Currently, if `generate_quiz` raises an exception, it sets `error` in state but there's no conditional edge after `generate_quiz` to check for it — it goes straight to `validate_quiz`, which will see no quiz and return invalid.

**Fix**: Add error-checking conditional edges after generation nodes:

```python
def _generation_error_router(state) -> str:
    return END if state.get("error") else "validate_quiz"

graph.add_conditional_edges("generate_quiz", _generation_error_router)
```

### 5.4 Make the Tutor Graph Smarter with Conditional Retrieval

The current tutor graph is always: retrieve → generate. But some student messages don't need retrieval (e.g., "thanks", "can you explain that again?", greetings).

**Improvement**: Add a `classify_intent` node:

```
START → classify_intent ─┬→ retrieve → generate → END
                          └→ generate → END  (no retrieval needed)
```

```python
class TutorState(TypedDict, total=False):
    # ... existing fields ...
    needs_retrieval: bool  # NEW

def _build_classify_intent_node(openai_client):
    async def classify_intent(state: TutorState) -> dict:
        query = state["query"].lower().strip()

        # Simple heuristic first (no LLM call needed)
        no_retrieval_patterns = [
            "thank", "thanks", "ok", "okay", "got it",
            "explain that again", "can you clarify",
            "hello", "hi", "hey",
        ]
        if any(p in query for p in no_retrieval_patterns):
            return {"needs_retrieval": False}

        return {"needs_retrieval": True}
    return classify_intent

# In graph builder:
def intent_router(state: TutorState) -> str:
    return "retrieve" if state.get("needs_retrieval", True) else "generate"

graph.add_conditional_edges("classify_intent", intent_router)
```

This saves an embedding call + Qdrant search for conversational messages.

### 5.5 Add a Rewrite Query Node (Tutor)

For better RAG results, add a query rewrite step that uses conversation history to resolve references:

Student history: "What is React?" → "How does it handle state?"
The "it" refers to React, but the raw query "How does it handle state?" won't retrieve React-related chunks.

```
START → classify_intent → rewrite_query → retrieve → generate → END
```

```python
def _build_rewrite_query_node(openai_client):
    async def rewrite_query(state: TutorState) -> dict:
        history = state.get("conversation_history", [])
        if not history:
            return {}  # no rewrite needed

        messages = [
            {"role": "system", "content": (
                "Rewrite the user's question to be self-contained, "
                "resolving any pronouns or references using the conversation history. "
                "Return ONLY the rewritten question, nothing else."
            )},
            *[{"role": m["role"], "content": m["content"]} for m in history[-6:]],
            {"role": "user", "content": state["query"]},
        ]
        rewritten = await openai_client.chat_completion(messages)
        return {"query": rewritten.strip()}
    return rewrite_query
```

### 5.6 Use LangGraph's `Annotated` Reducers for List State

For `TutorState.sources` and `retrieved_chunks`, if you ever expand to multi-step retrieval (retrieve from multiple sources), use LangGraph's annotation-based reducers:

```python
from operator import add
from typing import Annotated

class TutorState(TypedDict, total=False):
    # ...
    retrieved_chunks: Annotated[list[dict], add]  # auto-appends across nodes
    sources: Annotated[list[dict], add]
```

This becomes important when you have parallel retrieval nodes.

### 5.7 Add Checkpointing for Long-Running Graphs

The instructor graphs (extract → generate → validate → persist) can take 30+ seconds. If the process crashes mid-way, all work is lost.

LangGraph supports checkpointing with `MemorySaver` or `SqliteSaver`:

```python
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()  # or SqliteSaver for persistence
compiled = graph.compile(checkpointer=checkpointer)

# Invoke with a thread_id for resumability
result = await compiled.ainvoke(
    initial_state,
    config={"configurable": {"thread_id": f"{course_id}:{module_id}:quiz"}}
)
```

This lets you resume from the last successful node if a crash occurs.

### 5.8 Make the Indexing Pipeline a LangGraph

Currently, indexing is procedural code in `IndexService`. This is a missed opportunity — it should be a graph:

```
START → extract_content → chunk_text → embed_chunks → store_vectors → END
                                           │
                                     (error → retry_embed)
```

Benefits:
- Retry individual embedding batches on failure (OpenAI rate limits)
- Checkpointing: resume from last successful batch on crash
- Observable: LangGraph's built-in tracing shows exactly where indexing is
- Consistent pattern across the whole service

### 5.9 Add LangGraph Streaming for Tutor

Instead of waiting for the full response, stream tokens to the student:

```python
async for event in graph.astream_events(state, version="v2"):
    if event["event"] == "on_chat_model_stream":
        yield event["data"]["chunk"].content
```

This requires switching the generate node to use a streaming-capable OpenAI call, but dramatically improves perceived latency for the tutor.

---

## 6. PDF with Images — The Multimodal Approach

### 6.1 The Problem

`page.get_text("text")` only gets the text layer. For course PDFs, this misses:
- Diagrams and flowcharts
- Code screenshots
- Mathematical formulas rendered as images
- Charts and graphs
- Slide-deck PDFs (mostly visual)
- Scanned documents

### 6.2 Approach 1: Vision LLM Page Description (Recommended)

Convert each PDF page to an image, send it to a vision model (GPT-4o), and get a text description.

```python
import fitz
import base64

async def extract_page_with_vision(
    page: fitz.Page,
    openai_client: OpenAIClient,
) -> str:
    """Extract text + describe visual content using GPT-4o vision."""

    # 1. Get regular text
    text = page.get_text("text").strip()

    # 2. Check if page has images
    image_list = page.get_images(full=True)
    has_images = len(image_list) > 0

    # 3. If no images and text exists, just return text (cheaper)
    if not has_images and text:
        return text

    # 4. Render page to image for vision analysis
    pix = page.get_pixmap(dpi=150)  # 150 DPI balances quality vs size
    img_bytes = pix.tobytes("png")
    img_b64 = base64.b64encode(img_bytes).decode()

    # 5. Send to GPT-4o vision
    messages = [
        {
            "role": "system",
            "content": (
                "You are a document analysis assistant. Extract ALL information from this "
                "PDF page — both text and visual content (diagrams, charts, tables, formulas, "
                "images). Describe visual elements in detail so a student who cannot see the "
                "image understands the content. Output structured text."
            ),
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{img_b64}",
                        "detail": "high",  # high detail for text-heavy pages
                    },
                },
                {
                    "type": "text",
                    "text": (
                        "Extract all text and describe all visual elements "
                        "(diagrams, charts, tables, images) from this PDF page."
                    ),
                },
            ],
        },
    ]

    description = await openai_client.chat_completion(messages, model="gpt-4o")
    return description
```

**Key decisions**:
- **DPI 150**: Good balance. 72 DPI is too blurry for text; 300 DPI is too large/expensive.
- **Only use vision when images are detected**: Pages with just text skip the vision call (saves cost).
- **`detail: "high"`**: Needed for reading text in images. `"low"` would miss small text.

### 6.3 Approach 2: OCR + Vision Hybrid

For scanned PDFs (no text layer at all), use OCR as a first pass, then vision for diagrams:

```python
import fitz

def extract_with_ocr(page: fitz.Page) -> str:
    """Use PyMuPDF's built-in OCR (needs Tesseract installed)."""
    # PyMuPDF 1.23+ supports OCR via Tesseract
    tp = page.get_textpage_ocr(flags=0, language="eng", dpi=300)
    return page.get_text("text", textpage=tp)
```

**Hybrid approach**:
```python
async def extract_page_hybrid(page, openai_client):
    # 1. Try regular text extraction
    text = page.get_text("text").strip()

    # 2. If no text, try OCR
    if not text:
        text = extract_with_ocr(page)

    # 3. If page has images OR OCR result is sparse, use vision
    images = page.get_images(full=True)
    if images or (text and len(text) < 100):
        vision_text = await extract_page_with_vision(page, openai_client)
        if vision_text:
            text = f"{text}\n\n[Visual Content Description]\n{vision_text}" if text else vision_text

    return text
```

### 6.4 Making This a LangGraph Pipeline

This is where PDF parsing should become a graph:

```
START → download_pdf → classify_pages → ┬→ text_extract (text-only pages)     ─┐
                                         ├→ ocr_extract (scanned pages)         ├→ merge_results → END
                                         └→ vision_extract (image-heavy pages) ─┘
```

```python
class PDFExtractionState(TypedDict, total=False):
    pdf_url: str
    pdf_name: str
    pdf_bytes: bytes
    pages: list[dict]           # [{page_num, has_text, has_images, image_ratio}]
    text_pages: list[dict]      # [{page_num, text}]
    ocr_pages: list[dict]       # [{page_num, text}]
    vision_pages: list[dict]    # [{page_num, text}]
    merged_text: str
    error: str | None

def build_pdf_extraction_graph(openai_client) -> CompiledStateGraph:
    graph = StateGraph(PDFExtractionState)

    graph.add_node("download_pdf", download_node)
    graph.add_node("classify_pages", classify_pages_node)
    graph.add_node("extract_text_pages", text_extract_node)
    graph.add_node("extract_ocr_pages", ocr_extract_node)
    graph.add_node("extract_vision_pages", vision_extract_node)
    graph.add_node("merge_results", merge_node)

    graph.add_edge(START, "download_pdf")
    graph.add_edge("download_pdf", "classify_pages")

    # After classification, fan out to all three extractors
    graph.add_edge("classify_pages", "extract_text_pages")
    graph.add_edge("classify_pages", "extract_ocr_pages")
    graph.add_edge("classify_pages", "extract_vision_pages")

    # All three merge into final result
    graph.add_edge("extract_text_pages", "merge_results")
    graph.add_edge("extract_ocr_pages", "merge_results")
    graph.add_edge("extract_vision_pages", "merge_results")

    graph.add_edge("merge_results", END)

    return graph.compile()
```

**classify_pages node** determines extraction strategy per page:

```python
async def classify_pages(state: PDFExtractionState) -> dict:
    doc = fitz.open(stream=state["pdf_bytes"], filetype="pdf")
    pages = []
    for i in range(min(len(doc), MAX_PAGES_PER_PDF)):
        page = doc[i]
        text = page.get_text("text").strip()
        images = page.get_images(full=True)

        # Calculate image area ratio
        page_area = page.rect.width * page.rect.height
        image_area = 0
        for img in images:
            xref = img[0]
            img_rect = page.get_image_rects(xref)
            for rect in img_rect:
                image_area += rect.width * rect.height

        image_ratio = image_area / page_area if page_area > 0 else 0

        pages.append({
            "page_num": i,
            "has_text": bool(text),
            "has_images": len(images) > 0,
            "image_ratio": image_ratio,
            "strategy": _classify_page_strategy(text, images, image_ratio),
        })
    doc.close()
    return {"pages": pages}

def _classify_page_strategy(text, images, image_ratio) -> str:
    if not text and not images:
        return "skip"       # blank page
    if not text and images:
        return "vision"     # scanned or image-only
    if text and image_ratio > 0.3:
        return "vision"     # significant visual content
    if text and not images:
        return "text"       # pure text
    return "text"           # text with minor decorative images
```

### 6.5 Cost Considerations

Vision API calls are expensive. To manage costs:

| Strategy | Cost per page (approx) | When to use |
|----------|----------------------|-------------|
| Text extraction | Free | Pages with text, no meaningful images |
| OCR (Tesseract) | Free (local) | Scanned text-only pages |
| GPT-4o Vision (low detail) | ~$0.003 | Simple diagrams, tables |
| GPT-4o Vision (high detail) | ~$0.01-0.03 | Complex diagrams, dense text in images |

**Cost control strategies**:
1. Only use vision for pages where `image_ratio > 0.3`
2. Use `detail: "low"` for simple diagrams, `"high"` for text-heavy images
3. Set a per-PDF vision call budget (e.g., max 10 vision calls per PDF)
4. Cache vision descriptions — same PDF page = same description

### 6.6 Changes Needed in Your Codebase

1. **`resource_extractor.py`**: Replace `_extract_text_from_bytes` with the hybrid approach
2. **`openai_client.py`**: Add a `describe_image(img_bytes) -> str` method
3. **`content_extractor.py`**: No changes needed (it just consumes the extracted text)
4. **`text_chunker.py`**: May need to handle vision descriptions differently (they tend to be longer)
5. **Config**: Add `ENABLE_VISION_EXTRACTION=true/false` toggle and `VISION_MODEL=gpt-4o`

### 6.7 Embedding Images Directly (Advanced)

For the RAG index, you could also embed images directly using multimodal embedding models (like CLIP or future OpenAI multimodal embeddings). This enables image-to-image retrieval.

However, this is a bigger architectural change and not necessary for your current use case. The vision-description approach (describe image → embed description text) works well and keeps your existing Qdrant text-embedding pipeline intact.

---

## 7. Edge Cases & Best Practices

### 7.1 LangGraph Edge Cases

**a) Infinite retry loops**
Your `MAX_RETRIES = 1` is good, but the retry_count mutation in the router means if the router doesn't execute (LangGraph internal error), you could theoretically loop. With the fix in 5.1 (move increment to node), this becomes impossible.

**b) Graph error propagation**
If `persist_quiz` fails, the error is set in state but the graph still returns normally. The caller checks `result.get("error")`, which is correct. However, consider raising a custom exception from the persist node for truly unrecoverable errors (e.g., course-service is down), so the caller can distinguish "quiz is bad" from "infrastructure failure".

**c) Large state objects**
`combined_text` can be huge (50K+ chars from PDFs). This entire string gets carried through every node. For the tutor graph it's fine (2 nodes), but for instructor graphs (4+ nodes), consider storing large text externally (Redis) and only passing a key in state.

**d) Concurrent graph invocations**
Multiple instructors generating quizzes simultaneously is fine since each `ainvoke` gets its own state. But if two instructors generate for the **same module** at the same time, you could get a race condition in `persist_quiz` (both try POST, one gets 409, retries with PUT). Consider a Redis lock:

```python
lock_key = f"generation_lock:{course_id}:{module_id}:{content_type}"
if not await redis.setnx(lock_key, "1", ex=300):
    raise HTTPException(409, "Generation already in progress")
```

### 7.2 RAG Edge Cases

**a) Empty index**
If a student asks a question before the instructor builds the index, `retrieve` returns no chunks, and the tutor says "I couldn't find relevant information." This is correct behavior but could be improved with a pre-check:

```python
# In tutor session creation or first message
chunk_count = await vector_store.count_course_vectors(course_id)
if chunk_count == 0:
    return "The course materials haven't been indexed yet. Please ask your instructor to build the index."
```

**b) Stale index**
If an instructor updates lesson content but doesn't rebuild the index, the RAG returns outdated info. Consider auto-triggering re-index when content changes (via a webhook from course-service).

**c) Cross-module contamination**
The tutor's `module_id` filter is optional. If a student asks about Module 1 content but their session is scoped to Module 2, they might not get relevant results. Consider falling back to course-wide search if module-scoped search returns low scores.

**d) Chunk boundary issues**
The `RecursiveCharacterTextSplitter` with 200-char overlap handles most cases, but key concepts that span a chunk boundary might be split awkwardly. Consider increasing overlap to 300+ chars for better coverage, or using semantic chunking (split at paragraph boundaries only).

### 7.3 PDF Edge Cases

**a) Password-protected PDFs**: `fitz.open()` will throw an error. Add explicit handling:
```python
doc = fitz.open(stream=pdf_bytes, filetype="pdf")
if doc.is_encrypted:
    logger.warning("PDF is encrypted, skipping", name=name)
    doc.close()
    return None
```

**b) Corrupted PDFs**: Already handled by the try/except, but consider validating the PDF magic bytes before parsing:
```python
if not pdf_bytes[:4] == b'%PDF':
    logger.warning("Invalid PDF header", name=name)
    return None
```

**c) Very large pages (maps, posters)**: A single page could produce enormous text. Add per-page char limits:
```python
page_text = doc[page_num].get_text("text")[:10_000]  # cap per page
```

**d) Non-English PDFs**: PyMuPDF handles Unicode fine, but OCR needs the right language pack. Make OCR language configurable.

**e) PDF links and bookmarks**: Currently ignored. For navigation-heavy PDFs, extracting the table of contents (`doc.get_toc()`) could provide useful structural metadata.

### 7.4 Prompt Engineering Best Practices

**a) Structured output reliability**: You're using `response_format` with Pydantic models for quiz/summary generation. This is the right approach. But add a fallback for when structured output parsing fails:

```python
try:
    result = await client.beta.chat.completions.parse(...)
except openai.LengthFinishReasonError:
    # Output was cut off due to max_tokens
    logger.warning("Structured output truncated, retrying with higher limit")
    # Retry with increased max_tokens or simplified prompt
```

**b) Token budget awareness**: Your prompts include the full `combined_text` (up to 50K chars per PDF, multiple PDFs per module). This could exceed token limits. Add a token estimate before sending:

```python
estimated_tokens = len(combined_text) // 4  # rough estimate
if estimated_tokens > 100_000:
    # Truncate or summarize first
    combined_text = combined_text[:400_000]  # ~100K tokens
    logger.warning("Content truncated to fit token limits")
```

**c) System prompt in tutor**: Your tutor system prompt is well-structured. One improvement — include the student's current module/lesson context:

```python
TUTOR_SYSTEM_PROMPT = """...
## Student Context
The student is currently studying: {module_title} — {lesson_title}
...
"""
```

### 7.5 Observability

**a) Add LangSmith tracing**: LangGraph integrates natively with LangSmith for tracing:
```python
import os
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = "..."
```
This gives you full visibility into node execution times, state at each step, and LLM calls.

**b) Add timing to nodes**: Currently you log start/end but not duration. Add timing:
```python
import time

async def generate_quiz(state):
    start = time.monotonic()
    # ... generation logic ...
    duration = time.monotonic() - start
    log.info("Quiz generated", duration_seconds=round(duration, 2))
```

---

## 8. Priority Roadmap

### High Priority (Do First)
| # | Change | File | Effort |
|---|--------|------|--------|
| 1 | Fix state mutation in routers | `instructor_graphs.py` | 30 min |
| 2 | Add error edge after generate nodes | `instructor_graphs.py` | 30 min |
| 3 | Cache compiled graphs | `instructor.py`, `tutor.py` | 15 min |
| 4 | Add encrypted/corrupted PDF checks | `resource_extractor.py` | 15 min |
| 5 | Add generation lock (prevent concurrent same-module) | `instructor.py` | 30 min |

### Medium Priority (Next Sprint)
| # | Change | File | Effort |
|---|--------|------|--------|
| 6 | Add query rewriting for tutor | `tutor_agent.py` | 1-2 hrs |
| 7 | Add vision extraction for image PDFs | `resource_extractor.py`, `openai_client.py` | 3-4 hrs |
| 8 | Token budget checking before LLM calls | `openai_client.py` | 1 hr |
| 9 | Empty index pre-check in tutor | `tutor.py` | 30 min |
| 10 | Add LangSmith tracing | `config.py`, env vars | 30 min |

### Lower Priority (When Needed)
| # | Change | File | Effort |
|---|--------|------|--------|
| 11 | Convert indexing to LangGraph | `index.py` (new graph) | 4-6 hrs |
| 12 | PDF extraction as LangGraph pipeline | new file | 6-8 hrs |
| 13 | Streaming for tutor responses | `tutor_agent.py`, `tutor.py`, `api/tutor.py` | 3-4 hrs |
| 14 | LangGraph checkpointing | all graph builders | 2-3 hrs |
| 15 | Intent classification node for tutor | `tutor_agent.py` | 2-3 hrs |

---

**Bottom line**: Your LangGraph usage is solid for an initial implementation. The factory pattern, validation-retry loops, and clean state definitions are all good. The highest-impact improvements are: (1) fixing the router state mutation, (2) adding vision-based PDF extraction for image-heavy content, and (3) query rewriting for better tutor RAG results. Everything else is incremental polish.
