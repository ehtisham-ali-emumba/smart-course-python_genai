import uuid as _uuid
from datetime import date

from sqlalchemy import select

from analytics_service.models.ai_usage import AIUsageDaily
from analytics_service.repositories.base import BaseRepository


class AIUsageDailyRepository(BaseRepository):
    async def get_or_create(self, day: date, course_id: _uuid.UUID | None = None) -> AIUsageDaily:
        stmt = (
            select(AIUsageDaily)
            .where(AIUsageDaily.date == day)
            .where(AIUsageDaily.course_id == course_id)
        )
        result = await self.session.execute(stmt)
        item = result.scalar_one_or_none()
        if item:
            return item
        item = AIUsageDaily(date=day, course_id=course_id)
        self.session.add(item)
        await self.session.flush()
        return item

    async def list_between(self, date_from: date, date_to: date) -> list[AIUsageDaily]:
        stmt = (
            select(AIUsageDaily)
            .where(AIUsageDaily.date >= date_from)
            .where(AIUsageDaily.date <= date_to)
            .where(AIUsageDaily.course_id.is_(None))
            .order_by(AIUsageDaily.date)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
