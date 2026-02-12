from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from models.enrollment import Enrollment
from repositories.course import CourseRepository
from repositories.enrollment import EnrollmentRepository
from schemas.enrollment import EnrollmentCreate, ProgressUpdate


class EnrollmentService:
    """Business logic for enrollment and progress operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.enrollment_repo = EnrollmentRepository(db)
        self.course_repo = CourseRepository(db)

    async def enroll_student(self, student_id: int, data: EnrollmentCreate) -> Enrollment:
        """Enroll a student in a course."""
        # Check course exists and is published
        course = await self.course_repo.get_by_id(data.course_id)
        if not course or course.is_deleted:
            raise ValueError("Course not found")
        if course.status != "published":
            raise ValueError("Course is not available for enrollment")

        # Check max_students limit
        if course.max_students:
            current_count = await self.enrollment_repo.count_by_course(data.course_id)
            if current_count >= course.max_students:
                raise ValueError("Course enrollment limit reached")

        # Check not already enrolled
        if await self.enrollment_repo.is_enrolled(student_id, data.course_id):
            raise ValueError("Already enrolled in this course")

        enrollment_data = {
            "student_id": student_id,
            "course_id": data.course_id,
            "status": "active",
            "payment_amount": data.payment_amount,
            "payment_status": "completed" if data.payment_amount else None,
            "enrollment_source": data.enrollment_source,
        }
        return await self.enrollment_repo.create(enrollment_data)

    async def get_enrollment(self, enrollment_id: int) -> Enrollment | None:
        """Get a single enrollment by ID."""
        return await self.enrollment_repo.get_by_id(enrollment_id)

    async def get_student_enrollments(
        self, student_id: int, skip: int = 0, limit: int = 100
    ):
        """List all enrollments for a student."""
        enrollments = await self.enrollment_repo.get_by_student(student_id, skip=skip, limit=limit)
        total = await self.enrollment_repo.count_by_student(student_id)
        return enrollments, total

    async def get_course_enrollments(
        self, course_id: int, skip: int = 0, limit: int = 100
    ):
        """List all enrollments for a course (instructor view)."""
        enrollments = await self.enrollment_repo.get_by_course(course_id, skip=skip, limit=limit)
        total = await self.enrollment_repo.count_by_course(course_id)
        return enrollments, total

    async def update_progress(
        self, enrollment_id: int, student_id: int, data: ProgressUpdate
    ) -> Enrollment | None:
        """Update student progress on a course."""
        enrollment = await self.enrollment_repo.get_by_id(enrollment_id)
        if not enrollment:
            return None
        if enrollment.student_id != student_id:
            raise PermissionError("This is not your enrollment")

        update_data: dict = {"last_accessed_at": datetime.utcnow()}

        # Mark lesson as completed
        if data.lesson_id is not None:
            completed = list(enrollment.completed_lessons or [])
            if data.lesson_id not in completed:
                completed.append(data.lesson_id)
                update_data["completed_lessons"] = completed

            # Recalculate completion percentage
            total = enrollment.total_lessons
            if total > 0:
                update_data["completion_percentage"] = round(
                    (len(completed) / total) * 100, 2
                )

        # Mark module as completed
        if data.module_id is not None:
            completed_mods = list(enrollment.completed_modules or [])
            if data.module_id not in completed_mods:
                completed_mods.append(data.module_id)
                update_data["completed_modules"] = completed_mods

        # Add time spent
        if data.time_spent_minutes is not None:
            update_data["time_spent_minutes"] = (
                enrollment.time_spent_minutes + data.time_spent_minutes
            )

        # Set started_at on first progress update
        if enrollment.started_at is None:
            update_data["started_at"] = datetime.utcnow()

        # Auto-complete if 100%
        pct = update_data.get("completion_percentage", float(enrollment.completion_percentage))
        if pct >= 100 and enrollment.status == "active":
            update_data["status"] = "completed"
            update_data["completed_at"] = datetime.utcnow()

        return await self.enrollment_repo.update(enrollment_id, update_data)

    async def drop_enrollment(self, enrollment_id: int, student_id: int) -> Enrollment | None:
        """Student drops a course."""
        enrollment = await self.enrollment_repo.get_by_id(enrollment_id)
        if not enrollment:
            return None
        if enrollment.student_id != student_id:
            raise PermissionError("This is not your enrollment")

        return await self.enrollment_repo.update(enrollment_id, {
            "status": "dropped",
            "dropped_at": datetime.utcnow(),
        })
