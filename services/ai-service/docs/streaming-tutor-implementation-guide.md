# Streaming AI Tutor - Implementation Guide (LangGraph Native)

> Convert the tutor chat from HTTP request-response to **SSE streaming** using LangGraph's built-in streaming APIs (`astream` with `stream_mode`) and `ChatOpenAI` for automatic token-level streaming.

---

## Current Architecture

```
Client  ──POST /sessions/{id}/messages──>  FastAPI
                                             │
                                        TutorService._run_agent()
                                             │
                                        graph.ainvoke(state)
                                        LangGraph: RETRIEVE → GENERATE → END
                                             │
                                        openai_client.chat_completion()  ← raw SDK, blocks until done
                                             │
Client  <──── Full JSON response ────────────
```

**Problem:** `ainvoke()` waits for the entire LLM response before returning. The student sees nothing for 3-10 seconds.

## Target Architecture

```
Client  ──POST /sessions/{id}/messages/stream──>  FastAPI (StreamingResponse)
                                                      │
                                                 TutorService.stream_message()
                                                      │
                                                 graph.astream(state, stream_mode=["messages", "custom"])
                                                      │
                                              RETRIEVE node  ─── writer({"event":"sources", ...})
                                                      │              ↓ (custom stream)
                                              GENERATE node  ─── ChatOpenAI(streaming=True)
                                                                     ↓ (messages stream, token by token)
Client  <──── SSE events ─────────────────────────────
                data: {"event": "sources", "sources": [...]}
                data: {"event": "token", "content": "Hello"}
                data: {"event": "token", "content": " there"}
                data: {"event": "done", "message_id": "abc123"}
```

**Key LangGraph features used:**
- `stream_mode=["messages", "custom"]` — combines LLM token streaming with custom events
- `ChatOpenAI(streaming=True)` — LangChain wrapper that integrates with LangGraph's streaming callbacks automatically
- `get_stream_writer()` — emits custom events (sources, status) from inside graph nodes

---

## Why These LangGraph APIs?

| API | Purpose | Why not alternatives |
|---|---|---|
| `stream_mode="messages"` | Token-by-token LLM streaming | `astream_events` is lower-level and noisier — you'd filter through dozens of event types. `"messages"` gives you exactly LLM tokens. |
| `stream_mode="custom"` | Emit structured events (sources, status) from nodes | Cleaner than `adispatch_custom_event` which has async context issues. `get_stream_writer()` is the LangGraph-recommended approach (>=0.2). |
| `ChatOpenAI` wrapper | Enables `stream_mode="messages"` | Raw OpenAI SDK calls are invisible to LangGraph's callback system — tokens won't appear in `"messages"` mode. You already have `langchain-openai` in your deps. |
| Combined `["messages", "custom"]` | Single `astream()` call for everything | Avoids running the graph twice or managing two separate streams. |

---

## Implementation Steps

### Step 1: Update the GENERATE Node to Use `ChatOpenAI`

**File:** `src/ai_service/services/tutor_agent.py`

Currently the generate node calls `openai_client.chat_completion()` (raw SDK). LangGraph can't see inside that call, so it can't stream tokens. Switch the generate node to use `ChatOpenAI`.

**Changes:**

```python
# ── New imports ──
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.config import get_stream_writer
from ai_service.config import settings

# ...existing code stays...
```

**Replace `_build_generate_node`:**

```python
def _build_generate_node(openai_client: OpenAIClient):
    """Factory that creates the GENERATE node function.

    Uses ChatOpenAI for LangGraph-native token streaming support.
    The raw openai_client is kept for non-streaming use (embeddings, etc.).
    """
    # ChatOpenAI integrates with LangGraph's callback system,
    # enabling stream_mode="messages" to yield individual tokens.
    llm = ChatOpenAI(
        model=settings.OPENAI_MODEL,
        api_key=settings.OPENAI_API_KEY,
        temperature=0.7,
        max_tokens=1024,
        streaming=True,
    )

    async def generate(state: TutorState) -> dict:
        """Build the prompt and generate a response via ChatOpenAI."""
        query = state["query"]
        context_text = state.get("context_text", "")
        conversation_history = state.get("conversation_history", [])

        # 1. Build the system prompt with retrieved context
        system_prompt = TUTOR_SYSTEM_PROMPT.format(context=context_text)

        # 2. Build message list using LangChain message types
        messages = [SystemMessage(content=system_prompt)]

        # Add conversation history (last 10 messages = 5 turns)
        max_history = 10
        recent_history = conversation_history[-max_history:]
        for msg in recent_history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                messages.append(AIMessage(content=msg["content"]))

        # Add the current question
        messages.append(HumanMessage(content=query))

        # 3. Call the LLM — LangGraph intercepts this for token streaming
        response = await llm.ainvoke(messages)

        logger.info(
            "Tutor response generated",
            response_length=len(response.content),
            history_messages=len(recent_history),
            context_chunks=len(state.get("retrieved_chunks", [])),
        )

        return {"response": response.content}

    return generate
```

**Why this works for streaming:** When you call `graph.astream(..., stream_mode="messages")`, LangGraph hooks into `ChatOpenAI`'s callback system and yields each `AIMessageChunk` as the LLM produces it. The `ainvoke()` call inside the node still completes normally and returns the final state — but the tokens are intercepted and streamed out in parallel.

---

### Step 2: Add `get_stream_writer()` to the RETRIEVE Node

**File:** `src/ai_service/services/tutor_agent.py`

The retrieve node runs fast (embedding + vector search), but we want to emit the sources as a custom event so the client gets them before any tokens arrive.

**Update `_build_retrieve_node`** — add writer calls at the end:

```python
def _build_retrieve_node(
    openai_client: OpenAIClient,
    vector_store: VectorStoreRepository,
):
    """Factory that creates the RETRIEVE node function with injected dependencies."""

    async def retrieve(state: TutorState) -> dict:
        """Embed the query and search Qdrant for relevant chunks."""
        writer = get_stream_writer()  # <-- NEW

        query = state["query"]
        course_id = state["course_id"]
        module_id = state.get("module_id")
        lesson_id = state.get("lesson_id")

        log = logger.bind(
            course_id=course_id,
            module_id=module_id,
            lesson_id=lesson_id,
        )

        # 1. Embed the student's question
        query_embedding = await openai_client.embed_query(query)

        # 2. Search Qdrant
        raw_results = await vector_store.search(
            query_embedding=query_embedding,
            course_id=course_id,
            module_id=module_id,
            lesson_id=lesson_id,
            top_k=TOP_K,
        )

        # 3. Filter by score threshold
        chunks = [chunk for chunk in raw_results if chunk.get("score", 0) >= SCORE_THRESHOLD]

        log.info(
            "RAG retrieval completed",
            total_results=len(raw_results),
            after_threshold=len(chunks),
            top_score=chunks[0]["score"] if chunks else 0,
        )

        # 4. Format context for the LLM prompt
        if chunks:
            context_parts = []
            for i, chunk in enumerate(chunks, 1):
                module_title = chunk.get("module_title", "Unknown Module")
                lesson_title = chunk.get("lesson_title", "Unknown Lesson")
                text = chunk.get("text", "")
                context_parts.append(
                    f"### Source {i} "
                    f'(Module: "{module_title}", Lesson: "{lesson_title}")\n'
                    f"{text}"
                )
            context_text = "\n\n".join(context_parts)
        else:
            context_text = "(No relevant context found in the course materials.)"

        # 5. Build source attributions
        sources = [
            {
                "module_title": chunk.get("module_title", ""),
                "lesson_title": chunk.get("lesson_title", ""),
                "module_id": chunk.get("module_id", ""),
                "lesson_id": chunk.get("lesson_id", ""),
                "chunk_index": chunk.get("chunk_index", 0),
                "score": chunk.get("score", 0),
                "text_preview": chunk.get("text", "")[:200],
            }
            for chunk in chunks
        ]

        # 6. Emit sources as a custom stream event  <-- NEW
        writer({
            "event": "sources",
            "sources": sources,
        })

        return {
            "retrieved_chunks": chunks,
            "context_text": context_text,
            "sources": sources,
        }

    return retrieve
```

**Only 2 lines added:** `writer = get_stream_writer()` and the `writer({...})` call. Everything else is your existing code.

---

### Step 3: Add `stream_message()` to `TutorService`

**File:** `src/ai_service/services/tutor.py`

Add a new method alongside the existing `send_message()` (keep the original for backward compatibility):

```python
import json
from collections.abc import AsyncIterator


async def stream_message(
    self,
    session_id: str,
    user_id: _uuid.UUID,
    request: SendMessageRequest,
) -> AsyncIterator[str]:
    """Stream a tutor response as SSE events using LangGraph's native streaming.

    Uses graph.astream() with stream_mode=["messages", "custom"]:
    - "messages" mode: yields AIMessageChunk tokens from ChatOpenAI
    - "custom" mode: yields custom events from get_stream_writer() (sources, status)

    Yields:
        SSE-formatted strings: 'data: {"event": "...", ...}\n\n'
    """
    log = logger.bind(session_id=session_id, user_id=user_id)

    # ── Validate session (same checks as send_message) ──
    session = self._sessions.get(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found. Please create a new session.")
    if session["student_id"] != user_id:
        raise ValueError("Session does not belong to this user.")

    module_id = request.module_id or session.get("module_id")
    lesson_id = request.lesson_id or session.get("lesson_id")

    # ── Prepare graph input state ──
    initial_state: TutorState = {
        "query": request.message,
        "course_id": session["course_id"],
        "module_id": module_id,
        "lesson_id": lesson_id,
        "conversation_history": session["history"],
    }

    # ── Stream from the LangGraph graph ──
    full_response_tokens: list[str] = []

    try:
        async for mode, payload in self._tutor_graph.astream(
            initial_state,
            stream_mode=["messages", "custom"],
        ):
            if mode == "custom":
                # Custom events from get_stream_writer() (e.g., sources from retrieve node)
                yield f"data: {json.dumps(payload)}\n\n"

            elif mode == "messages":
                # LLM token chunks from ChatOpenAI in the generate node
                # payload is a tuple: (AIMessageChunk, metadata_dict)
                chunk, metadata = payload

                # Only emit tokens from the generate node, and only non-empty content
                if metadata.get("langgraph_node") == "generate" and chunk.content:
                    full_response_tokens.append(chunk.content)
                    yield f"data: {json.dumps({'event': 'token', 'content': chunk.content})}\n\n"

    except Exception as e:
        log.error("Streaming failed", error=str(e))
        yield f"data: {json.dumps({'event': 'error', 'message': 'Response generation failed. Please try again.'})}\n\n"
        return

    # ── Update conversation history (after stream completes) ──
    complete_text = "".join(full_response_tokens)
    session["history"].append({"role": "user", "content": request.message})
    session["history"].append({"role": "assistant", "content": complete_text})

    if len(session["history"]) > MAX_HISTORY_PER_SESSION:
        session["history"] = session["history"][-MAX_HISTORY_PER_SESSION:]

    # ── Emit done event ──
    message_id = uuid4().hex
    yield f"data: {json.dumps({'event': 'done', 'message_id': message_id})}\n\n"

    log.info(
        "Streamed tutor response",
        response_length=len(complete_text),
    )
```

**How `astream` with combined modes works:**

```python
async for mode, payload in graph.astream(state, stream_mode=["messages", "custom"]):
```

When you pass a list of modes, each yielded item is a `(mode_name, payload)` tuple:
- `mode == "custom"` → `payload` is whatever you passed to `writer(...)` in the node
- `mode == "messages"` → `payload` is `(AIMessageChunk, metadata)` where metadata includes `langgraph_node` telling you which node produced it

This is why we filter `metadata.get("langgraph_node") == "generate"` — we only want tokens from the generate node, not any other LangChain internals.

---

### Step 4: Add the Streaming Endpoint

**File:** `src/ai_service/api/tutor.py`

Add a new endpoint. Keep the existing `send_message` endpoint unchanged.

```python
from fastapi.responses import StreamingResponse


@router.post(
    "/sessions/{session_id}/messages/stream",
    status_code=status.HTTP_200_OK,
)
async def stream_message(
    session_id: str,
    request: SendMessageRequest,
    user_info: tuple[_uuid.UUID, str] = Depends(get_authenticated_user),
    tutor_service: TutorService = Depends(get_tutor_service),
) -> StreamingResponse:
    """Stream a tutor response as Server-Sent Events.

    Uses LangGraph's native astream() with combined stream modes
    for token-level streaming and custom events.

    SSE event types:
    - sources: RAG sources used (emitted by retrieve node before generation starts)
    - token:   Individual text token from the LLM (emitted during generation)
    - error:   If something fails mid-stream
    - done:    Stream complete, includes message_id
    """
    user_id = user_info[0]

    # Validate session upfront (before opening the stream)
    try:
        session = tutor_service._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found.")
        if session["student_id"] != user_id:
            raise ValueError("Session does not belong to this user.")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    return StreamingResponse(
        tutor_service.stream_message(session_id, user_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Prevents nginx from buffering SSE
        },
    )
```

---

## SSE Event Protocol

| Event | Payload | Produced By |
|---|---|---|
| `sources` | `{"event": "sources", "sources": [...]}` | `get_stream_writer()` in retrieve node |
| `token` | `{"event": "token", "content": "..."}` | `stream_mode="messages"` from ChatOpenAI |
| `error` | `{"event": "error", "message": "..."}` | Exception handler in `stream_message()` |
| `done` | `{"event": "done", "message_id": "..."}` | After stream completes in `stream_message()` |

**Event order:** `sources` (once) → `token` (many) → `done` (once)

---

## Files Changed (Summary)

| File | What Changes |
|---|---|
| `services/tutor_agent.py` | (1) Import `ChatOpenAI`, `get_stream_writer`, LangChain message types. (2) Replace `_build_generate_node` to use `ChatOpenAI` instead of raw `openai_client.chat_completion()`. (3) Add `writer = get_stream_writer()` + `writer(...)` call in `_build_retrieve_node`. |
| `services/tutor.py` | Add `stream_message()` async generator method using `self._tutor_graph.astream(..., stream_mode=["messages", "custom"])`. |
| `api/tutor.py` | Add `POST /sessions/{session_id}/messages/stream` endpoint returning `StreamingResponse`. |

**No changes to:** `schemas/tutor.py`, `clients/openai_client.py`, `main.py`, `config.py`, `service_factory.py`, session creation endpoint, or existing `send_message` endpoint.

---

## What Stays the Same

- **Session creation** (`POST /sessions`) — unchanged. `initial_message` still uses `ainvoke()` (non-streaming). This is fine since it's a setup call, not a chat interaction.
- **Non-streaming endpoint** (`POST /sessions/{id}/messages`) — kept for backward compatibility. Uses the same graph via `ainvoke()` as before.
- **Graph structure** — still `RETRIEVE → GENERATE → END`. The graph itself is identical; only the internal implementation of the two node functions changes.
- **Retrieval logic** — identical RAG search (same embeddings, same Qdrant query, same score threshold, same context formatting).
- **Auth** — same `X-User-ID` / `X-User-Role` headers. SSE is still a standard HTTP POST.
- **`openai_client.py`** — no changes. The `chat_completion()` method is still used by `ainvoke()` for the non-streaming path. Only the graph's generate node switches to `ChatOpenAI`.

---

## Client-Side Consumption

**JavaScript (browser):**

```javascript
async function sendStreamingMessage(sessionId, message) {
  const response = await fetch(
    `/api/v1/ai/tutor/sessions/${sessionId}/messages/stream`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-ID': userId,
        'X-User-Role': 'student',
      },
      body: JSON.stringify({ message }),
    }
  );

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n\n');
    buffer = lines.pop(); // Keep incomplete chunk in buffer

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const data = JSON.parse(line.slice(6));

      switch (data.event) {
        case 'sources':
          displaySources(data.sources);
          break;
        case 'token':
          appendToMessage(data.content); // Append token to chat bubble
          break;
        case 'error':
          showError(data.message);
          break;
        case 'done':
          finalizeMessage(data.message_id);
          break;
      }
    }
  }
}
```

**Python (httpx, for testing):**

```python
import httpx
import json

async def test_streaming():
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            f"{base_url}/api/v1/ai/tutor/sessions/{session_id}/messages/stream",
            json={"message": "What is React?"},
            headers={"X-User-ID": user_id, "X-User-Role": "student"},
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    event = json.loads(line[6:])
                    if event["event"] == "token":
                        print(event["content"], end="", flush=True)
                    elif event["event"] == "sources":
                        print(f"\n[Sources: {len(event['sources'])} chunks]\n")
                    elif event["event"] == "done":
                        print(f"\n[Done: {event['message_id']}]")
```

---

## Important Notes

1. **`ChatOpenAI` is created once at graph build time** (inside `_build_generate_node`), not per-request. The compiled graph is stateless and reusable — same as your current architecture.

2. **`get_stream_writer()` only works inside `astream()`**. When the graph runs via `ainvoke()` (non-streaming path), the writer calls are silently ignored — no errors, no side effects. So the same graph works for both streaming and non-streaming paths.

3. **`stream_mode` list ordering doesn't matter.** Events are yielded in the order they're produced by the graph execution, not by mode.

4. **The `metadata` dict** in `(chunk, metadata)` from `"messages"` mode contains `langgraph_node`, `langgraph_path`, and other trace info. We filter on `langgraph_node == "generate"` to ignore any internal LangChain scaffolding.

5. **No new dependencies needed.** You already have `langchain-openai>=0.3.0` and `langgraph>=0.2.0` in your `pyproject.toml`.

---

## Optional Enhancements (Not Required for MVP)

1. **Stream `initial_message` too** — Return `session_id` immediately from `POST /sessions`, then have the client open a stream for the initial message as a second call.

2. **Token batching** — If per-token SSE events are too chatty, buffer 3-5 tokens before yielding. Reduces network overhead with minimal latency impact.

3. **`sse-starlette` package** — Provides `EventSourceResponse` with keepalive pings and client disconnect detection. Small dependency, removes some SSE boilerplate:
   ```
   pip install sse-starlette
   ```

4. **Typing indicator event** — Emit a `{"event": "typing"}` event right before generation starts (after sources) so the client can show a typing animation immediately.
