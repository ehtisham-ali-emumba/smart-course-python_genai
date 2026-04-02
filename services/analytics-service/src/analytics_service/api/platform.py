from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from analytics_service.api.dependencies import require_instructor
from analytics_service.core.cache import get_or_set_json
from analytics_service.core.database import get_db
from analytics_service.core.redis import get_redis
from analytics_service.services.platform_service import PlatformAnalyticsService

router = APIRouter()


@router.get("/platform/overview", dependencies=[Depends(require_instructor)])
async def platform_overview(db: AsyncSession = Depends(get_db)):
    service = PlatformAnalyticsService(db)
    cache = get_redis()
    return await get_or_set_json(
        cache,
        "analytics:platform:overview",
        ttl_seconds=300,
        loader=service.overview,
    )


@router.get("/platform/trends", dependencies=[Depends(require_instructor)])
async def platform_trends(
    period: str = "daily",
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    del period
    date_to = to_date or date.today()
    date_from = from_date or (date_to - timedelta(days=30))

    service = PlatformAnalyticsService(db)
    return await service.trends(date_from=date_from, date_to=date_to)


@router.get("/platform/ai-usage", dependencies=[Depends(require_instructor)])
async def platform_ai_usage(
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    date_to = to_date or date.today()
    date_from = from_date or (date_to - timedelta(days=30))

    service = PlatformAnalyticsService(db)
    return await service.ai_usage(date_from=date_from, date_to=date_to)
