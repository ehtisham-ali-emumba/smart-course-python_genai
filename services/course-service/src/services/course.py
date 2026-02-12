from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from models.course import Course
from repositories.course import CourseRepository
from schemas.course import CourseCreate, CourseStatusUpdate, CourseUpdate


class CourseService:
    """Business logic for course operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.course_repo = CourseRepository(db)

    async def create_course(self, data: CourseCreate, instructor_id: int) -> Course:
        """Create a new course. instructor_id comes from X-User-ID header."""
        if await self.course_repo.slug_exists(data.slug):
            raise ValueError(f"Slug '{data.slug}' is already taken")

        course_data = data.model_dump(mode="python")  # Ensures Decimal/float preserved
        course_data["instructor_id"] = instructor_id
        course_data["status"] = "draft"

        # Explicitly convert numeric fields to Decimal for SQLAlchemy Numeric columns
        # (handles edge cases with JSON float → DB Numeric)
        if data.duration_hours is not None:
            course_data["duration_hours"] = Decimal(str(data.duration_hours))
        course_data["price"] = Decimal(str(data.price))

        return await self.course_repo.create(course_data)

    async def get_course(self, course_id: int) -> Course | None:
        """Get a single course by ID (excludes soft-deleted)."""
        course = await self.course_repo.get_by_id(course_id)
        if course and course.is_deleted:
            return None
        return course

    async def get_course_by_slug(self, slug: str) -> Course | None:
        """Get a course by its URL slug."""
        return await self.course_repo.get_by_slug(slug)

    async def list_published_courses(self, skip: int = 0, limit: int = 100):
        """List published courses for browsing."""
        courses = await self.course_repo.get_published(skip=skip, limit=limit)
        total = await self.course_repo.count_published()
        return courses, total

    async def list_instructor_courses(
        self, instructor_id: int, skip: int = 0, limit: int = 100
    ):
        """List all courses by an instructor."""
        courses = await self.course_repo.get_by_instructor(instructor_id, skip=skip, limit=limit)
        total = await self.course_repo.count_by_instructor(instructor_id)
        return courses, total

    async def update_course(
        self, course_id: int, data: CourseUpdate, instructor_id: int
    ) -> Course | None:
        """Update course details. Only the owning instructor can update."""
        course = await self.get_course(course_id)
        if not course:
            return None
        if course.instructor_id != instructor_id:
            raise PermissionError("You do not own this course")

        update_data = data.model_dump(exclude_unset=True, mode="python")
        # Explicitly convert numeric fields for SQLAlchemy
        if "duration_hours" in update_data and update_data["duration_hours"] is not None:
            update_data["duration_hours"] = Decimal(str(update_data["duration_hours"]))
        if "price" in update_data and update_data["price"] is not None:
            update_data["price"] = Decimal(str(update_data["price"]))
        return await self.course_repo.update(course_id, update_data)

    async def update_status(
        self, course_id: int, data: CourseStatusUpdate, instructor_id: int
    ) -> Course | None:
        """Change course status (draft → published → archived)."""
        course = await self.get_course(course_id)
        if not course:
            return None
        if course.instructor_id != instructor_id:
            raise PermissionError("You do not own this course")

        update_data = {"status": data.status}
        if data.status == "published" and course.status != "published":
            update_data["published_at"] = datetime.utcnow()

        return await self.course_repo.update(course_id, update_data)

    async def delete_course(self, course_id: int, instructor_id: int) -> bool:
        """Soft-delete a course. Only the owning instructor can delete."""
        course = await self.get_course(course_id)
        if not course:
            return False
        if course.instructor_id != instructor_id:
            raise PermissionError("You do not own this course")

        await self.course_repo.soft_delete(course_id)
        return True
