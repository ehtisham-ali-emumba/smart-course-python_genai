# SmartCourse: Final Architecture Tree & Communication Flow

**Last Updated:** February 9, 2026

---

## Complete Project Structure

```
smart-course/
│
├── docker-compose.yml              # All infrastructure + services
├── .env                            # Environment variables
├── README.md
│
├── infrastructure/                 # Shared configs
│   ├── kafka/
│   │   └── schema-registry/        # Event schemas
│   ├── temporal/
│   │   └── workflows/              # Shared workflow definitions
│   └── monitoring/
│       ├── prometheus.yml
│       └── grafana/
│           └── dashboards/
│
├── services/                       # All microservices
│   │
│   ├── api-gateway/               # Entry point (Port 8000)
│   │   ├── main.py
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── routers/
│   │   │   ├── auth_routes.py      # → User Service
│   │   │   ├── course_routes.py    # → Course Service
│   │   │   ├── enrollment_routes.py # → Enrollment Service
│   │   │   └── progress_routes.py  # → Progress Service
│   │   └── middleware/
│   │       ├── auth.py             # JWT verification
│   │       └── rate_limit.py       # Rate limiting with Redis
│   │
│   ├── user-service/              # User management (Port 8001)
│   │   ├── main.py
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── models/
│   │   │   └── user.py             # SQLAlchemy model
│   │   ├── schemas/
│   │   │   └── user.py             # Pydantic schemas
│   │   ├── routers/
│   │   │   └── auth.py             # POST /register, /login
│   │   ├── services/
│   │   │   └── user_service.py     # Business logic
│   │   ├── database.py             # PostgreSQL connection
│   │   └── utils/
│   │       └── jwt.py              # Token generation
│   │
│   ├── course-service/            # Course management (Port 8002)
│   │   ├── main.py
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── models/
│   │   │   └── course.py           # SQLAlchemy (PostgreSQL)
│   │   ├── documents/
│   │   │   └── course_content.py   # Beanie (MongoDB)
│   │   ├── schemas/
│   │   │   └── course.py
│   │   ├── routers/
│   │   │   ├── courses.py          # GET/POST/PUT courses
│   │   │   └── publish.py          # POST /courses/{id}/publish
│   │   ├── services/
│   │   │   ├── course_service.py
│   │   │   └── publish_service.py  # Triggers Temporal workflow
│   │   ├── database.py             # PostgreSQL + MongoDB
│   │   ├── kafka_producer.py       # Publish events
│   │   └── temporal_client.py      # Workflow client
│   │
│   ├── enrollment-service/        # Enrollment logic (Port 8003)
│   │   ├── main.py
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── models/
│   │   │   └── enrollment.py       # SQLAlchemy
│   │   ├── schemas/
│   │   │   └── enrollment.py
│   │   ├── routers/
│   │   │   └── enrollments.py      # POST /enroll, GET /my-courses
│   │   ├── services/
│   │   │   └── enrollment_service.py # ACID transactions
│   │   ├── database.py             # PostgreSQL connection
│   │   ├── kafka_producer.py       # Publish enrollment.created
│   │   └── temporal_client.py      # Start enrollment workflow
│   │
│   ├── progress-service/          # Progress tracking (Port 8004)
│   │   ├── main.py
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── models/
│   │   │   └── progress.py         # SQLAlchemy
│   │   ├── schemas/
│   │   │   └── progress.py
│   │   ├── routers/
│   │   │   └── progress.py         # POST /lessons/{id}/complete
│   │   ├── services/
│   │   │   └── progress_service.py
│   │   ├── database.py             # PostgreSQL connection
│   │   ├── redis_client.py         # Cache progress data
│   │   └── kafka_producer.py       # Publish progress.updated
│   │
│   ├── notification-service/      # Notifications (Port 8005)
│   │   ├── main.py
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── consumers/
│   │   │   └── kafka_consumer.py   # Listen to events
│   │   ├── tasks/
│   │   │   └── celery_tasks.py     # Send emails, SMS
│   │   ├── services/
│   │   │   ├── email_service.py
│   │   │   └── sms_service.py
│   │   └── config.py
│   │
│   ├── content-service/           # Content processing (Port 8006)
│   │   ├── main.py
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── documents/
│   │   │   └── content_chunk.py    # Beanie (MongoDB)
│   │   ├── services/
│   │   │   ├── extraction_service.py # Extract text from videos/PDFs
│   │   │   ├── embedding_service.py  # Generate embeddings
│   │   │   └── vector_service.py     # Store in Qdrant
│   │   ├── database.py             # MongoDB connection
│   │   ├── qdrant_client.py        # Vector DB client
│   │   └── openai_client.py        # OpenAI API
│   │
│   ├── ai-assistant-service/      # AI Q&A (Port 8007)
│   │   ├── main.py
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── routers/
│   │   │   └── chat.py             # POST /ask
│   │   ├── services/
│   │   │   ├── rag_service.py      # RAG pipeline
│   │   │   └── llm_service.py      # LLM integration
│   │   ├── documents/
│   │   │   └── conversation.py     # Beanie (MongoDB)
│   │   ├── qdrant_client.py        # Retrieve similar chunks
│   │   ├── openai_client.py        # GPT-4 API
│   │   └── database.py             # MongoDB
│   │
│   └── analytics-service/         # Analytics (Port 8008)
│       ├── main.py
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── consumers/
│       │   └── kafka_consumer.py   # All events
│       ├── models/
│       │   └── analytics.py        # SQLAlchemy
│       ├── routers/
│       │   └── reports.py          # GET /reports/enrollments
│       ├── services/
│       │   └── analytics_service.py
│       └── database.py             # PostgreSQL
│
├── workers/                        # Background processors
│   │
│   ├── celery-workers/            # Task workers
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── worker.py               # Celery worker process
│   │   ├── tasks/
│   │   │   ├── email_tasks.py      # send_welcome_email
│   │   │   ├── sms_tasks.py
│   │   │   └── report_tasks.py
│   │   └── config.py               # RabbitMQ connection
│   │
│   └── temporal-workers/          # Workflow workers
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── worker.py               # Temporal worker process
│       ├── workflows/
│       │   ├── course_publish_workflow.py
│       │   ├── enrollment_workflow.py
│       │   └── content_process_workflow.py
│       ├── activities/
│       │   ├── course_activities.py
│       │   ├── enrollment_activities.py
│       │   └── content_activities.py
│       └── config.py               # Temporal connection
│
├── shared/                         # Shared libraries
│   ├── __init__.py
│   ├── schemas/
│   │   └── events.py               # Kafka event schemas
│   ├── database/
│   │   ├── postgres.py             # Shared DB utils
│   │   └── mongodb.py
│   └── utils/
│       ├── logging.py
│       └── metrics.py              # Prometheus metrics
│
└── migrations/                     # Database migrations
    ├── alembic.ini
    ├── env.py
    └── versions/
        ├── 001_create_users_table.py
        ├── 002_create_courses_table.py
        ├── 003_create_enrollments_table.py
        └── 004_create_progress_table.py
```

---

## Docker Compose Structure

```yaml
# docker-compose.yml

version: "3.8"

services:
  # ============ INFRASTRUCTURE LAYER ============

  postgres:
    image: postgres:15
    container_name: smartcourse-postgres
    environment:
      POSTGRES_DB: smartcourse
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  mongodb:
    image: mongo:7
    container_name: smartcourse-mongodb
    ports:
      - "27017:27017"
    volumes:
      - mongodb_data:/data/db

  redis:
    image: redis:7-alpine
    container_name: smartcourse-redis
    ports:
      - "6379:6379"

  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    container_name: smartcourse-zookeeper
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    container_name: smartcourse-kafka
    depends_on:
      - zookeeper
    ports:
      - "9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092

  rabbitmq:
    image: rabbitmq:3-management
    container_name: smartcourse-rabbitmq
    ports:
      - "5672:5672" # AMQP
      - "15672:15672" # Management UI

  temporal:
    image: temporalio/auto-setup:latest
    container_name: smartcourse-temporal
    depends_on:
      - postgres
    ports:
      - "7233:7233" # gRPC
      - "8233:8233" # Web UI
    environment:
      - DB=postgresql
      - DB_PORT=5432
      - POSTGRES_USER=postgres
      - POSTGRES_PWD=password
      - POSTGRES_SEEDS=postgres

  qdrant:
    image: qdrant/qdrant:latest
    container_name: smartcourse-qdrant
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

  # ============ MICROSERVICES LAYER ============

  api-gateway:
    build: ./services/api-gateway
    container_name: smartcourse-api-gateway
    ports:
      - "8000:8000"
    environment:
      - USER_SERVICE_URL=http://user-service:8000
      - COURSE_SERVICE_URL=http://course-service:8000
      - ENROLLMENT_SERVICE_URL=http://enrollment-service:8000
      - PROGRESS_SERVICE_URL=http://progress-service:8000
      - REDIS_URL=redis://redis:6379
    depends_on:
      - redis

  user-service:
    build: ./services/user-service
    container_name: smartcourse-user-service
    ports:
      - "8001:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:password@postgres:5432/smartcourse
      - REDIS_URL=redis://redis:6379
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
    depends_on:
      - postgres
      - redis
      - kafka

  course-service:
    build: ./services/course-service
    container_name: smartcourse-course-service
    ports:
      - "8002:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:password@postgres:5432/smartcourse
      - MONGODB_URL=mongodb://mongodb:27017
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
      - TEMPORAL_HOST=temporal:7233
    depends_on:
      - postgres
      - mongodb
      - kafka
      - temporal

  enrollment-service:
    build: ./services/enrollment-service
    container_name: smartcourse-enrollment-service
    ports:
      - "8003:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:password@postgres:5432/smartcourse
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
      - TEMPORAL_HOST=temporal:7233
    depends_on:
      - postgres
      - kafka
      - temporal

  progress-service:
    build: ./services/progress-service
    container_name: smartcourse-progress-service
    ports:
      - "8004:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:password@postgres:5432/smartcourse
      - REDIS_URL=redis://redis:6379
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
    depends_on:
      - postgres
      - redis
      - kafka

  notification-service:
    build: ./services/notification-service
    container_name: smartcourse-notification-service
    ports:
      - "8005:8000"
    environment:
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
      - RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
    depends_on:
      - kafka
      - rabbitmq

  content-service:
    build: ./services/content-service
    container_name: smartcourse-content-service
    ports:
      - "8006:8000"
    environment:
      - MONGODB_URL=mongodb://mongodb:27017
      - QDRANT_HOST=qdrant
      - QDRANT_PORT=6333
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      - mongodb
      - qdrant

  ai-assistant-service:
    build: ./services/ai-assistant-service
    container_name: smartcourse-ai-assistant-service
    ports:
      - "8007:8000"
    environment:
      - MONGODB_URL=mongodb://mongodb:27017
      - QDRANT_HOST=qdrant
      - QDRANT_PORT=6333
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      - mongodb
      - qdrant

  analytics-service:
    build: ./services/analytics-service
    container_name: smartcourse-analytics-service
    ports:
      - "8008:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:password@postgres:5432/smartcourse
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
    depends_on:
      - postgres
      - kafka

  # ============ WORKERS LAYER ============

  celery-worker:
    build: ./workers/celery-workers
    container_name: smartcourse-celery-worker
    command: celery -A worker worker --loglevel=info --concurrency=4
    environment:
      - RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
    depends_on:
      - rabbitmq
    deploy:
      replicas: 3 # 3 worker instances

  temporal-worker:
    build: ./workers/temporal-workers
    container_name: smartcourse-temporal-worker
    command: python worker.py
    environment:
      - TEMPORAL_HOST=temporal:7233
      - DATABASE_URL=postgresql://postgres:password@postgres:5432/smartcourse
      - MONGODB_URL=mongodb://mongodb:27017
    depends_on:
      - temporal
      - postgres
      - mongodb
    deploy:
      replicas: 2 # 2 worker instances

  # ============ MONITORING ============

  prometheus:
    image: prom/prometheus:latest
    container_name: smartcourse-prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./infrastructure/monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus

  grafana:
    image: grafana/grafana:latest
    container_name: smartcourse-grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana_data:/var/lib/grafana
      - ./infrastructure/monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
    depends_on:
      - prometheus

volumes:
  postgres_data:
  mongodb_data:
  qdrant_data:
  prometheus_data:
  grafana_data:
```

---

## Service Communication Patterns

### **Pattern 1: Synchronous (REST)**

```
Client
  │
  └──→ API Gateway (Port 8000)
         │
         ├──→ User Service (Port 8001)      [GET /users, POST /login]
         ├──→ Course Service (Port 8002)    [GET /courses, POST /courses]
         ├──→ Enrollment Service (Port 8003) [POST /enroll]
         └──→ Progress Service (Port 8004)  [POST /progress/complete]
```

**Example Flow:**

```
1. Client → GET /api/courses
2. API Gateway → Course Service: GET http://course-service:8000/courses
3. Course Service queries PostgreSQL
4. Course Service returns JSON
5. API Gateway returns to Client
```

---

### **Pattern 2: Asynchronous (Kafka Events)**

```
Enrollment Service
  │
  └──→ Kafka Topic: "enrollment.created"
         │
         ├──→ Progress Service (Consumer)
         │      └──→ Initialize progress in PostgreSQL
         │
         ├──→ Notification Service (Consumer)
         │      └──→ Queue email task in RabbitMQ
         │
         └──→ Analytics Service (Consumer)
                └──→ Update enrollment count in PostgreSQL
```

**Example Flow:**

```
1. Student enrolls via API
2. Enrollment Service creates record in PostgreSQL
3. Enrollment Service publishes to Kafka:
   {
     "event": "enrollment.created",
     "user_id": 123,
     "course_id": 456
   }
4. Progress Service receives event → initializes progress
5. Notification Service receives event → queues welcome email
6. Analytics Service receives event → updates metrics
```

---

### **Pattern 3: Background Tasks (RabbitMQ + Celery)**

```
Notification Service
  │
  └──→ RabbitMQ Queue: "email_queue"
         │
         └──→ Celery Worker (3 instances)
                ├──→ Worker 1: Sending email to user@example.com
                ├──→ Worker 2: Sending SMS to +1234567890
                └──→ Worker 3: Idle (waiting for tasks)
```

**Example Flow:**

```
1. Notification Service receives Kafka event
2. Queue task: send_welcome_email.delay(user_id)
3. Task goes to RabbitMQ queue
4. Celery Worker picks up task
5. Worker sends email via SMTP/SendGrid
6. Worker marks task complete
```

---

### **Pattern 4: Workflows (Temporal)**

```
Course Service
  │
  └──→ Temporal Server
         │
         └──→ Temporal Worker (executes workflow)
                │
                ├──→ Activity 1: Validate course (PostgreSQL)
                ├──→ Activity 2: Save content (MongoDB)
                ├──→ Activity 3: Upload files (S3)
                ├──→ Activity 4: Extract text (Content Service)
                ├──→ Activity 5: Generate embeddings (OpenAI API)
                ├──→ Activity 6: Store in Qdrant
                └──→ Activity 7: Mark published (PostgreSQL)
```

**Example Flow:**

```
1. Instructor clicks "Publish Course"
2. Course Service starts Temporal workflow
3. Temporal Worker executes activities sequentially
4. Each activity can retry on failure
5. Workflow survives server crashes
6. Frontend polls workflow status
```

---

## Complete Data Flow Examples

### **Flow 1: Student Enrolls in Course**

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Client sends POST /api/courses/123/enroll                │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. API Gateway forwards to Enrollment Service               │
│    POST http://enrollment-service:8000/enroll               │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Enrollment Service (ACID Transaction)                    │
│    - Check if already enrolled (PostgreSQL)                 │
│    - Check course capacity (PostgreSQL)                     │
│    - Create enrollment record (PostgreSQL)                  │
│    - Publish event to Kafka: "enrollment.created"           │
│    - Start Temporal workflow: EnrollmentWorkflow            │
│    - Return enrollment_id to API Gateway                    │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Kafka broadcasts "enrollment.created" event              │
└─────┬───────────────────────┬───────────────────────┬───────┘
      │                       │                       │
      ▼                       ▼                       ▼
┌───────────────┐    ┌──────────────────┐    ┌──────────────┐
│ Progress      │    │ Notification     │    │ Analytics    │
│ Service       │    │ Service          │    │ Service      │
│               │    │                  │    │              │
│ Initialize    │    │ Queue email task │    │ Update count │
│ progress in   │    │ in RabbitMQ      │    │ in PostgreSQL│
│ PostgreSQL    │    │                  │    │              │
└───────────────┘    └────────┬─────────┘    └──────────────┘
                              │
                              ▼
                     ┌──────────────────┐
                     │ RabbitMQ Queue   │
                     │ "email_queue"    │
                     └────────┬─────────┘
                              │
                              ▼
                     ┌──────────────────┐
                     │ Celery Worker    │
                     │ Sends welcome    │
                     │ email to student │
                     └──────────────────┘
```

**Meanwhile (Parallel):**

```
┌─────────────────────────────────────────────────────────────┐
│ 5. Temporal Worker executes EnrollmentWorkflow              │
│                                                              │
│ Step 1: Call Progress Service API to initialize progress    │
│         (already done via Kafka, this is backup/verification)│
│                                                              │
│ Step 2: Call Notification Service to queue email            │
│         (already done via Kafka)                             │
│                                                              │
│ Step 3: Update user's enrolled courses cache in Redis       │
│                                                              │
│ Step 4: Mark workflow complete                              │
└─────────────────────────────────────────────────────────────┘
```

**Total Time:**

- API response: ~50ms (ACID transaction + Kafka publish)
- Email sent: ~2-5 seconds (background)
- Workflow complete: ~10 seconds

---

### **Flow 2: Instructor Publishes Course**

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Instructor clicks "Publish Course"                       │
│    POST /api/courses/123/publish                            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. API Gateway → Course Service                             │
│    POST http://course-service:8000/courses/123/publish      │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Course Service                                            │
│    - Update status to "publishing" (PostgreSQL)             │
│    - Start Temporal workflow: CoursePublishingWorkflow      │
│    - Return workflow_id to client                           │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Temporal Worker executes CoursePublishingWorkflow        │
│                                                              │
│ Step 1: Validate course completeness (PostgreSQL)           │
│ Step 2: Save content to MongoDB                             │
│ Step 3: Upload files to S3/MinIO                            │
│ Step 4: Extract text from videos/PDFs                       │
│         → Call Content Service API                          │
│ Step 5: Generate embeddings (OpenAI API)                    │
│         → Call Content Service API                          │
│ Step 6: Store embeddings in Qdrant                          │
│         → Call Content Service API                          │
│ Step 7: Update search index (if using Elasticsearch)        │
│ Step 8: Mark course as "published" (PostgreSQL)             │
│ Step 9: Publish "course.published" event to Kafka           │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Kafka broadcasts "course.published" event                │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
         ┌────────────────┐
         │ Analytics      │
         │ Service        │
         │ Update metrics │
         └────────────────┘
```

**Frontend polling:**

```
Every 2 seconds:
  GET /api/workflows/{workflow_id}/status

Response:
  {
    "status": "RUNNING",
    "current_step": "Step 5/8: Generating embeddings",
    "progress": 62
  }
```

**Total Time:** 5-15 minutes (depending on course size)

---

### **Flow 3: Student Asks AI Question**

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Student types: "Explain Python decorators"               │
│    POST /api/ai/ask                                         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. API Gateway → AI Assistant Service                       │
│    POST http://ai-assistant-service:8000/ask                │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. AI Assistant Service (RAG Pipeline)                      │
│                                                              │
│ Step 1: Generate query embedding (OpenAI API)               │
│         "Explain Python decorators" → [0.23, 0.45, ...]     │
│                                                              │
│ Step 2: Search Qdrant for similar chunks                    │
│         Query: embedding vector                             │
│         Result: Top 5 relevant text chunks from course      │
│                                                              │
│ Step 3: Build context from retrieved chunks                 │
│         Context: "Decorators in Python are... @decorator..." │
│                                                              │
│ Step 4: Send to OpenAI GPT-4 with context                   │
│         Prompt: "Answer based on: {context}                 │
│                  Question: {question}"                      │
│                                                              │
│ Step 5: Stream response back to client                      │
│         Server-Sent Events (SSE)                            │
│                                                              │
│ Step 6: Save conversation to MongoDB                        │
└─────────────────────────────────────────────────────────────┘
```

**Total Time:**

- First token: <800ms
- Full response: 2-4 seconds (streaming)

---

## Service Dependencies Matrix

| Service                  | PostgreSQL | MongoDB | Redis | Kafka | RabbitMQ | Temporal | Qdrant |
| ------------------------ | ---------- | ------- | ----- | ----- | -------- | -------- | ------ |
| **API Gateway**          | ❌         | ❌      | ✅    | ❌    | ❌       | ❌       | ❌     |
| **User Service**         | ✅         | ❌      | ✅    | ✅    | ❌       | ❌       | ❌     |
| **Course Service**       | ✅         | ✅      | ❌    | ✅    | ❌       | ✅       | ❌     |
| **Enrollment Service**   | ✅         | ❌      | ❌    | ✅    | ❌       | ✅       | ❌     |
| **Progress Service**     | ✅         | ❌      | ✅    | ✅    | ❌       | ❌       | ❌     |
| **Notification Service** | ❌         | ❌      | ❌    | ✅    | ✅       | ❌       | ❌     |
| **Content Service**      | ❌         | ✅      | ❌    | ❌    | ❌       | ❌       | ✅     |
| **AI Assistant**         | ❌         | ✅      | ❌    | ❌    | ❌       | ❌       | ✅     |
| **Analytics Service**    | ✅         | ❌      | ❌    | ✅    | ❌       | ❌       | ❌     |

---

## Network Communication Map

```
                    Internet
                       │
                       ▼
                 [Port 8000]
                 API Gateway
                       │
         ┌─────────────┼─────────────┐
         │             │             │
    [Port 8001]   [Port 8002]   [Port 8003]
    User Service  Course Svc    Enroll Svc
         │             │             │
         └─────────────┼─────────────┘
                       │
         ┌─────────────┼─────────────┐
         │             │             │
    [Port 8004]   [Port 8005]   [Port 8006]
    Progress Svc  Notify Svc    Content Svc
                       │
         ┌─────────────┼─────────────┐
         │             │             │
    [Port 8007]   [Port 8008]
    AI Assistant  Analytics Svc

═══════════════════════════════════════════════════════
                  SHARED INFRASTRUCTURE
═══════════════════════════════════════════════════════

[Port 5432]      [Port 27017]     [Port 6379]
PostgreSQL       MongoDB          Redis

[Port 9092]      [Port 5672]      [Port 7233]
Kafka            RabbitMQ         Temporal

[Port 6333]
Qdrant (Vector DB)
```

---

## Startup Order

```bash
# 1. Start infrastructure (wait for healthy)
docker-compose up -d postgres mongodb redis zookeeper kafka rabbitmq temporal qdrant

# 2. Run database migrations
docker-compose run --rm alembic upgrade head

# 3. Start microservices
docker-compose up -d user-service course-service enrollment-service progress-service

# 4. Start additional services
docker-compose up -d notification-service content-service ai-assistant-service analytics-service

# 5. Start workers
docker-compose up -d celery-worker temporal-worker

# 6. Start API Gateway (entry point)
docker-compose up -d api-gateway

# 7. Start monitoring
docker-compose up -d prometheus grafana
```

**Or simply:**

```bash
docker-compose up -d
# Wait 30 seconds for everything to start
```

---

## Key Takeaways

### **Infrastructure Layer** (Shared, managed separately)

- PostgreSQL, MongoDB, Redis
- Kafka, RabbitMQ, Temporal
- Qdrant, Prometheus, Grafana

### **Microservices Layer** (Your code)

- 8 independent FastAPI services
- Each service in own container
- Each connects to needed infrastructure

### **Workers Layer** (Background processors)

- Celery workers (RabbitMQ tasks)
- Temporal workers (workflows)

### **Communication Patterns**

- **Synchronous:** API Gateway → Services (REST)
- **Asynchronous:** Services → Kafka → Services (events)
- **Background:** Services → RabbitMQ → Celery (tasks)
- **Workflows:** Services → Temporal → Workers (orchestration)

### **Scaling Strategy**

- Add more service instances (horizontal scaling)
- Add more workers (Celery, Temporal)
- Kafka partitions for load distribution
- Redis caching for performance

---

**This is your complete architecture tree and communication flow!** 🚀
