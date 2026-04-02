# Analytics Service: Replace `admin` Role with `instructor`

## Context

The system currently references an `admin` role that has not been properly implemented.
Instructor users hold admin-level privileges. This document lists every change needed in
the analytics service to replace `admin` with `instructor`.

---

## Files to Change

### 1. `services/analytics-service/src/analytics_service/api/dependencies.py`

#### Change `require_admin` → `require_instructor`

**Line 27–30** — rename the function and fix the role check:

```python
# BEFORE
def require_admin(request: Request) -> _uuid.UUID:
    role = get_current_user_role(request)
    if role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")

# AFTER
def require_instructor(request: Request) -> _uuid.UUID:
    role = get_current_user_role(request)
    if role != "instructor":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Instructor role required")
```

#### Change `require_instructor_or_admin` → `require_instructor`

The two functions `require_instructor_or_admin` and `require_admin` now collapse into the
same check. The helper used in `instructors.py` and `students.py` that currently
short-circuits on `"admin"` should instead short-circuit on `"instructor"`.

**Lines 36, 50** — replace `"admin"` with `"instructor"` in both helper functions:

```python
# BEFORE (require_instructor_or_admin, line 36)
if role == "admin":
    return

# AFTER
if role == "instructor":
    return

# BEFORE (require_student_or_admin, line 50)
if role == "admin":
    return

# AFTER
if role == "instructor":
    return
```

Also rename `require_instructor_or_admin` → `require_instructor_or_self` and
`require_student_or_admin` → `require_student_or_instructor` for clarity (optional but
recommended).

---

### 2. `services/analytics-service/src/analytics_service/api/platform.py`

#### Update import and route dependencies

**Line 6** — update import:

```python
# BEFORE
from analytics_service.api.dependencies import require_admin

# AFTER
from analytics_service.api.dependencies import require_instructor
```

**Lines 15, 27, 42** — replace dependency in all three platform routes:

```python
# BEFORE
@router.get("/platform/overview", dependencies=[Depends(require_admin)])
@router.get("/platform/trends",   dependencies=[Depends(require_admin)])
@router.get("/platform/ai-usage", dependencies=[Depends(require_admin)])

# AFTER
@router.get("/platform/overview", dependencies=[Depends(require_instructor)])
@router.get("/platform/trends",   dependencies=[Depends(require_instructor)])
@router.get("/platform/ai-usage", dependencies=[Depends(require_instructor)])
```

---

### 3. `services/analytics-service/src/analytics_service/api/courses.py`

#### Replace inline role checks (lines 23, 44, 69)

All three locations have the same pattern — replace `"admin"` with `"instructor"` and
update the error message:

```python
# BEFORE
if role not in {"admin", "instructor"}:
    raise HTTPException(status_code=403, detail="Admin or instructor role required")

# AFTER
if role not in {"instructor"}:
    raise HTTPException(status_code=403, detail="Instructor role required")
```

> Note: since `instructor` is now the only elevated role, the set can just be a direct
> equality check `if role != "instructor":` for clarity.

---

### 4. `services/analytics-service/src/analytics_service/api/instructors.py`

#### Update import (line 6)

```python
# BEFORE
from analytics_service.api.dependencies import require_instructor_or_admin

# AFTER
from analytics_service.api.dependencies import require_instructor_or_self
```

#### Update inline role check (line 45)

```python
# BEFORE
if role not in {"admin", "instructor"}:
    raise HTTPException(status_code=403, detail="Admin or instructor role required")

# AFTER
if role != "instructor":
    raise HTTPException(status_code=403, detail="Instructor role required")
```

---

### 5. `services/analytics-service/src/analytics_service/api/students.py`

#### Update import (line 6)

```python
# BEFORE
from analytics_service.api.dependencies import require_student_or_admin

# AFTER
from analytics_service.api.dependencies import require_student_or_instructor
```

No other changes needed — the function call on lines 21 and 41 stays the same, just
using the renamed function.

---

## Summary of All Changes

| File | Change |
|------|--------|
| `dependencies.py` | Rename `require_admin` → `require_instructor`; replace `"admin"` with `"instructor"` in role checks; rename helper functions |
| `platform.py` | Update import + all 3 route `Depends(...)` calls |
| `courses.py` | Replace `{"admin", "instructor"}` sets with `"instructor"` check (3 locations) |
| `instructors.py` | Update import + inline role check |
| `students.py` | Update import only |

No database schema changes, no consumer changes, and no config changes are required.
