from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from analytics_service.models.course_metrics import CourseMetrics
from analytics_service.models.instructor_metrics import InstructorMetrics
from analytics_service.models.student_metrics import StudentMetrics
from analytics_service.repositories.platform_repo import PlatformRepository


class SnapshotService:
    def __init__(self, session):
        self.session = session
        self.platform_repo = PlatformRepository(session)

    async def build_daily_snapshot(self, target_date: date) -> None:
        students = await self.session.scalar(select(func.count()).select_from(StudentMetrics))
        instructors = await self.session.scalar(select(func.count()).select_from(InstructorMetrics))

        courses = await self.session.scalar(
            select(func.count())
            .select_from(CourseMetrics)
            .where(CourseMetrics.published_at.is_not(None))
        )

        total_enrollments = await self.session.scalar(
            select(func.coalesce(func.sum(CourseMetrics.total_enrollments), 0))
        )
        total_completions = await self.session.scalar(
            select(func.coalesce(func.sum(CourseMetrics.completed_enrollments), 0))
        )

        avg_completion_rate = Decimal("0.00")
        if total_enrollments and total_enrollments > 0:
            avg_completion_rate = Decimal(
                (total_completions or 0) * 100 / total_enrollments
            ).quantize(Decimal("0.01"))

        avg_courses_per_student = Decimal("0.00")
        if students and students > 0:
            avg_courses_per_student = Decimal((courses or 0) / students).quantize(Decimal("0.01"))

        snapshot = await self.platform_repo.get_or_create_today(target_date)
        snapshot.total_students = students or 0
        snapshot.total_instructors = instructors or 0
        snapshot.total_courses_published = courses or 0
        snapshot.total_enrollments = total_enrollments or 0
        snapshot.total_completions = total_completions or 0
        snapshot.avg_completion_rate = avg_completion_rate
        snapshot.avg_courses_per_student = avg_courses_per_student

        await self.session.commit()
