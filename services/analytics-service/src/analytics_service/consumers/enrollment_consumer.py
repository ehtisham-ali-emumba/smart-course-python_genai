from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from shared.kafka.topics import Topics

from analytics_service.consumers.base_consumer import BaseAnalyticsConsumer, Repos


class EnrollmentEventConsumer(BaseAnalyticsConsumer):
    def __init__(self, session_factory, group_id: str, bootstrap_servers: str):
        super().__init__(
            session_factory=session_factory,
            group_id=group_id,
            bootstrap_servers=bootstrap_servers,
            topic=Topics.ENROLLMENT.value,
        )

    async def handle_event(self, envelope, payload: dict[str, Any], repos: Repos) -> None:
        if envelope.event_type == "enrollment.created":
            course_id = UUID(payload["course_id"])
            student_id = UUID(payload["student_id"])
            instructor_id_raw = payload.get("instructor_id")

            course = await repos.course.get_or_create(course_id)
            course.total_enrollments += 1
            course.active_enrollments += 1
            course.last_enrollment_at = datetime.now(timezone.utc)

            student = await repos.student.get_or_create(student_id)
            student.total_enrollments += 1
            student.active_enrollments += 1
            student.last_active_at = datetime.now(timezone.utc)

            if instructor_id_raw:
                instructor = await repos.instructor.get_or_create(UUID(instructor_id_raw))
                instructor.total_enrollments += 1

            daily_platform = await repos.enrollment_daily.get_or_create(
                datetime.now(timezone.utc).date(), None
            )
            daily_platform.new_enrollments += 1
            daily_course = await repos.enrollment_daily.get_or_create(
                datetime.now(timezone.utc).date(), course_id
            )
            daily_course.new_enrollments += 1

        elif envelope.event_type == "enrollment.completed":
            course_id = UUID(payload["course_id"])
            student_id = UUID(payload["student_id"])
            instructor_id_raw = payload.get("instructor_id")

            course = await repos.course.get_or_create(course_id)
            course.active_enrollments = max(0, course.active_enrollments - 1)
            course.completed_enrollments += 1
            if course.total_enrollments > 0:
                course.completion_rate = Decimal(
                    (course.completed_enrollments * 100) / course.total_enrollments
                ).quantize(Decimal("0.01"))

            student = await repos.student.get_or_create(student_id)
            student.active_enrollments = max(0, student.active_enrollments - 1)
            student.completed_courses += 1
            student.last_active_at = datetime.now(timezone.utc)

            if instructor_id_raw:
                instructor = await repos.instructor.get_or_create(UUID(instructor_id_raw))
                instructor.total_completions += 1

            now_date = datetime.now(timezone.utc).date()
            daily_platform = await repos.enrollment_daily.get_or_create(now_date, None)
            daily_platform.new_completions += 1
            daily_course = await repos.enrollment_daily.get_or_create(now_date, course_id)
            daily_course.new_completions += 1

        elif envelope.event_type == "enrollment.dropped":
            course_id = UUID(payload["course_id"])
            student_id = UUID(payload["student_id"])

            course = await repos.course.get_or_create(course_id)
            course.active_enrollments = max(0, course.active_enrollments - 1)
            course.dropped_enrollments += 1

            student = await repos.student.get_or_create(student_id)
            student.active_enrollments = max(0, student.active_enrollments - 1)
            student.dropped_courses += 1
            student.last_active_at = datetime.now(timezone.utc)

            now_date = datetime.now(timezone.utc).date()
            daily_platform = await repos.enrollment_daily.get_or_create(now_date, None)
            daily_platform.new_drops += 1
            daily_course = await repos.enrollment_daily.get_or_create(now_date, course_id)
            daily_course.new_drops += 1
