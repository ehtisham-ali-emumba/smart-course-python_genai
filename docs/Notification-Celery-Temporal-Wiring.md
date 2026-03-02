# Notification Service — Wire Temporal HTTP Calls to Celery Tasks

**Date:** March 2, 2026
**Services affected:** `notification-service`, `core-service` (payload fixes)

---

## Problem

Temporal `EnrollmentWorkflow` calls notification-service via HTTP:

- `POST /notifications/enrollment` — step 5 (welcome email)
- `POST /notifications/send` — step 6 (in-app notification)

Three things are broken:

1. **Endpoints only log** — both handlers call `NotificationService` which just logs. No Celery tasks are enqueued.
2. **`enrollment_id` missing from step 5 payload** — `EnrollmentNotificationRequest` has `enrollment_id: int` as a required field but the activity never sends it → Pydantic 422 error.
3. **`channel` and `priority` missing from step 6 payload** — `SendNotificationRequest` requires both but the activity omits them → Pydantic 422 error.

Additionally, the notification-service Kafka consumer still handles `enrollment.created` and would enqueue the same Celery tasks independently, causing double-triggering once the HTTP path is wired.

---

## Goal

1. Wire `/notifications/enrollment` and `/notifications/send` to enqueue Celery tasks.
2. Fix the two activity payloads in core-service so they pass schema validation.
3. Add `email` to `EnrollmentNotificationRequest` schema (activity already sends it, schema doesn't accept it yet).
4. Remove `enrollment.created` from the Kafka event handler — Temporal owns it now.
5. Keep `enrollment.completed` in Kafka — Temporal does not handle that yet.

---

## What Changes — File Map

### Files to MODIFY in `notification-service`

| File | Change |
|------|--------|
| `src/notification_service/schemas/notification.py` | Add optional `email` field to `EnrollmentNotificationRequest` |
| `src/notification_service/api/notification.py` | Wire `/enrollment` and `/send` handlers to enqueue Celery tasks |
| `src/notification_service/consumers/event_handlers.py` | Remove `enrollment.created` handler and delete `_on_enrollment_created` method |

### Files to MODIFY in `core-service`

| File | Change |
|------|--------|
| `src/core_service/temporal/activities/notification_activities.py` | Add `enrollment_id` to enrollment payload; add `channel` + `priority` to send payload |

---

## 1. Schema — add `email` to `EnrollmentNotificationRequest`

**File:** `services/notification-service/src/notification_service/schemas/notification.py`

The `send_enrollment_welcome_email` Temporal activity already sends an `email` key in the request body, but `EnrollmentNotificationRequest` doesn't declare it. Pydantic silently drops unknown fields, so the email never reaches the handler. Add it as optional:

**Before:**
```python
class EnrollmentNotificationRequest(BaseModel):
    """Notification request for enrollment events."""
    user_id: int
    course_id: int
    course_title: str
    enrollment_id: int
    instructor_name: str = ""
```

**After:**
```python
class EnrollmentNotificationRequest(BaseModel):
    """Notification request for enrollment events."""
    user_id: int
    course_id: int
    course_title: str
    enrollment_id: int
    instructor_name: str = ""
    email: str = ""          # ← ADD THIS
```

---

## 2. API endpoints — enqueue Celery tasks on HTTP call

**File:** `services/notification-service/src/notification_service/api/notification.py`

### 2a. Add imports at top of file

Add alongside the existing imports:

```python
from datetime import datetime

from notification_service.worker import celery_app

EMAIL_QUEUE        = "email_queue"
NOTIFICATION_QUEUE = "notification_queue"
```

> `datetime` may already be imported via the schemas — check first and skip if so.

### 2b. Wire `/enrollment` endpoint

**Before (actual current code):**
```python
@router.post("/enrollment", response_model=NotificationResponse)
async def notify_enrollment(
    request: EnrollmentNotificationRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """Handle enrollment notification (logs only for now)."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID header")
    return await notification_service.notify_enrollment(request)
```

**After:**
```python
@router.post("/enrollment", response_model=NotificationResponse)
async def notify_enrollment(
    request: EnrollmentNotificationRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """
    Called by Temporal EnrollmentWorkflow step 5 (welcome email).
    Enqueues:
      1. send_enrollment_confirmation  → email_queue      (only if email provided)
      2. create_in_app_notification    → notification_queue
    """
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID header")

    # Task 1 — enrollment confirmation email (skip if no email address)
    if request.email:
        celery_app.send_task(
            "notification_service.tasks.email.send_enrollment_confirmation",
            kwargs={
                "student_id": request.user_id,
                "course_id": request.course_id,
                "course_title": request.course_title,
                "email": request.email,
            },
            queue=EMAIL_QUEUE,
        )

    # Task 2 — in-app notification
    celery_app.send_task(
        "notification_service.tasks.notification.create_in_app_notification",
        kwargs={
            "user_id": request.user_id,
            "title": "Enrollment Confirmed!",
            "message": f"You're enrolled in '{request.course_title}'.",
            "notification_type": "enrollment",
        },
        queue=NOTIFICATION_QUEUE,
    )

    return NotificationResponse(
        success=True,
        message="Enrollment notification tasks enqueued",
        notification_type=NotificationType.ENROLLMENT,
        channel=NotificationChannel.EMAIL,
        timestamp=datetime.utcnow(),
    )
```

### 2c. Wire `/send` endpoint

**Before (actual current code):**
```python
@router.post("/send", response_model=NotificationResponse)
async def send_notification(
    request: SendNotificationRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """Send a generic notification (logs only for now)."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID header")
    return await notification_service.send_notification(request)
```

**After:**
```python
@router.post("/send", response_model=NotificationResponse)
async def send_notification(
    request: SendNotificationRequest,
    x_user_id: str = Header(None, alias="X-User-ID"),
):
    """
    Generic send endpoint. Called by Temporal EnrollmentWorkflow step 6 (in-app notification).
    Enqueues create_in_app_notification when channel is in_app.
    """
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Missing X-User-ID header")

    if request.channel == NotificationChannel.IN_APP:
        celery_app.send_task(
            "notification_service.tasks.notification.create_in_app_notification",
            kwargs={
                "user_id": request.user_id,
                "title": request.title,
                "message": request.message,
                "notification_type": str(request.type),
            },
            queue=NOTIFICATION_QUEUE,
        )

    return NotificationResponse(
        success=True,
        message="Notification task enqueued",
        notification_type=request.type,
        channel=request.channel,
        timestamp=datetime.utcnow(),
    )
```

> **Note on enum value:** The Temporal activity sends `"channel": "in_app"`. Check the `NotificationChannel` enum in `schemas/notification.py` to confirm the exact member name (e.g., `IN_APP`, `in_app`). The comparison must match exactly.

> **Note on `notification_service` name:** The module-level `notification_service = NotificationService()` at the top of the file is still used by the other three endpoints (`/course`, `/certificate`, `/progress`). Do not remove it.

---

## 3. Remove `enrollment.created` from Kafka event handlers

**File:** `services/notification-service/src/notification_service/consumers/event_handlers.py`

Find the dispatch block inside the `handle` method (an `if/elif` chain or `match` statement on `event_type`). **Remove only the `enrollment.created` branch.** Keep `enrollment.completed` unchanged.

Remove this block:
```python
# DELETE — Temporal EnrollmentWorkflow handles this now
elif event_type == "enrollment.created":
    self._on_enrollment_created(event)
```

Also **delete the `_on_enrollment_created` private method** from the class body — it is now dead code.

> **Do not touch `Topics.ENROLLMENT` in `kafka_consumer.py`.** The consumer must stay subscribed to the enrollment topic because `enrollment.completed` events also arrive on it.

---

## 4. Core-service — fix activity payloads

**File:** `services/core/src/core_service/temporal/activities/notification_activities.py`

### 4a. `send_enrollment_welcome_email` — add missing `enrollment_id`

`EnrollmentNotificationRequest.enrollment_id` is a required `int` field. The activity currently omits it, causing a 422 validation error.

Find the payload dict in `send_enrollment_welcome_email`:

**Before:**
```python
payload = {
    "user_id": input.student_id,
    "email": input.student_email,
    "student_name": input.student_name,
    "course_id": input.course_id,
    "course_title": input.course_title,
    "instructor_name": "",
}
```

**After:**
```python
payload = {
    "user_id": input.student_id,
    "email": input.student_email,
    "course_id": input.course_id,
    "course_title": input.course_title,
    "enrollment_id": input.enrollment_id,   # ← ADD THIS
    "instructor_name": "",
}
```

Also remove `"student_name"` from the payload — it is not a field in `EnrollmentNotificationRequest` and serves no purpose here.

### 4b. `send_in_app_notification` — add missing `channel` and `priority`

`SendNotificationRequest` requires `channel` and `priority` fields. Both are missing from the activity payload, causing a 422 validation error.

Find the payload dict in `send_in_app_notification`:

**Before:**
```python
payload = {
    "user_id": input.user_id,
    "title": input.title,
    "type": input.notification_type,
    "message": input.message,
}
```

**After:**
```python
payload = {
    "user_id": input.user_id,
    "type": input.notification_type,
    "channel": "in_app",     # ← ADD THIS
    "priority": "normal",    # ← ADD THIS
    "title": input.title,
    "message": input.message,
}
```

> **Verify enum string values:** Check `NotificationChannel` and `NotificationPriority` enum definitions in `notification-service/schemas/notification.py` to confirm `"in_app"` and `"normal"` are the correct serialised values. Use whatever strings those enums define.

---

## 5. Implementation Order

### Phase 1 — Schema update

- [ ] `notification-service/schemas/notification.py` — add `email: str = ""` to `EnrollmentNotificationRequest`

### Phase 2 — Fix core-service activity payloads

- [ ] `core-service/temporal/activities/notification_activities.py` — add `enrollment_id`, remove `student_name` from enrollment payload
- [ ] `core-service/temporal/activities/notification_activities.py` — add `channel` and `priority` to send payload

### Phase 3 — Wire API endpoints to Celery

- [ ] `notification-service/api/notification.py` — add `celery_app` import and queue name constants
- [ ] `notification-service/api/notification.py` — replace `/enrollment` handler body to enqueue 2 tasks
- [ ] `notification-service/api/notification.py` — replace `/send` handler body to enqueue in-app task

### Phase 4 — Remove Kafka enrollment.created handler

- [ ] `notification-service/consumers/event_handlers.py` — remove `enrollment.created` dispatch branch
- [ ] `notification-service/consumers/event_handlers.py` — delete `_on_enrollment_created` method

### Phase 5 — Restart and verify

- [ ] Restart `notification-service` container
- [ ] Restart `core-service` container
- [ ] Enroll a student via Postman
- [ ] Watch `EnrollmentWorkflow` steps 5 and 6 complete successfully in Temporal UI (no 422/500)
- [ ] Check notification-service logs — should see Celery task enqueue log lines for `send_enrollment_confirmation` and `create_in_app_notification`
- [ ] Check RabbitMQ management UI (`localhost:15672`) — tasks appear in `email_queue` and `notification_queue`
- [ ] Confirm Kafka consumer no longer logs anything for `enrollment.created` events

---

## Summary of New Enrollment Notification Flow

```
Student POST /enrollments
        │
        ▼
course-service
  └── Publishes enrollment.created to Kafka
        │
        ▼ enrollment.events topic
core-service Kafka Consumer
  └── Starts EnrollmentWorkflow
        │
        ▼ Temporal Worker:
        │
        ├─ Step 5: send_enrollment_welcome_email
        │     → POST http://notification-service:8005/notifications/enrollment
        │         { user_id, course_id, course_title, enrollment_id, email }
        │     notification-service enqueues:
        │       • send_enrollment_confirmation  → email_queue      (RabbitMQ)
        │       • create_in_app_notification    → notification_queue (RabbitMQ)
        │     Temporal awaits HTTP 200 ✓
        │
        └─ Step 6: send_in_app_notification
              → POST http://notification-service:8005/notifications/send
                  { user_id, type, channel: "in_app", priority: "normal", title, message }
              notification-service enqueues:
                • create_in_app_notification    → notification_queue (RabbitMQ)
              Temporal awaits HTTP 200 ✓

notification-service Kafka consumer:
  enrollment.created  → handler removed (Temporal owns this now)
  enrollment.completed → still handled via Kafka (unchanged)
```

---

## Notes

- **No double-trigger after this change** — only Temporal enqueues enrollment Celery tasks. The Kafka handler for `enrollment.created` is removed.
- **`enrollment.completed` is untouched** — its Kafka handler and topic subscription stay exactly as-is.
- **Celery task names are exact strings** — they must match the `name=` argument in `@celery_app.task(...)`. Verify against `tasks/email.py` and `tasks/notification.py` before deploying.
- **`NotificationChannel.IN_APP` enum value** — verify the exact Python enum member name in `schemas/notification.py` and use it consistently in both the `/send` endpoint comparison and the activity payload string.
