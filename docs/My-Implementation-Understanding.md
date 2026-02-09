# SmartCourse: My Implementation Understanding & Approach

**Date:** February 9, 2026  
**Project:** SmartCourse - Intelligent Learning Management Platform  
**Timeline:** 4 Weeks

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture Understanding](#architecture-understanding)
3. [Technology Stack Rationale](#technology-stack-rationale)
4. [Database Design Strategy](#database-design-strategy)
5. [Microservices Breakdown](#microservices-breakdown)
6. [Implementation Timeline](#implementation-timeline)
7. [Key Workflows](#key-workflows)
8. [Monitoring & Observability](#monitoring--observability)
9. [Critical Concepts Explained](#critical-concepts-explained)
10. [Common Questions Answered](#common-questions-answered)

---

## Project Overview

SmartCourse is a next-generation learning management system that provides:

- **Course lifecycle management** (authoring, publishing, updating)
- **Student enrollment and progress tracking**
- **AI-powered learning assistance** (Q&A, content enhancement)
- **Real-time analytics and reporting**
- **Event-driven, scalable architecture**

### Core Business Requirements

- Instructors can create, publish, and manage courses
- Students can discover, enroll in, and complete courses
- System tracks progress and generates analytics
- AI assistant provides contextual help and content generation
- Platform must handle high traffic with reliable background processing

---

## Architecture Understanding

### High-Level Architecture

```
                    API Gateway (FastAPI)
                            |
        +-------------------+-------------------+
        |                   |                   |
   User Service      Course Service     Enrollment Service
        |                   |                   |
        +-------------------+-------------------+
                            |
        +-------------------+-------------------+
        |                   |                   |
  Progress Service   Notification Service   AI Assistant
                            |
                    Content Service
                            |
        +-------------------+-------------------+
        |                   |                   |
   PostgreSQL          MongoDB          Redis Cache
        |                   |                   |
   Kafka Events      RabbitMQ Tasks    Vector DB (Qdrant)
        |
   Temporal Workflows
```

### Communication Patterns

- **Synchronous (REST):** Client → API Gateway → Services
- **Asynchronous (Kafka):** Services publish events, others consume
- **Background Tasks (RabbitMQ + Celery):** Email, file processing
- **Workflows (Temporal):** Multi-step orchestration

---

## Technology Stack Rationale

### Why Two Databases? PostgreSQL + MongoDB

**PostgreSQL (Relational Database):**

- **Purpose:** Store structured, transactional data requiring ACID guarantees
- **Use Cases:**
  - User accounts (prevent duplicate emails)
  - Course metadata (title, instructor, price)
  - Enrollments (prevent duplicate enrollments, enforce constraints)
  - Progress tracking (query completion rates)
- **Why:** Strong consistency, relationships via foreign keys, complex queries with JOINs

**MongoDB (NoSQL Document Database):**

- **Purpose:** Store flexible, nested content with varying schemas
- **Use Cases:**
  - Course content (modules with videos, text, quizzes, PDFs)
  - Content chunks for AI processing
  - Chat conversation history
- **Why:** Flexible schema (each course can have different structure), easy nested data retrieval, high write throughput

**Analogy:** PostgreSQL is the "bookkeeper" (precise, structured), MongoDB is the "content library" (flexible, dynamic).

---

### Why RabbitMQ AND Redis?

**RabbitMQ (Message Queue):**

- **Purpose:** Queue background tasks for asynchronous processing
- **Use Cases:**
  - Send enrollment emails (don't block API response)
  - Process file uploads
  - Generate reports
- **How:** Celery workers consume tasks from RabbitMQ queues
- **Benefit:** API responds instantly, work happens in background

**Redis (In-Memory Cache):**

- **Purpose:** Fast caching and temporary data storage
- **Use Cases:**
  - Cache course data (avoid repeated DB queries)
  - Session tokens
  - Rate limiting (track API calls per user)
  - Quick lookups (microsecond response times)
- **Benefit:** Reduce database load, ultra-fast reads

**Key Difference:**

- RabbitMQ = "Do this work later" (task queue)
- Redis = "Remember this quickly" (cache + fast storage)

---

### Why Kafka?

**Apache Kafka (Event Streaming Platform):**

- **Purpose:** Event bus for microservices communication
- **Use Cases:**
  - `course.published` event → Content service processes, Analytics updates
  - `enrollment.created` event → Progress service initializes, Notification sends email
  - `progress.updated` event → Analytics tracks, Gamification updates
- **Benefits:**
  - Services are decoupled (don't need to know about each other)
  - Multiple services can react to same event
  - Event replay capability (audit, debugging)
  - If one service is down, others continue working

**Example Flow:**

```python
# Enrollment Service publishes
kafka.publish("enrollment.created", {
    "user_id": 123,
    "course_id": 456
})

# Multiple services react independently
Progress Service → Initialize progress
Notification Service → Send welcome email
Analytics Service → Update enrollment count
```

---

### Why Temporal?

**Temporal (Workflow Orchestration):**

- **Purpose:** Make multi-step processes reliable and recoverable
- **Use Cases:**
  - **Course Publishing Workflow:** Validate → Extract content → Generate embeddings → Index → Mark ready
  - **Enrollment Workflow:** Create enrollment → Initialize progress → Send email → Update analytics
- **Benefits:**
  - Automatic retries on failure
  - State persistence (survives server crashes)
  - Resumes from last completed step
  - Tracks workflow status and history
  - Handles timeouts and compensations

**Without Temporal:**
If step 3 of 5 fails, we manually track which steps completed, handle retries, manage state - nightmare!

**With Temporal:**
It automatically handles retries, resumes after crashes, tracks progress. We just define the workflow.

**Important:** Temporal is NOT about AI - it's about making ANY multi-step process reliable (course creation, enrollment, payment processing, etc.)

**Temporal Architecture (3 Components):**

1. **Temporal Server** (Infrastructure - separate container like PostgreSQL)
   - Stores workflow state
   - Manages task queues
   - Handles retries and timeouts
   - Runs independently in Docker

2. **Temporal Client** (In your microservices)
   - Used to START workflows
   - Used to QUERY workflow status
   - Example: Course Service starts a publishing workflow

3. **Temporal Worker** (Separate container/process)
   - EXECUTES workflows and activities
   - Listens to task queues
   - Calls your microservices via HTTP to perform actual work
   - Separate from your microservices

**Key Point:** Your microservices don't execute workflows directly. They start workflows via the Temporal Client, and Temporal Workers execute them.

---

### Why Docker Compose?

**Docker Compose:**

- **Purpose:** Run all infrastructure services locally with one command
- **Services in Compose:**
  - PostgreSQL
  - MongoDB
  - Redis
  - Kafka + Zookeeper
  - RabbitMQ
  - Temporal
  - Qdrant (Vector DB)
- **Benefits:**
  - One command to start: `docker-compose up`
  - Isolated environment (doesn't affect Mac system)
  - Same setup for all developers
  - Easy to share and replicate

---

## Database Design Strategy

### PostgreSQL Tables (Structured Data)

#### 1. users

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50), -- 'student', 'instructor', 'admin'
    password_hash VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### 2. courses

```sql
CREATE TABLE courses (
    id SERIAL PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    instructor_id INTEGER REFERENCES users(id),
    status VARCHAR(50), -- 'draft', 'published', 'archived'
    price DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### 3. enrollments

```sql
CREATE TABLE enrollments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    course_id INTEGER REFERENCES courses(id),
    status VARCHAR(50), -- 'active', 'completed', 'dropped'
    enrolled_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, course_id) -- Prevent duplicate enrollments
);
```

#### 4. progress

```sql
CREATE TABLE progress (
    id SERIAL PRIMARY KEY,
    enrollment_id INTEGER REFERENCES enrollments(id),
    lesson_id VARCHAR(100), -- References MongoDB lesson
    status VARCHAR(50), -- 'not_started', 'in_progress', 'completed'
    completed_at TIMESTAMP,
    quiz_score INTEGER,
    UNIQUE(enrollment_id, lesson_id)
);
```

---

### MongoDB Collections (Flexible Content)

#### 1. course_contents

```json
{
  "_id": "course_123",
  "course_id": 123,
  "modules": [
    {
      "id": "module_1",
      "title": "Introduction to Python",
      "order": 1,
      "lessons": [
        {
          "id": "lesson_1_1",
          "title": "Variables and Data Types",
          "type": "video",
          "content": {
            "video_url": "s3://bucket/lesson1.mp4",
            "duration_seconds": 600,
            "transcript": "..."
          },
          "order": 1
        },
        {
          "id": "lesson_1_2",
          "title": "Quiz: Python Basics",
          "type": "quiz",
          "content": {
            "questions": [...]
          },
          "order": 2
        }
      ]
    }
  ]
}
```

**Why MongoDB for content:** Each course has different structure (videos, PDFs, quizzes), easy to retrieve entire course in one query, flexible schema.

#### 2. content_chunks (for AI/RAG)

```json
{
  "_id": "chunk_456",
  "course_id": 123,
  "lesson_id": "lesson_1_1",
  "chunk_text": "Python is a high-level programming language...",
  "chunk_index": 0,
  "metadata": {
    "source": "lesson",
    "type": "video_transcript"
  }
}
```

---

### Database Decision Guide

| Data Type         | Database   | Reason                              |
| ----------------- | ---------- | ----------------------------------- |
| User accounts     | PostgreSQL | Unique constraints, relationships   |
| Course metadata   | PostgreSQL | Structured, needs JOINs             |
| Enrollments       | PostgreSQL | Prevent duplicates, ACID            |
| Progress tracking | PostgreSQL | Aggregate queries (completion rate) |
| Course content    | MongoDB    | Flexible nested structure           |
| Content chunks    | MongoDB    | Many small documents, high writes   |
| Chat history      | MongoDB    | Growing message arrays              |

---

## Microservices Breakdown

### Core Services

**1. User Service**

- User registration, login, JWT authentication
- Role management (student, instructor, admin)
- PostgreSQL: `users` table

**2. Course Service**

- Course CRUD operations
- Publish course (triggers Temporal workflow)
- PostgreSQL: `courses` table
- MongoDB: `course_contents` collection

**3. Enrollment Service**

- Handle student enrollments
- Prevent duplicate enrollments
- Publish `enrollment.created` event to Kafka
- PostgreSQL: `enrollments` table

**4. Progress Service**

- Track lesson completions
- Calculate completion percentages
- PostgreSQL: `progress` table

**5. Notification Service**

- Listen to events via Kafka
- Queue email tasks in RabbitMQ
- Send emails, SMS, push notifications

### Advanced Services (Week 4)

**6. Content Service**

- Extract text from videos/PDFs
- Generate embeddings (via OpenAI API)
- Store in Vector DB (Qdrant)
- Update search index

**7. AI Assistant Service**

- Implement RAG (Retrieval Augmented Generation)
- Context-aware Q&A
- Use LangChain/LangGraph
- Connect to LLM providers (OpenAI, Anthropic)

**8. Analytics Service**

- Consume events from Kafka
- Generate reports and dashboards
- Track enrollments, completions, popular courses

---

## Implementation Timeline

### Week 1: Foundation (Modular Monolith)

**Goal:** Build core CRUD operations with solid database foundation

**Deliverables:**

- Single FastAPI application with modular structure
- User registration and JWT authentication
- Course CRUD (create, read, update, delete)
- Enrollment endpoints
- Progress tracking endpoints
- Docker Compose with PostgreSQL, MongoDB, Redis
- Database migrations with Alembic

**Project Structure:**

```
smart-course/
├── main.py                  # FastAPI app
├── models/                  # SQLAlchemy models
│   ├── user.py
│   ├── course.py
│   ├── enrollment.py
│   └── progress.py
├── routers/                 # API routes
│   ├── auth.py
│   ├── courses.py
│   ├── enrollments.py
│   └── progress.py
├── services/                # Business logic
├── schemas/                 # Pydantic models
└── docker-compose.yml
```

**Endpoints:**

```
POST /auth/register
POST /auth/login
GET  /courses
POST /courses
GET  /courses/{id}
POST /courses/{id}/enroll
POST /progress/lessons/{id}/complete
GET  /progress/courses/{id}
```

**Why start as monolith?**

- Faster to develop and debug
- No network overhead
- Easy to split into microservices later
- Focus on business logic first

---

### Week 2: Event-Driven Architecture

**Goal:** Decouple services with Kafka and add background task processing

**Deliverables:**

- Split monolith into 5 microservices:
  - User Service
  - Course Service
  - Enrollment Service
  - Progress Service
  - Notification Service
- Add Kafka for event streaming
- Add RabbitMQ + Celery for background tasks
- Services communicate via events

**New in Docker Compose:**

- Kafka + Zookeeper
- RabbitMQ

**Key Events:**

- `course.published` → Content service reacts, Analytics updates
- `enrollment.created` → Progress initializes, Notification sends email
- `progress.updated` → Analytics tracks

**Example Flow:**

```python
# Enrollment Service
@app.post("/courses/{course_id}/enroll")
async def enroll(course_id: int, user_id: int):
    enrollment = create_enrollment(user_id, course_id)

    # Publish event to Kafka
    await kafka.publish("enrollment.created", {
        "enrollment_id": enrollment.id,
        "user_id": user_id,
        "course_id": course_id
    })

    return {"enrollment_id": enrollment.id}

# Notification Service (separate process)
@kafka.subscribe("enrollment.created")
async def on_enrollment(event):
    # Queue email task in RabbitMQ
    send_welcome_email.delay(event['user_id'], event['course_id'])
```

**Benefits Achieved:**

- API responds instantly (doesn't wait for email)
- Services are independent (can deploy separately)
- Easy to add new services that react to events

---

### Week 3: Workflow Orchestration

**Goal:** Add Temporal for reliable multi-step processes

**Deliverables:**

- Add Temporal server to Docker Compose
- Implement Course Publishing Workflow
- Implement Enrollment Workflow
- Workflow status tracking API

**Workflows:**

**1. Course Publishing Workflow**

```python
@workflow.defn
class CoursePublishingWorkflow:
    async def run(self, course_id: str):
        # Step 1: Validate course
        await workflow.execute_activity(validate_course, course_id)

        # Step 2: Save content to MongoDB
        await workflow.execute_activity(save_content, course_id)

        # Step 3: Upload files to S3
        await workflow.execute_activity(upload_files, course_id)

        # Step 4: Update search index
        await workflow.execute_activity(index_course, course_id)

        # Step 5: Mark as published
        await workflow.execute_activity(mark_published, course_id)
```

**2. Enrollment Workflow**

```python
@workflow.defn
class EnrollmentWorkflow:
    async def run(self, user_id: str, course_id: str):
        # Step 1: Create enrollment
        enrollment = await workflow.execute_activity(
            create_enrollment, user_id, course_id
        )

        # Step 2: Initialize progress
        await workflow.execute_activity(
            initialize_progress, enrollment.id
        )

        # Step 3: Queue welcome email
        await workflow.execute_activity(
            queue_email, user_id, course_id
        )

        # Step 4: Update analytics
        await workflow.execute_activity(
            update_analytics, course_id
        )
```

**Benefits:**

- Automatic retries on failure
- Survives server crashes (resumes from last step)
- Track workflow status in real-time
- Easy debugging (see exactly which step failed)

---

### Week 4: AI Features

**Goal:** Add intelligent features with RAG and embeddings

**Deliverables:**

- Content Service (extract text, generate embeddings)
- AI Assistant Service (RAG-based Q&A)
- Vector Database (Qdrant)
- Content Processing Workflow (with Temporal)

**New Infrastructure:**

- Qdrant (Vector Database)
- OpenAI API integration
- LangChain/LangGraph

**Content Processing Workflow:**

```python
@workflow.defn
class ContentProcessingWorkflow:
    async def run(self, course_id: str):
        # Step 1: Extract text from course content
        text_chunks = await workflow.execute_activity(
            extract_text, course_id
        )

        # Step 2: Generate embeddings
        embeddings = await workflow.execute_activity(
            generate_embeddings, text_chunks
        )

        # Step 3: Store in Qdrant
        await workflow.execute_activity(
            store_embeddings, course_id, embeddings
        )

        # Step 4: Update course status
        await workflow.execute_activity(
            mark_ai_ready, course_id
        )
```

**AI Assistant RAG Pipeline:**

```python
# Student asks: "What is a variable in Python?"

# 1. Generate query embedding
query_embedding = openai.embeddings.create(
    model="text-embedding-3-small",
    input="What is a variable in Python?"
)

# 2. Search similar chunks in Qdrant
results = qdrant_client.search(
    collection_name="course_content",
    query_vector=query_embedding.data[0].embedding,
    limit=5
)

# 3. Build context from retrieved chunks
context = "\n".join([r.payload['text'] for r in results])

# 4. Generate answer with LLM
prompt = f"""Answer based on this context:
{context}

Question: What is a variable in Python?
Answer:"""

answer = openai.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": prompt}]
)
```

---

## Key Workflows

### Workflow 1: Student Enrolls in Course

**Full Flow:**

1. Student clicks "Enroll" → Frontend calls API Gateway
2. API Gateway → Enrollment Service (FastAPI)
3. Enrollment Service:
   - Check prerequisites (PostgreSQL query)
   - Create enrollment record (PostgreSQL transaction)
   - Publish `enrollment.created` event to Kafka
   - Start Temporal Enrollment Workflow
4. Temporal Workflow:
   - Initialize progress (calls Progress Service)
   - Queue welcome email (RabbitMQ task)
   - Update analytics (Kafka event)
5. Celery Worker picks up email task, sends email
6. Analytics Service consumes Kafka event, updates counters
7. Done! Student is enrolled

**If anything fails:**

- Temporal retries automatically
- If server crashes, resumes from last completed step
- Email gets retried up to 3 times

---

### Workflow 2: Instructor Publishes Course

**Full Flow:**

1. Instructor clicks "Publish" → Frontend calls API Gateway
2. API Gateway → Course Service
3. Course Service:
   - Start Temporal Course Publishing Workflow
   - Return workflow ID to frontend
4. Temporal Workflow (runs in background):
   - Validate course completeness
   - Save content to MongoDB
   - Upload assets to S3
   - Extract text from videos/PDFs (Content Service)
   - Generate embeddings (calls OpenAI API)
   - Store embeddings in Qdrant
   - Update search index (Elasticsearch/OpenSearch)
   - Mark course as "published" (PostgreSQL update)
   - Publish `course.published` event to Kafka
5. Frontend polls workflow status:
   - "Step 1/7: Validating..."
   - "Step 3/7: Uploading files..."
   - "Complete!"

**Benefits:**

- Long-running process (10+ minutes) doesn't block API
- Each step is retried on failure
- Instructor sees real-time progress
- If server crashes, resumes automatically

---

### Workflow 3: Student Asks AI Question

**Full Flow:**

1. Student types: "Explain decorators in Python"
2. Frontend → API Gateway → AI Assistant Service
3. AI Assistant:
   - Generate embedding for question
   - Search Qdrant for similar content chunks (top 5)
   - Build context from retrieved chunks
   - Send to OpenAI GPT-4 with context
   - Stream response back to frontend
4. Student sees answer typing in real-time

**RAG Benefits:**

- Answers are based on actual course content
- More accurate than generic ChatGPT
- Cites specific lessons/modules
- Prevents hallucinations (AI making things up)

---

## Monitoring & Observability

### Prometheus + Grafana Setup

**Prometheus (Metrics Collection):**

- Each FastAPI service exposes `/metrics` endpoint
- Prometheus scrapes metrics every 15 seconds
- Tracks:
  - API response times (P50, P95, P99)
  - Error rates
  - Request counts
  - Database query times
  - Kafka message lag
  - Celery queue lengths

**Grafana (Visualization):**

- Connects to Prometheus as data source
- Dashboards show:
  - Service health overview
  - API latency by endpoint
  - Error rates by service
  - System resource usage (CPU, memory)
  - Kafka throughput
  - Temporal workflow success/failure rates

**Metrics to Track:**

```python
# In FastAPI services
from prometheus_client import Counter, Histogram

request_count = Counter('http_requests_total', 'Total requests')
request_duration = Histogram('http_request_duration_seconds', 'Request duration')

@app.get("/courses")
async def get_courses():
    request_count.inc()
    with request_duration.time():
        # Handle request
        return courses
```

**Alerts:**

- API error rate > 5% → Alert on-call engineer
- Kafka consumer lag > 1000 messages → Scale consumers
- Database query time > 500ms → Investigate slow queries
- Temporal workflow failure rate > 10% → Check logs

---

## Background from JavaScript/TypeScript

As a developer with strong TypeScript background (Next.js, Nest.js, React Native), the transition to Python/FastAPI is straightforward:

### Familiar Concepts:

- **FastAPI ≈ Nest.js** (decorators, dependency injection, auto-generated docs)
- **Pydantic ≈ class-validator** (data validation)
- **SQLAlchemy ≈ TypeORM** (ORM, migrations)
- **async/await** (same syntax!)
- **Docker Compose** (same tool)

### New Concepts to Master:

- **Temporal** (no direct JS equivalent - workflow orchestration)
- **Vector Databases** (for AI/RAG - new paradigm)
- **Kafka** (similar to Node.js Kafka, different ecosystem)
- **Python type hints** (similar to TypeScript types)

---

## Key Takeaways

### Architecture Decisions:

✅ **PostgreSQL + MongoDB:** Structured data vs flexible content  
✅ **Kafka:** Event-driven microservices communication  
✅ **RabbitMQ:** Background task queue  
✅ **Redis:** Caching and fast lookups  
✅ **Temporal:** Reliable multi-step workflows  
✅ **Docker Compose:** Local infrastructure management  
✅ **Grafana + Prometheus:** Monitoring and observability

### Implementation Strategy:

✅ **Week 1:** Modular monolith (fast iteration, validate business logic)  
✅ **Week 2:** Split into microservices with event-driven architecture  
✅ **Week 3:** Add workflow orchestration for reliability  
✅ **Week 4:** Layer on AI features (RAG, embeddings)

### Success Criteria:

- Services are independent and resilient
- Multi-step processes survive failures
- APIs respond quickly (background tasks don't block)
- Easy to add new features (listen to events)
- Observable and debuggable (metrics, logs, tracing)
- AI features provide value (accurate, context-aware)

---

## Next Steps

1. **Set up development environment:**
   - Install Python 3.11+, Docker Desktop
   - Clone repository, set up virtual environment
   - Run `docker-compose up` to start infrastructure

2. **Week 1 implementation:**
   - Initialize FastAPI project
   - Set up PostgreSQL + Alembic migrations
   - Implement User and Course CRUD
   - Add JWT authentication

3. **Daily learning (2 hours):**
   - Practice SQLAlchemy, Beanie, Docker
   - Study Kafka, Celery concepts
   - Prepare for upcoming weeks

---

## Critical Concepts Explained

### ACID Transactions in SmartCourse

**ACID = Atomicity, Consistency, Isolation, Durability**

PostgreSQL provides ACID guarantees for critical operations that involve money, user data, or business-critical state.

#### What is ACID?

**A - Atomicity (All or Nothing)**

- Either the entire transaction succeeds, or nothing happens
- Example: Student enrollment requires creating enrollment record AND updating course count - both must succeed together

**C - Consistency (Rules Are Enforced)**

- Database enforces constraints at all times
- Example: UNIQUE constraint prevents duplicate enrollments automatically

**I - Isolation (Transactions Don't Interfere)**

- Concurrent transactions don't see each other's partial changes
- Example: Two students enrolling simultaneously in a limited-capacity course - only one gets the last spot

**D - Durability (Committed = Permanent)**

- Once committed, data survives crashes and power loss
- Example: After enrollment commits, even if server crashes 1 second later, enrollment is saved

#### ACID Example: Student Enrollment

```python
from sqlalchemy.orm import Session
from fastapi import HTTPException

def enroll_student(user_id: int, course_id: int, db: Session):
    try:
        # Start transaction (automatic with SQLAlchemy)

        # 1. Check if already enrolled (Consistency)
        existing = db.query(Enrollment).filter(
            Enrollment.user_id == user_id,
            Enrollment.course_id == course_id
        ).first()

        if existing:
            raise HTTPException(400, "Already enrolled")

        # 2. Check capacity with row lock (Isolation)
        course = db.query(Course).filter(
            Course.id == course_id
        ).with_for_update().first()  # Locks row until commit

        enrolled_count = db.query(Enrollment).filter(
            Enrollment.course_id == course_id
        ).count()

        if enrolled_count >= course.max_enrollments:
            raise HTTPException(400, "Course is full")

        # 3. Create enrollment (Atomicity)
        enrollment = Enrollment(
            user_id=user_id,
            course_id=course_id
        )
        db.add(enrollment)

        # 4. Commit (Durability)
        db.commit()

        return enrollment

    except Exception as e:
        # Atomicity: If anything fails, rollback everything
        db.rollback()
        raise
```

**What ACID guarantees:**

- **Atomicity:** If commit fails, no enrollment record is created
- **Consistency:** UNIQUE constraint prevents duplicate enrollments
- **Isolation:** Row lock prevents race condition (only one student gets last spot)
- **Durability:** Once committed, enrollment survives crashes

#### When to Use ACID (PostgreSQL)

**Critical Operations (MUST use PostgreSQL with ACID):**

1. ✅ Student enrollment - Prevent duplicates, enforce capacity
2. ✅ Payment processing - Money involved!
3. ✅ Progress updates - Points, completion tracking
4. ✅ User registration - Prevent duplicate emails
5. ✅ Course capacity management - Prevent overselling

**Non-Critical Operations (MongoDB is fine):**

1. ⚠️ Storing course content - Can retry, no financial impact
2. ⚠️ Logging events - Missing one log entry is okay
3. ⚠️ Chat history - Not mission-critical
4. ⚠️ Content chunks for AI - Can regenerate

---

### Database Connection Pattern

**One Database Server, Multiple Service Connections**

A common confusion: Do you create separate PostgreSQL/MongoDB instances for each microservice?

**Answer: NO!**

You have:

- **ONE PostgreSQL container** (shared by all services)
- **ONE MongoDB container** (shared by all services)
- **Each microservice has its own connection code**

```
┌─────────────────────────────────────────────────────────┐
│         PostgreSQL Server (ONE container)                │
│  Database: smartcourse                                   │
│  ├── users table                                         │
│  ├── courses table                                       │
│  ├── enrollments table                                   │
│  └── progress table                                      │
└─────────────────────────────────────────────────────────┘
         ▲              ▲              ▲              ▲
         │              │              │              │
    User Service   Course Service  Enrollment    Progress
                                   Service       Service
    (connects)     (connects)     (connects)    (connects)
```

**Each service has:**

- Its own connection code (copy-paste is fine)
- Its own connection pool (managed by SQLAlchemy)
- Access to the same database server

**This is DESIRED because:**

- ✅ Each service is independent (can be deployed separately)
- ✅ Each service manages its own connection pool
- ✅ Services don't share memory/state
- ✅ Easy to scale (add more service instances)

**Example:**

```python
# services/user-service/database.py
DATABASE_URL = "postgresql://postgres:password@postgres:5432/smartcourse"
engine = create_engine(DATABASE_URL)

# services/course-service/database.py
DATABASE_URL = "postgresql://postgres:password@postgres:5432/smartcourse"
engine = create_engine(DATABASE_URL)

# Both connect to SAME PostgreSQL server
```

---

### Infrastructure vs Microservices: Where Things Live

**Common Confusion:** Are Kafka, RabbitMQ, and Temporal part of my microservices?

**Answer: NO! They are separate infrastructure services.**

#### Three Layers

**Layer 1: Infrastructure Services** (Separate containers, shared by all)

- Kafka + Zookeeper (event streaming)
- RabbitMQ (message queue)
- Temporal Server (workflow engine)
- PostgreSQL (database)
- MongoDB (database)
- Redis (cache)
- Qdrant (vector DB)

**Layer 2: Your Microservices** (Your code, connects to infrastructure)

- User Service
- Course Service
- Enrollment Service
- Progress Service
- Notification Service
- Content Service
- AI Assistant Service
- Analytics Service

**Layer 3: Workers** (Background processors)

- Celery Workers (connect to RabbitMQ)
- Temporal Workers (connect to Temporal Server)

**Visual:**

```
┌─────────────────────────────────────────────────────────────┐
│                   INFRASTRUCTURE LAYER                       │
│  (Separate containers, like PostgreSQL)                      │
├─────────────────────────────────────────────────────────────┤
│  Kafka      RabbitMQ    Temporal    PostgreSQL    MongoDB   │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │ (Connect as clients)
                            │
┌─────────────────────────────────────────────────────────────┐
│                   MICROSERVICES LAYER                        │
│  (Your FastAPI apps, each in own container)                  │
├─────────────────────────────────────────────────────────────┤
│  User        Course       Enrollment      Progress           │
│  Service     Service      Service         Service            │
└─────────────────────────────────────────────────────────────┘
```

**How Services Use Infrastructure:**

```python
# In Course Service (microservice)
from aiokafka import AIOKafkaProducer  # Kafka client
from temporalio.client import Client   # Temporal client

# Connect to Kafka (infrastructure)
kafka_producer = AIOKafkaProducer(bootstrap_servers='kafka:9092')

# Connect to Temporal (infrastructure)
temporal_client = await Client.connect("temporal:7233")

# Course Service doesn't RUN Kafka or Temporal
# It CONNECTS to them (like connecting to PostgreSQL)
```

---

### Temporal: Where Activities Live and How They Work

**Common Confusion:** Where are the workflow activity functions?

**Answer: In the Temporal Worker container, NOT in your microservices!**

#### File Structure

```
workers/temporal-workers/
├── worker.py                        # Main worker process
├── workflows/
│   └── course_publish_workflow.py   # Workflow definitions
└── activities/
    └── course_activities.py         # ← ACTIVITIES ARE HERE
```

#### What Activities Do

**Activities are HTTP wrappers** that call your microservices:

```python
# workers/temporal-workers/activities/course_activities.py
from temporalio import activity
import httpx

@activity.defn
async def validate_course(course_id: int) -> bool:
    """Calls Course Service API to validate"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"http://course-service:8000/courses/{course_id}"
        )
        return response.status_code == 200

@activity.defn
async def mark_published(course_id: int) -> bool:
    """Calls Course Service API to mark as published"""
    async with httpx.AsyncClient() as client:
        response = await client.put(
            f"http://course-service:8000/courses/{course_id}/status",
            json={"status": "published"}
        )
        return response.status_code == 200
```

**Key Point:** Activities don't have business logic! They just call your microservices.

#### Where Business Logic Lives

**Real business logic stays in your microservices:**

```python
# services/course-service/routers/courses.py
@app.put("/courses/{course_id}/status")
async def update_status(course_id: int, status: str, db: Session = Depends(get_db)):
    # REAL BUSINESS LOGIC HERE
    course = db.query(Course).filter(Course.id == course_id).first()
    course.status = status
    db.commit()
    return {"status": "updated"}
```

#### The Flow

```
Temporal Workflow (in Worker)
  → Activity: mark_published()
    → HTTP Call: PUT http://course-service:8000/courses/123/status
      → Course Service (real logic executes here)
        → Updates PostgreSQL
        → Returns response
      ← Response
    ← Activity completes
  ← Workflow continues to next step
```

---

## Common Questions Answered

### Q: Do I create separate PostgreSQL instances for each microservice?

**A:** No! One PostgreSQL container, all services connect to it. Each service has its own connection code, but they all connect to the same database server.

### Q: Where does Kafka/RabbitMQ/Temporal code go?

**A:**

- **Kafka Client:** In each microservice that needs to publish/consume events
- **RabbitMQ (via Celery):** In each microservice that needs background tasks
- **Temporal Client:** In microservices that start workflows (Course Service, Enrollment Service)
- **Temporal Worker:** Separate container that executes workflows

### Q: How does Temporal talk to my services?

**A:**

1. Your service (Course Service) uses **Temporal Client** to START a workflow
2. **Temporal Server** adds workflow to task queue
3. **Temporal Worker** (separate container) picks up workflow
4. Worker executes activities, which are **HTTP calls to your microservices**
5. Your microservices execute the actual business logic

### Q: Where are Temporal workflow activities defined?

**A:** In the Temporal Worker project (`workers/temporal-workers/activities/`), not in your microservices. Activities are just HTTP wrappers that call your microservice APIs.

### Q: Why use PostgreSQL for some data and MongoDB for others?

**A:**

- **PostgreSQL:** For data that requires ACID transactions (enrollments, payments, user accounts)
- **MongoDB:** For flexible, nested content (course modules, lessons, chat history)
- **Rule:** If money or critical business logic is involved → PostgreSQL. If it's flexible content → MongoDB.

### Q: What's the difference between Kafka and RabbitMQ?

**A:**

- **Kafka:** Event streaming (broadcast events, multiple services listen)
  - Example: `enrollment.created` → Progress Service, Notification Service, Analytics all react
- **RabbitMQ:** Task queue (send task to one worker)
  - Example: "Send this email" → One Celery worker picks it up and sends email

### Q: When do I need ACID transactions?

**A:** For operations involving:

- Money (payments, refunds)
- User data (registration, authentication)
- Enrollments (prevent duplicates, enforce capacity)
- Progress tracking (points, completions)
- Any operation where partial completion would be incorrect

### Q: How do services communicate?

**A:**

- **Synchronous (REST):** API Gateway → Service (user waits for response)
- **Asynchronous (Kafka):** Service → Kafka → Other services (fire and forget)
- **Background (RabbitMQ):** Service → Queue → Worker (task processing)
- **Workflows (Temporal):** Service → Temporal → Worker → Services (orchestrated multi-step)

---

3. **Daily learning (2 hours):**
   - Practice SQLAlchemy, Beanie, Docker
   - Study Kafka, Celery concepts
   - Prepare for upcoming weeks

---

**End of Document**
