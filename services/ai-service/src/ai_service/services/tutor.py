"""Student AI tutor service."""

from ai_service.schemas.tutor import (
    CreateSessionRequest,
    SessionResponse,
    SendMessageRequest,
    SendMessageResponse,
    MessageResponse,
)


class TutorService:
    """Handles AI tutor sessions and messages."""

    async def create_session(
        self, student_id: int, request: CreateSessionRequest
    ) -> SessionResponse:
        """Create a new tutor session."""
        # TODO: Verify student enrollment via course-service or direct DB query
        # TODO: Persist session to PostgreSQL
        # TODO: If initial_message, perform RAG + LLM call
        initial_reply = None
        if request.initial_message:
            initial_reply = "AI tutor is not yet implemented."

        return SessionResponse(
            student_id=student_id,
            course_id=request.course_id,
            module_id=request.module_id,
            lesson_id=request.lesson_id,
            is_active=True,
            initial_reply=initial_reply,
        )

    async def send_message(
        self, session_id: str, user_id: int, request: SendMessageRequest
    ) -> SendMessageResponse:
        """Send a message to the tutor."""
        # TODO: Validate session existence and ownership
        # TODO: Embed user question via OpenAI embeddings
        # TODO: Search Qdrant for relevant chunks (filtered by session scope)
        # TODO: Build prompt with context + conversation history
        # TODO: Call LLM and stream response
        # TODO: Persist both messages to PostgreSQL

        user_message = MessageResponse(
            session_id=session_id,
            role="user",
            content=request.message,
            module_id=request.module_id,
            lesson_id=request.lesson_id,
        )

        assistant_message = MessageResponse(
            session_id=session_id,
            role="assistant",
            content="AI tutor is not yet implemented.",
            module_id=request.module_id,
            lesson_id=request.lesson_id,
        )

        return SendMessageResponse(
            user_message=user_message,
            assistant_message=assistant_message,
        )
