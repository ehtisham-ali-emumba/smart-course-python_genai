from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import require_instructor
from core.database import get_db
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
):
    """Create a new course (instructors only)."""
    service = CourseService(db)
    try:
        course = await service.create_course(data, instructor_id)
        return CourseResponse.model_validate(course)
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
    courses, total = await service.list_published_courses(skip=skip, limit=limit)

    # Handle both SQLAlchemy objects (cache miss) and dicts (cache hit)
    if courses and isinstance(courses[0], dict):
        items = [CourseResponse(**c) for c in courses]
    else:
        items = [CourseResponse.model_validate(c) for c in courses]

    return CourseListResponse(
        items=items,
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
    courses, total = await service.list_instructor_courses(instructor_id, skip=skip, limit=limit)
    return CourseListResponse(
        items=[CourseResponse.model_validate(c) for c in courses],
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

    # Handle both SQLAlchemy object (cache miss) and dict (cache hit)
    if isinstance(course, dict):
        return CourseResponse(**course)
    return CourseResponse.model_validate(course)


@router.put("/{course_id}", response_model=CourseResponse)
async def update_course(
    course_id: int,
    data: CourseUpdate,
    instructor_id: int = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """Update a course (owning instructor only)."""
    service = CourseService(db)
    try:
        course = await service.update_course(course_id, data, instructor_id)
        if not course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
        return CourseResponse.model_validate(course)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.patch("/{course_id}/status", response_model=CourseResponse)
async def update_course_status(
    course_id: int,
    data: CourseStatusUpdate,
    instructor_id: int = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """Change course status — publish, archive, etc. (owning instructor only)."""
    service = CourseService(db)
    try:
        course = await service.update_status(course_id, data, instructor_id)
        if not course:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
        return CourseResponse.model_validate(course)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_course(
    course_id: int,
    instructor_id: int = Depends(require_instructor),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a course (owning instructor only)."""
    service = CourseService(db)
    try:
        deleted = await service.delete_course(course_id, instructor_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
