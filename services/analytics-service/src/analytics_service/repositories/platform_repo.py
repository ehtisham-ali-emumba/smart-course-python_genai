from datetime import date

from sqlalchemy import desc, func, select

from analytics_service.models.platform_snapshot import PlatformSnapshot
from analytics_service.repositories.base import BaseRepository


class PlatformRepository(BaseRepository):
    async def get_latest_snapshot(self) -> PlatformSnapshot | None:
        stmt = select(PlatformSnapshot).order_by(desc(PlatformSnapshot.snapshot_date)).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create_today(self, target_date: date) -> PlatformSnapshot:
        stmt = select(PlatformSnapshot).where(PlatformSnapshot.snapshot_date == target_date)
        result = await self.session.execute(stmt)
        snapshot = result.scalar_one_or_none()
        if snapshot:
            return snapshot

        snapshot = PlatformSnapshot(snapshot_date=target_date)
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    async def list_by_date_range(self, date_from: date, date_to: date) -> list[PlatformSnapshot]:
        stmt = (
            select(PlatformSnapshot)
            .where(PlatformSnapshot.snapshot_date >= date_from)
            .where(PlatformSnapshot.snapshot_date <= date_to)
            .order_by(PlatformSnapshot.snapshot_date)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
