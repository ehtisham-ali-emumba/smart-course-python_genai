from datetime import date

from analytics_service.repositories.ai_usage_repo import AIUsageDailyRepository
from analytics_service.repositories.enrollment_daily_repo import EnrollmentDailyRepository
from analytics_service.repositories.platform_repo import PlatformRepository


class PlatformAnalyticsService:
    def __init__(self, session):
        self.platform_repo = PlatformRepository(session)
        self.enrollment_daily_repo = EnrollmentDailyRepository(session)
        self.ai_usage_repo = AIUsageDailyRepository(session)

    async def overview(self) -> dict:
        snapshot = await self.platform_repo.get_latest_snapshot()
        if not snapshot:
            return {
                "total_students": 0,
                "total_instructors": 0,
                "total_courses_published": 0,
                "total_enrollments": 0,
                "total_completions": 0,
                "avg_completion_rate": 0,
                "avg_courses_per_student": 0,
                "total_certificates_issued": 0,
            }

        return {
            "total_students": snapshot.total_students,
            "total_instructors": snapshot.total_instructors,
            "total_courses_published": snapshot.total_courses_published,
            "total_enrollments": snapshot.total_enrollments,
            "total_completions": snapshot.total_completions,
            "avg_completion_rate": snapshot.avg_completion_rate,
            "avg_courses_per_student": snapshot.avg_courses_per_student,
            "total_certificates_issued": snapshot.total_certificates_issued,
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
