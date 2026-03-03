"""Common schemas and enums."""

from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class GenerationStatus(str, Enum):
    """Status values for content generation."""

    NOT_STARTED = "not_started"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class DifficultyLevel(str, Enum):
    """Question difficulty levels."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class QuestionType(str, Enum):
    """Question types for quizzes."""

    MULTIPLE_CHOICE = "multiple_choice"
    MULTIPLE_SELECT = "multiple_select"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"


class ContentScope(str, Enum):
    """Scope level for AI operations."""

    COURSE = "course"
    MODULE = "module"
    LESSON = "lesson"


class IndexStatus(str, Enum):
    """Status values for RAG indexing."""

    PENDING = "pending"
    INDEXING = "indexing"
    INDEXED = "indexed"
    FAILED = "failed"
    STALE = "stale"


class BaseTimestampSchema(BaseModel):
    """Base model with timestamp fields."""

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
