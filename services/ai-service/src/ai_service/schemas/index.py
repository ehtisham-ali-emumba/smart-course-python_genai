"""RAG indexing schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

from ai_service.schemas.common import IndexStatus


class BuildIndexRequest(BaseModel):
    """Optional body for build requests (both course and module level)."""

    force_rebuild: bool = Field(
        False,
        description="If True, rebuild even if content hasn't changed.",
    )


class IndexBuildResponse(BaseModel):
    """Response for triggering an index build."""

    course_id: UUID
    module_id: Optional[str] = None
    status: IndexStatus = IndexStatus.PENDING
    message: str = "Index building is not yet implemented."
    requested_at: datetime = Field(default_factory=datetime.utcnow)


class IndexStatusResponse(BaseModel):
    """Response for checking index build status."""

    course_id: UUID
    module_id: Optional[str] = None
    status: IndexStatus = IndexStatus.PENDING
    total_chunks: int = 0
    embedding_model: Optional[str] = None
    last_build_at: Optional[datetime] = None
    error_message: Optional[str] = None
    message: str = "Index status tracking is not yet implemented."
