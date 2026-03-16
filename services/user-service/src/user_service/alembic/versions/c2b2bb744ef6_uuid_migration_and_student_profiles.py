"""uuid_migration_and_student_profiles

Revision ID: c2b2bb744ef6
Revises:
Create Date: 2026-03-16 13:00:17.818149

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "c2b2bb744ef6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "role", sa.String(length=50), nullable=False, server_default=sa.text("'student'")
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("phone_number", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "student_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("interests", sa.String(length=500), nullable=True),
        sa.Column("education_level", sa.String(length=100), nullable=True),
        sa.Column("profile_picture_url", sa.String(length=500), nullable=True),
        sa.Column("total_enrollments", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_completed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "instructor_profiles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("expertise", sa.String(length=500), nullable=True),
        sa.Column("profile_picture_url", sa.String(length=500), nullable=True),
        sa.Column("phone_number", sa.String(length=20), nullable=True),
        sa.Column("total_students", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_courses", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("average_rating", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column(
            "is_verified_instructor", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("verification_date", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("instructor_profiles")
    op.drop_table("student_profiles")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
