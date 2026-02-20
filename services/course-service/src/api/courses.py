from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_event_producer, require_instructor
from core.database import get_db
from core_service.events.course import (
    CourseArchivedPayload,
    CourseCreatedPayload,
    CourseDeletedPayload,
    CoursePublishedPayload,
    CourseUpdatedPayload,
)
from core_service.providers.kafka.producer import EventProducer
from core_service.providers.kafka.topics import Topics
from schemas.course import (
    CourseCreate,
    CourseListResponse,
    CourseResponse,
    CourseStatusUpdate,
    CourseUpdate,
)
from services.course import CourseService

router = APIRouter()


@router.post("/", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
async def create_course(
    data: CourseCreate,
    instructor_id: int = Depends(require_instructor),
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
                slug=course["slug"],
                category=course.get("category"),
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
    instructor_id: int = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """List courses created by the current instructor."""
    service = CourseService(db)
    items, total = await service.list_instructor_courses(
        instructor_id, skip=skip, limit=limit
    )
    return CourseListResponse(
        items=[CourseResponse(**c) for c in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{course_id}", response_model=CourseResponse)
async def get_course(
    course_id: int,
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
    course_id: int,
    data: CourseUpdate,
    instructor_id: int = Depends(require_instructor),
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


@router.patch("/{course_id}/status", response_model=CourseResponse)
async def update_course_status(
    course_id: int,
    data: CourseStatusUpdate,
    instructor_id: int = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
    producer: EventProducer = Depends(get_event_producer),
):
    """Change course status — publish, archive, etc. (owning instructor only)."""
    service = CourseService(db)
    try:
        course = await service.update_status(course_id, data, instructor_id)
        if not course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

        if data.status == "published":
            published_at = course.get("published_at") or datetime.utcnow()
            await producer.publish(
                Topics.COURSE,
                "course.published",
                CoursePublishedPayload(
                    course_id=course_id,
                    instructor_id=instructor_id,
                    title=course.get("title", ""),
                    published_at=str(published_at) if published_at else "",
                ).model_dump(),
                key=str(course_id),
            )
        elif data.status == "archived":
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

        return CourseResponse(**course)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_course(
    course_id: int,
    instructor_id: int = Depends(require_instructor),
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
