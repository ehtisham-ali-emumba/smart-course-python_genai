from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from shared.kafka.topics import Topics

from analytics_service.consumers.base_consumer import BaseAnalyticsConsumer, Repos


class ProgressEventConsumer(BaseAnalyticsConsumer):
    def __init__(self, session_factory, group_id: str, bootstrap_servers: str):
        super().__init__(
            session_factory=session_factory,
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            topic=Topics.PROGRESS.value,
        )

    async def handle_event(self, envelope, payload: dict[str, Any], repos: Repos) -> None:
        if envelope.event_type == "progress.updated":
            course_id = UUID(payload["course_id"])
            student_id = UUID(payload["user_id"])
            progress = Decimal(str(payload.get("progress_percentage", 0))).quantize(
                Decimal("0.01")
            )

            course = await repos.course.get_or_create(course_id)
            course.avg_progress_percentage = progress

            student = await repos.student.get_or_create(student_id)
            student.avg_progress = progress
            student.last_active_at = datetime.now(timezone.utc)

        elif envelope.event_type == "quiz.graded":
            course_id = UUID(payload["course_id"])
            student_id = UUID(payload["student_id"])
            score = Decimal(str(payload.get("score", 0))).quantize(Decimal("0.01"))

            course = await repos.course.get_or_create(course_id)
            if course.avg_quiz_score is None:
                course.avg_quiz_score = score
            else:
                attempts = max(course.total_quiz_attempts, 1)
                course.avg_quiz_score = Decimal(
                    ((course.avg_quiz_score * attempts) + score) / (attempts + 1)
                ).quantize(Decimal("0.01"))
            course.total_quiz_attempts += 1

            student = await repos.student.get_or_create(student_id)
            student.avg_quiz_score = score
