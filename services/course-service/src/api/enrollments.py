from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_id
from core.database import get_db
from schemas.enrollment import (
    EnrollmentCreate,
    EnrollmentListResponse,
    EnrollmentResponse,
)
from services.enrollment import EnrollmentService

router = APIRouter()


@router.post("/", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED)
async def enroll(
    data: EnrollmentCreate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Enroll the current user in a course."""
    service = EnrollmentService(db)
    try:
        enrollment = await service.enroll_student(user_id, data)
        return EnrollmentResponse.model_validate(enrollment)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/my-enrollments", response_model=EnrollmentListResponse)
async def list_my_enrollments(
    skip: int = 0,
    limit: int = 20,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List all enrollments for the current user."""
    service = EnrollmentService(db)
    enrollments, total = await service.get_student_enrollments(user_id, skip=skip, limit=limit)
    return EnrollmentListResponse(
        items=[EnrollmentResponse.model_validate(e) for e in enrollments],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{enrollment_id}", response_model=EnrollmentResponse)
async def get_enrollment(
    enrollment_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get a single enrollment (must be the enrolled student)."""
    service = EnrollmentService(db)
    enrollment = await service.get_enrollment(enrollment_id)
    if not enrollment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")
    if enrollment.student_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your enrollment")
    return EnrollmentResponse.model_validate(enrollment)


@router.patch("/{enrollment_id}/drop", response_model=EnrollmentResponse)
async def drop_enrollment(
    enrollment_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Drop a course enrollment."""
    service = EnrollmentService(db)
    try:
        enrollment = await service.drop_enrollment(enrollment_id, user_id)
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found"
            )
        return EnrollmentResponse.model_validate(enrollment)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.patch("/{enrollment_id}/undrop", response_model=EnrollmentResponse)
async def undrop_enrollment(
    enrollment_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Re-enroll in a course after dropping."""
    service = EnrollmentService(db)
    try:
        enrollment = await service.undrop_enrollment(enrollment_id, user_id)
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found"
            )
        return EnrollmentResponse.model_validate(enrollment)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
