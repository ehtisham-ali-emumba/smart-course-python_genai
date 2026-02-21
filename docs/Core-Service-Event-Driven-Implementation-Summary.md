# Core Service Event-Driven Implementation — Summary

**Date:** February 20, 2026  
**Document:** Implementation of `docs/Core-Service-Event-Driven-Implementation.md`

---

## 1. What Was Implemented

### 1.1 Core Service (New)

- **Location:** `services/core/`
- **Structure:** Full package as specified — providers (Kafka, RabbitMQ), events (envelope + payload schemas), consumers (event bridge), tasks (email, notification, certificate)
- **Purpose:** Shared event-driven infrastructure — pip-installable library + standalone Kafka consumer + Celery worker

**New Files Created (26):**

| Path | Purpose |
|------|---------|
| `services/core/pyproject.toml` | Package config (aiokafka, pydantic, celery[redis], pydantic-settings) |
| `services/core/Dockerfile` | Container build for event bridge + Celery worker |
| `services/core/src/core_service/__init__.py` | Package init |
| `services/core/src/core_service/config.py` | CoreSettings (Kafka, RabbitMQ, Redis URLs, consumer group) |
| `services/core/src/core_service/providers/*` | Kafka producer, consumer, topics; Celery app, dispatcher |
| `services/core/src/core_service/events/*` | EventEnvelope + payload schemas (user, course, enrollment, progress, certificate) |
| `services/core/src/core_service/consumers/*` | Event bridge entry point + EventHandlerRegistry |
| `services/core/src/core_service/tasks/*` | Email, notification, certificate Celery tasks (mock implementations) |

### 1.2 Docker Infrastructure

- **Added to `docker-compose.yml`:**
  - `zookeeper` — Kafka coordination
  - `kafka` — Event streaming broker (port 9092)
  - `kafka-init` — Creates topics: user.events, course.events, enrollment.events, progress.events, notification.events
  - `rabbitmq` — Task queue broker (ports 5672, 15672)
  - `celery-worker` — Celery worker (email_queue, notification_queue, certificate_queue)
- **Volumes:** `rabbitmq_data`
- **`.env`:** Added `CELERY_RESULT_BACKEND`

### 1.3 User Service Integration

- **Config:** Added `KAFKA_BOOTSTRAP_SERVERS`
- **Lifespan:** EventProducer start/stop
- **Dockerfile:** Repo-root context, install core package
- **Events emitted:**
  - `auth/register` → `user.registered`
  - `auth/login` → `user.login`
  - `profile` PUT → `user.profile_updated`

### 1.4 Course Service Integration

- **Config:** Added `KAFKA_BOOTSTRAP_SERVERS`
- **Lifespan:** EventProducer start/stop
- **Dockerfile:** Repo-root context, install core package
- **Events emitted:**
  - `courses` POST → `course.created`
  - `courses` PUT → `course.updated`
  - `courses` PATCH status → `course.published` | `course.archived`
  - `courses` DELETE → `course.deleted`
  - `enrollments` POST → `enrollment.created`
  - `enrollments` PATCH drop → `enrollment.dropped`
  - `enrollments` PATCH undrop → `enrollment.reactivated`
  - `progress` POST → `progress.updated`
  - `ProgressService._check_auto_complete` → `progress.course_completed`, `enrollment.completed`, `certificate.issued`
  - `CertificateService.issue_certificate` → `certificate.issued`
  - `CertificateService.revoke_certificate` → `certificate.revoked`

---

## 2. Kafka → Processing Routing

**Notification Service (Kafka consumer):**

| Kafka Event | Actions (inline mock) |
|-------------|------------------------|
| `user.registered` | send_welcome_email, create_in_app_notification |
| `course.published` | send_course_published_email, create_in_app_notification |
| `course.archived` | create_in_app_notification |
| `enrollment.created` | send_enrollment_confirmation, create_in_app_notification |
| `enrollment.dropped` | create_in_app_notification |
| `enrollment.completed` | send_course_completion_email, create_in_app_notification |
| `certificate.issued` | send_certificate_ready_email, create_in_app_notification, generate_certificate_pdf |
| `certificate.revoked` | create_in_app_notification |

---

## 3. Modified Files

| File | Change |
|------|--------|
| `docker-compose.yml` | Kafka, Zookeeper, kafka-init, RabbitMQ, celery-worker; user/course build context + Kafka env/deps; rabbitmq_data volume |
| `.env` | CELERY_RESULT_BACKEND |
| `services/user-service/Dockerfile` | Repo-root context, install core, updated COPY paths |
| `services/user-service/src/user_service/config.py` | KAFKA_BOOTSTRAP_SERVERS |
| `services/user-service/src/user_service/main.py` | EventProducer lifecycle in lifespan |
| `services/user-service/src/user_service/api/auth.py` | Emit user.registered, user.login |
| `services/user-service/src/user_service/api/profile.py` | Emit user.profile_updated |
| `services/course-service/Dockerfile` | Repo-root context, install core, updated COPY paths |
| `services/course-service/src/config.py` | KAFKA_BOOTSTRAP_SERVERS |
| `services/course-service/src/main.py` | EventProducer lifecycle in lifespan |
| `services/course-service/src/api/dependencies.py` | get_event_producer |
| `services/course-service/src/api/enrollments.py` | Emit enrollment.created, dropped, reactivated |
| `services/course-service/src/api/courses.py` | Emit course.created, updated, published, archived, deleted |
| `services/course-service/src/api/progress.py` | Pass producer to ProgressService |
| `services/course-service/src/api/certificates.py` | Pass producer to CertificateService |
| `services/course-service/src/services/progress.py` | Optional event_producer; emit progress.updated, progress.course_completed, enrollment.completed, certificate.issued |
| `services/course-service/src/services/certificate.py` | Optional event_producer; emit certificate.issued, certificate.revoked |

---

## 4. Verification

To verify end-to-end:

```bash
docker compose up -d
# Wait for Kafka, RabbitMQ, Redis to be healthy

# 1. Register user → should see user.registered in Kafka, welcome email in Celery logs
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"Test1234!","first_name":"Ali","last_name":"Khan","role":"student"}'

# 2. Check Kafka
docker compose exec kafka kafka-console-consumer --topic user.events --from-beginning --max-messages 1 --bootstrap-server localhost:29092

# 3. Check logs
docker compose logs notification-service --tail=20
docker compose logs celery-worker --tail=20
```

---

## 5. No README Added

Per request, no additional README files were created. This single `.md` file documents the implementation.
