"""LangGraph implementation for quiz and summary generation with validation & retry.

Implements two state machines:
  - Quiz: extract_content → generate_quiz → validate_quiz ⇄ persist_quiz → END
  - Summary: extract_content → generate_summary → validate_summary ⇄ persist_summary → END

Uses stateful retry with validation feedback fed back to the LLM.
Follows the same closure/factory pattern as tutor_agent.py.
"""

import structlog
import uuid as _uuid
from typing import TypedDict, Any
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from ai_service.clients.openai_client import (
    OpenAIClient,
    GeneratedQuiz,
    GeneratedQuizQuestion,
    GeneratedQuizOption,
    GeneratedSummary,
)
from ai_service.clients.course_service_client import CourseServiceClient
from ai_service.services.content_extractor import ContentExtractor
from ai_service.schemas.instructor import GenerateQuizRequest

logger = structlog.get_logger(__name__)

# ── Configuration ──────────────────────────────────────────────────

MAX_RETRIES = 1  # Allow one retry attempt if validation fails


# ── Quiz State ─────────────────────────────────────────────────────


class QuizState(TypedDict):
    """State that flows through the quiz generation graph."""

    # Required Input
    course_id: _uuid.UUID
    module_id: str
    user_id: _uuid.UUID
    profile_id: _uuid.UUID
    num_questions: int
    language: str
    passing_score: int
    max_attempts: int
    retry_count: int

    # Optional Input
    source_lesson_ids: list[str] | None
    difficulty: str | None
    question_types: list[str]
    time_limit_minutes: int | None

    # Intermediate (set by nodes)
    combined_text: str
    generated_quiz: GeneratedQuiz | None
    validation_passed: bool
    validation_feedback: str

    # Output (set by persist node)
    persisted: bool
    error: str | None


# ── Summary State ──────────────────────────────────────────────────


class SummaryState(TypedDict):
    """State that flows through the summary generation graph."""

    # Required Input
    course_id: _uuid.UUID
    module_id: str
    user_id: _uuid.UUID
    profile_id: _uuid.UUID
    language: str
    retry_count: int

    # Optional Input
    source_lesson_ids: list[str] | None
    include_glossary: bool
    include_key_points: bool
    include_learning_objectives: bool
    max_length_words: int | None
    tone: str | None

    # Intermediate (set by nodes)
    combined_text: str
    generated_summary: GeneratedSummary | None
    validation_passed: bool
    validation_feedback: str

    # Output (set by persist node)
    persisted: bool
    error: str | None


# ── Shared Node: Extract Content ──────────────────────────────────


def _build_extract_content_node(content_extractor: ContentExtractor):
    """Factory for the extract_content node (shared by both graphs)."""

    async def extract_content(state: QuizState | SummaryState) -> dict:
        """Extract module content from MongoDB and PDFs."""
        course_id = state["course_id"]
        module_id = state["module_id"]
        source_lesson_ids = state.get("source_lesson_ids")

        log = logger.bind(course_id=course_id, module_id=module_id)
        log.info(
            "[EXTRACT_CONTENT] Starting content extraction", source_lesson_ids=source_lesson_ids
        )

        try:
            log.info("[EXTRACT_CONTENT] Calling content_extractor.extract_module_content()")
            content = await content_extractor.extract_module_content(
                course_id, module_id, source_lesson_ids
            )
            if not content:
                log.warning("[EXTRACT_CONTENT] No content found for module")
                return {
                    "combined_text": "",
                    "error": "Module not found or has no content",
                }

            combined_text = content.get("combined_text", "")
            if not combined_text:
                log.warning("[EXTRACT_CONTENT] Content extraction returned empty text")
                return {
                    "combined_text": "",
                    "error": "Module has no extractable content",
                }

            log.info(
                "[EXTRACT_CONTENT] ✓ Content extracted successfully", text_length=len(combined_text)
            )
            return {"combined_text": combined_text}

        except Exception as e:
            log.exception("[EXTRACT_CONTENT] ✗ Error extracting content", error=str(e))
            return {"error": str(e)}

    return extract_content


# ── Quiz Nodes ─────────────────────────────────────────────────────


def _build_generate_quiz_node(openai_client: OpenAIClient):
    """Factory for the generate_quiz node."""

    async def generate_quiz(state: QuizState) -> dict:
        """Generate quiz using OpenAI, with optional validation feedback appended."""
        combined_text = state["combined_text"]
        num_questions = state["num_questions"]
        difficulty = state.get("difficulty")
        question_types = state.get("question_types", [])
        language = state.get("language", "en")
        validation_feedback = state.get("validation_feedback", "")
        retry_count = state.get("retry_count", 0)

        log = logger.bind(
            course_id=state["course_id"],
            module_id=state["module_id"],
            retry_count=retry_count,
        )

        if retry_count > 0:
            log.info("[GENERATE_QUIZ] Retrying quiz generation", attempt=retry_count + 1)
        else:
            log.info(
                "[GENERATE_QUIZ] Starting initial quiz generation",
                num_questions=num_questions,
                difficulty=difficulty,
            )

        # If retrying, append feedback to the prompt
        context_text = combined_text
        if validation_feedback and retry_count > 0:
            log.info(
                "[GENERATE_QUIZ] Appending validation feedback to prompt for self-correction",
                num_issues=len(validation_feedback.split("- ")),
            )
            context_text = (
                f"{combined_text}\n\n"
                f"## Feedback from previous attempt (please fix):\n{validation_feedback}"
            )

        try:
            log.info("[GENERATE_QUIZ] Calling OpenAI.generate_quiz()")
            generated = await openai_client.generate_quiz(
                context_text,
                num_questions=num_questions,
                difficulty=difficulty,
                question_types=question_types,
                language=language,
            )

            log.info(
                "[GENERATE_QUIZ] ✓ Quiz generated successfully",
                num_questions=len(generated.questions),
                title=generated.title,
            )
            return {
                "generated_quiz": generated,
                "validation_passed": False,  # Will be set by validate node
                "validation_feedback": "",
            }

        except Exception as e:
            log.exception("[GENERATE_QUIZ] ✗ Error generating quiz", error=str(e))
            return {"error": str(e)}

    return generate_quiz


def _build_validate_quiz_node():
    """Factory for the validate_quiz node."""

    async def validate_quiz(state: QuizState) -> dict:
        """Validate generated quiz structure and content."""
        generated = state.get("generated_quiz")
        num_questions = state["num_questions"]
        retry_count = state.get("retry_count", 0)

        log = logger.bind(
            course_id=state["course_id"],
            module_id=state["module_id"],
            retry_count=retry_count,
        )

        log.info("[VALIDATE_QUIZ] Starting quiz validation")

        issues = []

        if not generated:
            log.error("[VALIDATE_QUIZ] No quiz generated")
            return {
                "validation_passed": False,
                "validation_feedback": "No quiz generated",
            }

        # 1. Check question count
        if len(generated.questions) != num_questions:
            issues.append(f"Expected {num_questions} questions, got {len(generated.questions)}")

        # 2. Check each question
        for i, question in enumerate(generated.questions, 1):
            # Check question text
            if not question.question_text or not question.question_text.strip():
                issues.append(f"Question {i}: missing or empty question_text")

            # Check explanation
            if not question.explanation or not question.explanation.strip():
                issues.append(f"Question {i}: missing or empty explanation")

            # Validate options for choice-based questions
            if question.question_type in ["multiple_choice", "multiple_select", "true_false"]:
                if not question.options:
                    issues.append(f"Question {i}: {question.question_type} has no options")
                elif len(question.options) < 2:
                    issues.append(
                        f"Question {i}: {question.question_type} has fewer than 2 options"
                    )
                else:
                    # Check at least one correct option
                    correct_count = sum(1 for opt in question.options if opt.is_correct)
                    if correct_count == 0:
                        issues.append(
                            f"Question {i}: {question.question_type} has no correct options"
                        )

            # Validate short_answer questions
            elif question.question_type == "short_answer":
                if not question.correct_answers or len(question.correct_answers) == 0:
                    issues.append(f"Question {i}: short_answer has no correct_answers")

        if issues:
            feedback = "Please fix the following issues:\n" + "\n".join(
                f"- {issue}" for issue in issues
            )
            log.warning("[VALIDATE_QUIZ] Validation failed", num_issues=len(issues), issues=issues)
            return {
                "validation_passed": False,
                "validation_feedback": feedback,
            }

        log.info("[VALIDATE_QUIZ] Quiz validation passed")
        return {
            "validation_passed": True,
            "validation_feedback": "",
        }

    return validate_quiz


def _build_persist_quiz_node(course_client: CourseServiceClient):
    """Factory for the persist_quiz node."""

    async def persist_quiz(state: QuizState) -> dict:
        """Normalize generated quiz and persist to course-service."""
        generated = state.get("generated_quiz")
        course_id = state["course_id"]
        module_id = state["module_id"]
        user_id = state["user_id"]
        profile_id = state["profile_id"]
        request_data = {
            "passing_score": state.get("passing_score", 70),
            "time_limit_minutes": state.get("time_limit_minutes"),
            "max_attempts": state.get("max_attempts", 3),
        }

        log = logger.bind(course_id=course_id, module_id=module_id)
        log.info("[PERSIST_QUIZ] Starting quiz persistence")

        try:
            if not generated:
                log.error("[PERSIST_QUIZ] No quiz to persist")
                return {"error": "No quiz to persist"}

            # Build quiz payload using normalization logic
            log.info("[PERSIST_QUIZ] Building quiz payload")
            payload = _build_quiz_payload(generated, request_data)
            log.info(
                "[PERSIST_QUIZ] Payload built", num_questions=len(payload.get("questions", []))
            )

            # Save via HTTP to course-service
            log.info("[PERSIST_QUIZ] Saving quiz to course-service")
            result = await course_client.save_quiz(
                course_id, module_id, payload, user_id, profile_id
            )

            if result:
                log.info("[PERSIST_QUIZ] Quiz persisted successfully to course-service")
                return {"persisted": True}
            else:
                log.warning("[PERSIST_QUIZ] Failed to save quiz to course-service")
                return {"error": "Failed to save to course-service"}

        except Exception as e:
            log.exception("[PERSIST_QUIZ] Error persisting quiz", error=str(e))
            return {"error": str(e)}

    return persist_quiz


# ── Summary Nodes ──────────────────────────────────────────────────


def _build_generate_summary_node(openai_client: OpenAIClient):
    """Factory for the generate_summary node."""

    async def generate_summary(state: SummaryState) -> dict:
        """Generate summary using OpenAI, with optional validation feedback appended."""
        combined_text = state["combined_text"]
        include_glossary = state.get("include_glossary", True)
        include_key_points = state.get("include_key_points", True)
        include_learning_objectives = state.get("include_learning_objectives", True)
        max_length_words = state.get("max_length_words")
        tone = state.get("tone")
        language = state.get("language", "en")
        validation_feedback = state.get("validation_feedback", "")
        retry_count = state.get("retry_count", 0)

        log = logger.bind(
            course_id=state["course_id"],
            module_id=state["module_id"],
            retry_count=retry_count,
        )

        if retry_count > 0:
            log.info("[GENERATE_SUMMARY] Retrying summary generation", attempt=retry_count + 1)
        else:
            log.info(
                "[GENERATE_SUMMARY] Starting initial summary generation",
                tone=tone,
                language=language,
            )

        # If retrying, append feedback to the prompt
        context_text = combined_text
        if validation_feedback and retry_count > 0:
            log.info(
                "[GENERATE_SUMMARY] Appending validation feedback to prompt for self-correction",
                num_issues=len(validation_feedback.split("- ")),
            )
            context_text = (
                f"{combined_text}\n\n"
                f"## Feedback from previous attempt (please fix):\n{validation_feedback}"
            )

        try:
            log.info("[GENERATE_SUMMARY] Calling OpenAI.generate_summary()")
            generated = await openai_client.generate_summary(
                context_text,
                include_glossary=include_glossary,
                include_key_points=include_key_points,
                include_learning_objectives=include_learning_objectives,
                max_length_words=max_length_words,
                tone=tone,
                language=language,
            )

            log.info("[GENERATE_SUMMARY] Summary generated successfully", title=generated.title)
            return {
                "generated_summary": generated,
                "validation_passed": False,  # Will be set by validate node
                "validation_feedback": "",
            }

        except Exception as e:
            log.exception("[GENERATE_SUMMARY] Error generating summary", error=str(e))
            return {"error": str(e)}

    return generate_summary


def _build_validate_summary_node():
    """Factory for the validate_summary node."""

    async def validate_summary(state: SummaryState) -> dict:
        """Validate generated summary structure and content."""
        generated = state.get("generated_summary")
        max_length_words = state.get("max_length_words")
        include_key_points = state.get("include_key_points", True)
        include_learning_objectives = state.get("include_learning_objectives", True)
        include_glossary = state.get("include_glossary", True)
        retry_count = state.get("retry_count", 0)

        log = logger.bind(
            course_id=state["course_id"],
            module_id=state["module_id"],
            retry_count=retry_count,
        )

        log.info("[VALIDATE_SUMMARY] Starting summary validation")

        issues = []

        if not generated:
            log.error("[VALIDATE_SUMMARY] No summary generated")
            return {
                "validation_passed": False,
                "validation_feedback": "No summary generated",
            }

        # 1. Check title
        if not generated.title or not generated.title.strip():
            issues.append("Missing or empty title")

        # 2. Check summary text
        if not generated.content.summary_text or len(generated.content.summary_text.strip()) < 50:
            issues.append("Summary text is too short (minimum 50 characters)")

        # 3. Check optional fields based on request
        if include_key_points and not generated.content.key_points:
            issues.append("include_key_points was True but key_points are empty")

        if include_learning_objectives and not generated.content.learning_objectives:
            issues.append("include_learning_objectives was True but learning_objectives are empty")

        if include_glossary and not generated.content.glossary:
            issues.append("include_glossary was True but glossary terms are empty")

        # 4. Check difficulty assessment
        if not generated.content.difficulty_assessment:
            issues.append("Missing difficulty_assessment")

        # 5. Check word count (with 20% tolerance)
        if max_length_words:
            summary_word_count = len(generated.content.summary_text.split())
            max_allowed = int(max_length_words * 1.2)
            if summary_word_count > max_allowed:
                issues.append(
                    f"Summary word count ({summary_word_count}) exceeds limit "
                    f"({max_length_words}, tolerance {max_allowed})"
                )

        if issues:
            feedback = "Please fix the following issues:\n" + "\n".join(
                f"- {issue}" for issue in issues
            )
            log.warning(
                "[VALIDATE_SUMMARY] Validation failed", num_issues=len(issues), issues=issues
            )
            return {
                "validation_passed": False,
                "validation_feedback": feedback,
            }

        log.info("[VALIDATE_SUMMARY] Summary validation passed")
        return {
            "validation_passed": True,
            "validation_feedback": "",
        }

    return validate_summary


def _build_persist_summary_node(course_client: CourseServiceClient):
    """Factory for the persist_summary node."""

    async def persist_summary(state: SummaryState) -> dict:
        """Build payload and persist summary to course-service."""
        generated = state.get("generated_summary")
        course_id = state["course_id"]
        module_id = state["module_id"]
        user_id = state["user_id"]
        profile_id = state["profile_id"]

        log = logger.bind(course_id=course_id, module_id=module_id)
        log.info("[PERSIST_SUMMARY] Starting summary persistence")

        try:
            if not generated:
                log.error("[PERSIST_SUMMARY] No summary to persist")
                return {"error": "No summary to persist"}

            # Build persistence payload
            log.info("[PERSIST_SUMMARY] Building summary payload")
            payload = {
                "title": generated.title,
                "content": {
                    "summary_text": generated.content.summary_text,
                    "key_points": generated.content.key_points,
                    "learning_objectives": generated.content.learning_objectives,
                    "glossary": [
                        {"term": g.term, "definition": g.definition}
                        for g in generated.content.glossary
                    ],
                    "difficulty_assessment": (
                        {
                            "level": generated.content.difficulty_assessment.level,
                            "estimated_read_minutes": generated.content.difficulty_assessment.estimated_read_minutes,
                        }
                        if generated.content.difficulty_assessment
                        else None
                    ),
                },
                "is_published": False,
            }
            log.info(
                "[PERSIST_SUMMARY] Payload built",
                title=payload["title"],
                summary_length=len(payload["content"]["summary_text"]),
            )

            # Save via HTTP to course-service
            log.info("[PERSIST_SUMMARY] Saving summary to course-service")
            result = await course_client.save_summary(
                course_id, module_id, payload, user_id, profile_id
            )

            if result:
                log.info("[PERSIST_SUMMARY] Summary persisted successfully to course-service")
                return {"persisted": True}
            else:
                log.warning("[PERSIST_SUMMARY] Failed to save summary to course-service")
                return {"error": "Failed to save to course-service"}

        except Exception as e:
            log.exception("[PERSIST_SUMMARY] Error persisting summary", error=str(e))
            return {"error": str(e)}

    return persist_summary


# ── Conditional Edge Routers ──────────────────────────────────────


def _quiz_validation_router(state: QuizState) -> str:
    """Route after quiz validation: retry or proceed."""
    log = logger.bind(course_id=state.get("course_id"), module_id=state.get("module_id"))

    if state.get("validation_passed", False):
        log.info("[ROUTER_QUIZ] Validation passed -> routing to persist_quiz")
        return "persist_quiz"

    current_retry = state.get("retry_count", 0)
    if current_retry < MAX_RETRIES:
        state["retry_count"] = current_retry + 1
        log.info(
            "[ROUTER_QUIZ] Validation failed -> routing back to generate_quiz for retry",
            retry_attempt=state["retry_count"],
        )
        return "generate_quiz"

    log.warning("[ROUTER_QUIZ] Retries exhausted -> routing to persist_quiz")
    return "persist_quiz"


def _summary_validation_router(state: SummaryState) -> str:
    """Route after summary validation: retry or proceed."""
    log = logger.bind(course_id=state.get("course_id"), module_id=state.get("module_id"))

    if state.get("validation_passed", False):
        log.info("[ROUTER_SUMMARY] Validation passed -> routing to persist_summary")
        return "persist_summary"

    current_retry = state.get("retry_count", 0)
    if current_retry < MAX_RETRIES:
        state["retry_count"] = current_retry + 1
        log.info(
            "[ROUTER_SUMMARY] Validation failed -> routing back to generate_summary for retry",
            retry_attempt=state["retry_count"],
        )
        return "generate_summary"

    log.warning("[ROUTER_SUMMARY] Retries exhausted -> routing to persist_summary")
    return "persist_summary"


# ── Helper Functions for Normalization ────────────────────────────


def _build_quiz_payload(generated: GeneratedQuiz, request_data: dict) -> dict[str, Any]:
    """Build quiz persistence payload from generated quiz."""
    questions: list[dict[str, Any]] = []
    for index, question in enumerate(generated.questions, start=1):
        normalized = _normalize_generated_question(question, index)
        if normalized is not None:
            questions.append(normalized)

    if not questions:
        raise ValueError("No valid quiz questions generated from AI response")

    title = (generated.title or "Module Quiz").strip()[:300] or "Module Quiz"
    description = generated.description.strip() if generated.description else None

    return {
        "title": title,
        "description": description,
        "settings": {
            "passing_score": request_data.get("passing_score", 70),
            "time_limit_minutes": request_data.get("time_limit_minutes"),
            "max_attempts": request_data.get("max_attempts", 3),
            "shuffle_questions": True,
            "shuffle_options": True,
            "show_correct_answers_after": "completion",
        },
        "questions": questions,
        "is_published": False,
    }


def _normalize_generated_question(
    question: GeneratedQuizQuestion, index: int
) -> dict[str, Any] | None:
    """Normalize a single generated quiz question."""
    question_type = question.question_type
    question_text = (question.question_text or "").strip() or f"Question {index}"
    explanation = question.explanation.strip() if question.explanation else None
    hint = question.hint.strip() if question.hint else None

    if question_type == "short_answer":
        correct_answers = [
            answer.strip()
            for answer in (question.correct_answers or [])
            if isinstance(answer, str) and answer.strip()
        ]
        if not correct_answers:
            logger.warning("Skipping invalid short_answer question with no correct_answers")
            return None

        return {
            "order": index,
            "question_text": question_text,
            "question_type": "short_answer",
            "options": None,
            "correct_answers": correct_answers,
            "explanation": explanation,
            "hint": hint,
        }

    # Process options for choice-based questions
    options = []
    for option in question.options or []:
        option_text = (option.text or "").strip()
        if not option_text:
            continue
        options.append(
            {
                "option_id": (option.option_id or "").strip(),
                "text": option_text,
                "is_correct": bool(option.is_correct),
            }
        )

    if question_type == "true_false":
        true_is_correct = True
        for option in options:
            option_id = option["option_id"].lower()
            option_text = option["text"].strip().lower()
            if option_id == "opt_false" or option_text in {"false", "no"}:
                if option["is_correct"]:
                    true_is_correct = False
                    break
            if option_id == "opt_true" or option_text in {"true", "yes"}:
                if option["is_correct"]:
                    true_is_correct = True
                    break

        normalized_options = [
            {"option_id": "opt_true", "text": "True", "is_correct": true_is_correct},
            {"option_id": "opt_false", "text": "False", "is_correct": not true_is_correct},
        ]
        return {
            "order": index,
            "question_text": question_text,
            "question_type": "true_false",
            "options": normalized_options,
            "correct_answers": None,
            "explanation": explanation,
            "hint": hint,
        }

    if len(options) < 2:
        logger.warning(
            "Skipping invalid objective question with insufficient options",
            question_type=question_type,
        )
        return None

    normalized_options = []
    for option_index, option in enumerate(options):
        letter = chr(ord("a") + option_index)
        normalized_options.append(
            {
                "option_id": f"opt_{letter}",
                "text": option["text"],
                "is_correct": bool(option["is_correct"]),
            }
        )

    if question_type == "multiple_choice":
        first_correct_index = next(
            (i for i, option in enumerate(normalized_options) if option["is_correct"]),
            0,
        )
        for option_index, option in enumerate(normalized_options):
            option["is_correct"] = option_index == first_correct_index

    if question_type == "multiple_select" and not any(
        option["is_correct"] for option in normalized_options
    ):
        normalized_options[0]["is_correct"] = True

    return {
        "order": index,
        "question_text": question_text,
        "question_type": question_type,
        "options": normalized_options,
        "correct_answers": None,
        "explanation": explanation,
        "hint": hint,
    }


# ── Graph Builders ─────────────────────────────────────────────────


def build_quiz_graph(
    openai_client: OpenAIClient,
    course_client: CourseServiceClient,
    content_extractor: ContentExtractor,
) -> CompiledStateGraph:
    """Build and compile the quiz generation LangGraph.

    Flow:
      START → extract_content → generate_quiz → validate_quiz ⇄ persist_quiz → END

    Args:
        openai_client: OpenAI client for quiz generation.
        course_client: Course service client for persistence.
        content_extractor: Content extractor for module content.

    Returns:
        Compiled LangGraph StateGraph ready for invocation.
    """
    # Create node functions with injected dependencies
    extract_node = _build_extract_content_node(content_extractor)
    generate_node = _build_generate_quiz_node(openai_client)
    validate_node = _build_validate_quiz_node()
    persist_node = _build_persist_quiz_node(course_client)

    # Build the graph
    graph = StateGraph(QuizState)

    # Add nodes
    graph.add_node("extract_content", extract_node)
    graph.add_node("generate_quiz", generate_node)
    graph.add_node("validate_quiz", validate_node)
    graph.add_node("persist_quiz", persist_node)

    # Define edges
    graph.add_edge(START, "extract_content")

    # After extraction, check for errors: if error, END; else generate_quiz
    def _extract_error_router(state: QuizState) -> str:
        return END if state.get("error") else "generate_quiz"

    graph.add_conditional_edges("extract_content", _extract_error_router)

    # Linear progression through generation and validation
    graph.add_edge("generate_quiz", "validate_quiz")

    # Conditional routing after validation: retry or persist
    graph.add_conditional_edges("validate_quiz", _quiz_validation_router)

    # Path to completion
    graph.add_edge("persist_quiz", END)

    # Compile
    return graph.compile()


def build_summary_graph(
    openai_client: OpenAIClient,
    course_client: CourseServiceClient,
    content_extractor: ContentExtractor,
) -> CompiledStateGraph:
    """Build and compile the summary generation LangGraph.

    Flow:
      START → extract_content → generate_summary → validate_summary ⇄ persist_summary → END

    Args:
        openai_client: OpenAI client for summary generation.
        course_client: Course service client for persistence.
        content_extractor: Content extractor for module content.

    Returns:
        Compiled LangGraph StateGraph ready for invocation.
    """
    # Create node functions with injected dependencies
    extract_node = _build_extract_content_node(content_extractor)
    generate_node = _build_generate_summary_node(openai_client)
    validate_node = _build_validate_summary_node()
    persist_node = _build_persist_summary_node(course_client)

    # Build the graph
    graph = StateGraph(SummaryState)

    # Add nodes
    graph.add_node("extract_content", extract_node)
    graph.add_node("generate_summary", generate_node)
    graph.add_node("validate_summary", validate_node)
    graph.add_node("persist_summary", persist_node)

    # Define edges
    graph.add_edge(START, "extract_content")

    # After extraction, check for errors: if error, END; else generate_summary
    def _extract_error_router(state: SummaryState) -> str:
        return END if state.get("error") else "generate_summary"

    graph.add_conditional_edges("extract_content", _extract_error_router)

    # Linear progression through generation and validation
    graph.add_edge("generate_summary", "validate_summary")

    # Conditional routing after validation: retry or persist
    graph.add_conditional_edges("validate_summary", _summary_validation_router)

    # Path to completion
    graph.add_edge("persist_summary", END)

    # Compile
    return graph.compile()
