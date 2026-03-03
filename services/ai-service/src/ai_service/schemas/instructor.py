"""Instructor content generation schemas."""

from datetime import datetime
from typing import Optional
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

    course_id: int
    module_id: str
    source_lesson_ids: list[str] = Field(default_factory=list)
    summary_id: Optional[str] = Field(
        None,
        description="MongoDB _id of the persisted summary (populated after generation).",
    )
    status: GenerationStatus = GenerationStatus.NOT_IMPLEMENTED
    message: str = "Summary generation is not yet implemented."
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

    course_id: int
    module_id: str
    source_lesson_ids: list[str] = Field(default_factory=list)
    quiz_id: Optional[str] = Field(
        None,
        description="MongoDB _id of the persisted quiz (populated after generation).",
    )
    question_count: int = 0
    status: GenerationStatus = GenerationStatus.NOT_IMPLEMENTED
    message: str = "Quiz generation is not yet implemented."
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


# ── Combined Generation ──────────────────────────────────────────────


class GenerateAllRequest(BaseModel):
    """Request body for POST /modules/{module_id}/generate-all."""

    source_lesson_ids: Optional[list[str]] = None

    # Summary options
    include_glossary: bool = True
    include_key_points: bool = True
    include_learning_objectives: bool = True
    summary_language: str = Field("en", max_length=10)

    # Quiz options
    num_questions: int = Field(5, ge=1, le=20)
    difficulty: Optional[DifficultyLevel] = None
    question_types: list[QuestionType] = Field(
        default_factory=lambda: [
            QuestionType.MULTIPLE_CHOICE,
            QuestionType.TRUE_FALSE,
        ],
    )
    quiz_language: str = Field("en", max_length=10)


class GenerateAllResponse(BaseModel):
    """Response for combined summary + quiz generation."""

    course_id: int
    module_id: str
    summary: GenerateSummaryResponse
    quiz: GenerateQuizResponse


# ── Generation Status ────────────────────────────────────────────────


class GenerationStatusResponse(BaseModel):
    """Response for GET /modules/{module_id}/generation-status."""

    course_id: int
    module_id: str
    summary_status: GenerationStatus = GenerationStatus.NOT_IMPLEMENTED
    quiz_status: GenerationStatus = GenerationStatus.NOT_IMPLEMENTED
    last_generation_at: Optional[datetime] = None
    message: str = "Generation status tracking is not yet implemented."
