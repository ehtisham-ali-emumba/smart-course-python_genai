# Graph Instance Centralization — Changes Applied

All LangGraph compiled graphs (tutor, quiz, summary) are now built **once at server startup** and reused across requests. Below are the changes made.

---

## New File Created

### `core/service_factory.py`

Centralizes all service singleton creation logic. Called from `main.py` during startup.

- `create_tutor_service(openai_client, vector_store)` — builds TutorService (tutor graph compiled once)
- `create_instructor_service(openai_client)` — builds InstructorService (quiz + summary graphs compiled once), wires up all dependencies (MongoDB repo, Redis status tracker, course client, content extractor) internally

---

## Files Modified

### 1. `main.py`

- **Removed:** Direct `TutorService` import and manual instantiation
- **Added:** Imports from `core.service_factory` (`create_tutor_service`, `create_instructor_service`)
- **Added:** Import `set_instructor_service` from dependencies
- **Changed:** `lifespan()` now uses factory functions and registers both singletons:
  ```python
  tutor_service = create_tutor_service(openai_client, _vector_store)
  set_tutor_service(tutor_service)

  instructor_service = create_instructor_service(openai_client)
  set_instructor_service(instructor_service)
  ```

### 2. `api/dependencies.py`

- **Added:** `InstructorService` import
- **Added:** Instructor singleton pattern (matching the existing tutor pattern):
  ```python
  _instructor_service: InstructorService | None = None

  def set_instructor_service(svc: InstructorService) -> None: ...
  def get_instructor_service() -> InstructorService: ...
  ```

### 3. `api/instructor.py`

- **Removed:** Local `get_instructor_service()` factory that created a new `InstructorService` (and rebuilt graphs) per request
- **Removed:** All unused imports (`get_mongodb`, `get_redis`, `CourseContentRepository`, `OpenAIClient`, `CourseServiceClient`, `ResourceTextExtractor`, `ContentExtractor`, `GenerationStatusTracker`)
- **Added:** `get_instructor_service` import from `api.dependencies` (now returns the singleton)

### 4. `services/instructor.py` (already changed)

Graphs built once in `__init__`:
```python
self._summary_graph = build_summary_graph(openai_client, course_client, content_extractor)
self._quiz_graph = build_quiz_graph(openai_client, course_client, content_extractor)
```
Used via `self._summary_graph` / `self._quiz_graph` in `_run_summary_graph` / `_run_quiz_graph`.

### 5. `services/tutor.py` (already changed)

Graph built once in `__init__`:
```python
self._tutor_graph = build_tutor_graph(openai_client=openai_client, vector_store=vector_store)
```
Used via `self._tutor_graph` in `_run_agent`.

---

## Why This Works

LangGraph `CompiledStateGraph` is **stateless** — all mutable data flows through the `State` dict passed to `ainvoke()`. The graph structure (nodes, edges, compiled transitions) never changes. Building once and reusing is both safe and more efficient.
