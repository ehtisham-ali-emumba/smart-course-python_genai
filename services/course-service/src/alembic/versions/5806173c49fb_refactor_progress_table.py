"""refactor_progress_table

Revision ID: 5806173c49fb
Revises: a1b2c3d4e5f6
Create Date: 2026-02-19

"""
from alembic import op
import sqlalchemy as sa

revision = "5806173c49fb"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Add new columns ────────────────────────────────────────

    # enrollment_id (nullable initially for data migration)
    op.add_column(
        "progress",
        sa.Column("enrollment_id", sa.Integer(), nullable=True),
    )

    # progress_percentage (default 0.00)
    op.add_column(
        "progress",
        sa.Column(
            "progress_percentage",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="0.00",
        ),
    )

    # updated_at
    op.add_column(
        "progress",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── 2. Backfill enrollment_id from enrollments table ──────────
    op.execute(
        """
        UPDATE progress p
        SET enrollment_id = e.id
        FROM enrollments e
        WHERE p.user_id = e.student_id
          AND p.course_id = e.course_id
        """
    )

    # Delete orphaned progress rows (no matching enrollment)
    op.execute("DELETE FROM progress WHERE enrollment_id IS NULL")

    # ── 3. Backfill progress_percentage for existing rows ─────────
    # Existing rows are already "completed" (that's how the old system worked),
    # so set them to 100.00
    op.execute("UPDATE progress SET progress_percentage = 100.00")

    # ── 4. Backfill updated_at from completed_at for existing rows
    op.execute("UPDATE progress SET updated_at = completed_at")

    # ── 5. Make enrollment_id NOT NULL ────────────────────────────
    op.alter_column("progress", "enrollment_id", nullable=False)

    # ── 6. Make completed_at NULLABLE ─────────────────────────────
    # (was NOT NULL before — now only set when progress = 100%)
    op.alter_column("progress", "completed_at", nullable=True)

    # ── 7. Add FK constraint for enrollment_id ────────────────────
    op.create_foreign_key(
        "fk_progress_enrollment",
        "progress",
        "enrollments",
        ["enrollment_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ── 8. Drop old unique index and indexes ─────────────────────
    # Note: a1b2c3d4e5f6 created uq_progress_user_item as a unique INDEX, not a constraint
    op.drop_index("uq_progress_user_item", table_name="progress")
    op.drop_index("ix_progress_course_id", table_name="progress")
    op.drop_index("ix_progress_user_course", table_name="progress")

    # ── 9. Drop course_id column ──────────────────────────────────
    op.drop_column("progress", "course_id")

    # ── 10. Create new unique constraint and indexes ──────────────
    op.create_unique_constraint(
        "uq_progress_user_enrollment_item",
        "progress",
        ["user_id", "enrollment_id", "item_type", "item_id"],
    )
    op.create_index("ix_progress_enrollment_id", "progress", ["enrollment_id"])
    op.create_index(
        "ix_progress_user_enrollment", "progress", ["user_id", "enrollment_id"]
    )


def downgrade() -> None:
    # ── 1. Add course_id back ─────────────────────────────────────
    op.add_column(
        "progress",
        sa.Column("course_id", sa.Integer(), nullable=True),
    )

    # ── 2. Backfill course_id from enrollments ────────────────────
    op.execute(
        """
        UPDATE progress p
        SET course_id = e.course_id
        FROM enrollments e
        WHERE p.enrollment_id = e.id
        """
    )
    op.alter_column("progress", "course_id", nullable=False)

    # ── 3. Drop new constraint + indexes ──────────────────────────
    op.drop_constraint("uq_progress_user_enrollment_item", "progress", type_="unique")
    op.drop_index("ix_progress_enrollment_id", table_name="progress")
    op.drop_index("ix_progress_user_enrollment", table_name="progress")
    op.drop_constraint("fk_progress_enrollment", "progress", type_="foreignkey")

    # ── 4. Drop new columns ───────────────────────────────────────
    op.drop_column("progress", "enrollment_id")
    op.drop_column("progress", "progress_percentage")
    op.drop_column("progress", "updated_at")

    # ── 5. Restore completed_at to NOT NULL ───────────────────────
    op.alter_column("progress", "completed_at", nullable=False)

    # ── 6. Recreate old unique index + indexes (matches a1b2c3d4e5f6) ───
    op.create_index(
        "uq_progress_user_item",
        "progress",
        ["user_id", "item_type", "item_id"],
        unique=True,
    )
    op.create_index("ix_progress_course_id", "progress", ["course_id"])
    op.create_index("ix_progress_user_course", "progress", ["user_id", "course_id"])
