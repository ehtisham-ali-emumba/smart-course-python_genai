"""initial_baseline

Revision ID: 4ac6063c6f0a
Revises:
Create Date: 2026-02-11 09:17:28.160331

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4ac6063c6f0a"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("phone_number", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # Create instructor_profiles table
    op.create_table(
        "instructor_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("expertise", sa.String(length=500), nullable=True),
        sa.Column("profile_picture_url", sa.String(length=500), nullable=True),
        sa.Column("phone_number", sa.String(length=20), nullable=True),
        sa.Column("total_students", sa.Integer(), nullable=False),
        sa.Column("total_courses", sa.Integer(), nullable=False),
        sa.Column("average_rating", sa.Float(), nullable=False),
        sa.Column("is_verified_instructor", sa.Integer(), nullable=False),
        sa.Column("verification_date", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_instructor_profiles_id"), "instructor_profiles", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_instructor_profiles_id"), table_name="instructor_profiles")
    op.drop_table("instructor_profiles")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users")
