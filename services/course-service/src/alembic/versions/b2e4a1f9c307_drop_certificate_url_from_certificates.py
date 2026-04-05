"""drop certificate_url from certificates

Revision ID: b2e4a1f9c307
Revises: 97fa588fd686
Create Date: 2026-04-05 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b2e4a1f9c307"
down_revision = "97fa588fd686"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("certificates", "certificate_url")


def downgrade() -> None:
    op.add_column(
        "certificates",
        sa.Column("certificate_url", sa.String(length=500), nullable=True),
    )
