import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from analytics_service.api.dependencies import require_student_or_instructor
from analytics_service.core.cache import get_or_set_json
from analytics_service.core.database import get_db
from analytics_service.core.redis import get_redis
from analytics_service.services.student_analytics_service import StudentAnalyticsService

router = APIRouter()


@router.get("/students/{student_id}")
async def student_details(
    request: Request,
    student_id: _uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    require_student_or_instructor(request, student_id)

    service = StudentAnalyticsService(db)
    cache = get_redis()
    key = f"analytics:student:{student_id}"
    payload = await get_or_set_json(
        cache, key, ttl_seconds=120, loader=lambda: service.details(student_id)
    )
    if payload is None:
        raise HTTPException(status_code=404, detail="Student analytics not found")
    return payload


@router.get("/students/{student_id}/courses")
async def student_courses(
    request: Request,
    student_id: _uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    # Placeholder for detailed per-course student analytics.
    require_student_or_instructor(request, student_id)
    service = StudentAnalyticsService(db)
    details = await service.details(student_id)
    if details is None:
        raise HTTPException(status_code=404, detail="Student analytics not found")
    return []
