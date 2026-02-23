from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_id, get_event_producer
from core.database import get_db
from core.mongodb import get_mongodb
from shared.kafka.producer import EventProducer
from schemas.progress import CourseProgressSummary, ProgressCreate, ProgressResponse
from services.progress import ProgressService

router = APIRouter()


@router.post("", response_model=ProgressResponse, status_code=status.HTTP_201_CREATED)
async def update_progress(
    data: ProgressCreate,
    user_id: int = Depends(get_current_user_id),
    pg_db: AsyncSession = Depends(get_db),
    producer: EventProducer = Depends(get_event_producer),
):
    """
    Create or update progress on a lesson/quiz/summary.

    Body:
      - enrollment_id: int
      - item_type: "lesson" | "quiz" | "summary"
      - item_id: str (MongoDB lesson/quiz/summary ID)
      - progress_percentage: 0–100

    When progress_percentage reaches 100, the item is marked as completed
    (completed_at is set). If ALL items in the course reach 100%, the
    enrollment is auto-completed and a certificate is auto-issued.
    """
    mongo_db = get_mongodb()
    service = ProgressService(pg_db, mongo_db, event_producer=producer)
    try:
        progress = await service.update_progress(user_id, data)
        return ProgressResponse.model_validate(progress)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/enrollment/{enrollment_id}", response_model=CourseProgressSummary)
async def get_progress_by_enrollment(
    enrollment_id: int,
    user_id: int = Depends(get_current_user_id),
    pg_db: AsyncSession = Depends(get_db),
):
    """
    Get full course progress by enrollment ID (primary endpoint).
    Returns course-level, module-level, and per-lesson progress.
    """
    mongo_db = get_mongodb()
    service = ProgressService(pg_db, mongo_db)  # no producer needed for read
    try:
        return await service.get_enrollment_progress(user_id, enrollment_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/course/{course_id}", response_model=CourseProgressSummary)
async def get_progress_by_course(
    course_id: int,
    user_id: int = Depends(get_current_user_id),
    pg_db: AsyncSession = Depends(get_db),
):
    """
    Get full course progress by course ID (convenience endpoint).
    Internally looks up the enrollment for the current user.
    """
    mongo_db = get_mongodb()
    service = ProgressService(pg_db, mongo_db)  # no producer needed for read
    try:
        return await service.get_course_progress(user_id, course_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
