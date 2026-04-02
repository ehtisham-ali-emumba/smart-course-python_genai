import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from analytics_service.api.dependencies import require_instructor_or_self
from analytics_service.core.cache import get_or_set_json
from analytics_service.core.database import get_db
from analytics_service.core.redis import get_redis
from analytics_service.services.instructor_analytics_service import InstructorAnalyticsService

router = APIRouter()


@router.get("/instructors/{instructor_id}")
async def instructor_details(
    request: Request,
    instructor_id: _uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    require_instructor_or_self(request, instructor_id)

    service = InstructorAnalyticsService(db)
    cache = get_redis()
    key = f"analytics:instructor:{instructor_id}"
    payload = await get_or_set_json(
        cache,
        key,
        ttl_seconds=120,
        loader=lambda: service.details(instructor_id),
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Instructor analytics not found")
    return payload


@router.get("/instructors/leaderboard")
async def instructor_leaderboard(
    request: Request,
    limit: int = 10,
    sort_by: str = "students",
    db: AsyncSession = Depends(get_db),
):
    role = request.headers.get("X-User-Role", "")
    if role != "instructor":
        raise HTTPException(status_code=403, detail="Instructor role required")

    service = InstructorAnalyticsService(db)
    return await service.leaderboard(limit=limit, sort_by=sort_by)
