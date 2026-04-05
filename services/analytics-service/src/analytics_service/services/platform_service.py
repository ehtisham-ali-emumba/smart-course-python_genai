from datetime import date
from decimal import Decimal

from sqlalchemy import func, select

from analytics_service.models.course_metrics import CourseMetrics
from analytics_service.models.instructor_metrics import InstructorMetrics
from analytics_service.models.student_metrics import StudentMetrics
from analytics_service.repositories.ai_usage_repo import AIUsageDailyRepository
from analytics_service.repositories.enrollment_daily_repo import EnrollmentDailyRepository


class PlatformAnalyticsService:
    def __init__(self, session):
        self.session = session
        self.enrollment_daily_repo = EnrollmentDailyRepository(session)
        self.ai_usage_repo = AIUsageDailyRepository(session)

    async def overview(self) -> dict:
        total_students = await self.session.scalar(
            select(func.count()).select_from(StudentMetrics)
        ) or 0
        total_instructors = await self.session.scalar(
            select(func.count()).select_from(InstructorMetrics)
        ) or 0
        total_courses_published = await self.session.scalar(
            select(func.count())
            .select_from(CourseMetrics)
            .where(CourseMetrics.published_at.is_not(None))
        ) or 0
        total_enrollments = await self.session.scalar(
            select(func.coalesce(func.sum(CourseMetrics.total_enrollments), 0))
        ) or 0
        total_completions = await self.session.scalar(
            select(func.coalesce(func.sum(CourseMetrics.completed_enrollments), 0))
        ) or 0
        total_certificates_issued = await self.session.scalar(
            select(func.coalesce(func.sum(StudentMetrics.total_certificates), 0))
        ) or 0

        avg_completion_rate = Decimal("0.00")
        if total_enrollments > 0:
            avg_completion_rate = Decimal(total_completions * 100 / total_enrollments).quantize(
                Decimal("0.01")
            )

        avg_courses_per_student = Decimal("0.00")
        if total_students > 0:
            avg_courses_per_student = Decimal(total_courses_published / total_students).quantize(
                Decimal("0.01")
            )

        return {
            "total_students": total_students,
            "total_instructors": total_instructors,
            "total_courses_published": total_courses_published,
            "total_enrollments": total_enrollments,
            "total_completions": total_completions,
            "avg_completion_rate": avg_completion_rate,
            "avg_courses_per_student": avg_courses_per_student,
            "total_certificates_issued": total_certificates_issued,
        }

    async def trends(self, date_from: date, date_to: date) -> list[dict]:
        rows = await self.enrollment_daily_repo.list_between(date_from, date_to)
        return [
            {
                "date": row.date,
                "new_enrollments": row.new_enrollments,
                "new_completions": row.new_completions,
                "new_drops": row.new_drops,
            }
            for row in rows
        ]

    async def ai_usage(self, date_from: date, date_to: date) -> list[dict]:
        rows = await self.ai_usage_repo.list_between(date_from, date_to)
        return [
            {
                "date": row.date,
                "tutor_questions": row.tutor_questions,
                "instructor_requests": row.instructor_requests,
                "total": row.total_questions,
            }
            for row in rows
        ]
