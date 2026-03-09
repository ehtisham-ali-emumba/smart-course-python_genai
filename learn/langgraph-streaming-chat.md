# LangGraph Streaming Chat — Quick Guide

## 1. Setup

```bash
pip install langgraph langchain-openai
```

## 2. Define State

```python
from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages

class ChatState(TypedDict):
    messages: Annotated[list, add_messages]  # auto-appends new messages
```

> `add_messages` is a **reducer** — it merges new messages into the list instead of replacing it.

## 3. Minimal Streaming Chat Graph

```python
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o-mini", streaming=True)

async def chatbot(state: ChatState):
    response = await llm.ainvoke(state["messages"])
    return {"messages": [response]}

graph = StateGraph(ChatState)
graph.add_node("chatbot", chatbot)
graph.add_edge(START, "chatbot")
graph.add_edge("chatbot", END)
app = graph.compile()
```

## 4. Three Ways to Stream

### A) `astream` — Stream Graph Events (node-level)

Each node's full output arrives as one chunk.

```python
async for event in app.astream({"messages": [("user", "What is AI?")]}):
    for node_name, output in event.items():
        print(f"[{node_name}]: {output['messages'][-1].content}")
```

### B) `astream_events` — Stream LLM Tokens (token-level)

Get individual tokens as the LLM generates them.

```python
async for event in app.astream_events(
    {"messages": [("user", "What is AI?")]},
    version="v2",
):
    if event["event"] == "on_chat_model_stream":
        token = event["data"]["chunk"].content
        if token:
            print(token, end="", flush=True)
```

### C) `astream` with `stream_mode="messages"` — Simplest Token Streaming

```python
async for msg, metadata in app.astream(
    {"messages": [("user", "What is AI?")]},
    stream_mode="messages",
):
    if msg.content:
        print(msg.content, end="", flush=True)
```

## 5. FastAPI SSE Endpoint

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app_api = FastAPI()

@app_api.post("/chat")
async def chat(user_message: str):
    async def generate():
        async for event in app.astream_events(
            {"messages": [("user", user_message)]},
            version="v2",
        ):
            if event["event"] == "on_chat_model_stream":
                token = event["data"]["chunk"].content
                if token:
                    yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

## 6. Multi-Node Graph with Streaming

```python
from langchain_core.messages import SystemMessage

async def classifier(state: ChatState):
    """Classifies the query topic."""
    response = await llm.ainvoke([
        SystemMessage(content="Classify the topic in one word."),
        *state["messages"],
    ])
    return {"messages": [response]}

async def responder(state: ChatState):
    """Generates the final answer."""
    response = await llm.ainvoke([
        SystemMessage(content="Answer helpfully based on the conversation."),
        *state["messages"],
    ])
    return {"messages": [response]}

graph = StateGraph(ChatState)
graph.add_node("classifier", classifier)
graph.add_node("responder", responder)
graph.add_edge(START, "classifier")
graph.add_edge("classifier", "responder")
graph.add_edge("responder", END)
app = graph.compile()

# Stream tokens — only from the "responder" node
async for event in app.astream_events(
    {"messages": [("user", "Explain gravity")]},
    version="v2",
):
    if (
        event["event"] == "on_chat_model_stream"
        and event["metadata"].get("langgraph_node") == "responder"
    ):
        print(event["data"]["chunk"].content, end="", flush=True)
```

## Quick Reference

| Method | Granularity | Use Case |
|--------|-------------|----------|
| `astream()` | Per node | See each node's complete output |
| `astream(stream_mode="messages")` | Per token | Simple token streaming |
| `astream_events(version="v2")` | Per token + metadata | Filter by node, full control |

## Key Takeaways

- Set `streaming=True` on the LLM for token-level streaming
- Use `astream_events` when you need to filter tokens by node
- Use `stream_mode="messages"` for the simplest token streaming
- `add_messages` reducer handles message list management automatically
