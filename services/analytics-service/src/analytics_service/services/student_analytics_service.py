import uuid as _uuid

from analytics_service.repositories.student_metrics_repo import StudentMetricsRepository


class StudentAnalyticsService:
    def __init__(self, session):
        self.student_repo = StudentMetricsRepository(session)

    async def details(self, student_id: _uuid.UUID) -> dict | None:
        row = await self.student_repo.get_by_student_id(student_id)
        if row is None:
            return None

        return {
            "student_id": row.student_id,
            "total_enrollments": row.total_enrollments,
            "active_enrollments": row.active_enrollments,
            "completed_courses": row.completed_courses,
            "dropped_courses": row.dropped_courses,
            "avg_progress": row.avg_progress,
            "avg_quiz_score": row.avg_quiz_score,
            "total_certificates": row.total_certificates,
            "last_active_at": row.last_active_at,
        }
