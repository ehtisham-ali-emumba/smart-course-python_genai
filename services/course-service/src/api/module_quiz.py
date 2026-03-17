import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_authenticated_user, require_instructor
from core.database import get_db
from core.mongodb import get_mongodb
from schemas.quiz_summary import (
    QuizCreate,
    QuizUpdate,
    QuizPatch,
    QuizPublishUpdate,
    QuizGenerateRequest,
    QuizResponse,
)
from services.module_quiz import ModuleQuizService

router = APIRouter()


@router.get("/{course_id}/modules/{module_id}/quiz", response_model=QuizResponse)
async def get_module_quiz(
    course_id: _uuid.UUID,
    module_id: str,
    authenticated_user: tuple[_uuid.UUID, str, _uuid.UUID] = Depends(get_authenticated_user),
    pg_db: AsyncSession = Depends(get_db),
):
    _, role, profile_id = authenticated_user
    service = ModuleQuizService(pg_db, get_mongodb())
    quiz = await service.get_quiz_for_viewer(course_id, module_id, profile_id, role)
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    return QuizResponse(**quiz)


@router.post(
    "/{course_id}/modules/{module_id}/quiz",
    response_model=QuizResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_module_quiz(
    course_id: _uuid.UUID,
    module_id: str,
    payload: QuizCreate,
    instructor_id: _uuid.UUID = Depends(require_instructor),
    pg_db: AsyncSession = Depends(get_db),
):
    service = ModuleQuizService(pg_db, get_mongodb())
    try:
        quiz = await service.create_quiz(course_id, module_id, payload, instructor_id)
        return QuizResponse(**quiz)
    except FileExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/{course_id}/modules/{module_id}/quiz", response_model=QuizResponse)
async def replace_module_quiz(
    course_id: _uuid.UUID,
    module_id: str,
    payload: QuizUpdate,
    instructor_id: _uuid.UUID = Depends(require_instructor),
    pg_db: AsyncSession = Depends(get_db),
):
    service = ModuleQuizService(pg_db, get_mongodb())
    try:
        quiz = await service.replace_quiz(course_id, module_id, payload, instructor_id)
        return QuizResponse(**quiz)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{course_id}/modules/{module_id}/quiz", response_model=QuizResponse)
async def patch_module_quiz(
    course_id: _uuid.UUID,
    module_id: str,
    payload: QuizPatch,
    instructor_id: _uuid.UUID = Depends(require_instructor),
    pg_db: AsyncSession = Depends(get_db),
):
    service = ModuleQuizService(pg_db, get_mongodb())
    try:
        quiz = await service.patch_quiz(course_id, module_id, payload, instructor_id)
        return QuizResponse(**quiz)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/{course_id}/modules/{module_id}/quiz", status_code=status.HTTP_204_NO_CONTENT)
async def delete_module_quiz(
    course_id: _uuid.UUID,
    module_id: str,
    instructor_id: _uuid.UUID = Depends(require_instructor),
    pg_db: AsyncSession = Depends(get_db),
):
    service = ModuleQuizService(pg_db, get_mongodb())
    try:
        deleted = await service.delete_quiz(course_id, module_id, instructor_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{course_id}/modules/{module_id}/quiz/publish", response_model=QuizResponse)
async def publish_module_quiz(
    course_id: _uuid.UUID,
    module_id: str,
    payload: QuizPublishUpdate,
    instructor_id: _uuid.UUID = Depends(require_instructor),
    pg_db: AsyncSession = Depends(get_db),
):
    service = ModuleQuizService(pg_db, get_mongodb())
    try:
        quiz = await service.publish_quiz(course_id, module_id, payload, instructor_id)
        return QuizResponse(**quiz)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/{course_id}/modules/{module_id}/quiz/generate",
    response_model=QuizResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_module_quiz(
    course_id: _uuid.UUID,
    module_id: str,
    payload: QuizGenerateRequest,
    instructor_id: _uuid.UUID = Depends(require_instructor),
    pg_db: AsyncSession = Depends(get_db),
):
    service = ModuleQuizService(pg_db, get_mongodb())
    try:
        quiz = await service.generate_quiz(course_id, module_id, payload, instructor_id)
        return QuizResponse(**quiz)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
