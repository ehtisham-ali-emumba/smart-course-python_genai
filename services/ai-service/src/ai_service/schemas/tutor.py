"""Tutor session and messaging schemas."""

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field
from uuid import UUID, uuid4


class CreateSessionRequest(BaseModel):
    """Request body for POST /sessions."""

    course_id: UUID
    module_id: Optional[str] = Field(
        None,
        description="Scope the tutor to a specific module.",
    )
    lesson_id: Optional[str] = Field(
        None,
        description="Scope the tutor to a specific lesson.",
    )
    initial_message: Optional[str] = Field(
        None,
        description="Optional first question to immediately ask.",
    )


class SessionResponse(BaseModel):
    """Response for tutor session creation."""

    session_id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="Unique session identifier.",
    )
    student_id: UUID
    course_id: UUID
    module_id: Optional[str] = None
    lesson_id: Optional[str] = None
    is_active: bool = True
    initial_reply: Optional[str] = Field(
        None,
        description="AI reply to the initial message (placeholder).",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SendMessageRequest(BaseModel):
    """Request body for POST /sessions/{session_id}/messages."""

    message: str = Field(..., min_length=1, max_length=5000)
    module_id: Optional[str] = Field(
        None,
        description="Optionally narrow or change the scope to a module.",
    )
    lesson_id: Optional[str] = Field(
        None,
        description="Optionally narrow or change the scope to a lesson.",
    )


class RetrievedSource(BaseModel):
    """A source chunk retrieved from the RAG index."""

    module_title: str
    lesson_title: str
    module_id: str
    lesson_id: str
    chunk_index: int
    score: float
    text_preview: str = Field(
        ...,
        description="First 200 chars of the retrieved chunk.",
    )


class SessionScope(BaseModel):
    """Tracks the active scope of a tutor session."""

    course_id: UUID
    module_id: Optional[str] = None
    lesson_id: Optional[str] = None


class MessageResponse(BaseModel):
    """A single message in a tutor conversation."""

    message_id: str = Field(default_factory=lambda: uuid4().hex)
    session_id: str
    role: Literal["user", "assistant"]
    content: str
    module_id: Optional[str] = None
    lesson_id: Optional[str] = None
    sources: list[RetrievedSource] = Field(
        default_factory=list,
        description="RAG sources used to generate this response (assistant messages only).",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SendMessageResponse(BaseModel):
    """Response for sending a message to the tutor."""

    user_message: MessageResponse
    assistant_message: MessageResponse
