# Agentic AI - Learn & Implement Plan

**Context:** SmartCourse platform (FastAPI, microservices)  
**Goal:** Build an AI Tutor Agent that reasons, uses tools, and acts autonomously

---

## Phase 0: Core Prerequisites (1-2 days)

Before touching agents, nail these fundamentals.

### LLM API Basics

| What | Why |
|------|-----|
| Chat Completions API (messages array, roles) | Every agent is built on top of this |
| System prompts | Controls agent persona and behavior |
| Temperature & token limits | Controls determinism vs creativity |
| Streaming responses | Real-time UX for your AI tutor |

**Do this:**
```python
from openai import OpenAI
client = OpenAI()

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "You are a helpful tutor."},
        {"role": "user", "content": "Explain recursion in 2 sentences."},
    ],
)
print(response.choices[0].message.content)
```

### Function Calling (Tool Use)

This is the **single most important concept** for agents. The LLM doesn't execute code — it outputs a structured JSON saying "call this function with these args." Your code executes it and feeds the result back.

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_student_progress",
            "description": "Get student's course progress",
            "parameters": {
                "type": "object",
                "properties": {
                    "student_id": {"type": "integer"},
                    "course_id": {"type": "integer"},
                },
                "required": ["student_id", "course_id"],
            },
        },
    }
]

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "How am I doing in course 101?"}],
    tools=tools,
    tool_choice="auto",
)
# LLM returns: call get_student_progress(student_id=1, course_id=101)
# YOU execute the function, then send result back as a tool message
```

### Resources - Prerequisites

| Resource | Type | Time |
|----------|------|------|
| [OpenAI Chat Completions Guide](https://platform.openai.com/docs/guides/text-generation) | Docs | 30 min |
| [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling) | Docs | 45 min |
| [Function Calling Tutorial - Sam Witteveen](https://www.youtube.com/watch?v=0lOSvOoF2to) | Video | 25 min |

---

## Phase 1: Agent Fundamentals (2-3 days)

### What is an Agent?

```
Agent = LLM + Tools + Loop + Memory

Traditional LLM:  User → LLM → Response (one-shot)
Agent:            User → LLM → [Think → Act → Observe]* → Response (loop)
```

The key difference: **the LLM decides what to do next**, not your code.

### The ReAct Pattern (Reason + Act)

Every agent framework implements some version of this:

```
1. THOUGHT:  "The user wants their progress. I should call get_progress."
2. ACTION:   get_progress(student_id=42, course_id=101)
3. OBSERVATION: {completion: 65%, modules_done: [1,2,3]}
4. THOUGHT:  "They're 65% done. Let me check what's next."
5. ACTION:   get_next_module(course_id=101, after=3)
6. OBSERVATION: {module: 4, title: "Advanced Patterns"}
7. THOUGHT:  "I have enough info to respond."
8. FINAL ANSWER: "You're 65% through course 101! Next up: Module 4 - Advanced Patterns."
```

### Agent Architectures

| Architecture | When to Use | Complexity |
|-------------|-------------|------------|
| **Single Agent** | One agent with multiple tools | Low |
| **Router Agent** | Routes to specialized sub-agents | Medium |
| **Supervisor + Workers** | Boss delegates to worker agents | High |
| **Swarm / Collaborative** | Agents negotiate and collaborate | Very High |

**Start with single agent. Move to multi-agent only when needed.**

### Resources - Fundamentals

| Resource | Type | Time |
|----------|------|------|
| [LLM Powered Autonomous Agents - Lilian Weng](https://lilianweng.github.io/posts/2023-06-23-agent/) | Blog | 1 hr |
| [What are AI Agents? - IBM](https://www.youtube.com/watch?v=F8NKVhkZZWI) | Video | 10 min |
| [Andrew Ng: What's next for AI agentic workflows](https://www.youtube.com/watch?v=sal78ACtGTc) | Video | 30 min |
| [AI Agents Explained - Anthropic](https://www.anthropic.com/engineering/building-effective-agents) | Blog | 45 min |
| [ReAct Paper (simplified)](https://arxiv.org/abs/2210.03629) | Paper | 30 min |

---

## Phase 2: Agent Frameworks (3-4 days)

### Framework Landscape

| Framework | Best For | Approach |
|-----------|---------|----------|
| **LangGraph** | Complex stateful agents with cycles | Graph-based state machine |
| **OpenAI Agents SDK** | Simple agents using OpenAI models | Minimal, production-ready |
| **CrewAI** | Multi-agent role-playing teams | High-level, opinionated |
| **Autogen** | Multi-agent conversations | Conversational agents |
| **LlamaIndex** | Data/RAG-heavy agents | Data framework first |

**Recommendation:** Learn **LangGraph** (most flexible) + **OpenAI Agents SDK** (simplest for production).

---

### 2A: LangGraph (Primary Framework)

LangGraph = state machine for agents. Nodes are functions, edges define flow, state persists across steps.

#### Core Concepts

| Concept | What It Is |
|---------|-----------|
| **StateGraph** | The agent's workflow as a directed graph |
| **State** | Dict-like object that persists across nodes (messages, context, etc.) |
| **Nodes** | Functions that read/write state (LLM call, tool execution, etc.) |
| **Edges** | Connections between nodes (can be conditional) |
| **Checkpointing** | Save/restore agent state (enables human-in-the-loop, resume) |

#### Minimal Agent

```python
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

@tool
def get_progress(student_id: int, course_id: int) -> str:
    """Get student progress in a course."""
    return f"Student {student_id}: 65% complete in course {course_id}"

@tool
def search_content(query: str) -> str:
    """Search course materials."""
    return f"Found: '{query}' is covered in Module 3, Section 2"

llm = ChatOpenAI(model="gpt-4o-mini")
tools = [get_progress, search_content]
llm_with_tools = llm.bind_tools(tools)

def agent(state: MessagesState):
    return {"messages": [llm_with_tools.invoke(state["messages"])]}

graph = StateGraph(MessagesState)
graph.add_node("agent", agent)
graph.add_node("tools", ToolNode(tools))
graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", tools_condition)
graph.add_edge("tools", "agent")

app = graph.compile()

# Run
result = app.invoke({"messages": [("user", "How am I doing in course 101?")]})
```

#### What to Build (Progressive)

1. **Basic chatbot** → LangGraph with no tools, just conversation
2. **Tool-using agent** → Add 2-3 tools (progress, search, recommendations)
3. **Agent with memory** → Add `MemorySaver` checkpointer for conversation persistence
4. **Agent with human-in-the-loop** → Add an interrupt node for approval before actions
5. **Multi-agent** → Supervisor routing to tutor + quiz + recommender sub-agents

#### Resources - LangGraph

| Resource | Type | Time |
|----------|------|------|
| [LangGraph Quick Start](https://langchain-ai.github.io/langgraph/tutorials/introduction/) | Tutorial | 1.5 hrs |
| [LangGraph Conceptual Guide](https://langchain-ai.github.io/langgraph/concepts/) | Docs | 1 hr |
| [LangGraph Full Course - freeCodeCamp](https://www.youtube.com/watch?v=R8KB-Zcynxc) | Video | 2 hrs |
| [AI Agents in LangGraph - DeepLearning.AI](https://www.deeplearning.ai/short-courses/ai-agents-in-langgraph/) | Course | 3 hrs |
| [LangGraph Examples Repo](https://github.com/langchain-ai/langgraph/tree/main/examples) | Code | Reference |

---

### 2B: OpenAI Agents SDK (Production Alternative)

Simpler than LangGraph, built directly on OpenAI API. Good for straightforward agents.

```python
from agents import Agent, Runner, function_tool

@function_tool
def get_progress(student_id: int, course_id: int) -> str:
    """Get student progress."""
    return f"Student {student_id}: 65% complete in course {course_id}"

tutor_agent = Agent(
    name="SmartCourse Tutor",
    instructions="You are a helpful tutor. Use tools to look up student data before answering.",
    tools=[get_progress],
    model="gpt-4o-mini",
)

result = Runner.run_sync(tutor_agent, "How am I doing in course 101?")
print(result.final_output)
```

#### Resources - OpenAI Agents SDK

| Resource | Type | Time |
|----------|------|------|
| [OpenAI Agents SDK Docs](https://openai.github.io/openai-agents-python/) | Docs | 1 hr |
| [OpenAI Agents SDK - Quickstart](https://openai.github.io/openai-agents-python/quickstart/) | Tutorial | 30 min |
| [Agents SDK Announcement Blog](https://openai.com/index/new-tools-for-building-agents/) | Blog | 15 min |

---

## Phase 3: RAG for Agents (2-3 days)

RAG = Retrieval-Augmented Generation. Your agent **retrieves relevant course content** before answering.

### RAG Pipeline

```
Course Content (MongoDB) 
    → Chunk into paragraphs
    → Embed with text-embedding-3-small
    → Store in Vector DB (Qdrant / pgvector)

At Query Time:
    User Question 
    → Embed question 
    → Similarity search in Vector DB 
    → Top-K relevant chunks 
    → Feed to LLM as context 
    → Answer grounded in actual course material
```

### Key Decisions

| Decision | Options | Recommendation |
|----------|---------|---------------|
| Vector DB | Qdrant, pgvector, Pinecone, Weaviate | **Qdrant** (Docker, free, fast) or **pgvector** (reuse PostgreSQL) |
| Embedding Model | OpenAI `text-embedding-3-small`, `nomic-embed-text` | `text-embedding-3-small` (cheap, good quality) |
| Chunking Strategy | Fixed-size, recursive, semantic | Recursive text splitter (LangChain) |
| Chunk Size | 256-2048 tokens | 512 tokens with 50 token overlap |

### RAG as an Agent Tool

```python
@tool
def search_course_content(query: str, course_id: int) -> str:
    """Search course materials to answer a student question. 
    Always use this before answering content questions."""
    # 1. Embed the query
    embedding = openai.embeddings.create(input=query, model="text-embedding-3-small")
    # 2. Search vector DB
    results = qdrant.search(collection="courses", query_vector=embedding, filter={"course_id": course_id}, limit=3)
    # 3. Return relevant chunks
    return "\n\n".join([r.payload["text"] for r in results])
```

### Resources - RAG

| Resource | Type | Time |
|----------|------|------|
| [RAG from Scratch - LangChain](https://www.youtube.com/watch?v=sVcwVQRHIc8) | Video | 1 hr |
| [RAG Tutorial - LangChain Docs](https://python.langchain.com/docs/tutorials/rag/) | Tutorial | 1.5 hrs |
| [Building Agentic RAG - DeepLearning.AI](https://www.deeplearning.ai/short-courses/building-agentic-rag-with-llamaindex/) | Course | 2 hrs |
| [Qdrant Quick Start](https://qdrant.tech/documentation/quick-start/) | Docs | 30 min |
| [pgvector Guide](https://github.com/pgvector/pgvector) | Docs | 30 min |
| [Chunking Strategies](https://www.pinecone.io/learn/chunking-strategies/) | Blog | 30 min |

---

## Phase 4: Memory & State (1-2 days)

Agents need memory to be useful across conversations.

### Memory Types

| Type | What | Implementation |
|------|------|---------------|
| **Short-term** | Current conversation messages | Messages list in state |
| **Long-term** | Past conversations, user preferences | Store in DB, retrieve relevant ones |
| **Episodic** | What happened in past sessions | Summarize + store key facts |
| **Semantic** | Knowledge about the user | Vector DB of user interactions |

### Implementation

```python
from langgraph.checkpoint.postgres import PostgresSaver

# Checkpointer persists agent state (conversation history) to PostgreSQL
checkpointer = PostgresSaver.from_conn_string("postgresql://...")

agent = graph.compile(checkpointer=checkpointer)

# Each thread_id gets its own conversation history
config = {"configurable": {"thread_id": f"user_{user_id}_session_{session_id}"}}
result = agent.invoke({"messages": [("user", "Continue where we left off")]}, config)
```

### Resources - Memory

| Resource | Type | Time |
|----------|------|------|
| [LangGraph Persistence Guide](https://langchain-ai.github.io/langgraph/concepts/persistence/) | Docs | 30 min |
| [LangGraph Memory Guide](https://langchain-ai.github.io/langgraph/concepts/memory/) | Docs | 30 min |
| [Conversational RAG - LangChain](https://python.langchain.com/docs/tutorials/qa_chat_history/) | Tutorial | 1 hr |

---

## Phase 5: Multi-Agent Systems (2-3 days)

Only go here after single agent works well.

### Supervisor Pattern (Recommended for SmartCourse)

```
User Query
    │
    ▼
┌──────────────────┐
│  Supervisor Agent │  ← Decides which agent handles the query
│  (Router/Planner) │
└────────┬─────────┘
         │
    ┌────┼────────────┐
    ▼    ▼            ▼
┌──────┐ ┌──────┐ ┌────────────┐
│Tutor │ │Quiz  │ │Recommender │
│Agent │ │Agent │ │Agent       │
└──────┘ └──────┘ └────────────┘
```

| Sub-Agent | Tools | Responsibility |
|-----------|-------|---------------|
| **Tutor** | `search_content`, `get_progress` | Answer content questions using RAG |
| **Quiz** | `generate_quiz`, `grade_answer` | Create and evaluate assessments |
| **Recommender** | `get_history`, `search_courses` | Suggest next courses/modules |

### Resources - Multi-Agent

| Resource | Type | Time |
|----------|------|------|
| [LangGraph Multi-Agent Tutorial](https://langchain-ai.github.io/langgraph/tutorials/multi_agent/multi-agent-collaboration/) | Tutorial | 1.5 hrs |
| [Multi-Agent Systems with CrewAI - DeepLearning.AI](https://www.deeplearning.ai/short-courses/multi-ai-agent-systems-with-crewai/) | Course | 2 hrs |
| [LangGraph Supervisor Pattern](https://langchain-ai.github.io/langgraph/tutorials/multi_agent/agent_supervisor/) | Tutorial | 1 hr |

---

## Phase 6: Production & Integration (3-4 days)

### SmartCourse AI Service Architecture

```
services/ai-service/
├── Dockerfile
├── pyproject.toml
└── src/
    └── ai_service/
        ├── main.py              # FastAPI app
        ├── config.py            # Settings (LLM keys, vector DB, etc.)
        ├── api/
        │   ├── chat.py          # POST /ai/chat (WebSocket for streaming)
        │   └── index.py         # POST /ai/index-course (trigger content indexing)
        ├── agents/
        │   ├── tutor.py         # Tutor agent (LangGraph)
        │   ├── quiz.py          # Quiz generation agent
        │   └── supervisor.py    # Supervisor routing agent
        ├── tools/
        │   ├── progress.py      # Calls course-service API
        │   ├── content.py       # RAG over course content
        │   ├── courses.py       # Course search/recommendations
        │   └── quiz.py          # Quiz generation tools
        ├── rag/
        │   ├── embeddings.py    # Embedding generation
        │   ├── indexer.py       # Index course content into vector DB
        │   └── retriever.py     # Search vector DB
        └── memory/
            └── store.py         # Conversation persistence
```

### Key API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ai/chat` | Send message, get agent response (stream via WebSocket) |
| POST | `/ai/index-course/{course_id}` | Index course content for RAG |
| GET | `/ai/sessions/{user_id}` | List past chat sessions |
| DELETE | `/ai/sessions/{session_id}` | Clear a chat session |

### Production Checklist

- [ ] Rate limiting per user
- [ ] Token usage tracking and cost monitoring
- [ ] Fallback responses when LLM is down
- [ ] Content safety filters on inputs/outputs
- [ ] Streaming responses via WebSocket or SSE
- [ ] Async tool execution for slow tools
- [ ] Observability: log every agent step (LangSmith or custom)
- [ ] Evaluation: test agent with sample questions, measure accuracy

### Docker Addition

```yaml
ai-service:
  build: ./services/ai-service
  ports:
    - "8009:8009"
  environment:
    - OPENAI_API_KEY=${OPENAI_API_KEY}
    - QDRANT_URL=http://qdrant:6333
    - COURSE_SERVICE_URL=http://course-service:8002
    - POSTGRES_URL=postgresql://smartcourse:smartcourse@postgres:5432/ai_service
  depends_on:
    - qdrant
    - postgres

qdrant:
  image: qdrant/qdrant:v1.12.1
  ports:
    - "6333:6333"
  volumes:
    - qdrant_data:/qdrant/storage
```

---

## Evaluation & Observability

### How to Know Your Agent Works

| Method | Tool | What It Tells You |
|--------|------|------------------|
| **Tracing** | LangSmith / Langfuse | See every step the agent took, latency per step |
| **Evals** | Custom test suite | Does it answer correctly? Does it use the right tools? |
| **Cost tracking** | Token counting middleware | How much each conversation costs |
| **User feedback** | Thumbs up/down in chat | Real-world quality signal |

### Resources - Observability

| Resource | Type | Time |
|----------|------|------|
| [LangSmith Docs](https://docs.smith.langchain.com/) | Docs | 30 min |
| [Langfuse (open-source alternative)](https://langfuse.com/docs) | Docs | 30 min |

---

## Complete Learning Roadmap (Summary)

| Phase | Focus | Duration | Outcome |
|-------|-------|----------|---------|
| **0** | LLM APIs + Function Calling | 1-2 days | Can call OpenAI API, use tool/function calling |
| **1** | Agent Concepts (ReAct, architectures) | 2-3 days | Understand how agents reason and act |
| **2** | LangGraph + OpenAI Agents SDK | 3-4 days | Build a working single agent with tools |
| **3** | RAG (embeddings, vector DB, retrieval) | 2-3 days | Agent answers questions from course content |
| **4** | Memory & State | 1-2 days | Agent remembers past conversations |
| **5** | Multi-Agent Systems | 2-3 days | Supervisor + specialized sub-agents |
| **6** | Production Integration | 3-4 days | AI service running in SmartCourse Docker stack |

**Total: ~3-4 weeks** (alongside other work)

---

## Top Resources (Curated, Priority Order)

### Must-Do (Free)

| # | Resource | Type | Time | Why |
|---|----------|------|------|-----|
| 1 | [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling) | Docs | 45 min | Foundation of all tool-use |
| 2 | [Building Effective Agents - Anthropic](https://www.anthropic.com/engineering/building-effective-agents) | Blog | 45 min | Best practices from Anthropic |
| 3 | [LLM Powered Agents - Lilian Weng](https://lilianweng.github.io/posts/2023-06-23-agent/) | Blog | 1 hr | Definitive agent architecture overview |
| 4 | [LangGraph Quick Start](https://langchain-ai.github.io/langgraph/tutorials/introduction/) | Tutorial | 1.5 hrs | Hands-on agent building |
| 5 | [AI Agents in LangGraph - DeepLearning.AI](https://www.deeplearning.ai/short-courses/ai-agents-in-langgraph/) | Course | 3 hrs | Full course, project-based |
| 6 | [RAG from Scratch - LangChain](https://www.youtube.com/watch?v=sVcwVQRHIc8) | Video | 1 hr | RAG pipeline end-to-end |
| 7 | [LangGraph Full Course - freeCodeCamp](https://www.youtube.com/watch?v=R8KB-Zcynxc) | Video | 2 hrs | Deep dive with real examples |
| 8 | [OpenAI Agents SDK Quickstart](https://openai.github.io/openai-agents-python/quickstart/) | Tutorial | 30 min | Simplest production agent framework |

### Deep Dives (Free)

| Resource | Type | Time |
|----------|------|------|
| [Building Agentic RAG - DeepLearning.AI](https://www.deeplearning.ai/short-courses/building-agentic-rag-with-llamaindex/) | Course | 2 hrs |
| [Multi-Agent Systems with CrewAI - DeepLearning.AI](https://www.deeplearning.ai/short-courses/multi-ai-agent-systems-with-crewai/) | Course | 2 hrs |
| [LangGraph Multi-Agent Tutorial](https://langchain-ai.github.io/langgraph/tutorials/multi_agent/multi-agent-collaboration/) | Tutorial | 1.5 hrs |
| [Prompt Engineering Guide](https://www.promptingguide.ai/techniques/react) | Docs | 1 hr |
| [Qdrant Quick Start](https://qdrant.tech/documentation/quick-start/) | Docs | 30 min |

### YouTube Channels to Follow

| Channel | Why |
|---------|-----|
| [LangChain](https://www.youtube.com/@LangChain) | Framework updates, tutorials, webinars |
| [Sam Witteveen](https://www.youtube.com/@samwitteveen) | Practical AI agent tutorials |
| [James Briggs](https://www.youtube.com/@jamesbriggs) | RAG, vector DBs, agent patterns |
| [Dave Ebbelaar](https://www.youtube.com/@daveebbelaar) | Production AI engineering |
| [AI Jason](https://www.youtube.com/@AIJasonZ) | Agent framework comparisons |

### GitHub Repos to Study

| Repo | What You'll Learn |
|------|------------------|
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | Agent framework source + examples |
| [openai/openai-agents-python](https://github.com/openai/openai-agents-python) | OpenAI's agent SDK |
| [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | Multi-agent framework |
| [langchain-ai/rag-from-scratch](https://github.com/langchain-ai/rag-from-scratch) | RAG implementations |

---

*Created: February 16, 2026*
