# SmartCourse Architecture & Learning Playbook

## 1. Executive Summary
SmartCourse is EduCorp's next-generation intelligent learning backend. The platform must deliver reliable course lifecycle management, AI-assisted learning experiences, and analytics-ready data under heavy load. This playbook consolidates the business context, product requirements, technical architecture, workflows, and a one-month upskilling roadmap tailored for an experienced JavaScript/Nest engineer transitioning into Python + GenAI microservices.

---

## 2. Business Context & Goals
1. **Frictionless Course Operations** – Rapid authoring, publishing, and updating of content with consistent downstream processing.
2. **Learner Delight Through Intelligence** – Context-aware Q&A, AI-generated learning aids, and adaptive support.
3. **Operational Scalability** – Event-driven, resilient workflows that survive spikes in enrollments, publishing, and AI usage.
4. **Data Trustworthiness** – Single source of truth for enrollments, progress, completions, certificates, and analytics.
5. **Future-Proof Foundation** – Modular services that accommodate new pedagogies, AI models, and workflow automations.

---

## 3. Personas & Top Use Cases
| Persona | Goals | Representative Use Cases |
| --- | --- | --- |
| Instructor | Publish engaging courses, keep content fresh | Create course, upload modules, trigger AI summaries, monitor enrollments |
| Student | Discover relevant content, learn efficiently | Search catalog, enroll, consume modules, ask contextual questions |
| Admin / Ops | Ensure platform reliability and compliance | Audit workflows, resolve stuck events, monitor analytics |

Key use cases (cross-cutting):
- Instructor publishes/updates a course; platform auto-processes assets and AI metadata.
- Student enrolls; system initializes progress, analytics, notifications.
- Student asks a question; AI assistant retrieves content, responds with streaming answer.
- Background workers process backlog while maintaining idempotency and observability.

---

## 4. Functional Requirements Breakdown
1. **Course & User Management**
   - CRUD for courses, modules, lessons, assets.
   - Role-aware user management (student/instructor/admin) with RBAC policies.
   - Enrollment rules (duplicate prevention, prerequisites, caps) enforced transactionally.

2. **Content Publishing Workflow**
   - Automatic content chunking, metadata extraction, vector embedding, search indexing.
   - Durable orchestration; partial failures retried without corrupt states.

3. **Enrollment Workflow**
   - Progress initialization, analytics increments, notification dispatch.
   - High-volume safe (idempotent, backpressure-aware, recoverable).

4. **Intelligent Learning Assistant**
   - Contextual Q&A (retrieval augmented generation) with guardrails.
   - Instructor content enhancement (summaries, quizzes, objectives) with streaming output.

5. **Distributed Event Handling**
   - Independent background tasks for publishing, analytics, notifications, AI prep.
   - Traceable, retryable, debuggable workflows.

6. **Analytics & Reporting**
   - Metrics enumerated in assignment captured in dedicated warehouse-ready store.
   - API + dashboards for trend analysis and anomaly detection.

7. **Observability & Reliability**
   - End-to-end tracing, structured logging, SLO-aligned dashboards, chaos testing hooks.

---

## 5. Non-Functional Requirements (NFRs)
- **Availability**: 99.5% API uptime; background workflows tolerate worker loss with graceful degradation.
- **Latency Targets**: <200 ms for core REST APIs (CRUD), <2 s P95 for AI assistant responses (first token <800 ms with streaming), <5 min for eventual consistency tasks (analytics refresh, search indexing).
- **Scalability**: Horizontally scalable FastAPI services behind autoscaling gateway; Kafka partitions sized for 10x growth; Temporal clusters sized for 5k concurrent workflows.
- **Consistency**: Strong consistency for enrollment state (PostgreSQL), eventual consistency for search/view models.
- **Security**: JWT + OAuth2, data encryption at rest and transit, audit logs, PII minimization.
- **Compliance**: FERPA-like data protections, GDPR-ready consent handling.

---

## 6. High-Level Architecture
```
          +---------------------+
          |  API Gateway / BFF  |
          +----------+----------+
                     |
       +-------------+-------------------------------+
       |             |               |               |
+------+--+   +------+-----+   +-----+------+   +----+-----+
| Course |   | Enrollment |   | AI Assistant|   | Analytics |
| Service|   | Service    |   | Service     |   | Service   |
+---+-----+   +-----+-----+   +------+------+
    |               |                |              
    |               |                |      +---------------+
+---+----+   +------+-----+   +------+----+ | Notification  |
|Content |   | Progress   |   |Workflow  | | Service       |
|Service |   | Service    |   |Orchestr. | +-------+-------+
+---+----+   +------+-----+   +------+----+         |
    |               |                |              v
 PostgreSQL   PostgreSQL/Redis   Vector DB     Email/SMS Push
```
Supporting infrastructure:
- **Event Backbone**: Kafka + Schema Registry for inter-service contracts.
- **Workflow Orchestration**: Temporal for multi-step publishing/enrollment workflows.
- **Async Tasks**: Celery workers (Redis broker for intra-service tasks) and RabbitMQ for fan-out notifications.
- **Caching**: Redis for session tokens, rate limits, progress snapshots.
- **Observability Stack**: OpenTelemetry instrumentation exported to Prometheus, Grafana, Jaeger.

---

## 7. Service-by-Service Responsibilities
1. **API Gateway / BFF (FastAPI)**
   - Aggregates responses for frontends (web, mobile).
   - Handles auth, throttling, schema validation (Pydantic models), request tracing.

2. **Course Service**
   - Owns course catalog domain (PostgreSQL primary store, read replicas for queries).
   - Publishes `course.published` events to Kafka.
   - Initiates Temporal workflows for content processing.

3. **Content Service**
   - Processes course assets using Celery workers.
   - Generates metadata, chunked text, embeddings (via AI service), persists to NoSQL (MongoDB or Dynamo-style) and vector DB (e.g., pgvector, Pinecone, Weaviate).
   - Updates search index (OpenSearch/Elasticsearch).

4. **Enrollment Service**
   - Manages student-course relationships, prerequisites, capacity enforcement.
   - Emits `enrollment.created` events; triggers Temporal enrollment workflow for progress + analytics + notifications.

5. **Progress Service**
   - Tracks lesson completions, quiz scores; stores in PostgreSQL partitioned tables for scale.
   - Provides APIs for checkpoints and completions.

6. **AI Assistant Service**
   - Implements LangGraph pipelines: Retrieval nodes, reasoning nodes, streaming response nodes.
   - Connects to LLM providers (OpenAI, Anthropic, Groq) with abstraction for switchability.
   - Maintains prompt templates, safety filters, telemetry.

7. **Analytics Service**
   - Consumes Kafka topics, writes to columnar warehouse (ClickHouse/BigQuery/Snowflake) or OLAP schema in PostgreSQL.
   - Exposes metrics for dashboards, powers admin insights.

8. **Notification Service**
   - Subscribes to workflow-complete events; sends email/SMS/push through providers (SES, Twilio, Firebase).
   - Tracks delivery receipts, retries, failure metrics.

9. **Workflow Orchestrator (Temporal)**
   - Defines durable workflows for course publishing and enrollment.
   - Ensures step-level retries, compensations, timeout handling.

10. **Observability & Platform Service**
    - Provides centralized logging (Loki/ELK), metrics, tracing; integrates with on-call alerts.

---

## 8. Data Stores & Access Patterns
| Data | Store | Access Pattern |
| --- | --- | --- |
| Users, Courses, Enrollments, Progress | PostgreSQL (with SQLAlchemy ORM) | ACID transactions, OLTP |
| Course Assets, Rich Content | Object store (S3/MinIO) + metadata table | Large blob reads/writes |
| Chunked Text + Metadata | NoSQL (MongoDB/Cosmos) | Flexible schema, high write throughput |
| Embeddings for Retrieval | Vector DB (pgvector, Pinecone, Weaviate) | kNN similarity search |
| Caches (sessions, rate limits, workflow checkpoints) | Redis | Low-latency reads |
| Event Streams | Kafka | Pub/Sub, replay |
| Analytics Warehouse | ClickHouse/Snowflake | OLAP queries |

Data quality strategies:
- CDC (Change Data Capture) from PostgreSQL to Kafka using Debezium for analytics synchronization.
- Schema Registry enforced Avro/JSON schemas for events to prevent consumer breakage.
- Periodic reconciliation jobs comparing authoritative stores (e.g., enrollments vs progress) to detect drift.

---

## 9. API & Contract Examples
### Course Publishing REST Endpoint
```
POST /courses/{course_id}/publish
Body: { "version": "v3", "notes": "Updated module 2" }
Response: { "workflow_id": "course-pub-123", "status": "QUEUED" }
```
- Triggers Temporal workflow `CoursePublishingWorkflow` with activities: validate -> snapshot -> chunk -> embed -> index -> mark ready.

### Enrollment Creation
```
POST /courses/{course_id}/enroll
Body: { "user_id": "student-456" }
Response: { "enrollment_id": "enr-789", "state": "PENDING" }
```
- Idempotency key = `course_id:user_id` to prevent duplicates.
- Emits Kafka event `enrollment.created` with schema version.

---

## 10. Workflow Deep Dives
### Course Publishing Workflow (Temporal)
1. **Trigger**: Instructor publishes via API.
2. **Validate Snapshot**: Activity ensures course completeness.
3. **Content Chunking**: Celery workers split content (max tokens per chunk) and persist to NoSQL.
4. **Embedding Generation**: AI service batches chunk text, stores vectors in vector DB.
5. **Search Index Update**: Content service updates OpenSearch index.
6. **AI Prep**: Register course context with LangGraph for RAG retrieval.
7. **Mark Ready**: Course service updates status to READY, emits `course.ready` event.
8. **Compensation**: On failure, rollback status to DRAFT, emit alert, leave partial data flagged for cleanup.

### Enrollment Workflow (Temporal)
1. **Record Enrollment** (PostgreSQL transaction, idempotent key).
2. **Initialize Progress** (Progress service default modules status = NOT_STARTED, stored in Redis + PostgreSQL).
3. **Analytics Update** (Analytics service increments counters via Kafka consumer).
4. **Notification Dispatch** (Notification service sends welcome, optionally schedule reminders).
5. **Completion** (Temporal signals success; API polls or receives webhook).

### AI Q&A Flow (LangGraph)
1. **Input Node**: Student question, metadata (course, module, user progress).
2. **Retrieval Node**: Query vector DB + metadata filters.
3. **Context Builder**: Assemble top-k chunks, citations, guard against hallucinations.
4. **LLM Generation Node**: Call provider with structured prompt, streaming tokens via Server-Sent Events.
5. **Post-Processor**: Apply policy filters, attach source references.
6. **Telemetry Node**: Emit usage metrics, latency, quality signals.

---

## 11. Eventing & Idempotency Strategy
- **Kafka Topics**
  - `course.published`, `course.ready`, `content.chunked`, `enrollment.created`, `enrollment.progressed`, `ai.requested`, `ai.completed`, `notification.sent`, `workflow.failed`.
- **Schema Management**: Confluent Schema Registry with versioning (compatibility = BACKWARD).
- **Idempotency**: Each consumer stores processed offsets + dedupe keys (Redis/DB) to avoid double processing.
- **Retry Policy**: Exponential backoff with DLQ topics; Temporal activities handle retries with jitter.

---

## 12. Observability & Reliability Plan
| Capability | Tooling | Notes |
| --- | --- | --- |
| Metrics | Prometheus + Grafana | SLO dashboards (latency, error rate, queue depth) |
| Tracing | OpenTelemetry SDK -> Jaeger | TraceIDs propagated via headers, Temporal + Celery instrumented |
| Logging | Structured JSON logs -> Loki/ELK | Correlate with trace IDs |
| Alerting | Grafana Alerting / PagerDuty | Threshold + anomaly-based alerts |
| Chaos | Toxiproxy, Temporal failure injection | Validate retries, compensations |

Reliability techniques:
- Circuit breakers around AI providers.
- Bulkhead isolation between user-facing APIs and background workers.
- Dead letter replayers + replay dashboards.

---

## 13. DevOps & Environments
- **Containerization**: Docker images per service; multi-stage builds (lint/test -> runtime).
- **Local Dev**: Docker Compose bringing up PostgreSQL, Redis, Kafka (Redpanda dev), Temporal, vector DB.
- **CI/CD**: GitHub Actions (lint -> tests -> security scan -> integration tests -> build -> deploy).
- **Environments**: Dev, Staging, Production. Feature flags for AI experiments.
- **Infrastructure as Code**: Terraform for cloud resources (VPC, databases, queues).

---

## 14. Security & Compliance Considerations
- OAuth2 + JWT with short-lived access tokens, refresh tokens stored securely (httpOnly cookies or secure storage).
- Role-based access enforced at gateway + service level (FastAPI dependencies verifying claims).
- Secrets management via Vault/Parameter Store; no secrets in code.
- Data encryption (TLS 1.2+, AES-256 at rest). Key rotation policy.
- PII minimization: Only store required user info, anonymize analytics where possible.
- Audit logging for enrollment changes, AI outputs (for compliance review).

---

## 15. Implementation Roadmap (1-Month Plan)
| Week | Focus | Deliverables |
| --- | --- | --- |
| Week 1 | Foundations & Environment | Finalize PRD, design diagrams, local dev stack (Docker Compose), base FastAPI skeleton, Postgres schema (users, courses, enrollments). |
| Week 2 | Core Workflows | Implement course CRUD, enrollment API, Temporal workflows stubs, Kafka topics, Celery worker scaffolding, seed data. |
| Week 3 | AI & Background Services | Content processing pipeline (chunking, embeddings), LangGraph RAG flow, vector DB integration, analytics consumers, notifications. |
| Week 4 | Hardening & Observability | End-to-end tests, load tests, observability dashboards, chaos drills, documentation polish, deployment scripts. |

Daily cadence: code, review, test, document; schedule pair sessions with Python/AI SMEs; block 1-2 hours for study using resources below.

---

## 16. Learning & Reference Materials
1. **Python & FastAPI**
   - FastAPI Official Docs: https://fastapi.tiangolo.com/
   - "FastAPI for Professionals" course (TestDriven.io).
   - Pydantic, SQLAlchemy async ORM tutorials.

2. **Celery & Distributed Tasks**
   - Celery Docs: https://docs.celeryq.dev/
   - "Celery Best Practices" (TestDriven).

3. **Temporal Workflows**
   - Temporal Academy: https://learn.temporal.io/
   - "Build Reliable Workflows with Temporal" playlist.

4. **Kafka & Event-Driven Systems**
   - Confluent Developer Track: https://developer.confluent.io/
   - "Designing Event-Driven Systems" (Ben Stopford).

5. **GenAI / LangGraph / RAG**
   - LangGraph Docs: https://langchain-ai.github.io/langgraph/
   - "RAG From Scratch" (Pinecone), "LLM University" (Deeplearning.ai).

6. **Vector Databases & Retrieval**
   - pgvector quickstart, Pinecone university.

7. **Observability**
   - OpenTelemetry Python instrumentation guide.
   - "Distributed Tracing in Practice" (O'Reilly).

8. **Architecture & Design**
   - "Building Microservices" (Newman), "Designing Data-Intensive Applications" (Kleppmann).

Study approach: pair theory with proof-of-concept (POC). For every module (e.g., Celery), build a minimal POC inside repo (scripts under `spikes/`).

---

## 17. Traceability Matrix (Features -> Requirements -> Deliverables)
| Feature | Requirement IDs | Deliverables |
| --- | --- | --- |
| Course Publishing | FR1, FR2, FR5 | Course service, Temporal workflow, content pipeline, Kafka events |
| Enrollment Handling | FR1, FR3, FR5 | Enrollment API, workflow, analytics update, notifications |
| AI Assistant | FR4, FR5 | LangGraph pipeline, vector DB, streaming API |
| Analytics & Metrics | FR6 | Kafka consumers, warehouse schema, Grafana dashboards |
| Observability | FR7 | OTel instrumentation, Jaeger traces, Prometheus metrics |

---

## 18. Testing Strategy
- **Unit Tests**: pytest + pytest-asyncio for FastAPI routes, services, repositories.
- **Contract Tests**: Schemathesis / Pact for API and Kafka schemas.
- **Integration Tests**: Docker Compose env running Nightly; use pytest + HTTPX + Faker.
- **Load Tests**: k6 / Locust scripts simulating enrollments, AI queries.
- **Chaos & Failure Injection**: Temporal failure scenarios, Kafka partition drop simulation.
- **AI Evaluation**: LLM-as-a-judge prompts for answer quality; track hallucination rate.

---

## 19. Risk Register & Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| New tech ramp-up slows delivery | Medium | Parallel learning plan, POC spikes, pair programming |
| AI provider latency/outage | High | Multi-provider abstraction, caching, fallback responses |
| Workflow failures causing inconsistency | High | Temporal + idempotent consumers, reconciliation jobs |
| Analytics lag | Medium | CDC pipelines, OLAP refresh alerts |
| Cost overruns (LLM usage) | Medium | Token budgeting, caching, streaming partial results |

---

## 20. Next Steps Checklist
1. Stand up repo structure: `services/`, `infrastructure/`, `docs/` with ADRs.
2. Scaffold FastAPI services with shared libraries (auth, logging, configs).
3. Write first ADR on data store selection (PostgreSQL + pgvector vs external vector DB).
4. Implement local dev automation script (`make dev-up`).
5. Schedule weekly architecture reviews; keep documentation living in this playbook.

---

## 21. Glossary
- **BFF**: Backend For Frontend.
- **RAG**: Retrieval Augmented Generation.
- **Temporal**: Durable workflow orchestration engine.
- **LangGraph**: Graph-based orchestration library for LLM flows built atop LangChain.
- **DLQ**: Dead Letter Queue.

---

## 22. Personal Upskilling Tips
- Translate existing Nest/Node patterns (controllers, services, interceptors) to FastAPI dependencies, routers, and middleware.
- Practice Python typing + pydantic models to achieve compile-time-like safety.
- Implement decorators for tracing/logging similar to Nest interceptors.
- Build reference microservice (e.g., Enrollment) end-to-end before cloning pattern for others.
- Document learnings daily in `docs/journal.md` to reinforce concepts.

This document should serve as your north star for both implementation and learning. Iterate on it as you refine requirements, discover constraints, or adopt new best practices.
