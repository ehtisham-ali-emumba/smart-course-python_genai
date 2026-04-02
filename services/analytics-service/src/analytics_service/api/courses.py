import uuid as _uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from analytics_service.core.cache import get_or_set_json
from analytics_service.core.database import get_db
from analytics_service.core.redis import get_redis
from analytics_service.services.course_analytics_service import CourseAnalyticsService

router = APIRouter()


@router.get("/courses/popular")
async def popular_courses(
    request: Request,
    limit: int = 10,
    sort_by: str = "enrollments",
    db: AsyncSession = Depends(get_db),
):
    role = request.headers.get("X-User-Role", "")
    if role != "instructor":
        raise HTTPException(status_code=403, detail="Instructor role required")

    service = CourseAnalyticsService(db)
    cache = get_redis()
    key = f"analytics:courses:popular:{sort_by}:{limit}"
    return await get_or_set_json(
        cache,
        key,
        ttl_seconds=300,
        loader=lambda: service.popular(limit=limit, sort_by=sort_by),
    )


@router.get("/courses/{course_id}")
async def course_details(
    request: Request,
    course_id: _uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    role = request.headers.get("X-User-Role", "")
    if role != "instructor":
        raise HTTPException(status_code=403, detail="Instructor role required")

    service = CourseAnalyticsService(db)
    cache = get_redis()
    key = f"analytics:course:{course_id}"
    payload = await get_or_set_json(
        cache, key, ttl_seconds=120, loader=lambda: service.details(course_id)
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Course analytics not found")
    return payload


@router.get("/courses/{course_id}/trends")
async def course_trends(
    request: Request,
    course_id: _uuid.UUID,
    period: str = "daily",
    from_date: date | None = None,
    to_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    del period
    role = request.headers.get("X-User-Role", "")
    if role != "instructor":
        raise HTTPException(status_code=403, detail="Instructor role required")

    date_to = to_date or date.today()
    date_from = from_date or (date_to - timedelta(days=30))
    service = CourseAnalyticsService(db)
    return await service.trends(course_id=course_id, date_from=date_from, date_to=date_to)
