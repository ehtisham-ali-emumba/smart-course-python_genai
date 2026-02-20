# SmartCourse — Progress System Refactor: Implementation Guide

**Version:** 2.0  
**Date:** February 19, 2026  
**Scope:** Two changes — (1) Replace `course_id` with `enrollment_id` in the Progress table, (2) Add `progress_percentage` + `updated_at` per lesson so course/module progress is calculated by aggregating lesson-level data. Auto-issue certificate on 100% course completion.

---

## Table of Contents

1. [Summary of Changes](#1-summary-of-changes)
2. [Current vs New Progress Table Design](#2-current-vs-new-progress-table-design)
3. [Database Migration](#3-database-migration)
4. [Model Changes](#4-model-changes)
5. [Schema Changes](#5-schema-changes)
6. [Repository Changes](#6-repository-changes)
7. [Service Changes](#7-service-changes)
8. [API Endpoint Changes](#8-api-endpoint-changes)
9. [ERD / Docs Update](#9-erd--docs-update)
10. [Full File-by-File Change List](#10-full-file-by-file-change-list)
11. [Migration Order / Execution Steps](#11-migration-order--execution-steps)
12. [Testing Checklist](#12-testing-checklist)

---

## 1. Summary of Changes

### What's Wrong Today

Looking at the current progress table data:

```
id | user_id | course_id | item_type | item_id                          | completed_at             | created_at
1  | 3       | 5         | lesson    | 674a1b2c3d4e5f6a7b8c9d0e         | 2026-02-13 07:48:15.471  | 2026-02-13 07:48:15.471
2  | 3       | 5         | lesson    | 698ed412a897034ee8ca80a7         | 2026-02-13 07:48:56.084  | 2026-02-13 07:48:56.084
...
```

Problems:
1. **`course_id` is redundant** — the enrollment already holds `(student_id, course_id)`. We should reference `enrollment_id` instead.
2. **Progress is binary** — a row only exists when the lesson is 100% done (`completed_at` is set immediately). There's no way to track *partial* progress (e.g., "watched 60% of the video").
3. **No `updated_at`** — we can't tell when progress was last modified.
4. **No per-lesson percentage** — module/course progress must be calculated by just counting rows, with no granularity.

### What We're Changing

| Aspect | Before | After |
|--------|--------|-------|
| FK reference | `course_id` → courses | `enrollment_id` → enrollments |
| Progress tracking | Binary (row = done) | `progress_percentage` (0–100) per lesson |
| Completion | `completed_at` always set on insert | `completed_at` is **nullable** — only set when `progress_percentage` reaches 100 |
| Timestamps | Only `created_at` | Both `created_at` and `updated_at` |
| Insert behavior | `INSERT ... ON CONFLICT DO NOTHING` | `INSERT ... ON CONFLICT DO UPDATE` (upsert percentage) |
| Module progress | Not tracked | Calculated from aggregating lesson percentages within the module |
| Course progress | Counted completed rows / total items | Calculated from aggregating all lesson percentages |
| Certificate | Manual request only | **Auto-issued** when course hits 100% |

### Hierarchy Reminder

```
Course
  └── Module 1
  │     ├── Lesson A  ← progress row (enrollment_id, item_type="lesson", progress_percentage=75)
  │     ├── Lesson B  ← progress row (enrollment_id, item_type="lesson", progress_percentage=100, completed_at=...)
  │     └── Lesson C  ← no row yet (user hasn't started)
  └── Module 2
        ├── Lesson D  ← progress row (enrollment_id, item_type="lesson", progress_percentage=30)
        └── Lesson E  ← no row yet

Module 1 progress = avg(75, 100, 0) / 100 = 58.33%    (0 for Lesson C since no row)
Module 2 progress = avg(30, 0) / 100 = 15.00%          (0 for Lesson E since no row)
Course progress   = avg(75, 100, 0, 30, 0) / 100 = 41.00%
```

One row per `(user_id, enrollment_id, item_type, item_id)`. That's it. Simple aggregation up the chain.

---

## 2. Current vs New Progress Table Design

### Current Table

```sql
CREATE TABLE progress (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL,
    course_id     INTEGER NOT NULL,          -- ❌ redundant, removing
    item_type     VARCHAR(20) NOT NULL,
    item_id       VARCHAR(50) NOT NULL,
    completed_at  TIMESTAMP NOT NULL,        -- ❌ always set, no partial tracking
    created_at    TIMESTAMP NOT NULL
                                             -- ❌ no updated_at
                                             -- ❌ no progress_percentage
);
-- UNIQUE(user_id, item_type, item_id)
```

### New Table

```sql
CREATE TABLE progress (
    id                   SERIAL PRIMARY KEY,
    user_id              INTEGER NOT NULL,
    enrollment_id        INTEGER NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
    item_type            VARCHAR(20) NOT NULL,       -- 'lesson', 'quiz', 'summary'
    item_id              VARCHAR(50) NOT NULL,
    progress_percentage  DECIMAL(5,2) NOT NULL DEFAULT 0.00,   -- 0.00 to 100.00
    completed_at         TIMESTAMP NULL,             -- set ONLY when progress_percentage = 100
    created_at           TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMP NOT NULL DEFAULT NOW()
);

-- One record per user + enrollment + item
UNIQUE(user_id, enrollment_id, item_type, item_id)
```

**Key design decisions:**
- **`progress_percentage`**: `DECIMAL(5,2)`, range 0.00–100.00. Allows partial progress (e.g., 65.50%).
- **`completed_at`**: Now **nullable**. Only populated when percentage hits 100. This way you can query "all completed lessons" with `WHERE completed_at IS NOT NULL`.
- **`updated_at`**: Tracks when the user last interacted with this lesson. Useful for "resume where you left off" and analytics.
- **Unique constraint changed**: From `(user_id, item_type, item_id)` to `(user_id, enrollment_id, item_type, item_id)`. This correctly scopes progress per enrollment — if a user re-enrolls (edge case), they get fresh progress.
- **Upsert behavior**: When the user updates progress on a lesson they already started, we `UPDATE` the existing row (percentage + updated_at) instead of doing nothing.

---

## 3. Database Migration

**File:** `services/course-service/src/alembic/versions/<new_revision>_refactor_progress_table.py`

Create a new Alembic migration. Set `down_revision` to whatever is currently the latest in your `versions/` folder (currently `a1b2c3d4e5f6`).

```python
"""refactor_progress_table

Revision ID: <generate_new_id>
Revises: a1b2c3d4e5f6
Create Date: 2026-02-19

"""
from alembic import op
import sqlalchemy as sa

revision = "<generate_new_id>"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Add new columns ────────────────────────────────────────

    # enrollment_id (nullable initially for data migration)
    op.add_column(
        "progress",
        sa.Column("enrollment_id", sa.Integer(), nullable=True),
    )

    # progress_percentage (default 0.00)
    op.add_column(
        "progress",
        sa.Column(
            "progress_percentage",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="0.00",
        ),
    )

    # updated_at
    op.add_column(
        "progress",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── 2. Backfill enrollment_id from enrollments table ──────────
    op.execute(
        """
        UPDATE progress p
        SET enrollment_id = e.id
        FROM enrollments e
        WHERE p.user_id = e.student_id
          AND p.course_id = e.course_id
        """
    )

    # Delete orphaned progress rows (no matching enrollment)
    op.execute("DELETE FROM progress WHERE enrollment_id IS NULL")

    # ── 3. Backfill progress_percentage for existing rows ─────────
    # Existing rows are already "completed" (that's how the old system worked),
    # so set them to 100.00
    op.execute("UPDATE progress SET progress_percentage = 100.00")

    # ── 4. Backfill updated_at from completed_at for existing rows
    op.execute("UPDATE progress SET updated_at = completed_at")

    # ── 5. Make enrollment_id NOT NULL ────────────────────────────
    op.alter_column("progress", "enrollment_id", nullable=False)

    # ── 6. Make completed_at NULLABLE ─────────────────────────────
    # (was NOT NULL before — now only set when progress = 100%)
    op.alter_column("progress", "completed_at", nullable=True)

    # ── 7. Add FK constraint for enrollment_id ────────────────────
    op.create_foreign_key(
        "fk_progress_enrollment",
        "progress",
        "enrollments",
        ["enrollment_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ── 8. Drop old unique constraint and indexes ─────────────────
    op.drop_constraint("uq_progress_user_item", "progress", type_="unique")
    op.drop_index("ix_progress_course_id", table_name="progress")
    op.drop_index("ix_progress_user_course", table_name="progress")

    # ── 9. Drop course_id column ──────────────────────────────────
    op.drop_column("progress", "course_id")

    # ── 10. Create new unique constraint and indexes ──────────────
    op.create_unique_constraint(
        "uq_progress_user_enrollment_item",
        "progress",
        ["user_id", "enrollment_id", "item_type", "item_id"],
    )
    op.create_index("ix_progress_enrollment_id", "progress", ["enrollment_id"])
    op.create_index(
        "ix_progress_user_enrollment", "progress", ["user_id", "enrollment_id"]
    )


def downgrade() -> None:
    # ── 1. Add course_id back ─────────────────────────────────────
    op.add_column(
        "progress",
        sa.Column("course_id", sa.Integer(), nullable=True),
    )

    # ── 2. Backfill course_id from enrollments ────────────────────
    op.execute(
        """
        UPDATE progress p
        SET course_id = e.course_id
        FROM enrollments e
        WHERE p.enrollment_id = e.id
        """
    )
    op.alter_column("progress", "course_id", nullable=False)

    # ── 3. Drop new constraint + indexes ──────────────────────────
    op.drop_constraint("uq_progress_user_enrollment_item", "progress", type_="unique")
    op.drop_index("ix_progress_enrollment_id", table_name="progress")
    op.drop_index("ix_progress_user_enrollment", table_name="progress")
    op.drop_constraint("fk_progress_enrollment", "progress", type_="foreignkey")

    # ── 4. Drop new columns ───────────────────────────────────────
    op.drop_column("progress", "enrollment_id")
    op.drop_column("progress", "progress_percentage")
    op.drop_column("progress", "updated_at")

    # ── 5. Restore completed_at to NOT NULL ───────────────────────
    op.alter_column("progress", "completed_at", nullable=False)

    # ── 6. Recreate old constraint + indexes ──────────────────────
    op.create_unique_constraint(
        "uq_progress_user_item", "progress", ["user_id", "item_type", "item_id"]
    )
    op.create_index("ix_progress_course_id", "progress", ["course_id"])
    op.create_index("ix_progress_user_course", "progress", ["user_id", "course_id"])
```

---

## 4. Model Changes

**File:** `services/course-service/src/models/progress.py`

Replace the entire file with:

```python
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)

from core.database import Base


class Progress(Base):
    """Progress model — tracks per-lesson progress for each enrollment."""

    __tablename__ = "progress"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    enrollment_id = Column(
        Integer,
        ForeignKey("enrollments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_type = Column(String(20), nullable=False)
    item_id = Column(String(50), nullable=False)
    progress_percentage = Column(Numeric(5, 2), nullable=False, default=0)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "enrollment_id", "item_type", "item_id",
            name="uq_progress_user_enrollment_item",
        ),
        Index("ix_progress_user_enrollment", "user_id", "enrollment_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<Progress(user={self.user_id}, enrollment={self.enrollment_id}, "
            f"item={self.item_type}:{self.item_id}, pct={self.progress_percentage})>"
        )
```

**What changed vs current file:**

| Column | Before | After |
|--------|--------|-------|
| `course_id` | `Column(Integer, nullable=False, index=True)` | **REMOVED** |
| `enrollment_id` | did not exist | `Column(Integer, ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False, index=True)` |
| `progress_percentage` | did not exist | `Column(Numeric(5, 2), nullable=False, default=0)` |
| `completed_at` | `default=datetime.utcnow, nullable=False` | `nullable=True` (no default — set explicitly only at 100%) |
| `updated_at` | did not exist | `Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)` |
| Unique constraint | `(user_id, item_type, item_id)` | `(user_id, enrollment_id, item_type, item_id)` |

---

## 5. Schema Changes

**File:** `services/course-service/src/schemas/progress.py`

Replace the entire file with:

```python
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Request Schemas ───────────────────────────────────────────────


class ProgressCreate(BaseModel):
    """Schema for creating or updating progress on a lesson/quiz/summary."""

    enrollment_id: int
    item_type: str = Field(..., pattern=r"^(lesson|quiz|summary)$")
    item_id: str
    progress_percentage: Decimal = Field(..., ge=0, le=100)


# ── Response Schemas ──────────────────────────────────────────────


class ProgressResponse(BaseModel):
    """Schema for a single progress record."""

    id: int
    user_id: int
    enrollment_id: int
    item_type: str
    item_id: str
    progress_percentage: Decimal
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ModuleProgressDetail(BaseModel):
    """Computed progress for a single module (not stored — calculated on the fly)."""

    module_id: str
    module_title: str
    total_lessons: int
    completed_lessons: int
    progress_percentage: Decimal
    lessons: List[dict]
    is_complete: bool


class CourseProgressSummary(BaseModel):
    """Computed course-level progress (aggregated from lesson-level data)."""

    course_id: int
    user_id: int
    enrollment_id: int
    total_lessons: int
    completed_lessons: int
    progress_percentage: Decimal
    module_progress: List[ModuleProgressDetail]
    has_certificate: bool
    is_complete: bool
```

**What changed vs current file:**

- `ProgressCreate`: `course_id` → `enrollment_id`, added `progress_percentage` field (required, 0–100)
- `ProgressResponse`: `course_id` → `enrollment_id`, added `progress_percentage`, `updated_at`, made `completed_at` optional, added `created_at`
- **NEW** `ModuleProgressDetail`: holds computed per-module data with a `lessons` list showing each lesson's status
- `CourseProgressSummary`: simplified — removed flat `completed_lessons`/`completed_quizzes`/`completed_summaries` string lists, replaced with structured `module_progress` array. Fields are now `total_lessons`, `completed_lessons` (counts), `progress_percentage` (overall)
- **REMOVED** `ProgressUpdate` schema (merged into `ProgressCreate` since create and update use the same upsert)

---

## 6. Repository Changes

**File:** `services/course-service/src/repositories/progress.py`

Replace the entire file with:

```python
from datetime import datetime
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.progress import Progress
from repositories.base import BaseRepository


class ProgressRepository(BaseRepository[Progress]):
    """Progress repository for PostgreSQL operations."""

    def __init__(self, db: AsyncSession):
        super().__init__(db, Progress)

    async def upsert_progress(
        self,
        user_id: int,
        enrollment_id: int,
        item_type: str,
        item_id: str,
        progress_percentage: float,
    ) -> Progress:
        """
        Create or update a progress record (upsert).

        - If no row exists: INSERT with the given percentage.
        - If row exists: UPDATE percentage (and completed_at if 100%).
        """
        completed_at = datetime.utcnow() if progress_percentage >= 100 else None

        stmt = (
            insert(Progress.__table__)
            .values(
                user_id=user_id,
                enrollment_id=enrollment_id,
                item_type=item_type,
                item_id=item_id,
                progress_percentage=progress_percentage,
                completed_at=completed_at,
                updated_at=datetime.utcnow(),
            )
            .on_conflict_do_update(
                constraint="uq_progress_user_enrollment_item",
                set_={
                    "progress_percentage": progress_percentage,
                    "completed_at": completed_at,
                    "updated_at": datetime.utcnow(),
                },
            )
            .returning(Progress.__table__.c.id)
        )

        result = await self.db.execute(stmt)
        await self.db.commit()

        row = result.one()
        return await self.get_by_id(row[0])

    async def get_by_user_and_item(
        self,
        user_id: int,
        enrollment_id: int,
        item_type: str,
        item_id: str,
    ) -> Optional[Progress]:
        """Get a specific progress record."""
        result = await self.db.execute(
            select(Progress).where(
                Progress.user_id == user_id,
                Progress.enrollment_id == enrollment_id,
                Progress.item_type == item_type,
                Progress.item_id == item_id,
            )
        )
        return result.scalars().first()

    async def get_enrollment_progress(
        self,
        enrollment_id: int,
    ) -> List[Progress]:
        """Get all progress records for an enrollment."""
        result = await self.db.execute(
            select(Progress)
            .where(Progress.enrollment_id == enrollment_id)
            .order_by(Progress.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_completed_items(
        self,
        enrollment_id: int,
        item_type: Optional[str] = None,
    ) -> List[Progress]:
        """Get all completed items (progress_percentage = 100) for an enrollment."""
        query = select(Progress).where(
            Progress.enrollment_id == enrollment_id,
            Progress.completed_at.isnot(None),
        )
        if item_type:
            query = query.where(Progress.item_type == item_type)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_completed(
        self,
        enrollment_id: int,
        item_type: Optional[str] = None,
    ) -> int:
        """Count completed items for an enrollment."""
        query = select(func.count()).select_from(Progress).where(
            Progress.enrollment_id == enrollment_id,
            Progress.completed_at.isnot(None),
        )
        if item_type:
            query = query.where(Progress.item_type == item_type)
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def delete_enrollment_progress(
        self,
        enrollment_id: int,
    ) -> int:
        """Delete all progress for an enrollment."""
        result = await self.db.execute(
            Progress.__table__.delete().where(
                Progress.enrollment_id == enrollment_id,
            )
        )
        await self.db.commit()
        return result.rowcount
```

**What changed vs current file:**

| Method | Before | After |
|--------|--------|-------|
| `mark_completed` | Insert-or-nothing, no percentage | **Renamed to `upsert_progress`** — insert-or-update with `progress_percentage`, sets `completed_at` only when ≥ 100 |
| `get_by_user_and_item` | Took `(user_id, item_type, item_id)` | Now also takes `enrollment_id` for scoped lookup |
| `get_user_course_progress` | Filtered by `course_id` | **Renamed to `get_enrollment_progress`** — filters by `enrollment_id`, ordered by `updated_at` |
| `get_completed_item_ids` | Returned string IDs | **Replaced with `get_completed_items`** — returns full Progress objects where `completed_at IS NOT NULL` |
| `count_completed` | Counted by `user_id + course_id` | Counts by `enrollment_id` where `completed_at IS NOT NULL` |
| `delete_progress` | By `user_id + course_id` | **Renamed to `delete_enrollment_progress`** — by `enrollment_id` only |

---

## 7. Service Changes

**File:** `services/course-service/src/services/progress.py`

Replace the entire file with:

```python
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List

from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.certificate import CertificateRepository
from repositories.course_content import CourseContentRepository
from repositories.enrollment import EnrollmentRepository
from repositories.progress import ProgressRepository
from schemas.progress import CourseProgressSummary, ModuleProgressDetail, ProgressCreate


class ProgressService:
    """Business logic for progress tracking."""

    def __init__(self, pg_db: AsyncSession, mongo_db: AsyncIOMotorDatabase):
        self.progress_repo = ProgressRepository(pg_db)
        self.enrollment_repo = EnrollmentRepository(pg_db)
        self.cert_repo = CertificateRepository(pg_db)
        self.content_repo = CourseContentRepository(mongo_db)
        self.pg_db = pg_db

    # ── UPDATE PROGRESS ───────────────────────────────────────────

    async def update_progress(
        self,
        user_id: int,
        data: ProgressCreate,
    ):
        """
        Create or update progress for a lesson/quiz/summary.

        Called every time a user interacts with a lesson (e.g., watches more
        of a video, re-opens a quiz, finishes reading). The frontend sends
        the current progress_percentage (0–100).
        """
        enrollment = await self.enrollment_repo.get_by_id(data.enrollment_id)
        if not enrollment:
            raise ValueError("Enrollment not found")
        if enrollment.student_id != user_id:
            raise ValueError("This enrollment does not belong to you")
        if enrollment.status not in ("active", "completed"):
            raise ValueError("Enrollment is not active")

        progress = await self.progress_repo.upsert_progress(
            user_id=user_id,
            enrollment_id=data.enrollment_id,
            item_type=data.item_type,
            item_id=data.item_id,
            progress_percentage=float(data.progress_percentage),
        )

        # Update enrollment timestamps
        update_data = {"last_accessed_at": datetime.utcnow()}
        if enrollment.started_at is None:
            update_data["started_at"] = datetime.utcnow()
        await self.enrollment_repo.update(enrollment.id, update_data)

        # Check if entire course is now 100%
        await self._check_auto_complete(enrollment.id, enrollment.course_id)

        return progress

    # ── GET PROGRESS ──────────────────────────────────────────────

    async def get_course_progress(
        self,
        user_id: int,
        course_id: int,
    ) -> CourseProgressSummary:
        """Get progress by course_id (convenience — looks up enrollment internally)."""
        enrollment = await self.enrollment_repo.get_by_student_and_course(
            user_id, course_id
        )
        if not enrollment:
            raise ValueError("User is not enrolled in this course")
        if enrollment.status not in ("active", "completed"):
            raise ValueError("Enrollment is not active (dropped or suspended)")

        return await self._build_progress_summary(user_id, enrollment.id, course_id)

    async def get_enrollment_progress(
        self,
        user_id: int,
        enrollment_id: int,
    ) -> CourseProgressSummary:
        """Get progress by enrollment_id (primary — use when you have enrollment_id)."""
        enrollment = await self.enrollment_repo.get_by_id(enrollment_id)
        if not enrollment:
            raise ValueError("Enrollment not found")
        if enrollment.student_id != user_id:
            raise ValueError("This enrollment does not belong to you")
        if enrollment.status not in ("active", "completed"):
            raise ValueError("Enrollment is not active (dropped or suspended)")

        return await self._build_progress_summary(
            user_id, enrollment.id, enrollment.course_id
        )

    # ── INTERNAL HELPERS ──────────────────────────────────────────

    async def _build_progress_summary(
        self,
        user_id: int,
        enrollment_id: int,
        course_id: int,
    ) -> CourseProgressSummary:
        """
        Build course progress by aggregating lesson-level progress records.

        For each module:
          1. Get all active lessons from MongoDB (the "total" count)
          2. Match against progress records from PostgreSQL
          3. Calculate module percentage = avg of all lesson percentages in that module
             (lessons with no progress row count as 0%)

        Course percentage = avg of ALL lesson percentages across ALL modules.
        """
        content = await self.content_repo.get_by_course_id(course_id)
        modules = content.get("modules", []) if content else []

        progress_records = await self.progress_repo.get_enrollment_progress(
            enrollment_id
        )
        # Build lookup: (item_type, item_id) → Progress record
        progress_map = {
            (p.item_type, p.item_id): p for p in progress_records
        }

        total_lessons_all = 0
        completed_lessons_all = 0
        all_lesson_percentages: List[float] = []
        module_progress_list: List[ModuleProgressDetail] = []

        for module in modules:
            if not module.get("is_active", True):
                continue

            module_lessons = self._get_active_lessons(module)
            module_total = len(module_lessons)
            module_completed = 0
            module_percentages: List[float] = []
            lesson_details: List[dict] = []

            for lesson_info in module_lessons:
                record = progress_map.get((lesson_info["type"], lesson_info["id"]))
                pct = float(record.progress_percentage) if record else 0.0
                is_done = record is not None and record.completed_at is not None

                if is_done:
                    module_completed += 1

                module_percentages.append(pct)
                lesson_details.append({
                    "item_type": lesson_info["type"],
                    "item_id": lesson_info["id"],
                    "title": lesson_info["title"],
                    "progress_percentage": pct,
                    "is_completed": is_done,
                })

            module_pct = Decimal("0.00")
            if module_percentages:
                avg = sum(module_percentages) / len(module_percentages)
                module_pct = Decimal(str(round(avg, 2)))

            module_progress_list.append(
                ModuleProgressDetail(
                    module_id=str(module.get("module_id")),
                    module_title=module.get("title", ""),
                    total_lessons=module_total,
                    completed_lessons=module_completed,
                    progress_percentage=module_pct,
                    lessons=lesson_details,
                    is_complete=(module_total > 0 and module_completed == module_total),
                )
            )

            total_lessons_all += module_total
            completed_lessons_all += module_completed
            all_lesson_percentages.extend(module_percentages)

        course_pct = Decimal("0.00")
        if all_lesson_percentages:
            avg = sum(all_lesson_percentages) / len(all_lesson_percentages)
            course_pct = Decimal(str(round(avg, 2)))

        cert = await self.cert_repo.get_by_enrollment(enrollment_id)
        has_certificate = cert is not None and not cert.is_revoked

        return CourseProgressSummary(
            course_id=course_id,
            user_id=user_id,
            enrollment_id=enrollment_id,
            total_lessons=total_lessons_all,
            completed_lessons=completed_lessons_all,
            progress_percentage=course_pct,
            module_progress=module_progress_list,
            has_certificate=has_certificate,
            is_complete=(
                total_lessons_all > 0
                and completed_lessons_all == total_lessons_all
            ),
        )

    @staticmethod
    def _get_active_lessons(module: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Extract all active trackable items from a module.
        Returns list of {type, id, title} dicts.
        """
        items = []
        for lesson in module.get("lessons", []):
            if not lesson.get("is_active", True):
                continue
            items.append({
                "type": "lesson",
                "id": str(lesson.get("lesson_id")),
                "title": lesson.get("title", ""),
            })

        for quiz in module.get("quizzes", []):
            if not quiz.get("is_active", True):
                continue
            items.append({
                "type": "quiz",
                "id": str(quiz.get("quiz_id")),
                "title": quiz.get("title", ""),
            })

        for summary in module.get("summaries", []):
            if not summary.get("is_active", True):
                continue
            items.append({
                "type": "summary",
                "id": str(summary.get("summary_id")),
                "title": summary.get("title", ""),
            })

        return items

    async def _check_auto_complete(
        self,
        enrollment_id: int,
        course_id: int,
    ) -> None:
        """
        After each progress update, check if all lessons are at 100%.
        If yes → mark enrollment completed + auto-issue certificate.
        """
        enrollment = await self.enrollment_repo.get_by_id(enrollment_id)
        if not enrollment or enrollment.status == "completed":
            return

        content = await self.content_repo.get_by_course_id(course_id)
        if not content:
            return

        modules = content.get("modules", [])
        all_items = []
        for module in modules:
            if not module.get("is_active", True):
                continue
            all_items.extend(self._get_active_lessons(module))

        if not all_items:
            return

        progress_records = await self.progress_repo.get_enrollment_progress(
            enrollment_id
        )
        completed_set = {
            (p.item_type, p.item_id)
            for p in progress_records
            if p.completed_at is not None
        }

        all_done = all(
            (item["type"], item["id"]) in completed_set
            for item in all_items
        )

        if not all_done:
            return

        # All items at 100% — mark enrollment completed
        await self.enrollment_repo.update(
            enrollment_id,
            {
                "status": "completed",
                "completed_at": datetime.utcnow(),
            },
        )

        # Auto-issue certificate (only if one doesn't already exist)
        existing_cert = await self.cert_repo.get_by_enrollment(enrollment_id)
        if existing_cert:
            return

        cert_data = {
            "enrollment_id": enrollment_id,
            "certificate_number": f"SC-{uuid.uuid4().hex[:12].upper()}",
            "issue_date": date.today(),
            "verification_code": uuid.uuid4().hex[:8].upper(),
            "grade": None,
            "score_percentage": Decimal("100.00"),
            "issued_by_id": None,
        }
        await self.cert_repo.create(cert_data)
```

**What changed vs current file:**

| Method | Before | After |
|--------|--------|-------|
| `mark_completed` | Binary — item is instantly "done" | **Renamed to `update_progress`** — accepts `progress_percentage`, calls `upsert_progress` |
| `get_course_progress` | Built flat summary | Now delegates to `_build_progress_summary` |
| *(new)* `get_enrollment_progress` | Did not exist | Lookup by enrollment_id directly |
| `_get_active_items` | Returned `{type, id}` | **Renamed to `_get_active_lessons`** — also returns `title` for inclusion in response |
| `_build_progress_summary` | Did not exist (was inline in `get_course_progress`) | Extracted method: aggregates lesson percentages → module percentages → course percentage |
| `_check_auto_complete` | Only set enrollment to `completed` | Now also **auto-issues a certificate** when all items are at 100%. Checks existence first to avoid duplicates |

---

## 8. API Endpoint Changes

**File:** `services/course-service/src/api/progress.py`

Replace the entire file with:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_id
from core.database import get_db
from core.mongodb import get_mongodb
from schemas.progress import CourseProgressSummary, ProgressCreate, ProgressResponse
from services.progress import ProgressService

router = APIRouter()


@router.post("", response_model=ProgressResponse, status_code=status.HTTP_201_CREATED)
async def update_progress(
    data: ProgressCreate,
    user_id: int = Depends(get_current_user_id),
    pg_db: AsyncSession = Depends(get_db),
):
    """
    Create or update progress on a lesson/quiz/summary.

    Body:
      - enrollment_id: int
      - item_type: "lesson" | "quiz" | "summary"
      - item_id: str (MongoDB lesson/quiz/summary ID)
      - progress_percentage: 0–100

    When progress_percentage reaches 100, the item is marked as completed
    (completed_at is set). If ALL items in the course reach 100%, the
    enrollment is auto-completed and a certificate is auto-issued.
    """
    mongo_db = get_mongodb()
    service = ProgressService(pg_db, mongo_db)
    try:
        progress = await service.update_progress(user_id, data)
        return ProgressResponse.model_validate(progress)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/enrollment/{enrollment_id}", response_model=CourseProgressSummary)
async def get_progress_by_enrollment(
    enrollment_id: int,
    user_id: int = Depends(get_current_user_id),
    pg_db: AsyncSession = Depends(get_db),
):
    """
    Get full course progress by enrollment ID (primary endpoint).
    Returns course-level, module-level, and per-lesson progress.
    """
    mongo_db = get_mongodb()
    service = ProgressService(pg_db, mongo_db)
    try:
        return await service.get_enrollment_progress(user_id, enrollment_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/course/{course_id}", response_model=CourseProgressSummary)
async def get_progress_by_course(
    course_id: int,
    user_id: int = Depends(get_current_user_id),
    pg_db: AsyncSession = Depends(get_db),
):
    """
    Get full course progress by course ID (convenience endpoint).
    Internally looks up the enrollment for the current user.
    """
    mongo_db = get_mongodb()
    service = ProgressService(pg_db, mongo_db)
    try:
        return await service.get_course_progress(user_id, course_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
```

**What changed vs current file:**

| Endpoint | Before | After |
|----------|--------|-------|
| `POST /course/progress` | Body: `{course_id, item_type, item_id}` — binary mark-as-done | Body: `{enrollment_id, item_type, item_id, progress_percentage}` — upsert with percentage |
| `GET /course/progress/{course_id}` | Single endpoint by course_id | **Split into two:** |
| `GET /course/progress/enrollment/{enrollment_id}` | Did not exist | Primary — lookup by enrollment_id |
| `GET /course/progress/course/{course_id}` | Was the only GET | Convenience — resolves enrollment internally |

---

## 9. ERD / Docs Update

**File:** `docs/SmartCourse-ERD-Complete.md`

### 9.1 Replace the Progress Section

Find the section titled `#### **~~PROGRESS~~ (REMOVED - Merged into ENROLLMENTS)**` and replace it with:

```markdown
#### **PROGRESS**

Tracks per-lesson progress for each enrollment. One row per (user, enrollment, item).

| Column              | Type          | Constraints                               | Description                                     |
| ------------------- | ------------- | ----------------------------------------- | ----------------------------------------------- |
| id                  | SERIAL        | PRIMARY KEY                               | Auto-incrementing identifier                    |
| user_id             | INTEGER       | NOT NULL, INDEX                           | User who owns this progress                     |
| enrollment_id       | INTEGER       | FK → enrollments(id), NOT NULL, INDEX     | The enrollment this progress belongs to         |
| item_type           | VARCHAR(20)   | NOT NULL                                  | 'lesson', 'quiz', or 'summary'                 |
| item_id             | VARCHAR(50)   | NOT NULL                                  | MongoDB ID of the lesson/quiz/summary           |
| progress_percentage | DECIMAL(5,2)  | NOT NULL, DEFAULT 0.00                    | 0.00 to 100.00 — how far the user has progressed |
| completed_at        | TIMESTAMP     | NULLABLE                                  | Set only when progress_percentage reaches 100   |
| created_at          | TIMESTAMP     | NOT NULL, DEFAULT NOW()                   | Row creation timestamp                          |
| updated_at          | TIMESTAMP     | NOT NULL, DEFAULT NOW()                   | Last progress update timestamp                  |

**Unique Constraint:** `(user_id, enrollment_id, item_type, item_id)`

**How Progress Aggregation Works:**
- **Lesson progress**: Stored directly as `progress_percentage` (0–100) in each row
- **Module progress**: Average of all lesson percentages within the module (lessons with no row = 0%)
- **Course progress**: Average of ALL lesson percentages across ALL modules
- **Completion**: An item is "completed" when `progress_percentage = 100` and `completed_at IS NOT NULL`
- **Course completion**: When ALL items reach 100%, enrollment status → 'completed', certificate auto-issued
```

### 9.2 Update Relationship Summary

Replace the Progress line in the relationship table:

```markdown
| Enrollments → Progress | 1:N | One enrollment has many progress records (one per lesson) |
```

### 9.3 Update Key Indexes Section

Remove the "Progress table REMOVED" comment and add:

```sql
-- Progress
CREATE INDEX ix_progress_user_id ON progress(user_id);
CREATE INDEX ix_progress_enrollment_id ON progress(enrollment_id);
CREATE INDEX ix_progress_user_enrollment ON progress(user_id, enrollment_id);
CREATE UNIQUE INDEX uq_progress_user_enrollment_item ON progress(user_id, enrollment_id, item_type, item_id);
```

### 9.4 Update Foreign Key Constraints Section

Add:

```sql
-- Progress
ALTER TABLE progress
ADD CONSTRAINT fk_progress_enrollment
FOREIGN KEY (enrollment_id) REFERENCES enrollments(id) ON DELETE CASCADE;
```

---

## 10. Full File-by-File Change List

| #  | File | Action | Description |
|----|------|--------|-------------|
| 1  | `alembic/versions/<new>_refactor_progress_table.py` | **CREATE** | Migration: add `enrollment_id`, `progress_percentage`, `updated_at`; make `completed_at` nullable; drop `course_id`; update unique constraint |
| 2  | `models/progress.py` | **REPLACE** | New columns, FK, updated constraint |
| 3  | `schemas/progress.py` | **REPLACE** | `enrollment_id` + `progress_percentage` in request/response, new `ModuleProgressDetail`, simplified `CourseProgressSummary` |
| 4  | `repositories/progress.py` | **REPLACE** | `upsert_progress` (insert-or-update), all methods use `enrollment_id` |
| 5  | `services/progress.py` | **REPLACE** | `update_progress`, `_build_progress_summary` with aggregation, auto-cert in `_check_auto_complete` |
| 6  | `api/progress.py` | **REPLACE** | POST accepts percentage, GET split into `/enrollment/{id}` and `/course/{id}` |
| 7  | `docs/SmartCourse-ERD-Complete.md` | **EDIT** | Updated Progress table, relationships, indexes, FK constraints |
| 8  | `main.py` | **NO CHANGE** | Already imports Progress model |
| 9  | `api/router.py` | **NO CHANGE** | Route prefix `/course/progress` stays the same |
| 10 | `services/certificate.py` | **NO CHANGE** | Manual certificate endpoint still works alongside auto-cert |
| 11 | `api/certificates.py` | **NO CHANGE** | Returns "already issued" if auto-cert exists |
| 12 | `models/enrollment.py` | **NO CHANGE** | |
| 13 | `models/certificate.py` | **NO CHANGE** | |
| 14 | `repositories/enrollment.py` | **NO CHANGE** | |
| 15 | `repositories/certificate.py` | **NO CHANGE** | |

---

## 11. Migration Order / Execution Steps

**IMPORTANT**: Update the model file BEFORE running the migration only if you're using `--autogenerate`. If writing the migration manually (as provided above), the order doesn't matter as long as the model matches the final DB state.

### Step 1: Write the migration file
Copy the migration from Section 3 into `alembic/versions/`. Generate a revision ID with:
```bash
cd services/course-service/src
python -c "import uuid; print(uuid.uuid4().hex[:12])"
```

### Step 2: Replace all source files
Replace these 5 files with the code from this guide (Sections 4–8):
1. `models/progress.py`
2. `schemas/progress.py`
3. `repositories/progress.py`
4. `services/progress.py`
5. `api/progress.py`

### Step 3: Run the migration
```bash
cd services/course-service/src
alembic upgrade head
```

### Step 4: Verify data
```sql
-- Check that enrollment_id was backfilled correctly
SELECT p.id, p.user_id, p.enrollment_id, e.student_id, e.course_id
FROM progress p
JOIN enrollments e ON p.enrollment_id = e.id;

-- Check that existing rows got progress_percentage = 100
SELECT id, progress_percentage, completed_at FROM progress;

-- Check course_id column is gone
SELECT column_name FROM information_schema.columns WHERE table_name = 'progress';
```

### Step 5: Update ERD docs
Edit `docs/SmartCourse-ERD-Complete.md` as described in Section 9.

### Step 6: Test
Follow the checklist in Section 12.

---

## 12. Testing Checklist

### Schema & Migration

- [ ] `alembic upgrade head` succeeds without errors
- [ ] `progress` table has columns: `id, user_id, enrollment_id, item_type, item_id, progress_percentage, completed_at, created_at, updated_at`
- [ ] `course_id` column no longer exists in `progress`
- [ ] Existing rows have `enrollment_id` correctly backfilled
- [ ] Existing rows have `progress_percentage = 100.00` and `completed_at` preserved
- [ ] Unique constraint `uq_progress_user_enrollment_item` exists
- [ ] FK `fk_progress_enrollment` exists referencing `enrollments(id)`
- [ ] `alembic downgrade -1` works correctly

### POST /course/progress (Create/Update Progress)

- [ ] Send `{enrollment_id, item_type: "lesson", item_id: "abc", progress_percentage: 50}` → 201, creates new row with `progress_percentage=50`, `completed_at=NULL`
- [ ] Send same request with `progress_percentage: 75` → 201, **updates** existing row to 75%, `completed_at` still NULL, `updated_at` changed
- [ ] Send same request with `progress_percentage: 100` → 201, updates to 100%, `completed_at` is now set
- [ ] Send with old `course_id` field instead of `enrollment_id` → validation error
- [ ] Send with invalid `enrollment_id` → 400 "Enrollment not found"
- [ ] Send with another user's enrollment → 400 "This enrollment does not belong to you"
- [ ] Send with dropped enrollment → 400 "Enrollment is not active"

### GET /course/progress/enrollment/{enrollment_id}

- [ ] Returns `CourseProgressSummary` with `module_progress` array
- [ ] Each module shows `total_lessons`, `completed_lessons`, `progress_percentage`, `lessons` list
- [ ] Each lesson in `lessons` list shows `item_id`, `progress_percentage`, `is_completed`
- [ ] Lessons with no progress row show 0% and `is_completed: false`
- [ ] Module `progress_percentage` = average of its lesson percentages
- [ ] Course `progress_percentage` = average of all lesson percentages
- [ ] `is_complete` is true only when ALL lessons are at 100%
- [ ] Returns 404 for invalid enrollment_id

### GET /course/progress/course/{course_id}

- [ ] Returns same `CourseProgressSummary` structure as enrollment endpoint
- [ ] Internally resolves the enrollment for the current user
- [ ] Returns 404 if user is not enrolled

### Auto-Completion + Certificate

- [ ] When all items reach 100%, enrollment `status` changes to `completed`
- [ ] When all items reach 100%, a certificate is automatically created
- [ ] Auto-issued certificate has `issued_by_id = NULL` (system-issued)
- [ ] `has_certificate: true` appears in progress response after auto-issue
- [ ] `POST /course/certificates/` for same enrollment → "Certificate already issued"
- [ ] Partial progress (not all items at 100%) does NOT trigger completion
- [ ] Certificate `score_percentage` is 100.00

---

## Appendix: Example API Response

`GET /course/progress/enrollment/3`

```json
{
  "course_id": 5,
  "user_id": 3,
  "enrollment_id": 3,
  "total_lessons": 8,
  "completed_lessons": 3,
  "progress_percentage": 46.25,
  "module_progress": [
    {
      "module_id": "1",
      "module_title": "Getting Started",
      "total_lessons": 3,
      "completed_lessons": 2,
      "progress_percentage": 83.33,
      "lessons": [
        {
          "item_type": "lesson",
          "item_id": "674a1b2c3d4e5f6a7b8c9d0e",
          "title": "Welcome & Setup",
          "progress_percentage": 100.0,
          "is_completed": true
        },
        {
          "item_type": "lesson",
          "item_id": "698ed412a897034ee8ca80a7",
          "title": "Your First Project",
          "progress_percentage": 100.0,
          "is_completed": true
        },
        {
          "item_type": "lesson",
          "item_id": "698ed4c5a897034ee8ca80aa",
          "title": "Core Concepts",
          "progress_percentage": 50.0,
          "is_completed": false
        }
      ],
      "is_complete": false
    },
    {
      "module_id": "2",
      "module_title": "Advanced Topics",
      "total_lessons": 5,
      "completed_lessons": 1,
      "progress_percentage": 25.0,
      "lessons": [
        {
          "item_type": "lesson",
          "item_id": "698ed4c5a897034ee8ca80aas",
          "title": "Deep Dive",
          "progress_percentage": 100.0,
          "is_completed": true
        },
        {
          "item_type": "lesson",
          "item_id": "698ed412a897034ee8ca80a6",
          "title": "Patterns",
          "progress_percentage": 25.0,
          "is_completed": false
        },
        {
          "item_type": "lesson",
          "item_id": "698efe5761d01a23d4d29924",
          "title": "Testing",
          "progress_percentage": 0.0,
          "is_completed": false
        },
        {
          "item_type": "quiz",
          "item_id": "quiz_mod2_1",
          "title": "Module 2 Quiz",
          "progress_percentage": 0.0,
          "is_completed": false
        },
        {
          "item_type": "summary",
          "item_id": "summary_mod2_1",
          "title": "Module 2 Summary",
          "progress_percentage": 0.0,
          "is_completed": false
        }
      ],
      "is_complete": false
    }
  ],
  "has_certificate": false,
  "is_complete": false
}
```

---

*Document Version: 2.0 | Created: February 19, 2026*
