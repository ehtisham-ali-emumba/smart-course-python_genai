# SmartCourse - Week 2 Plan: Analytics Service + Agentic AI

**Date:** February 16 - 22, 2026  
**Prerequisites Completed (Week 1):** User Service, Course Service, Notification Service (FastAPI, Docker, PostgreSQL, MongoDB, Redis)

---

## Week at a Glance

| Day | Focus Area | Goal |
|-----|-----------|------|
| **Mon (Feb 16)** | Kafka Fundamentals | Understand event streaming, producers/consumers, topics, partitions |
| **Tue (Feb 17)** | Kafka + FastAPI Integration | Build Kafka producer/consumer in Python, wire into SmartCourse |
| **Wed (Feb 18)** | RabbitMQ + Celery | Learn task queues, implement Celery workers with RabbitMQ |
| **Thu (Feb 19)** | Temporal Workflows | Understand durable workflows, implement enrollment/publishing workflows |
| **Fri (Feb 20)** | Analytics Service Build | Build the analytics-service consuming Kafka events, storing metrics |
| **Sat (Feb 21)** | Agentic AI - Foundations | Learn agent architectures, tool-use, ReAct pattern, LangGraph basics |
| **Sun (Feb 22)** | Agentic AI - Hands-On | Build a working agent with tools, plan AI tutor agent for SmartCourse |

---

## Part 1: Analytics Service (Mon-Fri)

### Why These Technologies?

Your SmartCourse system design already specifies:
- **Kafka** - Event bus for streaming events (`user.events`, `course.events`, `progress.events`, etc.) to the analytics service
- **RabbitMQ + Celery** - Task queue for heavy background jobs (emails, PDF certificates, report generation)
- **Temporal** - Durable workflow orchestration for multi-step processes (enrollment workflow, course publishing workflow)

```
Services (producers) ──► Kafka (event stream) ──► Analytics Service (consumer)
                     ──► RabbitMQ (task queue) ──► Celery Workers (background jobs)
                     ──► Temporal (orchestrator) ──► Multi-step workflows with retry/compensation
```

---

### Day 1 (Mon): Kafka Fundamentals

#### What to Learn

| Concept | Why It Matters for SmartCourse |
|---------|-------------------------------|
| Topics & Partitions | You have 5 topics: `user.events`, `course.events`, `enrollment.events`, `progress.events`, `analytics.events` |
| Producers & Consumers | Services publish events, analytics-service consumes them |
| Consumer Groups | `analytics-consumer-group` reads from all topics without duplicating messages |
| Offsets & Retention | Control how long events are kept (7d for most, 30d for analytics) |
| Serialization (JSON/Avro) | How event payloads are structured |
| Docker setup (Kafka + Zookeeper/KRaft) | Running Kafka locally in your docker-compose |

#### Learning Path (4-5 hours)

1. **Watch:** [Apache Kafka in 6 Minutes](https://www.youtube.com/watch?v=Ch5VhJzaoaI) by James Cutajar (6 min) - Quick mental model
2. **Read:** [Kafka Introduction](https://kafka.apache.org/intro) - Official docs intro (30 min)
3. **Watch:** [Apache Kafka Crash Course](https://www.youtube.com/watch?v=ZJJHm_bd9Zo) by Hussein Nasser (1.5 hrs) - Deep dive with visuals
4. **Hands-on:** Spin up Kafka in Docker and produce/consume messages via CLI

#### Hands-On Exercise

Add to your `docker-compose.yml`:

```yaml
zookeeper:
  image: confluentinc/cp-zookeeper:7.6.0
  environment:
    ZOOKEEPER_CLIENT_PORT: 2181

kafka:
  image: confluentinc/cp-kafka:7.6.0
  depends_on:
    - zookeeper
  ports:
    - "9092:9092"
  environment:
    KAFKA_BROKER_ID: 1
    KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
    KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:29092,PLAINTEXT_HOST://localhost:9092
    KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT
    KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
    KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
```

Then test with CLI:

```bash
# Create a topic
docker compose exec kafka kafka-topics --create --topic user.events --bootstrap-server localhost:29092 --partitions 3

# Produce a message
docker compose exec kafka kafka-console-producer --topic user.events --bootstrap-server localhost:29092

# Consume messages
docker compose exec kafka kafka-console-consumer --topic user.events --from-beginning --bootstrap-server localhost:29092
```

#### Checkpoint

You should be able to answer:
- What is the difference between a topic and a partition?
- Why do consumer groups matter?
- What happens when a consumer goes down and comes back?

---

### Day 2 (Tue): Kafka + Python/FastAPI Integration

#### What to Learn

| Concept | Details |
|---------|---------|
| `aiokafka` library | Async Kafka client for Python (fits FastAPI's async model) |
| Producer pattern | How your user-service/course-service will publish events |
| Consumer pattern | How analytics-service will consume events in the background |
| Event schema design | Standardized event envelope: `{event_type, timestamp, service, payload}` |
| Error handling | Dead letter topics, retry logic |

#### Learning Path (5-6 hours)

1. **Read:** [aiokafka Documentation](https://aiokafka.readthedocs.io/en/stable/) - Quick start section (1 hr)
2. **Watch:** [Python Kafka Tutorial](https://www.youtube.com/watch?v=LHNtL-NMNr4) by Ssali Jonathan (45 min) - Python producer/consumer
3. **Build:** Create a shared Kafka producer utility and a standalone consumer script

#### Hands-On: Build the Event Producer (shared utility)

```python
# shared/shared/events/producer.py
from aiokafka import AIOKafkaProducer
import json

class EventProducer:
    def __init__(self, bootstrap_servers: str = "kafka:29092"):
        self.producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )

    async def start(self):
        await self.producer.start()

    async def stop(self):
        await self.producer.stop()

    async def publish(self, topic: str, event_type: str, payload: dict):
        event = {
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "payload": payload,
        }
        await self.producer.send_and_wait(topic, value=event)
```

#### Hands-On: Build the Event Consumer

```python
# A consumer that analytics-service will run
from aiokafka import AIOKafkaConsumer
import json

async def consume_events():
    consumer = AIOKafkaConsumer(
        "user.events", "course.events", "enrollment.events", "progress.events",
        bootstrap_servers="kafka:29092",
        group_id="analytics-consumer-group",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    )
    await consumer.start()
    try:
        async for msg in consumer:
            await process_event(msg.topic, msg.value)
    finally:
        await consumer.stop()
```

#### Checkpoint

You should be able to:
- Publish an event from user-service when a user registers
- Consume that event in a standalone Python script
- See the full event flow: `service → Kafka → consumer`

---

### Day 3 (Wed): RabbitMQ + Celery for Background Tasks

#### What to Learn

| Concept | Why It Matters for SmartCourse |
|---------|-------------------------------|
| RabbitMQ basics | Message broker for task queues (emails, PDFs, reports) |
| Celery fundamentals | Distributed task queue framework in Python |
| Queues: `email_queue`, `certificate_queue`, `report_queue` | Your system design specifies these |
| Retry policies | Exponential backoff (60s, 300s, 900s) as per your design |
| Dead letter queues | Failed tasks go to DLQ for manual inspection |
| Celery + FastAPI integration | Triggering background tasks from your API endpoints |

#### Kafka vs RabbitMQ - When to Use Which

| | Kafka | RabbitMQ |
|--|-------|----------|
| **Pattern** | Event streaming (pub/sub) | Task queue (work distribution) |
| **Use in SmartCourse** | Broadcasting events to multiple consumers | Distributing work items to workers |
| **Example** | `user.registered` event → analytics + notification | `send_welcome_email` task → one worker picks it up |
| **Retention** | Messages persist (days/weeks) | Messages deleted after consumption |
| **Replay** | Can replay from any offset | No replay after acknowledgment |

#### Learning Path (5-6 hours)

1. **Watch:** [RabbitMQ in 5 Minutes](https://www.youtube.com/watch?v=deG25y_r6OY) (5 min) - Quick overview
2. **Read:** [RabbitMQ Tutorials](https://www.rabbitmq.com/tutorials) - Do tutorials 1-3 (Python/Pika) (1.5 hrs)
3. **Watch:** [Celery with FastAPI](https://www.youtube.com/watch?v=mcX_4EvYka4) by BugBytes (30 min)
4. **Read:** [Celery First Steps](https://docs.celeryq.dev/en/stable/getting-started/first-steps-with-celery.html) (1 hr)
5. **Build:** Set up Celery worker with RabbitMQ, create email and report tasks

#### Hands-On: Docker Setup

```yaml
rabbitmq:
  image: rabbitmq:3.13-management
  ports:
    - "5672:5672"
    - "15672:15672"  # Management UI
  environment:
    RABBITMQ_DEFAULT_USER: smartcourse
    RABBITMQ_DEFAULT_PASS: smartcourse
```

#### Hands-On: Celery Worker

```python
# services/notification-service/src/notification_service/worker.py
from celery import Celery

celery_app = Celery(
    "smartcourse",
    broker="amqp://smartcourse:smartcourse@rabbitmq:5672//",
    backend="redis://redis:6379/1",
)

celery_app.conf.task_routes = {
    "tasks.send_email": {"queue": "email_queue"},
    "tasks.generate_report": {"queue": "report_queue"},
    "tasks.generate_certificate": {"queue": "certificate_queue"},
}

celery_app.conf.task_default_retry_delay = 60
celery_app.conf.task_max_retries = 3

@celery_app.task(bind=True, max_retries=3)
def send_welcome_email(self, user_id: int, email: str):
    try:
        # send email logic
        pass
    except Exception as exc:
        self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
```

#### Checkpoint

You should be able to:
- Access RabbitMQ management UI at `localhost:15672`
- Trigger a Celery task from a FastAPI endpoint
- See the task execute in a Celery worker log
- Understand when to use Kafka (events) vs RabbitMQ (tasks)

---

### Day 4 (Thu): Temporal Workflows

#### What to Learn

| Concept | Why It Matters for SmartCourse |
|---------|-------------------------------|
| Workflows | Long-running, durable processes (CoursePublishingWorkflow, EnrollmentWorkflow) |
| Activities | Individual steps within a workflow (validate_course, initialize_progress, etc.) |
| Compensation (Saga pattern) | Rollback on failure (e.g., revert course status if publishing fails) |
| Retry policies | Built-in retry with exponential backoff per activity |
| Temporal Server + UI | Run locally via Docker, monitor workflows in the web UI |
| Python SDK (`temporalio`) | Official Python SDK for defining workflows and activities |

#### Learning Path (5-6 hours)

1. **Watch:** [Temporal in 7 Minutes](https://www.youtube.com/watch?v=2HjnQlnA5eY) by Temporal (7 min) - Core concepts
2. **Read:** [Temporal Core Concepts](https://docs.temporal.io/concepts) - Workflows, Activities, Task Queues (1 hr)
3. **Watch:** [Temporal with Python - Full Tutorial](https://www.youtube.com/watch?v=GpbOkDjpeYU) by Temporal (1 hr)
4. **Read:** [Temporal Python SDK Guide](https://docs.temporal.io/develop/python) (1 hr)
5. **Build:** Implement EnrollmentWorkflow with activities

#### Hands-On: Docker Setup

```yaml
temporal:
  image: temporalio/auto-setup:1.24
  ports:
    - "7233:7233"
  environment:
    - DB=postgresql
    - DB_PORT=5432
    - POSTGRES_USER=temporal
    - POSTGRES_PWD=temporal
    - POSTGRES_SEEDS=temporal-db

temporal-ui:
  image: temporalio/ui:2.26.2
  ports:
    - "8233:8080"
  environment:
    - TEMPORAL_ADDRESS=temporal:7233

temporal-db:
  image: postgres:16-alpine
  environment:
    POSTGRES_USER: temporal
    POSTGRES_PASSWORD: temporal
```

#### Hands-On: Enrollment Workflow

```python
# services/course-service/src/course_service/workflows/enrollment.py
from temporalio import workflow, activity
from datetime import timedelta

@activity.defn
async def initialize_progress(enrollment_id: int) -> dict:
    # Create progress record, set all modules to NOT_STARTED
    return {"progress_id": 1, "status": "initialized"}

@activity.defn
async def update_analytics(enrollment_id: int) -> dict:
    # Publish enrollment event to Kafka for analytics
    return {"updated": True}

@activity.defn
async def activate_enrollment(enrollment_id: int) -> dict:
    # Set enrollment status to ACTIVE
    return {"status": "active"}

@activity.defn
async def send_welcome_notification(enrollment_id: int) -> dict:
    # Queue welcome email via Celery
    return {"notified": True}

@workflow.defn
class EnrollmentWorkflow:
    @workflow.run
    async def run(self, enrollment_id: int) -> dict:
        # Step 1: Initialize progress tracking
        progress = await workflow.execute_activity(
            initialize_progress,
            enrollment_id,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        # Step 2: Update analytics counters
        await workflow.execute_activity(
            update_analytics, enrollment_id,
            start_to_close_timeout=timedelta(seconds=30),
        )

        # Step 3: Activate the enrollment
        await workflow.execute_activity(
            activate_enrollment, enrollment_id,
            start_to_close_timeout=timedelta(seconds=10),
        )

        # Step 4: Send welcome notification
        await workflow.execute_activity(
            send_welcome_notification, enrollment_id,
            start_to_close_timeout=timedelta(seconds=30),
        )

        return {"enrollment_id": enrollment_id, "status": "completed"}
```

#### Checkpoint

You should be able to:
- See Temporal UI at `localhost:8233`
- Trigger a workflow from a FastAPI endpoint
- Watch the workflow execute step-by-step in the Temporal UI
- Understand how compensation works when an activity fails

---

### Day 5 (Fri): Build the Analytics Service

#### What to Build

The analytics-service (port 8008) that:
1. Consumes Kafka events from all topics
2. Aggregates metrics into PostgreSQL
3. Exposes REST endpoints for dashboard data

#### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   ANALYTICS SERVICE (:8008)              │
│                                                         │
│  ┌──────────────┐   ┌──────────────┐   ┌─────────────┐ │
│  │ Kafka        │   │ Event        │   │ FastAPI     │ │
│  │ Consumer     │──►│ Processor    │──►│ Endpoints   │ │
│  │ (background) │   │ (aggregate)  │   │ (REST API)  │ │
│  └──────────────┘   └──────┬───────┘   └─────────────┘ │
│                            │                            │
│                     ┌──────▼───────┐                    │
│                     │  PostgreSQL  │                    │
│                     │  (metrics)   │                    │
│                     └──────────────┘                    │
└─────────────────────────────────────────────────────────┘
```

#### Service Structure

```
services/analytics-service/
├── Dockerfile
├── pyproject.toml
└── src/
    └── analytics_service/
        ├── main.py                  # FastAPI app + Kafka consumer startup
        ├── config.py                # Settings
        ├── api/
        │   └── analytics.py         # REST endpoints for dashboard
        ├── consumers/
        │   └── event_consumer.py    # Kafka consumer logic
        ├── services/
        │   └── metrics.py           # Business logic for aggregation
        ├── repositories/
        │   └── metrics.py           # DB queries
        ├── models/
        │   └── metrics.py           # SQLAlchemy models
        └── schemas/
            └── analytics.py         # Pydantic response schemas
```

#### Metrics to Track (from System Design)

| Metric | Type | Aggregation |
|--------|------|-------------|
| `total_students` | Gauge | Real-time |
| `total_instructors` | Gauge | Real-time |
| `total_courses_published` | Gauge | Real-time |
| `new_enrollments` | Counter | Daily/Weekly/Monthly |
| `course_completion_rate` | Gauge | Daily |
| `avg_time_to_complete` | Gauge | Daily |
| `popular_courses` | List | Daily |

#### REST Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/analytics/dashboard` | Overview metrics (totals, rates) |
| GET | `/analytics/enrollments?period=weekly` | Enrollment trends |
| GET | `/analytics/courses/popular` | Popular courses list |
| GET | `/analytics/completion-rates` | Completion rate by course |

#### Checkpoint

By end of Friday you should have:
- Analytics service running in Docker alongside Kafka
- Events flowing from existing services → Kafka → analytics-service
- Dashboard endpoint returning real aggregated data

---

## Part 2: Agentic AI (Sat-Sun)

### Why Agentic AI?

Your SmartCourse platform's next phase will include an AI tutor that can:
- Answer student questions about course content
- Recommend courses based on progress
- Generate quizzes and assessments
- Provide personalized learning paths

Agentic AI = LLMs that can **reason**, **plan**, **use tools**, and **take actions** autonomously.

---

### Day 6 (Sat): Agentic AI Foundations

#### What to Learn

| Concept | Description |
|---------|-------------|
| What is an AI Agent? | LLM + Memory + Tools + Planning loop |
| ReAct Pattern | Reason → Act → Observe → Repeat |
| Tool Use / Function Calling | LLM decides which function to call and with what args |
| Agent Architectures | Single agent, multi-agent, supervisor pattern |
| LangChain vs LangGraph | Chain = linear pipeline, Graph = stateful agent with cycles |
| Memory (short-term & long-term) | Conversation buffer, vector store retrieval |
| RAG (Retrieval-Augmented Generation) | Retrieve relevant docs → feed to LLM → generate answer |

#### Learning Path (5-6 hours)

1. **Watch:** [What are AI Agents?](https://www.youtube.com/watch?v=F8NKVhkZZWI) by IBM Technology (10 min) - Mental model
2. **Read:** [LLM Powered Autonomous Agents](https://lilianweng.github.io/posts/2023-06-23-agent/) by Lilian Weng (1 hr) - The definitive blog post on agent architecture
3. **Watch:** [LangGraph Tutorial - Build AI Agents](https://www.youtube.com/watch?v=R8KB-Zcynxc) by freeCodeCamp (2 hrs) - Full hands-on LangGraph tutorial
4. **Read:** [LangGraph Conceptual Guide](https://langchain-ai.github.io/langgraph/concepts/) (1 hr)
5. **Read:** [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling) (30 min) - Understand tool-use at the API level

#### Key Concepts to Internalize

**The Agent Loop:**

```
User Query
    │
    ▼
┌─────────────────────────────────────┐
│          LLM (the "brain")          │
│                                     │
│  Thinks: "I need to look up the     │
│  student's progress first"          │
│                                     │
│  Action: call get_progress(user=42) │
└──────────────────┬──────────────────┘
                   │
                   ▼
          ┌────────────────┐
          │  Tool Execution │ ◄── get_progress(user=42) → {completion: 65%}
          └────────┬───────┘
                   │
                   ▼
┌─────────────────────────────────────┐
│          LLM (observes result)      │
│                                     │
│  Thinks: "Student is 65% done,     │
│  let me check which modules are    │
│  incomplete"                        │
│                                     │
│  Action: call get_modules(...)      │
└──────────────────┬──────────────────┘
                   │
              ... (loop continues until LLM has enough info) ...
                   │
                   ▼
         Final Answer to User
```

**Single Agent vs Multi-Agent:**

```
Single Agent (start here):
  User ──► Agent (has all tools) ──► Response

Multi-Agent (advanced):
  User ──► Supervisor Agent
               ├──► Tutor Agent (answers questions)
               ├──► Quiz Agent (generates quizzes)
               └──► Recommender Agent (suggests courses)
```

#### Checkpoint

You should be able to explain:
- How does an agent differ from a simple ChatGPT prompt?
- What is the ReAct loop?
- When would you use a single agent vs multi-agent system?
- What role does RAG play in an AI tutor?

---

### Day 7 (Sun): Agentic AI Hands-On

#### What to Build

A minimal working AI agent with tools, as a prototype for SmartCourse's AI tutor.

#### Learning Path (5-6 hours)

1. **Follow:** [LangGraph Quick Start](https://langchain-ai.github.io/langgraph/tutorials/introduction/) (1.5 hrs) - Build your first agent
2. **Watch:** [RAG from Scratch](https://www.youtube.com/watch?v=sVcwVQRHIc8) by LangChain (1 hr) - Full RAG pipeline
3. **Build:** A prototype agent with 2-3 tools (3 hrs)

#### Hands-On: Build a SmartCourse Tutor Agent Prototype

```python
# Minimal agent prototype using LangGraph
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool

# Define tools the agent can use
@tool
def get_student_progress(student_id: int, course_id: int) -> str:
    """Get a student's progress in a specific course."""
    # In production, this calls your course-service API
    return f"Student {student_id} is 65% complete in course {course_id}. Modules completed: 3/5."

@tool
def search_course_content(query: str, course_id: int) -> str:
    """Search course materials to answer a student's question."""
    # In production, this does RAG over course content in MongoDB
    return f"Found relevant content for '{query}': [Module 3: Advanced Concepts - Section 3.2]"

@tool
def get_recommended_courses(student_id: int) -> str:
    """Get course recommendations based on student's history."""
    return "Recommended: 1) Advanced Python (matches your interests), 2) Data Structures (prerequisite gap)"

# Create the agent
llm = ChatOpenAI(model="gpt-4o-mini")
llm_with_tools = llm.bind_tools([get_student_progress, search_course_content, get_recommended_courses])

def agent_node(state: MessagesState):
    return {"messages": [llm_with_tools.invoke(state["messages"])]}

# Build the graph
graph = StateGraph(MessagesState)
graph.add_node("agent", agent_node)
graph.add_node("tools", ToolNode([get_student_progress, search_course_content, get_recommended_courses]))

graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", tools_condition)
graph.add_edge("tools", "agent")

agent = graph.compile()

# Run it
response = agent.invoke({"messages": [("user", "How am I doing in course 101?")]})
```

#### What to Plan for SmartCourse AI Service (Week 3+)

| Component | Technology | Purpose |
|-----------|-----------|---------|
| AI Service | FastAPI (:8009) | Host the AI tutor agent |
| Vector DB | Qdrant or pgvector | Store course content embeddings for RAG |
| LLM Provider | OpenAI API / Ollama (local) | The agent's brain |
| Agent Framework | LangGraph | Stateful agent with tool-use |
| Embedding Model | OpenAI `text-embedding-3-small` | Convert course content to vectors |

---

## Curated Resources

### Kafka

| Resource | Type | Cost | Time | Link |
|----------|------|------|------|------|
| Apache Kafka Crash Course - Hussein Nasser | Video | Free | 1.5 hrs | [YouTube](https://www.youtube.com/watch?v=ZJJHm_bd9Zo) |
| Kafka: The Definitive Guide (Ch 1-4) | Book | Free (Confluent) | 3 hrs | [Confluent](https://www.confluent.io/resources/kafka-the-definitive-guide-v2/) |
| aiokafka Documentation | Docs | Free | 1 hr | [ReadTheDocs](https://aiokafka.readthedocs.io/en/stable/) |
| Confluent Kafka 101 Course | Course | Free | 2 hrs | [Confluent Developer](https://developer.confluent.io/courses/apache-kafka/events/) |
| Kafka for Python Developers (Udemy - Stephane Maarek) | Course | Paid (~$15) | 5 hrs | [Udemy](https://www.udemy.com/course/apache-kafka-series-kafka-from-beginner-to-intermediate/) |

### RabbitMQ + Celery

| Resource | Type | Cost | Time | Link |
|----------|------|------|------|------|
| RabbitMQ Official Tutorials (1-3) | Tutorial | Free | 2 hrs | [RabbitMQ](https://www.rabbitmq.com/tutorials) |
| Celery First Steps | Docs | Free | 1 hr | [Celery Docs](https://docs.celeryq.dev/en/stable/getting-started/first-steps-with-celery.html) |
| Celery with FastAPI - BugBytes | Video | Free | 30 min | [YouTube](https://www.youtube.com/watch?v=mcX_4EvYka4) |
| Celery Best Practices | Blog | Free | 30 min | [DenisHaskin](https://denibertovic.com/posts/celery-best-practices/) |

### Temporal Workflows

| Resource | Type | Cost | Time | Link |
|----------|------|------|------|------|
| Temporal in 7 Minutes | Video | Free | 7 min | [YouTube](https://www.youtube.com/watch?v=2HjnQlnA5eY) |
| Temporal Concepts | Docs | Free | 1 hr | [Temporal Docs](https://docs.temporal.io/concepts) |
| Temporal Python SDK Guide | Docs | Free | 1.5 hrs | [Temporal Docs](https://docs.temporal.io/develop/python) |
| Temporal with Python - Full Tutorial | Video | Free | 1 hr | [YouTube](https://www.youtube.com/watch?v=GpbOkDjpeYU) |
| Building Reliable Distributed Systems (Temporal Blog) | Blog | Free | 30 min | [Temporal Blog](https://temporal.io/blog) |
| Temporal 101 with Python (Official Course) | Course | Free | 4 hrs | [Temporal Learn](https://learn.temporal.io/courses/temporal_101/python/) |

### Agentic AI

| Resource | Type | Cost | Time | Link |
|----------|------|------|------|------|
| LLM Powered Autonomous Agents - Lilian Weng | Blog | Free | 1 hr | [Lil'Log](https://lilianweng.github.io/posts/2023-06-23-agent/) |
| LangGraph Conceptual Guide | Docs | Free | 1 hr | [LangGraph Docs](https://langchain-ai.github.io/langgraph/concepts/) |
| LangGraph Quick Start Tutorial | Tutorial | Free | 1.5 hrs | [LangGraph Docs](https://langchain-ai.github.io/langgraph/tutorials/introduction/) |
| LangGraph Full Course - freeCodeCamp | Video | Free | 2 hrs | [YouTube](https://www.youtube.com/watch?v=R8KB-Zcynxc) |
| OpenAI Function Calling Guide | Docs | Free | 30 min | [OpenAI Docs](https://platform.openai.com/docs/guides/function-calling) |
| RAG from Scratch - LangChain | Video | Free | 1 hr | [YouTube](https://www.youtube.com/watch?v=sVcwVQRHIc8) |
| AI Agents in LangGraph (DeepLearning.AI) | Course | Free | 3 hrs | [DeepLearning.AI](https://www.deeplearning.ai/short-courses/ai-agents-in-langgraph/) |
| Building Agentic RAG with LlamaIndex (DeepLearning.AI) | Course | Free | 2 hrs | [DeepLearning.AI](https://www.deeplearning.ai/short-courses/building-agentic-rag-with-llamaindex/) |
| Crew AI Course - Multi-Agent Systems (DeepLearning.AI) | Course | Free | 2 hrs | [DeepLearning.AI](https://www.deeplearning.ai/short-courses/multi-ai-agent-systems-with-crewai/) |

---

## Daily Routine Template

```
09:00 - 10:30  │  Theory (videos/reading from resources above)
10:30 - 10:45  │  Break
10:45 - 12:30  │  Guided tutorial / following along
12:30 - 13:30  │  Lunch
13:30 - 16:00  │  Hands-on building (apply to SmartCourse)
16:00 - 16:30  │  Review checkpoint questions, fill gaps
16:30 - 17:00  │  Document what you learned, push code
```

---

## Success Criteria

By end of Week 2, you should have:

- [ ] Kafka running in Docker, events flowing between services
- [ ] RabbitMQ + Celery handling background email/report tasks
- [ ] At least one Temporal workflow (EnrollmentWorkflow) executing end-to-end
- [ ] Analytics service consuming events and serving dashboard data
- [ ] A working prototype AI agent with tools (local script)
- [ ] Clear understanding of where agentic AI fits in SmartCourse (AI tutor service plan)
- [ ] All new infrastructure added to `docker-compose.yml`

---

*Document Version: 1.0 | Created: February 16, 2026*
