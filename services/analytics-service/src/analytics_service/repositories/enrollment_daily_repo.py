import uuid as _uuid
from datetime import date

from sqlalchemy import select

from analytics_service.models.enrollment_daily import EnrollmentDaily
from analytics_service.repositories.base import BaseRepository


class EnrollmentDailyRepository(BaseRepository):
    async def get_or_create(
        self, day: date, course_id: _uuid.UUID | None = None
    ) -> EnrollmentDaily:
        stmt = (
            select(EnrollmentDaily)
            .where(EnrollmentDaily.date == day)
            .where(EnrollmentDaily.course_id == course_id)
        )
        result = await self.session.execute(stmt)
        entry = result.scalar_one_or_none()
        if entry:
            return entry
        entry = EnrollmentDaily(date=day, course_id=course_id)
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def list_between(self, date_from: date, date_to: date) -> list[EnrollmentDaily]:
        stmt = (
            select(EnrollmentDaily)
            .where(EnrollmentDaily.date >= date_from)
            .where(EnrollmentDaily.date <= date_to)
            .where(EnrollmentDaily.course_id.is_(None))
            .order_by(EnrollmentDaily.date)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
