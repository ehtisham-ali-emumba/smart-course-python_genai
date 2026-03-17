from datetime import datetime
import logging
import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, status

logger = logging.getLogger(__name__)
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client as TemporalClient

from api.dependencies import (
    get_current_user_id,
    get_event_producer,
    get_temporal_client,
    require_instructor,
)
from core.database import get_db
from shared.schemas.events.course import (
    CourseArchivedPayload,
    CourseCreatedPayload,
    CourseDeletedPayload,
    CoursePublishedPayload,
    CoursePublishRequestedPayload,
    CourseUpdatedPayload,
)
from shared.kafka.producer import EventProducer
from shared.kafka.topics import Topics
from schemas.course import (
    CourseCreate,
    CourseListResponse,
    CourseResponse,
    CourseStatusUpdate,
    CourseUpdate,
)
from services.course import CourseService
from temporal.course_publish import start_course_publish_workflow

router = APIRouter()


@router.post("/", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
async def create_course(
    data: CourseCreate,
    instructor_id: _uuid.UUID = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
    producer: EventProducer = Depends(get_event_producer),
):
    """Create a new course (instructors only)."""
    service = CourseService(db)
    try:
        course = await service.create_course(data, instructor_id)

        await producer.publish(
            Topics.COURSE,
            "course.created",
            CourseCreatedPayload(
                course_id=course["id"],
                instructor_id=instructor_id,
                title=course["title"],
            ).model_dump(),
            key=str(course["id"]),
        )

        return CourseResponse(**course)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/", response_model=CourseListResponse)
async def list_published_courses(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List all published courses (any authenticated user)."""
    service = CourseService(db)
    items, total = await service.list_published_courses(skip=skip, limit=limit)
    return CourseListResponse(
        items=[CourseResponse(**c) for c in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/my-courses", response_model=CourseListResponse)
async def list_my_courses(
    skip: int = 0,
    limit: int = 20,
    instructor_id: _uuid.UUID = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """List courses created by the current instructor."""
    service = CourseService(db)
    items, total = await service.list_instructor_courses(instructor_id, skip=skip, limit=limit)
    return CourseListResponse(
        items=[CourseResponse(**c) for c in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/my-courses/{course_id}", response_model=CourseResponse)
async def get_my_course(
    course_id: _uuid.UUID,
    instructor_id: _uuid.UUID = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """Validate instructor ownership of a single course.

    Returns 200 + course data only if the course exists and belongs to the
    requesting instructor.  Returns 404 otherwise.
    Primarily used by internal services (e.g. AI service) to confirm
    instructor ownership before dispatching generation tasks.
    """
    service = CourseService(db)
    course = await service.get_instructor_course(course_id, instructor_id)
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found or you do not own it",
        )
    return CourseResponse(**course)


@router.get("/{course_id}", response_model=CourseResponse)
async def get_course(
    course_id: _uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single course by ID."""
    service = CourseService(db)
    course = await service.get_course(course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return CourseResponse(**course)


@router.put("/{course_id}", response_model=CourseResponse)
async def update_course(
    course_id: _uuid.UUID,
    data: CourseUpdate,
    instructor_id: _uuid.UUID = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
    producer: EventProducer = Depends(get_event_producer),
):
    """Update a course (owning instructor only)."""
    service = CourseService(db)
    try:
        course = await service.update_course(course_id, data, instructor_id)
        if not course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

        fields_changed = list(data.model_dump(exclude_unset=True).keys())
        if fields_changed:
            await producer.publish(
                Topics.COURSE,
                "course.updated",
                CourseUpdatedPayload(
                    course_id=course_id,
                    instructor_id=instructor_id,
                    fields_changed=fields_changed,
                ).model_dump(),
                key=str(course_id),
            )

        return CourseResponse(**course)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.patch("/{course_id}/status", status_code=status.HTTP_202_ACCEPTED)
async def update_course_status(
    course_id: _uuid.UUID,
    data: CourseStatusUpdate,
    instructor_id: _uuid.UUID = Depends(require_instructor),
    user_id: _uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    producer: EventProducer = Depends(get_event_producer),
    temporal_client: TemporalClient = Depends(get_temporal_client),
):
    """Change course status — publish, archive, etc. (owning instructor only).

    For publish requests: returns 202 Accepted and triggers Temporal workflow.
    For other statuses: returns 200 OK with updated course.
    """
    service = CourseService(db)

    if data.status == "published":
        # Start course publish workflow on Temporal
        try:
            course = await service.validate_course_for_publish(course_id, instructor_id)
            # course is a dict; raises ValueError/PermissionError if invalid

            # Set status to publish_requested in DB before starting workflow
            await service.update_status(
                course_id,
                CourseStatusUpdate(status="publish_requested"),
                instructor_id,
            )

            await start_course_publish_workflow(
                temporal_client,
                course_id=course_id,
                instructor_id=instructor_id,
                user_id=user_id,
                course_title=course["title"],
            )

            return {
                "message": "Course publish workflow started",
                "course_id": course_id,
                "status": "publish_requested",
            }
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        except PermissionError as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

    # --- existing behavior for archive/draft and other statuses ---
    try:
        course = await service.update_status(course_id, data, instructor_id)
        if not course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

        if data.status == "archived":
            await producer.publish(
                Topics.COURSE,
                "course.archived",
                CourseArchivedPayload(
                    course_id=course_id,
                    instructor_id=instructor_id,
                    title=course.get("title", ""),
                ).model_dump(),
                key=str(course_id),
            )
        logger.info("Course %s status updated to %s", course_id, data.status)
        return CourseResponse(**course)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.patch("/{course_id}/internal/publish", response_model=CourseResponse)
async def internal_publish_course(
    course_id: _uuid.UUID,
    db: AsyncSession = Depends(get_db),
    producer: EventProducer = Depends(get_event_producer),
):
    """Internal endpoint — called by core-service Temporal workflow after
    RAG indexing completes. Marks course as published in DB and fires
    the course.published event.

    Guarded by X-User-ID / X-User-Role headers (internal services only).
    """
    service = CourseService(db)
    course = await service.get_course(course_id)
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    result = await service.force_publish(course_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to publish course"
        )

    # Now fire the actual course.published event
    await producer.publish(
        Topics.COURSE,
        "course.published",
        CoursePublishedPayload(
            course_id=course_id,
            instructor_id=result["instructor_id"],
            title=result.get("title", ""),
            published_at=str(result.get("published_at", "")),
        ).model_dump(),
        key=str(course_id),
    )

    return CourseResponse(**result)


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_course(
    course_id: _uuid.UUID,
    instructor_id: _uuid.UUID = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
    producer: EventProducer = Depends(get_event_producer),
):
    """Soft-delete a course (owning instructor only)."""
    service = CourseService(db)
    try:
        deleted = await service.delete_course(course_id, instructor_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

        await producer.publish(
            Topics.COURSE,
            "course.deleted",
            CourseDeletedPayload(
                course_id=course_id,
                instructor_id=instructor_id,
            ).model_dump(),
            key=str(course_id),
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
