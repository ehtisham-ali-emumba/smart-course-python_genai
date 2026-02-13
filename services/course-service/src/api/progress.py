from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_id
from core.database import get_db
from core.mongodb import get_mongodb
from schemas.progress import CourseProgressSummary, ProgressCreate, ProgressResponse
from services.progress import ProgressService

router = APIRouter()


@router.post("", response_model=ProgressResponse, status_code=status.HTTP_201_CREATED)
async def mark_item_completed(
    data: ProgressCreate,
    user_id: int = Depends(get_current_user_id),
    pg_db: AsyncSession = Depends(get_db),
):
    """Mark a lesson/quiz/summary as completed."""
    mongo_db = get_mongodb()
    service = ProgressService(pg_db, mongo_db)
    try:
        progress = await service.mark_completed(user_id, data)
        return ProgressResponse.model_validate(progress)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{course_id}", response_model=CourseProgressSummary)
async def get_course_progress(
    course_id: int,
    user_id: int = Depends(get_current_user_id),
    pg_db: AsyncSession = Depends(get_db),
):
    """Get computed progress for current user in a course. Requires enrollment."""
    mongo_db = get_mongodb()
    service = ProgressService(pg_db, mongo_db)
    try:
        return await service.get_course_progress(user_id, course_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
