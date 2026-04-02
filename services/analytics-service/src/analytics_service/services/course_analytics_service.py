import uuid as _uuid
from datetime import date

from analytics_service.repositories.course_metrics_repo import CourseMetricsRepository
from analytics_service.repositories.enrollment_daily_repo import EnrollmentDailyRepository


class CourseAnalyticsService:
    def __init__(self, session):
        self.course_repo = CourseMetricsRepository(session)
        self.daily_repo = EnrollmentDailyRepository(session)

    async def popular(self, limit: int, sort_by: str) -> list[dict]:
        courses = await self.course_repo.list_popular(limit=limit, sort_by=sort_by)
        return [
            {
                "course_id": row.course_id,
                "title": row.title,
                "total_enrollments": row.total_enrollments,
                "completion_rate": row.completion_rate,
                "avg_progress": row.avg_progress_percentage,
            }
            for row in courses
        ]

    async def details(self, course_id: _uuid.UUID) -> dict | None:
        row = await self.course_repo.get_by_course_id(course_id)
        if row is None:
            return None

        trends = await self.trends(course_id, date(1970, 1, 1), date.today())
        return {
            "course_id": row.course_id,
            "title": row.title,
            "total_enrollments": row.total_enrollments,
            "active_enrollments": row.active_enrollments,
            "completed_enrollments": row.completed_enrollments,
            "dropped_enrollments": row.dropped_enrollments,
            "completion_rate": row.completion_rate,
            "avg_progress_percentage": row.avg_progress_percentage,
            "avg_time_to_complete_hours": row.avg_time_to_complete_hours,
            "avg_quiz_score": row.avg_quiz_score,
            "total_quiz_attempts": row.total_quiz_attempts,
            "ai_questions_asked": row.ai_questions_asked,
            "enrollment_trend": trends,
        }

    async def trends(self, course_id: _uuid.UUID, date_from: date, date_to: date) -> list[dict]:
        rows = await self.daily_repo.list_between(date_from=date_from, date_to=date_to)
        course_rows = [row for row in rows if row.course_id == course_id]
        return [
            {
                "date": row.date,
                "new_enrollments": row.new_enrollments,
                "new_completions": row.new_completions,
            }
            for row in course_rows
        ]
