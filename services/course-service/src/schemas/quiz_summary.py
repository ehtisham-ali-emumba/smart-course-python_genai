from pydantic import BaseModel, Field, model_validator
from typing import Literal, Optional
from datetime import datetime
from uuid import UUID

# ── Options ──────────────────────────────────────────────────────────────────


class QuizOptionSchema(BaseModel):
    option_id: str
    text: str
    is_correct: bool


# ── Questions ─────────────────────────────────────────────────────────────────


class QuizQuestionCreate(BaseModel):
    order: int = Field(..., ge=1)
    question_text: str = Field(..., min_length=1)
    question_type: Literal["multiple_choice", "multiple_select", "true_false", "short_answer"]
    options: Optional[list[QuizOptionSchema]] = None  # required for all except short_answer
    correct_answers: Optional[list[str]] = None  # required for short_answer
    case_sensitive: Optional[bool] = False  # short_answer only
    explanation: Optional[str] = None
    hint: Optional[str] = None

    @model_validator(mode="after")
    def validate_by_question_type(self):
        requires_options = {
            "multiple_choice",
            "multiple_select",
            "true_false",
        }

        if self.question_type in requires_options:
            if not self.options:
                raise ValueError("options are required for this question_type")
            if self.correct_answers is not None:
                raise ValueError("correct_answers must not be provided when options are used")

        if self.question_type == "multiple_choice":
            correct_count = sum(1 for option in self.options or [] if option.is_correct)
            if correct_count != 1:
                raise ValueError("multiple_choice requires exactly one correct option")

        if self.question_type == "multiple_select":
            correct_count = sum(1 for option in self.options or [] if option.is_correct)
            if correct_count < 1:
                raise ValueError("multiple_select requires at least one correct option")

        if self.question_type == "true_false":
            option_ids = {option.option_id for option in self.options or []}
            if option_ids != {"opt_true", "opt_false"}:
                raise ValueError(
                    "true_false requires options with option_id values opt_true and opt_false"
                )
            correct_count = sum(1 for option in self.options or [] if option.is_correct)
            if correct_count != 1:
                raise ValueError("true_false requires exactly one correct option")

        if self.question_type == "short_answer":
            if self.options is not None:
                raise ValueError("options must not be provided for short_answer")
            if not self.correct_answers:
                raise ValueError("correct_answers are required for short_answer")

        return self


class QuizQuestionResponse(QuizQuestionCreate):
    question_id: str


# ── Settings ──────────────────────────────────────────────────────────────────


class QuizSettingsSchema(BaseModel):
    passing_score: int = Field(70, ge=0, le=100)
    time_limit_minutes: Optional[int] = Field(None, ge=1)
    max_attempts: int = Field(3, ge=1)
    shuffle_questions: bool = True
    shuffle_options: bool = True
    show_correct_answers_after: Literal["completion", "passing", "never"] = "completion"


# ── Authorship ────────────────────────────────────────────────────────────────


class AuthorshipResponse(BaseModel):
    source: Literal["ai_generated", "manual", "ai_edited"]
    generated_by_user_id: Optional[UUID]
    ai_model: Optional[str]
    source_lesson_ids: list[str]
    version: int
    last_edited_by: Optional[UUID]
    last_edited_at: Optional[datetime]


# ── Quiz Request/Response ─────────────────────────────────────────────────────


class QuizCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = None
    settings: QuizSettingsSchema = Field(default_factory=QuizSettingsSchema)
    questions: list[QuizQuestionCreate] = Field(..., min_length=1)
    is_published: bool = False


class QuizUpdate(BaseModel):
    """Full replacement — all fields required (PUT semantics)."""

    title: str = Field(..., min_length=1, max_length=300)
    description: Optional[str] = None
    settings: QuizSettingsSchema
    questions: list[QuizQuestionCreate] = Field(..., min_length=1)
    is_published: bool


class QuizPatch(BaseModel):
    """Partial update — all fields optional (PATCH semantics)."""

    title: Optional[str] = Field(None, min_length=1, max_length=300)
    description: Optional[str] = None
    settings: Optional[QuizSettingsSchema] = None
    questions: Optional[list[QuizQuestionCreate]] = None
    is_published: Optional[bool] = None


class QuizPublishUpdate(BaseModel):
    is_published: bool


class QuizGenerateRequest(BaseModel):
    """Trigger AI generation from selected lessons in the module."""

    source_lesson_ids: list[str] = Field(..., min_length=1)
    num_questions: int = Field(5, ge=1, le=20)
    passing_score: int = Field(70, ge=0, le=100)
    max_attempts: int = Field(3, ge=1)
    time_limit_minutes: Optional[int] = Field(None, ge=1)


class QuizResponse(BaseModel):
    id: str  # MongoDB _id as hex string
    course_id: UUID
    module_id: str
    title: str
    description: Optional[str]
    settings: QuizSettingsSchema
    questions: list[QuizQuestionResponse]
    authorship: AuthorshipResponse
    is_published: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ── Summary Schemas ───────────────────────────────────────────────────────────


class GlossaryTermSchema(BaseModel):
    term: str
    definition: str


class DifficultyAssessmentSchema(BaseModel):
    level: Literal["beginner", "intermediate", "advanced"]
    estimated_read_minutes: int = Field(..., ge=1)


class SummaryContentCreate(BaseModel):
    summary_text: str = Field(..., min_length=1)
    summary_html: Optional[str] = None
    key_points: list[str] = Field(default_factory=list)
    learning_objectives: list[str] = Field(default_factory=list)
    glossary: list[GlossaryTermSchema] = Field(default_factory=list)
    difficulty_assessment: Optional[DifficultyAssessmentSchema] = None


class SummaryCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    content: SummaryContentCreate
    is_published: bool = False


class SummaryUpdate(BaseModel):
    """Full replacement — all fields required (PUT semantics)."""

    title: str = Field(..., min_length=1, max_length=300)
    content: SummaryContentCreate
    is_published: bool


class SummaryPatch(BaseModel):
    """Partial update — all fields optional (PATCH semantics)."""

    title: Optional[str] = Field(None, min_length=1, max_length=300)
    content: Optional[SummaryContentCreate] = None
    is_published: Optional[bool] = None


class SummaryPublishUpdate(BaseModel):
    is_published: bool


class SummaryGenerateRequest(BaseModel):
    """Trigger AI generation from selected lessons in the module."""

    source_lesson_ids: list[str] = Field(..., min_length=1)
    include_glossary: bool = True
    include_key_points: bool = True
    include_learning_objectives: bool = True


class SummaryResponse(BaseModel):
    id: str  # MongoDB _id as hex string
    course_id: UUID
    module_id: str
    title: str
    content: SummaryContentCreate
    authorship: AuthorshipResponse
    is_published: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
