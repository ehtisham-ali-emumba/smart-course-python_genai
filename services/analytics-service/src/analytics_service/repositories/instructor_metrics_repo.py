import uuid as _uuid

from sqlalchemy import desc, select

from analytics_service.models.instructor_metrics import InstructorMetrics
from analytics_service.repositories.base import BaseRepository


class InstructorMetricsRepository(BaseRepository):
    async def get_by_instructor_id(self, instructor_id: _uuid.UUID) -> InstructorMetrics | None:
        stmt = select(InstructorMetrics).where(InstructorMetrics.instructor_id == instructor_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(self, instructor_id: _uuid.UUID) -> InstructorMetrics:
        metrics = await self.get_by_instructor_id(instructor_id)
        if metrics:
            return metrics
        metrics = InstructorMetrics(instructor_id=instructor_id)
        self.session.add(metrics)
        await self.session.flush()
        return metrics

    async def leaderboard(self, limit: int, sort_by: str) -> list[InstructorMetrics]:
        order_col = (
            InstructorMetrics.avg_completion_rate
            if sort_by == "completion_rate"
            else InstructorMetrics.total_students
        )
        stmt = select(InstructorMetrics).order_by(desc(order_col)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
