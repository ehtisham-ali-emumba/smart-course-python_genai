import uuid as _uuid
import logging

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client as TemporalClient

from api.dependencies import (
    get_authenticated_user,
    get_event_producer,
    get_temporal_client,
    require_instructor,
    get_current_profile_id,
)
from core.database import get_db
from core.enrollment_cache import EnrollmentWorkflowCache
from shared.kafka.producer import EventProducer
from shared.kafka.topics import Topics
from shared.schemas.events.enrollment import (
    EnrollmentDroppedPayload,
    EnrollmentReactivatedPayload,
)
from schemas.enrollment import (
    EnrollmentCreate,
    EnrollmentListResponse,
    EnrollmentResponse,
)
from services.enrollment import EnrollmentService
from temporal.enrollment import start_enrollment_workflow

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED)
async def enroll(
    data: EnrollmentCreate,
    request: Request,
    user: tuple[_uuid.UUID, str, _uuid.UUID] = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
    temporal_client: TemporalClient = Depends(get_temporal_client),
):
    """
    Enroll the current user in a course.

    - If already enrolled → returns existing enrollment (200 OK)
    - If enrollment in progress → return 202 "Enrollment already in progress"
    - If not enrolled and not in progress → starts enrollment workflow on Temporal (202 Accepted)
      The workflow will create the enrollment and send notifications.
    """
    user_id, role, profile_id = user
    if role == "instructor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Instructors cannot enroll in courses. Use a student account to enroll.",
        )

    service = EnrollmentService(db)

    # Step 1: Check if already enrolled
    existing = await service.enrollment_repo.get_by_student_and_course(profile_id, data.course_id)
    if existing:
        # Already enrolled - return existing with message
        enrollment_data = EnrollmentResponse.model_validate(existing)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "Enrollment already created",
                "enrollment": enrollment_data.model_dump(mode="json"),
                "status": "completed",
            },
        )

    # Step 2: Validate course exists and is available (before lock)
    course = await service.course_repo.get_by_id(data.course_id)
    if not course or course.is_deleted:  # type: ignore[truthy-bool]
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    if course.status != "published":  # type: ignore[truthy-bool]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Course is not available for enrollment",
        )

    # Step 3: Atomically acquire enrollment lock
    lock_acquired = await EnrollmentWorkflowCache.acquire_lock(profile_id, data.course_id)
    if not lock_acquired:
        logger.info(
            "Enrollment duplicate request detected",
            extra={"student_id": str(profile_id), "course_id": str(data.course_id)},
        )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "message": "Enrollment already in progress",
                "student_id": str(profile_id),
                "course_id": str(data.course_id),
                "status": "processing",
            },
        )

    # Step 4: Start enrollment workflow on Temporal
    student_email = request.headers.get("X-User-Email") or ""
    await start_enrollment_workflow(
        temporal_client,
        user_id=user_id,
        student_id=profile_id,
        course_id=data.course_id,
        course_title=course.title,  # type: ignore[arg-type]
        student_email=student_email,
        payment_amount=data.payment_amount or Decimal(0),
        enrollment_source=data.enrollment_source or "web",
    )

    # Step 5: Return 202 "Enrollment request received"
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "message": "Enrollment request received",
            "student_id": str(profile_id),
            "course_id": str(data.course_id),
            "status": "processing",
        },
    )


@router.get("/my-enrollments", response_model=EnrollmentListResponse)
async def list_my_enrollments(
    skip: int = 0,
    limit: int = 20,
    user_id: _uuid.UUID = Depends(get_current_profile_id),
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
    enrollment_id: _uuid.UUID,
    user_id: _uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
):
    """Get a single enrollment (must be the enrolled student)."""
    service = EnrollmentService(db)
    enrollment = await service.get_enrollment(enrollment_id)
    if not enrollment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")
    if enrollment.student_id != user_id:  # type: ignore[truthy-bool]
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your enrollment")

    # Check if enrollment is in progress
    if await EnrollmentWorkflowCache.is_in_progress(user_id, enrollment.course_id):
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "message": "Enrollment in progress",
                "student_id": str(user_id),
                "course_id": str(enrollment.course_id),
                "status": "processing",
            },
        )

    return EnrollmentResponse.model_validate(enrollment)


@router.patch("/{enrollment_id}/drop", response_model=EnrollmentResponse)
async def drop_enrollment(
    enrollment_id: _uuid.UUID,
    user_id: _uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
    producer: EventProducer = Depends(get_event_producer),
):
    """Drop a course enrollment."""
    service = EnrollmentService(db)
    try:
        enrollment = await service.drop_enrollment(enrollment_id, user_id)
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found"
            )

        await producer.publish(
            Topics.ENROLLMENT,
            "enrollment.dropped",
            EnrollmentDroppedPayload(
                enrollment_id=enrollment.id,
                student_id=enrollment.student_id,
                course_id=enrollment.course_id,
            ).model_dump(),
            key=str(enrollment.student_id),
        )

        return EnrollmentResponse.model_validate(enrollment)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.patch("/{enrollment_id}/undrop", response_model=EnrollmentResponse)
async def undrop_enrollment(
    enrollment_id: _uuid.UUID,
    user_id: _uuid.UUID = Depends(get_current_profile_id),
    db: AsyncSession = Depends(get_db),
    producer: EventProducer = Depends(get_event_producer),
):
    """Re-enroll in a course after dropping."""
    service = EnrollmentService(db)
    try:
        enrollment = await service.undrop_enrollment(enrollment_id, user_id)
        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found"
            )

        await producer.publish(
            Topics.ENROLLMENT,
            "enrollment.reactivated",
            EnrollmentReactivatedPayload(
                enrollment_id=enrollment.id,
                student_id=enrollment.student_id,
                course_id=enrollment.course_id,
            ).model_dump(),
            key=str(enrollment.student_id),
        )

        return EnrollmentResponse.model_validate(enrollment)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/course/{course_id}/active-students")
async def list_active_students_for_course(
    course_id: _uuid.UUID,
    instructor_id: _uuid.UUID = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """
    Internal endpoint: return active student_ids enrolled in a course.
    Used by core-service CoursePublishWorkflow to notify enrolled students.
    """
    service = EnrollmentService(db)
    # EnrollmentRepository.get_by_course() already exists
    enrollments = await service.enrollment_repo.get_by_course(course_id)
    active_ids = [e.student_id for e in enrollments if e.status == "active"]  # type: ignore[truthy-bool]
    return {
        "course_id": str(course_id),
        "student_ids": [str(sid) for sid in active_ids],
        "count": len(active_ids),
    }


@router.post(
    "/internal/create", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED
)
async def internal_create_enrollment(
    data: EnrollmentCreate,
    user: tuple[_uuid.UUID, str, _uuid.UUID] = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Internal endpoint: Create enrollment directly without publishing Kafka events.
    Used by core-service EnrollmentWorkflow to actually create the enrollment.

    This endpoint is idempotent - if enrollment already exists, returns it.
    """
    _, role, profile_id = user
    if role == "instructor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Instructors cannot enroll in courses.",
        )

    service = EnrollmentService(db)

    # Check if already enrolled - return existing (idempotent)
    existing = await service.enrollment_repo.get_by_student_and_course(profile_id, data.course_id)
    if existing:
        return EnrollmentResponse.model_validate(existing)

    # Create enrollment
    try:
        enrollment = await service.enroll_student(profile_id, data)

        # Release lock after successful enrollment creation
        await EnrollmentWorkflowCache.release_lock(profile_id, data.course_id)

        return EnrollmentResponse.model_validate(enrollment)
    except ValueError as e:
        # Release lock on failure too, so client isn't stuck seeing "in progress"
        await EnrollmentWorkflowCache.release_lock(profile_id, data.course_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
