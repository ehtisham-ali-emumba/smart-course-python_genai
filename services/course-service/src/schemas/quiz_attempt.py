from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


QuestionType = Literal["multiple_choice", "multiple_select", "true_false", "short_answer"]


class AnswerSubmission(BaseModel):
    question_id: str
    response: dict[str, Any]
    time_spent_seconds: int | None = Field(default=None, ge=0)


class QuizSubmitRequest(BaseModel):
    answers: list[AnswerSubmission] = Field(..., min_length=1)
    total_time_spent_seconds: int | None = Field(default=None, ge=0)


class StartQuizOption(BaseModel):
    option_id: str
    text: str


class StartQuizQuestion(BaseModel):
    question_id: str
    order: int
    question_text: str
    question_type: QuestionType
    options: list[StartQuizOption] | None = None
    hint: str | None = None


class StartQuizResponse(BaseModel):
    attempt_id: UUID
    started_at: datetime
    time_limit_minutes: int | None = None
    questions: list[StartQuizQuestion]


class AnswerResult(BaseModel):
    question_id: str
    is_correct: bool | None = None
    user_response: dict[str, Any]
    correct_answer: dict[str, Any] | None = None
    explanation: str | None = None


class SubmitQuizResponse(BaseModel):
    attempt_id: UUID
    status: str
    score: Decimal
    passed: bool
    total_questions: int
    correct_answers: int
    time_spent_seconds: int | None
    submitted_at: datetime
    results: list[AnswerResult]


class AttemptAnswerDetail(BaseModel):
    question_id: str
    question_type: QuestionType
    user_response: dict[str, Any]
    is_correct: bool | None = None
    time_spent_seconds: int | None = None
    correct_answer: dict[str, Any] | None = None
    explanation: str | None = None


class AttemptDetailResponse(BaseModel):
    attempt_id: UUID
    status: str
    score: Decimal | None = None
    passed: bool | None = None
    total_questions: int | None = None
    correct_answers: int | None = None
    time_spent_seconds: int | None = None
    started_at: datetime
    submitted_at: datetime | None = None
    quiz_outdated: bool = False
    answers: list[AttemptAnswerDetail]
