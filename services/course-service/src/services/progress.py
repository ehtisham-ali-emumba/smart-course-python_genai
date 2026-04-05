import uuid
import uuid as _uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, TYPE_CHECKING

from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.certificate import CertificateRepository
from repositories.course_content import CourseContentRepository
from repositories.enrollment import EnrollmentRepository
from repositories.progress import ProgressRepository
from schemas.progress import CourseProgressSummary, ModuleProgressDetail, ProgressCreate

if TYPE_CHECKING:
    from shared.kafka.producer import EventProducer


class ProgressService:
    """Business logic for progress tracking."""

    def __init__(
        self,
        pg_db: AsyncSession,
        mongo_db: AsyncIOMotorDatabase,
        event_producer: "EventProducer | None" = None,
    ):
        self.progress_repo = ProgressRepository(pg_db)
        self.enrollment_repo = EnrollmentRepository(pg_db)
        self.cert_repo = CertificateRepository(pg_db)
        self.content_repo = CourseContentRepository(mongo_db)
        self.pg_db = pg_db
        self._producer = event_producer

    # ── UPDATE PROGRESS ───────────────────────────────────────────

    async def update_progress(
        self,
        user_id: _uuid.UUID,
        data: ProgressCreate,
    ):
        """
        Create or update progress for a lesson/quiz/summary.

        Called every time a user interacts with a lesson (e.g., watches more
        of a video, re-opens a quiz, finishes reading). The frontend sends
        the current progress_percentage (0–100).
        """
        enrollment = await self.enrollment_repo.get_by_id(data.enrollment_id)
        if not enrollment:
            raise ValueError("Enrollment not found")
        if enrollment.student_id != user_id:
            raise ValueError("This enrollment does not belong to you")
        if enrollment.status not in ("active", "completed"):
            raise ValueError("Enrollment is not active")

        # Validate lesson item_id belongs to this course
        if data.item_type == "lesson":
            content = await self.content_repo.get_by_course_id(enrollment.course_id)
            if content:
                valid_lesson_ids = {
                    str(lesson.get("lesson_id"))
                    for module in content.get("modules", [])
                    if module.get("is_active", True)
                    for lesson in module.get("lessons", [])
                    if lesson.get("is_active", True)
                }
                if data.item_id not in valid_lesson_ids:
                    raise ValueError(f"lesson_id '{data.item_id}' does not exist in this course")

        progress = await self.progress_repo.upsert_progress(
            enrollment_id=data.enrollment_id,
            item_type=data.item_type,
            item_id=data.item_id,
            progress_percentage=float(data.progress_percentage),
        )

        if self._producer:
            from shared.schemas.events.progress import ProgressUpdatedPayload
            from shared.kafka.topics import Topics

            await self._producer.publish(
                Topics.PROGRESS,
                "progress.updated",
                ProgressUpdatedPayload(
                    user_id=user_id,
                    enrollment_id=data.enrollment_id,
                    course_id=enrollment.course_id,
                    item_type=data.item_type,
                    item_id=data.item_id,
                    progress_percentage=float(data.progress_percentage),
                ).model_dump(),
                key=str(user_id),
            )

        # Update enrollment timestamps
        update_data = {"last_accessed_at": datetime.utcnow()}
        if enrollment.started_at is None:
            update_data["started_at"] = datetime.utcnow()
        await self.enrollment_repo.update(enrollment.id, update_data)

        # Check if entire course is now 100%
        await self._check_auto_complete(enrollment.id, enrollment.course_id)

        return progress

    # ── GET PROGRESS ──────────────────────────────────────────────

    async def get_course_progress(
        self,
        user_id: _uuid.UUID,
        course_id: _uuid.UUID,
    ) -> CourseProgressSummary:
        """Get progress by course_id (convenience — looks up enrollment internally)."""
        enrollment = await self.enrollment_repo.get_by_student_and_course(user_id, course_id)
        if not enrollment:
            raise ValueError("User is not enrolled in this course")
        if enrollment.status not in ("active", "completed"):
            raise ValueError("Enrollment is not active (dropped or suspended)")

        return await self._build_progress_summary(enrollment.id, course_id)

    async def get_enrollment_progress(
        self,
        user_id: _uuid.UUID,
        enrollment_id: _uuid.UUID,
    ) -> CourseProgressSummary:
        """Get progress by enrollment_id (primary — use when you have enrollment_id)."""
        enrollment = await self.enrollment_repo.get_by_id(enrollment_id)
        if not enrollment:
            raise ValueError("Enrollment not found")
        if enrollment.student_id != user_id:
            raise ValueError("This enrollment does not belong to you")
        if enrollment.status not in ("active", "completed"):
            raise ValueError("Enrollment is not active (dropped or suspended)")

        return await self._build_progress_summary(enrollment.id, enrollment.course_id)

    # ── INTERNAL HELPERS ──────────────────────────────────────────

    async def _build_progress_summary(
        self,
        enrollment_id: _uuid.UUID,
        course_id: _uuid.UUID,
    ) -> CourseProgressSummary:
        """
        Build course progress by aggregating lesson-level progress records.

        For each module:
          1. Get all active lessons from MongoDB (the "total" count)
          2. Match against progress records from PostgreSQL
          3. Calculate module percentage = avg of all lesson percentages in that module
             (lessons with no progress row count as 0%)

        Course percentage = avg of ALL lesson percentages across ALL modules.
        """
        content = await self.content_repo.get_by_course_id(course_id)
        modules = content.get("modules", []) if content else []

        progress_records = await self.progress_repo.get_enrollment_progress(enrollment_id)
        # Build lookup: (item_type, item_id) → Progress record
        progress_map = {(p.item_type, p.item_id): p for p in progress_records}

        total_lessons_all = 0
        completed_lessons_all = 0
        all_lesson_percentages: List[float] = []
        module_progress_list: List[ModuleProgressDetail] = []

        for module in modules:
            if not module.get("is_active", True):
                continue

            module_lessons = self._get_active_lessons(module)
            module_total = len(module_lessons)
            module_completed = 0
            module_percentages: List[float] = []
            lesson_details: List[dict] = []

            for lesson_info in module_lessons:
                record = progress_map.get((lesson_info["type"], lesson_info["id"]))
                pct = float(record.progress_percentage) if record else 0.0
                is_done = record is not None and record.completed_at is not None

                if is_done:
                    module_completed += 1

                module_percentages.append(pct)
                lesson_details.append(
                    {
                        "item_type": lesson_info["type"],
                        "item_id": lesson_info["id"],
                        "title": lesson_info["title"],
                        "progress_percentage": pct,
                        "is_completed": is_done,
                    }
                )

            module_pct = Decimal("0.00")
            if module_percentages:
                avg = sum(module_percentages) / len(module_percentages)
                module_pct = Decimal(str(round(avg, 2)))

            module_progress_list.append(
                ModuleProgressDetail(
                    module_id=str(module.get("module_id")),
                    module_title=module.get("title", ""),
                    total_lessons=module_total,
                    completed_lessons=module_completed,
                    progress_percentage=module_pct,
                    lessons=lesson_details,
                    is_complete=(module_total > 0 and module_completed == module_total),
                )
            )

            total_lessons_all += module_total
            completed_lessons_all += module_completed
            all_lesson_percentages.extend(module_percentages)

        course_pct = Decimal("0.00")
        if all_lesson_percentages:
            avg = sum(all_lesson_percentages) / len(all_lesson_percentages)
            course_pct = Decimal(str(round(avg, 2)))

        cert = await self.cert_repo.get_by_enrollment(enrollment_id)
        has_certificate = cert is not None and not cert.is_revoked

        return CourseProgressSummary(
            course_id=course_id,
            enrollment_id=enrollment_id,
            total_lessons=total_lessons_all,
            completed_lessons=completed_lessons_all,
            progress_percentage=course_pct,
            module_progress=module_progress_list,
            has_certificate=has_certificate,
            is_complete=(total_lessons_all > 0 and completed_lessons_all == total_lessons_all),
        )

    @staticmethod
    def _get_active_lessons(module: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Extract all active trackable items from a module.
        Returns list of {type, id, title} dicts.
        """
        items = []
        for lesson in module.get("lessons", []):
            if not lesson.get("is_active", True):
                continue
            items.append(
                {
                    "type": "lesson",
                    "id": str(lesson.get("lesson_id")),
                    "title": lesson.get("title", ""),
                }
            )

        for quiz in module.get("quizzes", []):
            if not quiz.get("is_active", True):
                continue
            items.append(
                {
                    "type": "quiz",
                    "id": str(quiz.get("quiz_id")),
                    "title": quiz.get("title", ""),
                }
            )

        for summary in module.get("summaries", []):
            if not summary.get("is_active", True):
                continue
            items.append(
                {
                    "type": "summary",
                    "id": str(summary.get("summary_id")),
                    "title": summary.get("title", ""),
                }
            )

        return items

    async def _check_auto_complete(
        self,
        enrollment_id: _uuid.UUID,
        course_id: _uuid.UUID,
    ) -> None:
        """
        After each progress update, check if all lessons are at 100%.
        If yes → mark enrollment completed + auto-issue certificate.
        """
        enrollment = await self.enrollment_repo.get_by_id(enrollment_id)
        if not enrollment or enrollment.status == "completed":
            return

        content = await self.content_repo.get_by_course_id(course_id)
        if not content:
            return

        modules = content.get("modules", [])
        all_items = []
        for module in modules:
            if not module.get("is_active", True):
                continue
            all_items.extend(self._get_active_lessons(module))

        if not all_items:
            return

        progress_records = await self.progress_repo.get_enrollment_progress(enrollment_id)
        completed_set = {
            (p.item_type, p.item_id) for p in progress_records if p.completed_at is not None
        }

        all_done = all((item["type"], item["id"]) in completed_set for item in all_items)

        if not all_done:
            return

        # All items at 100% — mark enrollment completed
        if self._producer:
            from shared.schemas.events.progress import CourseCompletedPayload
            from shared.kafka.topics import Topics

            await self._producer.publish(
                Topics.PROGRESS,
                "progress.course_completed",
                CourseCompletedPayload(
                    user_id=enrollment.student_id,
                    enrollment_id=enrollment_id,
                    course_id=course_id,
                ).model_dump(),
                key=str(enrollment.student_id),
            )

        await self.enrollment_repo.update(
            enrollment_id,
            {
                "status": "completed",
                "completed_at": datetime.utcnow(),
            },
        )

        if self._producer:
            from shared.schemas.events.enrollment import EnrollmentCompletedPayload
            from shared.kafka.topics import Topics

            await self._producer.publish(
                Topics.ENROLLMENT,
                "enrollment.completed",
                EnrollmentCompletedPayload(
                    enrollment_id=enrollment_id,
                    student_id=enrollment.student_id,
                    course_id=course_id,
                    completed_at=datetime.utcnow().isoformat(),
                ).model_dump(),
                key=str(enrollment.student_id),
            )

        # Auto-issue certificate (only if one doesn't already exist)
        existing_cert = await self.cert_repo.get_by_enrollment(enrollment_id)
        if existing_cert:
            return

        cert_data = {
            "enrollment_id": enrollment_id,
            "certificate_number": f"SC-{uuid.uuid4().hex[:12].upper()}",
            "issue_date": date.today(),
            "verification_code": uuid.uuid4().hex[:8].upper(),
            "grade": None,
            "score_percentage": Decimal("100.00"),
            "issued_by_id": None,
        }
        cert = await self.cert_repo.create(cert_data)

        if self._producer:
            from shared.schemas.events.certificate import CertificateIssuedPayload
            from shared.kafka.topics import Topics

            await self._producer.publish(
                Topics.COURSE,
                "certificate.issued",
                CertificateIssuedPayload(
                    certificate_id=cert.id,
                    enrollment_id=enrollment_id,
                    student_id=enrollment.student_id,
                    course_id=course_id,
                    certificate_number=cert.certificate_number,
                    verification_code=cert.verification_code,
                ).model_dump(),
                key=str(enrollment_id),
            )
