from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List

from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

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
        data: ProgressCreate,
    ):
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
        course_id: int,
    ) -> CourseProgressSummary:
        """Get computed progress for a user in a course. Requires enrollment."""
        enrollment = await self.enrollment_repo.get_by_student_and_course(
            user_id, course_id
        )
        if not enrollment:
            raise ValueError("User is not enrolled in this course")
        if enrollment.status not in ("active", "completed"):
            raise ValueError("Enrollment is not active (dropped or suspended)")

        active_items = await self._get_active_items(course_id)
        total_items = len(active_items)

        completed = await self.progress_repo.get_user_course_progress(
            user_id, course_id
        )
        completed_ids = {(p.item_type, p.item_id) for p in completed}

        completed_active = [
            item
            for item in active_items
            if (item["type"], item["id"]) in completed_ids
        ]
        completed_count = len(completed_active)

        percentage = Decimal("0.00")
        if total_items > 0:
            percentage = Decimal(str(round((completed_count / total_items) * 100, 2)))

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
        enrollment_id: int,
    ) -> None:
        """Check if course should be marked as completed."""
        progress = await self.get_course_progress(user_id, course_id)

        if progress.completion_percentage >= 100 and not progress.has_certificate:
            await self.enrollment_repo.update(
                enrollment_id,
                {
                    "status": "completed",
                    "completed_at": datetime.utcnow(),
                },
            )
