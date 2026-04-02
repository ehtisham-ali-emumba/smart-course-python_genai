import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from analytics_service.core.cache import delete_by_patterns
from analytics_service.core.redis import get_redis
from analytics_service.repositories import (
    AIUsageDailyRepository,
    CourseMetricsRepository,
    EnrollmentDailyRepository,
    InstructorMetricsRepository,
    PlatformRepository,
    ProcessedEventRepository,
    StudentMetricsRepository,
)
from shared.kafka.consumer import EventConsumer

logger = logging.getLogger(__name__)


class BaseAnalyticsConsumer:
    topic: str

    def __init__(
        self, session_factory: async_sessionmaker, group_id: str, bootstrap_servers: str, topic: str
    ):
        self.session_factory = session_factory
        self.topic = topic
        self.consumer = EventConsumer(
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            topics=[topic],
        )

    async def run(self) -> None:
        await self.consumer.start(handler=self.handle)

    async def stop(self) -> None:
        await self.consumer.consumer.stop()

    async def handle(self, topic: str, envelope) -> None:
        async with self.session_factory() as session:
            processed_repo = ProcessedEventRepository(session)
            marked = await processed_repo.mark_processed(
                event_id=envelope.event_id,
                topic=topic,
                event_type=envelope.event_type,
            )
            if not marked:
                return

            platform_repo = PlatformRepository(session)
            course_repo = CourseMetricsRepository(session)
            instructor_repo = InstructorMetricsRepository(session)
            student_repo = StudentMetricsRepository(session)
            enrollment_daily_repo = EnrollmentDailyRepository(session)
            ai_daily_repo = AIUsageDailyRepository(session)

            payload: dict[str, Any] = envelope.payload or {}
            now_date = datetime.now(timezone.utc).date()

            if envelope.event_type == "user.registered":
                role = payload.get("role")
                profile_id = payload.get("profile_id") or payload.get("user_id")
                snapshot = await platform_repo.get_or_create_today(now_date)
                if role == "instructor":
                    snapshot.total_instructors += 1
                    snapshot.new_instructors_today += 1
                    if profile_id:
                        await instructor_repo.get_or_create(UUID(profile_id))
                else:
                    snapshot.total_students += 1
                    snapshot.new_students_today += 1
                    if profile_id:
                        await student_repo.get_or_create(UUID(profile_id))

            if envelope.event_type == "course.published":
                course_id = UUID(payload["course_id"])
                instructor_id_raw = payload.get("instructor_id")
                snapshot = await platform_repo.get_or_create_today(now_date)
                snapshot.total_courses_published += 1

                course = await course_repo.get_or_create(course_id)
                course.title = payload.get("title", course.title)
                course.category = payload.get("category")
                course.published_at = datetime.now(timezone.utc)
                if instructor_id_raw:
                    instructor_id = UUID(instructor_id_raw)
                    course.instructor_id = instructor_id
                    inst = await instructor_repo.get_or_create(instructor_id)
                    inst.total_courses += 1
                    inst.published_courses += 1

            if envelope.event_type == "enrollment.created":
                course_id = UUID(payload["course_id"])
                student_id = UUID(payload["student_id"])
                instructor_id_raw = payload.get("instructor_id")

                course = await course_repo.get_or_create(course_id)
                course.total_enrollments += 1
                course.active_enrollments += 1
                course.last_enrollment_at = datetime.now(timezone.utc)

                student = await student_repo.get_or_create(student_id)
                student.total_enrollments += 1
                student.active_enrollments += 1
                student.last_active_at = datetime.now(timezone.utc)

                if instructor_id_raw:
                    instructor = await instructor_repo.get_or_create(UUID(instructor_id_raw))
                    instructor.total_enrollments += 1

                daily_platform = await enrollment_daily_repo.get_or_create(now_date, None)
                daily_platform.new_enrollments += 1
                daily_course = await enrollment_daily_repo.get_or_create(now_date, course_id)
                daily_course.new_enrollments += 1

                snapshot = await platform_repo.get_or_create_today(now_date)
                snapshot.total_enrollments += 1
                snapshot.new_enrollments_today += 1

            if envelope.event_type == "enrollment.completed":
                course_id = UUID(payload["course_id"])
                student_id = UUID(payload["student_id"])
                instructor_id_raw = payload.get("instructor_id")

                course = await course_repo.get_or_create(course_id)
                course.active_enrollments = max(0, course.active_enrollments - 1)
                course.completed_enrollments += 1
                if course.total_enrollments > 0:
                    course.completion_rate = Decimal(
                        (course.completed_enrollments * 100) / course.total_enrollments
                    ).quantize(Decimal("0.01"))

                student = await student_repo.get_or_create(student_id)
                student.active_enrollments = max(0, student.active_enrollments - 1)
                student.completed_courses += 1
                student.last_active_at = datetime.now(timezone.utc)

                if instructor_id_raw:
                    instructor = await instructor_repo.get_or_create(UUID(instructor_id_raw))
                    instructor.total_completions += 1

                daily_platform = await enrollment_daily_repo.get_or_create(now_date, None)
                daily_platform.new_completions += 1
                daily_course = await enrollment_daily_repo.get_or_create(now_date, course_id)
                daily_course.new_completions += 1

                snapshot = await platform_repo.get_or_create_today(now_date)
                snapshot.total_completions += 1
                snapshot.new_completions_today += 1

            if envelope.event_type == "enrollment.dropped":
                course_id = UUID(payload["course_id"])
                student_id = UUID(payload["student_id"])
                course = await course_repo.get_or_create(course_id)
                course.active_enrollments = max(0, course.active_enrollments - 1)
                course.dropped_enrollments += 1

                student = await student_repo.get_or_create(student_id)
                student.active_enrollments = max(0, student.active_enrollments - 1)
                student.dropped_courses += 1
                student.last_active_at = datetime.now(timezone.utc)

                daily_platform = await enrollment_daily_repo.get_or_create(now_date, None)
                daily_platform.new_drops += 1
                daily_course = await enrollment_daily_repo.get_or_create(now_date, course_id)
                daily_course.new_drops += 1

            if envelope.event_type == "progress.updated":
                course_id = UUID(payload["course_id"])
                student_id = UUID(payload["user_id"])
                progress = Decimal(str(payload.get("progress_percentage", 0))).quantize(
                    Decimal("0.01")
                )

                course = await course_repo.get_or_create(course_id)
                course.avg_progress_percentage = progress

                student = await student_repo.get_or_create(student_id)
                student.avg_progress = progress
                student.last_active_at = datetime.now(timezone.utc)

            if envelope.event_type == "quiz.graded":
                course_id = UUID(payload["course_id"])
                student_id = UUID(payload["student_id"])
                score = Decimal(str(payload.get("score", 0))).quantize(Decimal("0.01"))

                course = await course_repo.get_or_create(course_id)
                if course.avg_quiz_score is None:
                    course.avg_quiz_score = score
                else:
                    attempts = max(course.total_quiz_attempts, 1)
                    course.avg_quiz_score = Decimal(
                        ((course.avg_quiz_score * attempts) + score) / (attempts + 1)
                    ).quantize(Decimal("0.01"))
                course.total_quiz_attempts += 1

                student = await student_repo.get_or_create(student_id)
                student.avg_quiz_score = score

            if envelope.event_type == "certificate.issued":
                student_id = UUID(payload["student_id"])
                student = await student_repo.get_or_create(student_id)
                student.total_certificates += 1

                snapshot = await platform_repo.get_or_create_today(now_date)
                snapshot.total_certificates_issued += 1

            if envelope.event_type in {"ai.question.asked", "ai.content.generated"}:
                course_id_raw = payload.get("course_id")
                course_id = UUID(course_id_raw) if course_id_raw else None
                usage_platform = await ai_daily_repo.get_or_create(now_date, None)
                usage_course = (
                    await ai_daily_repo.get_or_create(now_date, course_id) if course_id else None
                )

                usage_platform.total_questions += 1
                if usage_course:
                    usage_course.total_questions += 1

                if envelope.event_type == "ai.question.asked":
                    usage_platform.tutor_questions += 1
                    if usage_course:
                        usage_course.tutor_questions += 1
                    if course_id:
                        course = await course_repo.get_or_create(course_id)
                        course.ai_questions_asked += 1

                    snapshot = await platform_repo.get_or_create_today(now_date)
                    snapshot.ai_questions_asked_today += 1
                else:
                    usage_platform.instructor_requests += 1
                    if usage_course:
                        usage_course.instructor_requests += 1

            await session.commit()

            await delete_by_patterns(
                get_redis(),
                [
                    "analytics:platform:*",
                    "analytics:courses:popular:*",
                    "analytics:course:*",
                    "analytics:instructor:*",
                    "analytics:student:*",
                ],
            )

            logger.info(
                "analytics_event_processed topic=%s event_type=%s",
                topic,
                envelope.event_type,
            )
