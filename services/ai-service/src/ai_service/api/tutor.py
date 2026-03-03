"""Student AI tutor API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from ai_service.api.dependencies import get_authenticated_user
from ai_service.schemas.tutor import (
    CreateSessionRequest,
    SessionResponse,
    SendMessageRequest,
    SendMessageResponse,
)
from ai_service.services.tutor import TutorService

router = APIRouter()
tutor_service = TutorService()


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    request: CreateSessionRequest,
    user_info: tuple[int, str] = Depends(get_authenticated_user),
) -> SessionResponse:
    """Create a new tutor session.

    Args:
        request: Session creation request body
        user_info: Tuple of (user_id, role) from authenticated user

    Returns:
        SessionResponse with new session details
    """
    student_id = user_info[0]
    # TODO: Validate that the student is enrolled in the course
    # TODO: If module_id/lesson_id provided, validate they exist
    # TODO: If initial_message provided, perform RAG + LLM call
    # TODO: Persist session to PostgreSQL ai_conversations table
    return await tutor_service.create_session(student_id, request)


@router.post(
    "/sessions/{session_id}/messages",
    response_model=SendMessageResponse,
    status_code=status.HTTP_200_OK,
)
async def send_message(
    session_id: str,
    request: SendMessageRequest,
    user_info: tuple[int, str] = Depends(get_authenticated_user),
) -> SendMessageResponse:
    """Send a message to the tutor.

    Args:
        session_id: Session ID from path parameter
        request: Message request body
        user_info: Tuple of (user_id, role) from authenticated user

    Returns:
        SendMessageResponse with user and assistant messages
    """
    user_id = user_info[0]
    # TODO: Validate session exists and belongs to the authenticated user
    # TODO: Perform RAG retrieval filtered by session scope (course/module/lesson)
    # TODO: Call LLM with retrieved context + conversation history
    # TODO: Persist both messages to PostgreSQL ai_messages table
    return await tutor_service.send_message(session_id, user_id, request)
