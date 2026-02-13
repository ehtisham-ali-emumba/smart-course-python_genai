"""add_progress_table_refactor_enrollment

Revision ID: a1b2c3d4e5f6
Revises: 8ada7fdc14d3
Create Date: 2026-02-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a1b2c3d4e5f6"
down_revision = "8ada7fdc14d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create progress table
    op.create_table(
        "progress",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("item_type", sa.String(length=20), nullable=False),
        sa.Column("item_id", sa.String(length=50), nullable=False),
        sa.Column(
            "completed_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_progress_id", "progress", ["id"], unique=False)
    op.create_index("ix_progress_user_id", "progress", ["user_id"], unique=False)
    op.create_index("ix_progress_course_id", "progress", ["course_id"], unique=False)
    op.create_index(
        "uq_progress_user_item",
        "progress",
        ["user_id", "item_type", "item_id"],
        unique=True,
    )
    op.create_index(
        "ix_progress_user_course",
        "progress",
        ["user_id", "course_id"],
        unique=False,
    )

    # Drop progress-related columns from enrollments
    op.drop_column("enrollments", "completed_modules")
    op.drop_column("enrollments", "completed_lessons")
    op.drop_column("enrollments", "total_modules")
    op.drop_column("enrollments", "total_lessons")
    op.drop_column("enrollments", "completion_percentage")
    op.drop_column("enrollments", "completed_quizzes")
    op.drop_column("enrollments", "quiz_scores")
    op.drop_column("enrollments", "current_module_id")
    op.drop_column("enrollments", "current_lesson_id")


def downgrade() -> None:
    # Restore enrollments columns
    op.add_column(
        "enrollments",
        sa.Column("current_lesson_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "enrollments",
        sa.Column("current_module_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "enrollments",
        sa.Column("quiz_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "enrollments",
        sa.Column(
            "completed_quizzes",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "enrollments",
        sa.Column(
            "completion_percentage",
            sa.Numeric(5, 2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "enrollments",
        sa.Column(
            "total_lessons",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "enrollments",
        sa.Column(
            "total_modules",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "enrollments",
        sa.Column(
            "completed_lessons",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "enrollments",
        sa.Column(
            "completed_modules",
            postgresql.ARRAY(sa.Integer()),
            nullable=False,
            server_default="{}",
        ),
    )

    # Drop progress table
    op.drop_index("ix_progress_user_course", table_name="progress")
    op.drop_index("uq_progress_user_item", table_name="progress")
    op.drop_index("ix_progress_course_id", table_name="progress")
    op.drop_index("ix_progress_user_id", table_name="progress")
    op.drop_index("ix_progress_id", table_name="progress")
    op.drop_table("progress")
