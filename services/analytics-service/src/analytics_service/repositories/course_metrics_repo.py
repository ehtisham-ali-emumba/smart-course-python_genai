import uuid as _uuid

from sqlalchemy import desc, select

from analytics_service.models.course_metrics import CourseMetrics
from analytics_service.repositories.base import BaseRepository


class CourseMetricsRepository(BaseRepository):
    async def get_by_course_id(self, course_id: _uuid.UUID) -> CourseMetrics | None:
        stmt = select(CourseMetrics).where(CourseMetrics.course_id == course_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(self, course_id: _uuid.UUID) -> CourseMetrics:
        metrics = await self.get_by_course_id(course_id)
        if metrics:
            return metrics
        metrics = CourseMetrics(course_id=course_id)
        self.session.add(metrics)
        await self.session.flush()
        return metrics

    async def list_popular(self, limit: int, sort_by: str) -> list[CourseMetrics]:
        if sort_by == "completion_rate":
            order_col = CourseMetrics.completion_rate
        else:
            order_col = CourseMetrics.total_enrollments

        stmt = select(CourseMetrics).order_by(desc(order_col)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
