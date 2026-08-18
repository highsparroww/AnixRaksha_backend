"""remove manual government signal requirement

Revision ID: e8f4c2b6a901
Revises: d7e2a1f4b806
"""

from alembic import op

revision = "e8f4c2b6a901"
down_revision = "d7e2a1f4b806"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("surveillance_signals", "collected_by_user_id", nullable=True)


def downgrade() -> None:
    op.alter_column("surveillance_signals", "collected_by_user_id", nullable=False)
