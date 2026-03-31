"""remove interests and expertise columns

Revision ID: 9aa379d36b3d
Revises: c2b2bb744ef6
Create Date: 2026-03-31 07:03:10.522338

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "9aa379d36b3d"
down_revision = "c2b2bb744ef6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("student_profiles", "interests")
    op.drop_column("instructor_profiles", "expertise")


def downgrade() -> None:
    op.add_column("student_profiles", sa.Column("interests", sa.String(length=500), nullable=True))
    op.add_column(
        "instructor_profiles", sa.Column("expertise", sa.String(length=500), nullable=True)
    )
