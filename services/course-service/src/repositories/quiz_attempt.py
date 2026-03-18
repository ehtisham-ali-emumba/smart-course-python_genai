import uuid as _uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.quiz_attempt import QuizAttempt
from models.user_answer import UserAnswer


class QuizAttemptRepository:
    """Repository for quiz_attempts and user_answers writes/reads."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(
        self,
        attempt_id: _uuid.UUID,
        *,
        include_answers: bool = False,
    ) -> QuizAttempt | None:
        stmt = select(QuizAttempt).where(QuizAttempt.id == attempt_id)
        if include_answers:
            stmt = stmt.options(selectinload(QuizAttempt.user_answers))

        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_by_enrollment_and_module(
        self,
        enrollment_id: _uuid.UUID,
        module_id: str,
        *,
        include_answers: bool = False,
    ) -> QuizAttempt | None:
        stmt = select(QuizAttempt).where(
            QuizAttempt.enrollment_id == enrollment_id,
            QuizAttempt.module_id == module_id,
            QuizAttempt.attempt_number == 1,
        )
        if include_answers:
            stmt = stmt.options(selectinload(QuizAttempt.user_answers))

        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def create_attempt(
        self,
        enrollment_id: _uuid.UUID,
        module_id: str,
        *,
        attempt_number: int = 1,
    ) -> QuizAttempt:
        attempt = QuizAttempt(
            enrollment_id=enrollment_id,
            module_id=module_id,
            attempt_number=attempt_number,
            status="in_progress",
        )
        self.db.add(attempt)
        await self.db.flush()
        return attempt

    async def add_user_answers(self, answers: list[UserAnswer]) -> None:
        self.db.add_all(answers)
        await self.db.flush()

    async def delete_attempt(self, attempt: QuizAttempt) -> None:
        await self.db.delete(attempt)
        await self.db.flush()
