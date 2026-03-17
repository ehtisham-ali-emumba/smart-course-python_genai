import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_authenticated_user, require_instructor
from core.database import get_db
from core.mongodb import get_mongodb
from schemas.quiz_summary import (
    SummaryCreate,
    SummaryUpdate,
    SummaryPatch,
    SummaryPublishUpdate,
    SummaryGenerateRequest,
    SummaryResponse,
)
from services.module_summary import ModuleSummaryService

router = APIRouter()


@router.get("/{course_id}/modules/{module_id}/summary", response_model=SummaryResponse)
async def get_module_summary(
    course_id: _uuid.UUID,
    module_id: str,
    authenticated_user: tuple[_uuid.UUID, str, _uuid.UUID] = Depends(get_authenticated_user),
    pg_db: AsyncSession = Depends(get_db),
):
    _, role, profile_id = authenticated_user
    service = ModuleSummaryService(pg_db, get_mongodb())
    summary = await service.get_summary_for_viewer(course_id, module_id, profile_id, role)
    if not summary:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Summary not found")
    return SummaryResponse(**summary)


@router.post(
    "/{course_id}/modules/{module_id}/summary",
    response_model=SummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_module_summary(
    course_id: _uuid.UUID,
    module_id: str,
    payload: SummaryCreate,
    instructor_id: _uuid.UUID = Depends(require_instructor),
    pg_db: AsyncSession = Depends(get_db),
):
    service = ModuleSummaryService(pg_db, get_mongodb())
    try:
        summary = await service.create_summary(course_id, module_id, payload, instructor_id)
        return SummaryResponse(**summary)
    except FileExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/{course_id}/modules/{module_id}/summary", response_model=SummaryResponse)
async def replace_module_summary(
    course_id: _uuid.UUID,
    module_id: str,
    payload: SummaryUpdate,
    instructor_id: _uuid.UUID = Depends(require_instructor),
    pg_db: AsyncSession = Depends(get_db),
):
    service = ModuleSummaryService(pg_db, get_mongodb())
    try:
        summary = await service.replace_summary(course_id, module_id, payload, instructor_id)
        return SummaryResponse(**summary)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{course_id}/modules/{module_id}/summary", response_model=SummaryResponse)
async def patch_module_summary(
    course_id: _uuid.UUID,
    module_id: str,
    payload: SummaryPatch,
    instructor_id: _uuid.UUID = Depends(require_instructor),
    pg_db: AsyncSession = Depends(get_db),
):
    service = ModuleSummaryService(pg_db, get_mongodb())
    try:
        summary = await service.patch_summary(course_id, module_id, payload, instructor_id)
        return SummaryResponse(**summary)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/{course_id}/modules/{module_id}/summary", status_code=status.HTTP_204_NO_CONTENT)
async def delete_module_summary(
    course_id: _uuid.UUID,
    module_id: str,
    instructor_id: _uuid.UUID = Depends(require_instructor),
    pg_db: AsyncSession = Depends(get_db),
):
    service = ModuleSummaryService(pg_db, get_mongodb())
    try:
        deleted = await service.delete_summary(course_id, module_id, instructor_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Summary not found")
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{course_id}/modules/{module_id}/summary/publish", response_model=SummaryResponse)
async def publish_module_summary(
    course_id: _uuid.UUID,
    module_id: str,
    payload: SummaryPublishUpdate,
    instructor_id: _uuid.UUID = Depends(require_instructor),
    pg_db: AsyncSession = Depends(get_db),
):
    service = ModuleSummaryService(pg_db, get_mongodb())
    try:
        summary = await service.publish_summary(course_id, module_id, payload, instructor_id)
        return SummaryResponse(**summary)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post(
    "/{course_id}/modules/{module_id}/summary/generate",
    response_model=SummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_module_summary(
    course_id: _uuid.UUID,
    module_id: str,
    payload: SummaryGenerateRequest,
    instructor_id: _uuid.UUID = Depends(require_instructor),
    pg_db: AsyncSession = Depends(get_db),
):
    service = ModuleSummaryService(pg_db, get_mongodb())
    try:
        summary = await service.generate_summary(course_id, module_id, payload, instructor_id)
        return SummaryResponse(**summary)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
