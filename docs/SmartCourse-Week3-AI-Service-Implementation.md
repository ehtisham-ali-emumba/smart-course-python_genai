# SmartCourse Week 3: AI Microservice Implementation Guide

**Version:** 1.0  
**Date:** February 26, 2026  
**Scope:** AI Service with LangGraph for Quiz/Summary Generation & AI Tutor

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Technology Stack](#3-technology-stack)
4. [Database Design & Decisions](#4-database-design--decisions)
5. [Feature 1: Quiz & Summary Generation](#5-feature-1-quiz--summary-generation)
6. [Feature 2: AI Tutor (RAG-based)](#6-feature-2-ai-tutor-rag-based)
7. [LangGraph Agent Design](#7-langgraph-agent-design)
8. [API Endpoints](#8-api-endpoints)
9. [Event-Driven Integration](#9-event-driven-integration)
10. [Infrastructure Setup](#10-infrastructure-setup)
11. [Implementation Plan](#11-implementation-plan)
12. [Best Practices & Production Checklist](#12-best-practices--production-checklist)

---

## 1. Overview

### Goals

The AI Microservice provides two core capabilities:

| Feature                       | User     | Description                                                                                                   |
| ----------------------------- | -------- | ------------------------------------------------------------------------------------------------------------- |
| **Quiz & Summary Generation** | Teachers | Auto-generate quizzes and summaries for course modules based on lesson content (text, PDF, video transcripts) |
| **AI Tutor**                  | Students | Interactive RAG-powered tutor that answers questions about enrolled course content                            |

### Key Constraints

- Course content (modules, lessons) stored in **MongoDB** (course-service)
- Student progress & enrollments stored in **PostgreSQL** (course-service)
- Content types: `text`, `pdf`, `video` (with transcripts file), `quiz`, `assignment`
- Teachers can generate/regenerate quiz & summary anytime after adding ≥1 lesson
- AI Tutor activates only for **published courses**
- Teachers can manually edit AI-generated content

---

## 2. Architecture

### High-Level System Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                  SMARTCOURSE AI ARCHITECTURE                                 │
└─────────────────────────────────────────────────────────────────────────────────────────────┘

                              ┌──────────────────────┐
                              │    API Gateway       │
                              │  (Nginx + Auth       │
                              │   Sidecar :8000)     │
                              └──────────┬───────────┘
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        │                                │                                │
        ▼                                ▼                                ▼
┌───────────────┐              ┌───────────────┐              ┌───────────────────┐
│ User Service  │              │Course Service │              │   AI Service      │
│   (8001)      │              │   (8002)      │              │     (8009)        │
└───────────────┘              └───────┬───────┘              └─────────┬─────────┘
                                       │                                │
                                       │                                │
                               ┌───────┴───────┐                ┌───────┴───────┐
                               │               │                │               │
                               ▼               ▼                ▼               ▼
                        ┌──────────┐    ┌──────────┐     ┌──────────┐    ┌──────────┐
                        │PostgreSQL│    │ MongoDB  │     │  Qdrant  │    │PostgreSQL│
                        │(courses, │    │ (content)│     │(vectors) │    │(ai_data) │
                        │progress) │    └──────────┘     └──────────┘    └──────────┘
                        └──────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    EVENT LAYER (Kafka)                                       │
│                                                                                              │
│   course.events ──────────────────┐                                                          │
│   (course.published)              │     ┌─────────────────────────────────────────────────┐ │
│   (content.updated)               ├────►│ AI Service Consumer                             │ │
│                                   │     │ • Triggers RAG indexing on course publish       │ │
│   ai.events ◄─────────────────────┤     │ • Updates embeddings on content change          │ │
│   (quiz.generated)                │     └─────────────────────────────────────────────────┘ │
│   (summary.generated)             │                                                          │
│   (rag.indexed)                   │                                                          │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

### AI Service Internal Architecture

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              AI SERVICE (Port 8009)                                     │
│                                                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │                              API LAYER (FastAPI)                                 │   │
│  │  POST /ai/generate/quiz/{course_id}/{module_id}                                 │   │
│  │  POST /ai/generate/summary/{course_id}/{module_id}                              │   │
│  │  POST /ai/tutor/chat                         (WebSocket for streaming)          │   │
│  │  POST /ai/index/course/{course_id}           (Manual RAG indexing)              │   │
│  │  GET  /ai/sessions/{user_id}                 (Chat history)                     │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                          │                                              │
│                                          ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │                           LANGGRAPH AGENTS                                       │   │
│  │                                                                                  │   │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────────┐   │   │
│  │  │ Content Generator│  │   Quiz Agent     │  │      AI Tutor Agent          │   │   │
│  │  │     Agent        │  │                  │  │     (RAG + Conversation)     │   │   │
│  │  │                  │  │ • Parse content  │  │                              │   │   │
│  │  │ • Summarizer     │  │ • Generate Q&A   │  │  • Retrieve context (RAG)    │   │   │
│  │  │ • Content Parser │  │ • Validate quiz  │  │  • Answer questions          │   │   │
│  │  │                  │  │ • Format output  │  │  • Track conversation        │   │   │
│  │  └──────────────────┘  └──────────────────┘  └──────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                          │                                              │
│                                          ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │                              TOOLS LAYER                                         │   │
│  │                                                                                  │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                  │   │
│  │  │ Content Fetcher │  │  RAG Retriever  │  │ Progress Fetcher│                  │   │
│  │  │ (MongoDB)       │  │  (Qdrant)       │  │ (Course Service)│                  │   │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘                  │   │
│  │                                                                                  │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                  │   │
│  │  │ PDF Parser      │  │ Transcript      │  │ Quiz Validator  │                  │   │
│  │  │ (PyPDF2/pdfplumber)│ Parser          │  │                 │                  │   │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘                  │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
│                                          │                                              │
│                                          ▼                                              │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐   │
│  │                              DATA LAYER                                          │   │
│  │                                                                                  │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                  │   │
│  │  │    MongoDB      │  │     Qdrant      │  │   PostgreSQL    │                  │   │
│  │  │ (read content)  │  │ (vector store)  │  │ (AI metadata)   │                  │   │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘                  │   │
│  └─────────────────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Technology Stack

### Core Technologies

| Component            | Technology | Version                | Rationale                                                    |
| -------------------- | ---------- | ---------------------- | ------------------------------------------------------------ |
| **Framework**        | FastAPI    | 0.111+                 | Async, OpenAPI docs, WebSocket support                       |
| **Agent Framework**  | LangGraph  | 0.2+                   | Stateful agents with cycles, checkpointing, production-ready |
| **LLM Provider**     | OpenAI     | GPT-4o-mini            | Cost-effective, good quality, fast                           |
| **Embeddings**       | OpenAI     | text-embedding-3-small | 1536 dimensions, excellent quality/cost ratio                |
| **Vector Database**  | Qdrant     | 1.12+                  | Fast, Docker-ready, filtering support, free                  |
| **Document Parsing** | LangChain  | 0.3+                   | PDF loaders, text splitters, unified interface               |

### Python Dependencies

```toml
# pyproject.toml
[project]
name = "ai-service"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    # FastAPI
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.30.0",
    "python-multipart>=0.0.9",

    # LangGraph & LangChain
    "langgraph>=0.2.0",
    "langchain>=0.3.0",
    "langchain-openai>=0.2.0",
    "langchain-community>=0.3.0",

    # Vector DB
    "qdrant-client>=1.12.0",

    # Database
    "motor>=3.5.0",              # MongoDB async
    "asyncpg>=0.29.0",           # PostgreSQL async
    "sqlalchemy[asyncio]>=2.0.0",

    # Document Processing
    "pypdf>=4.0.0",
    "pdfplumber>=0.11.0",

    # Kafka
    "aiokafka>=0.11.0",

    # Utilities
    "pydantic>=2.9.0",
    "pydantic-settings>=2.5.0",
    "httpx>=0.27.0",
    "tiktoken>=0.7.0",           # Token counting

    # Shared package
    "shared @ file:///${PROJECT_ROOT}/../shared",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.6.0",
]
```

---

## 4. Database Design & Decisions

### Decision Matrix

| Data Type                                | Database   | Rationale                                                            |
| ---------------------------------------- | ---------- | -------------------------------------------------------------------- |
| **AI-Generated Content** (Quiz, Summary) | MongoDB    | Flexible schema, tied to course content structure, easy updates      |
| **Vector Embeddings**                    | Qdrant     | Purpose-built for similarity search, filtering by course/module      |
| **Conversation History**                 | PostgreSQL | Structured data, easy querying by user/session, joins with user data |
| **Generation Metadata**                  | PostgreSQL | Track generation history, versions, audit trail                      |

### MongoDB Collection: `ai_generated_content`

Stored alongside course content in the same MongoDB instance.

```javascript
// Collection: ai_generated_content
{
  "_id": ObjectId("..."),
  "course_id": 123,
  "module_id": "mod_abc123",

  // Summary
  "summary": {
    "content": "This module covers...",
    "version": 3,
    "generated_at": ISODate("2026-02-26T10:00:00Z"),
    "model": "gpt-4o-mini",
    "is_edited": true,                    // Teacher edited it
    "edited_at": ISODate("2026-02-26T12:00:00Z"),
    "original_content": "Original AI text..." // Keep original for reference
  },

  // Quiz
  "quiz": {
    "questions": [
      {
        "question_id": "q1",
        "question": "What is the main purpose of...",
        "type": "multiple_choice",        // multiple_choice, true_false, short_answer
        "options": ["A", "B", "C", "D"],
        "correct_answer": "B",
        "explanation": "Because...",
        "difficulty": "medium"            // easy, medium, hard
      }
    ],
    "version": 2,
    "generated_at": ISODate("2026-02-26T10:30:00Z"),
    "model": "gpt-4o-mini",
    "is_edited": false,
    "settings": {
      "num_questions": 10,
      "difficulty_distribution": {"easy": 3, "medium": 5, "hard": 2}
    }
  },

  // Metadata
  "source_lesson_ids": ["lesson_1", "lesson_2", "lesson_3"],
  "created_at": ISODate("2026-02-26T10:00:00Z"),
  "updated_at": ISODate("2026-02-26T12:00:00Z")
}
```

**Why MongoDB for AI Content?**

1. Schema flexibility — quiz format may evolve
2. Nested structure matches course content (modules → lessons)
3. Easy to query alongside existing course content
4. Supports teacher edits with version tracking

### Qdrant Collection: `course_embeddings`

```python
# Qdrant collection schema
{
    "collection_name": "course_embeddings",
    "vectors": {
        "size": 1536,  # text-embedding-3-small dimension
        "distance": "Cosine"
    }
}

# Point structure
{
    "id": "uuid-string",
    "vector": [0.123, 0.456, ...],  # 1536 dimensions
    "payload": {
        "course_id": 123,
        "module_id": "mod_abc123",
        "lesson_id": "lesson_xyz",
        "chunk_index": 0,
        "content_type": "text",         # text, pdf, transcript
        "text": "The actual chunk text...",
        "metadata": {
            "lesson_title": "Introduction to...",
            "module_title": "Fundamentals",
            "course_title": "Python Programming"
        }
    }
}
```

**Why Qdrant?**

1. Purpose-built for vector similarity search
2. Excellent filtering (by course_id, module_id)
3. Docker-ready, free, fast
4. Supports payload storage (no need for separate metadata DB)
5. Better than pgvector for dedicated vector workloads

### PostgreSQL Tables: AI Service Database

```sql
-- Table: ai_conversations (Chat history for AI Tutor)
CREATE TABLE ai_conversations (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL,           -- FK to user-service
    course_id INTEGER NOT NULL,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,

    -- Index for quick lookup
    UNIQUE(session_id)
);

CREATE INDEX idx_conversations_user ON ai_conversations(user_id);
CREATE INDEX idx_conversations_course ON ai_conversations(course_id);

-- Table: ai_messages (Individual messages in a conversation)
CREATE TABLE ai_messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES ai_conversations(id) ON DELETE CASCADE,

    role VARCHAR(20) NOT NULL,          -- 'user', 'assistant', 'system'
    content TEXT NOT NULL,

    -- RAG context (what was retrieved)
    retrieved_context JSONB,            -- [{chunk_id, text, score}]

    -- Metadata
    tokens_used INTEGER,
    model VARCHAR(50),
    latency_ms INTEGER,

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_messages_conversation ON ai_messages(conversation_id);

-- Table: ai_generation_history (Audit trail for quiz/summary generation)
CREATE TABLE ai_generation_history (
    id SERIAL PRIMARY KEY,
    course_id INTEGER NOT NULL,
    module_id VARCHAR(100) NOT NULL,

    generation_type VARCHAR(20) NOT NULL,  -- 'quiz', 'summary'
    version INTEGER NOT NULL DEFAULT 1,

    -- Who triggered it
    triggered_by INTEGER NOT NULL,          -- teacher user_id

    -- Generation details
    input_lesson_count INTEGER,
    model VARCHAR(50),
    tokens_used INTEGER,
    latency_ms INTEGER,

    -- Status
    status VARCHAR(20) DEFAULT 'completed', -- 'pending', 'completed', 'failed'
    error_message TEXT,

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_gen_history_course_module ON ai_generation_history(course_id, module_id);

-- Table: rag_index_status (Track RAG indexing for courses)
CREATE TABLE rag_index_status (
    id SERIAL PRIMARY KEY,
    course_id INTEGER NOT NULL UNIQUE,

    status VARCHAR(20) DEFAULT 'pending',   -- 'pending', 'indexing', 'indexed', 'failed'
    indexed_at TIMESTAMP,

    -- Stats
    total_chunks INTEGER,
    total_lessons INTEGER,
    embedding_model VARCHAR(50),

    -- For incremental updates
    last_content_hash VARCHAR(64),          -- MD5 of content, to detect changes

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_rag_status_course ON rag_index_status(course_id);
```

---

## 5. Feature 1: Quiz & Summary Generation

### User Flow

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                        QUIZ & SUMMARY GENERATION FLOW                                    │
└─────────────────────────────────────────────────────────────────────────────────────────┘

  Teacher                    Frontend                   AI Service                 MongoDB
    │                           │                           │                         │
    │  1. Create Module         │                           │                         │
    ├──────────────────────────►│                           │                         │
    │                           │                           │                         │
    │  2. Add Lesson(s)         │                           │                         │
    │  (text/pdf/video+transcript)                          │                         │
    ├──────────────────────────►│                           │                         │
    │                           │                           │                         │
    │  3. Click "Generate Quiz" │                           │                         │
    │  (button enabled when ≥1 lesson)                      │                         │
    ├──────────────────────────►│                           │                         │
    │                           │  4. POST /ai/generate/quiz│                         │
    │                           ├──────────────────────────►│                         │
    │                           │                           │  5. Fetch module content│
    │                           │                           ├────────────────────────►│
    │                           │                           │◄────────────────────────┤
    │                           │                           │                         │
    │                           │                           │  6. Parse & chunk       │
    │                           │                           │     content             │
    │                           │                           │                         │
    │                           │                           │  7. LangGraph Agent     │
    │                           │                           │     generates quiz      │
    │                           │                           │                         │
    │                           │                           │  8. Save to MongoDB     │
    │                           │                           ├────────────────────────►│
    │                           │◄──────────────────────────┤                         │
    │  9. Display Quiz          │                           │                         │
    │◄──────────────────────────┤                           │                         │
    │                           │                           │                         │
    │  10. Edit Quiz (optional) │                           │                         │
    ├──────────────────────────►│                           │                         │
    │                           │  11. PUT /ai/quiz/{id}    │                         │
    │                           ├──────────────────────────►│                         │
    │                           │                           │  12. Update (is_edited=true)
    │                           │                           ├────────────────────────►│
    │                           │                           │                         │
```

### Content Parsing Strategy

| Lesson Type    | Parsing Approach                                                |
| -------------- | --------------------------------------------------------------- |
| **text**       | Direct use of `content` field                                   |
| **pdf**        | Download from URL, extract text with `pypdf` or `pdfplumber`    |
| **video**      | Parse transcript file (uploaded by teacher as `.txt` or `.vtt`) |
| **quiz**       | Skip (existing quiz content)                                    |
| **assignment** | Include assignment description                                  |

```python
# Content parsing pseudocode
async def parse_lesson_content(lesson: dict) -> str:
    """Extract text content from a lesson."""
    lesson_type = lesson["type"]

    if lesson_type == "text":
        return lesson.get("content", "")

    elif lesson_type == "pdf":
        # Get PDF URL from resources
        pdf_resource = next(
            (r for r in lesson.get("resources", []) if r["type"] == "pdf"),
            None
        )
        if pdf_resource:
            return await extract_pdf_text(pdf_resource["url"])
        return ""

    elif lesson_type == "video":
        # Get transcript file from resources
        transcript_resource = next(
            (r for r in lesson.get("resources", []) if r["type"] == "transcript" or r["name"].endswith('.txt')),
            None
        )
        if transcript_resource:
            return await fetch_transcript(transcript_resource["url"])
        return ""

    elif lesson_type == "assignment":
        return lesson.get("content", "")

    return ""
```

### Quiz Generation Prompt

```python
QUIZ_GENERATION_SYSTEM_PROMPT = """You are an expert educational content creator specializing in creating
high-quality assessment questions for online courses.

Your task is to generate quiz questions based on the provided lesson content.

Guidelines:
1. Create questions that test understanding, not just memorization
2. Ensure questions are directly based on the provided content
3. Vary question types (multiple choice, true/false, short answer)
4. Include clear explanations for correct answers
5. Distribute difficulty levels as requested

Output Format:
Return a JSON object with the following structure:
{
  "questions": [
    {
      "question": "...",
      "type": "multiple_choice",
      "options": ["A", "B", "C", "D"],
      "correct_answer": "B",
      "explanation": "...",
      "difficulty": "medium"
    }
  ]
}
"""

QUIZ_GENERATION_USER_PROMPT = """
Module: {module_title}
Course: {course_title}

Generate {num_questions} quiz questions based on this content:

{content}

Difficulty distribution:
- Easy: {easy_count}
- Medium: {medium_count}
- Hard: {hard_count}
"""
```

### Summary Generation Prompt

```python
SUMMARY_GENERATION_SYSTEM_PROMPT = """You are an expert educational content summarizer.
Create a clear, comprehensive summary of the lesson content that helps students:
1. Understand the key concepts
2. Review before assessments
3. Quickly recall main points

Structure your summary with:
- Key Learning Objectives (bullet points)
- Main Concepts (with brief explanations)
- Important Terms (if applicable)
- Quick Review Points

Keep the summary concise but complete. Target 200-400 words.
"""
```

---

## 6. Feature 2: AI Tutor (RAG-based)

### RAG Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              RAG PIPELINE FOR AI TUTOR                                   │
└─────────────────────────────────────────────────────────────────────────────────────────┘

                                 INDEXING PHASE (On Course Publish)
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                        │
│  MongoDB                    AI Service                              Qdrant            │
│  (Course Content)           (Indexer)                               (Vector DB)       │
│                                                                                        │
│  ┌─────────────┐           ┌─────────────┐                         ┌─────────────┐   │
│  │ Module 1    │           │             │                         │             │   │
│  │ - Lesson 1  │──────────►│  1. Fetch   │                         │             │   │
│  │ - Lesson 2  │           │     Content │                         │             │   │
│  │ Module 2    │           │             │                         │             │   │
│  │ - Lesson 3  │           │  2. Parse   │                         │             │   │
│  └─────────────┘           │     (text,  │                         │             │   │
│                            │      pdf,   │                         │             │   │
│                            │   transcript)│                         │             │   │
│                            │             │                         │             │   │
│                            │  3. Chunk   │                         │             │   │
│                            │     (512    │                         │             │   │
│                            │      tokens)│                         │             │   │
│                            │             │   ┌───────────────┐     │  Points:    │   │
│                            │  4. Embed   │──►│ OpenAI API    │────►│  - vector   │   │
│                            │             │   │ text-embedding│     │  - payload  │   │
│                            │             │   │ -3-small      │     │    (text,   │   │
│                            └─────────────┘   └───────────────┘     │    metadata)│   │
│                                                                     └─────────────┘   │
└───────────────────────────────────────────────────────────────────────────────────────┘

                                  QUERY PHASE (Student Asks Question)
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                        │
│  Student                   AI Service                Qdrant           LLM             │
│                            (Tutor Agent)             (Vector DB)      (GPT-4o-mini)   │
│                                                                                        │
│  "How does                 ┌─────────────┐          ┌─────────────┐                   │
│   recursion                │             │          │             │                   │
│   work?"                   │  1. Embed   │          │             │                   │
│      │                     │     Query   │          │             │                   │
│      │                     │             │          │             │                   │
│      └────────────────────►│  2. Search  │─────────►│  Similarity │                   │
│                            │     Qdrant  │          │  Search     │                   │
│                            │             │◄─────────│  (top-k=5)  │                   │
│                            │             │          └─────────────┘                   │
│                            │  3. Build   │                                            │
│                            │     Prompt  │          ┌─────────────┐                   │
│                            │  (context + │─────────►│             │                   │
│                            │   question) │          │  Generate   │                   │
│                            │             │◄─────────│  Answer     │                   │
│      ◄─────────────────────│  4. Stream  │          │             │                   │
│   "Recursion is..."        │     Response│          └─────────────┘                   │
│                            └─────────────┘                                            │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

### Chunking Strategy

```python
from langchain.text_splitter import RecursiveCharacterTextSplitter

# Optimal settings for course content
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=512,           # ~512 tokens
    chunk_overlap=50,         # 10% overlap for context continuity
    length_function=len,
    separators=[
        "\n\n",               # Paragraph breaks
        "\n",                 # Line breaks
        ". ",                 # Sentences
        ", ",                 # Clauses
        " ",                  # Words
        ""                    # Characters
    ]
)
```

### RAG Retrieval with Filtering

```python
async def retrieve_context(
    query: str,
    course_id: int,
    module_id: Optional[str] = None,
    top_k: int = 5
) -> list[dict]:
    """Retrieve relevant content chunks for a query."""

    # 1. Embed the query
    query_embedding = await embed_text(query)

    # 2. Build filter
    filter_conditions = {"course_id": course_id}
    if module_id:
        filter_conditions["module_id"] = module_id

    # 3. Search Qdrant
    results = qdrant_client.search(
        collection_name="course_embeddings",
        query_vector=query_embedding,
        query_filter=Filter(
            must=[
                FieldCondition(key="course_id", match=MatchValue(value=course_id)),
                # Optional: filter by module
            ]
        ),
        limit=top_k
    )

    # 4. Return context chunks
    return [
        {
            "text": hit.payload["text"],
            "score": hit.score,
            "lesson_title": hit.payload["metadata"]["lesson_title"],
            "module_title": hit.payload["metadata"]["module_title"]
        }
        for hit in results
    ]
```

### AI Tutor System Prompt

```python
AI_TUTOR_SYSTEM_PROMPT = """You are an intelligent AI tutor for the SmartCourse platform.

Your role:
- Help students understand course content
- Answer questions based ONLY on the provided context
- If the answer isn't in the context, say "I don't have information about that in this course material"
- Be encouraging and supportive
- Use examples from the course content when helpful
- Suggest related topics the student might want to explore

Guidelines:
1. Always cite which module/lesson your answer comes from
2. Keep explanations clear and appropriate for the student's level
3. If asked about something outside the course, politely redirect
4. Never make up information that isn't in the context

Current Course: {course_title}
Student's Progress: {progress_summary}
"""

AI_TUTOR_USER_PROMPT = """
Context from course materials:
---
{retrieved_context}
---

Student's Question: {question}

Please provide a helpful, accurate answer based on the course materials above.
"""
```

### Conversation Memory

```python
from langgraph.checkpoint.postgres import PostgresSaver

# Use PostgreSQL for conversation persistence
checkpointer = PostgresSaver.from_conn_string(DATABASE_URL)

# Each student-course combination gets a unique thread
def get_thread_id(user_id: int, course_id: int, session_id: str) -> str:
    return f"tutor_{user_id}_{course_id}_{session_id}"

# Agent uses checkpointer for memory
tutor_graph = create_tutor_graph()
tutor_agent = tutor_graph.compile(checkpointer=checkpointer)

# Invoke with thread config
config = {"configurable": {"thread_id": get_thread_id(user_id, course_id, session_id)}}
response = await tutor_agent.ainvoke({"messages": messages}, config)
```

---

## 7. LangGraph Agent Design

### Quiz Generation Agent Graph

```python
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_openai import ChatOpenAI
from typing import TypedDict, Annotated
import operator

class QuizGenerationState(TypedDict):
    """State for quiz generation workflow."""
    course_id: int
    module_id: str

    # Content
    raw_content: list[str]           # Parsed lesson content
    combined_content: str            # Merged content

    # Generation settings
    num_questions: int
    difficulty_distribution: dict

    # Output
    generated_quiz: dict | None
    validation_errors: list[str]
    retry_count: int                 # Track retries to prevent infinite loops

    # Metadata
    messages: Annotated[list, operator.add]

def create_quiz_generation_graph():
    """Create LangGraph for quiz generation."""

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)

    # Node: Fetch content from MongoDB
    async def fetch_content(state: QuizGenerationState) -> dict:
        content = await fetch_module_content(
            state["course_id"],
            state["module_id"]
        )
        return {"raw_content": content}

    # Node: Parse and combine content
    async def parse_content(state: QuizGenerationState) -> dict:
        parsed = []
        for lesson_content in state["raw_content"]:
            text = await parse_lesson_content(lesson_content)
            if text:
                parsed.append(text)

        combined = "\n\n---\n\n".join(parsed)
        return {"combined_content": combined}

    # Node: Generate quiz with LLM
    async def generate_quiz(state: QuizGenerationState) -> dict:
        prompt = QUIZ_GENERATION_USER_PROMPT.format(
            module_title=state.get("module_title", ""),
            course_title=state.get("course_title", ""),
            num_questions=state["num_questions"],
            content=state["combined_content"][:8000],  # Truncate if too long
            easy_count=state["difficulty_distribution"].get("easy", 3),
            medium_count=state["difficulty_distribution"].get("medium", 5),
            hard_count=state["difficulty_distribution"].get("hard", 2),
        )

        response = await llm.ainvoke([
            {"role": "system", "content": QUIZ_GENERATION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ])

        quiz = parse_json_response(response.content)
        return {"generated_quiz": quiz}

    # Node: Validate quiz
    async def validate_quiz(state: QuizGenerationState) -> dict:
        errors = []
        quiz = state["generated_quiz"]

        if not quiz or "questions" not in quiz:
            errors.append("Invalid quiz format")
        elif len(quiz["questions"]) < state["num_questions"]:
            errors.append(f"Only {len(quiz['questions'])} questions generated")

        for i, q in enumerate(quiz.get("questions", [])):
            if "question" not in q:
                errors.append(f"Question {i+1} missing question text")
            if q.get("type") == "multiple_choice" and len(q.get("options", [])) < 2:
                errors.append(f"Question {i+1} has insufficient options")

        return {"validation_errors": errors}

    # Node: Save to MongoDB
    async def save_quiz(state: QuizGenerationState) -> dict:
        if state["validation_errors"]:
            return {"messages": ["Quiz validation failed"]}

        await save_generated_content(
            course_id=state["course_id"],
            module_id=state["module_id"],
            content_type="quiz",
            content=state["generated_quiz"]
        )
        return {"messages": ["Quiz saved successfully"]}

    # Conditional edge: retry or save (max 2 retries to prevent infinite loops)
    def should_retry(state: QuizGenerationState) -> str:
        if state["validation_errors"] and state.get("retry_count", 0) < 2:
            return "generate_quiz"  # Retry
        return "save_quiz"

    # Build graph
    graph = StateGraph(QuizGenerationState)

    graph.add_node("fetch_content", fetch_content)
    graph.add_node("parse_content", parse_content)
    graph.add_node("generate_quiz", generate_quiz)
    graph.add_node("validate_quiz", validate_quiz)
    graph.add_node("save_quiz", save_quiz)

    graph.add_edge(START, "fetch_content")
    graph.add_edge("fetch_content", "parse_content")
    graph.add_edge("parse_content", "generate_quiz")
    graph.add_edge("generate_quiz", "validate_quiz")
    graph.add_conditional_edges("validate_quiz", should_retry)
    graph.add_edge("save_quiz", END)

    return graph.compile()
```

### AI Tutor Agent Graph

```python
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.tools import tool

class TutorState(MessagesState):
    """Extended state for AI Tutor."""
    course_id: int
    user_id: int
    retrieved_context: list[dict]

# Define Tools
@tool
async def search_course_content(query: str, course_id: int) -> str:
    """Search course materials to answer student questions.
    Always use this before answering content-related questions.

    Args:
        query: The search query based on student's question
        course_id: The course to search within
    """
    results = await retrieve_context(query, course_id, top_k=5)

    if not results:
        return "No relevant content found in course materials."

    context_str = "\n\n".join([
        f"[From: {r['module_title']} > {r['lesson_title']}]\n{r['text']}"
        for r in results
    ])
    return context_str

@tool
async def get_student_progress(user_id: int, course_id: int) -> str:
    """Get the student's current progress in the course.

    Args:
        user_id: The student's user ID
        course_id: The course ID
    """
    # Call course-service API
    progress = await fetch_student_progress(user_id, course_id)
    return f"""
    Course Progress: {progress['completion_percentage']}%
    Completed Modules: {progress['completed_modules']}
    Current Module: {progress['current_module']}
    """

@tool
def get_module_quiz(course_id: int, module_id: str) -> str:
    """Get quiz questions for a specific module to help the student practice.

    Args:
        course_id: The course ID
        module_id: The module ID
    """
    quiz = fetch_module_quiz(course_id, module_id)
    if not quiz:
        return "No quiz available for this module yet."

    return f"Quiz for this module has {len(quiz['questions'])} questions. Would you like to practice?"

def create_tutor_graph():
    """Create LangGraph for AI Tutor."""

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7, streaming=True)
    tools = [search_course_content, get_student_progress, get_module_quiz]
    llm_with_tools = llm.bind_tools(tools)

    # Node: Agent reasoning
    async def agent(state: TutorState):
        system_message = AI_TUTOR_SYSTEM_PROMPT.format(
            course_title=state.get("course_title", ""),
            progress_summary=state.get("progress_summary", "")
        )

        messages = [{"role": "system", "content": system_message}] + state["messages"]
        response = await llm_with_tools.ainvoke(messages)

        return {"messages": [response]}

    # Build graph
    graph = StateGraph(TutorState)

    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(tools))

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")

    return graph
```

### Agent Visualization

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              AI TUTOR AGENT GRAPH                                        │
└─────────────────────────────────────────────────────────────────────────────────────────┘

                                    ┌─────────┐
                                    │  START  │
                                    └────┬────┘
                                         │
                                         ▼
                              ┌──────────────────┐
                              │                  │
                         ┌───►│   Agent Node     │◄───┐
                         │    │  (LLM Reasoning) │    │
                         │    │                  │    │
                         │    └────────┬─────────┘    │
                         │             │              │
                         │             ▼              │
                         │    ┌──────────────────┐    │
                         │    │  tools_condition │    │
                         │    │  (Route Decision)│    │
                         │    └────────┬─────────┘    │
                         │             │              │
                         │      ┌──────┴──────┐       │
                         │      │             │       │
                         │      ▼             ▼       │
                         │ ┌────────┐   ┌─────────┐   │
                         │ │  END   │   │  Tools  │───┘
                         │ │(answer)│   │  Node   │
                         │ └────────┘   │         │
                         │              │ • search_course_content
                         │              │ • get_student_progress
                         │              │ • get_module_quiz
                         │              └─────────┘
                         │
                    (Loop back after tool execution)
```

---

## 8. API Endpoints

### Complete API Specification

```python
# services/ai-service/src/ai_service/api/routes.py

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from pydantic import BaseModel

router = APIRouter(prefix="/ai", tags=["AI Service"])

# ═══════════════════════════════════════════════════════════════
#  QUIZ & SUMMARY GENERATION
# ═══════════════════════════════════════════════════════════════

class GenerationSettings(BaseModel):
    num_questions: int = 10
    difficulty_distribution: dict = {"easy": 3, "medium": 5, "hard": 2}

class GenerationResponse(BaseModel):
    success: bool
    content: dict | None
    version: int
    message: str

@router.post("/generate/quiz/{course_id}/{module_id}", response_model=GenerationResponse)
async def generate_quiz(
    course_id: int,
    module_id: str,
    settings: GenerationSettings = GenerationSettings(),
    current_user: dict = Depends(get_current_teacher)  # Requires teacher role
):
    """
    Generate quiz questions for a module.

    - Requires teacher role and course ownership
    - Module must have at least 1 lesson
    - Can be regenerated multiple times (version increments)
    """
    pass

@router.post("/generate/summary/{course_id}/{module_id}", response_model=GenerationResponse)
async def generate_summary(
    course_id: int,
    module_id: str,
    current_user: dict = Depends(get_current_teacher)
):
    """Generate a summary for a module's lessons."""
    pass

@router.get("/content/{course_id}/{module_id}")
async def get_ai_content(
    course_id: int,
    module_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get AI-generated content (quiz & summary) for a module."""
    pass

@router.put("/content/{course_id}/{module_id}/quiz")
async def update_quiz(
    course_id: int,
    module_id: str,
    quiz_update: dict,
    current_user: dict = Depends(get_current_teacher)
):
    """Update/edit AI-generated quiz (marks as edited)."""
    pass

@router.put("/content/{course_id}/{module_id}/summary")
async def update_summary(
    course_id: int,
    module_id: str,
    summary_update: dict,
    current_user: dict = Depends(get_current_teacher)
):
    """Update/edit AI-generated summary (marks as edited)."""
    pass

# ═══════════════════════════════════════════════════════════════
#  AI TUTOR (CHAT)
# ═══════════════════════════════════════════════════════════════

class ChatMessage(BaseModel):
    content: str
    course_id: int
    session_id: str | None = None  # For continuing conversation

class ChatResponse(BaseModel):
    response: str
    session_id: str
    sources: list[dict]  # Retrieved context sources

@router.post("/tutor/chat", response_model=ChatResponse)
async def chat_with_tutor(
    message: ChatMessage,
    current_user: dict = Depends(get_current_student)  # Requires enrollment
):
    """
    Send a message to the AI Tutor.

    - Student must be enrolled in the course
    - Course must be published and indexed
    - Returns response with source citations
    """
    pass

@router.websocket("/tutor/chat/stream")
async def chat_stream(websocket: WebSocket):
    """
    WebSocket endpoint for streaming chat responses.

    Protocol:
    1. Client connects
    2. Client sends: {"type": "auth", "token": "jwt_token"}
    3. Client sends: {"type": "message", "content": "...", "course_id": 123, "session_id": "..."}
    4. Server streams: {"type": "chunk", "content": "partial response..."}
    5. Server sends: {"type": "done", "sources": [...]}
    """
    await websocket.accept()
    try:
        # Handle WebSocket communication
        pass
    except WebSocketDisconnect:
        pass

@router.get("/tutor/sessions/{user_id}")
async def list_chat_sessions(
    user_id: int,
    current_user: dict = Depends(get_current_user)
):
    """List all chat sessions for a user."""
    pass

@router.get("/tutor/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get all messages in a chat session."""
    pass

@router.delete("/tutor/sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a chat session."""
    pass

# ═══════════════════════════════════════════════════════════════
#  RAG INDEXING
# ═══════════════════════════════════════════════════════════════

class IndexStatus(BaseModel):
    course_id: int
    status: str  # pending, indexing, indexed, failed
    total_chunks: int | None
    indexed_at: str | None
    error: str | None

@router.post("/index/course/{course_id}")
async def index_course(
    course_id: int,
    force: bool = False,  # Force re-index even if already indexed
    current_user: dict = Depends(get_current_admin)  # Admin only for manual trigger
):
    """
    Manually trigger RAG indexing for a course.

    - Usually triggered automatically on course publish
    - Use force=True to re-index after content updates
    """
    pass

@router.get("/index/status/{course_id}", response_model=IndexStatus)
async def get_index_status(course_id: int):
    """Get RAG indexing status for a course."""
    pass

@router.delete("/index/course/{course_id}")
async def delete_index(
    course_id: int,
    current_user: dict = Depends(get_current_admin)
):
    """Delete RAG index for a course (e.g., when course is deleted)."""
    pass

# ═══════════════════════════════════════════════════════════════
#  HEALTH & METRICS
# ═══════════════════════════════════════════════════════════════

@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "qdrant": await check_qdrant_health(),
        "mongodb": await check_mongodb_health(),
        "llm": "available"
    }
```

---

## 9. Event-Driven Integration

### Kafka Events

#### Events Consumed by AI Service

| Topic           | Event              | Trigger                   | AI Service Action                   |
| --------------- | ------------------ | ------------------------- | ----------------------------------- |
| `course.events` | `course.published` | Course status → published | Start RAG indexing workflow         |
| `course.events` | `course.archived`  | Course archived           | Delete RAG index                    |
| `course.events` | `content.updated`  | Lesson content changed    | Mark index as stale, queue re-index |

#### Events Produced by AI Service

| Topic       | Event               | Trigger                     | Payload                                        |
| ----------- | ------------------- | --------------------------- | ---------------------------------------------- |
| `ai.events` | `quiz.generated`    | Quiz generation complete    | `{course_id, module_id, version, timestamp}`   |
| `ai.events` | `summary.generated` | Summary generation complete | `{course_id, module_id, version, timestamp}`   |
| `ai.events` | `rag.indexed`       | RAG indexing complete       | `{course_id, status, chunks_count, timestamp}` |
| `ai.events` | `rag.failed`        | RAG indexing failed         | `{course_id, error, timestamp}`                |

> **Note:** The `ai.events` topic must be added to both the shared library (`shared/kafka/topics.py` as `Topics.AI = "ai.events"`) and the Kafka topic initialization in `docker-compose.yml`.

### Kafka Consumer Implementation

Uses the shared `EventConsumer` from the shared library for consistent event handling across services.

```python
# services/ai-service/src/ai_service/kafka/consumer.py

from shared.kafka.consumer import EventConsumer
from shared.kafka.topics import Topics
from shared.schemas.envelope import EventEnvelope

class AIServiceKafkaConsumer:
    def __init__(self, bootstrap_servers: str, schema_registry_url: str):
        self.consumer = EventConsumer(
            bootstrap_servers=bootstrap_servers,
            group_id="ai-service-consumer",
            topics=[Topics.COURSE],  # Listens to course.events topic
            schema_registry_url=schema_registry_url,
        )

    async def start(self):
        await self.consumer.start(handler=self.handle_message)

    async def handle_message(self, envelope: EventEnvelope):
        event_type = envelope.event_type
        payload = envelope.payload

        if event_type == "course.published":
            course_id = payload["course_id"]
            await self.trigger_rag_indexing(course_id)

        elif event_type == "course.archived":
            course_id = payload["course_id"]
            await self.delete_rag_index(course_id)

        elif event_type == "content.updated":
            course_id = payload["course_id"]
            await self.mark_index_stale(course_id)

    async def trigger_rag_indexing(self, course_id: int):
        """Start RAG indexing workflow."""
        from services.rag_indexer import RAGIndexer
        indexer = RAGIndexer()
        await indexer.index_course(course_id)

    async def delete_rag_index(self, course_id: int):
        """Delete all embeddings for a course."""
        from services.rag_indexer import RAGIndexer
        indexer = RAGIndexer()
        await indexer.delete_course_index(course_id)

    async def mark_index_stale(self, course_id: int):
        """Mark course index as needing re-indexing."""
        # Update status in PostgreSQL
        pass
```

### Integration Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                         EVENT-DRIVEN RAG INDEXING FLOW                                   │
└─────────────────────────────────────────────────────────────────────────────────────────┘

  Course Service                Kafka                    AI Service               Qdrant
       │                          │                          │                      │
       │  course.published        │                          │                      │
       ├─────────────────────────►│                          │                      │
       │                          │  Consume event           │                      │
       │                          ├─────────────────────────►│                      │
       │                          │                          │                      │
       │                          │                          │  1. Update status   │
       │                          │                          │     'indexing'       │
       │                          │                          │                      │
       │                          │                          │  2. Fetch content   │
       │◄─────────────────────────┼──────────────────────────┤     from MongoDB    │
       │  (HTTP: GET /content)    │                          │                      │
       ├─────────────────────────►│                          │                      │
       │                          │                          │                      │
       │                          │                          │  3. Parse & chunk   │
       │                          │                          │                      │
       │                          │                          │  4. Generate        │
       │                          │                          │     embeddings      │
       │                          │                          │                      │
       │                          │                          │  5. Upsert to       │
       │                          │                          ├─────────────────────►│
       │                          │                          │     Qdrant          │
       │                          │                          │                      │
       │                          │  rag.indexed             │  6. Update status   │
       │                          │◄─────────────────────────┤     'indexed'       │
       │                          │                          │                      │
 Notification                     │                          │                      │
  Service◄────────────────────────┤                          │                      │
       │  (notify teacher)        │                          │                      │
       │                          │                          │                      │
```

---

## 10. Infrastructure Setup

### Docker Compose Addition

Add these services to your `docker-compose.yml`:

```yaml
# ═══════════════════════════════════════════════════════════════
#  AI SERVICE INFRASTRUCTURE
# ═══════════════════════════════════════════════════════════════

  # Vector Database for RAG
  qdrant:
    image: qdrant/qdrant:v1.12.1
    container_name: smartcourse-qdrant
    ports:
      - "6333:6333"
      - "6334:6334"   # gRPC port
    volumes:
      - qdrant_data:/qdrant/storage
    environment:
      - QDRANT__SERVICE__GRPC_PORT=6334
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/health"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - smartcourse-network

  # AI Service
  ai-service:
    build:
      context: .
      dockerfile: services/ai-service/Dockerfile
    container_name: smartcourse-ai-service
    # No ports exposed to host — only accessible through API Gateway
    environment:
      # Service
      - SERVICE_NAME=ai-service
      - SERVICE_PORT=8009
      - LOG_LEVEL=INFO

      # OpenAI
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - OPENAI_MODEL=gpt-4o-mini
      - OPENAI_EMBEDDING_MODEL=text-embedding-3-small

      # Databases
      - DATABASE_URL=postgresql://${POSTGRES_USER:-smartcourse}:${POSTGRES_PASSWORD:-smartcourse_secret}@postgres:5432/${AI_DB:-smartcourse_ai}
      - MONGODB_URL=mongodb://${MONGO_USER:-smartcourse}:${MONGO_PASSWORD:-smartcourse_secret}@mongodb:27017/${MONGO_DB:-smartcourse}?authSource=admin
      - MONGODB_DB_NAME=${MONGO_DB:-smartcourse}
      - QDRANT_URL=http://qdrant:6333

      # Kafka
      - KAFKA_BOOTSTRAP_SERVERS=${KAFKA_BOOTSTRAP_SERVERS:-kafka:29092}
      - SCHEMA_REGISTRY_URL=${SCHEMA_REGISTRY_URL:-http://schema-registry:8081}

      # Service URLs (for HTTP calls)
      - COURSE_SERVICE_URL=http://course-service:8002
      - USER_SERVICE_URL=http://user-service:8001

      # Redis (for caching)
      - REDIS_URL=redis://:${REDIS_PASSWORD:-smartcourse_secret}@redis:6379/3

    depends_on:
      postgres:
        condition: service_healthy
      mongodb:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      kafka:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8009/health')"]
      interval: 15s
      timeout: 10s
      retries: 3
    networks:
      - smartcourse-network

# Add to volumes section
volumes:
  qdrant_data:

# Add to kafka-init topics
  kafka-init:
    command:
      - |
        # ... existing topics ...
        kafka-topics --bootstrap-server kafka:29092 --create --if-not-exists --topic ai.events --partitions 3 --replication-factor 1 &&
        echo 'All Kafka topics created.'
```

### Nginx Configuration Update

Add AI service routing to `services/api-gateway/nginx/conf.d/upstreams.conf`:

```nginx
# AI Service
upstream ai_service {
    server ai-service:8009;
    keepalive 32;
}
```

Add to your main nginx.conf or routes:

```nginx
# AI Service Routes
location /api/v1/ai/ {
    include /etc/nginx/conf.d/protected-snippet.conf;  # JWT verification

    proxy_pass http://ai_service/ai/;
    include /etc/nginx/conf.d/proxy-params.conf;

    # WebSocket support for streaming
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 86400;
}
```

### AI Service Dockerfile

```dockerfile
# services/ai-service/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY services/ai-service/pyproject.toml ./
COPY shared/ /app/shared/

RUN pip install --no-cache-dir -e .

# Copy application code
COPY services/ai-service/src/ ./src/

# Set Python path
ENV PYTHONPATH=/app/src

EXPOSE 8009

CMD ["uvicorn", "ai_service.main:app", "--host", "0.0.0.0", "--port", "8009"]
```

---

## 11. Implementation Plan

### Phase 1: Foundation (Days 1-2)

| Task | Description                           | Files to Create                           |
| ---- | ------------------------------------- | ----------------------------------------- |
| 1.1  | Create AI service directory structure | `services/ai-service/`                    |
| 1.2  | Setup FastAPI application             | `main.py`, `config.py`                    |
| 1.3  | Add Docker configuration              | `Dockerfile`, update `docker-compose.yml` |
| 1.4  | Setup Qdrant vector database          | Docker service, health check              |
| 1.5  | Create database models                | `models/`, alembic migrations             |
| 1.6  | Implement health endpoint             | `api/health.py`                           |

### Phase 2: Quiz & Summary Generation (Days 3-5)

| Task | Description                       | Files to Create               |
| ---- | --------------------------------- | ----------------------------- |
| 2.1  | Content fetcher service           | `services/content_fetcher.py` |
| 2.2  | PDF & transcript parsers          | `tools/content_parser.py`     |
| 2.3  | Quiz generation LangGraph agent   | `agents/quiz_generator.py`    |
| 2.4  | Summary generation agent          | `agents/summary_generator.py` |
| 2.5  | MongoDB repository for AI content | `repositories/ai_content.py`  |
| 2.6  | Generation API endpoints          | `api/generation.py`           |
| 2.7  | Teacher edit functionality        | Update endpoints              |

### Phase 3: RAG Infrastructure (Days 6-8)

| Task | Description               | Files to Create              |
| ---- | ------------------------- | ---------------------------- |
| 3.1  | Embedding service         | `rag/embeddings.py`          |
| 3.2  | Qdrant repository         | `rag/vector_store.py`        |
| 3.3  | RAG indexer service       | `rag/indexer.py`             |
| 3.4  | Chunking utilities        | `rag/chunker.py`             |
| 3.5  | Kafka consumer for events | `kafka/consumer.py`          |
| 3.6  | RAG status tracking       | `repositories/rag_status.py` |

### Phase 4: AI Tutor (Days 9-12)

| Task | Description              | Files to Create          |
| ---- | ------------------------ | ------------------------ |
| 4.1  | RAG retriever service    | `rag/retriever.py`       |
| 4.2  | Tool definitions         | `tools/tutor_tools.py`   |
| 4.3  | AI Tutor LangGraph agent | `agents/tutor.py`        |
| 4.4  | Conversation memory      | `memory/conversation.py` |
| 4.5  | Chat API endpoint        | `api/chat.py`            |
| 4.6  | WebSocket streaming      | `api/websocket.py`       |
| 4.7  | Session management       | `services/session.py`    |

### Phase 5: Integration & Testing (Days 13-15)

| Task | Description                  |
| ---- | ---------------------------- |
| 5.1  | Kafka producer for AI events |
| 5.2  | Integration with API Gateway |
| 5.3  | End-to-end testing           |
| 5.4  | Error handling & fallbacks   |
| 5.5  | Documentation                |

---

## 12. Best Practices & Production Checklist

### LangGraph Best Practices

```python
# 1. Always use typed state
class AgentState(TypedDict):
    messages: list
    context: dict
    # ... be explicit about state shape

# 2. Handle errors gracefully
async def safe_tool_execution(state):
    try:
        result = await execute_tool(state)
        return {"result": result, "error": None}
    except Exception as e:
        return {"result": None, "error": str(e)}

# 3. Use checkpointing for long conversations
checkpointer = PostgresSaver.from_conn_string(DATABASE_URL)
graph = create_graph().compile(checkpointer=checkpointer)

# 4. Set reasonable timeouts
llm = ChatOpenAI(model="gpt-4o-mini", timeout=30, max_retries=2)

# 5. Log every step for debugging
import logging
logger = logging.getLogger("langgraph")
logger.setLevel(logging.DEBUG)
```

### RAG Best Practices

```python
# 1. Optimal chunk size for educational content
CHUNK_SIZE = 512  # tokens
CHUNK_OVERLAP = 50  # ~10% overlap

# 2. Use metadata filtering
results = qdrant.search(
    collection="course_embeddings",
    query_vector=embedding,
    query_filter=Filter(must=[
        FieldCondition(key="course_id", match=MatchValue(value=course_id))
    ]),
    limit=5
)

# 3. Rerank results if needed
from sentence_transformers import CrossEncoder
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

# 4. Include source citations
context = "\n\n".join([
    f"[Source: {r.payload['metadata']['lesson_title']}]\n{r.payload['text']}"
    for r in results
])

# 5. Handle empty results gracefully
if not results:
    return "I couldn't find relevant information in the course materials."
```

### Production Checklist

- [ ] **Security**
  - [ ] JWT authentication on all endpoints
  - [ ] Rate limiting per user (e.g., 50 requests/minute)
  - [ ] Input sanitization before LLM calls
  - [ ] Content safety filter on outputs

- [ ] **Reliability**
  - [ ] Circuit breaker for OpenAI API calls
  - [ ] Fallback responses when LLM is unavailable
  - [ ] Retry logic with exponential backoff
  - [ ] Request timeout handling

- [ ] **Observability**
  - [ ] Structured logging (JSON format)
  - [ ] OpenTelemetry tracing
  - [ ] Token usage tracking
  - [ ] Latency metrics per endpoint

- [ ] **Cost Management**
  - [ ] Token counting before LLM calls
  - [ ] Daily/monthly usage limits
  - [ ] Caching for repeated queries
  - [ ] Use cheaper models where appropriate

- [ ] **Testing**
  - [ ] Unit tests for content parsing
  - [ ] Integration tests for RAG pipeline
  - [ ] Agent evaluation with test questions
  - [ ] Load testing for concurrent users

---

## Directory Structure

```
services/ai-service/
├── Dockerfile
├── pyproject.toml
├── alembic.ini
└── src/
    └── ai_service/
        ├── __init__.py
        ├── main.py                    # FastAPI app entry
        ├── config.py                  # Settings (Pydantic)
        │
        ├── api/
        │   ├── __init__.py
        │   ├── generation.py          # Quiz/Summary endpoints
        │   ├── chat.py                # AI Tutor endpoints
        │   ├── indexing.py            # RAG index endpoints
        │   └── websocket.py           # WebSocket streaming
        │
        ├── agents/
        │   ├── __init__.py
        │   ├── quiz_generator.py      # Quiz generation graph
        │   ├── summary_generator.py   # Summary generation graph
        │   └── tutor.py               # AI Tutor graph
        │
        ├── tools/
        │   ├── __init__.py
        │   ├── content_parser.py      # PDF, transcript parsing
        │   └── tutor_tools.py         # RAG search, progress tools
        │
        ├── rag/
        │   ├── __init__.py
        │   ├── embeddings.py          # OpenAI embedding wrapper
        │   ├── chunker.py             # Text chunking utilities
        │   ├── indexer.py             # RAG indexing service
        │   ├── retriever.py           # Qdrant search wrapper
        │   └── vector_store.py        # Qdrant client wrapper
        │
        ├── services/
        │   ├── __init__.py
        │   ├── content_fetcher.py     # Fetch from course-service
        │   └── session.py             # Conversation session mgmt
        │
        ├── repositories/
        │   ├── __init__.py
        │   ├── ai_content.py          # MongoDB: AI generated content
        │   ├── conversation.py        # PostgreSQL: Chat history
        │   └── rag_status.py          # PostgreSQL: Index status
        │
        ├── models/
        │   ├── __init__.py
        │   └── conversation.py        # SQLAlchemy models
        │
        ├── schemas/
        │   ├── __init__.py
        │   ├── generation.py          # Pydantic: Quiz/Summary
        │   └── chat.py                # Pydantic: Chat messages
        │
        ├── kafka/
        │   ├── __init__.py
        │   ├── consumer.py            # Consume course.events
        │   └── producer.py            # Produce ai.events
        │
        └── alembic/
            ├── env.py
            └── versions/
```

---

## Environment Variables

```bash
# .env additions for AI Service

# OpenAI
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# AI Service Database (separate DB for AI data)
AI_DB=smartcourse_ai

# Qdrant
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=course_embeddings

# RAG Settings
RAG_CHUNK_SIZE=512
RAG_CHUNK_OVERLAP=50
RAG_TOP_K=5

# Rate Limiting
AI_RATE_LIMIT_PER_MINUTE=50
AI_MAX_TOKENS_PER_REQUEST=4000
```

---

## Quick Start Commands

```bash
# 1. Start infrastructure (including new Qdrant)
docker-compose up -d qdrant

# 2. Create AI service database
docker exec -it smartcourse-postgres psql -U smartcourse -c "CREATE DATABASE smartcourse_ai;"

# 3. Build and start AI service
docker-compose build ai-service
docker-compose up -d ai-service

# 4. Run migrations
docker exec -it smartcourse-ai-service alembic upgrade head

# 5. Verify health
curl http://localhost:8000/api/v1/ai/health

# 6. Test quiz generation (with valid JWT)
curl -X POST http://localhost:8000/api/v1/ai/generate/quiz/1/mod_abc123 \
  -H "Authorization: Bearer <teacher_jwt>" \
  -H "Content-Type: application/json" \
  -d '{"num_questions": 5}'

# 7. Test AI Tutor (with valid JWT)
curl -X POST http://localhost:8000/api/v1/ai/tutor/chat \
  -H "Authorization: Bearer <student_jwt>" \
  -H "Content-Type: application/json" \
  -d '{"content": "What is recursion?", "course_id": 1}'
```

---

## Summary

This Week 3 implementation adds an AI Microservice with two main capabilities:

1. **Quiz & Summary Generation** - LangGraph agents that parse course content (text, PDF, transcripts) and generate educational quizzes and summaries for teachers

2. **AI Tutor** - RAG-powered conversational agent that helps students learn by answering questions based on enrolled course content

Key architectural decisions:

- **LangGraph** for stateful, production-ready AI agents
- **Qdrant** for vector storage (better than pgvector for dedicated workloads)
- **MongoDB** for AI-generated content (flexible schema, collocated with course content)
- **PostgreSQL** for structured data (conversations, audit trails)
- **Kafka** for event-driven RAG indexing on course publish

The service integrates with existing infrastructure via:

- Kafka events (`course.published` triggers RAG indexing)
- API Gateway (JWT-protected endpoints)
- Course Service (fetch content, progress)

---

_Created: February 26, 2026_
