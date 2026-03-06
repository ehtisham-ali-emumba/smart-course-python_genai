"""OpenAI client for LLM-based content generation with structured outputs."""

from typing import Literal
from pydantic import BaseModel, Field
from openai import AsyncOpenAI
import structlog

from ai_service.config import settings

logger = structlog.get_logger(__name__)


# ── Summary Output Models ──────────────────────────────────────────


class GlossaryTerm(BaseModel):
    """A glossary term with definition."""

    term: str
    definition: str


class DifficultyAssessment(BaseModel):
    """Assessment of module difficulty level."""

    level: Literal["beginner", "intermediate", "advanced"]
    estimated_read_minutes: int = Field(..., ge=1)


class GeneratedSummaryContent(BaseModel):
    """Content body for a generated summary."""

    summary_text: str
    key_points: list[str] = Field(default_factory=list)
    learning_objectives: list[str] = Field(default_factory=list)
    glossary: list[GlossaryTerm] = Field(default_factory=list)
    difficulty_assessment: DifficultyAssessment | None = None


class GeneratedSummary(BaseModel):
    """Top-level structured output for summary generation."""

    title: str = Field(..., max_length=300)
    content: GeneratedSummaryContent


# ── Quiz Output Models ─────────────────────────────────────────────


class GeneratedQuizOption(BaseModel):
    """A quiz option/answer choice."""

    option_id: str
    text: str
    is_correct: bool


class GeneratedQuizQuestion(BaseModel):
    """A single quiz question."""

    order: int = Field(..., ge=1)
    question_text: str
    question_type: Literal["multiple_choice", "multiple_select", "true_false", "short_answer"]
    options: list[GeneratedQuizOption] | None = None
    correct_answers: list[str] | None = None
    explanation: str | None = None
    hint: str | None = None


class GeneratedQuiz(BaseModel):
    """Top-level structured output for quiz generation."""

    title: str = Field(..., max_length=300)
    description: str | None = None
    questions: list[GeneratedQuizQuestion]


# ── OpenAI Client ─────────────────────────────────────────────────


class OpenAIClient:
    """Client for generating content with OpenAI using structured outputs."""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_MODEL

    async def generate_summary(
        self,
        context_text: str,
        include_glossary: bool = True,
        include_key_points: bool = True,
        include_learning_objectives: bool = True,
        max_length_words: int | None = None,
        tone: str | None = None,
        language: str = "en",
    ) -> GeneratedSummary:
        """Generate a summary from lesson context using OpenAI.

        Args:
            context_text: Combined lesson text from CourseContentRepository
            include_glossary: Whether to include glossary terms
            include_key_points: Whether to include key points
            include_learning_objectives: Whether to include learning objectives
            max_length_words: Optional max word count for summary
            tone: Optional tone hint (e.g., 'formal', 'conversational')
            language: Language code (default 'en')

        Returns:
            GeneratedSummary with validated JSON structure

        Raises:
            openai.OpenAIError: On OpenAI API errors
        """
        # Build user prompt with all instructions
        prompt_parts = [
            "Generate a comprehensive module summary from the following lesson content:\n",
            context_text,
            "\n\n## Instructions:",
        ]

        if include_key_points:
            prompt_parts.append("- Include key points from the material")
        else:
            prompt_parts.append("- Do NOT include key points")

        if include_learning_objectives:
            prompt_parts.append("- Include learning objectives")
        else:
            prompt_parts.append("- Do NOT include learning objectives")

        if include_glossary:
            prompt_parts.append("- Include important glossary terms with definitions")
        else:
            prompt_parts.append("- Do NOT include glossary terms")

        if max_length_words:
            prompt_parts.append(f"- Keep the summary under {max_length_words} words")

        if tone:
            prompt_parts.append(f"- Use a {tone} tone")

        if language != "en":
            prompt_parts.append(f"- Write the summary in {language}")

        prompt_parts.append("- Provide a difficulty assessment (beginner/intermediate/advanced)")

        user_prompt = "\n".join(prompt_parts)

        system_prompt = (
            "You are an expert educational content summarizer. Generate a comprehensive "
            "module summary from the provided lesson content. Provide structured output "
            "suitable for an educational platform."
        )

        try:
            completion = await self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=GeneratedSummary,
            )

            result = completion.choices[0].message.parsed
            if result is None:
                raise ValueError("OpenAI returned no parsed content")
            return result

        except Exception as e:
            logger.error(
                "Failed to generate summary with OpenAI",
                error=str(e),
                model=self.model,
            )
            raise

    async def generate_quiz(
        self,
        context_text: str,
        num_questions: int = 5,
        difficulty: str | None = None,
        question_types: list[str] | None = None,
        language: str = "en",
    ) -> GeneratedQuiz:
        """Generate quiz questions from lesson context using OpenAI.

        Args:
            context_text: Combined lesson text from CourseContentRepository
            num_questions: Number of questions to generate
            difficulty: Target difficulty level (beginner/intermediate/advanced)
            question_types: List of question types to include (multiple_choice, true_false, etc.)
            language: Language code (default 'en')

        Returns:
            GeneratedQuiz with validated JSON structure

        Raises:
            openai.OpenAIError: On OpenAI API errors
        """
        if question_types is None:
            question_types = [
                "multiple_choice",
                "multiple_select",
                "true_false",
                "short_answer",
            ]

        # Build user prompt with all instructions
        prompt_parts = [
            "Generate quiz questions from the following lesson content:\n",
            context_text,
            f"\n\n## Instructions:",
            f"- Generate exactly {num_questions} questions",
            f"- Allowed question types: {', '.join(question_types)}",
        ]

        if difficulty:
            prompt_parts.append(f"- Difficulty level: {difficulty}")

        prompt_parts.extend(
            [
                "- For multiple_choice: exactly 4 options with IDs 'opt_a', 'opt_b', 'opt_c', 'opt_d', exactly 1 correct",
                "- For multiple_select: 4+ options, at least 1 correct",
                "- For true_false: exactly 2 options with IDs 'opt_true' and 'opt_false', exactly 1 correct",
                "- For short_answer: no options, provide correct_answers list instead",
                "- Include an explanation for each question",
                f"- Questions must test knowledge directly from the material",
            ]
        )

        if language != "en":
            prompt_parts.append(f"- Write questions in {language}")

        user_prompt = "\n".join(prompt_parts)

        system_prompt = (
            "You are an expert quiz creator for educational courses. Generate quiz questions "
            "based on the provided lesson content. Each question must be pedagogically sound "
            "and directly test knowledge from the material. Provide structured output with "
            "guaranteed valid JSON format."
        )

        try:
            completion = await self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=GeneratedQuiz,
            )

            result = completion.choices[0].message.parsed
            if result is None:
                raise ValueError("OpenAI returned no parsed content")
            return result

        except Exception as e:
            logger.error(
                "Failed to generate quiz with OpenAI",
                error=str(e),
                model=self.model,
            )
            raise

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts.

        Uses OpenAI's text-embedding-3-small model (1536 dimensions).
        Handles batching internally — OpenAI supports up to 2048 texts per request.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors (each is a list of 1536 floats).
            Order matches input texts.

        Raises:
            openai.OpenAIError: On API errors.
        """
        if not texts:
            return []

        try:
            response = await self.client.embeddings.create(
                model=settings.OPENAI_EMBEDDING_MODEL,
                input=texts,
            )

            # Sort by index to guarantee order matches input
            sorted_data = sorted(response.data, key=lambda x: x.index)
            return [item.embedding for item in sorted_data]

        except Exception as e:
            logger.error(
                "Failed to generate embeddings",
                error=str(e),
                model=settings.OPENAI_EMBEDDING_MODEL,
                num_texts=len(texts),
            )
            raise

    async def embed_query(self, query: str) -> list[float]:
        """Generate embedding for a single query string.

        Convenience method for search-time embedding (AI Tutor will use this).

        Args:
            query: The search query text.

        Returns:
            Embedding vector (list of 1536 floats).
        """
        result = await self.embed_texts([query])
        return result[0]

    async def chat_completion(
        self,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """Generate a chat completion response.

        Used by the AI Tutor for conversational responses.
        Unlike generate_summary/quiz, this returns free-text (not structured JSON).

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
                      Should include system, user, and optionally assistant messages.
            temperature: Sampling temperature (0.0-2.0). Higher = more creative.
                         Default 0.7 for balanced tutoring responses.
            max_tokens: Maximum tokens in the response. Default 1024.

        Returns:
            The assistant's response text.

        Raises:
            openai.OpenAIError: On API errors.
        """
        try:
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            response = completion.choices[0].message.content
            if response is None:
                raise ValueError("OpenAI returned empty response")
            return response

        except Exception as e:
            logger.error(
                "Failed to generate chat completion",
                error=str(e),
                model=self.model,
                num_messages=len(messages),
            )
            raise
