from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
import uuid as _uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from models.progress import Progress
from models.quiz_attempt import QuizAttempt
from models.user_answer import UserAnswer
from repositories.enrollment import EnrollmentRepository
from repositories.module_quiz import ModuleQuizRepository
from repositories.quiz_attempt import QuizAttemptRepository
from schemas.quiz_attempt import QuizSubmitRequest


class QuizAttemptService:
    """Business logic for student quiz attempts and grading."""

    def __init__(self, pg_db: AsyncSession, mongo_db: Any):
        self.pg_db = pg_db
        self.enrollment_repo = EnrollmentRepository(pg_db)
        self.quiz_repo = ModuleQuizRepository(mongo_db)
        self.attempt_repo = QuizAttemptRepository(pg_db)

    async def start_attempt(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        student_id: _uuid.UUID,
    ) -> tuple[dict[str, Any], bool]:
        enrollment = await self._get_enrollment(course_id, student_id)
        quiz_doc = await self._get_published_quiz(course_id, module_id)

        existing = await self.attempt_repo.get_by_enrollment_and_module(enrollment.id, module_id)
        if existing and existing.status == "in_progress":
            return self._build_start_response(existing.id, existing.started_at, quiz_doc), False

        if existing and existing.status == "graded":
            if not self._is_quiz_outdated(quiz_doc, existing):
                raise FileExistsError("Quiz already submitted")

        try:
            if existing is not None:
                await self.attempt_repo.delete_attempt(existing)

            attempt = await self.attempt_repo.create_attempt(
                enrollment.id, module_id, attempt_number=1
            )
            await self.pg_db.commit()
            await self.pg_db.refresh(attempt)
        except Exception:
            await self.pg_db.rollback()
            raise

        return self._build_start_response(attempt.id, attempt.started_at, quiz_doc), True

    async def submit_attempt(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        attempt_id: _uuid.UUID,
        payload: QuizSubmitRequest,
        student_id: _uuid.UUID,
    ) -> dict[str, Any]:
        enrollment = await self._get_enrollment(course_id, student_id)
        attempt = await self.attempt_repo.get_by_id(attempt_id)
        if not attempt:
            raise LookupError("Quiz attempt not found")
        if attempt.enrollment_id != enrollment.id or attempt.module_id != module_id:
            raise PermissionError("Quiz attempt does not belong to this student")
        if attempt.status != "in_progress":
            raise FileExistsError("Quiz attempt already submitted")

        quiz_doc = await self._get_published_quiz(course_id, module_id)
        self._validate_time_limit(attempt.started_at, quiz_doc)

        questions = quiz_doc.get("questions", [])
        question_map = {question["question_id"]: question for question in questions}
        submissions = self._validate_submission(payload, question_map)

        correct_count = 0
        graded_answers: list[UserAnswer] = []
        visible_results: list[dict[str, Any]] = []
        show_setting = quiz_doc.get("settings", {}).get("show_correct_answers_after", "completion")

        for answer in submissions:
            question = question_map[answer.question_id]
            is_correct = self._grade_answer(question, answer.response)
            if is_correct:
                correct_count += 1

            graded_answers.append(
                UserAnswer(
                    quiz_attempt_id=attempt.id,
                    question_id=answer.question_id,
                    question_type=question["question_type"],
                    user_response=answer.response,
                    is_correct=is_correct,
                    time_spent_seconds=answer.time_spent_seconds,
                )
            )
            visible_results.append(
                self._build_answer_result(
                    question=question,
                    user_response=answer.response,
                    is_correct=is_correct,
                    reveal=self._should_reveal_answers(show_setting, False),
                )
            )

        total_questions = len(questions)
        score = self._calculate_score(correct_count, total_questions)
        passed = score >= Decimal(str(quiz_doc.get("settings", {}).get("passing_score", 0)))
        submitted_at = datetime.utcnow()
        time_spent_seconds = payload.total_time_spent_seconds
        if time_spent_seconds is None:
            time_spent_seconds = max(int((submitted_at - attempt.started_at).total_seconds()), 0)

        reveal_answers = self._should_reveal_answers(show_setting, passed)
        if reveal_answers:
            visible_results = [
                self._build_answer_result(
                    question=question_map[result["question_id"]],
                    user_response=result["user_response"],
                    is_correct=bool(result["is_correct"]),
                    reveal=True,
                )
                for result in visible_results
            ]
        else:
            visible_results = [self._redact_answer_result(result) for result in visible_results]

        try:
            await self.attempt_repo.add_user_answers(graded_answers)

            attempt.status = "graded"
            attempt.score = score
            attempt.passed = passed
            attempt.time_spent_seconds = time_spent_seconds
            attempt.quiz_version = int(quiz_doc.get("authorship", {}).get("version") or 1)
            attempt.submitted_at = submitted_at
            attempt.graded_at = submitted_at

            await self._upsert_module_quiz_progress(enrollment.id, module_id)
            await self.pg_db.commit()
            await self.pg_db.refresh(attempt)
        except Exception:
            await self.pg_db.rollback()
            raise

        return {
            "attempt_id": attempt.id,
            "status": attempt.status,
            "score": attempt.score,
            "passed": attempt.passed,
            "total_questions": total_questions,
            "correct_answers": correct_count,
            "time_spent_seconds": attempt.time_spent_seconds,
            "submitted_at": attempt.submitted_at,
            "results": visible_results,
        }

    async def get_attempt_detail(
        self,
        course_id: _uuid.UUID,
        module_id: str,
        attempt_id: _uuid.UUID,
        student_id: _uuid.UUID,
    ) -> dict[str, Any]:
        enrollment = await self._get_enrollment(course_id, student_id, allow_completed=True)
        attempt = await self.attempt_repo.get_by_id(attempt_id, include_answers=True)
        if not attempt:
            raise LookupError("Quiz attempt not found")
        if attempt.enrollment_id != enrollment.id or attempt.module_id != module_id:
            raise PermissionError("Quiz attempt does not belong to this student")

        quiz_doc = await self.quiz_repo.get_by_course_module(course_id, module_id)
        question_map = {
            question["question_id"]: question for question in (quiz_doc or {}).get("questions", [])
        }

        quiz_outdated = self._is_quiz_outdated(quiz_doc or {}, attempt)

        show_setting = (
            (quiz_doc or {}).get("settings", {}).get("show_correct_answers_after", "completion")
        )
        reveal_answers = (
            attempt.status == "graded"
            and not quiz_outdated
            and self._should_reveal_answers(show_setting, bool(attempt.passed))
        )

        ordered_answers = sorted(
            attempt.user_answers,
            key=lambda item: (
                question_map.get(item.question_id, {}).get("order", 10**6),
                item.answered_at,
            ),
        )
        answer_details = [
            self._build_attempt_answer_detail(
                answer=answer,
                question=question_map.get(answer.question_id),
                reveal=reveal_answers,
            )
            for answer in ordered_answers
        ]

        correct_answers = None
        total_questions = None
        if attempt.status == "graded":
            total_questions = len(ordered_answers)
            correct_answers = sum(1 for answer in ordered_answers if answer.is_correct)

        return {
            "attempt_id": attempt.id,
            "status": attempt.status,
            "score": attempt.score,
            "passed": attempt.passed,
            "total_questions": total_questions,
            "correct_answers": correct_answers,
            "time_spent_seconds": attempt.time_spent_seconds,
            "started_at": attempt.started_at,
            "submitted_at": attempt.submitted_at,
            "quiz_outdated": quiz_outdated,
            "answers": answer_details,
        }

    async def _get_enrollment(
        self,
        course_id: _uuid.UUID,
        student_id: _uuid.UUID,
        *,
        allow_completed: bool = False,
    ):
        enrollment = await self.enrollment_repo.get_by_student_and_course(student_id, course_id)
        if not enrollment:
            raise LookupError("Enrollment not found")

        allowed_statuses = {"active"}
        if allow_completed:
            allowed_statuses.add("completed")

        if enrollment.status not in allowed_statuses:
            raise PermissionError("Enrollment is not active")
        return enrollment

    async def _get_published_quiz(self, course_id: _uuid.UUID, module_id: str) -> dict[str, Any]:
        quiz_doc = await self.quiz_repo.get_published_by_course_module(course_id, module_id)
        if not quiz_doc or not quiz_doc.get("is_active", True):
            raise LookupError("Quiz not found")
        return quiz_doc

    def _build_start_response(
        self,
        attempt_id: _uuid.UUID,
        started_at: datetime,
        quiz_doc: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "attempt_id": attempt_id,
            "started_at": started_at,
            "time_limit_minutes": quiz_doc.get("settings", {}).get("time_limit_minutes"),
            "questions": [
                self._sanitize_question(question) for question in quiz_doc.get("questions", [])
            ],
        }

    def _sanitize_question(self, question: dict[str, Any]) -> dict[str, Any]:
        return {
            "question_id": question["question_id"],
            "order": question.get("order", 0),
            "question_text": question["question_text"],
            "question_type": question["question_type"],
            "options": [
                {"option_id": option["option_id"], "text": option["text"]}
                for option in question.get("options", [])
            ]
            or None,
            "hint": question.get("hint"),
        }

    def _validate_time_limit(self, started_at: datetime, quiz_doc: dict[str, Any]) -> None:
        time_limit_minutes = quiz_doc.get("settings", {}).get("time_limit_minutes")
        if time_limit_minutes is None:
            return

        elapsed_seconds = int((datetime.utcnow() - started_at).total_seconds())
        if elapsed_seconds > int(time_limit_minutes) * 60:
            raise ValueError("Quiz time limit exceeded")

    def _validate_submission(
        self,
        payload: QuizSubmitRequest,
        question_map: dict[str, dict[str, Any]],
    ):
        if not question_map:
            raise LookupError("Quiz questions not found")

        submitted_ids = [answer.question_id for answer in payload.answers]
        expected_ids = list(question_map.keys())

        if len(submitted_ids) != len(set(submitted_ids)):
            raise ValueError("Duplicate answers are not allowed")
        if set(submitted_ids) != set(expected_ids):
            raise ValueError("All quiz questions must be answered exactly once")

        return payload.answers

    def _grade_answer(self, question: dict[str, Any], user_response: dict[str, Any]) -> bool:
        question_type = question["question_type"]

        if question_type in {"multiple_choice", "true_false"}:
            correct_option = next(
                (option for option in question.get("options", []) if option.get("is_correct")),
                None,
            )
            return user_response.get("selected_option_id") == (correct_option or {}).get(
                "option_id"
            )

        if question_type == "multiple_select":
            correct_ids = {
                option["option_id"]
                for option in question.get("options", [])
                if option.get("is_correct")
            }
            selected_ids = set(user_response.get("selected_option_ids", []))
            return selected_ids == correct_ids

        if question_type == "short_answer":
            user_text = str(user_response.get("text", "")).strip()
            case_sensitive = bool(question.get("case_sensitive", False))
            for answer in question.get("correct_answers", []):
                candidate = str(answer).strip()
                if case_sensitive and user_text == candidate:
                    return True
                if not case_sensitive and user_text.lower() == candidate.lower():
                    return True

        return False

    def _calculate_score(self, correct_count: int, total_questions: int) -> Decimal:
        if total_questions == 0:
            return Decimal("0.00")
        raw_score = (Decimal(correct_count) / Decimal(total_questions)) * Decimal("100")
        return raw_score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _is_quiz_outdated(
        quiz_doc: dict[str, Any],
        attempt: QuizAttempt,
    ) -> bool:
        """Check if quiz version has changed since the student submitted."""
        if attempt.status != "graded" or attempt.quiz_version is None:
            return False
        current_version = int(quiz_doc.get("authorship", {}).get("version") or 1)
        return attempt.quiz_version != current_version

    def _should_reveal_answers(self, show_setting: str, passed: bool) -> bool:
        if show_setting == "completion":
            return True
        if show_setting == "passing":
            return passed
        return False

    def _build_answer_result(
        self,
        *,
        question: dict[str, Any],
        user_response: dict[str, Any],
        is_correct: bool,
        reveal: bool,
    ) -> dict[str, Any]:
        result = {
            "question_id": question["question_id"],
            "is_correct": is_correct,
            "user_response": user_response,
            "correct_answer": None,
            "explanation": None,
        }
        if reveal:
            result["correct_answer"] = self._build_correct_answer(question)
            result["explanation"] = question.get("explanation")
        return result

    def _redact_answer_result(self, result: dict[str, Any]) -> dict[str, Any]:
        redacted = dict(result)
        redacted["correct_answer"] = None
        redacted["explanation"] = None
        return redacted

    def _build_correct_answer(self, question: dict[str, Any]) -> dict[str, Any] | None:
        question_type = question["question_type"]

        if question_type in {"multiple_choice", "true_false"}:
            correct_option = next(
                (option for option in question.get("options", []) if option.get("is_correct")),
                None,
            )
            if not correct_option:
                return None
            return {
                "option_id": correct_option["option_id"],
                "text": correct_option["text"],
            }

        if question_type == "multiple_select":
            correct_options = [
                option for option in question.get("options", []) if option.get("is_correct")
            ]
            return {
                "option_ids": [option["option_id"] for option in correct_options],
                "options": [
                    {"option_id": option["option_id"], "text": option["text"]}
                    for option in correct_options
                ],
            }

        if question_type == "short_answer":
            answers = question.get("correct_answers", [])
            if not answers:
                return None
            return {"text": answers[0]}

        return None

    def _build_attempt_answer_detail(
        self,
        *,
        answer: UserAnswer,
        question: dict[str, Any] | None,
        reveal: bool,
    ) -> dict[str, Any]:
        detail = {
            "question_id": answer.question_id,
            "question_type": answer.question_type,
            "user_response": answer.user_response,
            "is_correct": answer.is_correct,
            "time_spent_seconds": answer.time_spent_seconds,
            "correct_answer": None,
            "explanation": None,
        }
        if reveal and question is not None:
            detail["correct_answer"] = self._build_correct_answer(question)
            detail["explanation"] = question.get("explanation")
        return detail

    async def _upsert_module_quiz_progress(self, enrollment_id: _uuid.UUID, module_id: str) -> None:
        now = datetime.utcnow()
        stmt = (
            insert(Progress.__table__)
            .values(
                enrollment_id=enrollment_id,
                item_type="module_quiz",
                item_id=module_id,
                progress_percentage=Decimal("100.00"),
                completed_at=now,
                updated_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_progress_enrollment_item",
                set_={
                    "progress_percentage": Decimal("100.00"),
                    "completed_at": now,
                    "updated_at": now,
                },
            )
        )
        await self.pg_db.execute(stmt)
