import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import require_student
from core.database import get_db
from core.mongodb import get_mongodb
from schemas.quiz_attempt import (
    AttemptDetailResponse,
    QuizSubmitRequest,
    StartQuizResponse,
    SubmitQuizResponse,
)
from services.quiz_attempt import QuizAttemptService

router = APIRouter()


@router.post(
    "/{course_id}/modules/{module_id}/quiz/attempts/start",
    response_model=StartQuizResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_quiz_attempt(
    course_id: _uuid.UUID,
    module_id: str,
    response: Response,
    student_id: _uuid.UUID = Depends(require_student),
    pg_db: AsyncSession = Depends(get_db),
):
    service = QuizAttemptService(pg_db, get_mongodb())
    try:
        attempt, created = await service.start_attempt(course_id, module_id, student_id)
        if not created:
            response.status_code = status.HTTP_200_OK
        return StartQuizResponse(**attempt)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post(
    "/{course_id}/modules/{module_id}/quiz/attempts/{attempt_id}/submit",
    response_model=SubmitQuizResponse,
)
async def submit_quiz_attempt(
    course_id: _uuid.UUID,
    module_id: str,
    attempt_id: _uuid.UUID,
    payload: QuizSubmitRequest,
    student_id: _uuid.UUID = Depends(require_student),
    pg_db: AsyncSession = Depends(get_db),
):
    service = QuizAttemptService(pg_db, get_mongodb())
    try:
        result = await service.submit_attempt(course_id, module_id, attempt_id, payload, student_id)
        return SubmitQuizResponse(**result)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except FileExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/{course_id}/modules/{module_id}/quiz/attempts/{attempt_id}",
    response_model=AttemptDetailResponse,
)
async def get_quiz_attempt_detail(
    course_id: _uuid.UUID,
    module_id: str,
    attempt_id: _uuid.UUID,
    student_id: _uuid.UUID = Depends(require_student),
    pg_db: AsyncSession = Depends(get_db),
):
    service = QuizAttemptService(pg_db, get_mongodb())
    try:
        attempt = await service.get_attempt_detail(course_id, module_id, attempt_id, student_id)
        return AttemptDetailResponse(**attempt)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
