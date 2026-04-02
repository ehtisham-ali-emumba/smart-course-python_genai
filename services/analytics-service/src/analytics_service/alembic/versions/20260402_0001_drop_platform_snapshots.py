"""drop platform_snapshots table

Revision ID: 20260402_0001
Revises: 20260401_0001
Create Date: 2026-04-02 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260402_0001"
down_revision: str | None = "20260401_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_platform_snapshots_snapshot_date", table_name="platform_snapshots")
    op.drop_table("platform_snapshots")


def downgrade() -> None:
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
