# Course Service - Schema Migration & Progress Tracking Refactor

**Version:** 2.0  
**Date:** February 13, 2026  
**Purpose:** Complete implementation guide for:

1. Migrating MongoDB `module_id` and `lesson_id` from integers to ObjectId strings
2. Adding `is_active` field for soft delete support
3. Refactoring progress tracking to solve data synchronization issues

---

## 1. Problem Statement

### 1.1 Current Architecture

The system uses two databases:

- **PostgreSQL**: Stores courses metadata, enrollments (with embedded progress arrays), and certificates.
- **MongoDB**: Stores course content (modules → lessons structure).

### 1.2 Current Issues

#### Issue 1: Integer IDs in MongoDB (Non-Standard)

Current MongoDB document structure uses **integer IDs**:

```json
{
  "_id": ObjectId("698da3520d082d817a90fae6"),
  "course_id": 4,
  "modules": [
    {
      "module_id": 1,
      "title": "Introduction - Updated Title",
      "lessons": [
        {
          "lesson_id": 1,
          "title": "Welcome Video"
        },
        {
          "lesson_id": 2,
          "title": "Course Overview"
        }
      ]
    }
  ]
}
```

**Problems with integer IDs:**

- Not globally unique across documents.
- Requires manual ID management (auto-increment logic).
- Collision risk when content is copied between courses.
- Not idiomatic MongoDB design.

#### Issue 2: Progress Arrays in Enrollment (Sync Problem)

Current `Enrollment` model embeds progress as **PostgreSQL arrays**:

```python
completed_modules = Column(ARRAY(Integer), default=list, nullable=False)
completed_lessons = Column(ARRAY(Integer), default=list, nullable=False)
total_modules = Column(Integer, default=0, nullable=False)
total_lessons = Column(Integer, default=0, nullable=False)
completion_percentage = Column(Numeric(5, 2), default=0.00, nullable=False)
completed_quizzes = Column(ARRAY(Integer), default=list, nullable=False)
quiz_scores = Column(JSONB, nullable=True)
```

**Problems:**

- When instructor modifies course content in MongoDB, `total_modules` and `total_lessons` become stale.
- The `completed_modules` and `completed_lessons` arrays may contain IDs that no longer exist.
- If a course has 10,000 enrolled students and instructor updates content, system must update **10,000 rows** in PostgreSQL.

#### Issue 3: No Soft Delete Support

Current system has no `is_active` field on modules/lessons:

- Hard deletes break referential integrity with progress records.
- No way to "archive" content without losing history.

---

## 2. Current Schema Analysis

### 2.1 PostgreSQL Tables

#### `enrollments` table (current - problematic)

| Column                  | Type           | Issue                                                        |
| ----------------------- | -------------- | ------------------------------------------------------------ |
| `completed_modules`     | `INTEGER[]`    | Array stores module IDs - becomes stale on content change    |
| `completed_lessons`     | `INTEGER[]`    | Array stores lesson IDs - becomes stale on content change    |
| `total_modules`         | `INTEGER`      | Cached count - must be updated when content changes          |
| `total_lessons`         | `INTEGER`      | Cached count - must be updated when content changes          |
| `completion_percentage` | `DECIMAL(5,2)` | Derived value - must be recalculated on every content change |
| `completed_quizzes`     | `INTEGER[]`    | Array stores quiz IDs - same problem                         |
| `quiz_scores`           | `JSONB`        | Quiz results - acceptable but should be separate             |

#### `certificates` table (no changes needed)

- Links to `enrollment_id`.
- Certificate is a terminal achievement (100% at time of issue).
- No changes required.

### 2.2 MongoDB Collection

#### `course_content` collection (current)

```json
{
  "_id": ObjectId("698da3520d082d817a90fae6"),
  "course_id": 4,
  "created_at": "2026-02-12T09:54:26.390+00:00",
  "metadata": {
    "total_modules": 4,
    "total_lessons": 8
  },
  "modules": [
    {
      "module_id": 1,
      "title": "Introduction - Updated Title",
      "description": "Updated description for getting started",
      "order": 1,
      "is_published": true,
      "lessons": [
        {
          "lesson_id": 1,
          "title": "Welcome Video",
          "type": "video",
          "content": "Introduction to what you'll learn",
          "duration_minutes": 10,
          "order": 1,
          "is_preview": true,
          "resources": [
            {
              "name": "Advanced Python Tutorial",
              "url": "https://storage.example.com/videos/python-advanced.mp4",
              "type": "video"
            }
          ]
        },
        {
          "lesson_id": 2,
          "title": "Course Overview",
          "type": "text",
          "content": "Detailed syllabus and expectations",
          "duration_minutes": 5,
          "order": 2,
          "is_preview": false,
          "resources": []
        }
      ]
    }
  ],
  "updated_at": "2026-02-12T10:30:15.000+00:00"
}
```

**Issues:**

- `module_id` and `lesson_id` are integers (1, 2, 3...).
- No `is_active` field for soft delete.

---

## 3. Solution Architecture

### 3.1 Core Principles

1. **Use ObjectId strings for content IDs**: Auto-generated, globally unique, no collision risk.
2. **Store completion events, not structure**: Progress is stored as discrete events (one row per completed item).
3. **Compute progress at read time**: Compare completed items against current active content.
4. **Soft delete with `is_active`**: Never hard-delete content; mark as inactive instead.

### 3.2 Target Data Model

#### MongoDB: New Structure with ObjectId Strings

```json
{
  "_id": ObjectId("698da3520d082d817a90fae6"),
  "course_id": 4,
  "modules": [
    {
      "module_id": "65f1a2b3c4d5e6f7a8b9c0d1",
      "title": "Introduction",
      "order": 1,
      "is_published": true,
      "is_active": true,
      "lessons": [
        {
          "lesson_id": "65f1a2b3c4d5e6f7a8b9c0d2",
          "title": "Welcome Video",
          "type": "video",
          "is_active": true
        }
      ]
    }
  ]
}
```

#### PostgreSQL: New `progress` Table

| Column         | Type          | Constraints               | Description                       |
| -------------- | ------------- | ------------------------- | --------------------------------- |
| `id`           | `SERIAL`      | `PRIMARY KEY`             | Auto-increment ID                 |
| `user_id`      | `INTEGER`     | `NOT NULL, INDEX`         | Student who completed the item    |
| `course_id`    | `INTEGER`     | `NOT NULL, INDEX`         | Course context                    |
| `item_type`    | `VARCHAR(20)` | `NOT NULL`                | `'lesson'`, `'quiz'`, `'summary'` |
| `item_id`      | `VARCHAR(50)` | `NOT NULL`                | ObjectId string from MongoDB      |
| `completed_at` | `TIMESTAMP`   | `NOT NULL, DEFAULT NOW()` | Completion timestamp              |
| `created_at`   | `TIMESTAMP`   | `NOT NULL, DEFAULT NOW()` | Row creation time                 |

**Indexes:**

- `UNIQUE (user_id, item_type, item_id)` — prevents duplicate completions.
- `INDEX (user_id, course_id)` — fast lookup of user progress per course.

#### PostgreSQL: Simplified `enrollments` Table

**Columns to REMOVE:**

- `completed_modules`
- `completed_lessons`
- `total_modules`
- `total_lessons`
- `completion_percentage`
- `completed_quizzes`
- `quiz_scores`
- `current_module_id`
- `current_lesson_id`

**Columns to KEEP:**

- `id`, `student_id`, `course_id`
- `status` (active, completed, dropped, suspended)
- `enrolled_at`, `started_at`, `completed_at`, `dropped_at`
- `last_accessed_at`
- `payment_status`, `payment_amount`, `enrollment_source`
- `time_spent_minutes`
- `created_at`, `updated_at`

---

## 4. Implementation Steps

### PHASE 1: MongoDB Schema Updates (ObjectId + is_active)

#### 4.1 Update Pydantic Schemas for Course Content

**File:** `services/course-service/src/schemas/course_content.py`

Change `module_id` and `lesson_id` from `int` to `Optional[str]` (auto-generated if not provided):

```python
from datetime import datetime
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, Field


def generate_object_id() -> str:
    """Generate a new ObjectId as string."""
    return str(ObjectId())


class ResourceSchema(BaseModel):
    """A single resource attached to a lesson."""
    resource_id: str = Field(default_factory=generate_object_id)
    name: str
    url: str
    type: str
    is_active: bool = True


class LessonSchema(BaseModel):
    """A single lesson within a module."""
    lesson_id: str = Field(default_factory=generate_object_id)
    title: str
    type: str = Field(..., pattern=r"^(video|text|quiz|assignment)$")
    content: Optional[str] = None
    duration_minutes: Optional[int] = None
    order: int
    is_preview: bool = False
    is_active: bool = True
    resources: list[ResourceSchema] = []


class ModuleSchema(BaseModel):
    """A single module containing lessons."""
    module_id: str = Field(default_factory=generate_object_id)
    title: str
    description: Optional[str] = None
    order: int
    is_published: bool = True
    is_active: bool = True
    lessons: list[LessonSchema] = []


class CourseContentMetadata(BaseModel):
    """Metadata stored alongside course content."""
    total_modules: int = 0
    total_lessons: int = 0
    total_duration_hours: Optional[float] = None
    tags: list[str] = []


class CourseContentCreate(BaseModel):
    """Schema for creating/replacing full course content."""
    modules: list[ModuleSchema] = []
    metadata: Optional[CourseContentMetadata] = None


class CourseContentResponse(BaseModel):
    """Schema for course content API responses."""
    course_id: int
    modules: list[ModuleSchema] = []
    metadata: Optional[CourseContentMetadata] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ModuleCreate(BaseModel):
    """Schema for adding a single module."""
    module_id: str = Field(default_factory=generate_object_id)
    title: str
    description: Optional[str] = None
    order: int
    is_published: bool = True
    is_active: bool = True
    lessons: list[LessonSchema] = []


class LessonCreate(BaseModel):
    """Schema for adding a single lesson to a module."""
    lesson_id: str = Field(default_factory=generate_object_id)
    title: str
    type: str = Field(..., pattern=r"^(video|text|quiz|assignment)$")
    content: Optional[str] = None
    duration_minutes: Optional[int] = None
    order: int
    is_preview: bool = False
    is_active: bool = True
    resources: list[ResourceSchema] = []


class ModuleUpdate(BaseModel):
    """Schema for updating a module."""
    title: Optional[str] = None
    description: Optional[str] = None
    order: Optional[int] = None
    is_published: Optional[bool] = None
    is_active: Optional[bool] = None


class LessonUpdate(BaseModel):
    """Schema for updating a lesson."""
    title: Optional[str] = None
    type: Optional[str] = Field(None, pattern=r"^(video|text|quiz|assignment)$")
    content: Optional[str] = None
    duration_minutes: Optional[int] = None
    order: Optional[int] = None
    is_preview: Optional[bool] = None
    is_active: Optional[bool] = None


class MediaResourceCreate(BaseModel):
    """Schema for adding media resources."""
    resource_id: str = Field(default_factory=generate_object_id)
    name: str
    url: str
    type: str = Field(..., pattern=r"^(video|pdf|audio|image|link)$")
    is_active: bool = True


class MediaResourceUpdate(BaseModel):
    """Schema for updating a media resource."""
    name: Optional[str] = None
    url: Optional[str] = None
    type: Optional[str] = Field(None, pattern=r"^(video|pdf|audio|image|link)$")
    is_active: Optional[bool] = None
```

#### 4.2 Update Course Content Repository

**File:** `services/course-service/src/repositories/course_content.py`

Change all `module_id: int` and `lesson_id: int` parameters to `str`:

```python
from datetime import datetime
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument


class CourseContentRepository:
    """Course content repository for MongoDB operations."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db["course_content"]

    async def get_by_course_id(self, course_id: int) -> Optional[dict[str, Any]]:
        """Get course content document by course_id."""
        return await self.collection.find_one({"course_id": course_id})

    async def create(self, course_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new course content document."""
        now = datetime.utcnow()
        document = {
            "course_id": course_id,
            "modules": data.get("modules", []),
            "metadata": data.get("metadata", {}),
            "created_at": now,
            "updated_at": now,
        }
        result = await self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    async def update(self, course_id: int, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Replace course content for a given course_id."""
        now = datetime.utcnow()
        update_data = {
            "modules": data.get("modules", []),
            "metadata": data.get("metadata", {}),
            "updated_at": now,
        }
        result = await self.collection.find_one_and_update(
            {"course_id": course_id},
            {"$set": update_data},
            return_document=ReturnDocument.AFTER,
        )
        return result

    async def upsert(self, course_id: int, data: dict[str, Any]) -> dict[str, Any]:
        """Create or update course content (upsert)."""
        now = datetime.utcnow()
        update_data = {
            "modules": data.get("modules", []),
            "metadata": data.get("metadata", {}),
            "updated_at": now,
        }
        result = await self.collection.find_one_and_update(
            {"course_id": course_id},
            {
                "$set": update_data,
                "$setOnInsert": {"course_id": course_id, "created_at": now},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return result

    async def delete(self, course_id: int) -> bool:
        """Delete course content document."""
        result = await self.collection.delete_one({"course_id": course_id})
        return result.deleted_count > 0

    async def add_module(self, course_id: int, module: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Add a module to course content."""
        result = await self.collection.find_one_and_update(
            {"course_id": course_id},
            {
                "$push": {"modules": module},
                "$set": {"updated_at": datetime.utcnow()},
            },
            return_document=ReturnDocument.AFTER,
        )
        return result

    async def add_lesson_to_module(
        self, course_id: int, module_id: str, lesson: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Add a lesson to a specific module."""
        result = await self.collection.find_one_and_update(
            {"course_id": course_id, "modules.module_id": module_id},
            {
                "$push": {"modules.$.lessons": lesson},
                "$set": {"updated_at": datetime.utcnow()},
            },
            return_document=ReturnDocument.AFTER,
        )
        return result

    async def update_module(
        self, course_id: int, module_id: str, update_data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Update a module's fields."""
        set_fields = {f"modules.$.{k}": v for k, v in update_data.items()}
        set_fields["updated_at"] = datetime.utcnow()

        result = await self.collection.find_one_and_update(
            {"course_id": course_id, "modules.module_id": module_id},
            {"$set": set_fields},
            return_document=ReturnDocument.AFTER,
        )
        return result

    async def update_lesson(
        self, course_id: int, module_id: str, lesson_id: str, update_data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Update a lesson's fields within a module."""
        doc = await self.collection.find_one({"course_id": course_id})
        if not doc:
            return None

        module_idx = None
        lesson_idx = None
        for m_idx, module in enumerate(doc.get("modules", [])):
            if module.get("module_id") == module_id:
                module_idx = m_idx
                for l_idx, lesson in enumerate(module.get("lessons", [])):
                    if lesson.get("lesson_id") == lesson_id:
                        lesson_idx = l_idx
                        break
                break

        if module_idx is None or lesson_idx is None:
            return None

        set_fields = {
            f"modules.{module_idx}.lessons.{lesson_idx}.{k}": v
            for k, v in update_data.items()
        }
        set_fields["updated_at"] = datetime.utcnow()

        result = await self.collection.find_one_and_update(
            {"course_id": course_id},
            {"$set": set_fields},
            return_document=ReturnDocument.AFTER,
        )
        return result

    async def soft_delete_module(
        self, course_id: int, module_id: str
    ) -> Optional[dict[str, Any]]:
        """Soft-delete a module (set is_active=false)."""
        return await self.update_module(course_id, module_id, {"is_active": False})

    async def soft_delete_lesson(
        self, course_id: int, module_id: str, lesson_id: str
    ) -> Optional[dict[str, Any]]:
        """Soft-delete a lesson (set is_active=false)."""
        return await self.update_lesson(course_id, module_id, lesson_id, {"is_active": False})

    async def add_resource_to_lesson(
        self, course_id: int, module_id: str, lesson_id: str, resource: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Add a resource to a lesson."""
        doc = await self.collection.find_one({"course_id": course_id})
        if not doc:
            return None

        module_idx = None
        lesson_idx = None
        for m_idx, module in enumerate(doc.get("modules", [])):
            if module.get("module_id") == module_id:
                module_idx = m_idx
                for l_idx, lesson in enumerate(module.get("lessons", [])):
                    if lesson.get("lesson_id") == lesson_id:
                        lesson_idx = l_idx
                        break
                break

        if module_idx is None or lesson_idx is None:
            return None

        result = await self.collection.find_one_and_update(
            {"course_id": course_id},
            {
                "$push": {f"modules.{module_idx}.lessons.{lesson_idx}.resources": resource},
                "$set": {"updated_at": datetime.utcnow()},
            },
            return_document=ReturnDocument.AFTER,
        )
        return result
```

#### 4.3 Update Course Content Service

**File:** `services/course-service/src/services/course_content.py`

Change method signatures to use `str` for IDs and add soft delete methods:

```python
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from core.cache import cache_delete, cache_get, cache_set
from repositories.course_content import CourseContentRepository
from schemas.course_content import (
    CourseContentCreate,
    LessonCreate,
    LessonUpdate,
    MediaResourceCreate,
    ModuleCreate,
    ModuleUpdate,
)


CONTENT_TTL = 900


class CourseContentService:
    """Business logic for course content (MongoDB)."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.content_repo = CourseContentRepository(db)

    async def get_content(self, course_id: int) -> dict[str, Any] | None:
        """Get full course content by course_id."""
        cache_key = f"course:content:{course_id}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        doc = await self.content_repo.get_by_course_id(course_id)
        if doc:
            doc.pop("_id", None)
            await cache_set(cache_key, doc, ttl=CONTENT_TTL)

        return doc

    async def create_or_update_content(
        self, course_id: int, data: CourseContentCreate
    ) -> dict[str, Any]:
        """Create or fully replace course content (upsert)."""
        content_data = data.model_dump()

        if data.metadata is None:
            total_modules = len(data.modules)
            total_lessons = sum(len(m.lessons) for m in data.modules)
            content_data["metadata"] = {
                "total_modules": total_modules,
                "total_lessons": total_lessons,
                "total_duration_hours": None,
                "tags": [],
            }

        doc = await self.content_repo.upsert(course_id, content_data)
        doc.pop("_id", None)

        await cache_delete(f"course:content:{course_id}")

        return doc

    async def add_module(self, course_id: int, data: ModuleCreate) -> dict[str, Any] | None:
        """Add a single module to existing course content."""
        module_data = data.model_dump()
        doc = await self.content_repo.add_module(course_id, module_data)
        if doc:
            doc.pop("_id", None)
            await cache_delete(f"course:content:{course_id}")
        return doc

    async def add_lesson(
        self, course_id: int, module_id: str, data: LessonCreate
    ) -> dict[str, Any] | None:
        """Add a single lesson to a specific module."""
        lesson_data = data.model_dump()
        doc = await self.content_repo.add_lesson_to_module(
            course_id, module_id, lesson_data
        )
        if doc:
            doc.pop("_id", None)
            await cache_delete(f"course:content:{course_id}")
        return doc

    async def update_module(
        self, course_id: int, module_id: str, data: ModuleUpdate
    ) -> dict[str, Any] | None:
        """Update a module in the course content."""
        update_data = data.model_dump(exclude_unset=True)
        doc = await self.content_repo.update_module(course_id, module_id, update_data)
        if doc:
            doc.pop("_id", None)
            await cache_delete(f"course:content:{course_id}")
        return doc

    async def update_lesson(
        self, course_id: int, module_id: str, lesson_id: str, data: LessonUpdate
    ) -> dict[str, Any] | None:
        """Update a lesson in a module."""
        update_data = data.model_dump(exclude_unset=True)
        doc = await self.content_repo.update_lesson(
            course_id, module_id, lesson_id, update_data
        )
        if doc:
            doc.pop("_id", None)
            await cache_delete(f"course:content:{course_id}")
        return doc

    async def delete_module(
        self, course_id: int, module_id: str
    ) -> dict[str, Any] | None:
        """Soft-delete a module (set is_active=false)."""
        doc = await self.content_repo.soft_delete_module(course_id, module_id)
        if doc:
            doc.pop("_id", None)
            await cache_delete(f"course:content:{course_id}")
        return doc

    async def delete_lesson(
        self, course_id: int, module_id: str, lesson_id: str
    ) -> dict[str, Any] | None:
        """Soft-delete a lesson (set is_active=false)."""
        doc = await self.content_repo.soft_delete_lesson(
            course_id, module_id, lesson_id
        )
        if doc:
            doc.pop("_id", None)
            await cache_delete(f"course:content:{course_id}")
        return doc

    async def add_resource(
        self, course_id: int, module_id: str, lesson_id: str, data: MediaResourceCreate
    ) -> dict[str, Any] | None:
        """Add a resource to a lesson."""
        resource_data = data.model_dump()
        doc = await self.content_repo.add_resource_to_lesson(
            course_id, module_id, lesson_id, resource_data
        )
        if doc:
            doc.pop("_id", None)
            await cache_delete(f"course:content:{course_id}")
        return doc
```

#### 4.4 Update Course Content API Endpoints

**File:** `services/course-service/src/api/course_content.py`

Change path parameters from `int` to `str`:

```python
from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies import get_current_user, get_mongo_db
from schemas.course_content import (
    CourseContentCreate,
    CourseContentResponse,
    LessonCreate,
    LessonUpdate,
    MediaResourceCreate,
    ModuleCreate,
    ModuleUpdate,
)
from services.course_content import CourseContentService

router = APIRouter(prefix="/courses/{course_id}/content", tags=["Course Content"])


@router.get("", response_model=CourseContentResponse)
async def get_course_content(
    course_id: int,
    mongo_db=Depends(get_mongo_db),
):
    """Get full course content."""
    service = CourseContentService(mongo_db)
    content = await service.get_content(course_id)
    if not content:
        raise HTTPException(status_code=404, detail="Course content not found")
    return content


@router.put("", response_model=CourseContentResponse)
async def create_or_update_content(
    course_id: int,
    data: CourseContentCreate,
    current_user: dict = Depends(get_current_user),
    mongo_db=Depends(get_mongo_db),
):
    """Create or replace full course content."""
    service = CourseContentService(mongo_db)
    return await service.create_or_update_content(course_id, data)


@router.post("/modules", response_model=CourseContentResponse)
async def add_module(
    course_id: int,
    data: ModuleCreate,
    current_user: dict = Depends(get_current_user),
    mongo_db=Depends(get_mongo_db),
):
    """Add a module to the course."""
    service = CourseContentService(mongo_db)
    result = await service.add_module(course_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Course content not found")
    return result


@router.patch("/modules/{module_id}", response_model=CourseContentResponse)
async def update_module(
    course_id: int,
    module_id: str,
    data: ModuleUpdate,
    current_user: dict = Depends(get_current_user),
    mongo_db=Depends(get_mongo_db),
):
    """Update a module."""
    service = CourseContentService(mongo_db)
    result = await service.update_module(course_id, module_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Module not found")
    return result


@router.delete("/modules/{module_id}", response_model=CourseContentResponse)
async def delete_module(
    course_id: int,
    module_id: str,
    current_user: dict = Depends(get_current_user),
    mongo_db=Depends(get_mongo_db),
):
    """Soft-delete a module (set is_active=false)."""
    service = CourseContentService(mongo_db)
    result = await service.delete_module(course_id, module_id)
    if not result:
        raise HTTPException(status_code=404, detail="Module not found")
    return result


@router.post("/modules/{module_id}/lessons", response_model=CourseContentResponse)
async def add_lesson(
    course_id: int,
    module_id: str,
    data: LessonCreate,
    current_user: dict = Depends(get_current_user),
    mongo_db=Depends(get_mongo_db),
):
    """Add a lesson to a module."""
    service = CourseContentService(mongo_db)
    result = await service.add_lesson(course_id, module_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Module not found")
    return result


@router.patch("/modules/{module_id}/lessons/{lesson_id}", response_model=CourseContentResponse)
async def update_lesson(
    course_id: int,
    module_id: str,
    lesson_id: str,
    data: LessonUpdate,
    current_user: dict = Depends(get_current_user),
    mongo_db=Depends(get_mongo_db),
):
    """Update a lesson."""
    service = CourseContentService(mongo_db)
    result = await service.update_lesson(course_id, module_id, lesson_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return result


@router.delete("/modules/{module_id}/lessons/{lesson_id}", response_model=CourseContentResponse)
async def delete_lesson(
    course_id: int,
    module_id: str,
    lesson_id: str,
    current_user: dict = Depends(get_current_user),
    mongo_db=Depends(get_mongo_db),
):
    """Soft-delete a lesson (set is_active=false)."""
    service = CourseContentService(mongo_db)
    result = await service.delete_lesson(course_id, module_id, lesson_id)
    if not result:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return result


@router.post("/modules/{module_id}/lessons/{lesson_id}/resources", response_model=CourseContentResponse)
async def add_resource(
    course_id: int,
    module_id: str,
    lesson_id: str,
    data: MediaResourceCreate,
    current_user: dict = Depends(get_current_user),
    mongo_db=Depends(get_mongo_db),
):
    """Add a resource to a lesson."""
    service = CourseContentService(mongo_db)
    result = await service.add_resource(course_id, module_id, lesson_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return result
```

#### 4.5 MongoDB Data Migration Script

Run this script to migrate existing integer IDs to ObjectId strings:

**File:** `services/course-service/scripts/migrate_to_objectid.py`

```python
"""
MongoDB Migration Script: Integer IDs → ObjectId Strings

Run this script ONCE to migrate existing course content from integer module_id/lesson_id
to ObjectId strings and add is_active fields.

Usage:
    cd services/course-service
    python scripts/migrate_to_objectid.py
"""

import asyncio
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = "mongodb://localhost:27017"
DATABASE_NAME = "smartcourse"
COLLECTION_NAME = "course_content"


async def migrate_content():
    """Migrate all course content documents."""
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DATABASE_NAME]
    collection = db[COLLECTION_NAME]

    cursor = collection.find({})
    migrated_count = 0

    async for doc in cursor:
        course_id = doc.get("course_id")
        modules = doc.get("modules", [])
        updated_modules = []

        for module in modules:
            old_module_id = module.get("module_id")
            if isinstance(old_module_id, int):
                module["module_id"] = str(ObjectId())
            elif old_module_id is None:
                module["module_id"] = str(ObjectId())

            if "is_active" not in module:
                module["is_active"] = True

            lessons = module.get("lessons", [])
            updated_lessons = []
            for lesson in lessons:
                old_lesson_id = lesson.get("lesson_id")
                if isinstance(old_lesson_id, int):
                    lesson["lesson_id"] = str(ObjectId())
                elif old_lesson_id is None:
                    lesson["lesson_id"] = str(ObjectId())

                if "is_active" not in lesson:
                    lesson["is_active"] = True

                resources = lesson.get("resources", [])
                for resource in resources:
                    if "resource_id" not in resource:
                        resource["resource_id"] = str(ObjectId())
                    if "is_active" not in resource:
                        resource["is_active"] = True

                updated_lessons.append(lesson)

            module["lessons"] = updated_lessons
            updated_modules.append(module)

        await collection.update_one(
            {"_id": doc["_id"]},
            {"$set": {"modules": updated_modules}}
        )
        migrated_count += 1
        print(f"Migrated course_id={course_id}")

    print(f"\nMigration complete. {migrated_count} documents updated.")
    client.close()


if __name__ == "__main__":
    asyncio.run(migrate_content())
```

---

### PHASE 2: PostgreSQL Progress Table

#### 4.6 Database Migration (PostgreSQL)

Create a new Alembic migration:

**File:** `services/course-service/src/alembic/versions/xxxx_add_progress_table.py`

```python
"""add_progress_table_refactor_enrollment

Revision ID: <auto-generate>
Revises: 8ada7fdc14d3
Create Date: 2026-02-13
"""
from alembic import op
import sqlalchemy as sa

revision = '<auto-generate>'
down_revision = '8ada7fdc14d3'


def upgrade() -> None:
    op.create_table(
        'progress',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('course_id', sa.Integer(), nullable=False),
        sa.Column('item_type', sa.String(length=20), nullable=False),
        sa.Column('item_id', sa.String(length=50), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_progress_id', 'progress', ['id'], unique=False)
    op.create_index('ix_progress_user_id', 'progress', ['user_id'], unique=False)
    op.create_index('ix_progress_course_id', 'progress', ['course_id'], unique=False)
    op.create_index(
        'uq_progress_user_item',
        'progress',
        ['user_id', 'item_type', 'item_id'],
        unique=True
    )
    op.create_index(
        'ix_progress_user_course',
        'progress',
        ['user_id', 'course_id'],
        unique=False
    )

    op.drop_column('enrollments', 'completed_modules')
    op.drop_column('enrollments', 'completed_lessons')
    op.drop_column('enrollments', 'total_modules')
    op.drop_column('enrollments', 'total_lessons')
    op.drop_column('enrollments', 'completion_percentage')
    op.drop_column('enrollments', 'completed_quizzes')
    op.drop_column('enrollments', 'quiz_scores')
    op.drop_column('enrollments', 'current_module_id')
    op.drop_column('enrollments', 'current_lesson_id')


def downgrade() -> None:
    op.add_column('enrollments', sa.Column('current_lesson_id', sa.Integer(), nullable=True))
    op.add_column('enrollments', sa.Column('current_module_id', sa.Integer(), nullable=True))
    op.add_column('enrollments', sa.Column('quiz_scores', sa.JSON(), nullable=True))
    op.add_column('enrollments', sa.Column('completed_quizzes', sa.ARRAY(sa.Integer()), nullable=False, server_default='{}'))
    op.add_column('enrollments', sa.Column('completion_percentage', sa.Numeric(5, 2), nullable=False, server_default='0'))
    op.add_column('enrollments', sa.Column('total_lessons', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('enrollments', sa.Column('total_modules', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('enrollments', sa.Column('completed_lessons', sa.ARRAY(sa.Integer()), nullable=False, server_default='{}'))
    op.add_column('enrollments', sa.Column('completed_modules', sa.ARRAY(sa.Integer()), nullable=False, server_default='{}'))

    op.drop_index('ix_progress_user_course', table_name='progress')
    op.drop_index('uq_progress_user_item', table_name='progress')
    op.drop_index('ix_progress_course_id', table_name='progress')
    op.drop_index('ix_progress_user_id', table_name='progress')
    op.drop_index('ix_progress_id', table_name='progress')
    op.drop_table('progress')
```

#### 4.7 New SQLAlchemy Model

Create `services/course-service/src/models/progress.py`:

```python
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, UniqueConstraint

from core.database import Base


class Progress(Base):
    """Progress model — tracks individual content item completions."""
    __tablename__ = "progress"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    course_id = Column(Integer, nullable=False, index=True)
    item_type = Column(String(20), nullable=False)
    item_id = Column(String(50), nullable=False)
    completed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "item_type", "item_id", name="uq_progress_user_item"),
        Index("ix_progress_user_course", "user_id", "course_id"),
    )

    def __repr__(self) -> str:
        return f"<Progress(user={self.user_id}, item={self.item_type}:{self.item_id})>"
```

#### 4.8 Update Enrollment Model

Modify `services/course-service/src/models/enrollment.py`:

```python
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, Numeric, String, UniqueConstraint

from core.database import Base


class Enrollment(Base):
    """Enrollment model — stored in PostgreSQL."""
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, nullable=False, index=True)
    course_id = Column(Integer, nullable=False, index=True)

    status = Column(String(50), nullable=False, default="active", index=True)
    enrolled_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    dropped_at = Column(DateTime, nullable=True)
    last_accessed_at = Column(DateTime, nullable=True)

    payment_status = Column(String(50), nullable=True)
    payment_amount = Column(Numeric(10, 2), nullable=True)
    enrollment_source = Column(String(100), nullable=True)

    time_spent_minutes = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="uq_enrollment_student_course"),
        Index("idx_enrollments_enrolled_at", "enrolled_at"),
        Index("idx_enrollments_last_accessed", "last_accessed_at"),
    )

    def __repr__(self) -> str:
        return f"<Enrollment(id={self.id}, student={self.student_id}, course={self.course_id})>"
```

#### 4.9 New Progress Repository

Create `services/course-service/src/repositories/progress.py`:

```python
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

    async def mark_completed(
        self,
        user_id: int,
        course_id: int,
        item_type: str,
        item_id: str
    ) -> Progress:
        """Mark an item as completed (upsert — idempotent)."""
        stmt = insert(Progress).values(
            user_id=user_id,
            course_id=course_id,
            item_type=item_type,
            item_id=item_id,
        ).on_conflict_do_nothing(
            index_elements=["user_id", "item_type", "item_id"]
        ).returning(Progress)

        result = await self.db.execute(stmt)
        await self.db.commit()

        row = result.first()
        if row:
            return row[0]

        return await self.get_by_user_and_item(user_id, item_type, item_id)

    async def get_by_user_and_item(
        self,
        user_id: int,
        item_type: str,
        item_id: str
    ) -> Optional[Progress]:
        """Get a specific progress record."""
        result = await self.db.execute(
            select(Progress).where(
                Progress.user_id == user_id,
                Progress.item_type == item_type,
                Progress.item_id == item_id,
            )
        )
        return result.scalars().first()

    async def get_user_course_progress(
        self,
        user_id: int,
        course_id: int
    ) -> List[Progress]:
        """Get all progress records for a user in a course."""
        result = await self.db.execute(
            select(Progress).where(
                Progress.user_id == user_id,
                Progress.course_id == course_id,
            )
        )
        return list(result.scalars().all())

    async def get_completed_item_ids(
        self,
        user_id: int,
        course_id: int,
        item_type: str
    ) -> List[str]:
        """Get list of completed item IDs for a specific type."""
        result = await self.db.execute(
            select(Progress.item_id).where(
                Progress.user_id == user_id,
                Progress.course_id == course_id,
                Progress.item_type == item_type,
            )
        )
        return [row[0] for row in result.fetchall()]

    async def count_completed(
        self,
        user_id: int,
        course_id: int,
        item_type: Optional[str] = None
    ) -> int:
        """Count completed items for a user in a course."""
        query = select(func.count()).select_from(Progress).where(
            Progress.user_id == user_id,
            Progress.course_id == course_id,
        )
        if item_type:
            query = query.where(Progress.item_type == item_type)

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def delete_progress(
        self,
        user_id: int,
        course_id: int
    ) -> int:
        """Delete all progress for a user in a course."""
        result = await self.db.execute(
            Progress.__table__.delete().where(
                Progress.user_id == user_id,
                Progress.course_id == course_id,
            )
        )
        await self.db.commit()
        return result.rowcount
```

#### 4.10 New Progress Schema

Create `services/course-service/src/schemas/progress.py`:

```python
from datetime import datetime
from decimal import Decimal
from typing import List

from pydantic import BaseModel, ConfigDict, Field


class ProgressCreate(BaseModel):
    """Schema for marking an item as completed."""
    course_id: int
    item_type: str = Field(..., pattern=r"^(lesson|quiz|summary)$")
    item_id: str


class ProgressResponse(BaseModel):
    """Schema for a single progress record."""
    id: int
    user_id: int
    course_id: int
    item_type: str
    item_id: str
    completed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CourseProgressSummary(BaseModel):
    """Schema for computed course progress."""
    course_id: int
    user_id: int
    total_items: int
    completed_items: int
    completion_percentage: Decimal
    completed_lessons: List[str]
    completed_quizzes: List[str]
    completed_summaries: List[str]
    has_certificate: bool
    is_complete: bool


class ProgressUpdate(BaseModel):
    """Schema for marking a lesson/quiz/summary as completed."""
    item_type: str = Field(..., pattern=r"^(lesson|quiz|summary)$")
    item_id: str
```

#### 4.11 New Progress Service

Create `services/course-service/src/services/progress.py`:

```python
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List

from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from models.progress import Progress
from repositories.certificate import CertificateRepository
from repositories.course_content import CourseContentRepository
from repositories.enrollment import EnrollmentRepository
from repositories.progress import ProgressRepository
from schemas.progress import CourseProgressSummary, ProgressCreate


class ProgressService:
    """Business logic for progress tracking."""

    def __init__(self, pg_db: AsyncSession, mongo_db: AsyncIOMotorDatabase):
        self.progress_repo = ProgressRepository(pg_db)
        self.enrollment_repo = EnrollmentRepository(pg_db)
        self.cert_repo = CertificateRepository(pg_db)
        self.content_repo = CourseContentRepository(mongo_db)
        self.pg_db = pg_db

    async def mark_completed(
        self,
        user_id: int,
        data: ProgressCreate
    ) -> Progress:
        """Mark an item as completed."""
        enrollment = await self.enrollment_repo.get_by_student_and_course(
            user_id, data.course_id
        )
        if not enrollment:
            raise ValueError("User is not enrolled in this course")
        if enrollment.status not in ("active", "completed"):
            raise ValueError("Enrollment is not active")

        progress = await self.progress_repo.mark_completed(
            user_id=user_id,
            course_id=data.course_id,
            item_type=data.item_type,
            item_id=data.item_id,
        )

        update_data = {"last_accessed_at": datetime.utcnow()}
        if enrollment.started_at is None:
            update_data["started_at"] = datetime.utcnow()
        await self.enrollment_repo.update(enrollment.id, update_data)

        await self._check_auto_complete(user_id, data.course_id, enrollment.id)

        return progress

    async def get_course_progress(
        self,
        user_id: int,
        course_id: int
    ) -> CourseProgressSummary:
        """Get computed progress for a user in a course."""
        active_items = await self._get_active_items(course_id)
        total_items = len(active_items)

        completed = await self.progress_repo.get_user_course_progress(
            user_id, course_id
        )
        completed_ids = {(p.item_type, p.item_id) for p in completed}

        completed_active = [
            item for item in active_items
            if (item["type"], item["id"]) in completed_ids
        ]
        completed_count = len(completed_active)

        percentage = Decimal("0.00")
        if total_items > 0:
            percentage = Decimal(str(round((completed_count / total_items) * 100, 2)))

        enrollment = await self.enrollment_repo.get_by_student_and_course(
            user_id, course_id
        )
        has_certificate = False
        if enrollment:
            cert = await self.cert_repo.get_by_enrollment(enrollment.id)
            has_certificate = cert is not None and not cert.is_revoked

        completed_lessons = [p.item_id for p in completed if p.item_type == "lesson"]
        completed_quizzes = [p.item_id for p in completed if p.item_type == "quiz"]
        completed_summaries = [p.item_id for p in completed if p.item_type == "summary"]

        return CourseProgressSummary(
            course_id=course_id,
            user_id=user_id,
            total_items=total_items,
            completed_items=completed_count,
            completion_percentage=percentage,
            completed_lessons=completed_lessons,
            completed_quizzes=completed_quizzes,
            completed_summaries=completed_summaries,
            has_certificate=has_certificate,
            is_complete=percentage >= 100,
        )

    async def _get_active_items(self, course_id: int) -> List[Dict[str, Any]]:
        """Get all active content items for a course."""
        content = await self.content_repo.get_by_course_id(course_id)
        if not content:
            return []

        items = []
        for module in content.get("modules", []):
            if not module.get("is_active", True):
                continue

            for lesson in module.get("lessons", []):
                if not lesson.get("is_active", True):
                    continue

                items.append({
                    "type": "lesson",
                    "id": str(lesson.get("lesson_id")),
                })

            for quiz in module.get("quizzes", []):
                if not quiz.get("is_active", True):
                    continue
                items.append({
                    "type": "quiz",
                    "id": str(quiz.get("quiz_id")),
                })

            for summary in module.get("summaries", []):
                if not summary.get("is_active", True):
                    continue
                items.append({
                    "type": "summary",
                    "id": str(summary.get("summary_id")),
                })

        return items

    async def _check_auto_complete(
        self,
        user_id: int,
        course_id: int,
        enrollment_id: int
    ) -> None:
        """Check if course should be marked as completed."""
        progress = await self.get_course_progress(user_id, course_id)

        if progress.completion_percentage >= 100 and not progress.has_certificate:
            await self.enrollment_repo.update(enrollment_id, {
                "status": "completed",
                "completed_at": datetime.utcnow(),
            })
```

#### 4.12 New Progress API Endpoints

Create `services/course-service/src/api/progress.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user, get_mongo_db, get_pg_db
from schemas.progress import CourseProgressSummary, ProgressCreate, ProgressResponse
from services.progress import ProgressService

router = APIRouter(prefix="/progress", tags=["Progress"])


@router.post("", response_model=ProgressResponse, status_code=status.HTTP_201_CREATED)
async def mark_item_completed(
    data: ProgressCreate,
    current_user: dict = Depends(get_current_user),
    pg_db: AsyncSession = Depends(get_pg_db),
    mongo_db = Depends(get_mongo_db),
):
    """Mark a lesson/quiz/summary as completed."""
    service = ProgressService(pg_db, mongo_db)
    try:
        progress = await service.mark_completed(current_user["id"], data)
        return progress
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/course/{course_id}", response_model=CourseProgressSummary)
async def get_course_progress(
    course_id: int,
    current_user: dict = Depends(get_current_user),
    pg_db: AsyncSession = Depends(get_pg_db),
    mongo_db = Depends(get_mongo_db),
):
    """Get computed progress for current user in a course."""
    service = ProgressService(pg_db, mongo_db)
    return await service.get_course_progress(current_user["id"], course_id)
```

#### 4.13 Update Enrollment Service

Remove progress-related methods from `services/course-service/src/services/enrollment.py`:

- **Remove:** `update_progress` method entirely.
- **Keep:** `enroll_student`, `get_enrollment`, `drop_enrollment`, etc.

#### 4.14 Update Enrollment Schemas

Simplify `services/course-service/src/schemas/enrollment.py`:

```python
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class EnrollmentCreate(BaseModel):
    """Schema for enrolling a student in a course."""
    course_id: int
    payment_amount: Optional[Decimal] = None
    enrollment_source: Optional[str] = Field(None, max_length=100)


class EnrollmentUpdate(BaseModel):
    """Schema for updating enrollment."""
    status: Optional[str] = Field(None, pattern=r"^(active|completed|dropped|suspended)$")


class EnrollmentResponse(BaseModel):
    """Schema for enrollment API responses."""
    id: int
    student_id: int
    course_id: int
    status: str
    enrolled_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    dropped_at: Optional[datetime]
    last_accessed_at: Optional[datetime]
    payment_status: Optional[str]
    payment_amount: Optional[Decimal]
    enrollment_source: Optional[str]
    time_spent_minutes: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EnrollmentListResponse(BaseModel):
    """Paginated list of enrollments."""
    items: list[EnrollmentResponse]
    total: int
    skip: int
    limit: int
```

#### 4.15 Update Router

Add progress router to `services/course-service/src/api/router.py`:

```python
from fastapi import APIRouter

from api.certificates import router as certificates_router
from api.course_content import router as course_content_router
from api.courses import router as courses_router
from api.enrollments import router as enrollments_router
from api.progress import router as progress_router

api_router = APIRouter()
api_router.include_router(courses_router)
api_router.include_router(course_content_router)
api_router.include_router(enrollments_router)
api_router.include_router(certificates_router)
api_router.include_router(progress_router)
```

---

## 5. Execution Order

Run the migrations in this order:

1. **Run MongoDB migration script first** (converts integer IDs to ObjectId strings, adds `is_active`):

   ```bash
   cd services/course-service
   python scripts/migrate_to_objectid.py
   ```

2. **Apply PostgreSQL migration** (creates `progress` table, removes columns from `enrollments`):

   ```bash
   cd services/course-service/src
   alembic upgrade head
   ```

3. **Update all Python files** as described above.

4. **Restart the service**.

---

## 6. Certificate Logic (No Changes)

Certificates remain unchanged:

- Issued when progress reaches 100% (auto or manual).
- Once issued, certificate is **final**.
- If instructor adds new content after certificate is issued:
  - Certificate remains valid.
  - UI can show "new content added" badge.
  - Progress percentage may drop below 100% (expected).

---

## 7. API Changes Summary

| Old Endpoint                                                    | New Endpoint                       | ID Type                  |
| --------------------------------------------------------------- | ---------------------------------- | ------------------------ |
| `PUT /enrollments/{id}/progress`                                | `POST /progress`                   | N/A                      |
| N/A                                                             | `GET /progress/course/{course_id}` | N/A                      |
| `/courses/{id}/content/modules/{module_id}`                     | Same                               | `module_id: int` → `str` |
| `/courses/{id}/content/modules/{module_id}/lessons/{lesson_id}` | Same                               | `lesson_id: int` → `str` |

---

## 8. Files to Modify

| File                             | Action                                                    |
| -------------------------------- | --------------------------------------------------------- |
| `schemas/course_content.py`      | Change `module_id`/`lesson_id` to `str`, add `is_active`  |
| `repositories/course_content.py` | Change ID parameters from `int` to `str`                  |
| `services/course_content.py`     | Change ID parameters from `int` to `str`, add soft delete |
| `api/course_content.py`          | Change path params from `int` to `str`                    |
| `models/enrollment.py`           | Remove progress columns                                   |
| `models/progress.py`             | **Create new file**                                       |
| `schemas/enrollment.py`          | Simplify response                                         |
| `schemas/progress.py`            | **Create new file**                                       |
| `repositories/progress.py`       | **Create new file**                                       |
| `services/enrollment.py`         | Remove `update_progress` method                           |
| `services/progress.py`           | **Create new file**                                       |
| `api/progress.py`                | **Create new file**                                       |
| `api/router.py`                  | Add progress router                                       |
| `alembic/versions/`              | **New migration**                                         |
| `scripts/migrate_to_objectid.py` | **Create migration script**                               |

---

## 9. Testing Checklist

### MongoDB ObjectId Migration

- [ ] New modules get ObjectId string IDs automatically
- [ ] New lessons get ObjectId string IDs automatically
- [ ] Existing data migrated (integer → ObjectId string)
- [ ] `is_active` field added to all modules/lessons

### Progress Tracking

- [ ] Mark lesson as completed (with ObjectId string)
- [ ] Mark quiz as completed
- [ ] Mark summary as completed
- [ ] Get progress for a course (shows correct %)
- [ ] Soft-delete a lesson (progress % recalculates)
- [ ] Add new lesson (progress % updates)
- [ ] Complete all items (enrollment auto-completes)
- [ ] Verify certificate not revoked after content change
- [ ] Duplicate completion request (idempotent)
- [ ] Progress for non-enrolled user (error)

---

## 10. Summary

| Before                                  | After                                                            |
| --------------------------------------- | ---------------------------------------------------------------- |
| `module_id` / `lesson_id` are integers  | ObjectId strings (auto-generated)                                |
| No soft delete support                  | `is_active` field for soft delete                                |
| Progress stored as arrays in enrollment | Progress stored as rows in dedicated table                       |
| Content changes require mass updates    | Content changes require zero updates                             |
| Completion % cached and synced          | Completion % computed at read time                               |
| Hard delete of content                  | Soft delete with `is_active = false`                             |
| Tightly coupled enrollment + progress   | Decoupled: enrollment tracks status, progress tracks completions |

This refactor eliminates the synchronization problem and scales to millions of enrollments without degradation.
