"""add quiz_version to quiz_attempts

Revision ID: 5d9ec67bf16f
Revises: 3e9d0ce09e7f
Create Date: 2026-03-18 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5d9ec67bf16f"
down_revision: Union[str, None] = "3e9d0ce09e7f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("quiz_attempts", sa.Column("quiz_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("quiz_attempts", "quiz_version")