"""
Alembic migration for quiz_attempts and user_answers tables
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "9f31b6a2d7c1"
down_revision = "5806173c49fb"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("enrollment_id", sa.Integer, nullable=False),
        sa.Column("module_id", sa.String(50), nullable=False),
        sa.Column("attempt_number", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="in_progress"),
        sa.Column("score", sa.Numeric(5, 2)),
        sa.Column("passed", sa.Boolean),
        sa.Column("time_spent_seconds", sa.Integer),
        sa.Column("started_at", sa.TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("submitted_at", sa.TIMESTAMP),
        sa.Column("graded_at", sa.TIMESTAMP),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "user_id", "enrollment_id", "module_id", "attempt_number", name="uq_quiz_attempts"
        ),
        sa.ForeignKeyConstraint(["enrollment_id"], ["enrollments.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_quiz_attempts_user_id", "quiz_attempts", ["user_id"])
    op.create_index("idx_quiz_attempts_enrollment_id", "quiz_attempts", ["enrollment_id"])
    op.create_index("idx_quiz_attempts_module_id", "quiz_attempts", ["module_id"])
    op.create_index("idx_quiz_attempts_status", "quiz_attempts", ["status"])

    op.create_table(
        "user_answers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("quiz_attempt_id", sa.Integer, nullable=False),
        sa.Column("user_id", sa.Integer, nullable=False),
        sa.Column("question_id", sa.String(50), nullable=False),
        sa.Column("question_type", sa.String(20), nullable=False),
        sa.Column("user_response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_correct", sa.Boolean),
        sa.Column("time_spent_seconds", sa.Integer),
        sa.Column("answered_at", sa.TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP, server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["quiz_attempt_id"], ["quiz_attempts.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_user_answers_attempt_id", "user_answers", ["quiz_attempt_id"])
    op.create_index("idx_user_answers_user_id", "user_answers", ["user_id"])
    op.create_index("idx_user_answers_question_id", "user_answers", ["question_id"])
    op.create_index(
        "idx_user_answers_response", "user_answers", ["user_response"], postgresql_using="gin"
    )


def downgrade():
    op.drop_index("idx_user_answers_response", table_name="user_answers")
    op.drop_index("idx_user_answers_question_id", table_name="user_answers")
    op.drop_index("idx_user_answers_user_id", table_name="user_answers")
    op.drop_index("idx_user_answers_attempt_id", table_name="user_answers")
    op.drop_table("user_answers")
    op.drop_index("idx_quiz_attempts_status", table_name="quiz_attempts")
    op.drop_index("idx_quiz_attempts_module_id", table_name="quiz_attempts")
    op.drop_index("idx_quiz_attempts_enrollment_id", table_name="quiz_attempts")
    op.drop_index("idx_quiz_attempts_user_id", table_name="quiz_attempts")
    op.drop_table("quiz_attempts")
