"""API router aggregation."""

from fastapi import APIRouter

from ai_service.api import instructor, tutor, index

router = APIRouter()

router.include_router(
    instructor.router,
    prefix="/api/v1/ai/instructor",
    tags=["Instructor Content Generation"],
)
router.include_router(
    tutor.router,
    prefix="/api/v1/ai/tutor",
    tags=["Student AI Tutor"],
)
router.include_router(
    index.router,
    prefix="/api/v1/ai/index",
    tags=["RAG Indexing"],
)
