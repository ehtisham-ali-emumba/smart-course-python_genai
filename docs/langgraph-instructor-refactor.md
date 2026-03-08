# LangGraph Refactor: Quiz & Summary Generation

## Goal

Replace the current linear OpenAI calls in `InstructorService` with LangGraph state machines for both quiz and summary generation. Add a **validation node** after generation that checks output quality and can trigger a retry with feedback.

---

## Current Implementation (What Exists)

### Files Involved

| File | Role |
|------|------|
| `services/instructor.py` | `InstructorService` — orchestrates the full flow inline (extract → generate → normalize → persist) |
| `clients/openai_client.py` | `OpenAIClient` — wraps OpenAI structured output calls (`generate_summary`, `generate_quiz`) |
| `api/instructor.py` | FastAPI endpoints — injects `InstructorService`, returns 202 ACCEPTED |
| `services/generation_status.py` | Redis-based status tracker (PENDING → IN_PROGRESS → COMPLETED/FAILED) |
| `services/content_extractor.py` | Extracts lesson content from MongoDB + PDFs |
| `clients/course_service_client.py` | HTTP client to persist quiz/summary to course-service |
| `schemas/instructor.py` | Request/response Pydantic models |
| `schemas/common.py` | Enums: `GenerationStatus`, `DifficultyLevel`, `QuestionType` |

### Current Flow (Both Quiz & Summary)

```
Endpoint (202 ACCEPTED) → asyncio.create_task() → Background:
  1. status_tracker.set_in_progress()
  2. content_extractor.extract_module_content()
  3. openai_client.generate_quiz() / generate_summary()  ← single OpenAI call
  4. Normalize response (quiz only: _build_quiz_payload / _normalize_generated_question)
  5. course_client.save_quiz() / save_summary()
  6. status_tracker.set_completed() or set_failed()
```

No validation. No retry. Single LLM call with structured output.

### Reference: Existing LangGraph Usage (Tutor Agent)

`services/tutor_agent.py` already uses LangGraph with:
- `TypedDict` state (`TutorState`)
- Factory functions for nodes (`_build_retrieve_node`, `_build_generate_node`)
- `StateGraph` with `START → retrieve → generate → END`
- Dependencies injected via closures (not LangChain wrappers)
- OpenAI called directly via `openai_client` (not LangChain's ChatOpenAI)

**Follow this exact same pattern** for the instructor graphs.

---

## New LangGraph Architecture

### New File to Create

**`services/instructor_graphs.py`** — Contains both quiz and summary LangGraph definitions.

### Quiz Generation Graph

```
START → extract_content → generate_quiz → validate_quiz ─→ persist_quiz → END
                                ↑              │
                                └──── (retry) ←┘ (if validation fails & retries < MAX_RETRIES)
```

**Nodes:**

1. **`extract_content`** — Calls `content_extractor.extract_module_content()`. Sets `combined_text` in state. If no content found, sets `error` and short-circuits to END.

2. **`generate_quiz`** — Calls `openai_client.generate_quiz()` with params from state. If `validation_feedback` exists in state (retry), appends it as extra instructions to the prompt so the LLM fixes the issues.

3. **`validate_quiz`** — Checks the `GeneratedQuiz` object for:
   - Question count matches `num_questions`
   - No empty `question_text`
   - Option-based questions have ≥2 options with at least 1 correct
   - `short_answer` questions have `correct_answers`
   - Each question has an `explanation`

   Sets `validation_passed` (bool) and `validation_feedback` (string of issues).

4. **`persist_quiz`** — Runs the existing normalization logic (`_build_quiz_payload` / `_normalize_generated_question` — move these here as module-level functions). Calls `course_client.save_quiz()`. Sets `persisted` flag.

**Conditional Edges:**

- After `extract_content`: → END if `error` is set, else → `generate_quiz`
- After `validate_quiz`: → `persist_quiz` if passed OR retries exhausted (MAX_RETRIES=1), else → `generate_quiz`

**State (`QuizState`, TypedDict):**

```python
class QuizState(TypedDict, total=False):
    # Input
    course_id: int
    module_id: str
    user_id: int
    source_lesson_ids: list[str] | None
    num_questions: int
    difficulty: str | None
    question_types: list[str]
    language: str
    passing_score: int
    max_attempts: int
    time_limit_minutes: int | None

    # Intermediate
    combined_text: str
    generated_quiz: GeneratedQuiz
    validation_passed: bool
    validation_feedback: str
    retry_count: int

    # Output
    persisted: bool
    error: str | None
```

### Summary Generation Graph

```
START → extract_content → generate_summary → validate_summary ─→ persist_summary → END
                                  ↑                 │
                                  └──── (retry) ←───┘
```

**Nodes:**

1. **`extract_content`** — Same pattern as quiz. Sets `combined_text` or `error`.

2. **`generate_summary`** — Calls `openai_client.generate_summary()` with params from state. Appends `validation_feedback` if retrying.

3. **`validate_summary`** — Checks the `GeneratedSummary` object for:
   - Title is not empty
   - `summary_text` is at least 50 characters
   - `key_points` present if `include_key_points` was True
   - `learning_objectives` present if `include_learning_objectives` was True
   - `glossary` present if `include_glossary` was True
   - `difficulty_assessment` is present
   - Word count within `max_length_words * 1.2` tolerance (if limit was set)

4. **`persist_summary`** — Builds the payload dict (same structure as current `_process_and_save_summary`). Calls `course_client.save_summary()`.

**State (`SummaryState`, TypedDict):**

```python
class SummaryState(TypedDict, total=False):
    # Input
    course_id: int
    module_id: str
    user_id: int
    source_lesson_ids: list[str] | None
    include_glossary: bool
    include_key_points: bool
    include_learning_objectives: bool
    max_length_words: int | None
    tone: str | None
    language: str

    # Intermediate
    combined_text: str
    generated_summary: GeneratedSummary
    validation_passed: bool
    validation_feedback: str
    retry_count: int

    # Output
    persisted: bool
    error: str | None
```

---

## Changes to Existing Files

### 1. `services/instructor.py` — Simplify to Graph Invocation

**Remove:**
- `_process_and_save_summary()` method (entire background logic)
- `_process_and_save_quiz()` method (entire background logic)
- `_build_quiz_payload()` method (moved to `instructor_graphs.py`)
- `_normalize_generated_question()` method (moved to `instructor_graphs.py`)

**Keep:**
- `_validate_course_ownership_and_module()` — still runs before dispatching
- `generate_summary()` / `generate_quiz()` — still the public API, still return 202
- `get_generation_status()` — unchanged

**Replace background tasks with graph invocations:**

The two new background methods should:
1. Call `status_tracker.set_in_progress()`
2. Build the graph via `build_quiz_graph()` / `build_summary_graph()`
3. Invoke the graph with `await graph.ainvoke(initial_state)`
4. Check the final state for `persisted` / `error`
5. Call `status_tracker.set_completed()` or `set_failed()`

Example skeleton for `_run_quiz_graph`:

```python
async def _run_quiz_graph(self, course_id, module_id, request, user_id):
    try:
        await self.status_tracker.set_in_progress(course_id, module_id, "quiz")

        graph = build_quiz_graph(self.openai_client, self.course_client, self.content_extractor)

        result = await graph.ainvoke({
            "course_id": course_id,
            "module_id": module_id,
            "user_id": user_id,
            "source_lesson_ids": request.source_lesson_ids,
            "num_questions": request.num_questions,
            "difficulty": request.difficulty.value if request.difficulty else None,
            "question_types": [qt.value for qt in request.question_types],
            "language": request.language,
            "passing_score": request.passing_score,
            "max_attempts": request.max_attempts,
            "time_limit_minutes": request.time_limit_minutes,
        })

        if result.get("persisted"):
            await self.status_tracker.set_completed(course_id, module_id, "quiz")
        else:
            await self.status_tracker.set_failed(
                course_id, module_id, "quiz", result.get("error", "Unknown error")
            )
    except Exception as e:
        await self.status_tracker.set_failed(course_id, module_id, "quiz", str(e))
        logger.exception("Quiz generation graph failed", error=str(e))
```

Same pattern for `_run_summary_graph`.

### 2. `clients/openai_client.py` — No Changes

Keep as-is. The LangGraph nodes call the same `openai_client.generate_quiz()` and `openai_client.generate_summary()` methods. We stay on OpenAI under the hood.

### 3. `api/instructor.py` — No Changes

Endpoints stay the same. They still call `service.generate_quiz()` / `service.generate_summary()` and get back a 202 response.

### 4. `schemas/` — No Changes

Request/response schemas are unchanged. The state TypedDicts live inside `instructor_graphs.py`.

---

## Node Function Pattern

Follow the same closure/factory pattern from `tutor_agent.py`:

```python
def _build_generate_quiz_node(openai_client: OpenAIClient):
    async def generate_quiz(state: QuizState) -> dict:
        # ... use openai_client from closure
        return {"generated_quiz": generated}
    return generate_quiz
```

Each node function:
- Receives `state` (the TypedDict)
- Returns a `dict` with only the keys it wants to update
- LangGraph merges the returned dict into the state automatically

---

## Conditional Edge Pattern

Use a plain function that reads state and returns the next node name:

```python
def _quiz_validation_router(state: QuizState) -> Literal["generate_quiz", "persist_quiz"]:
    if state["validation_passed"]:
        return "persist_quiz"
    if state.get("retry_count", 0) <= MAX_RETRIES:
        return "generate_quiz"
    return "persist_quiz"  # exhausted retries, proceed anyway
```

Wire it with `graph.add_conditional_edges("validate_quiz", _quiz_validation_router)`.

---

## Retry Mechanism

When validation fails and a retry happens:
- `retry_count` is incremented
- `validation_feedback` contains a bullet list of specific issues
- The `generate_*` node appends this feedback to the prompt so the LLM can self-correct
- `MAX_RETRIES = 1` (one retry attempt; after that, proceed with what we have)

---

## Summary of File Changes

| File | Action |
|------|--------|
| `services/instructor_graphs.py` | **CREATE** — Two LangGraph definitions (quiz + summary) with states, nodes, validation, conditional edges |
| `services/instructor.py` | **EDIT** — Replace `_process_and_save_*` with graph invocation wrappers. Remove `_build_quiz_payload` and `_normalize_generated_question` (moved to graphs file) |
| `clients/openai_client.py` | No changes |
| `api/instructor.py` | No changes |
| `schemas/instructor.py` | No changes |
| `schemas/common.py` | No changes |

---

## What This Achieves

1. **LangGraph orchestration** — Both flows are now proper state machines, matching the tutor agent pattern your manager expects to see.
2. **Validation node** — Post-generation quality gate that catches bad outputs (empty fields, wrong question counts, missing explanations).
3. **Self-healing retry** — Validation feedback is fed back to the LLM for a corrective second attempt.
4. **Conditional routing** — Graph uses `add_conditional_edges` for branching (early exit on no content, retry vs proceed after validation).
5. **Same output** — The final persisted quiz/summary payload is identical to what the current code produces. No API or schema changes needed.
