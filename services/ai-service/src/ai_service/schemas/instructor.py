"""Instructor content generation schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field

from ai_service.schemas.common import (
    GenerationStatus,
    DifficultyLevel,
    QuestionType,
)


# ── Summary Generation ──────────────────────────────────────────────


class GenerateSummaryRequest(BaseModel):
    """Request body for POST /modules/{module_id}/generate-summary."""

    source_lesson_ids: Optional[list[str]] = Field(
        None,
        description="Specific lesson IDs to use. If omitted, all lessons in the module are used.",
    )
    include_glossary: bool = True
    include_key_points: bool = True
    include_learning_objectives: bool = True
    language: str = Field("en", max_length=10)
    tone: Optional[str] = Field(
        None,
        description="Desired tone: 'formal', 'conversational', 'academic'. Optional.",
    )
    max_length_words: Optional[int] = Field(None, ge=50, le=5000)


class GenerateSummaryResponse(BaseModel):
    """Response for summary generation request."""

    course_id: UUID
    module_id: str
    source_lesson_ids: list[str] = Field(default_factory=list)
    summary_id: Optional[str] = Field(
        None,
        description="MongoDB _id of the persisted summary (populated after generation).",
    )
    status: GenerationStatus = GenerationStatus.PENDING
    message: str = "Summary generation started."
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


# ── Quiz Generation ──────────────────────────────────────────────────


class GenerateQuizRequest(BaseModel):
    """Request body for POST /modules/{module_id}/generate-quiz."""

    source_lesson_ids: Optional[list[str]] = Field(
        None,
        description="Specific lesson IDs to use. If omitted, all lessons in the module are used.",
    )
    num_questions: int = Field(5, ge=1, le=20)
    difficulty: Optional[DifficultyLevel] = None
    question_types: list[QuestionType] = Field(
        default_factory=lambda: [
            QuestionType.MULTIPLE_CHOICE,
            QuestionType.TRUE_FALSE,
        ],
    )
    passing_score: int = Field(70, ge=0, le=100)
    max_attempts: int = Field(3, ge=1)
    time_limit_minutes: Optional[int] = Field(None, ge=1)
    language: str = Field("en", max_length=10)


class GenerateQuizResponse(BaseModel):
    """Response for quiz generation request."""

    course_id: UUID
    module_id: str
    source_lesson_ids: list[str] = Field(default_factory=list)
    quiz_id: Optional[str] = Field(
        None,
        description="MongoDB _id of the persisted quiz (populated after generation).",
    )
    question_count: int = 0
    status: GenerationStatus = GenerationStatus.PENDING
    message: str = "Quiz generation started."
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


# ── Generation Status ────────────────────────────────────────────────


class GenerationStatusResponse(BaseModel):
    """Response for GET /modules/{module_id}/generation-status."""

    course_id: UUID
    module_id: str
    summary_status: GenerationStatus = GenerationStatus.NOT_STARTED
    quiz_status: GenerationStatus = GenerationStatus.NOT_STARTED
    summary_error: str | None = None
    quiz_error: str | None = None
    last_generation_at: Optional[datetime] = None
