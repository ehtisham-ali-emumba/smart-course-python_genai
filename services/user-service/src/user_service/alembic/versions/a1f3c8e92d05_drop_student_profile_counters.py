"""drop total_enrollments and total_completed from student_profiles

Revision ID: a1f3c8e92d05
Revises: 9aa379d36b3d
Create Date: 2026-04-05

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1f3c8e92d05'
down_revision = '9aa379d36b3d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('student_profiles', 'total_enrollments')
    op.drop_column('student_profiles', 'total_completed')


def downgrade() -> None:
    op.add_column('student_profiles', sa.Column('total_enrollments', sa.Integer(), server_default='0', nullable=False))
    op.add_column('student_profiles', sa.Column('total_completed', sa.Integer(), server_default='0', nullable=False))
