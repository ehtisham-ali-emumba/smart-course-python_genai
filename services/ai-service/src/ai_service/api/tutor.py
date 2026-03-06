"""Student AI tutor API routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from ai_service.api.dependencies import get_authenticated_user, get_tutor_service
from ai_service.schemas.tutor import (
    CreateSessionRequest,
    SessionResponse,
    SendMessageRequest,
    SendMessageResponse,
)
from ai_service.services.tutor import TutorService

router = APIRouter()


@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    request: CreateSessionRequest,
    user_info: tuple[int, str] = Depends(get_authenticated_user),
    tutor_service: TutorService = Depends(get_tutor_service),
) -> SessionResponse:
    """Create a new tutor session.

    The student specifies a course (required) and optionally a module/lesson
    to scope the tutor's context. An optional initial message can be provided
    to immediately get a response.
    """
    student_id = user_info[0]
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
    tutor_service: TutorService = Depends(get_tutor_service),
) -> SendMessageResponse:
    """Send a message to the tutor and receive an AI-generated response.

    The tutor searches the course's RAG index for relevant content,
    then generates a response using GPT-4o-mini with the retrieved context.

    Optionally override the scope (module_id, lesson_id) per message.
    """
    user_id = user_info[0]
    try:
        return await tutor_service.send_message(session_id, user_id, request)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
