from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from analytics_service.models.processed_event import ProcessedEvent
from analytics_service.repositories.base import BaseRepository


class ProcessedEventRepository(BaseRepository):
    async def mark_processed(self, event_id: str, topic: str, event_type: str) -> bool:
        marker = ProcessedEvent(event_id=event_id, topic=topic, event_type=event_type)
        self.session.add(marker)
        try:
            await self.session.flush()
            return True
        except IntegrityError:
            await self.session.rollback()
            return False

    async def exists(self, event_id: str) -> bool:
        stmt = select(ProcessedEvent.event_id).where(ProcessedEvent.event_id == event_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None
