# SmartCourse - 4-Week Implementation Plan & Stack Guide

**Target Audience:** Developers transitioning from JavaScript (Next.js, Nest.js, React Native) to Python + GenAI  
**Timeline:** 4 Weeks  
**Goal:** Build production-ready SmartCourse platform while mastering Python, GenAI, and distributed systems

---

## Table of Contents

1. [Stack Overview & JS to Python Translation](#stack-overview--js-to-python-translation)
2. [Microservices Architecture & Flow](#microservices-architecture--flow)
3. [Week-by-Week Implementation Plan](#week-by-week-implementation-plan)
4. [Detailed Component Breakdown](#detailed-component-breakdown)
5. [Testing Strategy](#testing-strategy)
6. [Deployment & Monitoring](#deployment--monitoring)

---

## Stack Overview & JS to Python Translation

### Backend Framework: FastAPI vs Express/Nest.js

| Concept | JavaScript (Nest.js/Express) | Python (FastAPI) |
|---------|------------------------------|------------------|
| **Framework** | `@nestjs/core`, `express` | `fastapi` |
| **Routing** | `@Controller()`, `@Get()` | `@app.get()`, `@app.post()` |
| **Dependency Injection** | `@Injectable()`, providers | `Depends()` function |
| **Validation** | `class-validator`, DTOs | `pydantic` models |
| **Async/Await** | `async/await` (same!) | `async/await` (same!) |
| **Middleware** | `app.use()` | `app.middleware()` |
| **Documentation** | Swagger + decorators | Auto-generated OpenAPI |

**Example Comparison:**

```typescript
// Nest.js
@Controller('courses')
export class CoursesController {
  @Get(':id')
  async getCourse(@Param('id') id: string) {
    return this.coursesService.findOne(id);
  }
}
```

```python
# FastAPI
@app.get("/courses/{course_id}")
async def get_course(course_id: str, db: Session = Depends(get_db)):
    return await courses_service.find_one(course_id, db)
```

---

### Database Layer

#### 1. **PostgreSQL (Relational Data)**

**What it stores:** Structured data (users, courses, enrollments, progress)

**JS Equivalent:** Similar to using PostgreSQL with TypeORM or Prisma

**Python Tools:**
- **SQLAlchemy** (like TypeORM) - ORM for database operations
- **Alembic** (like TypeORM migrations) - Database migrations

```python
# SQLAlchemy Model (like TypeORM Entity)
from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Course(Base):
    __tablename__ = "courses"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String)
    instructor_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
```

---

#### 2. **NoSQL Database (MongoDB recommended)**

**What it stores:** Course content, flexible schemas, documents

**JS Equivalent:** MongoDB with Mongoose

**Python Tools:**
- **Motor** (async MongoDB driver)
- **PyMongo** (sync MongoDB driver)
- **Beanie** (ODM like Mongoose)

**Use Cases in SmartCourse:**
- Store course modules with nested structure
- Store learning materials (text, videos, files metadata)
- Store flexible course metadata

```python
# Beanie Document Model (like Mongoose Schema)
from beanie import Document
from pydantic import Field

class CourseContent(Document):
    course_id: str
    modules: List[Dict]
    materials: List[Dict]
    metadata: Dict = Field(default_factory=dict)
    
    class Settings:
        name = "course_contents"
```

---

#### 3. **Redis (Caching & Sessions)**

**What it stores:** Cache, session data, rate limiting, job queues

**JS Equivalent:** Same as in Node.js (redis/ioredis)

**Python Tools:**
- **redis-py** (standard Redis client)
- **aioredis** (async Redis)

**Use Cases:**
- Cache course data
- Session management
- Rate limiting API requests
- Pub/Sub for real-time features

```python
# Redis Usage
import redis.asyncio as redis

cache = redis.Redis(host='localhost', port=6379, decode_responses=True)

# Cache course data
await cache.setex(f"course:{course_id}", 3600, json.dumps(course_data))
cached = await cache.get(f"course:{course_id}")
```

---

#### 4. **Vector Database (Pinecone/Weaviate/Qdrant)**

**What it stores:** Embeddings for semantic search and RAG

**JS Equivalent:** New concept (not common in JS backend)

**Recommended:** **Qdrant** (open-source, Docker-friendly)

**Use Cases:**
- Store course content embeddings
- Semantic search for courses
- Contextual Q&A (RAG - Retrieval Augmented Generation)

```python
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance

# Create collection
client = QdrantClient(host="localhost", port=6333)
client.create_collection(
    collection_name="course_embeddings",
    vectors_config=VectorParams(size=1536, distance=Distance.COSINE)
)

# Store embeddings
client.upsert(
    collection_name="course_embeddings",
    points=[{
        "id": chunk_id,
        "vector": embedding_vector,
        "payload": {"text": chunk_text, "course_id": course_id}
    }]
)
```

---

### Message Queue & Event Streaming

#### 1. **RabbitMQ (Task Queue)**

**What it does:** Queue background tasks for workers

**JS Equivalent:** Bull/BullMQ with Redis

**Use Case:** Asynchronous task processing (sending emails, processing uploads)

```python
# With Celery
from celery import Celery

celery_app = Celery('smartcourse', broker='pyamqp://guest@localhost//')

@celery_app.task
def process_enrollment(enrollment_id):
    # Initialize progress
    # Update analytics
    # Send welcome email
    pass
```

---

#### 2. **Apache Kafka (Event Streaming)**

**What it does:** Event streaming for microservices communication

**JS Equivalent:** Kafka with kafkajs

**Use Case:** Event-driven architecture, real-time data pipelines

**Events in SmartCourse:**
- `course.published`
- `student.enrolled`
- `progress.updated`
- `content.processed`

```python
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
import json

# Producer
producer = AIOKafkaProducer(bootstrap_servers='localhost:9092')
await producer.start()
await producer.send_and_wait(
    "course.events",
    json.dumps({"event": "course.published", "course_id": course_id}).encode()
)

# Consumer
consumer = AIOKafkaConsumer(
    'course.events',
    bootstrap_servers='localhost:9092',
    group_id='analytics-service'
)
async for msg in consumer:
    event = json.loads(msg.value)
    # Process event
```

---

#### 3. **Celery Workers (Background Tasks)**

**What it does:** Distributed task queue for Python

**JS Equivalent:** Bull/BullMQ workers

**Use Cases:**
- Send emails
- Process file uploads
- Generate reports
- Extract content

```python
# celery_config.py
from celery import Celery

app = Celery('smartcourse',
             broker='amqp://guest@localhost//',
             backend='redis://localhost:6379/0')

# Task definition
@app.task(bind=True, max_retries=3)
def send_enrollment_email(self, user_email, course_title):
    try:
        # Send email logic
        pass
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)
```

---

### Workflow Orchestration: Temporal

**What it is:** Workflow orchestration engine for complex, long-running processes

**JS Equivalent:** No direct equivalent (new paradigm)

**Why use it:** 
- Reliable execution of multi-step workflows
- Automatic retries and error handling
- Saga pattern for distributed transactions
- State management for long-running processes

**SmartCourse Workflows:**

1. **Course Publishing Workflow**
   - Extract content
   - Generate embeddings
   - Index in vector DB
   - Update search index
   - Mark as published

2. **Enrollment Workflow**
   - Validate enrollment
   - Create enrollment record
   - Initialize progress
   - Update analytics
   - Send notifications

```python
from temporalio import workflow, activity
from datetime import timedelta

@workflow.defn
class CoursePublishingWorkflow:
    @workflow.run
    async def run(self, course_id: str) -> str:
        # Step 1: Extract content
        content = await workflow.execute_activity(
            extract_course_content,
            course_id,
            start_to_close_timeout=timedelta(minutes=5)
        )
        
        # Step 2: Generate embeddings
        embeddings = await workflow.execute_activity(
            generate_embeddings,
            content,
            start_to_close_timeout=timedelta(minutes=10)
        )
        
        # Step 3: Store in vector DB
        await workflow.execute_activity(
            store_embeddings,
            embeddings,
            start_to_close_timeout=timedelta(minutes=5)
        )
        
        # Step 4: Mark as published
        await workflow.execute_activity(
            mark_course_published,
            course_id,
            start_to_close_timeout=timedelta(minutes=1)
        )
        
        return "success"

@activity.defn
async def extract_course_content(course_id: str) -> dict:
    # Implementation
    pass
```

---

### AI/ML Stack

#### 1. **LangGraph (LangChain Evolution)**

**What it is:** Framework for building stateful, multi-agent AI applications

**JS Equivalent:** LangChain.js (but LangGraph is more advanced)

**Use Cases:**
- Build conversational AI agents
- Create multi-step reasoning chains
- Implement RAG (Retrieval Augmented Generation)

**SmartCourse Use Cases:**
- Contextual Q&A assistant
- Content summarization
- Quiz generation

```python
from langgraph.graph import Graph, StateGraph
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate

# Define agent state
class AgentState(TypedDict):
    question: str
    context: List[str]
    answer: str

# Build graph
workflow = StateGraph(AgentState)

def retrieve_context(state):
    # Search vector DB for relevant content
    results = vector_db.search(state["question"])
    state["context"] = [r.payload["text"] for r in results]
    return state

def generate_answer(state):
    # Use LLM to generate answer
    llm = ChatOpenAI(model="gpt-4")
    prompt = ChatPromptTemplate.from_template(
        "Context: {context}\n\nQuestion: {question}\n\nAnswer:"
    )
    answer = llm.invoke(prompt.format(**state))
    state["answer"] = answer.content
    return state

# Add nodes
workflow.add_node("retrieve", retrieve_context)
workflow.add_node("generate", generate_answer)

# Add edges
workflow.add_edge("retrieve", "generate")
workflow.set_entry_point("retrieve")
workflow.set_finish_point("generate")

app = workflow.compile()
```

---

#### 2. **LLM Providers**

**Options:** OpenAI, Groq, Anthropic

**Recommendation for Learning:** Start with OpenAI (GPT-4), then explore Groq (fast inference)

```python
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_groq import ChatGroq

# OpenAI
llm_openai = ChatOpenAI(model="gpt-4-turbo-preview", temperature=0.7)

# Anthropic (Claude)
llm_claude = ChatAnthropic(model="claude-3-opus-20240229")

# Groq (Fast inference)
llm_groq = ChatGroq(model="mixtral-8x7b-32768")

# Use interchangeably
response = await llm_openai.ainvoke("Explain quantum physics")
```

---

### Observability & Monitoring

#### 1. **Prometheus + Grafana (Metrics)**

**What it does:** Collect and visualize metrics

**Metrics to track:**
- Request rate, latency, error rate
- Database connection pool
- Cache hit rate
- Celery queue length
- Workflow execution time

```python
from prometheus_client import Counter, Histogram, generate_latest

# Define metrics
request_count = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint'])
request_duration = Histogram('http_request_duration_seconds', 'HTTP request duration')

# In your FastAPI app
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    request_count.labels(method=request.method, endpoint=request.url.path).inc()
    request_duration.observe(duration)
    
    return response

# Expose metrics endpoint
@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

---

#### 2. **Jaeger (Distributed Tracing)**

**What it does:** Trace requests across microservices

**JS Equivalent:** Similar to using Jaeger with Node.js

```python
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Setup
trace.set_tracer_provider(TracerProvider())
jaeger_exporter = JaegerExporter(
    agent_host_name="localhost",
    agent_port=6831,
)
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(jaeger_exporter)
)

tracer = trace.get_tracer(__name__)

# Usage
with tracer.start_as_current_span("process_enrollment"):
    # Your code here
    pass
```

---

#### 3. **OpenTelemetry (Unified Observability)**

**What it does:** Standard for metrics, logs, and traces

**Instruments:** FastAPI, SQLAlchemy, Redis, Kafka automatically

```python
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

# Auto-instrument FastAPI
FastAPIInstrumentor.instrument_app(app)

# Auto-instrument SQLAlchemy
SQLAlchemyInstrumentor().instrument(engine=engine)
```

---

## Microservices Architecture & Flow

### Service Breakdown

SmartCourse will consist of the following microservices:

```
┌─────────────────────────────────────────────────────────────────┐
│                         API Gateway                              │
│                  (FastAPI - Entry Point)                         │
└────────────┬────────────────────────────────────────────────────┘
             │
             ├─────────────┬──────────────┬──────────────┬─────────
             │             │              │              │
    ┌────────▼──────┐ ┌───▼─────┐ ┌──────▼──────┐ ┌────▼─────────┐
    │ Course        │ │ User    │ │ Enrollment  │ │ AI Assistant │
    │ Service       │ │ Service │ │ Service     │ │ Service      │
    └────────┬──────┘ └───┬─────┘ └──────┬──────┘ └────┬─────────┘
             │             │              │              │
             └─────────────┴──────────────┴──────────────┘
                                  │
                     ┌────────────▼────────────┐
                     │   Event Bus (Kafka)     │
                     └────────────┬────────────┘
                                  │
             ┌────────────────────┼────────────────────┐
             │                    │                    │
    ┌────────▼──────┐  ┌─────────▼────────┐  ┌───────▼────────┐
    │ Analytics     │  │ Notification     │  │ Content        │
    │ Service       │  │ Service          │  │ Processing Svc │
    └───────────────┘  └──────────────────┘  └────────────────┘
```

---

### Microservice Details

#### 1. **API Gateway Service**
- **Role:** Single entry point, request routing, authentication
- **Tech:** FastAPI
- **Port:** 8000
- **Endpoints:** Routes requests to appropriate services

#### 2. **Course Service**
- **Role:** Manage courses, modules, content
- **Tech:** FastAPI + PostgreSQL + MongoDB
- **Port:** 8001
- **Responsibilities:**
  - CRUD operations for courses
  - Module management
  - Content storage
  - Publishing workflow

#### 3. **User Service**
- **Role:** User management, authentication
- **Tech:** FastAPI + PostgreSQL + Redis
- **Port:** 8002
- **Responsibilities:**
  - User registration/login
  - Role management (student/instructor/admin)
  - Session management
  - JWT token generation

#### 4. **Enrollment Service**
- **Role:** Handle enrollments, progress tracking
- **Tech:** FastAPI + PostgreSQL
- **Port:** 8003
- **Responsibilities:**
  - Enrollment creation
  - Progress tracking
  - Completion management
  - Certificate generation

#### 5. **AI Assistant Service**
- **Role:** Intelligent Q&A, content generation
- **Tech:** FastAPI + LangGraph + Vector DB
- **Port:** 8004
- **Responsibilities:**
  - Contextual Q&A using RAG
  - Content summarization
  - Quiz generation
  - Streaming responses

#### 6. **Analytics Service**
- **Role:** Consume events and generate metrics
- **Tech:** FastAPI + PostgreSQL + Kafka Consumer
- **Port:** 8005
- **Responsibilities:**
  - Track enrollments
  - Calculate completion rates
  - Generate dashboards
  - Report generation

#### 7. **Notification Service**
- **Role:** Send notifications (email, push)
- **Tech:** FastAPI + Celery + Kafka Consumer
- **Port:** 8006
- **Responsibilities:**
  - Email notifications
  - In-app notifications
  - Notification templates

#### 8. **Content Processing Service**
- **Role:** Process course content, generate embeddings
- **Tech:** Python Workers + Temporal
- **Responsibilities:**
  - Extract text from PDFs/videos
  - Generate embeddings
  - Store in vector DB
  - Image processing

---

### Data Flow Diagrams

#### Flow 1: Course Publishing Workflow

```
┌──────────┐
│Instructor│
└────┬─────┘
     │ 1. Create course
     ▼
┌─────────────────┐
│ Course Service  │──┐
└────┬────────────┘  │ 2. Store in DB
     │                │
     │ 3. Publish     │
     ▼                │
┌─────────────────┐  │
│ Temporal        │  │
│ Workflow Engine │  │
└────┬────────────┘  │
     │                │
     │ 4. Start workflow
     ▼                │
┌─────────────────────────┐
│ Content Processing Svc  │
└────┬────────────────────┘
     │
     │ 5. Extract content
     │ 6. Generate embeddings
     │ 7. Store in Vector DB
     ▼
┌─────────────────┐
│ Vector DB       │
│ (Qdrant)        │
└────┬────────────┘
     │
     │ 8. Publish event
     ▼
┌─────────────────┐
│ Kafka           │──────► Analytics Service
│                 │──────► Notification Service
└─────────────────┘
```

**Step-by-step:**

1. Instructor creates course via API Gateway
2. Course Service stores course data in PostgreSQL + MongoDB
3. Instructor clicks "Publish"
4. Course Service triggers Temporal workflow
5. Temporal orchestrates content processing:
   - Activity 1: Extract text from materials
   - Activity 2: Chunk content into smaller pieces
   - Activity 3: Generate embeddings using OpenAI
   - Activity 4: Store embeddings in Qdrant
   - Activity 5: Update course status to "published"
6. Publish `course.published` event to Kafka
7. Analytics Service updates metrics
8. Notification Service notifies subscribed students

---

#### Flow 2: Student Enrollment Workflow

```
┌─────────┐
│ Student │
└────┬────┘
     │ 1. Enroll in course
     ▼
┌───────────────────┐
│Enrollment Service │
└────┬──────────────┘
     │ 2. Validate
     │    - Check prerequisites
     │    - Check duplicates
     │    - Check limits
     ▼
┌───────────────────┐
│ PostgreSQL        │
│ (enrollment table)│
└────┬──────────────┘
     │ 3. Create enrollment
     │
     │ 4. Trigger workflow
     ▼
┌───────────────────┐
│ Temporal Workflow │
└────┬──────────────┘
     │
     │ 5. Execute activities
     │    - Initialize progress
     │    - Update analytics
     │    - Queue notification
     ▼
┌───────────────────┐
│ Kafka Event Bus   │
└────┬──────────────┘
     │
     ├──────► Analytics Service (update enrollment count)
     ├──────► Notification Service (send welcome email)
     └──────► Course Service (update enrollment count)
```

---

#### Flow 3: AI Assistant Q&A (RAG Pattern)

```
┌─────────┐
│ Student │
└────┬────┘
     │ 1. Ask question about course
     ▼
┌───────────────────────┐
│ AI Assistant Service  │
└────┬──────────────────┘
     │
     │ 2. LangGraph starts
     ▼
┌─────────────────────────────────────────┐
│           LangGraph Workflow            │
│  ┌────────────────────────────────┐    │
│  │ Node 1: Retrieve Context       │    │
│  │  - Query Vector DB             │    │
│  │  - Get relevant course chunks  │    │
│  └──────────┬─────────────────────┘    │
│             │                           │
│             ▼                           │
│  ┌────────────────────────────────┐    │
│  │ Node 2: Rerank Results         │    │
│  │  - Score relevance             │    │
│  │  - Filter top K                │    │
│  └──────────┬─────────────────────┘    │
│             │                           │
│             ▼                           │
│  ┌────────────────────────────────┐    │
│  │ Node 3: Generate Answer        │    │
│  │  - Build prompt with context   │    │
│  │  - Call LLM (OpenAI/Groq)      │    │
│  │  - Stream response             │    │
│  └──────────┬─────────────────────┘    │
│             │                           │
└─────────────┼───────────────────────────┘
              │
              ▼
        ┌──────────┐
        │ Response │
        │ (Stream) │
        └──────────┘
```

**RAG (Retrieval Augmented Generation) Explained:**

1. **Retrieval Phase:**
   - Student's question is converted to embedding
   - Vector DB (Qdrant) searches for similar content embeddings
   - Top K most relevant chunks are retrieved

2. **Augmentation Phase:**
   - Retrieved chunks are added to prompt as context
   - Prompt template: "Given this context about the course, answer the question"

3. **Generation Phase:**
   - LLM generates answer based on context + question
   - Response is streamed back to student

---

#### Flow 4: Background Task Processing (Celery)

```
┌──────────────┐
│ Any Service  │
└──────┬───────┘
       │ 1. Queue task
       ▼
┌──────────────┐
│ RabbitMQ     │
└──────┬───────┘
       │
       │ 2. Pick up task
       ▼
┌──────────────────────┐
│ Celery Worker Pool   │
│  ┌─────────┐         │
│  │ Worker 1│         │
│  └─────────┘         │
│  ┌─────────┐         │
│  │ Worker 2│         │
│  └─────────┘         │
│  ┌─────────┐         │
│  │ Worker 3│         │
│  └─────────┘         │
└──────┬───────────────┘
       │ 3. Execute task
       │    - Retries on failure
       │    - Store result in Redis
       ▼
┌──────────────┐
│ Redis        │
│ (Result)     │
└──────────────┘
```

**Task Examples:**
- Send email notification
- Generate PDF certificate
- Process uploaded video
- Extract text from PDF
- Generate course thumbnail

---

### Event-Driven Architecture (Kafka)

#### Event Schema Registry

```python
# Event schemas with Avro/JSON Schema
{
  "course.published": {
    "course_id": "string",
    "instructor_id": "string",
    "title": "string",
    "published_at": "timestamp"
  },
  
  "student.enrolled": {
    "enrollment_id": "string",
    "student_id": "string",
    "course_id": "string",
    "enrolled_at": "timestamp"
  },
  
  "progress.updated": {
    "enrollment_id": "string",
    "student_id": "string",
    "course_id": "string",
    "module_id": "string",
    "completion_percentage": "float",
    "updated_at": "timestamp"
  },
  
  "course.completed": {
    "enrollment_id": "string",
    "student_id": "string",
    "course_id": "string",
    "completed_at": "timestamp",
    "duration_days": "int"
  }
}
```

#### Producer-Consumer Pattern

```
┌─────────────────┐
│ Course Service  │──┐
└─────────────────┘  │
                     │ Produce: course.published
┌─────────────────┐  │
│Enrollment Svc   │──┤ Produce: student.enrolled
└─────────────────┘  │
                     ▼
              ┌──────────────┐
              │    Kafka     │
              │    Topics    │
              └──────┬───────┘
                     │
       ┌─────────────┼─────────────┐
       │             │             │
       ▼             ▼             ▼
┌──────────┐  ┌──────────┐  ┌──────────┐
│Analytics │  │Notification│ │Content  │
│Consumer  │  │Consumer    │ │Consumer │
│          │  │            │ │         │
│Group: A  │  │Group: N    │ │Group: C │
└──────────┘  └──────────┘  └──────────┘
```

**Consumer Groups:**
- Each consumer group gets its own copy of events
- Within a group, only one consumer processes each event (load balancing)
- Kafka tracks offsets per consumer group

---

## Week-by-Week Implementation Plan

### **Week 1: Foundation & Core Services**

#### **Day 1-2: Environment Setup & Fundamentals**

**Learning Goals:**
- Python basics for JS developers
- FastAPI fundamentals
- SQLAlchemy ORM

**Tasks:**

1. **Setup Development Environment**
   ```bash
   # Install Python 3.11+
   brew install python@3.11
   
   # Create virtual environment
   python3.11 -m venv venv
   source venv/bin/activate
   
   # Install core dependencies
   pip install fastapi uvicorn sqlalchemy alembic psycopg2-binary pydantic python-dotenv
   ```

2. **Learn Python Essentials (if needed)**
   - Type hints (similar to TypeScript)
   - Async/await (same as JS!)
   - List comprehensions
   - Context managers (`with` statement)
   - Decorators (like decorators in TypeScript/Nest.js)

3. **Create Project Structure**
   ```
   smartcourse/
   ├── services/
   │   ├── api_gateway/
   │   ├── course_service/
   │   ├── user_service/
   │   ├── enrollment_service/
   │   └── ai_assistant_service/
   ├── shared/
   │   ├── database/
   │   ├── schemas/
   │   └── utils/
   ├── docker-compose.yml
   └── README.md
   ```

4. **Setup Docker Compose**
   ```yaml
   # docker-compose.yml
   version: '3.8'
   services:
     postgres:
       image: postgres:15
       environment:
         POSTGRES_DB: smartcourse
         POSTGRES_USER: admin
         POSTGRES_PASSWORD: password
       ports:
         - "5432:5432"
     
     mongodb:
       image: mongo:7
       ports:
         - "27017:27017"
     
     redis:
       image: redis:7-alpine
       ports:
         - "6379:6379"
   ```

**Deliverables:**
- ✅ Development environment ready
- ✅ Docker services running
- ✅ Basic FastAPI app with /health endpoint

---

#### **Day 3-4: User Service + Authentication**

**Learning Goals:**
- JWT authentication
- Password hashing (bcrypt)
- SQLAlchemy models and relationships

**Tasks:**

1. **Database Models**
   ```python
   # services/user_service/models.py
   from sqlalchemy import Column, String, Integer, Boolean, DateTime, Enum
   from datetime import datetime
   import enum
   
   class UserRole(enum.Enum):
       STUDENT = "student"
       INSTRUCTOR = "instructor"
       ADMIN = "admin"
   
   class User(Base):
       __tablename__ = "users"
       
       id = Column(Integer, primary_key=True, index=True)
       email = Column(String, unique=True, index=True, nullable=False)
       username = Column(String, unique=True, index=True, nullable=False)
       hashed_password = Column(String, nullable=False)
       role = Column(Enum(UserRole), nullable=False)
       is_active = Column(Boolean, default=True)
       created_at = Column(DateTime, default=datetime.utcnow)
       updated_at = Column(DateTime, onupdate=datetime.utcnow)
   ```

2. **Authentication Endpoints**
   - POST `/auth/register` - User registration
   - POST `/auth/login` - User login (returns JWT)
   - GET `/auth/me` - Get current user
   - POST `/auth/refresh` - Refresh token

3. **JWT Implementation**
   ```python
   from jose import jwt
   from passlib.context import CryptContext
   from datetime import datetime, timedelta
   
   pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
   
   def create_access_token(data: dict, expires_delta: timedelta = None):
       to_encode = data.copy()
       expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
       to_encode.update({"exp": expire})
       return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
   ```

**Deliverables:**
- ✅ User registration/login working
- ✅ JWT authentication middleware
- ✅ Protected endpoints with role-based access

---

#### **Day 5-6: Course Service - Basic CRUD**

**Learning Goals:**
- PostgreSQL + MongoDB hybrid approach
- File uploads
- Relationships in SQLAlchemy

**Tasks:**

1. **Database Models**
   ```python
   # PostgreSQL - Structured data
   class Course(Base):
       __tablename__ = "courses"
       
       id = Column(Integer, primary_key=True)
       title = Column(String, nullable=False)
       description = Column(String)
       instructor_id = Column(Integer, ForeignKey("users.id"))
       status = Column(Enum(CourseStatus), default=CourseStatus.DRAFT)
       created_at = Column(DateTime, default=datetime.utcnow)
       
       # Relationships
       instructor = relationship("User", back_populates="courses")
       enrollments = relationship("Enrollment", back_populates="course")
   ```

   ```python
   # MongoDB - Flexible content
   class CourseContent(Document):
       course_id: int
       modules: List[Module]
       materials: List[Material]
       
       class Settings:
           name = "course_contents"
   ```

2. **Endpoints**
   - POST `/courses` - Create course (instructors only)
   - GET `/courses` - List all courses (with pagination)
   - GET `/courses/{id}` - Get course details
   - PUT `/courses/{id}` - Update course
   - DELETE `/courses/{id}` - Delete course
   - POST `/courses/{id}/modules` - Add module

3. **File Upload for Materials**
   ```python
   from fastapi import UploadFile, File
   
   @app.post("/courses/{course_id}/materials")
   async def upload_material(
       course_id: int,
       file: UploadFile = File(...),
       current_user: User = Depends(get_current_user)
   ):
       # Save file to disk/S3
       # Store metadata in MongoDB
       pass
   ```

**Deliverables:**
- ✅ Course CRUD operations
- ✅ Module management
- ✅ File upload for materials
- ✅ PostgreSQL + MongoDB integration

---

#### **Day 7: Code Review & Testing**

**Tasks:**

1. **Write Unit Tests**
   ```python
   # tests/test_user_service.py
   import pytest
   from fastapi.testclient import TestClient
   
   def test_register_user(client: TestClient):
       response = client.post("/auth/register", json={
           "email": "test@example.com",
           "username": "testuser",
           "password": "password123",
           "role": "student"
       })
       assert response.status_code == 201
       assert response.json()["email"] == "test@example.com"
   ```

2. **Integration Tests**
   - Test auth flow
   - Test course creation
   - Test relationships

3. **Documentation**
   - Update README with setup instructions
   - Document API endpoints
   - Create architecture diagram

**Week 1 Deliverables:**
- ✅ User Service with authentication
- ✅ Course Service with CRUD
- ✅ PostgreSQL + MongoDB + Redis running
- ✅ Basic tests passing
- ✅ API documentation

---

### **Week 2: Enrollment, Background Jobs & Events**

#### **Day 8-9: Enrollment Service**

**Learning Goals:**
- Complex database queries
- Transaction management
- Business logic validation

**Tasks:**

1. **Database Models**
   ```python
   class Enrollment(Base):
       __tablename__ = "enrollments"
       
       id = Column(Integer, primary_key=True)
       student_id = Column(Integer, ForeignKey("users.id"))
       course_id = Column(Integer, ForeignKey("courses.id"))
       status = Column(Enum(EnrollmentStatus), default=EnrollmentStatus.ACTIVE)
       enrolled_at = Column(DateTime, default=datetime.utcnow)
       completed_at = Column(DateTime, nullable=True)
       
       # Relationships
       student = relationship("User", back_populates="enrollments")
       course = relationship("Course", back_populates="enrollments")
       progress = relationship("Progress", back_populates="enrollment", uselist=False)
   
   class Progress(Base):
       __tablename__ = "progress"
       
       id = Column(Integer, primary_key=True)
       enrollment_id = Column(Integer, ForeignKey("enrollments.id"), unique=True)
       completed_modules = Column(ARRAY(Integer), default=[])
       completion_percentage = Column(Float, default=0.0)
       last_accessed_at = Column(DateTime, default=datetime.utcnow)
       
       enrollment = relationship("Enrollment", back_populates="progress")
   ```

2. **Enrollment Logic**
   ```python
   async def enroll_student(student_id: int, course_id: int, db: Session):
       # 1. Check if already enrolled
       existing = db.query(Enrollment).filter(
           Enrollment.student_id == student_id,
           Enrollment.course_id == course_id
       ).first()
       
       if existing:
           raise HTTPException(400, "Already enrolled")
       
       # 2. Check prerequisites (if any)
       course = db.query(Course).filter(Course.id == course_id).first()
       if course.prerequisites:
           # Verify student completed prerequisites
           pass
       
       # 3. Create enrollment with transaction
       async with db.begin():
           enrollment = Enrollment(student_id=student_id, course_id=course_id)
           db.add(enrollment)
           await db.flush()
           
           # Initialize progress
           progress = Progress(enrollment_id=enrollment.id)
           db.add(progress)
           
           await db.commit()
       
       return enrollment
   ```

3. **Endpoints**
   - POST `/enrollments` - Enroll in course
   - GET `/enrollments/my-courses` - Get student's enrollments
   - GET `/enrollments/{id}/progress` - Get progress
   - PUT `/enrollments/{id}/progress` - Update progress
   - POST `/enrollments/{id}/complete` - Mark as completed

**Deliverables:**
- ✅ Enrollment service with validation
- ✅ Progress tracking
- ✅ Completion logic

---

#### **Day 10-11: Celery + RabbitMQ Setup**

**Learning Goals:**
- Asynchronous task processing
- Celery configuration
- Task retries and error handling

**Tasks:**

1. **Setup RabbitMQ**
   ```yaml
   # Add to docker-compose.yml
   rabbitmq:
     image: rabbitmq:3-management
     ports:
       - "5672:5672"
       - "15672:15672"  # Management UI
     environment:
       RABBITMQ_DEFAULT_USER: admin
       RABBITMQ_DEFAULT_PASS: password
   ```

2. **Celery Configuration**
   ```python
   # shared/celery_app.py
   from celery import Celery
   
   celery_app = Celery(
       'smartcourse',
       broker='amqp://admin:password@localhost:5672//',
       backend='redis://localhost:6379/0'
   )
   
   celery_app.conf.update(
       task_serializer='json',
       accept_content=['json'],
       result_serializer='json',
       timezone='UTC',
       enable_utc=True,
       task_track_started=True,
       task_time_limit=30 * 60,  # 30 minutes
   )
   ```

3. **Define Tasks**
   ```python
   # services/notification_service/tasks.py
   from shared.celery_app import celery_app
   
   @celery_app.task(bind=True, max_retries=3)
   def send_enrollment_email(self, user_email: str, course_title: str):
       try:
           # Send email using SMTP or SendGrid
           send_email(
               to=user_email,
               subject=f"Welcome to {course_title}",
               body=f"You've successfully enrolled in {course_title}"
           )
       except Exception as exc:
           raise self.retry(exc=exc, countdown=60)
   
   @celery_app.task
   def generate_certificate(enrollment_id: int):
       # Generate PDF certificate
       pass
   
   @celery_app.task
   def process_video_upload(file_path: str, course_id: int):
       # Extract audio, generate subtitles, create thumbnails
       pass
   ```

4. **Trigger Tasks from API**
   ```python
   @app.post("/enrollments")
   async def create_enrollment(
       enrollment_data: EnrollmentCreate,
       current_user: User = Depends(get_current_user)
   ):
       enrollment = await enroll_student(...)
       
       # Queue background task
       send_enrollment_email.delay(
           user_email=current_user.email,
           course_title=enrollment.course.title
       )
       
       return enrollment
   ```

5. **Run Celery Worker**
   ```bash
   celery -A shared.celery_app worker --loglevel=info
   ```

**Deliverables:**
- ✅ Celery + RabbitMQ integrated
- ✅ Email notification tasks
- ✅ Certificate generation task
- ✅ File processing tasks

---

#### **Day 12-13: Kafka Event Streaming**

**Learning Goals:**
- Event-driven architecture
- Producer-consumer pattern
- Schema Registry

**Tasks:**

1. **Setup Kafka**
   ```yaml
   # docker-compose.yml
   zookeeper:
     image: confluentinc/cp-zookeeper:latest
     environment:
       ZOOKEEPER_CLIENT_PORT: 2181
   
   kafka:
     image: confluentinc/cp-kafka:latest
     depends_on:
       - zookeeper
     ports:
       - "9092:9092"
     environment:
       KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
       KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
   
   schema-registry:
     image: confluentinc/cp-schema-registry:latest
     depends_on:
       - kafka
     ports:
       - "8081:8081"
     environment:
       SCHEMA_REGISTRY_HOST_NAME: schema-registry
       SCHEMA_REGISTRY_KAFKASTORE_BOOTSTRAP_SERVERS: kafka:9092
   ```

2. **Event Schemas**
   ```python
   # shared/events/schemas.py
   from pydantic import BaseModel
   from datetime import datetime
   
   class CoursePublishedEvent(BaseModel):
       event_type: str = "course.published"
       course_id: int
       instructor_id: int
       title: str
       published_at: datetime
   
   class StudentEnrolledEvent(BaseModel):
       event_type: str = "student.enrolled"
       enrollment_id: int
       student_id: int
       course_id: int
       enrolled_at: datetime
   ```

3. **Kafka Producer**
   ```python
   # shared/kafka/producer.py
   from aiokafka import AIOKafkaProducer
   import json
   
   class EventProducer:
       def __init__(self):
           self.producer = None
       
       async def start(self):
           self.producer = AIOKafkaProducer(
               bootstrap_servers='localhost:9092',
               value_serializer=lambda v: json.dumps(v).encode('utf-8')
           )
           await self.producer.start()
       
       async def publish(self, topic: str, event: dict):
           await self.producer.send_and_wait(topic, event)
       
       async def stop(self):
           await self.producer.stop()
   ```

4. **Publish Events**
   ```python
   # In course service
   @app.post("/courses/{course_id}/publish")
   async def publish_course(course_id: int):
       course = await get_course(course_id)
       course.status = CourseStatus.PUBLISHED
       await db.commit()
       
       # Publish event
       event = CoursePublishedEvent(
           course_id=course.id,
           instructor_id=course.instructor_id,
           title=course.title,
           published_at=datetime.utcnow()
       )
       await event_producer.publish("course.events", event.dict())
       
       return course
   ```

5. **Kafka Consumer (Analytics Service)**
   ```python
   # services/analytics_service/consumer.py
   from aiokafka import AIOKafkaConsumer
   import json
   
   async def consume_events():
       consumer = AIOKafkaConsumer(
           'course.events',
           'enrollment.events',
           bootstrap_servers='localhost:9092',
           group_id='analytics-service',
           value_deserializer=lambda m: json.loads(m.decode('utf-8'))
       )
       await consumer.start()
       
       try:
           async for msg in consumer:
               event = msg.value
               
               if event['event_type'] == 'course.published':
                   await update_course_count()
               elif event['event_type'] == 'student.enrolled':
                   await update_enrollment_metrics(event)
               
       finally:
           await consumer.stop()
   ```

**Deliverables:**
- ✅ Kafka cluster running
- ✅ Event schemas defined
- ✅ Producer publishing events
- ✅ Consumer processing events

---

#### **Day 14: Week 2 Integration & Testing**

**Tasks:**

1. **End-to-End Flow Testing**
   - Test enrollment → event → analytics update
   - Test course publish → event → notification

2. **Create Analytics Service**
   ```python
   @app.get("/analytics/dashboard")
   async def get_dashboard_metrics():
       return {
           "total_students": await count_students(),
           "total_instructors": await count_instructors(),
           "total_courses": await count_published_courses(),
           "new_enrollments_today": await count_enrollments_today(),
           "completion_rate": await calculate_completion_rate()
       }
   ```

3. **Monitoring Dashboard (Basic)**
   - Celery tasks in queue
   - Kafka lag per consumer group
   - Database connection pool

**Week 2 Deliverables:**
- ✅ Enrollment service complete
- ✅ Celery background tasks working
- ✅ Kafka event streaming implemented
- ✅ Analytics service consuming events
- ✅ End-to-end flows tested

---

### **Week 3: AI Integration & Temporal Workflows**

#### **Day 15-16: Vector Database & Embeddings**

**Learning Goals:**
- Vector embeddings
- Semantic search
- Qdrant vector database

**Tasks:**

1. **Setup Qdrant**
   ```yaml
   # docker-compose.yml
   qdrant:
     image: qdrant/qdrant:latest
     ports:
       - "6333:6333"
     volumes:
       - ./qdrant_storage:/qdrant/storage
   ```

2. **Install Dependencies**
   ```bash
   pip install qdrant-client openai langchain langchain-openai tiktoken
   ```

3. **Create Embedding Service**
   ```python
   # shared/embeddings/service.py
   from openai import OpenAI
   from qdrant_client import QdrantClient
   from qdrant_client.models import PointStruct, VectorParams, Distance
   
   class EmbeddingService:
       def __init__(self):
           self.openai_client = OpenAI(api_key=OPENAI_API_KEY)
           self.qdrant_client = QdrantClient(host="localhost", port=6333)
       
       async def create_collection(self, collection_name: str):
           self.qdrant_client.create_collection(
               collection_name=collection_name,
               vectors_config=VectorParams(
                   size=1536,  # OpenAI embedding dimension
                   distance=Distance.COSINE
               )
           )
       
       def generate_embedding(self, text: str) -> list[float]:
           response = self.openai_client.embeddings.create(
               model="text-embedding-3-small",
               input=text
           )
           return response.data[0].embedding
       
       async def store_course_content(self, course_id: int, chunks: list[dict]):
           points = []
           for i, chunk in enumerate(chunks):
               embedding = self.generate_embedding(chunk['text'])
               points.append(PointStruct(
                   id=f"{course_id}_{i}",
                   vector=embedding,
                   payload={
                       "course_id": course_id,
                       "text": chunk['text'],
                       "module_id": chunk.get('module_id'),
                       "chunk_index": i
                   }
               ))
           
           self.qdrant_client.upsert(
               collection_name="course_embeddings",
               points=points
           )
       
       async def search(self, query: str, course_id: int = None, top_k: int = 5):
           query_embedding = self.generate_embedding(query)
           
           search_filter = None
           if course_id:
               search_filter = {
                   "must": [{"key": "course_id", "match": {"value": course_id}}]
               }
           
           results = self.qdrant_client.search(
               collection_name="course_embeddings",
               query_vector=query_embedding,
               limit=top_k,
               query_filter=search_filter
           )
           
           return results
   ```

4. **Content Chunking**
   ```python
   # shared/embeddings/chunking.py
   from langchain.text_splitter import RecursiveCharacterTextSplitter
   
   def chunk_course_content(content: str, chunk_size: int = 1000) -> list[str]:
       splitter = RecursiveCharacterTextSplitter(
           chunk_size=chunk_size,
           chunk_overlap=200,
           length_function=len,
       )
       chunks = splitter.split_text(content)
       return chunks
   ```

5. **Process Course Content Task**
   ```python
   @celery_app.task
   def process_course_content(course_id: int):
       # 1. Get course content from MongoDB
       course_content = get_course_content(course_id)
       
       # 2. Chunk content
       all_chunks = []
       for module in course_content.modules:
           for material in module.materials:
               chunks = chunk_course_content(material.content)
               all_chunks.extend([{
                   'text': chunk,
                   'module_id': module.id
               } for chunk in chunks])
       
       # 3. Generate embeddings and store
       embedding_service = EmbeddingService()
       embedding_service.store_course_content(course_id, all_chunks)
   ```

**Deliverables:**
- ✅ Qdrant running and configured
- ✅ Embedding generation working
- ✅ Course content indexed
- ✅ Semantic search functional

---

#### **Day 17-18: AI Assistant with LangGraph**

**Learning Goals:**
- LangGraph for multi-step AI workflows
- RAG (Retrieval Augmented Generation)
- Streaming responses

**Tasks:**

1. **Install LangGraph**
   ```bash
   pip install langgraph langchain-openai langchain-community
   ```

2. **Build Q&A Agent**
   ```python
   # services/ai_assistant_service/agents/qa_agent.py
   from langgraph.graph import StateGraph, END
   from langchain_openai import ChatOpenAI
   from langchain.prompts import ChatPromptTemplate
   from typing import TypedDict, List
   
   class QAState(TypedDict):
       question: str
       course_id: int
       retrieved_chunks: List[str]
       answer: str
       confidence: float
   
   class QAAgent:
       def __init__(self):
           self.embedding_service = EmbeddingService()
           self.llm = ChatOpenAI(model="gpt-4-turbo-preview", temperature=0.7)
           self.workflow = self._build_workflow()
       
       def _build_workflow(self):
           workflow = StateGraph(QAState)
           
           # Add nodes
           workflow.add_node("retrieve", self._retrieve_context)
           workflow.add_node("generate", self._generate_answer)
           workflow.add_node("evaluate", self._evaluate_answer)
           
           # Add edges
           workflow.set_entry_point("retrieve")
           workflow.add_edge("retrieve", "generate")
           workflow.add_edge("generate", "evaluate")
           workflow.add_conditional_edges(
               "evaluate",
               self._should_retry,
               {
                   "retry": "retrieve",
                   "end": END
               }
           )
           
           return workflow.compile()
       
       async def _retrieve_context(self, state: QAState) -> QAState:
           # Search vector DB
           results = await self.embedding_service.search(
               query=state["question"],
               course_id=state["course_id"],
               top_k=5
           )
           
           state["retrieved_chunks"] = [r.payload["text"] for r in results]
           return state
       
       async def _generate_answer(self, state: QAState) -> QAState:
           # Build prompt with context
           prompt = ChatPromptTemplate.from_template("""
           You are a helpful teaching assistant. Use the following context from the course 
           to answer the student's question. If the answer cannot be found in the context, 
           say so.
           
           Context:
           {context}
           
           Question: {question}
           
           Answer:
           """)
           
           context = "\n\n".join(state["retrieved_chunks"])
           
           response = await self.llm.ainvoke(
               prompt.format(context=context, question=state["question"])
           )
           
           state["answer"] = response.content
           return state
       
       async def _evaluate_answer(self, state: QAState) -> QAState:
           # Simple evaluation: check if answer is too short or uncertain
           if len(state["answer"]) < 50 or "I don't know" in state["answer"]:
               state["confidence"] = 0.3
           else:
               state["confidence"] = 0.9
           return state
       
       def _should_retry(self, state: QAState):
           if state["confidence"] < 0.5:
               return "retry"
           return "end"
       
       async def answer_question(self, question: str, course_id: int) -> dict:
           initial_state = {
               "question": question,
               "course_id": course_id,
               "retrieved_chunks": [],
               "answer": "",
               "confidence": 0.0
           }
           
           result = await self.workflow.ainvoke(initial_state)
           return result
   ```

3. **Content Generation Agent**
   ```python
   # services/ai_assistant_service/agents/content_generator.py
   class ContentGenerator:
       def __init__(self):
           self.llm = ChatOpenAI(model="gpt-4-turbo-preview")
       
       async def generate_summary(self, course_content: str) -> str:
           prompt = ChatPromptTemplate.from_template("""
           Create a concise summary of the following course content:
           
           {content}
           
           Summary:
           """)
           
           response = await self.llm.ainvoke(prompt.format(content=course_content))
           return response.content
       
       async def generate_quiz(self, course_content: str, num_questions: int = 5) -> list:
           prompt = ChatPromptTemplate.from_template("""
           Generate {num_questions} multiple-choice quiz questions based on this content:
           
           {content}
           
           Format each question as:
           Q: [question]
           A) [option]
           B) [option]
           C) [option]
           D) [option]
           Correct: [letter]
           """)
           
           response = await self.llm.ainvoke(
               prompt.format(content=course_content, num_questions=num_questions)
           )
           return self._parse_quiz(response.content)
   ```

4. **AI Assistant API Endpoints**
   ```python
   # services/ai_assistant_service/main.py
   from fastapi import FastAPI
   from fastapi.responses import StreamingResponse
   
   app = FastAPI()
   qa_agent = QAAgent()
   content_generator = ContentGenerator()
   
   @app.post("/ai/ask")
   async def ask_question(
       question: str,
       course_id: int,
       current_user: User = Depends(get_current_user)
   ):
       result = await qa_agent.answer_question(question, course_id)
       return {
           "answer": result["answer"],
           "confidence": result["confidence"],
           "sources": result["retrieved_chunks"]
       }
   
   @app.post("/ai/generate-summary")
   async def generate_summary(
       course_id: int,
       current_user: User = Depends(get_current_instructor)
   ):
       course_content = await get_course_content(course_id)
       summary = await content_generator.generate_summary(course_content)
       return {"summary": summary}
   
   @app.post("/ai/generate-quiz")
   async def generate_quiz(
       course_id: int,
       num_questions: int = 5,
       current_user: User = Depends(get_current_instructor)
   ):
       course_content = await get_course_content(course_id)
       quiz = await content_generator.generate_quiz(course_content, num_questions)
       return {"quiz": quiz}
   ```

5. **Streaming Response (Advanced)**
   ```python
   @app.post("/ai/ask-stream")
   async def ask_question_stream(
       question: str,
       course_id: int,
       current_user: User = Depends(get_current_user)
   ):
       async def generate():
           # Retrieve context
           results = await embedding_service.search(question, course_id)
           context = "\n\n".join([r.payload["text"] for r in results])
           
           # Stream LLM response
           async for chunk in llm.astream(prompt.format(context=context, question=question)):
               yield f"data: {chunk.content}\n\n"
       
       return StreamingResponse(generate(), media_type="text/event-stream")
   ```

**Deliverables:**
- ✅ QA agent with RAG working
- ✅ Content generation endpoints
- ✅ Streaming responses implemented
- ✅ LangGraph workflow tested

---

#### **Day 19-20: Temporal Workflow Orchestration**

**Learning Goals:**
- Workflow orchestration with Temporal
- Activity implementation
- Saga pattern for distributed transactions

**Tasks:**

1. **Setup Temporal**
   ```yaml
   # docker-compose.yml
   temporal:
     image: temporalio/auto-setup:latest
     ports:
       - "7233:7233"
     environment:
       - DB=postgresql
       - DB_PORT=5432
       - POSTGRES_USER=admin
       - POSTGRES_PWD=password
       - POSTGRES_SEEDS=postgres
   
   temporal-ui:
     image: temporalio/ui:latest
     ports:
       - "8080:8080"
     environment:
       - TEMPORAL_ADDRESS=temporal:7233
   ```

2. **Install Temporal SDK**
   ```bash
   pip install temporalio
   ```

3. **Course Publishing Workflow**
   ```python
   # workflows/course_publishing_workflow.py
   from temporalio import workflow, activity
   from datetime import timedelta
   
   @workflow.defn
   class CoursePublishingWorkflow:
       @workflow.run
       async def run(self, course_id: int) -> dict:
           workflow.logger.info(f"Starting publishing workflow for course {course_id}")
           
           try:
               # Step 1: Validate course
               await workflow.execute_activity(
                   validate_course,
                   course_id,
                   start_to_close_timeout=timedelta(minutes=2)
               )
               
               # Step 2: Extract and chunk content
               chunks = await workflow.execute_activity(
                   extract_course_content,
                   course_id,
                   start_to_close_timeout=timedelta(minutes=5)
               )
               
               # Step 3: Generate embeddings
               embeddings = await workflow.execute_activity(
                   generate_course_embeddings,
                   chunks,
                   start_to_close_timeout=timedelta(minutes=10)
               )
               
               # Step 4: Store in vector DB
               await workflow.execute_activity(
                   store_embeddings_in_vector_db,
                   args=[course_id, embeddings],
                   start_to_close_timeout=timedelta(minutes=5)
               )
               
               # Step 5: Update course status
               await workflow.execute_activity(
                   update_course_status,
                   args=[course_id, "published"],
                   start_to_close_timeout=timedelta(minutes=1)
               )
               
               # Step 6: Publish event
               await workflow.execute_activity(
                   publish_course_event,
                   course_id,
                   start_to_close_timeout=timedelta(minutes=1)
               )
               
               return {"status": "success", "course_id": course_id}
               
           except Exception as e:
               workflow.logger.error(f"Workflow failed: {str(e)}")
               # Rollback activities
               await workflow.execute_activity(
                   rollback_course_publishing,
                   course_id,
                   start_to_close_timeout=timedelta(minutes=2)
               )
               raise
   
   # Activities
   @activity.defn
   async def validate_course(course_id: int) -> bool:
       # Check course has content, modules, etc.
       course = await get_course(course_id)
       if not course.modules:
           raise ValueError("Course must have at least one module")
       return True
   
   @activity.defn
   async def extract_course_content(course_id: int) -> list[dict]:
       # Get content from MongoDB and chunk it
       content = await get_course_content_from_db(course_id)
       chunks = chunk_course_content(content)
       return chunks
   
   @activity.defn
   async def generate_course_embeddings(chunks: list[dict]) -> list[dict]:
       embedding_service = EmbeddingService()
       embeddings = []
       for chunk in chunks:
           embedding = embedding_service.generate_embedding(chunk['text'])
           embeddings.append({
               'text': chunk['text'],
               'embedding': embedding,
               'metadata': chunk.get('metadata', {})
           })
       return embeddings
   
   @activity.defn
   async def store_embeddings_in_vector_db(course_id: int, embeddings: list[dict]):
       embedding_service = EmbeddingService()
       await embedding_service.store_course_content(course_id, embeddings)
   
   @activity.defn
   async def update_course_status(course_id: int, status: str):
       await update_course_in_db(course_id, {"status": status})
   
   @activity.defn
   async def publish_course_event(course_id: int):
       event_producer = EventProducer()
       await event_producer.publish("course.events", {
           "event_type": "course.published",
           "course_id": course_id,
           "published_at": datetime.utcnow().isoformat()
       })
   
   @activity.defn
   async def rollback_course_publishing(course_id: int):
       # Delete embeddings, revert status
       pass
   ```

4. **Enrollment Workflow**
   ```python
   @workflow.defn
   class EnrollmentWorkflow:
       @workflow.run
       async def run(self, student_id: int, course_id: int) -> dict:
           # Step 1: Create enrollment
           enrollment_id = await workflow.execute_activity(
               create_enrollment_record,
               args=[student_id, course_id],
               start_to_close_timeout=timedelta(minutes=2)
           )
           
           # Step 2: Initialize progress
           await workflow.execute_activity(
               initialize_progress,
               enrollment_id,
               start_to_close_timeout=timedelta(minutes=1)
           )
           
           # Step 3: Update analytics
           await workflow.execute_activity(
               update_enrollment_analytics,
               enrollment_id,
               start_to_close_timeout=timedelta(minutes=1)
           )
           
           # Step 4: Send notification
           await workflow.execute_activity(
               send_enrollment_notification,
               args=[student_id, course_id],
               start_to_close_timeout=timedelta(minutes=1)
           )
           
           return {"enrollment_id": enrollment_id}
   ```

5. **Start Temporal Worker**
   ```python
   # workers/temporal_worker.py
   import asyncio
   from temporalio.client import Client
   from temporalio.worker import Worker
   from workflows.course_publishing_workflow import CoursePublishingWorkflow
   from workflows.enrollment_workflow import EnrollmentWorkflow
   
   async def main():
       client = await Client.connect("localhost:7233")
       
       worker = Worker(
           client,
           task_queue="smartcourse-workflows",
           workflows=[CoursePublishingWorkflow, EnrollmentWorkflow],
           activities=[
               validate_course,
               extract_course_content,
               # ... all activities
           ],
       )
       
       await worker.run()
   
   if __name__ == "__main__":
       asyncio.run(main())
   ```

6. **Trigger Workflow from API**
   ```python
   from temporalio.client import Client
   
   @app.post("/courses/{course_id}/publish")
   async def publish_course(course_id: int):
       # Connect to Temporal
       client = await Client.connect("localhost:7233")
       
       # Start workflow
       handle = await client.start_workflow(
           CoursePublishingWorkflow.run,
           course_id,
           id=f"course-publish-{course_id}",
           task_queue="smartcourse-workflows",
       )
       
       return {
           "workflow_id": handle.id,
           "status": "started"
       }
   
   @app.get("/workflows/{workflow_id}/status")
   async def get_workflow_status(workflow_id: str):
       client = await Client.connect("localhost:7233")
       handle = client.get_workflow_handle(workflow_id)
       
       try:
           result = await handle.result()
           return {"status": "completed", "result": result}
       except:
           return {"status": "running"}
   ```

**Deliverables:**
- ✅ Temporal running with UI
- ✅ Course publishing workflow
- ✅ Enrollment workflow
- ✅ Activities implemented
- ✅ Workflow monitoring

---

#### **Day 21: Week 3 Integration**

**Tasks:**

1. **End-to-End Flow**
   - Instructor creates course
   - Adds content
   - Clicks "Publish"
   - Temporal workflow processes everything
   - Student can search and ask questions

2. **Testing**
   - Test workflow failure scenarios
   - Test retry logic
   - Test saga rollback

3. **Documentation**
   - Document AI assistant usage
   - Document workflow patterns
   - Create sequence diagrams

**Week 3 Deliverables:**
- ✅ Vector DB with course embeddings
- ✅ AI assistant with Q&A
- ✅ Content generation tools
- ✅ Temporal workflows orchestrating complex flows
- ✅ Full publishing pipeline working

---

### **Week 4: Observability, Testing & Production Ready**

#### **Day 22-23: Observability Stack**

**Learning Goals:**
- Prometheus metrics
- Grafana dashboards
- Jaeger distributed tracing
- OpenTelemetry instrumentation

**Tasks:**

1. **Setup Prometheus & Grafana**
   ```yaml
   # docker-compose.yml
   prometheus:
     image: prom/prometheus:latest
     ports:
       - "9090:9090"
     volumes:
       - ./prometheus.yml:/etc/prometheus/prometheus.yml
       - prometheus_data:/prometheus
     command:
       - '--config.file=/etc/prometheus/prometheus.yml'
   
   grafana:
     image: grafana/grafana:latest
     ports:
       - "3000:3000"
     environment:
       - GF_SECURITY_ADMIN_PASSWORD=admin
     volumes:
       - grafana_data:/var/lib/grafana
   ```

   ```yaml
   # prometheus.yml
   global:
     scrape_interval: 15s
   
   scrape_configs:
     - job_name: 'course-service'
       static_configs:
         - targets: ['host.docker.internal:8001']
     
     - job_name: 'user-service'
       static_configs:
         - targets: ['host.docker.internal:8002']
     
     - job_name: 'ai-assistant'
       static_configs:
         - targets: ['host.docker.internal:8004']
   ```

2. **Add Prometheus Metrics**
   ```python
   # shared/monitoring/metrics.py
   from prometheus_client import Counter, Histogram, Gauge, generate_latest
   from prometheus_client import CollectorRegistry
   
   # Create registry
   registry = CollectorRegistry()
   
   # Metrics
   http_requests_total = Counter(
       'http_requests_total',
       'Total HTTP requests',
       ['method', 'endpoint', 'status'],
       registry=registry
   )
   
   http_request_duration = Histogram(
       'http_request_duration_seconds',
       'HTTP request duration',
       ['method', 'endpoint'],
       registry=registry
   )
   
   db_connections = Gauge(
       'db_connections_active',
       'Active database connections',
       registry=registry
   )
   
   celery_tasks_total = Counter(
       'celery_tasks_total',
       'Total Celery tasks',
       ['task_name', 'status'],
       registry=registry
   )
   
   ai_queries_total = Counter(
       'ai_queries_total',
       'Total AI assistant queries',
       ['type'],
       registry=registry
   )
   
   ai_query_duration = Histogram(
       'ai_query_duration_seconds',
       'AI query processing time',
       ['type'],
       registry=registry
   )
   ```

3. **Instrument FastAPI**
   ```python
   # shared/monitoring/middleware.py
   import time
   from fastapi import Request
   
   async def metrics_middleware(request: Request, call_next):
       start_time = time.time()
       
       response = await call_next(request)
       
       duration = time.time() - start_time
       
       http_requests_total.labels(
           method=request.method,
           endpoint=request.url.path,
           status=response.status_code
       ).inc()
       
       http_request_duration.labels(
           method=request.method,
           endpoint=request.url.path
       ).observe(duration)
       
       return response
   
   # In main.py
   app.middleware("http")(metrics_middleware)
   
   @app.get("/metrics")
   async def metrics():
       from prometheus_client import generate_latest
       return Response(generate_latest(registry), media_type="text/plain")
   ```

4. **Setup Jaeger**
   ```yaml
   # docker-compose.yml
   jaeger:
     image: jaegertracing/all-in-one:latest
     ports:
       - "6831:6831/udp"  # Accept jaeger.thrift
       - "16686:16686"     # UI
       - "14268:14268"     # Accept jaeger.thrift from clients
   ```

5. **Add OpenTelemetry**
   ```bash
   pip install opentelemetry-api opentelemetry-sdk \
               opentelemetry-instrumentation-fastapi \
               opentelemetry-instrumentation-sqlalchemy \
               opentelemetry-instrumentation-redis \
               opentelemetry-exporter-jaeger
   ```

   ```python
   # shared/monitoring/tracing.py
   from opentelemetry import trace
   from opentelemetry.sdk.trace import TracerProvider
   from opentelemetry.sdk.trace.export import BatchSpanProcessor
   from opentelemetry.exporter.jaeger.thrift import JaegerExporter
   from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
   from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
   
   def setup_tracing(app, service_name: str):
       # Setup tracer
       trace.set_tracer_provider(TracerProvider())
       tracer_provider = trace.get_tracer_provider()
       
       # Setup Jaeger exporter
       jaeger_exporter = JaegerExporter(
           agent_host_name="localhost",
           agent_port=6831,
       )
       
       tracer_provider.add_span_processor(
           BatchSpanProcessor(jaeger_exporter)
       )
       
       # Auto-instrument FastAPI
       FastAPIInstrumentor.instrument_app(app)
       
       # Auto-instrument SQLAlchemy
       SQLAlchemyInstrumentor().instrument()
   
   # In main.py
   setup_tracing(app, "course-service")
   ```

6. **Create Grafana Dashboards**
   - Import pre-built dashboards
   - Create custom dashboard for SmartCourse metrics:
     - Request rate per service
     - Error rate
     - P95 latency
     - Database connections
     - Celery queue length
     - AI query duration

**Deliverables:**
- ✅ Prometheus collecting metrics
- ✅ Grafana dashboards
- ✅ Jaeger tracing
- ✅ All services instrumented

---

#### **Day 24: Comprehensive Testing**

**Learning Goals:**
- Pytest for Python
- Unit tests, integration tests, E2E tests
- Test fixtures and mocking

**Tasks:**

1. **Setup Testing**
   ```bash
   pip install pytest pytest-asyncio pytest-cov httpx
   ```

   ```python
   # conftest.py
   import pytest
   from fastapi.testclient import TestClient
   from sqlalchemy import create_engine
   from sqlalchemy.orm import sessionmaker
   from shared.database.base import Base
   
   # Test database
   TEST_DATABASE_URL = "postgresql://admin:password@localhost:5432/smartcourse_test"
   engine = create_engine(TEST_DATABASE_URL)
   TestingSessionLocal = sessionmaker(bind=engine)
   
   @pytest.fixture(scope="function")
   def db():
       Base.metadata.create_all(bind=engine)
       db = TestingSessionLocal()
       try:
           yield db
       finally:
           db.close()
           Base.metadata.drop_all(bind=engine)
   
   @pytest.fixture
   def client(db):
       from services.course_service.main import app
       
       def override_get_db():
           try:
               yield db
           finally:
               pass
       
       app.dependency_overrides[get_db] = override_get_db
       return TestClient(app)
   ```

2. **Unit Tests**
   ```python
   # tests/test_course_service.py
   import pytest
   from services.course_service.models import Course
   from services.course_service.crud import create_course
   
   def test_create_course(db):
       course_data = {
           "title": "Test Course",
           "description": "Test Description",
           "instructor_id": 1
       }
       
       course = create_course(db, course_data)
       
       assert course.title == "Test Course"
       assert course.status == "draft"
   
   @pytest.mark.asyncio
   async def test_get_course_api(client):
       # Create course
       response = client.post("/courses", json={
           "title": "API Test Course",
           "description": "Test"
       }, headers={"Authorization": "Bearer test_token"})
       
       course_id = response.json()["id"]
       
       # Get course
       response = client.get(f"/courses/{course_id}")
       assert response.status_code == 200
       assert response.json()["title"] == "API Test Course"
   ```

3. **Integration Tests**
   ```python
   # tests/integration/test_enrollment_flow.py
   @pytest.mark.asyncio
   async def test_enrollment_flow(client, db):
       # 1. Create course
       course = await create_test_course(db)
       
       # 2. Create student
       student = await create_test_user(db, role="student")
       
       # 3. Enroll
       response = client.post("/enrollments", json={
           "course_id": course.id
       }, headers=auth_headers(student))
       
       assert response.status_code == 201
       enrollment = response.json()
       
       # 4. Check progress initialized
       progress = db.query(Progress).filter(
           Progress.enrollment_id == enrollment["id"]
       ).first()
       
       assert progress is not None
       assert progress.completion_percentage == 0.0
   ```

4. **Mock External Services**
   ```python
   # tests/mocks.py
   from unittest.mock import Mock, AsyncMock
   
   @pytest.fixture
   def mock_openai():
       mock = AsyncMock()
       mock.embeddings.create.return_value = Mock(
           data=[Mock(embedding=[0.1] * 1536)]
       )
       mock.chat.completions.create.return_value = Mock(
           choices=[Mock(message=Mock(content="Test answer"))]
       )
       return mock
   
   @pytest.fixture
   def mock_qdrant():
       mock = Mock()
       mock.search.return_value = [
           Mock(payload={"text": "Test context"}, score=0.9)
       ]
       return mock
   
   # In test
   def test_ai_query(mock_openai, mock_qdrant):
       # Use mocks instead of real services
       pass
   ```

5. **Test Coverage**
   ```bash
   pytest --cov=services --cov-report=html
   ```

**Deliverables:**
- ✅ Unit tests for all services
- ✅ Integration tests for key flows
- ✅ Mocked external services
- ✅ >80% code coverage

---

#### **Day 25-26: API Documentation & DevOps**

**Tasks:**

1. **Enhance API Documentation**
   ```python
   # Better OpenAPI docs
   from fastapi import FastAPI
   from fastapi.openapi.utils import get_openapi
   
   app = FastAPI(
       title="SmartCourse API",
       description="Intelligent Course Delivery Platform",
       version="1.0.0",
       docs_url="/docs",
       redoc_url="/redoc"
   )
   
   # Add examples to endpoints
   @app.post(
       "/courses",
       response_model=CourseResponse,
       summary="Create a new course",
       description="Create a new course as an instructor",
       responses={
           201: {
               "description": "Course created successfully",
               "content": {
                   "application/json": {
                       "example": {
                           "id": 1,
                           "title": "Introduction to Python",
                           "status": "draft"
                       }
                   }
               }
           }
       }
   )
   async def create_course(course: CourseCreate):
       pass
   ```

2. **Create Docker Images**
   ```dockerfile
   # services/course_service/Dockerfile
   FROM python:3.11-slim
   
   WORKDIR /app
   
   # Install dependencies
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   
   # Copy code
   COPY . .
   
   # Run
   CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
   ```

3. **Production Docker Compose**
   ```yaml
   # docker-compose.prod.yml
   version: '3.8'
   
   services:
     course-service:
       build: ./services/course_service
       ports:
         - "8001:8001"
       environment:
         - DATABASE_URL=postgresql://...
         - REDIS_URL=redis://...
       depends_on:
         - postgres
         - redis
       restart: unless-stopped
     
     user-service:
       build: ./services/user_service
       ports:
         - "8002:8002"
       restart: unless-stopped
     
     # ... other services
   ```

4. **Health Checks**
   ```python
   @app.get("/health")
   async def health_check():
       # Check database
       try:
           db.execute("SELECT 1")
           db_status = "healthy"
       except:
           db_status = "unhealthy"
       
       # Check Redis
       try:
           await redis.ping()
           redis_status = "healthy"
       except:
           redis_status = "unhealthy"
       
       return {
           "status": "healthy" if all([db_status, redis_status]) else "unhealthy",
           "database": db_status,
           "cache": redis_status
       }
   ```

5. **Environment Variables**
   ```python
   # shared/config.py
   from pydantic_settings import BaseSettings
   
   class Settings(BaseSettings):
       # Database
       database_url: str
       mongodb_url: str
       redis_url: str
       
       # External Services
       openai_api_key: str
       qdrant_host: str = "localhost"
       qdrant_port: int = 6333
       
       # Kafka
       kafka_bootstrap_servers: str = "localhost:9092"
       
       # Temporal
       temporal_host: str = "localhost:7233"
       
       # Security
       secret_key: str
       algorithm: str = "HS256"
       access_token_expire_minutes: int = 30
       
       class Config:
           env_file = ".env"
   
   settings = Settings()
   ```

**Deliverables:**
- ✅ Comprehensive API documentation
- ✅ Docker images for all services
- ✅ Production docker-compose
- ✅ Health checks

---

#### **Day 27-28: Final Integration & PRD**

**Tasks:**

1. **Product Requirements Document (PRD)**
   ```markdown
   # SmartCourse PRD
   
   ## Executive Summary
   [Overview of the platform]
   
   ## Key Features
   1. Course Management
      - CRUD operations
      - Module structure
      - Content upload
   
   2. Student Enrollment
      - Enrollment workflow
      - Progress tracking
      - Certificates
   
   3. AI Assistant
      - Contextual Q&A
      - Content generation
      - Intelligent search
   
   ## Technical Architecture
   [Architecture diagrams]
   
   ## Implementation Timeline
   - Week 1: Core services
   - Week 2: Background processing
   - Week 3: AI integration
   - Week 4: Production ready
   
   ## Success Metrics
   - API response time < 200ms (P95)
   - 99.9% uptime
   - Support 10,000 concurrent users
   ```

2. **Create System Architecture Diagrams**
   - Use draw.io or Mermaid
   - Service architecture
   - Data flow diagrams
   - Deployment architecture

3. **Performance Testing**
   ```python
   # Load testing with Locust
   from locust import HttpUser, task, between
   
   class SmartCourseUser(HttpUser):
       wait_time = between(1, 3)
       
       @task
       def list_courses(self):
           self.client.get("/courses")
       
       @task(3)
       def get_course(self):
           self.client.get("/courses/1")
       
       @task(2)
       def ask_question(self):
           self.client.post("/ai/ask", json={
               "question": "What is machine learning?",
               "course_id": 1
           })
   ```

4. **Final Testing Checklist**
   - [ ] All CRUD operations work
   - [ ] Authentication & authorization
   - [ ] Enrollment flow complete
   - [ ] Course publishing workflow
   - [ ] AI assistant responding
   - [ ] Background tasks processing
   - [ ] Events flowing through Kafka
   - [ ] Metrics in Grafana
   - [ ] Traces in Jaeger
   - [ ] All tests passing

5. **Documentation**
   - API documentation
   - Architecture documentation
   - Deployment guide
   - Development setup guide
   - Troubleshooting guide

**Week 4 Deliverables:**
- ✅ Full observability stack
- ✅ Comprehensive testing
- ✅ Production-ready deployment
- ✅ Complete documentation
- ✅ PRD document

---

## Detailed Component Breakdown

### Database Schema Design

```sql
-- PostgreSQL Schema

-- Users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    username VARCHAR(100) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('student', 'instructor', 'admin')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Courses table
CREATE TABLE courses (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    instructor_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'archived')),
    thumbnail_url VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMP
);

-- Enrollments table
CREATE TABLE enrollments (
    id SERIAL PRIMARY KEY,
    student_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'completed', 'dropped')),
    enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    UNIQUE(student_id, course_id)
);

-- Progress tracking
CREATE TABLE progress (
    id SERIAL PRIMARY KEY,
    enrollment_id INTEGER UNIQUE REFERENCES enrollments(id) ON DELETE CASCADE,
    completed_modules INTEGER[] DEFAULT '{}',
    completion_percentage DECIMAL(5,2) DEFAULT 0.00,
    last_accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Analytics metrics
CREATE TABLE analytics_metrics (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL(10,2) NOT NULL,
    dimension JSONB,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_courses_instructor ON courses(instructor_id);
CREATE INDEX idx_courses_status ON courses(status);
CREATE INDEX idx_enrollments_student ON enrollments(student_id);
CREATE INDEX idx_enrollments_course ON enrollments(course_id);
CREATE INDEX idx_analytics_metric_name ON analytics_metrics(metric_name);
CREATE INDEX idx_analytics_recorded_at ON analytics_metrics(recorded_at);
```

```javascript
// MongoDB Schemas

// Course Content
{
  _id: ObjectId,
  course_id: 123,
  modules: [
    {
      id: 1,
      title: "Introduction to Python",
      order: 1,
      lessons: [
        {
          id: 1,
          title: "Variables and Data Types",
          type: "video",
          content_url: "https://...",
          duration_minutes: 15,
          materials: [
            {
              type: "pdf",
              url: "https://...",
              title: "Lecture Notes"
            }
          ]
        }
      ]
    }
  ],
  metadata: {
    total_duration_hours: 40,
    difficulty: "beginner",
    tags: ["python", "programming", "basics"]
  }
}
```

---

### API Endpoints Reference

#### **Authentication Service**
```
POST   /auth/register          - Register new user
POST   /auth/login             - Login and get JWT
GET    /auth/me                - Get current user
POST   /auth/refresh           - Refresh access token
POST   /auth/logout            - Logout
```

#### **Course Service**
```
GET    /courses                - List all courses (paginated)
POST   /courses                - Create course (instructor only)
GET    /courses/{id}           - Get course details
PUT    /courses/{id}           - Update course
DELETE /courses/{id}           - Delete course
POST   /courses/{id}/publish   - Publish course (triggers workflow)
POST   /courses/{id}/modules   - Add module to course
PUT    /courses/{id}/modules/{module_id}  - Update module
DELETE /courses/{id}/modules/{module_id}  - Delete module
POST   /courses/{id}/materials - Upload learning material
```

#### **Enrollment Service**
```
POST   /enrollments            - Enroll in a course
GET    /enrollments/my-courses - Get my enrollments
GET    /enrollments/{id}       - Get enrollment details
GET    /enrollments/{id}/progress  - Get progress
PUT    /enrollments/{id}/progress  - Update progress
POST   /enrollments/{id}/complete  - Mark as completed
DELETE /enrollments/{id}       - Unenroll
```

#### **AI Assistant Service**
```
POST   /ai/ask                 - Ask question (RAG)
POST   /ai/ask-stream          - Ask question (streaming)
POST   /ai/generate-summary    - Generate course summary
POST   /ai/generate-quiz       - Generate quiz questions
POST   /ai/explain             - Explain concept
```

#### **Analytics Service**
```
GET    /analytics/dashboard    - Get dashboard metrics
GET    /analytics/course/{id}  - Get course analytics
GET    /analytics/student/{id} - Get student analytics
GET    /analytics/enrollments  - Enrollment trends
GET    /analytics/completions  - Completion metrics
```

---

## Testing Strategy

### Test Pyramid

```
                 ┌─────────┐
                 │   E2E   │  (Few, critical user journeys)
                 └─────────┘
              ┌──────────────┐
              │ Integration  │  (Service interactions)
              └──────────────┘
          ┌────────────────────┐
          │   Unit Tests       │  (Most tests here)
          └────────────────────┘
```

### Unit Tests (70%)
- Test individual functions
- Mock external dependencies
- Fast execution

### Integration Tests (20%)
- Test service interactions
- Use test database
- Test workflows

### E2E Tests (10%)
- Critical user journeys
- Full stack testing
- Slower execution

---

## Deployment & Monitoring

### Deployment Checklist

- [ ] All environment variables configured
- [ ] Database migrations applied
- [ ] Redis cluster configured
- [ ] RabbitMQ cluster configured
- [ ] Kafka cluster configured
- [ ] Temporal cluster configured
- [ ] Vector DB initialized
- [ ] SSL certificates installed
- [ ] Load balancer configured
- [ ] Monitoring enabled
- [ ] Logging configured
- [ ] Backup strategy in place

### Monitoring Dashboards

**1. Service Health Dashboard**
- Request rate per service
- Error rate
- P50, P95, P99 latency
- CPU and memory usage

**2. Business Metrics Dashboard**
- Total users (students, instructors)
- Total courses published
- New enrollments (daily, weekly, monthly)
- Course completion rate
- AI queries per day

**3. Infrastructure Dashboard**
- Database connections
- Cache hit rate
- Queue length (Celery, Kafka)
- Workflow execution time
- Worker utilization

---

## Learning Resources

### Python Fundamentals
- [Official Python Tutorial](https://docs.python.org/3/tutorial/)
- "Python for JavaScript Developers" guide
- Type hints and async/await

### FastAPI
- [FastAPI Official Docs](https://fastapi.tiangolo.com/)
- "FastAPI from Scratch" course
- Compare with Nest.js patterns

### LangChain/LangGraph
- [LangChain Docs](https://python.langchain.com/)
- [LangGraph Tutorial](https://langchain-ai.github.io/langgraph/)
- RAG patterns and examples

### Temporal
- [Temporal Python SDK](https://docs.temporal.io/dev-guide/python)
- Workflow patterns
- Saga pattern implementation

### Observability
- Prometheus query language (PromQL)
- Grafana dashboard creation
- Jaeger trace analysis

---

## Common Pitfalls & Solutions

### 1. **Database Connection Pool Exhaustion**
**Problem:** Too many concurrent requests, DB connections exhausted

**Solution:**
```python
# Use connection pooling
engine = create_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True
)
```

### 2. **Celery Task Failures**
**Problem:** Tasks failing silently

**Solution:**
```python
# Add retry logic and error handling
@celery_app.task(bind=True, max_retries=3, autoretry_for=(Exception,))
def my_task(self):
    try:
        # Task logic
        pass
    except Exception as exc:
        logger.error(f"Task failed: {exc}")
        raise self.retry(exc=exc, countdown=60)
```

### 3. **Kafka Consumer Lag**
**Problem:** Consumers can't keep up with producers

**Solution:**
- Scale consumers (more instances)
- Optimize processing logic
- Use batch processing
- Monitor lag in Grafana

### 4. **Vector DB Query Performance**
**Problem:** Slow semantic search queries

**Solution:**
- Use HNSW index in Qdrant
- Limit top_k results
- Add filters to narrow search
- Cache frequent queries in Redis

### 5. **LLM Rate Limits**
**Problem:** Hitting OpenAI rate limits

**Solution:**
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def call_llm(prompt):
    return await llm.ainvoke(prompt)
```

---

## Success Criteria

### Week 1 ✅
- [ ] User authentication working
- [ ] Course CRUD operations
- [ ] Database migrations
- [ ] Basic tests passing

### Week 2 ✅
- [ ] Enrollment workflow complete
- [ ] Celery tasks processing
- [ ] Kafka events flowing
- [ ] Analytics tracking enrollments

### Week 3 ✅
- [ ] Vector DB storing embeddings
- [ ] AI assistant answering questions
- [ ] Content generation working
- [ ] Temporal workflows orchestrating

### Week 4 ✅
- [ ] Prometheus metrics collected
- [ ] Grafana dashboards created
- [ ] Jaeger traces visible
- [ ] All tests passing (>80% coverage)
- [ ] PRD document complete
- [ ] Production deployment ready

---

## Next Steps After 4 Weeks

1. **Scalability Improvements**
   - Implement caching layer
   - Add read replicas for PostgreSQL
   - Implement API rate limiting
   - Add CDN for static content

2. **Feature Enhancements**
   - Real-time collaboration (WebSocket)
   - Video conferencing integration
   - Mobile app API
   - Gamification (badges, leaderboards)

3. **Security Hardening**
   - Implement RBAC (Role-Based Access Control)
   - Add API key management
   - Implement audit logging
   - Add data encryption at rest

4. **Advanced AI Features**
   - Personalized learning paths
   - Adaptive assessments
   - Multi-agent systems
   - Fine-tuned models for specific domains

---

## Glossary

**RAG:** Retrieval Augmented Generation - AI technique combining retrieval and generation

**Saga Pattern:** Distributed transaction pattern for microservices

**Vector Embedding:** Numerical representation of text for semantic search

**Idempotency:** Operation that produces same result when called multiple times

**HNSW:** Hierarchical Navigable Small World - efficient vector index algorithm

**JWT:** JSON Web Token for stateless authentication

**ORM:** Object-Relational Mapping (SQLAlchemy)

**ODM:** Object-Document Mapping (Beanie for MongoDB)

**P95 Latency:** 95th percentile response time

**Event Sourcing:** Storing state changes as events

---

## Appendix: Comparison Tables

### Python vs JavaScript Equivalents

| JavaScript | Python | Notes |
|------------|--------|-------|
| `const` | `variable =` | No const/let in Python |
| `let` | `variable =` | Variables are dynamic |
| `function() {}` | `def function():` | Use def keyword |
| `() => {}` | `lambda:` | Lambda for inline functions |
| `async/await` | `async/await` | Same! |
| `Promise` | `asyncio.Future` | Similar concepts |
| `Array.map()` | `[... for ... in ...]` | List comprehension |
| `Array.filter()` | `[... for ... in ... if ...]` | Comprehension with filter |
| `try/catch` | `try/except` | Exception handling |
| `console.log()` | `print()` | Output |
| `import` | `import` | Same! |
| `export` | No direct equivalent | Use `__all__` |
| `class` | `class` | OOP syntax similar |
| `interface` | `Protocol` (typing) | Type hints |
| `type` | `TypeAlias` | Type aliases |

---

**Good luck with your 4-week journey! 🚀**

Remember:
- Take it step by step
- Don't skip testing
- Monitor everything
- Ask questions when stuck
- Build incrementally

You've got this! 💪
