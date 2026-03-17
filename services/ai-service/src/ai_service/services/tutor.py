"""Student AI tutor service — LangGraph-powered RAG tutoring."""

import structlog
import uuid as _uuid
from uuid import uuid4

from ai_service.clients.openai_client import OpenAIClient
from ai_service.repositories.vector_store import VectorStoreRepository
from ai_service.services.tutor_agent import build_tutor_graph, TutorState
from ai_service.schemas.tutor import (
    CreateSessionRequest,
    SessionResponse,
    SendMessageRequest,
    SendMessageResponse,
    MessageResponse,
    RetrievedSource,
)

logger = structlog.get_logger(__name__)

# Max conversation history entries to keep in memory per session
MAX_HISTORY_PER_SESSION = 50


class TutorService:
    """Handles AI tutor sessions and messages using LangGraph."""

    def __init__(
        self,
        openai_client: OpenAIClient,
        vector_store: VectorStoreRepository,
    ):
        self.openai_client = openai_client
        self.vector_store = vector_store

        # In-memory session store (MVP — no persistence)
        # Structure: {session_id: {course_id, module_id, lesson_id, student_id, history}}
        self._sessions: dict[str, dict] = {}

    async def create_session(
        self, student_id: _uuid.UUID, request: CreateSessionRequest
    ) -> SessionResponse:
        """Create a new tutor session."""
        session_id = uuid4().hex

        # Store session in memory
        self._sessions[session_id] = {
            "student_id": student_id,
            "course_id": request.course_id,
            "module_id": request.module_id,
            "lesson_id": request.lesson_id,
            "history": [],  # [{role, content}, ...]
        }

        logger.info(
            "Tutor session created",
            session_id=session_id,
            student_id=student_id,
            course_id=request.course_id,
            module_id=request.module_id,
            lesson_id=request.lesson_id,
        )

        # If initial message provided, process it through the agent
        initial_reply = None
        if request.initial_message:
            response = await self._run_agent(
                session_id=session_id,
                query=request.initial_message,
                module_id=request.module_id,
                lesson_id=request.lesson_id,
            )
            initial_reply = response["response"]

        return SessionResponse(
            session_id=session_id,
            student_id=student_id,
            course_id=request.course_id,
            module_id=request.module_id,
            lesson_id=request.lesson_id,
            is_active=True,
            initial_reply=initial_reply,
        )

    async def send_message(
        self, session_id: str, user_id: _uuid.UUID, request: SendMessageRequest
    ) -> SendMessageResponse:
        """Send a message to the tutor and get a response."""
        log = logger.bind(session_id=session_id, user_id=user_id)

        # Validate session exists
        session = self._sessions.get(session_id)
        if not session:
            log.warning("Session not found")
            # For MVP, create an ad-hoc session if not found
            # (handles service restarts gracefully)
            raise ValueError(f"Session {session_id} not found. Please create a new session.")

        # Validate ownership
        if session["student_id"] != user_id:
            raise ValueError("Session does not belong to this user.")

        # Determine scope (request can override session scope)
        module_id = request.module_id or session.get("module_id")
        lesson_id = request.lesson_id or session.get("lesson_id")

        # Run the LangGraph agent
        result = await self._run_agent(
            session_id=session_id,
            query=request.message,
            module_id=module_id,
            lesson_id=lesson_id,
        )

        # Build source attributions
        sources = [
            RetrievedSource(
                module_title=s.get("module_title", ""),
                lesson_title=s.get("lesson_title", ""),
                module_id=s.get("module_id", ""),
                lesson_id=s.get("lesson_id", ""),
                chunk_index=s.get("chunk_index", 0),
                score=s.get("score", 0.0),
                text_preview=s.get("text_preview", ""),
            )
            for s in result.get("sources", [])
        ]

        # Build response messages
        user_message = MessageResponse(
            session_id=session_id,
            role="user",
            content=request.message,
            module_id=module_id,
            lesson_id=lesson_id,
        )

        assistant_message = MessageResponse(
            session_id=session_id,
            role="assistant",
            content=result["response"],
            module_id=module_id,
            lesson_id=lesson_id,
            sources=sources,
        )

        return SendMessageResponse(
            user_message=user_message,
            assistant_message=assistant_message,
        )

    async def _run_agent(
        self,
        session_id: str,
        query: str,
        module_id: str | None = None,
        lesson_id: str | None = None,
    ) -> dict:
        """Run the LangGraph tutor agent and update conversation history.

        Returns:
            Dict with keys: response (str), sources (list[dict])
        """
        session = self._sessions[session_id]

        # Build the LangGraph agent (cheap — just wires closures)
        graph = build_tutor_graph(
            openai_client=self.openai_client,
            vector_store=self.vector_store,
        )

        # Prepare initial state
        initial_state: TutorState = {
            "query": query,
            "course_id": session["course_id"],
            "module_id": module_id,
            "lesson_id": lesson_id,
            "conversation_history": session["history"],
        }

        # Run the graph
        result = await graph.ainvoke(initial_state)

        # Update conversation history
        session["history"].append({"role": "user", "content": query})
        session["history"].append({"role": "assistant", "content": result["response"]})

        # Trim history if it gets too long
        if len(session["history"]) > MAX_HISTORY_PER_SESSION:
            session["history"] = session["history"][-MAX_HISTORY_PER_SESSION:]

        return {
            "response": result["response"],
            "sources": result.get("sources", []),
        }
