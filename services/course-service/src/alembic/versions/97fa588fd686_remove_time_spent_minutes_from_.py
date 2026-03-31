"""remove time_spent_minutes from enrollments

Revision ID: 97fa588fd686
Revises: 5d9ec67bf16f
Create Date: 2026-03-31 07:02:36.515543

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "97fa588fd686"
down_revision = "5d9ec67bf16f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("enrollments", "time_spent_minutes")


def downgrade() -> None:
    op.add_column(
        "enrollments",
        sa.Column("time_spent_minutes", sa.Integer(), nullable=False, server_default="0"),
    )
