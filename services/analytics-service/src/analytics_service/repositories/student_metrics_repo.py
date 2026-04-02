import uuid as _uuid

from sqlalchemy import select

from analytics_service.models.student_metrics import StudentMetrics
from analytics_service.repositories.base import BaseRepository


class StudentMetricsRepository(BaseRepository):
    async def get_by_student_id(self, student_id: _uuid.UUID) -> StudentMetrics | None:
        stmt = select(StudentMetrics).where(StudentMetrics.student_id == student_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(self, student_id: _uuid.UUID) -> StudentMetrics:
        metrics = await self.get_by_student_id(student_id)
        if metrics:
            return metrics
        metrics = StudentMetrics(student_id=student_id)
        self.session.add(metrics)
        await self.session.flush()
        return metrics
