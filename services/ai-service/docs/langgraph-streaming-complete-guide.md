# LangGraph Streaming — The Complete Guide

> Everything you need to know about streaming in LangGraph: every mode, every API, every pattern, every gotcha.

---

## Table of Contents

1. [Why Streaming Matters](#1-why-streaming-matters)
2. [The Two Streaming APIs](#2-the-two-streaming-apis)
3. [Stream Mode: `"values"`](#3-stream-mode-values)
4. [Stream Mode: `"updates"`](#4-stream-mode-updates)
5. [Stream Mode: `"messages"`](#5-stream-mode-messages)
6. [Stream Mode: `"custom"`](#6-stream-mode-custom)
7. [Stream Mode: `"debug"`](#7-stream-mode-debug)
8. [Combining Multiple Stream Modes](#8-combining-multiple-stream-modes)
9. [`astream_events()` — The Low-Level API](#9-astream_events--the-low-level-api)
10. [`get_stream_writer()` — Emitting Custom Events](#10-get_stream_writer--emitting-custom-events)
11. [`adispatch_custom_event()` — The Legacy Alternative](#11-adispatch_custom_event--the-legacy-alternative)
12. [LLM Integration and Why It Matters for Streaming](#12-llm-integration-and-why-it-matters-for-streaming)
13. [Streaming in Subgraphs](#13-streaming-in-subgraphs)
14. [Streaming with Checkpointers / Persistence](#14-streaming-with-checkpointers--persistence)
15. [FastAPI SSE Integration](#15-fastapi-sse-integration)
16. [Error Handling During Streams](#16-error-handling-during-streams)
17. [Performance and Production Considerations](#17-performance-and-production-considerations)
18. [Practical Patterns](#18-practical-patterns)
19. [Decision Matrix — Which API/Mode to Use](#19-decision-matrix--which-apimode-to-use)

---

## 1. Why Streaming Matters

When an LLM generates a response, it produces tokens one at a time. Without streaming, your app waits for the **entire** response (3-10+ seconds) before showing anything. With streaming, users see tokens as they're generated — the classic "typing" effect.

But LangGraph streaming goes beyond just LLM tokens. A graph has multiple nodes that execute sequentially or in parallel. Streaming lets you:

- Show LLM tokens as they generate (chat UIs)
- Emit progress updates from long-running nodes (status bars)
- Send intermediate results before the graph finishes (sources before the answer)
- Monitor graph execution for debugging (which node ran, what changed)
- Build responsive UIs that update at every step of a multi-step pipeline

---

## 2. The Two Streaming APIs

LangGraph provides two distinct streaming APIs on compiled graphs:

### `graph.astream()` — High-Level, Mode-Based

```python
async for chunk in graph.astream(inputs, stream_mode="messages"):
    ...
```

- You pick a **mode** (or multiple modes) that controls what you receive
- Each mode gives you a specific type of data (tokens, state updates, custom events, etc.)
- Clean and purpose-built — you get exactly what you asked for

### `graph.astream_events()` — Low-Level, Event-Based

```python
async for event in graph.astream_events(inputs, version="v2"):
    ...
```

- Emits **every lifecycle event** from every component (LLMs, tools, chains, nodes)
- More verbose — you filter through many event types to find what you need
- Useful when you need fine-grained visibility (e.g., "when did tool X start/end?")

**Rule of thumb:** Start with `astream()` + `stream_mode`. Only reach for `astream_events()` if you need lifecycle visibility that modes don't provide.

---

## 3. Stream Mode: `"values"`

**What it does:** Yields the **complete graph state** after every node finishes.

```python
graph = build_my_graph()

async for state in graph.astream(
    {"query": "What is React?"},
    stream_mode="values",
):
    print(state)
```

**Output (conceptual):**

```python
# After START (initial state)
{"query": "What is React?"}

# After RETRIEVE node
{"query": "What is React?", "context_text": "React is a...", "sources": [...]}

# After GENERATE node
{"query": "What is React?", "context_text": "React is a...", "sources": [...], "response": "React is a JavaScript library..."}
```

**When to use:**
- Debugging — see the full state at every step
- Simple graphs where you want to track overall progress
- When you need the complete picture, not just deltas

**Downside:** Bandwidth-heavy. The entire state dict is transmitted after every node, even if only one key changed. Not suitable for production chat streaming.

**Default behavior:** If you don't specify `stream_mode`, LangGraph defaults to `"values"`.

---

## 4. Stream Mode: `"updates"`

**What it does:** Yields only the **keys that changed** after each node, along with which node produced them.

```python
async for update in graph.astream(
    {"query": "What is React?"},
    stream_mode="updates",
):
    print(update)
```

**Output:**

```python
# After RETRIEVE node
{"retrieve": {"context_text": "React is a...", "sources": [...]}}

# After GENERATE node
{"generate": {"response": "React is a JavaScript library..."}}
```

**Structure:** `{node_name: {changed_keys}}`

**When to use:**
- Dashboards showing per-node progress
- When you need to know **what** changed and **who** changed it
- More efficient than `"values"` for large state objects

**Downside:** You don't see the full state — just the deltas. Good for monitoring, not great for reconstructing final state.

---

## 5. Stream Mode: `"messages"`

This is the most important mode for chat applications. It streams LLM tokens as they're generated.

### Basic Usage

```python
async for chunk, metadata in graph.astream(
    {"query": "What is React?"},
    stream_mode="messages",
):
    if chunk.content:
        print(chunk.content, end="", flush=True)
```

**Output:** Characters appear one at a time: `R`, `e`, `a`, `c`, `t`, ` `, `i`, `s`, ...

### What Gets Yielded

Each item is a tuple of `(AIMessageChunk, metadata_dict)`:

```python
# chunk: AIMessageChunk from langchain_core.messages
chunk.content      # "Hello"  (the token text)
chunk.id           # "run-abc123"  (run identifier)
chunk.type         # "AIMessageChunk"

# metadata: dict with execution context
metadata = {
    "langgraph_node": "generate",        # Which node produced this token
    "langgraph_step": 2,                  # Step number in graph execution
    "langgraph_triggers": ["retrieve"],   # What triggered this node
    "langgraph_path": ("__pregel_pull", "generate"),
    "ls_provider": "openai",             # LLM provider
    "ls_model_name": "gpt-4o-mini",      # Model name
    "ls_model_type": "chat",             # Model type
    "ls_stop": None,                     # Stop reason (populated on last chunk)
    "thread_id": "session-123",          # If using checkpointer
    "tags": [],                          # Any tags you set
}
```

### Filtering by Node Name

In a multi-node graph, you usually only want tokens from a specific node:

```python
async for chunk, metadata in graph.astream(inputs, stream_mode="messages"):
    # Only tokens from the "generate" node
    if metadata["langgraph_node"] == "generate" and chunk.content:
        print(chunk.content, end="", flush=True)
```

### Critical Requirement: LangChain ChatModel Wrappers

**`stream_mode="messages"` ONLY works with LangChain ChatModel wrappers** like `ChatOpenAI`, `ChatAnthropic`, etc. It does NOT work with raw SDK calls.

Why? LangGraph hooks into LangChain's callback system to intercept tokens. Raw SDK calls (like `openai.AsyncOpenAI().chat.completions.create()`) happen outside this system — LangGraph can't see them.

```python
# THIS WORKS — tokens appear in stream_mode="messages"
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4o-mini", streaming=True)

async def generate(state):
    response = await llm.ainvoke(messages)
    return {"response": response.content}

# THIS DOES NOT WORK — tokens are invisible to LangGraph
from openai import AsyncOpenAI
client = AsyncOpenAI()

async def generate(state):
    response = await client.chat.completions.create(model="gpt-4o-mini", messages=messages)
    return {"response": response.choices[0].message.content}
```

### The Redundant Final Message

After streaming all individual token chunks, `stream_mode="messages"` also yields a **final complete `AIMessage`** (not `AIMessageChunk`) with the full assembled content. This has a different `id` than the chunks.

To avoid showing duplicate content, check the type:

```python
from langchain_core.messages import AIMessageChunk

async for chunk, metadata in graph.astream(inputs, stream_mode="messages"):
    # Only process streaming chunks, not the final assembled message
    if isinstance(chunk, AIMessageChunk) and chunk.content:
        print(chunk.content, end="", flush=True)
```

### Tool Calls in Message Streams

When an LLM decides to call a tool (function calling), the chunks look different:

```python
async for chunk, metadata in graph.astream(inputs, stream_mode="messages"):
    if chunk.content:
        # Regular text token
        print(chunk.content, end="")
    elif chunk.tool_call_chunks:
        # Tool call being streamed
        for tc in chunk.tool_call_chunks:
            if tc.get("name"):
                print(f"\n[Calling tool: {tc['name']}]")
            # tc["args"] contains partial JSON string
            # You need to accumulate args across chunks
```

Tool call arguments are streamed incrementally. The first chunk has the tool `name` and `id`; subsequent chunks have these empty and only contain partial `args` JSON. You must accumulate across chunks to get the complete tool call.

---

## 6. Stream Mode: `"custom"`

**What it does:** Yields whatever data you emit from inside graph nodes using `get_stream_writer()`.

This is your escape hatch for streaming **anything** — progress updates, intermediate results, metadata, status messages, etc.

### Basic Usage

```python
from langgraph.config import get_stream_writer

async def my_node(state):
    writer = get_stream_writer()

    writer({"event": "status", "message": "Searching..."})
    # ... do some work ...
    writer({"event": "status", "message": "Found 5 results"})
    # ... do more work ...
    writer({"event": "result", "data": [1, 2, 3]})

    return {"output": "done"}
```

```python
# Consuming
async for event in graph.astream(inputs, stream_mode="custom"):
    print(event)
    # {"event": "status", "message": "Searching..."}
    # {"event": "status", "message": "Found 5 results"}
    # {"event": "result", "data": [1, 2, 3]}
```

**Payload:** Whatever you pass to `writer(...)`. No wrapping, no transformation. If you pass a dict, you get a dict. If you pass a string, you get a string.

**When to use:**
- Emitting RAG sources before LLM generation starts
- Progress bars for long-running operations
- Streaming from non-LangChain LLMs (raw Anthropic/OpenAI SDK)
- Any custom data that doesn't fit other modes

---

## 7. Stream Mode: `"debug"`

**What it does:** Emits detailed execution traces including step numbers, timestamps, node entry/exit, state snapshots.

**Requires a checkpointer.**

```python
from langgraph.checkpoint.memory import MemorySaver

graph = builder.compile(checkpointer=MemorySaver())
config = {"configurable": {"thread_id": "debug-1"}}

async for event in graph.astream(inputs, config=config, stream_mode="debug"):
    print(event)
```

**When to use:** Development and debugging only. Very verbose output. Not for production.

**Related modes that also require a checkpointer:**

| Mode | What It Does |
|---|---|
| `"checkpoints"` | Checkpoint events matching `get_state()` format |
| `"tasks"` | Task start/finish events with input/output/result |
| `"debug"` | Combines checkpoints + tasks + extra metadata |

---

## 8. Combining Multiple Stream Modes

You can pass a list of modes to `astream()`. This is how you get both LLM tokens AND custom events in a single stream.

### How It Works

```python
async for mode, payload in graph.astream(
    inputs,
    stream_mode=["messages", "custom"],
):
    if mode == "messages":
        chunk, metadata = payload
        if chunk.content:
            print(f"[TOKEN] {chunk.content}")
    elif mode == "custom":
        print(f"[CUSTOM] {payload}")
```

**Key change:** When you pass a **list** of modes, each yielded item becomes a `(mode_name, payload)` **tuple**. When you pass a **single** mode (string), you get the raw payload directly.

```python
# Single mode — raw payload
async for chunk, metadata in graph.astream(inputs, stream_mode="messages"):
    ...

# Multiple modes — (mode, payload) tuples
async for mode, payload in graph.astream(inputs, stream_mode=["messages", "custom"]):
    ...
```

### Practical Example: RAG + Streaming

```python
# In retrieve node:
writer = get_stream_writer()
writer({"event": "sources", "sources": [...]})   # Emitted via "custom" mode

# In generate node:
llm = ChatOpenAI(streaming=True)
response = await llm.ainvoke(messages)            # Tokens emitted via "messages" mode

# Consumer:
async for mode, payload in graph.astream(state, stream_mode=["messages", "custom"]):
    if mode == "custom":
        # Sources arrive FIRST (retrieve runs before generate)
        yield f"data: {json.dumps(payload)}\n\n"
    elif mode == "messages":
        chunk, metadata = payload
        if metadata["langgraph_node"] == "generate" and chunk.content:
            yield f"data: {json.dumps({'event': 'token', 'content': chunk.content})}\n\n"
```

### Event Ordering

Events are yielded in the order they're **produced by graph execution**, not grouped by mode. So if your graph runs RETRIEVE then GENERATE:

1. Custom events from RETRIEVE (sources)
2. Message chunks from GENERATE (tokens)

This is exactly the order you want for a chat UI — show sources first, then stream the answer.

### You Can Combine Any Modes

```python
# Everything at once
async for mode, payload in graph.astream(
    inputs,
    stream_mode=["values", "updates", "messages", "custom"],
):
    if mode == "values":
        print(f"[FULL STATE] {payload}")
    elif mode == "updates":
        print(f"[DELTA] {payload}")
    elif mode == "messages":
        chunk, meta = payload
        print(f"[TOKEN] {chunk.content}")
    elif mode == "custom":
        print(f"[CUSTOM] {payload}")
```

---

## 9. `astream_events()` — The Low-Level API

### When to Use It

Use `astream_events()` when you need **lifecycle visibility** that stream modes don't provide:

- Know exactly when a tool starts and finishes executing
- Track when a retriever query begins and ends
- Monitor prompt template formatting
- Filter events by component name, type, or tags

### Basic Usage

```python
async for event in graph.astream_events(inputs, version="v2"):
    print(event["event"], event["name"])
```

**Always use `version="v2"`** — v1 is deprecated and doesn't support custom events.

### Event Structure

Every event is a dict:

```python
{
    "event": "on_chat_model_stream",       # Event type
    "name": "ChatOpenAI",                   # Component name
    "run_id": "uuid-string",               # Unique run ID
    "parent_ids": ["parent-uuid"],         # Parent chain (v2 only)
    "tags": ["generation"],                # Tags for filtering
    "metadata": {
        "langgraph_node": "generate",
        "langgraph_step": 2,
        "ls_provider": "openai",
        "ls_model_name": "gpt-4o-mini",
    },
    "data": {                              # Event-specific payload
        "chunk": AIMessageChunk(content="Hello"),
    },
}
```

### Complete Event Types

| Event | When It Fires | `data` Fields |
|---|---|---|
| `on_chain_start` | Node/chain begins | `{"input": ...}` |
| `on_chain_stream` | Node/chain yields | `{"chunk": ...}` |
| `on_chain_end` | Node/chain finishes | `{"input": ..., "output": ...}` |
| `on_chat_model_start` | LLM call begins | `{"messages": [[...]]}` |
| `on_chat_model_stream` | Each LLM token | `{"chunk": AIMessageChunk}` |
| `on_chat_model_end` | LLM call finishes | `{"output": ChatResult}` |
| `on_tool_start` | Tool execution begins | `{"input": {params}}` |
| `on_tool_end` | Tool execution finishes | `{"output": result}` |
| `on_retriever_start` | Retriever query begins | `{"input": {"query": "..."}}` |
| `on_retriever_end` | Retriever query finishes | `{"documents": [...]}` |
| `on_custom_event` | `adispatch_custom_event()` called | `{"data": your_payload}` |

### Filtering Events

Instead of processing every event and checking `event["event"]`, you can filter upfront:

```python
# Only LLM streaming tokens
async for event in graph.astream_events(
    inputs,
    version="v2",
    include_types=["chat_model"],
):
    if event["event"] == "on_chat_model_stream":
        token = event["data"]["chunk"].content
        print(token, end="")
```

```python
# Only events from a specifically named component
async for event in graph.astream_events(
    inputs,
    version="v2",
    include_names=["ChatOpenAI"],
):
    ...
```

```python
# By tags
async for event in graph.astream_events(
    inputs,
    version="v2",
    include_tags=["generation"],
    exclude_tags=["internal"],
):
    ...
```

### `astream_events` vs `astream` with `stream_mode`

| | `astream` + `stream_mode` | `astream_events` |
|---|---|---|
| **Verbosity** | Focused — you get what you ask for | Noisy — every lifecycle event |
| **Token streaming** | `stream_mode="messages"` | Filter for `on_chat_model_stream` |
| **Custom events** | `stream_mode="custom"` + `get_stream_writer()` | `on_custom_event` + `adispatch_custom_event()` |
| **State updates** | `stream_mode="updates"` | Parse from `on_chain_end` |
| **Tool lifecycle** | Not available | `on_tool_start` / `on_tool_end` |
| **Filtering** | By mode selection | By name/type/tags |
| **Recommended for** | Production streaming | Debugging, complex monitoring |

---

## 10. `get_stream_writer()` — Emitting Custom Events

### Import

```python
from langgraph.config import get_stream_writer
```

### How It Works

`get_stream_writer()` uses Python's `contextvars` to retrieve a writer function that was set up by `astream()`. When you call `writer(data)`, the data is immediately yielded to the consumer through `stream_mode="custom"`.

### Full Example

```python
from langgraph.config import get_stream_writer

async def retrieve_node(state):
    writer = get_stream_writer()

    # Emit a status update
    writer({"event": "status", "message": "Embedding your question..."})

    embedding = await embed(state["query"])

    writer({"event": "status", "message": "Searching course materials..."})

    results = await search(embedding)

    # Emit the sources
    writer({
        "event": "sources",
        "sources": [{"title": r["title"], "score": r["score"]} for r in results],
    })

    return {"context": format_context(results), "sources": results}
```

### Where It Works

- Sync graph nodes
- Async graph nodes (Python 3.11+)
- Inside tools called from nodes
- `@task` decorated functions
- `@entrypoint` decorated workflows

### Python Version Caveat

**Python >= 3.11:** `get_stream_writer()` works everywhere (sync, async, nested calls).

**Python < 3.11:** `get_stream_writer()` does NOT work in async code due to context variable propagation limitations. Use the **injected parameter pattern** instead:

```python
from langgraph.types import StreamWriter

# Python < 3.11: add writer as a parameter, LangGraph injects it automatically
async def my_node(state: MyState, writer: StreamWriter) -> dict:
    writer({"event": "progress", "percent": 50})
    return {"result": "done"}
```

### Behavior Outside `astream()`

When `get_stream_writer()` is called outside an active streaming context (e.g., during `ainvoke()`), it returns a **silent no-op function**. Calls to `writer(...)` do nothing — no errors, no side effects.

This means the **same graph works for both streaming and non-streaming** without any conditional logic:

```python
async def my_node(state):
    writer = get_stream_writer()
    writer({"event": "status", "message": "Working..."})  # No-op during ainvoke()
    # ... do work ...
    return {"result": "done"}

# Streaming path — writer emits events
async for mode, payload in graph.astream(inputs, stream_mode=["custom"]):
    print(payload)  # {"event": "status", "message": "Working..."}

# Non-streaming path — writer is silent
result = await graph.ainvoke(inputs)  # writer calls are ignored
```

---

## 11. `adispatch_custom_event()` — The Legacy Alternative

### Import

```python
from langchain_core.callbacks import adispatch_custom_event
```

### How It Differs from `get_stream_writer()`

| | `get_stream_writer()` | `adispatch_custom_event()` |
|---|---|---|
| **Origin** | LangGraph-native | LangChain Core |
| **Consumed via** | `stream_mode="custom"` | `astream_events()` as `on_custom_event` |
| **Works in** | Graph nodes, tasks, entrypoints | Any LangChain Runnable context |
| **Sync support** | Yes | No (async only) |
| **Recommended** | Yes (LangGraph >= 0.2) | For non-graph LangChain code |

### Usage

```python
from langchain_core.callbacks import adispatch_custom_event

async def my_node(state):
    await adispatch_custom_event(
        name="my_event",
        data={"key": "value"},
        # config=config,  # Required on Python < 3.11
    )
    return {"result": "done"}
```

Consuming (via `astream_events`, NOT `stream_mode`):

```python
async for event in graph.astream_events(inputs, version="v2"):
    if event["event"] == "on_custom_event" and event["name"] == "my_event":
        print(event["data"])  # {"key": "value"}
```

### When to Use

- When working in pure LangChain (non-graph) contexts
- When you specifically need events in `astream_events()` callbacks
- For `get_stream_writer()` — use that instead in LangGraph code

### Known Issues

- Requires explicit `config` parameter on Python < 3.11
- Has documented reliability issues inside LangGraph nodes (async context propagation)
- `get_stream_writer()` is more reliable and the recommended approach for LangGraph

---

## 12. LLM Integration and Why It Matters for Streaming

This section explains the most common confusion point in LangGraph streaming.

### The Core Rule

**`stream_mode="messages"` requires LangChain ChatModel wrappers.** Raw SDK calls are invisible to LangGraph's streaming system.

### Why?

LangGraph's token streaming works through LangChain's **callback system**. When `ChatOpenAI` generates a token, it fires a callback that LangGraph intercepts and routes to the stream consumer. Raw SDK calls bypass this entirely.

### Option A: Use LangChain Wrappers (Recommended)

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="gpt-4o-mini",
    api_key="sk-...",
    temperature=0.7,
    max_tokens=1024,
    streaming=True,  # Enable streaming
)

async def generate(state):
    messages = [SystemMessage(content="..."), HumanMessage(content=state["query"])]
    response = await llm.ainvoke(messages)
    return {"response": response.content}
```

With this, `stream_mode="messages"` works automatically. No extra code needed.

Available wrappers:

| Provider | Package | Class |
|---|---|---|
| OpenAI | `langchain-openai` | `ChatOpenAI` |
| Anthropic | `langchain-anthropic` | `ChatAnthropic` |
| Google | `langchain-google-genai` | `ChatGoogleGenerativeAI` |
| AWS Bedrock | `langchain-aws` | `ChatBedrock` |

### Option B: Raw SDK + `get_stream_writer()` (Alternative)

If you don't want to use LangChain wrappers (or your LLM doesn't have one), use the raw SDK with `get_stream_writer()`:

```python
from openai import AsyncOpenAI
from langgraph.config import get_stream_writer

async def generate(state):
    writer = get_stream_writer()
    client = AsyncOpenAI()

    full_response = ""
    stream = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": "..."}, {"role": "user", "content": state["query"]}],
        stream=True,
    )

    async for chunk in stream:
        token = chunk.choices[0].delta.content or ""
        if token:
            writer({"event": "token", "content": token})
            full_response += token

    return {"response": full_response}
```

Consume with `stream_mode="custom"` instead of `"messages"`:

```python
async for event in graph.astream(inputs, stream_mode="custom"):
    if event.get("event") == "token":
        print(event["content"], end="")
```

**Trade-off:** You lose `stream_mode="messages"` and its rich metadata (`ls_provider`, `ls_model_name`, etc.). But you get full control over the streaming loop and can use any LLM SDK.

### This Works for Any Provider

```python
# Anthropic raw SDK
import anthropic
from langgraph.config import get_stream_writer

async def generate_with_claude(state):
    writer = get_stream_writer()
    client = anthropic.AsyncAnthropic()

    full_text = ""
    async with client.messages.stream(
        model="claude-sonnet-4-20250514",
        messages=[{"role": "user", "content": state["query"]}],
        max_tokens=1024,
    ) as stream:
        async for text in stream.text_stream:
            writer({"event": "token", "content": text})
            full_text += text

    return {"response": full_text}
```

---

## 13. Streaming in Subgraphs

When you have nested graphs (a graph that calls another graph), streaming behavior propagates through the hierarchy.

### Enabling Subgraph Streaming

```python
async for chunk in graph.astream(
    inputs,
    stream_mode="updates",
    subgraphs=True,  # <-- Enable subgraph event visibility
):
    print(chunk)
```

Without `subgraphs=True`, you only see events from the **root graph**. Subgraph execution appears as a single atomic step.

### Namespace Identification

With `subgraphs=True`, events include namespace information telling you which (sub)graph produced them:

```python
# V2 format (recommended)
async for chunk in graph.astream(inputs, stream_mode="updates", subgraphs=True, version="v2"):
    ns = chunk["ns"]       # Namespace tuple
    data = chunk["data"]

    if ns == ():
        print(f"[Root graph] {data}")
    else:
        print(f"[Subgraph: {ns}] {data}")
```

Namespace format:
- Root graph: `()` (empty tuple)
- One level deep: `("parent_node_name:<task_id>",)`
- Two levels deep: `("parent_node:<task_id>", "child_node:<task_id>")`

### Known Limitations

- Combining multiple `stream_mode` values with `subgraphs=True` can have output format issues
- `stream_mode="messages"` with `subgraphs=False` may miss tokens from subgraph LLM calls in some configurations

---

## 14. Streaming with Checkpointers / Persistence

Checkpointers save graph state at every step. This enables multi-turn conversations, stream resumption, and state inspection.

### Setup

```python
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
graph = builder.compile(checkpointer=checkpointer)

# thread_id is REQUIRED when using a checkpointer
config = {"configurable": {"thread_id": "session-123"}}
```

### Multi-Turn Conversations

```python
# First message
async for chunk in graph.astream(
    {"query": "What is React?"},
    config=config,
    stream_mode="messages",
):
    ...

# Second message — same thread_id, graph has memory of first message
async for chunk in graph.astream(
    {"query": "How does JSX work?"},
    config=config,
    stream_mode="messages",
):
    ...
```

### Available Checkpointers

| Checkpointer | Package | Use Case |
|---|---|---|
| `MemorySaver` | `langgraph` (built-in) | Development/testing (lost on restart) |
| `SqliteSaver` | `langgraph-checkpoint-sqlite` | Local persistence |
| `PostgresSaver` | `langgraph-checkpoint-postgres` | Production |
| `DynamoDBSaver` | `langgraph-checkpoint-aws` | AWS production |

### Human-in-the-Loop with Streaming

Checkpointers enable `interrupt()` — pausing graph execution to wait for human input:

```python
from langgraph.types import interrupt, Command

async def review_node(state):
    decision = interrupt({
        "question": "Approve this action?",
        "action": state["proposed_action"],
    })
    return {"approved": decision == "yes"}

# Stream until interrupt
config = {"configurable": {"thread_id": "thread-1"}}
async for chunk in graph.astream(inputs, config=config, stream_mode="values"):
    print(chunk)
# Graph pauses at interrupt()

# Resume with user's decision
async for chunk in graph.astream(
    Command(resume="yes"),
    config=config,
    stream_mode="values",
):
    print(chunk)  # Continues from interrupt point
```

---

## 15. FastAPI SSE Integration

### What is SSE?

Server-Sent Events (SSE) is a standard for streaming data from server to client over HTTP. The client sends a normal request; the server responds with a stream of `data:` lines.

SSE format:
```
data: {"event": "token", "content": "Hello"}\n\n
data: {"event": "token", "content": " world"}\n\n
data: {"event": "done"}\n\n
```

Each event is a `data:` line followed by two newlines (`\n\n`).

### Pattern 1: FastAPI `StreamingResponse` (Simple)

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import json

app = FastAPI()

@app.post("/chat/stream")
async def stream_chat(request: ChatRequest):
    async def event_generator():
        try:
            async for mode, payload in graph.astream(
                {"query": request.message},
                stream_mode=["messages", "custom"],
            ):
                if mode == "custom":
                    yield f"data: {json.dumps(payload)}\n\n"
                elif mode == "messages":
                    chunk, metadata = payload
                    if metadata.get("langgraph_node") == "generate" and chunk.content:
                        yield f"data: {json.dumps({'event': 'token', 'content': chunk.content})}\n\n"

            yield f"data: {json.dumps({'event': 'done'})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

### Pattern 2: `sse-starlette` (Production)

The `sse-starlette` package adds keepalive pings, client disconnect detection, and send timeouts:

```bash
pip install sse-starlette
```

```python
from sse_starlette.sse import EventSourceResponse
import json

@app.post("/chat/stream")
async def stream_chat(request: ChatRequest):
    async def event_generator():
        async for mode, payload in graph.astream(
            {"query": request.message},
            stream_mode=["messages", "custom"],
        ):
            if mode == "custom":
                yield json.dumps(payload)
            elif mode == "messages":
                chunk, metadata = payload
                if metadata.get("langgraph_node") == "generate" and chunk.content:
                    yield json.dumps({"event": "token", "content": chunk.content})

        yield json.dumps({"event": "done"})

    return EventSourceResponse(
        event_generator(),
        ping=15,           # Keepalive ping every 15 seconds
        send_timeout=30,   # Timeout for frozen clients
    )
```

Note: `EventSourceResponse` handles the `data:` prefix and `\n\n` suffix automatically. You just yield the payload.

### `EventSourceResponse` Features

| Feature | Description |
|---|---|
| **Keepalive pings** | Sends `: ping` comments at configurable intervals to keep connection alive |
| **Send timeout** | Detects frozen clients and cleans up |
| **Disconnect detection** | Monitors ASGI receive channel for `http.disconnect` |
| **Auto headers** | Sets `Cache-Control: no-store`, `Connection: keep-alive`, `X-Accel-Buffering: no` |

### Proxy Configuration

SSE streams can be broken by proxy buffering. Key headers and configs:

| Proxy | Fix |
|---|---|
| **Nginx** | `X-Accel-Buffering: no` header (set by both patterns above) |
| **Cloudflare** | Disable response buffering or use `chunked` transfer encoding |
| **AWS ALB** | Increase idle timeout beyond expected stream duration (default 60s) |
| **General** | Ensure chunked transfer encoding passes through without buffering |

### CORS for SSE

SSE is standard HTTP — CORS applies normally:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 16. Error Handling During Streams

### What Happens When a Node Throws

If a node raises an exception during `astream()`:

1. The exception propagates up through the async iterator
2. No more events are yielded
3. **With checkpointer:** State is saved up to the last successful node. You can inspect state and potentially resume.
4. **Without checkpointer:** All state is lost.

### Server-Side Error Handling

Wrap your generator in try/except to send an error event before the stream closes:

```python
async def event_generator():
    try:
        async for mode, payload in graph.astream(state, stream_mode=["messages", "custom"]):
            if mode == "messages":
                chunk, metadata = payload
                if chunk.content:
                    yield f"data: {json.dumps({'event': 'token', 'content': chunk.content})}\n\n"
            elif mode == "custom":
                yield f"data: {json.dumps(payload)}\n\n"
    except Exception as e:
        # Send error event so the client knows what happened
        yield f"data: {json.dumps({'event': 'error', 'message': 'Generation failed. Please try again.'})}\n\n"
    finally:
        # Always send done event so the client knows the stream ended
        yield f"data: {json.dumps({'event': 'done'})}\n\n"
```

### Client-Side Error Handling

```javascript
// Handle HTTP-level errors (before stream starts)
const response = await fetch('/chat/stream', { method: 'POST', body: ... });
if (!response.ok) {
  const error = await response.json();
  showError(error.detail);
  return;
}

// Handle stream-level errors (during streaming)
const reader = response.body.getReader();
while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  // ... parse SSE lines ...
  const data = JSON.parse(line.slice(6));
  if (data.event === 'error') {
    showError(data.message);
    break;
  }
}
```

### Pre-Stream Validation

Validate everything you can **before** opening the stream. Once the stream starts, you can't send HTTP error codes:

```python
@app.post("/chat/stream")
async def stream_chat(session_id: str, request: ChatRequest):
    # Validate BEFORE opening stream
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["owner"] != request.user_id:
        raise HTTPException(status_code=403, detail="Not your session")

    # Now open the stream (errors from here are sent as SSE events)
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

---

## 17. Performance and Production Considerations

### Token Batching

Per-token SSE events can be chatty (hundreds of tiny HTTP chunks). Options:

**Server-side batching:**
```python
import asyncio

async def event_generator():
    buffer = []
    last_flush = asyncio.get_event_loop().time()

    async for mode, payload in graph.astream(state, stream_mode=["messages", "custom"]):
        if mode == "custom":
            # Flush any buffered tokens first
            if buffer:
                yield f"data: {json.dumps({'event': 'token', 'content': ''.join(buffer)})}\n\n"
                buffer.clear()
            yield f"data: {json.dumps(payload)}\n\n"
        elif mode == "messages":
            chunk, metadata = payload
            if chunk.content:
                buffer.append(chunk.content)
                # Flush every 5 tokens or every 50ms
                now = asyncio.get_event_loop().time()
                if len(buffer) >= 5 or (now - last_flush) > 0.05:
                    yield f"data: {json.dumps({'event': 'token', 'content': ''.join(buffer)})}\n\n"
                    buffer.clear()
                    last_flush = now

    # Flush remaining
    if buffer:
        yield f"data: {json.dumps({'event': 'token', 'content': ''.join(buffer)})}\n\n"
```

**Client-side batching (simpler):** Send every token, but batch DOM updates:
```javascript
let pendingText = '';
let rafId = null;

function appendToken(token) {
  pendingText += token;
  if (!rafId) {
    rafId = requestAnimationFrame(() => {
      chatBubble.textContent += pendingText;
      pendingText = '';
      rafId = null;
    });
  }
}
```

### Backpressure

Python async generators provide natural backpressure. If the HTTP client reads slowly, `yield` blocks, which pauses the LLM token consumption. The system self-regulates.

### Connection Keepalive

Idle SSE connections get dropped by proxies and load balancers. Solutions:

- **`sse-starlette`:** Built-in `ping` parameter (default 15 seconds)
- **Manual with `StreamingResponse`:** Periodically yield SSE comments:
  ```python
  yield ": keepalive\n\n"  # SSE comment, ignored by clients
  ```

### Timeouts

| Setting | Where | Default | Recommendation |
|---|---|---|---|
| `send_timeout` | `EventSourceResponse` | None | Set to 30s to catch frozen clients |
| `--timeout-keep-alive` | Uvicorn | 5s | Increase for long SSE streams |
| Idle timeout | Load balancer (ALB, nginx) | 60s | Set higher than max expected stream duration |

### Concurrent Streams

Each SSE connection holds an open HTTP connection. For high-concurrency:

- Use Uvicorn with `--workers` > 1 for multi-process
- Monitor open connection count
- Consider connection limits per user
- Use async everywhere (which you already do with FastAPI + async LangGraph)

---

## 18. Practical Patterns

### Pattern 1: RAG + Streaming (Your Tutor Use Case)

```
RETRIEVE (emit sources via writer) → GENERATE (stream tokens via ChatOpenAI)
```

```python
from langgraph.config import get_stream_writer
from langchain_openai import ChatOpenAI

async def retrieve(state):
    writer = get_stream_writer()
    # ... embed query, search vector store ...
    writer({"event": "sources", "sources": sources})
    return {"context": context, "sources": sources}

async def generate(state):
    llm = ChatOpenAI(model="gpt-4o-mini", streaming=True)
    response = await llm.ainvoke(messages)
    return {"response": response.content}

# Consume with stream_mode=["messages", "custom"]
```

### Pattern 2: Multi-Step Pipeline with Progress

```
ANALYZE → PLAN → EXECUTE → SUMMARIZE
```

```python
async def analyze(state):
    writer = get_stream_writer()
    writer({"event": "progress", "step": "analyze", "status": "started"})
    # ... work ...
    writer({"event": "progress", "step": "analyze", "status": "done", "result": "Found 3 issues"})
    return {"analysis": result}

async def plan(state):
    writer = get_stream_writer()
    writer({"event": "progress", "step": "plan", "status": "started"})
    # ... work ...
    writer({"event": "progress", "step": "plan", "status": "done"})
    return {"plan": plan}

# Each step emits its own progress events
# Client shows a step-by-step progress indicator
```

### Pattern 3: Conditional Routing with Streaming

Conditional edges don't affect streaming. Events flow from whichever path the graph takes:

```python
def route(state):
    if state["needs_search"]:
        return "search_node"
    return "direct_answer_node"

graph.add_conditional_edges("classify", route)

# Streaming works identically regardless of which branch runs
async for mode, payload in graph.astream(inputs, stream_mode=["messages", "custom"]):
    ...
```

### Pattern 4: Parallel Execution (Map-Reduce) with Streaming

LangGraph's `Send()` API enables fan-out. Streaming works across all parallel branches:

```python
from langgraph.types import Send

def fan_out(state):
    return [Send("process_item", {"item": item}) for item in state["items"]]

graph.add_conditional_edges("orchestrator", fan_out)

# Events from all parallel branches arrive as they're produced
async for mode, payload in graph.astream(
    {"items": ["a", "b", "c"]},
    stream_mode=["updates", "custom"],
):
    # You'll see updates from all 3 parallel "process_item" invocations
    print(mode, payload)
```

### Pattern 5: Non-LangChain LLM Streaming

Use `get_stream_writer()` with any SDK:

```python
# Works with Anthropic, Google, Cohere, local models, anything
from langgraph.config import get_stream_writer

async def generate(state):
    writer = get_stream_writer()
    # Use whatever SDK you want
    async for token in my_custom_llm.stream(state["query"]):
        writer({"event": "token", "content": token})
    return {"response": full_text}

# Consume with stream_mode="custom"
```

---

## 19. Decision Matrix — Which API/Mode to Use

### Quick Reference

| I want to... | Use |
|---|---|
| Stream LLM tokens to a chat UI | `stream_mode="messages"` + `ChatOpenAI(streaming=True)` |
| Emit custom events (sources, progress) | `stream_mode="custom"` + `get_stream_writer()` |
| Both tokens AND custom events | `stream_mode=["messages", "custom"]` |
| See full state after each node | `stream_mode="values"` |
| See what each node changed | `stream_mode="updates"` |
| Debug graph execution | `stream_mode="debug"` (requires checkpointer) |
| Track tool start/end lifecycle | `astream_events(version="v2")` |
| Stream from non-LangChain LLMs | `stream_mode="custom"` + `get_stream_writer()` + raw SDK |
| Multi-turn chat memory | Add checkpointer + `thread_id` in config |
| Pause for human approval | `interrupt()` + checkpointer |
| See subgraph events | `subgraphs=True` parameter |
| Production FastAPI endpoint | `sse-starlette` `EventSourceResponse` |
| Simple FastAPI endpoint | `StreamingResponse` with `text/event-stream` |

### The 80% Path

For most chat applications, you need exactly this:

```python
# In your graph nodes:
from langgraph.config import get_stream_writer
from langchain_openai import ChatOpenAI

# Retrieve node — emit sources
writer = get_stream_writer()
writer({"event": "sources", "sources": [...]})

# Generate node — use ChatOpenAI for auto token streaming
llm = ChatOpenAI(model="gpt-4o-mini", streaming=True)
response = await llm.ainvoke(messages)

# In your FastAPI endpoint:
async for mode, payload in graph.astream(state, stream_mode=["messages", "custom"]):
    if mode == "custom":
        yield f"data: {json.dumps(payload)}\n\n"
    elif mode == "messages":
        chunk, metadata = payload
        if metadata["langgraph_node"] == "generate" and chunk.content:
            yield f"data: {json.dumps({'event': 'token', 'content': chunk.content})}\n\n"
```

That's it. Three concepts: `ChatOpenAI` for tokens, `get_stream_writer()` for custom events, `stream_mode=["messages", "custom"]` to receive both.
