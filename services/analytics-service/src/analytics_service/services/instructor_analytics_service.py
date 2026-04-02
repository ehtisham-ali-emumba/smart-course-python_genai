import uuid as _uuid

from analytics_service.repositories.course_metrics_repo import CourseMetricsRepository
from analytics_service.repositories.instructor_metrics_repo import InstructorMetricsRepository


class InstructorAnalyticsService:
    def __init__(self, session):
        self.instructor_repo = InstructorMetricsRepository(session)
        self.course_repo = CourseMetricsRepository(session)

    async def details(self, instructor_id: _uuid.UUID) -> dict | None:
        row = await self.instructor_repo.get_by_instructor_id(instructor_id)
        if row is None:
            return None

        courses = await self.course_repo.list_popular(limit=1000, sort_by="enrollments")
        own_courses = [c for c in courses if c.instructor_id == instructor_id]
        return {
            "instructor_id": row.instructor_id,
            "total_courses": row.total_courses,
            "published_courses": row.published_courses,
            "total_students": row.total_students,
            "total_enrollments": row.total_enrollments,
            "total_completions": row.total_completions,
            "avg_completion_rate": row.avg_completion_rate,
            "avg_quiz_score": row.avg_quiz_score,
            "courses": [
                {
                    "course_id": c.course_id,
                    "title": c.title,
                    "enrollments": c.total_enrollments,
                    "completion_rate": c.completion_rate,
                }
                for c in own_courses
            ],
        }

    async def leaderboard(self, limit: int, sort_by: str) -> list[dict]:
        rows = await self.instructor_repo.leaderboard(limit=limit, sort_by=sort_by)
        return [
            {
                "instructor_id": row.instructor_id,
                "total_students": row.total_students,
                "avg_completion_rate": row.avg_completion_rate,
            }
            for row in rows
        ]
