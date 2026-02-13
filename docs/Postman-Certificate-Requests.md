# Postman Requests: Certificates

**Base URL:** `http://localhost:8000`  
**Auth:** Most requests require `Authorization: Bearer <your_jwt_token>`.

---

## Certificates

Certificates are issued when a student completes all course modules. **Students** request their own certificate (backend verifies completion); **instructors** can issue for any completed enrollment. Anyone can verify a certificate with a verification code.

### 1. Request/Issue a Certificate (Student or Instructor)

**Method:** `POST`  
**URL:** `http://localhost:8000/course/certificates/`

**Headers:**
| Key | Value |
|-----|-------|
| Authorization | Bearer \<your_jwt_token\> |
| Content-Type | application/json |

**Body (raw JSON):**
```json
{
  "enrollment_id": 15,
  "grade": "A",
  "score_percentage": 95.50
}
```

**Required:** `enrollment_id`  
**Optional:** `grade` (e.g. `"A"`, `"B"`, `"C"`), `score_percentage` (0–100)

**Response (201 Created):**
```json
{
  "id": 5,
  "enrollment_id": 15,
  "certificate_number": "SC-ABC123DEF456",
  "issue_date": "2025-02-13",
  "certificate_url": null,
  "verification_code": "abc123xyz789",
  "grade": "A",
  "score_percentage": 95.50,
  "issued_by_id": 10,
  "is_revoked": false,
  "revoked_at": null,
  "revoked_reason": null,
  "created_at": "2025-02-13T10:30:00"
}
```

**Notes:**
- **Students:** Call this when all modules are complete. Use `enrollment_id` and `score_percentage` from `GET /course/progress/{course_id}`. Backend verifies you own the enrollment and that it is completed.
- **Instructors:** Can issue for any completed enrollment.
- Enrollment must be marked "completed" (auto-set when all modules are finished).
- Each enrollment can only have one certificate (requesting again will fail with 400).

---

### 2. Get All My Certificates

**Method:** `GET`  
**URL:** `http://localhost:8000/course/certificates/my`

**Query params (optional):**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| skip | int | 0 | Pagination offset |
| limit | int | 50 | Max items per page |

**Headers:**
| Key | Value |
|-----|-------|
| Authorization | Bearer \<your_jwt_token\> |

**Example:** `http://localhost:8000/course/certificates/my?skip=0&limit=20`

**Response (200 OK):**
```json
{
  "items": [
    {
      "id": 5,
      "enrollment_id": 15,
      "certificate_number": "SC-ABC123DEF456",
      "issue_date": "2025-02-13",
      "certificate_url": null,
      "verification_code": "abc123xyz789",
      "grade": "A",
      "score_percentage": 95.50,
      "issued_by_id": 10,
      "is_revoked": false,
      "revoked_at": null,
      "revoked_reason": null,
      "created_at": "2025-02-13T10:30:00"
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 20
}
```

**Notes:** Returns all certificates for the current user (their completed enrollments).

---

### 3. Get Certificate by Enrollment ID

**Method:** `GET`  
**URL:** `http://localhost:8000/course/certificates/enrollment/{enrollment_id}`

**Headers:**
| Key | Value |
|-----|-------|
| Authorization | Bearer \<your_jwt_token\> |

**Example:** `http://localhost:8000/course/certificates/enrollment/15`

**Response (200 OK):** Same structure as single certificate (CertificateResponse).

**Returns:** 404 if enrollment not found or no certificate for that enrollment. 403 if student tries to access another user's enrollment.

---

### 4. Get Certificate by ID

**Method:** `GET`  
**URL:** `http://localhost:8000/course/certificates/{certificate_id}`

**Headers:**
| Key | Value |
|-----|-------|
| Authorization | Bearer \<your_jwt_token\> |

**Example:** `http://localhost:8000/course/certificates/5`

**Response (200 OK):**
```json
{
  "id": 5,
  "enrollment_id": 15,
  "certificate_number": "CERT-2025-0001",
  "issue_date": "2025-02-13",
  "certificate_url": null,
  "verification_code": "abc123xyz789",
  "grade": "A",
  "score_percentage": 95.50,
  "issued_by_id": 2,
  "is_revoked": false,
  "revoked_at": null,
  "revoked_reason": null,
  "created_at": "2025-02-13T10:30:00"
}
```

**Returns:** 404 if certificate not found.

---

### 5. Verify Certificate (Public - No Auth Required)

**Method:** `GET`  
**URL:** `http://localhost:8000/course/certificates/verify/{verification_code}`

**Headers:**
| Key | Value |
|-----|-------|
| Content-Type | application/json |

**Example:** `http://localhost:8000/course/certificates/verify/abc123xyz789`

**Response (200 OK - Valid Certificate):**
```json
{
  "is_valid": true,
  "certificate_number": "CERT-2025-0001",
  "issue_date": "2025-02-13",
  "grade": "A",
  "is_revoked": false
}
```

**Response (200 OK - Invalid Certificate):**
```json
{
  "is_valid": false,
  "certificate_number": null,
  "issue_date": null,
  "grade": null,
  "is_revoked": false
}
```

**Notes:**
- **No authentication required** — anyone can verify a certificate
- This endpoint is public and can be shared for verification purposes
- Verification code is unique and issued when certificate is created
- If `is_valid` is `false`, the certificate does not exist or has been revoked

---

## Example Flow

### Step 1: Student completes course
1. **Enroll:** `POST /course/enrollments/` with `{"course_id": 4}`
2. **Mark lessons/quizzes/summaries complete:** `POST /course/progress` multiple times
3. **Check progress:** `GET /course/progress/4` → verify `is_complete: true`, get `enrollment_id`
4. When the last item is marked complete, the enrollment is auto-marked as "completed"

### Step 2: Student requests certificate (or instructor issues)
1. **Request certificate:** `POST /course/certificates/` (use student token)
   ```json
   {
     "enrollment_id": 15,
     "grade": "A",
     "score_percentage": 95.50
   }
   ```
   - Get `enrollment_id` from `GET /course/progress/4` (now included in the response)
   - Use `completion_percentage` for `score_percentage`
2. **Get certificate details:** `GET /course/certificates/5` (using the `id` from the response)

### Step 3: Share & verify certificate
1. **Share verification link:** Give the student or employer the verification code: `abc123xyz789`
2. **Public verification:** Anyone can verify with `GET /course/certificates/verify/abc123xyz789`

---

## Sample Test Data

**Student user (for enrollments, progress, and claiming certificates):**
- `user_id`: 10
- `Authorization`: Bearer `<token_from_signin>`

**Instructor user (can also issue for any student):**
- `user_id`: 2
- Role: instructor
- `Authorization`: Bearer `<instructor_token_from_signin>`

**Course:**
- `course_id`: 4

**Enrollment (created after student enrolls, `enrollment_id` returned in progress):**
- `enrollment_id`: 15

---

## Notes

- **Certificate number** is auto-generated (e.g., `SC-ABC123DEF456`)
- **Verification code** is a unique random string for public verification
- **Issue date** defaults to today's date
- Only one certificate per enrollment; requesting again will fail with 400
- Students can only request certificates for their own completed enrollments
- Certificates can be revoked by instructors (future feature)
- All responses use ISO 8601 date/datetime format
