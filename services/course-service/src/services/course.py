from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from core.cache import cache_delete, cache_delete_pattern, cache_get, cache_set
from models.course import Course
from repositories.course import CourseRepository
from schemas.course import CourseCreate, CourseResponse, CourseStatusUpdate, CourseUpdate


# ── TTL Constants ─────────────────────────────────────────────────
COURSE_DETAIL_TTL = 600  # 10 minutes
COURSE_LIST_TTL = 300  # 5 minutes


def _course_to_dict(course: Course) -> dict:
    """Convert Course ORM to dict for consistent API/response use."""
    return CourseResponse.model_validate(course).model_dump(mode="json")


class CourseService:
    """Business logic for course operations.

    All read methods return dicts (not ORM objects) so the API layer
    can always use CourseResponse(**data) with no isinstance branching.
    Cache logic is fully contained in the service layer.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.course_repo = CourseRepository(db)

    # ── READS (with cache) ────────────────────────────────────────

    async def get_course(self, course_id: int) -> dict | None:
        """Get a single course by ID (excludes soft-deleted).
        Always returns dict or None — never ORM. Cache handled internally.
        """
        # 1. Try cache
        cache_key = f"course:detail:{course_id}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        # 2. Fallback to DB
        course = await self.course_repo.get_by_id(course_id)
        if course and course.is_deleted:
            return None

        # 3. Store in cache and return normalized dict
        if course:
            course_dict = _course_to_dict(course)
            await cache_set(cache_key, course_dict, ttl=COURSE_DETAIL_TTL)
            return course_dict

        return None

    async def get_course_by_slug(self, slug: str) -> Course | None:
        """Get a course by its URL slug. No cache — slug lookups are rare.
        Returns ORM for internal use (e.g. by other services).
        """
        return await self.course_repo.get_by_slug(slug)

    async def list_published_courses(
        self, skip: int = 0, limit: int = 100
    ) -> tuple[list[dict], int]:
        """List published courses for browsing.
        Always returns (list[dict], total). Cache handled internally.
        """
        # 1. Try cache
        cache_key = f"course:published:p:{skip}:l:{limit}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached["items"], cached["total"]

        # 2. Fallback to DB
        courses = await self.course_repo.get_published(skip=skip, limit=limit)
        total = await self.course_repo.count_published()

        # 3. Normalize to dicts, store in cache, return
        items = [_course_to_dict(c) for c in courses]
        await cache_set(cache_key, {"items": items, "total": total}, ttl=COURSE_LIST_TTL)

        return items, total

    async def list_instructor_courses(
        self, instructor_id: int, skip: int = 0, limit: int = 100
    ) -> tuple[list[dict], int]:
        """List all courses by an instructor. No cache — instructor-specific, low reuse.
        Returns (list[dict], total) for consistent API handling.
        """
        courses = await self.course_repo.get_by_instructor(
            instructor_id, skip=skip, limit=limit
        )
        total = await self.course_repo.count_by_instructor(instructor_id)
        return [_course_to_dict(c) for c in courses], total

    # ── WRITES (with cache invalidation) ──────────────────────────

    async def create_course(self, data: CourseCreate, instructor_id: int) -> dict:
        """Create a new course. instructor_id comes from X-User-ID header.
        Returns dict for consistent API handling.
        """
        if await self.course_repo.slug_exists(data.slug):
            raise ValueError(f"Slug '{data.slug}' is already taken")

        course_data = data.model_dump(mode="python")
        course_data["instructor_id"] = instructor_id
        course_data["status"] = "draft"

        if data.duration_hours is not None:
            course_data["duration_hours"] = Decimal(str(data.duration_hours))
        course_data["price"] = Decimal(str(data.price))

        course = await self.course_repo.create(course_data)
        return _course_to_dict(course)

    async def update_course(
        self, course_id: int, data: CourseUpdate, instructor_id: int
    ) -> dict | None:
        """Update course details. Invalidates detail and list caches.
        Returns dict or None for consistent API handling.
        """
        course = await self.course_repo.get_by_id(course_id)
        if not course or course.is_deleted:
            return None
        if course.instructor_id != instructor_id:
            raise PermissionError("You do not own this course")

        update_data = data.model_dump(exclude_unset=True, mode="python")
        if "duration_hours" in update_data and update_data["duration_hours"] is not None:
            update_data["duration_hours"] = Decimal(str(update_data["duration_hours"]))
        if "price" in update_data and update_data["price"] is not None:
            update_data["price"] = Decimal(str(update_data["price"]))

        result = await self.course_repo.update(course_id, update_data)

        # Invalidate caches
        await cache_delete(f"course:detail:{course_id}")
        await cache_delete_pattern("course:published:*")

        return _course_to_dict(result) if result else None

    async def update_status(
        self, course_id: int, data: CourseStatusUpdate, instructor_id: int
    ) -> dict | None:
        """Change course status (draft → published → archived).
        Returns dict or None for consistent API handling.
        """
        course = await self.course_repo.get_by_id(course_id)
        if not course or course.is_deleted:
            return None
        if course.instructor_id != instructor_id:
            raise PermissionError("You do not own this course")

        update_data = {"status": data.status}
        if data.status == "published" and course.status != "published":
            update_data["published_at"] = datetime.utcnow()

        result = await self.course_repo.update(course_id, update_data)

        # Invalidate caches — status change affects listings
        await cache_delete(f"course:detail:{course_id}")
        await cache_delete_pattern("course:published:*")

        return _course_to_dict(result) if result else None

    async def delete_course(self, course_id: int, instructor_id: int) -> bool:
        """Soft-delete a course. Invalidates all course caches."""
        course = await self.course_repo.get_by_id(course_id)
        if not course or course.is_deleted:
            return False
        if course.instructor_id != instructor_id:
            raise PermissionError("You do not own this course")

        await self.course_repo.soft_delete(course_id)

        # Invalidate caches
        await cache_delete(f"course:detail:{course_id}")
        await cache_delete_pattern("course:published:*")

        return True
