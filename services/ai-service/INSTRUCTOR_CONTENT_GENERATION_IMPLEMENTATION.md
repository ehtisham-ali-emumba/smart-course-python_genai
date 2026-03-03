# Instructor Content Generation — Implementation Guide

This document contains step-by-step instructions for implementing the summary and quiz generation endpoints in the `ai-service`.

---

## Architecture Overview

```
Instructor (frontend)
    │
    ▼  POST /api/v1/ai/instructor/modules/{module_id}/generate-summary
ai-service (FastAPI)
    │
    ├─ 1. Returns { status: "pending" } immediately
    │
    └─ 2. Background task:
         ├─ READ module + lessons from MongoDB (motor) ← CourseContentRepository
         ├─ DOWNLOAD lesson PDF resources from S3 (httpx, public URLs)
         ├─ EXTRACT text from PDFs (PyMuPDF / fitz)
         ├─ CALL OpenAI gpt-4o-mini (structured outputs)
         └─ WRITE via HTTP POST to course-service (httpx)
```

**Key decisions:**
- **Reads** go directly to MongoDB (faster than HTTP to course-service).
- **PDF resources** are fetched directly from S3 public URLs and text-extracted in-process. This enriches the LLM context beyond just lesson titles.
- **Writes** go through the course-service REST API (single source of truth for persistence).
- **Background tasks** via `asyncio.create_task` so the endpoint returns instantly while generation runs.
- **LLM**: OpenAI `gpt-4o-mini` with structured outputs for guaranteed JSON shapes.

---

## Prerequisites: Obtaining the OpenAI API Key

Before starting implementation, you need an OpenAI API key for `gpt-4o-mini` access.

### How to get the key:

1. Go to [https://platform.openai.com/signup](https://platform.openai.com/signup) and create an account (or sign in).
2. Navigate to **Settings > Billing** and add a payment method. `gpt-4o-mini` is pay-per-use — it's very cheap (~$0.15 per 1M input tokens, ~$0.60 per 1M output tokens), so even $5 of credit will last a long time for development.
3. Go to **API Keys** page: [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys).
4. Click **"Create new secret key"**, give it a name like `smartcourse-ai-service`, and copy the key.
5. Add the key to your ai-service `.env` file:

```env
# services/ai-service/.env
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxx
```

### Security notes:
- **Never commit** the `.env` file or the API key to git. The `.gitignore` should already exclude `.env` — verify this.
- For production / Docker Compose, pass it as an environment variable or use a secrets manager (Docker secrets, AWS SSM, etc.).
- The key is already wired in `config.py` as `OPENAI_API_KEY: str = ""` — no config changes needed, just set the env var.

---

## Architecture Decision: Why Direct MongoDB Reads (Not HTTP to course-service)

You might wonder: if the course-service owns the data, isn't reading MongoDB directly from the ai-service a form of duplication or tight coupling?

It's a fair concern. Here's the reasoning:

### Why this is the right approach:

1. **Read-only access** — The ai-service never writes to MongoDB. The course-service remains the sole owner of all create/update/delete operations. There is zero risk of data inconsistency from two services writing to the same collections.

2. **Speed matters here** — A direct MongoDB query takes ~2-5ms. An HTTP roundtrip to course-service adds network hop + JSON serialization + FastAPI overhead (~20-50ms minimum). Since the instructor is polling every 3-4 seconds expecting results, every millisecond saved in the background task (MongoDB read + LLM call + HTTP persist) helps meet that expectation.

3. **The infrastructure already exists** — The motor connection, `CourseContentRepository`, and methods like `get_module()` / `get_lessons_for_module()` are already built and wired in the ai-service. This pattern was an intentional architectural decision from the start.

4. **Minimal surface area** — The ai-service only reads raw text content (module title, lesson text) to build an LLM prompt. It doesn't duplicate business logic, validation, or access control. If the MongoDB document shape changes, you update one repository method — same effort as updating an API contract.

### When would HTTP be better?

- If the course-service added authorization logic to content reads (e.g., "only enrolled users can view lesson text") — then you'd need to go through its API to respect those rules. Currently, auth is handled at the API gateway level, not inside course-service read queries.
- If the services ran on separate database clusters with no shared MongoDB access.

### The pattern in short:

```
ai-service → MongoDB (reads)     ← fast, direct, read-only
ai-service → course-service HTTP (writes) ← preserves single source of truth for mutations
```

This is a well-established microservices pattern called **"shared database for reads, API for writes"** and is appropriate when both services are internal, trusted, and deployed together.

---

## Step 1: Add Dependencies

### File: `services/ai-service/pyproject.toml`

Add `openai` and `PyMuPDF` to the `dependencies` list. `httpx` is already present.

```toml
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "motor>=3.3.0",
    "redis>=5.0.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "httpx>=0.26.0",
    "structlog>=24.1.0",
    "openai>=1.40.0",           # <── ADD: LLM client
    "PyMuPDF>=1.24.0",          # <── ADD: PDF text extraction (import as 'fitz')
]
```

**Why PyMuPDF (`fitz`) over alternatives?**
- **Fast** — C-based, extracts text from a 50-page PDF in <100ms. `pdfplumber` and `PyPDF2` are 5-10x slower.
- **Reliable** — handles scanned-text PDFs, complex layouts, and multi-column documents better than `PyPDF2`.
- **No system dependencies** — unlike `pdftotext` which needs `poppler` installed on the system. PyMuPDF is a single pip install.
- **Memory efficient** — can process from bytes in-memory (no temp files needed).

Then reinstall:
```bash
cd services/ai-service && pip install -e .
```

### File: `services/ai-service/Dockerfile`

The Dockerfile hardcodes pip install lines separately from `pyproject.toml`. Add the two new packages to the `RUN pip install` block:

```dockerfile
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    ...existing packages... \
    openai>=1.40.0 \
    PyMuPDF>=1.24.0
```

> PyMuPDF publishes pre-built wheels for `python:3.11-slim` (manylinux), so no extra `apt-get` system dependencies are needed. The existing `gcc` in the Dockerfile is sufficient.

### File: `services/ai-service/src/ai_service/config.py`

**No changes needed.** The config already has all required settings:
- `OPENAI_API_KEY: str = ""`
- `OPENAI_MODEL: str = "gpt-4o-mini"`
- `COURSE_SERVICE_URL: str = "http://course-service:8002"`

Make sure your `.env` has a valid `OPENAI_API_KEY`.

---

## Step 2: Add `get_module_with_lessons` to `CourseContentRepository`

### File: `services/ai-service/src/ai_service/repositories/course_content.py`

Add a new method that builds a text context payload from the module and its lessons. This is the text that will be sent to the LLM.

**Method signature:**
```python
async def get_module_with_lessons(
    self, course_id: int, module_id: str, lesson_ids: list[str] | None = None
) -> dict | None:
```

**Implementation logic:**
1. Call `self.get_module(course_id, module_id)` to get the module document.
2. If module is `None`, return `None`.
3. Extract `module["title"]` and `module.get("description", "")`.
4. Get lessons from `module.get("lessons", [])`.
5. If `lesson_ids` is provided and non-empty, filter lessons to only those whose `lesson_id` is in the list.
6. For each lesson, extract `lesson["title"]` and `lesson.get("content", {}).get("text_content", "")` (or however the text is stored — check the actual document shape).
7. Return a dict:
```python
{
    "module_title": module["title"],
    "module_description": module.get("description", ""),
    "lessons": [
        {
            "lesson_id": lesson["lesson_id"],
            "title": lesson["title"],
            "text_content": lesson.get("content", {}).get("text_content", ""),
        }
        for lesson in filtered_lessons
    ],
    "combined_text": combined_text,  # All lesson texts joined with headers
}
```
8. Build `combined_text` by concatenating:
```
## Module: {module_title}
{module_description}

### Lesson: {lesson_title}
{lesson_text_content}

### Lesson: {lesson_title}
{lesson_text_content}
...
```

This `combined_text` is what gets sent to the LLM prompt — but it may be sparse if lessons are video/PDF-based and `text_content` is empty. That's where Step 2B comes in.

---

## Step 2B: Create the Resource Text Extractor

### New file: `services/ai-service/src/ai_service/clients/resource_extractor.py`

Also ensure `services/ai-service/src/ai_service/clients/__init__.py` exists (empty).

**Purpose:** Download PDF resources from S3 and extract their text content to enrich the LLM context. Many lessons are video-based with PDF handouts/transcripts as the only text source — without this step, the LLM would have almost nothing to work with.

### How lesson resources are stored in MongoDB:

Each lesson has an embedded `resources` array:
```json
{
  "lesson_id": "les_3d4e5f",
  "title": "Variables and Data Types",
  "type": "video",
  "content": "https://smartcourse-uploads-bucket.s3.ap-southeast-2.amazonaws.com/course-content/videos/a3f9e1b2.mp4",
  "resources": [
    {
      "resource_id": "res_7h8i9j",
      "name": "Python Cheat Sheet",
      "url": "https://smartcourse-uploads-bucket.s3.ap-southeast-2.amazonaws.com/course-content/documents/7b2c3d4e.pdf",
      "type": "pdf",
      "is_active": true
    }
  ]
}
```

The `url` field is a **public S3 URL** — directly fetchable via HTTP GET without authentication or presigning.

**Relevant resource types:** Only `pdf` and `application/pdf` resources should be processed. Video, audio, image, and link types should be skipped.

### Implementation:

```python
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

    async def extract_text_from_lessons(
        self, lessons: list[dict]
    ) -> dict[str, str]:
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
                    r for r in resources
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
                        lesson_texts.append(
                            f"[Resource: {resource.get('name', 'PDF')}]\n{text}"
                        )

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
                    name=name, size_mb=content_length / (1024 * 1024),
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
                        name=name, pages_read=page_num + 1,
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
```

### Scalability safeguards built in:

| Safeguard | Value | Why |
|-----------|-------|-----|
| `MAX_PDF_SIZE_MB` | 50 MB | Skip corrupted or huge uploads |
| `MAX_PAGES_PER_PDF` | 200 pages | Don't process entire textbooks |
| `MAX_CHARS_PER_RESOURCE` | 50,000 chars (~12.5K tokens) | Keep per-resource LLM context bounded |
| `httpx.Limits(max_connections=10)` | 10 concurrent | Don't overwhelm S3 or exhaust file descriptors |
| `timeout=60.0` | 60s per request | Don't hang on slow downloads |
| Per-resource error isolation | `try/except` per PDF | One bad PDF doesn't kill the whole batch |

### Update `get_module_with_lessons` in `CourseContentRepository` (Step 2 revision):

The repository method from Step 2 should now also **return the raw `resources` array** for each lesson so the extractor can process them:

```python
# In the return dict, each lesson entry should include resources:
{
    "lesson_id": lesson["lesson_id"],
    "title": lesson["title"],
    "text_content": lesson.get("content", {}).get("text_content", ""),
    "resources": lesson.get("resources", []),  # <── ADD THIS
}
```

### Update `combined_text` building (Step 2 revision):

After calling `get_module_with_lessons`, the service layer (Step 5) will call `ResourceTextExtractor.extract_text_from_lessons()` and merge the extracted text into the combined context. The `combined_text` format becomes:

```
## Module: {module_title}
{module_description}

### Lesson: {lesson_title}
{lesson_text_content}

#### PDF Resources:
[Resource: Python Cheat Sheet]
(extracted PDF text here...)

### Lesson: {next_lesson_title}
...
```

This merging happens in `InstructorService._process_and_save_summary` (Step 5), NOT in the repository — the repository stays a pure data-access layer.

---

## Step 3: Create the Course Service HTTP Client

### New file: `services/ai-service/src/ai_service/clients/course_service_client.py`

Also create `services/ai-service/src/ai_service/clients/__init__.py` (empty).

**Purpose:** Send the LLM-generated summary/quiz to the course-service for persistence.

**Key details about course-service endpoints:**
- Base URL: `settings.COURSE_SERVICE_URL` (default `http://course-service:8002`)
- The router has **no** `/api/v1` prefix — routes are mounted at root
- Auth: course-service reads `X-User-ID` and `X-User-Role` headers (set by API gateway). For internal service-to-service calls, you must forward these headers.

**Endpoint paths:**

| Action | Method | Path |
|--------|--------|------|
| Create quiz | `POST` | `/{course_id}/modules/{module_id}/quiz` |
| Replace quiz | `PUT` | `/{course_id}/modules/{module_id}/quiz` |
| Create summary | `POST` | `/{course_id}/modules/{module_id}/summary` |
| Replace summary | `PUT` | `/{course_id}/modules/{module_id}/summary` |

**Implementation outline:**

```python
import httpx
import structlog
from ai_service.config import settings

logger = structlog.get_logger(__name__)

class CourseServiceClient:
    def __init__(self):
        self.base_url = settings.COURSE_SERVICE_URL

    async def save_summary(
        self,
        course_id: int,
        module_id: str,
        payload: dict,
        user_id: int,
    ) -> dict | None:
        """POST or PUT summary to course-service."""
        ...

    async def save_quiz(
        self,
        course_id: int,
        module_id: str,
        payload: dict,
        user_id: int,
    ) -> dict | None:
        """POST or PUT quiz to course-service."""
        ...
```

**For each `save_*` method:**
1. Create an `httpx.AsyncClient` (use `async with` for proper cleanup).
2. Set headers: `{"X-User-ID": str(user_id), "X-User-Role": "instructor"}`.
3. First attempt a `POST` to create. If the response is `409 Conflict` (quiz/summary already exists), fall back to `PUT` to replace it.
4. On success (`201` or `200`), return the response JSON.
5. On failure, log the error with `structlog` and return `None` (do NOT raise — the background task should not crash).

**Example for `save_summary`:**
```python
async def save_summary(self, course_id, module_id, payload, user_id):
    url = f"{self.base_url}/{course_id}/modules/{module_id}/summary"
    headers = {"X-User-ID": str(user_id), "X-User-Role": "instructor"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 409:
                resp = await client.put(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Failed to save summary", error=str(e), course_id=course_id)
            return None
```

Same pattern for `save_quiz`.

---

## Step 4: Create the OpenAI Client with Structured Outputs

### New file: `services/ai-service/src/ai_service/clients/openai_client.py`

**Purpose:** Call `gpt-4o-mini` and get back guaranteed JSON matching the course-service schemas.

**Pydantic response models to define in this file** (these mirror the course-service schemas and are used for OpenAI structured outputs):

### Summary structured output model:

```python
from pydantic import BaseModel, Field

class GlossaryTerm(BaseModel):
    term: str
    definition: str

class DifficultyAssessment(BaseModel):
    level: Literal["beginner", "intermediate", "advanced"]
    estimated_read_minutes: int = Field(..., ge=1)

class GeneratedSummaryContent(BaseModel):
    """Matches course-service SummaryContentCreate schema."""
    summary_text: str
    key_points: list[str] = Field(default_factory=list)
    learning_objectives: list[str] = Field(default_factory=list)
    glossary: list[GlossaryTerm] = Field(default_factory=list)
    difficulty_assessment: DifficultyAssessment | None = None

class GeneratedSummary(BaseModel):
    """Top-level structured output for summary generation."""
    title: str = Field(..., max_length=300)
    content: GeneratedSummaryContent
```

### Quiz structured output model:

```python
class GeneratedQuizOption(BaseModel):
    option_id: str
    text: str
    is_correct: bool

class GeneratedQuizQuestion(BaseModel):
    order: int = Field(..., ge=1)
    question_text: str
    question_type: Literal["multiple_choice", "multiple_select", "true_false", "short_answer"]
    options: list[GeneratedQuizOption] | None = None
    correct_answers: list[str] | None = None
    explanation: str | None = None
    hint: str | None = None

class GeneratedQuiz(BaseModel):
    """Top-level structured output for quiz generation."""
    title: str = Field(..., max_length=300)
    description: str | None = None
    questions: list[GeneratedQuizQuestion]
```

### OpenAI client class:

```python
from openai import AsyncOpenAI
from ai_service.config import settings

class OpenAIClient:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL

    async def generate_summary(
        self,
        context_text: str,
        include_glossary: bool = True,
        include_key_points: bool = True,
        include_learning_objectives: bool = True,
        max_length_words: int | None = None,
        tone: str | None = None,
        language: str = "en",
    ) -> GeneratedSummary:
        ...

    async def generate_quiz(
        self,
        context_text: str,
        num_questions: int = 5,
        difficulty: str | None = None,
        question_types: list[str] | None = None,
        language: str = "en",
    ) -> GeneratedQuiz:
        ...
```

### `generate_summary` implementation:

1. Build a system prompt:
   ```
   You are an expert educational content summarizer. Generate a comprehensive
   module summary from the provided lesson content.
   ```
2. Build a user prompt including:
   - The `context_text` (module + lessons text from Step 2)
   - Instructions based on flags: "Include key_points: yes/no", "Include glossary: yes/no", etc.
   - If `max_length_words` is set: "Keep the summary under {max_length_words} words."
   - If `tone` is set: "Use a {tone} tone."
   - If `language` != "en": "Write the summary in {language}."
3. Call:
   ```python
   completion = await self.client.beta.chat.completions.parse(
       model=self.model,
       messages=[
           {"role": "system", "content": system_prompt},
           {"role": "user", "content": user_prompt},
       ],
       response_format=GeneratedSummary,
   )
   return completion.choices[0].message.parsed
   ```
4. Wrap the call in a `try/except` for `openai.OpenAIError`, log the error, and re-raise so the calling code knows it failed.

### `generate_quiz` implementation:

1. Build a system prompt:
   ```
   You are an expert quiz creator for educational courses. Generate quiz
   questions based on the provided lesson content. Each question must be
   pedagogically sound and directly test knowledge from the material.
   ```
2. Build a user prompt including:
   - The `context_text`
   - `"Generate exactly {num_questions} questions."`
   - If `difficulty` is set: `"Difficulty level: {difficulty}."`
   - `"Allowed question types: {', '.join(question_types)}."`
   - Explicit instructions for option format:
     - `multiple_choice`: exactly 4 options with `option_id` values `opt_a`, `opt_b`, `opt_c`, `opt_d`; exactly 1 correct
     - `true_false`: exactly 2 options with `option_id` values `opt_true` and `opt_false`; exactly 1 correct
     - `multiple_select`: 4 options with at least 1 correct
     - `short_answer`: no options, provide `correct_answers` list instead
   - `"Include an explanation for each question."`
   - If `language` != "en": `"Write questions in {language}."`
3. Call `client.beta.chat.completions.parse` with `response_format=GeneratedQuiz`.
4. Same error handling pattern as summary.

---

## Step 5: Update `InstructorService`

### File: `services/ai-service/src/ai_service/services/instructor.py`

**Major changes:**
1. The constructor now accepts dependencies.
2. Public methods kick off background tasks and return `status: "pending"`.
3. Private methods do the actual work (fetch → LLM → persist).

### Constructor:

```python
class InstructorService:
    def __init__(
        self,
        repo: CourseContentRepository,
        openai_client: OpenAIClient,
        course_client: CourseServiceClient,
        resource_extractor: ResourceTextExtractor,
    ):
        self.repo = repo
        self.openai_client = openai_client
        self.course_client = course_client
        self.resource_extractor = resource_extractor
```

### Public method `generate_summary`:

```python
async def generate_summary(
    self,
    course_id: int,
    module_id: str,
    request: GenerateSummaryRequest,
    user_id: int,
) -> GenerateSummaryResponse:
    # Fire background task
    asyncio.create_task(
        self._process_and_save_summary(course_id, module_id, request, user_id)
    )
    return GenerateSummaryResponse(
        course_id=course_id,
        module_id=module_id,
        source_lesson_ids=request.source_lesson_ids or [],
        status=GenerationStatus.PENDING,
        message="Summary generation started.",
    )
```

Same pattern for `generate_quiz` and `generate_all`.

### Private method `_process_and_save_summary`:

```python
async def _process_and_save_summary(
    self,
    course_id: int,
    module_id: str,
    request: GenerateSummaryRequest,
    user_id: int,
) -> None:
```

**Steps:**
1. **Fetch content** — call `self.repo.get_module_with_lessons(course_id, module_id, request.source_lesson_ids)`. If `None`, log an error and return early.
2. **Extract PDF text** — call `self.resource_extractor.extract_text_from_lessons(context_data["lessons"])`. This returns a `dict[lesson_id, extracted_text]`.
3. **Build enriched context** — merge the PDF text into the combined context:
   ```python
   pdf_texts = await self.resource_extractor.extract_text_from_lessons(
       context_data["lessons"]
   )
   # Build combined_text with PDF content inline
   sections = [f"## Module: {context_data['module_title']}\n{context_data['module_description']}"]
   for lesson in context_data["lessons"]:
       lid = lesson["lesson_id"]
       section = f"### Lesson: {lesson['title']}\n{lesson.get('text_content', '')}"
       if lid in pdf_texts:
           section += f"\n\n#### PDF Resources:\n{pdf_texts[lid]}"
       sections.append(section)
   combined_text = "\n\n".join(sections)
   ```
4. **Call LLM** — call `self.openai_client.generate_summary(...)` passing the enriched `combined_text` and the request flags (`include_glossary`, `include_key_points`, `include_learning_objectives`, `max_length_words`, `tone`, `language`).
5. **Build persistence payload** — convert the `GeneratedSummary` Pydantic model to a dict matching `SummaryCreate`:
   ```python
   payload = {
       "title": generated.title,
       "content": {
           "summary_text": generated.content.summary_text,
           "key_points": generated.content.key_points,
           "learning_objectives": generated.content.learning_objectives,
           "glossary": [g.model_dump() for g in generated.content.glossary],
           "difficulty_assessment": (
               generated.content.difficulty_assessment.model_dump()
               if generated.content.difficulty_assessment else None
           ),
       },
       "is_published": False,
   }
   ```
   > **Note:** Authorship fields (`source: "ai_generated"`, `ai_model`, `source_lesson_ids`) are managed by the course-service internally on create. If the course-service expects them in the request body, add them. Otherwise, the course-service `create_summary` service method sets authorship from the `instructor_id` and request context. Check course-service `ModuleSummaryService.create_summary` to confirm.
4. **Save via HTTP** — call `self.course_client.save_summary(course_id, module_id, payload, user_id)`.
5. **Error handling** — wrap the entire method body in `try/except Exception`, log with `structlog`, and never let exceptions propagate (it's a background task).

### Private method `_process_and_save_quiz`:

```python
async def _process_and_save_quiz(
    self,
    course_id: int,
    module_id: str,
    request: GenerateQuizRequest,
    user_id: int,
) -> None:
```

**Steps:**
1. **Fetch content** — same as summary: call `get_module_with_lessons`, then `extract_text_from_lessons`, then build enriched `combined_text`.
2. **Call LLM** — call `self.openai_client.generate_quiz(...)` passing the enriched `combined_text`, `request.num_questions`, `request.difficulty`, `[qt.value for qt in request.question_types]`, `request.language`.
3. **Build persistence payload** matching `QuizCreate`:
   ```python
   payload = {
       "title": generated.title,
       "description": generated.description,
       "settings": {
           "passing_score": request.passing_score,
           "time_limit_minutes": request.time_limit_minutes,
           "max_attempts": request.max_attempts,
           "shuffle_questions": True,
           "shuffle_options": True,
           "show_correct_answers_after": "completion",
       },
       "questions": [q.model_dump() for q in generated.questions],
       "is_published": False,
   }
   ```
4. **Save via HTTP** — call `self.course_client.save_quiz(course_id, module_id, payload, user_id)`.
5. **Error handling** — same as summary.

### Updated `generate_all`:

Kick off both `_process_and_save_summary` and `_process_and_save_quiz` as separate `asyncio.create_task` calls (they run in parallel). Return both responses with `status=PENDING`.

### Updated `get_generation_status`:

Query the MongoDB read-only collections to check if quiz/summary exist:
```python
existing_summary = await self.repo.get_existing_summary(course_id, module_id)
existing_quiz = await self.repo.get_existing_quiz(course_id, module_id)
```
Return `GenerationStatusResponse` with:
- `summary_status = COMPLETED if existing_summary else PENDING`
- `quiz_status = COMPLETED if existing_quiz else PENDING`
- `last_generation_at` from whichever document is newer

> **Note on status tracking:** This simple approach (check if document exists) works for the initial implementation. For more granular tracking (pending → in_progress → completed/failed), you could use Redis to store ephemeral generation status keyed by `{course_id}:{module_id}:summary_status` and `{course_id}:{module_id}:quiz_status`. Update Redis at the start and end of each background task. This is optional for v1 but recommended if the frontend needs real-time status feedback.

---

## Step 6: Update the Router and Wiring

### File: `services/ai-service/src/ai_service/api/instructor.py`

**Changes needed:**

1. Remove the module-level `instructor_service = InstructorService()` singleton.
2. Create a dependency function that builds `InstructorService` with its dependencies:

```python
from ai_service.core.mongodb import get_mongodb
from ai_service.repositories.course_content import CourseContentRepository
from ai_service.clients.openai_client import OpenAIClient
from ai_service.clients.course_service_client import CourseServiceClient
from ai_service.clients.resource_extractor import ResourceTextExtractor

def get_instructor_service() -> InstructorService:
    db = get_mongodb()
    repo = CourseContentRepository(db)
    openai_client = OpenAIClient()
    course_client = CourseServiceClient()
    resource_extractor = ResourceTextExtractor()
    return InstructorService(repo, openai_client, course_client, resource_extractor)
```

3. Update each endpoint to use `Depends(get_instructor_service)` and pass `user_id` to the service:

**Example for `generate_summary`:**
```python
@router.post(
    "/modules/{module_id}/generate-summary",
    response_model=GenerateSummaryResponse,
    status_code=status.HTTP_202_ACCEPTED,   # <── Changed from 200 to 202
)
async def generate_summary(
    module_id: str,
    course_id: int,
    request: GenerateSummaryRequest,
    user_id: int = Depends(require_instructor),
    service: InstructorService = Depends(get_instructor_service),
) -> GenerateSummaryResponse:
    return await service.generate_summary(course_id, module_id, request, user_id)
```

4. Change status codes from `200` to `202 Accepted` for the three generation endpoints (summary, quiz, generate-all) since work is now asynchronous.
5. The `GET /generation-status` endpoint stays `200`.

---

## Step 7: Update `main.py` Lifespan (Optional Optimization)

### File: `services/ai-service/src/ai_service/main.py`

No changes are strictly required since `OpenAIClient` and `CourseServiceClient` are lightweight and can be instantiated per-request. However, if you want to share a single `httpx.AsyncClient` across requests (connection pooling), you can:

1. Create a global `httpx.AsyncClient` in the lifespan:
   ```python
   _http_client: httpx.AsyncClient | None = None

   async def lifespan(app):
       global _http_client
       _http_client = httpx.AsyncClient(timeout=30.0)
       # ... existing startup ...
       yield
       # ... existing shutdown ...
       await _http_client.aclose()
   ```
2. Expose it via a `get_http_client()` getter and inject it into `CourseServiceClient`.

This is optional for v1. The per-request `async with httpx.AsyncClient()` approach in Step 3 works fine for low-to-moderate traffic.

---

## File Change Summary

| File | Action | Description |
|------|--------|-------------|
| `pyproject.toml` | **Edit** | Add `openai>=1.40.0` and `PyMuPDF>=1.24.0` to dependencies |
| `src/ai_service/repositories/course_content.py` | **Edit** | Add `get_module_with_lessons()` method (include `resources` in output) |
| `src/ai_service/clients/__init__.py` | **Create** | Empty init file |
| `src/ai_service/clients/resource_extractor.py` | **Create** | PDF download + text extraction from S3 lesson resources |
| `src/ai_service/clients/course_service_client.py` | **Create** | HTTP client for course-service persistence |
| `src/ai_service/clients/openai_client.py` | **Create** | OpenAI client with structured output models |
| `src/ai_service/services/instructor.py` | **Edit** | Add constructor with 4 deps, background task methods with PDF extraction, update public methods |
| `src/ai_service/api/instructor.py` | **Edit** | Add DI function (including ResourceTextExtractor), pass `user_id`, change to `202` status |

---

## Course-Service Endpoint Reference

These are the exact endpoints in the course-service that the `CourseServiceClient` will call:

```
POST  {COURSE_SERVICE_URL}/{course_id}/modules/{module_id}/summary
  Body: SummaryCreate { title, content: SummaryContentCreate, is_published }
  Headers: X-User-ID, X-User-Role: "instructor"
  Returns: 201 + SummaryResponse  |  409 if already exists

PUT   {COURSE_SERVICE_URL}/{course_id}/modules/{module_id}/summary
  Body: SummaryUpdate { title, content: SummaryContentCreate, is_published }
  Headers: X-User-ID, X-User-Role: "instructor"
  Returns: 200 + SummaryResponse

POST  {COURSE_SERVICE_URL}/{course_id}/modules/{module_id}/quiz
  Body: QuizCreate { title, description, settings: QuizSettingsSchema, questions: [QuizQuestionCreate], is_published }
  Headers: X-User-ID, X-User-Role: "instructor"
  Returns: 201 + QuizResponse  |  409 if already exists

PUT   {COURSE_SERVICE_URL}/{course_id}/modules/{module_id}/quiz
  Body: QuizUpdate { title, description, settings: QuizSettingsSchema, questions: [QuizQuestionCreate], is_published }
  Headers: X-User-ID, X-User-Role: "instructor"
  Returns: 200 + QuizResponse
```

### QuizQuestionCreate Validation Rules (enforced by course-service):

| `question_type` | `options` | `correct_answers` | Special rules |
|---|---|---|---|
| `multiple_choice` | Required, 4 options | Must NOT be set | Exactly 1 option with `is_correct: true` |
| `multiple_select` | Required | Must NOT be set | At least 1 option with `is_correct: true` |
| `true_false` | Required: `option_id` must be `opt_true` and `opt_false` | Must NOT be set | Exactly 1 correct |
| `short_answer` | Must NOT be set | Required, non-empty list | `case_sensitive` defaults to `false` |

Make sure the LLM prompt explicitly states these rules to avoid validation errors on persist.
