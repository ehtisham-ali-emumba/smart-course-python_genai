"""init analytics schema

Revision ID: 20260401_0001
Revises:
Create Date: 2026-04-01 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260401_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("total_students", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_instructors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_courses_published", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_enrollments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_completions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_certificates_issued", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_students_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_instructors_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_enrollments_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_completions_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_courses_per_student", sa.Numeric(8, 2), nullable=False, server_default="0"),
        sa.Column("avg_completion_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("ai_questions_asked_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ai_questions_answered_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_platform_snapshots_snapshot_date", "platform_snapshots", ["snapshot_date"], unique=True
    )

    op.create_table(
        "course_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instructor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False, server_default="Untitled Course"),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("total_enrollments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_enrollments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_enrollments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dropped_enrollments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("avg_progress_percentage", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("avg_time_to_complete_hours", sa.Numeric(10, 2), nullable=True),
        sa.Column("avg_quiz_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("total_quiz_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ai_questions_asked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_enrollment_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_course_metrics_course_id", "course_metrics", ["course_id"], unique=True)
    op.create_index(
        "ix_course_metrics_instructor_id", "course_metrics", ["instructor_id"], unique=False
    )

    op.create_table(
        "instructor_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("instructor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("total_courses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_courses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_students", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_enrollments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_completions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_completion_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("avg_quiz_score", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_instructor_metrics_instructor_id", "instructor_metrics", ["instructor_id"], unique=True
    )

    op.create_table(
        "student_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("total_enrollments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_enrollments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_courses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dropped_courses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_progress", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("avg_quiz_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("total_certificates", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_student_metrics_student_id", "student_metrics", ["student_id"], unique=True)

    op.create_table(
        "enrollment_daily",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("new_enrollments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_completions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_drops", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("date", "course_id", name="uq_enrollment_daily_date_course"),
    )
    op.create_index("ix_enrollment_daily_date", "enrollment_daily", ["date"], unique=False)
    op.create_index(
        "ix_enrollment_daily_course_id", "enrollment_daily", ["course_id"], unique=False
    )

    op.create_table(
        "ai_usage_daily",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tutor_questions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("instructor_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_questions", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("date", "course_id", name="uq_ai_usage_daily_date_course"),
    )
    op.create_index("ix_ai_usage_daily_date", "ai_usage_daily", ["date"], unique=False)
    op.create_index("ix_ai_usage_daily_course_id", "ai_usage_daily", ["course_id"], unique=False)

    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.String(length=100), primary_key=True, nullable=False),
        sa.Column("topic", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column(
            "processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_processed_events_topic", "processed_events", ["topic"], unique=False)
    op.create_index(
        "ix_processed_events_event_type", "processed_events", ["event_type"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_processed_events_event_type", table_name="processed_events")
    op.drop_index("ix_processed_events_topic", table_name="processed_events")
    op.drop_table("processed_events")

    op.drop_index("ix_ai_usage_daily_course_id", table_name="ai_usage_daily")
    op.drop_index("ix_ai_usage_daily_date", table_name="ai_usage_daily")
    op.drop_table("ai_usage_daily")

    op.drop_index("ix_enrollment_daily_course_id", table_name="enrollment_daily")
    op.drop_index("ix_enrollment_daily_date", table_name="enrollment_daily")
    op.drop_table("enrollment_daily")

    op.drop_index("ix_student_metrics_student_id", table_name="student_metrics")
    op.drop_table("student_metrics")

    op.drop_index("ix_instructor_metrics_instructor_id", table_name="instructor_metrics")
    op.drop_table("instructor_metrics")

    op.drop_index("ix_course_metrics_instructor_id", table_name="course_metrics")
    op.drop_index("ix_course_metrics_course_id", table_name="course_metrics")
    op.drop_table("course_metrics")

    op.drop_index("ix_platform_snapshots_snapshot_date", table_name="platform_snapshots")
    op.drop_table("platform_snapshots")
