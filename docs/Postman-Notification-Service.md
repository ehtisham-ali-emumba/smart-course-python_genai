# Notification Service - Sample Postman Requests

All notification endpoints are accessed through the **API Gateway** and require JWT authentication.

**Base URL:** `http://localhost:8000`

**Headers:** 
- `Content-Type: application/json`
- `Authorization: Bearer <your_jwt_token>`

---

## 1. Auth - Get Token

### Register (run once)
```
POST http://localhost:8000/auth/register
```

```json
{
  "email": "test@example.com",
  "username": "testuser",
  "password": "TestPass123!",
  "first_name": "Test",
  "last_name": "User"
}
```

### Login (get access_token)
```
POST http://localhost:8000/auth/login
```

```json
{
  "email": "test@example.com",
  "password": "TestPass123!"
}
```

Copy `access_token` from the response and use it in the `Authorization` header for all notification requests.

---

## 2. Send (Generic)

```
POST http://localhost:8000/notifications/send
```

```json
{
  "user_id": 42,
  "type": "generic",
  "channel": "email",
  "priority": "normal",
  "title": "Test Notification",
  "message": "This is a test notification message.",
  "metadata": {
    "course_id": 1,
    "enrollment_id": 101
  }
}
```

**type:** `generic`, `enrollment_welcome`, `course_published`, `certificate_issued`, `module_completed`, etc.

**channel:** `email`, `push`, `in_app`, `sms`

**priority:** `low`, `normal`, `high`, `urgent`

---

## 3. Enrollment

```
POST http://localhost:8000/notifications/enrollment
```

```json
{
  "user_id": 42,
  "course_id": 1,
  "course_title": "Python Basics",
  "enrollment_id": 101,
  "instructor_name": "John Doe"
}
```

---

## 4. Course Event

```
POST http://localhost:8000/notifications/course
```

```json
{
  "course_id": 1,
  "course_title": "Python Basics",
  "instructor_id": 5,
  "event": "published",
  "affected_user_ids": [1, 2, 3]
}
```

**event:** `published`, `archived`, `updated`

---

## 5. Certificate

```
POST http://localhost:8000/notifications/certificate
```

```json
{
  "user_id": 42,
  "course_id": 1,
  "course_title": "Python Basics",
  "certificate_id": 10,
  "certificate_number": "CERT-2026-001",
  "verification_code": "ABC123XYZ"
}
```

---

## 6. Progress

```
POST http://localhost:8000/notifications/progress
```

```json
{
  "user_id": 42,
  "course_id": 1,
  "course_title": "Python Basics",
  "enrollment_id": 101,
  "module_title": "Variables & Data Types",
  "completion_percentage": 35.5
}
```

---

## 7. Health Check

```
GET http://localhost:8000/health
```
